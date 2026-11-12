"""CLI selection stays pinned, offline, and free of application writes."""

import builtins
import hashlib
import json
from dataclasses import asdict

import numpy as np
import pytest
from PIL import Image

from image_dataset_train import caption_explanations, preparation
from image_dataset_train.cli import main
from image_dataset_train.collection_registry import CollectionRegistry
from image_dataset_train.config import CaptionConfig, Config, SubsetRule, ValidationConfig
from image_dataset_train.model_bundle import MODELS, Label
from image_dataset_train.tagging import _publish


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def scored(tmp_path):
    source = tmp_path / "source [猫]"
    source.mkdir()
    rules = CaptionConfig(
        general_threshold=0.5,
        tag_thresholds={"near_cutoff": 0.35},
        drop_tags=["dropped_tag"],
        trigger="blue hair",
        force_tags=["fixture", "BLUE HAIR"],
        subset_rules=[SubsetRule("portrait", all_tags=["blue_hair"], expect_tags=["low_tag"])],
    )
    labels = [
        Label(0, "blue_hair", 0),
        Label(1, "dropped_tag", 0),
        Label(2, "character_name", 4),
        Label(3, "low_tag", 0),
        Label(4, "general", 9),
        Label(5, "near_cutoff", 0),
    ]
    identity = hashlib.sha256(b"generated offline fixture").hexdigest()
    run = _publish(
        tmp_path / "saved runs [猫]",
        [{"source_path": "portrait [猫].png", "sha256": identity, "decision": "tagged"}],
        {
            identity: np.array(
                [0.9, 0.8, 0.9, 0.1, 0.9, np.nextafter(np.float32(0.35), np.float32(1))],
                dtype=np.float32,
            )
        },
        labels,
        {"stage": "tagging", "source": str(source)},
        {},
        rules,
        0.35,
    )
    source.rmdir()
    return run


def invoke(capsys, *args, expect=0):
    assert main(["caption-explain", *map(str, args), "--json"]) == expect
    return json.loads(capsys.readouterr().out)


def test_explicit_run_unicode_paging_omission_and_read_only(scored, tmp_path, capsys):
    before = tree(tmp_path)
    result = invoke(capsys, "--run", scored, "--image", "portrait [猫].png", "--limit", 2)
    assert result["status"] == "available" and result["selection"]["kind"] == "run"
    assert len(result["tags"]) == 2 and result["has_more"]
    remaining = invoke(
        capsys, "--run", scored, "--image", "portrait [猫].png", "--offset", 2, "--limit", 2
    )
    assert result["tags"][0]["index"] < remaining["tags"][0]["index"]
    tag = invoke(capsys, "--run", scored, "--image", "portrait [猫].png", "--tag", "low_tag")[
        "tags"
    ][0]
    assert tag["reasons"] == ["below_or_equal_threshold"] and not tag["selected"]
    assert tree(tmp_path) == before


def test_human_output_explains_thresholds_subsets_and_additions(scored, capsys):
    assert main(["caption-explain", "--run", str(scored), "--image", "portrait [猫].png"]) == 0
    output = capsys.readouterr().out
    for phrase in (
        "strictly > 0.5",
        "explicit_drop",
        "characters_disabled",
        "rating only",
        "portrait: matched",
        "expected: low_tag; missing low_tag",
        "Trigger: blue hair",
        "Forced phrases: fixture, BLUE HAIR",
        "Duplicate phrase omitted",
        "Run SHA-256:",
        "near_cutoff: score 0.3500000238418579; strictly > 0.35",
    ):
        assert phrase in output
    assert "{'" not in output


@pytest.mark.parametrize(
    "extra",
    [
        ["--job", "anything"],
        ["--tag", "unknown"],
        ["--limit", "0"],
        ["--offset", "-1"],
        ["--tag", "low_tag", "--tag", "low_tag"],
    ],
)
def test_bad_arguments_are_json_errors_without_logs(scored, tmp_path, capsys, extra):
    before = tree(tmp_path)
    result = invoke(capsys, "--run", scored, "--image", "portrait [猫].png", *extra, expect=2)
    assert result["status"] == "failed" and result["error"]["type"] == "ValueError"
    assert tree(tmp_path) == before


