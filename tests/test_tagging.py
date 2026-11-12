from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from image_dataset_train.captions import caption_record, check_rules
from image_dataset_train.config import CaptionConfig, Config, TaggingConfig, ValidationConfig
from image_dataset_train.inventory import file_sha256
from image_dataset_train.model_bundle import (
    MODELS,
    Label,
    ModelBundle,
    atomic_json,
    bundle_path,
    fetch_bundle,
    fingerprint,
    load_bundle,
    read_labels,
)
from image_dataset_train.runs import run_scan
from image_dataset_train.score_cache import ScoreCache
from image_dataset_train.tagging import recaption, tag_inventory
from image_dataset_train.wd_tagger import WDTagger, prepare_image, validate_scores


@pytest.fixture
def labels() -> list[Label]:
    # Ratings deliberately interleaved. A character has no parentheses, a general tag does.
    return [
        Label(0, "blue_hair", 0),
        Label(1, "general", 9),
        Label(2, "hatsune_miku", 4),
        Label(3, "^_^", 0),
        Label(4, "1girl", 0),
        Label(5, "solo", 0),
        Label(6, "2girls", 0),
        Label(7, "pose_(test)", 0),
    ]


def make_bundle(
    directory: Path,
    labels: list[Label],
    fixed_batch: int | None = None,
    *,
    model_name: str = "swinv2-v3",
    revision: str | None = None,
) -> ModelBundle:
    directory.mkdir(parents=True)
    count = len(labels)
    batch = fixed_batch or "batch"
    # A real, small ONNX graph: each image's mean brightness becomes a vector of scores.
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["images"], ["mean"], axes=[1, 2, 3], keepdims=0),
            helper.make_node("Div", ["mean", "scale"], ["normalized"]),
            helper.make_node("Unsqueeze", ["normalized", "axes"], ["column"]),
            helper.make_node("Mul", ["column", "weights"], ["scores"]),
        ],
        "fixture-wd-contract",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [batch, 8, 8, 3])],
        [helper.make_tensor_value_info("scores", TensorProto.FLOAT, [batch, count])],
        [
            numpy_helper.from_array(np.array(255, dtype=np.float32), "scale"),
            numpy_helper.from_array(np.array([1], dtype=np.int64), "axes"),
            numpy_helper.from_array(
                np.linspace(0.2, 1.0, count, dtype=np.float32)[None, :], "weights"
            ),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=10)
    onnx.checker.check_model(model)
    onnx.save(model, directory / "model.onnx")
    text = "name,category\n" + "".join(f"{label.name},{label.category}\n" for label in labels)
    (directory / "selected_tags.csv").write_text(text, encoding="utf-8")
    # Synthetic graph bytes model the configured identity contract; these fixtures
    # are not publisher weights and receive no production validation exemption.
    spec = MODELS[model_name]
    identity = {
        "repo": spec.repo,
        "revision": spec.revision if revision is None else revision,
        "files": {
            name: file_sha256(directory / name) for name in ("model.onnx", "selected_tags.csv")
        },
    }
    atomic_json(
        directory / "model.json",
        {
            "schema_version": 1,
            "family": "wd-v3",
            "model": model_name,
            **identity,
            "artifact_id": fingerprint(identity),
            "label_count": count,
        },
    )
    return load_bundle(directory)


@pytest.fixture
def setup(tmp_path: Path, labels: list[Label]) -> tuple[Config, Path]:
    source = tmp_path / "originals"
    source.mkdir()
    Image.new("RGB", (20, 40), "white").save(source / "white.png")
    Image.new("RGB", (40, 20), "black").save(source / "black.png")
    (source / "copy.png").write_bytes((source / "white.png").read_bytes())
    (source / "white.txt").write_text("manual caption", encoding="utf-8")
    (source / "bad.jpg").write_bytes(b"broken")
    config = Config(
        source,
        tmp_path / "runs",
        ValidationConfig(min_short_side=8),
        models=tmp_path / "models",
        scores=tmp_path / "cache",
        tagging=TaggingConfig(device="cpu", batch_size=2),
    )
    make_bundle(bundle_path(config.models, config.tagging.model), labels)
    inventory, _ = run_scan(config)
    return config, inventory


