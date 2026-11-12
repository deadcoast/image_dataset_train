import json
import sqlite3
from pathlib import Path

import pytest
from test_collection_catalog import _setup
from test_dataset_catalog import exported as exported
from test_exports import reviewed as reviewed
from test_preparation import collection as collection

from image_dataset_train import collection_catalog, dataset_catalog
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256


def _rewrite(path):
    value = json.loads(path.read_bytes())
    value["coherence_probe"] = "same identifier, different bytes"
    path.write_text(json.dumps(value), encoding="utf-8")


def test_catalog_metadata_identity_cannot_mix_captured_values_and_later_hash(exported, monkeypatch):
    _, directory, _ = exported
    original = dataset_catalog._checked
    changed = False

    def checked(root, name, expected):
        nonlocal changed
        raw = original(root, name, expected)
        if not changed:
            changed = True
            _rewrite(directory / "run.json")
        return raw

    monkeypatch.setattr(dataset_catalog, "_checked", checked)
    with pytest.raises(ValueError, match="changed"):
        dataset_catalog.read_catalog(directory)
    assert changed


@pytest.mark.parametrize("query", [False, True])
@pytest.mark.parametrize(
    "target",
    [
        "run.json",
        "manifest.jsonl",
        "provenance/reviews.json",
        "train/metadata.jsonl",
        "catalog.sqlite",
    ],
)
def test_catalog_checks_all_metadata_after_validation(exported, monkeypatch, query, target):
    _, directory, _ = exported
    original = dataset_catalog.verify_catalog_payload

    def verify(*args, **kwargs):
        result = original(*args, **kwargs)
        path = directory / target
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(dataset_catalog, "verify_catalog_payload", verify)
    with pytest.raises(ValueError, match="changed"):
        (dataset_catalog.query_catalog if query else dataset_catalog.read_catalog)(directory)


def test_collection_omits_run_that_changes_after_metadata_read(collection, tmp_path, monkeypatch):
    _, _, _, entry = _setup(collection, tmp_path)
    original = collection_catalog._run
    changed = []

    def run(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if result and result["stage"] == "qa":
            _rewrite(Path(path) / "run.json")
            changed.append(str(path))
        return result

    monkeypatch.setattr(collection_catalog, "_run", run)
    result = collection_catalog.collection_snapshot(entry)
    assert changed
    assert not any(row["path"] in changed for row in result["runs"])
    assert any("changed" in row["error"].lower() for row in result["errors"])
    assert any(row["stage"] == "export" for row in result["runs"])


@pytest.mark.parametrize("digest", [None, True, 1, "", "A" * 64, "0" * 64])
def test_explicit_invalid_checksum_never_becomes_an_unchecked_capture(exported, digest):
    _, directory, _ = exported
    metadata = json.loads((directory / "run.json").read_bytes())
    metadata["files"]["manifest.jsonl"] = digest
    atomic_json(directory / "run.json", metadata)
    before = (directory / "run.json").read_bytes()
    with pytest.raises(ValueError, match="hash mismatch"):
        dataset_catalog.read_catalog(directory)
    assert (directory / "run.json").read_bytes() == before


@pytest.mark.parametrize("target", ["run.json", "manifest.jsonl", "provenance/reviews.json"])
def test_query_final_fence_includes_metadata_after_sql_execution(exported, monkeypatch, target):
    _, directory, _ = exported
    original = dataset_catalog._connect
    changed = False

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)

        def trace(statement):
            nonlocal changed
            if statement.startswith("SELECT i.record_json") and not changed:
                changed = True
                path = directory / target
                path.write_bytes(path.read_bytes() + b"\n")

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(dataset_catalog, "_connect", connect)
    with pytest.raises(ValueError, match="changed"):
        dataset_catalog.query_catalog(directory, limit=1)
    assert changed


def test_final_fence_rechecks_controlling_metadata_after_payloads(exported, monkeypatch):
    _, directory, _ = exported
    original = dataset_catalog.file_sha256
    changed = False

    def digest(path):
        nonlocal changed
        result = original(path)
        if path == directory / "catalog.sqlite":
            changed = True
            _rewrite(directory / "run.json")
        return result

    monkeypatch.setattr(dataset_catalog, "file_sha256", digest)
    with pytest.raises(ValueError, match="changed.*run.json"):
        dataset_catalog.query_catalog(directory, limit=1)
    assert changed


def test_query_uses_captured_database_even_during_transient_path_replacement(exported, monkeypatch):
    _, directory, rows = exported
    database = directory / "catalog.sqlite"
    original_bytes = database.read_bytes()
    original = dataset_catalog._connect
    connections = 0

    def connect(path, **kwargs):
        nonlocal connections
        connections += 1
        if connections == 2:
            # An external writer temporarily substitutes a different valid DB at
            # the query boundary, then restores the original bytes (ABA).
            with sqlite3.connect(database) as external:
                external.execute("UPDATE images SET record_json = '{}' ")
            try:
                return original(path, **kwargs)
            finally:
                database.write_bytes(original_bytes)
        return original(path, **kwargs)

    monkeypatch.setattr(dataset_catalog, "_connect", connect)
    assert dataset_catalog.query_catalog(directory) == rows
    assert connections == 2 and database.read_bytes() == original_bytes


