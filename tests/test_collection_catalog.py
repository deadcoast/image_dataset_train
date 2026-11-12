import json
import shutil
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run

from image_dataset_train import preparation
from image_dataset_train.collection_catalog import collection_snapshot, select_run
from image_dataset_train.collection_registry import CollectionRegistry
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.review_ui import ReviewSession
from image_dataset_train.reviews import ReviewStore


def _setup(collection, tmp_path):
    config, workspace = collection
    completed = run(config, workspace)
    entry = CollectionRegistry(tmp_path / "application").register(workspace, "Collection")
    return config, workspace, completed, entry


def _tree(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_catalog_lists_exact_artifacts_offline_without_mutation(collection, tmp_path):
    config, workspace, completed, entry = _setup(collection, tmp_path)
    before = _tree(workspace)
    config.source.rename(config.source.with_name("offline"))
    snapshot = collection_snapshot(entry)
    assert snapshot["errors"] == []
    assert snapshot["current_job_id"] == completed["job_id"]
    assert snapshot["current_review_revision"] == 0
    assert not snapshot["source_revalidated"]
    assert {r["stage"] for r in snapshot["runs"]} == {
        "inventory",
        "similarity",
        "groups",
        "export",
        "qa",
    }
    assert {r["path"] for r in snapshot["runs"]} == {
        r["path"] for r in completed["outputs"].values()
    }
    qa = next(record for record in snapshot["runs"] if record["stage"] == "qa")
    selected = select_run(entry, qa["id"], qa["run_sha256"])
    assert selected["config_sha256"] == file_sha256(Path(completed["config"]))
    assert selected["metadata_verification"] == "metadata_only"
    with pytest.raises(ValueError, match="exact catalog"):
        select_run(entry, Path(qa["path"]).name)
    assert _tree(workspace) == before


def test_current_and_historical_jobs_have_distinct_ownership(collection, tmp_path):
    config, workspace, completed, entry = _setup(collection, tmp_path)
    latest = run(config, workspace, new=True)
    pointer = (workspace / "collection.json").read_bytes()
    snapshot = collection_snapshot(entry)
    assert len(snapshot["jobs"]) == 2
    assert [job["id"] for job in snapshot["jobs"] if job["current"]] == [latest["job_id"]]
    assert {r["job_id"] for r in snapshot["runs"]} == {completed["job_id"], latest["job_id"]}
    assert (workspace / "collection.json").read_bytes() == pointer


def test_shared_run_root_filters_sources_and_isolates_bad_metadata(collection, tmp_path):
    config, workspace, completed, entry = _setup(collection, tmp_path)
    shared = workspace / "runs"
    shared.mkdir(exist_ok=True)
    good = shared / "same-name"
    shutil.copytree(completed["outputs"]["qa"]["path"], good)
    foreign = shared / "foreign"
    shutil.copytree(good, foreign)
    metadata = json.loads((foreign / "run.json").read_text())
    metadata["source"] = str(tmp_path / "unregistered-source")
    atomic_json(foreign / "run.json", metadata)
    damaged = shared / "damaged"
    damaged.mkdir()
    (damaged / "run.json").write_text('{"schema_version":', encoding="utf-8")
    snapshot = collection_snapshot(entry)
    assert str(good) in {r["path"] for r in snapshot["runs"]}
    assert str(foreign) not in {r["path"] for r in snapshot["runs"]}
    assert any(error["path"] == str(damaged) for error in snapshot["errors"])
    same_bytes = [r for r in snapshot["runs"] if r["run_sha256"] == file_sha256(good / "run.json")]
    assert len(same_bytes) == 2 and len({r["id"] for r in same_bytes}) == 2


def test_changed_run_and_job_configuration_cannot_satisfy_previous_selection(collection, tmp_path):
    _, _, completed, entry = _setup(collection, tmp_path)
    selected = next(r for r in collection_snapshot(entry)["runs"] if r["stage"] == "qa")
    meta = Path(selected["path"]) / "run.json"
    original = meta.read_bytes()
    data = json.loads(original)
    data["untrusted_note"] = "changed after listing"
    atomic_json(meta, data)
    with pytest.raises(ValueError, match="missing, changed"):
        select_run(entry, selected["id"])
    meta.write_bytes(original)
    with pytest.raises(ValueError, match="metadata changed"):
        select_run(entry, selected["id"], "0" * 64)
    config = Path(completed["config"])
    config.write_text(config.read_text() + "\n# edited after job publication\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing, changed"):
        select_run(entry, selected["id"])


def test_missing_workspace_and_malformed_job_are_visible_without_stopping_other_jobs(
    collection, tmp_path
):
    config, workspace, _, entry = _setup(collection, tmp_path)
    run(config, workspace, new=True)
    old = sorted((workspace / "jobs").iterdir())[0]
    (old / "job.json").write_text("[]", encoding="utf-8")
    snapshot = collection_snapshot(entry)
    assert len(snapshot["jobs"]) == 1 and snapshot["runs"]
    assert any(error["path"] == str(old) for error in snapshot["errors"])
    workspace.rename(tmp_path / "offline-workspace")
    snapshot = collection_snapshot(entry)
    assert not snapshot["jobs"] and not snapshot["runs"] and snapshot["errors"]


def test_publication_discovery_does_not_recover_or_rewrite_jobs(collection, tmp_path):
    config, workspace, completed, entry = _setup(collection, tmp_path)
    session = ReviewSession(
        config, Path(completed["outputs"]["qa"]["path"]), config_path=Path(completed["config"])
    )
    session.publication.start({"mode": "groups", "expected_revision": 0})
    session.publication.wait()
    assert session.publication.read()["status"] == "completed"
    job_path = session.publication.path
    value = json.loads(job_path.read_text())
    value["attempts"][-1]["status"] = "running"
    atomic_json(job_path, value)
    before = _tree(workspace)
    snapshot = collection_snapshot(entry)
    assert snapshot["publications"][0]["attempts"][-1]["status"] == "running"
    assert snapshot["publications"][0]["process_liveness"] == "unknown"
    assert any(run["ownership"] == "publication" for run in snapshot["runs"])
    assert _tree(workspace) == before
    # A damaged review store must not hide independently readable publication history.
    reviews = ReviewStore(config.reviews, config.source)
    reviews.directory.mkdir(parents=True, exist_ok=True)
    reviews.path.write_text("[]", encoding="utf-8")
    snapshot = collection_snapshot(entry)
    assert snapshot["publications"] and snapshot["errors"]
    assert job_path.read_bytes() == before[job_path.relative_to(workspace)]


@pytest.mark.parametrize("field,value", [("created_at", None), ("updated_at", {})])
def test_malformed_job_timestamp_is_isolated(collection, tmp_path, field, value):
    config, workspace, first, entry = _setup(collection, tmp_path)
    second = run(config, workspace, new=True)
    path = Path(first["job"]) / "job.json"
    state = json.loads(path.read_text())
    state[field] = value
    atomic_json(path, state)
    snapshot = collection_snapshot(entry)
    assert [job["id"] for job in snapshot["jobs"]] == [second["job_id"]]
    assert snapshot["runs"]
    assert any(error["path"] == str(path.parent) for error in snapshot["errors"])


def test_review_root_source_overlap_is_rejected_before_review_read(
    collection, tmp_path, monkeypatch
):
    config, _, completed, entry = _setup(collection, tmp_path)
    path = Path(completed["job"]) / "job.json"
    state = json.loads(path.read_text())
    state["settings"]["reviews"] = str(config.source / "unsafe-reviews")
    state["settings_sha256"] = preparation._digest(state["settings"])
    configuration = path.parent / "config.toml"
    preparation._write_config(configuration, preparation._config(state["settings"]))
    state["config_sha256"] = file_sha256(configuration)
    atomic_json(path, state)
    monkeypatch.setattr(
        ReviewStore, "read", lambda _: pytest.fail("Source-overlapping review read")
    )
    snapshot = collection_snapshot(entry)
    assert not snapshot["registered_roots"]["reviews"]
    assert any("Review root overlaps" in error["error"] for error in snapshot["errors"])
    assert not (config.source / "unsafe-reviews").exists()


def test_trainer_receipts_bind_export_hashes_and_keep_stale_path_evidence(collection, tmp_path):
    _, workspace, completed, entry = _setup(collection, tmp_path)
    exported = Path(completed["outputs"]["export"]["path"])
    for name, digest in (("exact", file_sha256(exported / "run.json")), ("stale", "0" * 64)):
        directory = workspace / "runs" / name
        directory.mkdir(parents=True)
        atomic_json(
            directory / "result.json",
            {
                "export": str(exported),
                "export_run_sha256": digest,
                "export_manifest_sha256": file_sha256(exported / "manifest.jsonl"),
            },
        )
        atomic_json(
            directory / "run.json",
            {
                "schema_version": 1,
                "stage": "trainer-check",
                "status": "completed",
                "files": {"result.json": file_sha256(directory / "result.json")},
            },
        )
    receipts = [r for r in collection_snapshot(entry)["runs"] if r["stage"] == "trainer-check"]
    assert {r["receipt_binding"] for r in receipts} == {"exact_export", "stale_same_path"}
    assert all(r["metadata_verification"] == "metadata_only" for r in receipts)
