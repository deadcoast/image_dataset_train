from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from test_tagging import make_bundle

from image_dataset_train.cache_inspection import inspect_inference_cache
from image_dataset_train.config import Config, TaggingConfig, ValidationConfig
from image_dataset_train.inventory_data import read_inventory
from image_dataset_train.model_bundle import Label, atomic_json, bundle_path
from image_dataset_train.runs import run_scan
from image_dataset_train.score_cache import ScoreCache
from image_dataset_train.wd_tagger import WDTagger


@pytest.fixture
def cache_case(tmp_path: Path) -> tuple:
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
    bundle = make_bundle(
        bundle_path(config.models, config.tagging.model),
        [Label(0, "white", 0), Label(1, "black", 0)],
    )
    inventory, _ = run_scan(config)
    tagger = WDTagger(bundle, "cpu")
    cache = ScoreCache(config.scores, tagger.cache_namespace, len(bundle.labels))
    digests = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.glob("*.png")
    }
    return config, inventory, bundle, tagger, cache, digests


def _snapshot(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in root.rglob("*")
    }


def _forbid_writes_and_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("cache inspection attempted inference, download, or application mutation")

    monkeypatch.setattr(WDTagger, "predict", forbidden)
    monkeypatch.setattr("image_dataset_train.wd_tagger.ort.InferenceSession.run", forbidden)
    monkeypatch.setattr("image_dataset_train.model_bundle.fetch_bundle", forbidden)
    monkeypatch.setattr(ScoreCache, "put", forbidden)
    monkeypatch.setattr("image_dataset_train.doctor.preserve", forbidden)
    monkeypatch.setattr("image_dataset_train.diagnostics.EventLog.exception", forbidden)