def test_standalone_membership_is_rechecked_after_payload_validation(
    exported, tmp_path, monkeypatch
):
    _, export, _ = exported
    catalog, _ = dataset_catalog.build_catalog(export, output_root=tmp_path / "catalogs")
    original = dataset_catalog.verify_catalog_payload

    def verify(*args, **kwargs):
        result = original(*args, **kwargs)
        (catalog / "unexpected.json").write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(dataset_catalog, "verify_catalog_payload", verify)
    with pytest.raises(ValueError, match="membership changed"):
        dataset_catalog.read_catalog(catalog)


def test_catalog_build_fences_source_metadata_before_publication(exported, tmp_path, monkeypatch):
    _, export, _ = exported
    original = dataset_catalog.write_catalog

    def write(*args, **kwargs):
        result = original(*args, **kwargs)
        _rewrite(export / "run.json")
        return result

    monkeypatch.setattr(dataset_catalog, "write_catalog", write)
    output = tmp_path / "catalogs"
    with pytest.raises(ValueError, match="changed"):
        dataset_catalog.build_catalog(export, output_root=output)
    assert not any(not path.name.startswith(".pending-") for path in output.iterdir())


@pytest.mark.parametrize("target", ["binding", "job", "config", "reviews"])
def test_collection_removes_changed_context_and_its_dependent_rows(
    collection, tmp_path, monkeypatch, target
):
    config, workspace, completed, entry = _setup(collection, tmp_path)
    paths = {
        "binding": workspace / "collection.json",
        "job": Path(completed["job"]) / "job.json",
        "config": Path(completed["config"]),
        "reviews": collection_catalog.ReviewStore(config.reviews, config.source).path,
    }
    path = paths[target]
    original = collection_catalog._run
    changed = False

    def run(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((path.read_bytes() if path.exists() else b"{}") + b"\n")
        return result

    monkeypatch.setattr(collection_catalog, "_run", run)
    result = collection_catalog.collection_snapshot(entry)
    assert changed and any("changed" in row["error"] for row in result["errors"])
    if target == "reviews":
        assert result["current_review_revision"] is None
        assert result["review_revisions"] == [] and result["runs"]
    else:
        assert result["current_job_id"] is None
        assert result["jobs"] == [] and result["runs"] == []
        assert all(not roots for roots in result["registered_roots"].values())


@pytest.mark.parametrize("during_final_fence", [False, True])
def test_collection_receipt_change_cannot_retain_exact_export_binding(
    collection, tmp_path, monkeypatch, during_final_fence
):
    _, workspace, completed, entry = _setup(collection, tmp_path)
    export = Path(completed["outputs"]["export"]["path"])
    receipt = workspace / "runs" / "receipt"
    receipt.mkdir(parents=True)
    atomic_json(
        receipt / "result.json",
        {
            "export": str(export),
            "export_run_sha256": file_sha256(export / "run.json"),
            "export_manifest_sha256": file_sha256(export / "manifest.jsonl"),
        },
    )
    atomic_json(
        receipt / "run.json",
        {
            "schema_version": 1,
            "stage": "trainer-check",
            "status": "completed",
            "files": {"result.json": file_sha256(receipt / "result.json")},
        },
    )
    if during_final_fence:
        original = collection_catalog.file_sha256

        def read(path):
            result = original(path)
            if path == receipt / "result.json":
                _rewrite(receipt / "run.json")
            return result

        monkeypatch.setattr(collection_catalog, "file_sha256", read)
    else:
        original = collection_catalog.read_object

        def read(path):
            result = original(path)
            if path == receipt / "result.json":
                _rewrite(path)
            return result

        monkeypatch.setattr(collection_catalog, "read_object", read)
    result = collection_catalog.collection_snapshot(entry)
    assert not any(row["stage"] == "trainer-check" for row in result["runs"])
    assert any("changed" in row["error"] for row in result["errors"])
    assert any(row["stage"] == "export" for row in result["runs"])


@pytest.mark.parametrize("locator", ["bad", None, 1, [], "jobs/../escape", "jobs/"])
def test_malformed_collection_binding_is_a_recorded_error(collection, tmp_path, locator):
    _, workspace, _, entry = _setup(collection, tmp_path)
    path = workspace / "collection.json"
    binding = json.loads(path.read_bytes())
    binding["job"] = locator
    atomic_json(path, binding)
    before = path.read_bytes()
    result = collection_catalog.collection_snapshot(entry)
    assert result["errors"] and not result["jobs"] and not result["runs"]
    assert path.read_bytes() == before


def test_selection_rechecks_context_after_selected_metadata_read(collection, tmp_path, monkeypatch):
    _, workspace, _, entry = _setup(collection, tmp_path)
    selected = next(
        row for row in collection_catalog.collection_snapshot(entry)["runs"] if row["stage"] == "qa"
    )
    original = collection_catalog.read_object
    count = 0

    def read(path):
        nonlocal count
        result = original(path)
        if path == Path(selected["path"]) / "run.json":
            count += 1
            if count == 2:
                _rewrite(workspace / "collection.json")
        return result

    monkeypatch.setattr(collection_catalog, "read_object", read)
    with pytest.raises(ValueError, match="changed"):
        collection_catalog.select_run(entry, selected["id"])
    assert count == 2
