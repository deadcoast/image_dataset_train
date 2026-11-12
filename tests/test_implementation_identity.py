import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from test_exports import reviewed as reviewed
from test_label_evaluation import evaluation_pilot as evaluation_pilot

from image_dataset_train import execution, implementation, trainer
from image_dataset_train.dataset_catalog import build_catalog, read_catalog
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import export_dataset
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import create_qa
from image_dataset_train.similarity_evaluation import evaluate_similarity
from image_dataset_train.tagging_evaluation import evaluate_labels
from image_dataset_train.trainer_receipts import receipt_artifact, trainer_status


@pytest.fixture
def payload(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    for name in ("implementation.py", "view.html", "view.js", "pins.txt", "pins.in"):
        (package / name).write_text(name, encoding="utf-8")
    (package / "nested").mkdir()
    (package / "nested/helper.py").write_text("helper", encoding="utf-8")
    monkeypatch.setattr(implementation, "__file__", str(package / "implementation.py"))
    return package


def test_identity_is_relocatable_and_ignores_cache_and_unowned_data(payload, tmp_path, monkeypatch):
    identity = implementation.implementation_identity()
    implementation.validate_implementation_identity(identity)
    (payload / "__pycache__").mkdir()
    (payload / "__pycache__/odd.py").write_text("ignored", encoding="utf-8")
    (payload / "state.json").write_text("{}", encoding="utf-8")
    (payload / "extension.pyc").write_bytes(b"bytecode")
    assert implementation.implementation_identity() == identity
    relocated = tmp_path / "different installation"
    shutil.copytree(payload, relocated)
    monkeypatch.setattr(implementation, "__file__", str(relocated / "implementation.py"))
    assert implementation.implementation_identity() == identity
    assert set(identity["files"]) == {
        "implementation.py",
        "view.html",
        "view.js",
        "pins.txt",
        "pins.in",
        "nested/helper.py",
    }
    assert str(tmp_path) not in json.dumps(identity)


@pytest.mark.parametrize(
    "name", ["implementation.py", "view.html", "view.js", "pins.txt", "pins.in"]
)
def test_each_runtime_payload_kind_changes_the_fingerprint(payload, name):
    before = implementation.implementation_identity()
    (payload / name).write_bytes(b"changed payload")
    after = implementation.implementation_identity()
    assert before["payload_sha256"] != after["payload_sha256"]
    assert before["files"][name] != after["files"][name]


@pytest.mark.parametrize("mutation", ["digest", "path", "cache", "alias", "schema", "file_hash"])
def test_identity_validator_rejects_inconsistent_or_unsafe_evidence(payload, mutation):
    identity = implementation.implementation_identity()
    if mutation == "digest":
        identity["payload_sha256"] = "0" * 64
    elif mutation == "path":
        identity["files"]["../outside.py"] = "0" * 64
    elif mutation == "cache":
        identity["files"]["__pycache__/hidden.py"] = "0" * 64
    elif mutation == "alias":
        identity["files"]["VIEW.js"] = identity["files"]["view.js"]
    elif mutation == "schema":
        identity["schema_version"] = True
    else:
        identity["files"]["view.js"] = "not a hash"
    with pytest.raises(ValueError, match="[Ii]mplementation"):
        implementation.validate_implementation_identity(identity)


def test_clock_freezes_identity_at_start_and_old_history_remains_readable(payload, tmp_path):
    clock = execution.RunClock()
    before = implementation.implementation_identity()
    (payload / "view.js").write_text("new build", encoding="utf-8")
    assert clock.measure(tmp_path)["implementation"] == before
    assert implementation.implementation_identity() != before
    legacy = {"run_id": "old", "stage": "qa", "status": "completed", "metrics": None}
    current = {"run_id": "new", "stage": "qa", "metrics": clock.measure(tmp_path)}
    assert execution.processing_history(legacy, current) == [legacy, {**current, "status": None}]
    current["metrics"]["implementation"]["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="identity hash mismatch"):
        execution.processing_history(current)


def test_pipeline_qa_history_and_standalone_catalog_keep_build_identity(reviewed, monkeypatch):
    config, groups, drafts = reviewed
    exported, _ = export_dataset(config, groups, captions_run=drafts)
    qa, _ = create_qa(config, exported)
    records = [
        json.loads(path.read_text(encoding="utf-8")) for path in config.runs.glob("*/run.json")
    ] + [json.loads((exported / "run.json").read_text(encoding="utf-8"))]
    assert {record["stage"] for record in records} == {
        "inventory",
        "similarity",
        "groups",
        "recaption",
        "export",
        "qa",
    }
    for record in records:
        implementation.validate_implementation_identity(record["metrics"]["implementation"])
    qa_metadata = json.loads((qa / "run.json").read_text(encoding="utf-8"))
    original = {record["run_id"]: record for record in records}
    for receipt in qa_metadata["processing_history"]:
        assert (
            receipt["metrics"]["implementation"]
            == original[receipt["run_id"]]["metrics"]["implementation"]
        )
    catalog, _ = build_catalog(exported, output_root=config.runs.parent / "catalogs")
    metadata = json.loads((catalog / "run.json").read_text(encoding="utf-8"))
    implementation.validate_implementation_identity(metadata["implementation"])
    monkeypatch.setattr(implementation, "__version__", "future-build")
    assert read_catalog(catalog)["images"] == 4
    del metadata["implementation"]
    atomic_json(catalog / "run.json", metadata)
    assert read_catalog(catalog)["images"] == 4  # Historical receipts never require the field.


def test_trainer_receipt_binds_same_identity_and_accepts_historical_builds(reviewed, monkeypatch):
    config, groups, drafts = reviewed
    exported, _ = export_dataset(config, groups, captions_run=drafts)
    runtime = config.runs.parent / "runtime"
    python = trainer._python(runtime)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"synthetic runtime marker")
    monkeypatch.setattr(trainer, "_check_revision", lambda _: None)

    def worker(command, **kwargs):
        atomic_json(Path(command[-2]), {"qualified": True})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(trainer.subprocess, "run", worker)
    receipt, result = trainer.check_trainer(config, exported, runtime)
    metadata = json.loads((receipt / "run.json").read_text(encoding="utf-8"))
    assert metadata["implementation"] == result["implementation"]
    implementation.validate_implementation_identity(result["implementation"])
    monkeypatch.setattr(implementation, "__version__", "future-build")
    assert trainer_status(exported, config.runs)["status"] == "passed"
    inconsistent = deepcopy(metadata)
    inconsistent["implementation"]["version"] = "different receipt claim"
    atomic_json(receipt / "run.json", inconsistent)
    assert trainer_status(exported, config.runs)["status"] == "invalid"
    del metadata["implementation"]
    del result["implementation"]
    atomic_json(receipt / "result.json", result)
    metadata["files"]["result.json"] = file_sha256(receipt / "result.json")
    atomic_json(receipt / "run.json", metadata)
    assert trainer_status(exported, config.runs)["status"] == "passed"
    atomic_json(receipt / "result.json", [])
    metadata["files"]["result.json"] = file_sha256(receipt / "result.json")
    atomic_json(receipt / "run.json", metadata)
    with pytest.raises(ValueError, match="JSON object"):
        receipt_artifact(receipt, "result.json")


def test_label_workspace_and_evaluation_receipts_identify_implementation(evaluation_pilot):
    config, qa, scored, workspace, _ = evaluation_pilot
    workspace_meta = json.loads((workspace / "run.json").read_text(encoding="utf-8"))
    implementation.validate_implementation_identity(workspace_meta["implementation"])
    label_evaluation, _ = evaluate_labels(config, workspace, [scored])
    qa_meta = json.loads((qa / "run.json").read_text(encoding="utf-8"))
    pair_evaluation, _ = evaluate_similarity(config, Path(qa_meta["similarity_run"]))
    for directory in (scored, label_evaluation, pair_evaluation):
        metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        implementation.validate_implementation_identity(metadata["metrics"]["implementation"])