def read_rows(run: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_categories_follow_original_csv_positions(tmp_path: Path, labels: list[Label]) -> None:
    bundle = make_bundle(tmp_path / "model", labels)
    assert bundle.labels == labels
    scores = np.full(len(labels), 0.9, dtype=np.float32)
    result = caption_record(bundle.labels, scores, CaptionConfig(), 0.35)
    names = {item["name"] for item in result["selected_tags"]}
    assert "hatsune_miku" not in names
    assert "pose_(test)" in names
    assert "general" not in names
    assert result["ratings"]["general"] == pytest.approx(0.9)
    assert "^_^" in result["caption"]
    assert "blue hair" in result["caption"]


def test_threshold_override_and_drop_rules(labels: list[Label]) -> None:
    scores = np.full(len(labels), 0.7, dtype=np.float32)
    rules = CaptionConfig(
        keep_characters=True,
        character_threshold=0.9,
        drop_tags=["blue_hair"],
        tag_thresholds={"hatsune_miku": 0.6},
    )
    check_rules(labels, rules)
    names = {item["name"] for item in caption_record(labels, scores, rules, 0.35)["selected_tags"]}
    assert "hatsune_miku" in names and "blue_hair" not in names
    with pytest.raises(ValueError, match="unknown raw tags"):
        check_rules(labels, CaptionConfig(tag_thresholds={"blue hair": 0.5}))


def test_conflicts_are_reported_without_inventing_or_removing_tags(labels: list[Label]) -> None:
    scores = np.full(len(labels), 0.9, dtype=np.float32)
    result = caption_record(labels, scores, CaptionConfig(), 0.35)
    assert "conflicting_girl_counts" in result["review_flags"]
    assert "solo_count_conflict" in result["review_flags"]
    assert {"1girl", "2girls", "solo"}.issubset({tag["name"] for tag in result["selected_tags"]})
    assert "nude" not in result["caption"]


def test_exact_threshold_is_excluded_and_uncertainty_is_retained(labels: list[Label]) -> None:
    scores = np.full(len(labels), 0.5, dtype=np.float32)
    result = caption_record(labels, scores, CaptionConfig(general_threshold=0.5), 0.35)
    assert result["caption"] == ""
    assert "empty_caption" in result["review_flags"]
    assert result["uncertain_tags"]


def test_caption_additions_do_not_become_subset_or_composition_evidence(labels):
    scores = np.array([0.9, 0.9, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1], dtype=np.float32)
    rules = CaptionConfig(
        trigger="custom style",
        force_tags=["blue hair", "2girls", "BLUE HAIR"],
        drop_tags=["blue_hair", "1girl"],
        subset_rules=[{"name": "Blue", "all_tags": ["blue_hair"], "expect_tags": ["pose_(test)"]}],
    )
    check_rules(labels, rules)
    result = caption_record(labels, scores, rules, 0.35)
    assert result["caption"] == "custom style, blue hair, 2girls"
    assert result["selected_tags"] == [] and result["composition"] == "single_subject"
    assert {item["name"] for item in result["observed_tags"]} == {"blue_hair", "1girl"}
    assert result["subset_proposal"] == {
        "value": "blue",
        "matches": ["blue"],
        "missing_tags": {"blue": ["pose_(test)"]},
    }
    assert "subset_missing_expected_tags" in result["review_flags"]
    # Removing caption evidence neither repairs conflicting counts nor hides them.
    scores[6] = 0.9
    conflict = caption_record(labels, scores, replace(rules, drop_tags=["1girl", "2girls"]), 0.35)
    assert conflict["composition"] == "unknown"
    assert "conflicting_girl_counts" in conflict["review_flags"]
    overlapping = replace(
        rules,
        subset_rules=[
            {"name": "blue", "any_tags": ["blue_hair"], "none_tags": ["solo"]},
            {"name": "counted", "all_tags": ["1girl"]},
        ],
    )
    result = caption_record(labels, scores, overlapping, 0.35)
    assert result["subset_proposal"]["value"] is None
    assert result["subset_proposal"]["matches"] == ["blue", "counted"]
    assert "subset_rule_conflict" in result["review_flags"]
    scores[0] = 0.1
    assert not caption_record(labels, scores, rules, 0.35)["subset_proposal"]["missing_tags"]


def test_subset_rule_configuration_rejects_ambiguous_schema_and_unknown_evidence(labels):
    for options in (
        {"trigger": "two, phrases"},
        {"force_tags": [""]},
        {"subset_rules": [{"name": "missing predicate"}]},
        {"subset_rules": [{"name": "x", "all_tags": ["solo"], "none_tags": ["solo"]}]},
        {"subset_rules": [{"name": "x", "any_tags": ["solo"], "typo": True}]},
    ):
        with pytest.raises(ValueError):
            CaptionConfig(**options)
    for tag in ("blue hair", "general"):
        with pytest.raises(ValueError):
            check_rules(labels, CaptionConfig(subset_rules=[{"name": "x", "all_tags": [tag]}]))


def test_geometry_channel_order_and_transparency() -> None:
    image = Image.new("RGBA", (2, 4), (10, 20, 30, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    array = prepare_image(image, 4)
    assert array.shape == (4, 4, 3) and array.dtype == np.float32
    assert array.flags.c_contiguous
    np.testing.assert_array_equal(array[:, 0], 255)
    np.testing.assert_array_equal(array[:, 3], 255)
    np.testing.assert_array_equal(array[0, 1], [255, 255, 255])
    np.testing.assert_array_equal(array[1, 1], [30, 20, 10])


def test_exif_orientation_is_applied_without_altering_input() -> None:
    image = Image.new("RGB", (2, 4), "red")
    image.getexif()[274] = 6
    result = prepare_image(image, 4)
    assert image.size == (2, 4)
    np.testing.assert_array_equal(result[0], 255)
    np.testing.assert_array_equal(result[1, 0], [0, 0, 255])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_score_values_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        validate_scores(np.array([value], dtype=np.float32), 1)


def test_invalid_label_csv_and_bundle_mutation(tmp_path: Path, labels: list[Label]) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("name,category\ntag,0\ntag,4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_labels(path)
    bundle = make_bundle(tmp_path / "bundle", labels)
    (bundle.directory / "selected_tags.csv").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_bundle(bundle.directory)


def test_fetch_pins_both_files_and_reuses_verified_bundle(
    tmp_path: Path, labels: list[Label], monkeypatch: pytest.MonkeyPatch
) -> None:
    import huggingface_hub

    fixture = make_bundle(tmp_path / "fixture", labels)
    requests = []

    def download(**kwargs):
        requests.append(kwargs)
        destination = Path(kwargs["local_dir"]) / kwargs["filename"]
        shutil.copyfile(fixture.directory / kwargs["filename"], destination)
        return str(destination)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    root = tmp_path / "downloads"
    directory = fetch_bundle(root, "swinv2-v3")
    assert len(requests) == 2
    assert {request["revision"] for request in requests} == {MODELS["swinv2-v3"].revision}
    assert all(request["token"] is False for request in requests)
    assert fetch_bundle(root, "swinv2-v3") == directory
    assert len(requests) == 2


def test_real_onnx_runtime_handles_batches_and_checks_label_count(
    tmp_path: Path, labels: list[Label]
) -> None:
    bundle = make_bundle(tmp_path / "bundle", labels)
    tagger = WDTagger(bundle, "cpu")
    batch = np.stack(
        [np.zeros((8, 8, 3), dtype=np.float32), np.full((8, 8, 3), 255, dtype=np.float32)]
    )
    result = tagger.predict(batch)
    assert result.shape == (2, len(labels))
    np.testing.assert_array_equal(result[0], 0)
    np.testing.assert_allclose(result[1], np.linspace(0.2, 1, len(labels)), atol=1e-6)
    with pytest.raises(ValueError, match="label count"):
        WDTagger(ModelBundle(bundle.directory, bundle.metadata, labels[:-1]), "cpu")


def test_explicit_cuda_refuses_silent_fallback(
    tmp_path: Path, labels: list[Label], monkeypatch: pytest.MonkeyPatch
) -> None:
    import image_dataset_train.wd_tagger as module

    bundle = make_bundle(tmp_path / "bundle", labels)
    monkeypatch.setattr(module.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    with pytest.raises(RuntimeError, match="unavailable"):
        WDTagger(bundle, "cuda")
    automatic = WDTagger(bundle, "auto")
    assert automatic.fallback == "CUDA unavailable; using CPU"


def test_tag_rerun_cache_and_source_preservation(
    setup: tuple[Config, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory = setup
    before = {p.name: p.read_bytes() for p in config.source.iterdir()}
    first, summary = tag_inventory(config, inventory)
    assert summary["inferred_images"] == 2
    assert summary["duplicate_score_reuse"] == 1
    assert summary["decisions"] == {"skipped": 1, "tagged": 3}

    def should_not_infer(*args, **kwargs):
        pytest.fail("cache hit unexpectedly ran inference")

    monkeypatch.setattr(WDTagger, "predict", should_not_infer)
    second, cached = tag_inventory(config, inventory)
    assert cached["inferred_images"] == 0 and cached["cached_images"] == 2
    assert (first / "manifest.jsonl").read_bytes() == (second / "manifest.jsonl").read_bytes()
    assert before == {p.name: p.read_bytes() for p in config.source.iterdir()}
    assert len(list((first / "captions").glob("*.txt"))) == 3
    assert len(list((first / "scores").glob("*.npy"))) == 2


def test_source_changes_are_rejected_even_on_cache_hit(setup: tuple[Config, Path]) -> None:
    config, inventory = setup
    tag_inventory(config, inventory)
    (config.source / "white.png").write_bytes(b"changed")
    directory, summary = tag_inventory(config, inventory)
    assert summary["decisions"]["error"] == 1
    row = next(row for row in read_rows(directory) if row["source_path"] == "white.png")
    assert "source_changed_since_inventory" in row["error"]
    assert "caption_path" not in row


def test_square_allocation_limit_applies_to_cached_images(setup: tuple[Config, Path]) -> None:
    config, inventory = setup
    tag_inventory(config, inventory)
    # Original 20x40 pixels fit, but padding to 40x40 would exceed this limit.
    constrained = replace(config, validation=replace(config.validation, max_decode_pixels=1000))
    _, summary = tag_inventory(constrained, inventory)
    assert summary["decisions"]["error"] == 3
    assert summary["inferred_images"] == 0 and summary["cached_images"] == 0


@pytest.mark.parametrize(
    "options",
    [
        {"device": []},
        {"model": []},
        {"revision": ""},
        {"revision": "main"},
        {"revision": True},
        {"batch_size": 0},
        {"batch_size": True},
    ],
)
def test_invalid_tagging_config_rejected(options: dict) -> None:
    with pytest.raises(ValueError):
        TaggingConfig(**options)


def test_recaption_uses_scores_without_source_model_or_inference(
    setup: tuple[Config, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory = setup
    first, _ = tag_inventory(config, inventory)
    before = (first / "manifest.jsonl").read_bytes()
    config.source.rename(config.source.with_name("moved-originals"))
    config.models.rename(config.models.with_name("moved-models"))

    def no_session(*args, **kwargs):
        pytest.fail("recaption initialized an ONNX session")

    monkeypatch.setattr(WDTagger, "__init__", no_session)
    changed = replace(config, captions=CaptionConfig(general_threshold=0.95))
    second, summary = recaption(changed, first)
    assert summary["inferred_images"] == 0
    assert before == (first / "manifest.jsonl").read_bytes()
    assert before != (second / "manifest.jsonl").read_bytes()
    metadata = json.loads((second / "run.json").read_text())
    assert metadata["source_revalidated"] is False


def test_modified_saved_scores_cannot_be_recaptioned(setup: tuple[Config, Path]) -> None:
    config, inventory = setup
    first, _ = tag_inventory(config, inventory)
    score = next((first / "scores").glob("*.npy"))
    score.write_bytes(b"changed")
    with pytest.raises(ValueError, match="score artifact hash mismatch"):
        recaption(config, first)


def test_cache_corruption_is_not_silently_reused(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    cache = ScoreCache(tmp_path, "test", 2)
    path = cache.put(digest, np.array([0.1, 0.9], dtype=np.float32))
    path.write_bytes(b"not a score file")
    with pytest.raises(ValueError, match="invalid score cache"):
        cache.get(digest)
    assert path.read_bytes() == b"not a score file"


def test_interrupted_inference_resumes_completed_batches(
    setup: tuple[Config, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory = setup
    config = replace(config, tagging=replace(config.tagging, batch_size=1))
    original = WDTagger.predict
    calls = 0

    def interrupt_second(self, batch):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture interruption")
        return original(self, batch)

    monkeypatch.setattr(WDTagger, "predict", interrupt_second)
    before = set(config.runs.iterdir())
    with pytest.raises(RuntimeError, match="fixture interruption"):
        tag_inventory(config, inventory)
    assert set(config.runs.iterdir()) == before
    monkeypatch.setattr(WDTagger, "predict", original)
    _, summary = tag_inventory(config, inventory)
    assert summary["inferred_images"] == 1 and summary["cached_images"] == 1


def test_fixed_batch_one_model_is_respected(
    setup: tuple[Config, Path], tmp_path: Path, labels: list[Label]
) -> None:
    config, inventory = setup
    alternate = tmp_path / "fixed-models"
    make_bundle(bundle_path(alternate, config.tagging.model), labels, fixed_batch=1)
    directory, summary = tag_inventory(replace(config, models=alternate), inventory)
    assert summary["inferred_images"] == 2
    assert json.loads((directory / "run.json").read_text())["batch_size"] == 1


def test_inventory_tampering_is_rejected(setup: tuple[Config, Path]) -> None:
    config, inventory = setup
    with (inventory / "manifest.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        tag_inventory(config, inventory)


def test_threshold_profiles_are_not_accidentally_shared() -> None:
    assert MODELS["eva02-large-v3"].suggested_general_threshold == 0.5296
    assert MODELS["swinv2-v3"].suggested_general_threshold == 0.35


@pytest.mark.parametrize(
    "options",
    [
        {"general_threshold": float("nan")},
        {"character_threshold": 1.1},
        {"keep_characters": "false"},
        {"tag_thresholds": {"test": True}},
    ],
)
def test_invalid_caption_rules_rejected(options: dict) -> None:
    with pytest.raises(ValueError):
        CaptionConfig(**options)