def test_unknown_exact_image_and_corrupted_vector_are_errors(scored, capsys, tmp_path):
    invoke(capsys, "--run", scored, "--image", "missing.png", expect=2)
    vector = next((scored / "scores").glob("*.npy"))
    vector.write_bytes(b"damaged retained fixture")
    before = tree(tmp_path)
    result = invoke(capsys, "--run", scored, "--image", "portrait [猫].png", expect=2)
    assert "hash mismatch" in result["error"]["message"].lower()
    assert tree(tmp_path) == before


def test_unsupported_rules_are_successful_unavailable_inspection(scored, capsys):
    meta = read(scored / "run.json")
    meta["caption_version"] = "legacy-caption-fixture"
    save(scored / "run.json", meta)
    result = invoke(capsys, "--run", scored, "--image", "portrait [猫].png")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "unsupported_caption_version"


def test_help_does_not_import_numpy_and_dependency_errors_do_not_log(
    scored, capsys, tmp_path, monkeypatch
):
    importer = builtins.__import__

    def guard(name, *args, **kwargs):
        if name in {"numpy", "image_dataset_train.caption_explanations"}:
            raise ImportError("controlled missing optional dependency")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    before = tree(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["caption-explain", "--help"])
    assert exc.value.code == 0
    capsys.readouterr()
    result = invoke(capsys, "--run", scored, "--image", "portrait [猫].png", expect=2)
    assert "image-dataset-train[tag-cpu]" in result["error"]["message"]
    assert tree(tmp_path) == before


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    source, workspace = tmp_path / "images [猫]", tmp_path / "prepared [猫]"
    source.mkdir()
    Image.new("RGB", (128, 128), "blue").save(source / "portrait [猫].png")
    Image.new("RGB", (128, 128), "red").save(source / "other.png")
    config = preparation.preparation_config(
        source,
        workspace,
        base=Config(
            source,
            workspace / "runs",
            ValidationConfig(min_short_side=64),
            models=tmp_path / "no models",
            reviews=workspace / "reviews",
            scores=tmp_path / "no score cache",
            exports=workspace / "exports",
        ),
    )
    original = preparation._execute

    def execute(stage, config, job, state, progress):
        if stage == "groups":
            raise RuntimeError("Generated checkpoint fixture stops before groups")
        if stage != "tagging":
            return original(stage, config, job, state, progress)
        inventory = job / state["stages"]["inventory"]["output"]
        metadata = read(inventory / "run.json")
        rows = [
            json.loads(line) for line in (inventory / "manifest.jsonl").read_text().splitlines()
        ]
        rows = [
            {"source_path": r["source_path"], "sha256": r["sha256"], "decision": "tagged"}
            for r in rows
            if r["kind"] == "image"
        ]
        spec = MODELS[config.tagging.model]
        state["model_identity"] = {
            "generated": True,
            "model": config.tagging.model,
            "repo": spec.repo,
            "revision": config.tagging.revision or spec.revision,
        }
        return _publish(
            config.runs,
            rows,
            {r["sha256"]: np.array([0.9], dtype=np.float32) for r in rows},
            [Label(0, "blue_hair", 0)],
            {
                "stage": "tagging",
                "source": str(source),
                "inventory_run": str(inventory),
                "inventory_manifest_sha256": metadata["manifest_sha256"],
                "model": state["model_identity"],
                "requested_device": config.tagging.device,
                "validation": asdict(config.validation),
            },
            {},
            config.captions,
            0.35,
        )

    with monkeypatch.context() as fixture_patch:
        fixture_patch.setattr(preparation, "_execute", execute)
        for _ in range(2):
            with pytest.raises(RuntimeError, match="Generated checkpoint"):
                preparation.prepare_directory(config, workspace, new=True, progress=lambda _: None)
    jobs = sorted((workspace / "jobs").iterdir())
    source.rename(tmp_path / "offline source")
    return workspace, jobs


def test_workspace_current_and_historical_collection_are_exact_and_offline(
    workspace, tmp_path, capsys
):
    root, jobs = workspace
    registry = CollectionRegistry()
    registry.register(root, "saved fixture")
    before = tree(tmp_path)
    current = invoke(capsys, "--workspace", root, "--image", "portrait [猫].png")
    historical = invoke(
        capsys,
        "--collection",
        "saved fixture",
        "--job",
        jobs[0].name,
        "--image",
        "portrait [猫].png",
    )
    assert current["selection"]["job_id"] == jobs[-1].name
    assert historical["selection"]["job_id"] == jobs[0].name
    assert historical["run"] != current["run"] and tree(tmp_path) == before