def _rewrite_inventory(inventory: Path, transform) -> None:
    metadata, rows, _ = read_inventory(inventory)
    transform(rows)
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (inventory / "manifest.jsonl").write_bytes(raw)
    metadata["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    atomic_json(inventory / "run.json", metadata)


def test_actual_cpu_session_counts_content_once_and_preserves_every_file(
    cache_case: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config, inventory, bundle, tagger, cache, digests = cache_case
    cache.put(digests["white.png"], np.array([0.2, 0.8], dtype=np.float32))
    # Unrelated entries and namespaces are outside this inspection's scope.
    unrelated = cache.path("f" * 64)
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"unrelated malformed archive")
    other = config.scores / "other-contract" / "leftover.npz"
    other.parent.mkdir()
    other.write_bytes(b"not this runtime")
    before = _snapshot(tmp_path)
    _forbid_writes_and_inference(monkeypatch)

    result = inspect_inference_cache(config, inventory, expected_model=bundle.metadata)

    assert result["status"] == "complete"
    assert result["counts"] == {"valid": 1, "missing": 1, "invalid": 0}
    assert result["eligible_occurrences"] == 3
    assert result["eligible_unique_contents"] == 2
    assert result["source_counts"] == {"verified": 3, "invalid": 0}
    assert result["runtime"] == tagger.runtime
    assert result["runtime"]["providers"] == ["CPUExecutionProvider"]
    assert result["cache_namespace"] == tagger.cache_namespace
    assert result["model_artifact_id"] == bundle.metadata["artifact_id"]
    assert result["provider_fallback"] is None
    assert result["requested_device"] == "cpu"
    assert result["application_writes"] is result["inference_performed"] is False
    entries = {entry["sha256"]: entry for entry in result["entries"]}
    assert set(entries) == {digests["black.png"], digests["white.png"]}
    assert set(entries[digests["white.png"]]["aliases"]) == {"white.png", "copy.png"}
    assert entries[digests["white.png"]]["source_errors"] == []
    assert _snapshot(tmp_path) == before


def test_missing_cache_tree_is_ordinary_work_and_is_not_created(
    cache_case: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, *_ = cache_case
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "complete"
    assert result["counts"] == {"valid": 0, "missing": 2, "invalid": 0}
    assert not config.scores.exists()


def test_corrupt_entry_is_isolated_and_preserved(
    cache_case: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config, inventory, _, _, cache, digests = cache_case
    valid = cache.put(digests["white.png"], np.array([0.2, 0.8], dtype=np.float32))
    corrupt = cache.path(digests["black.png"])
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"interrupted npz")
    before = _snapshot(tmp_path)
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "partial"
    assert result["counts"] == {"valid": 1, "missing": 0, "invalid": 1}
    assert result["source_counts"] == {"verified": 3, "invalid": 0}
    assert any(entry["path"] == str(valid) for entry in result["entries"])
    assert next(entry for entry in result["entries"] if entry["status"] == "invalid")["error"]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("mutation", ["changed_alias", "offline", "geometry", "byte_limit"])
def test_source_failures_do_not_discard_valid_stored_vectors(
    cache_case: tuple, mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, _, _, cache, digests = cache_case
    for digest in set(digests.values()):
        cache.put(digest, np.array([0.2, 0.8], dtype=np.float32))
    if mutation == "changed_alias":
        (config.source / "copy.png").write_bytes(b"changed after inventory")
        invalid = 1
    elif mutation == "offline":
        config.source.rename(config.source.with_name("offline-originals"))
        invalid = 3
    elif mutation == "geometry":

        def change(rows):
            for row in rows:
                if row["source_path"] == "copy.png":
                    row["stored_width"] = 0

        _rewrite_inventory(inventory, change)
        invalid = 1
    else:
        config = replace(config, validation=replace(config.validation, max_file_bytes=1))
        invalid = 3
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "partial"
    assert result["counts"] == {"valid": 2, "missing": 0, "invalid": 0}
    assert result["source_counts"] == {"verified": 3 - invalid, "invalid": invalid}
    assert sum(len(entry["source_errors"]) for entry in result["entries"]) == invalid


@pytest.mark.parametrize("mutation", ["missing_model", "changed_model", "changed_csv"])
def test_unavailable_model_is_unknown_not_zero_progress(
    cache_case: tuple, mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, bundle, *_ = cache_case
    if mutation == "missing_model":
        (bundle.directory / "model.json").unlink()
    elif mutation == "changed_model":
        (bundle.directory / "model.onnx").write_bytes(b"changed local model")
    else:
        (bundle.directory / "selected_tags.csv").write_text("name,category\nchanged,0\n")
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_unavailable"
    assert result["counts"] is None
    assert result["runtime"] is None
    assert result["error"]["message"]


def test_expected_model_mismatch_does_not_initialize_a_session(
    cache_case: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, bundle, *_ = cache_case

    def forbidden(*args, **kwargs):
        pytest.fail("mismatched model must not initialize a session")

    monkeypatch.setattr(WDTagger, "__init__", forbidden)
    result = inspect_inference_cache(
        config, inventory, expected_model={**bundle.metadata, "artifact_id": "f" * 64}
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_identity_changed"
    assert result["counts"] is None


@pytest.mark.parametrize("failure", ["missing_dependency", "unsupported_cuda", "session_failure"])
def test_unavailable_runtime_is_explicit(
    cache_case: tuple, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, *_ = cache_case
    if failure == "unsupported_cuda":
        config = replace(config, tagging=replace(config.tagging, device="cuda"))
        monkeypatch.setattr(
            "image_dataset_train.wd_tagger.ort.get_available_providers",
            lambda: ["CPUExecutionProvider"],
        )
    else:

        def fail(*args, **kwargs):
            if failure == "missing_dependency":
                raise ImportError("onnxruntime is unavailable")
            raise RuntimeError("local ONNX session could not initialize")

        monkeypatch.setattr(WDTagger, "__init__", fail)
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable"
    assert result["reason"] == "runtime_unavailable"
    assert result["counts"] is None
    assert result["error"]["message"]


def test_auto_cpu_fallback_uses_actual_runtime_namespace(
    cache_case: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, _, tagger, cache, digests = cache_case
    cache.put(digests["white.png"], np.array([0.2, 0.8], dtype=np.float32))
    config = replace(config, tagging=replace(config.tagging, device="auto"))
    monkeypatch.setattr(
        "image_dataset_train.wd_tagger.ort.get_available_providers",
        lambda: ["CPUExecutionProvider"],
    )
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["runtime"] == tagger.runtime
    assert result["cache_namespace"] == tagger.cache_namespace
    assert result["provider_fallback"] == "CUDA unavailable; using CPU"
    assert result["counts"]["valid"] == 1


@pytest.mark.parametrize("contract_part", ["runtime_version", "provider_options", "preprocessing"])
def test_changed_runtime_contract_does_not_reuse_another_namespace(
    cache_case: tuple, contract_part: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, _, tagger, cache, digests = cache_case
    for digest in set(digests.values()):
        cache.put(digest, np.array([0.2, 0.8], dtype=np.float32))
    if contract_part == "runtime_version":
        monkeypatch.setattr("image_dataset_train.wd_tagger.ort.__version__", "fixture-new-runtime")
    elif contract_part == "provider_options":
        monkeypatch.setattr(
            "image_dataset_train.wd_tagger.ort.InferenceSession.get_provider_options",
            lambda self: {"CPUExecutionProvider": {"fixture_changed_option": "true"}},
        )
    else:
        monkeypatch.setattr("image_dataset_train.wd_tagger.PREPROCESS_VERSION", "fixture-v2")
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "complete"
    assert result["cache_namespace"] != tagger.cache_namespace
    assert result["counts"] == {"valid": 0, "missing": 2, "invalid": 0}
    assert not (config.scores / result["cache_namespace"]).exists()


@pytest.mark.parametrize("when", ["bundle_load", "session_creation"])
def test_model_changes_during_verification_do_not_report_cache_progress(
    cache_case: tuple, when: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, bundle, *_ = cache_case
    if when == "bundle_load":
        from image_dataset_train.cache_inspection import load_bundle

        def changing_bundle(directory, **expected):
            checked = load_bundle(directory, **expected)
            (directory / "selected_tags.csv").write_bytes(b"changed during bundle load")
            return checked

        monkeypatch.setattr("image_dataset_train.cache_inspection.load_bundle", changing_bundle)
    else:
        initialize = WDTagger.__init__

        def changing_session(self, *args, **kwargs):
            initialize(self, *args, **kwargs)
            (bundle.directory / "model.onnx").write_bytes(b"changed during session creation")

        monkeypatch.setattr(WDTagger, "__init__", changing_session)
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_unavailable"
    assert result["counts"] is None
    assert "changed" in result["error"]["message"]


@pytest.mark.parametrize("mutation", ["wrong_source", "bad_manifest", "bad_row", "overlap"])
def test_inventory_or_path_failures_do_not_claim_progress(
    cache_case: tuple, mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, *_ = cache_case
    reason = "inventory_unavailable"
    if mutation == "wrong_source":
        config = replace(config, source=config.source.with_name("other-source"))
    elif mutation == "bad_manifest":
        with (inventory / "manifest.jsonl").open("ab") as stream:
            stream.write(b"{}\n")
    elif mutation == "bad_row":
        _rewrite_inventory(inventory, lambda rows: rows[0].update(source_path="../escape.png"))
    else:
        config = replace(config, scores=config.source / "scores")
        reason = "unsafe_paths"
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable"
    assert result["reason"] == reason
    assert result["counts"] is None


@pytest.mark.parametrize("linked", ["model.json", "model.onnx", "selected_tags.csv"])
def test_linked_model_files_are_rejected_before_loading(
    cache_case: tuple, linked: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, inventory, bundle, *_ = cache_case
    path = bundle.directory / linked
    target = path.with_suffix(path.suffix + ".original")
    path.rename(target)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("creating file symlinks requires Windows developer mode or permission")
    _forbid_writes_and_inference(monkeypatch)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_unavailable"
    assert "linked" in result["error"]["message"]
    assert result["counts"] is None
