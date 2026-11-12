"""Independent recovery and provenance regressions from the preparation review."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image
from test_preparation import collection as collection
from test_tagging import make_bundle

from image_dataset_train import preparation, tagging
from image_dataset_train.dataset_catalog import query_catalog, write_catalog
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import _load_groups, verify_export
from image_dataset_train.inventory import file_sha256
from image_dataset_train.model_bundle import Label, bundle_path
from image_dataset_train.preparation import (
    preparation_config,
    prepare_directory,
    resume_preparation,
)
from image_dataset_train.reviews import (
    ReviewStore,
    review_image,
    review_link,
    review_pair,
    review_status,
)
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


def _run(config, workspace, **kwargs):
    return prepare_directory(
        config, workspace, captions="existing", progress=lambda _: None, **kwargs
    )


def _review_run(config, workspace):
    staging = replace(config, runs=workspace.parent / "existing review runs")
    inventory, _ = run_scan(staging)
    return propose_similar(staging, inventory, max_distance=64)[0]


def test_published_tagging_errors_can_retry_without_adopting_failed_output(collection, monkeypatch):
    config, workspace = collection
    make_bundle(
        bundle_path(config.models, config.tagging.model, config.tagging.revision),
        [Label(0, "object", 0)],
    )
    verify_bytes = tagging._verified_bytes
    failed = False

    def transient_read(source, row, limits):
        nonlocal failed
        if row["source_path"] == "a.png" and not failed:
            failed = True
            raise OSError("Transient image-read failure")
        return verify_bytes(source, row, limits)

    monkeypatch.setattr(tagging, "_verified_bytes", transient_read)
    with pytest.raises(ValueError, match="completed with errors"):
        prepare_directory(config, workspace, captions="model", progress=lambda _: None)
    failed_output = next(workspace.glob("jobs/*/attempts/tagging-*/runs/*/run.json"))
    failed_bytes = failed_output.read_bytes()
    before = preparation.job_status(workspace)["outputs"]
    result = resume_preparation(workspace, progress=lambda _: None)
    assert result["status"] == "completed"
    assert len(list(workspace.glob("jobs/*/attempts/tagging-*"))) == 2
    assert result["outputs"]["inventory"] == before["inventory"]
    assert result["outputs"]["similarity"] == before["similarity"]
    assert Path(result["outputs"]["tagging"]["path"]) != failed_output.parent
    assert result["outputs"]["tagging"]["summary"]["cached_images"] == 2
    assert result["outputs"]["tagging"]["summary"]["inferred_images"] == 1
    assert failed_output.read_bytes() == failed_bytes
    assert json.loads(failed_bytes)["status"] == "completed_with_errors"


def test_crashed_attempt_cannot_adopt_a_valid_unrelated_export(collection, tmp_path, monkeypatch):
    config, workspace = collection
    checkpoint = preparation._checkpoint

    def crash_before_export_checkpoint(job, state, stage, path, *, recovered):
        if stage == "export":
            raise OSError("Crash before recording the published export")
        return checkpoint(job, state, stage, path, recovered=recovered)

    monkeypatch.setattr(preparation, "_checkpoint", crash_before_export_checkpoint)
    with pytest.raises(OSError, match="Crash before"):
        _run(config, workspace)
    published = next(workspace.glob("jobs/*/attempts/export-*/exports/*/run.json")).parent
    monkeypatch.setattr(preparation, "_checkpoint", checkpoint)
    # Produce a genuinely valid snapshot of another registered source, with the
    # same relative filenames and bytes. Per-artifact verification alone passes.
    foreign_source = tmp_path / "different collection"
    shutil.copytree(config.source, foreign_source)
    foreign_workspace = tmp_path / "different preparation"
    foreign_config = preparation_config(foreign_source, foreign_workspace)
    foreign_result = _run(foreign_config, foreign_workspace)
    foreign_export = Path(foreign_result["outputs"]["export"]["path"])
    assert verify_export(foreign_export)["images"] == 3
    replacement = published.parent / foreign_export.name
    published.rename(tmp_path / "retained original export")
    shutil.copytree(foreign_export, replacement)
    assert verify_export(replacement)["images"] == 3
    with pytest.raises(ValueError, match="(?i)(identity|input|source|lineage|contract|checkpoint)"):
        resume_preparation(workspace, progress=lambda _: None)
    status = preparation.job_status(workspace)
    assert status["status"] == "failed" and "export" not in status["outputs"]
    assert verify_export(foreign_export)["images"] == 3


def test_stale_distinct_review_does_not_constrain_changed_content(collection):
    config, workspace = collection
    similarity = _review_run(config, workspace)
    pair = next(
        pair
        for pair in review_status(config, similarity, limit=100)["pairs"]
        if {pair["left_source_path"], pair["right_source_path"]} == {"a.png", "c.png"}
    )
    review_pair(config, similarity, pair["pair_id"], "distinct", "Old c content was distinct")
    store = ReviewStore(config.reviews, config.source)
    review_bytes = store.path.read_bytes()
    with Image.open(config.source / "c.png") as image:
        changed = image.copy()
    changed.putpixel((0, 0), (1, 2, 3))
    changed.save(config.source / "c.png")
    result = _run(config, workspace, max_distance=64)
    assert result["status"] == "completed"
    assert result["outputs"]["policy"]["summary"]["blockers"] == []
    assert store.path.read_bytes() == review_bytes


def test_unresolved_manual_link_outside_proposals_remains_a_split_constraint(collection):
    config, workspace = collection
    staging = replace(config, runs=workspace.parent / "existing review runs")
    inventory, _ = run_scan(staging)
    similarity, _ = propose_similar(staging, inventory, max_distance=0)
    pair_paths = {"a.png", "c.png"}
    assert not any(
        {pair["left_source_path"], pair["right_source_path"]} == pair_paths
        for pair in review_status(config, similarity, limit=100)["pairs"]
    )
    review_link(config, similarity, ["a.png", "c.png"], "unreviewed", "Known uncertain family")
    result = _run(config, workspace, max_distance=0)
    policy = Path(result["outputs"]["policy"]["path"])
    records = [json.loads(line) for line in (policy / "groups.jsonl").read_text().splitlines()]
    assignments = {
        member["source_path"]: group["group_id"] for group in records for member in group["members"]
    }
    assert assignments["a.png"] == assignments["c.png"]
    assert result["outputs"]["policy"]["summary"]["unresolved_pairs"] >= 1


@pytest.mark.parametrize("intent", ["caption", "labels", "subset"])
def test_duplicate_policy_retains_alias_with_explicit_saved_review_intent(collection, intent):
    config, workspace = collection
    (config.source / "alias.png").write_bytes((config.source / "a.png").read_bytes())
    (config.source / "alias.txt").write_text("caption a", encoding="utf-8")
    similarity = _review_run(config, workspace)
    change = {
        "caption": {"caption": "caption a"},
        "labels": {"add_labels": ["intentional alias"]},
        "subset": {"subset": "intentional alias"},
    }[intent]
    review_image(
        config, similarity, "alias.png", reason="Preserve this occurrence annotation", **change
    )
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    result = _run(config, workspace)
    exported = {
        row["source_path"]: row for row in query_catalog(Path(result["outputs"]["export"]["path"]))
    }
    assert "a.png" in exported and "alias.png" in exported
    assert exported["alias.png"]["caption"] == "caption a"
    assert store.path.read_bytes() == before


def test_export_verifier_binds_decision_attribution_to_policy_provenance(collection, tmp_path):
    config, workspace = collection
    result = _run(config, workspace)
    export = Path(result["outputs"]["export"]["path"])
    rows = query_catalog(export)
    rows[0]["decision_origin"] = {"kind": "saved_review", "reason": "fabricated saved review"}
    (export / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    staging = tmp_path / ".pending-reindexed-test"
    descriptor = write_catalog(staging, rows)
    for name in (descriptor["database"], *descriptor["metadata"].values()):
        shutil.copyfile(staging / name, export / name)
    metadata = json.loads((export / "run.json").read_text())
    metadata["catalog"] = descriptor
    for name in ("manifest.jsonl", descriptor["database"], *descriptor["metadata"].values()):
        metadata["files"][name] = file_sha256(export / name)
    atomic_json(export / "run.json", metadata)
    with pytest.raises(ValueError, match="(?i)(origin|attribution|decision)"):
        verify_export(export)


@pytest.mark.parametrize("target", ["run.json", "summary.json"])
def test_preparation_verifier_never_accepts_fabricated_human_acceptance(collection, target):
    config, workspace = collection
    result = _run(config, workspace)
    policy = Path(result["outputs"]["policy"]["path"])
    data = json.loads((policy / target).read_text())
    data["human_accepted"] = True
    atomic_json(policy / target, data)
    if target != "run.json":
        meta = json.loads((policy / "run.json").read_text())
        meta["files"][target] = file_sha256(policy / target)
        atomic_json(policy / "run.json", meta)
    with pytest.raises(ValueError, match="(?i)(preparation|acceptance|human)"):
        _load_groups(policy, require_reviewed=False)