@pytest.mark.parametrize("mode", ["missing", "running", "checksum", "inventory"])
def test_workspace_rejects_incomplete_or_inconsistent_tagging(workspace, capsys, mode):
    root, jobs = workspace
    job = jobs[-1] / "job.json"
    state = read(job)
    record = state["stages"]["tagging"]
    if mode == "missing":
        del state["stages"]["tagging"]
    elif mode == "running":
        record["status"] = "running"
    elif mode == "checksum":
        record["files"]["run.json"] = "0" * 64
    else:
        path = jobs[-1] / record["output"] / "run.json"
        meta = read(path)
        meta["inventory_manifest_sha256"] = "0" * 64
        save(path, meta)
        record["files"]["run.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(job, state)
    assert (
        invoke(capsys, "--workspace", root, "--image", "portrait [猫].png", expect=2)["status"]
        == "failed"
    )


def test_workspace_checks_selection_again_after_explanation(workspace, capsys, monkeypatch):
    root, jobs = workspace
    original = caption_explanations.explain_caption

    def race(*args, **kwargs):
        result = original(*args, **kwargs)
        path = jobs[-1] / "job.json"
        state = read(path)
        state["race_probe"] = True
        save(path, state)
        return result

    monkeypatch.setattr(caption_explanations, "explain_caption", race)
    result = invoke(capsys, "--workspace", root, "--image", "portrait [猫].png", expect=2)
    assert "changed during inspection" in result["error"]["message"]


def test_workspace_does_not_read_unselected_score_vectors(workspace, capsys):
    root, jobs = workspace
    state = read(jobs[-1] / "job.json")
    run = jobs[-1] / state["stages"]["tagging"]["output"]
    rows = [json.loads(line) for line in (run / "manifest.jsonl").read_text().splitlines()]
    other = next(row for row in rows if row["source_path"] == "other.png")
    (run / "scores" / f"{other['sha256']}.npy").write_bytes(b"unselected corrupted fixture")
    result = invoke(capsys, "--workspace", root, "--image", "portrait [猫].png")
    assert result["status"] == "available"


@pytest.mark.parametrize("mode", ["current", "historical_source"])
def test_workspace_rejects_transient_binding_selection(workspace, capsys, monkeypatch, mode):
    root, jobs = workspace
    path = root / "collection.json"
    original_bytes = path.read_bytes()
    captured = json.loads(original_bytes)
    transient = dict(captured)
    extra = []
    if mode == "current":
        transient["job"] = "jobs/" + jobs[0].name
    else:
        captured["source"] = str(root.parent / "unrelated source")
        save(path, captured)
        extra = ["--job", jobs[0].name]
    captured_bytes = path.read_bytes()
    original = preparation.read_preparation_job

    def race(*args, **kwargs):
        save(path, transient)
        try:
            return original(*args, **kwargs)
        finally:
            path.write_bytes(captured_bytes)

    monkeypatch.setattr(preparation, "read_preparation_job", race)
    result = invoke(capsys, "--workspace", root, "--image", "portrait [猫].png", *extra, expect=2)
    assert "captured collection binding" in result["error"]["message"]
    assert path.read_bytes() == captured_bytes


def test_collection_rejects_transient_registry_selection(workspace, capsys, monkeypatch):
    root, _ = workspace
    registry = CollectionRegistry()
    registry.register(root, "saved fixture")
    raw = registry.path.read_bytes()
    transient = json.loads(raw)
    transient["collections"][0]["registered_at"] = "2020-01-01T00:00:00+00:00"
    original = CollectionRegistry.read

    def race(current):
        save(current.path, transient)
        try:
            return original(current)
        finally:
            current.path.write_bytes(raw)

    monkeypatch.setattr(CollectionRegistry, "read", race)
    result = invoke(
        capsys, "--collection", "saved fixture", "--image", "portrait [猫].png", expect=2
    )
    assert "registration changed" in result["error"]["message"]
    assert registry.path.read_bytes() == raw
