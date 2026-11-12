import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_preparation import collection as collection

from image_dataset_train import preparation, preparation_cli
from image_dataset_train.cli import main
from image_dataset_train.collection_registry import CollectionRegistry


def arguments(config, workspace):
    return [
        "prepare",
        str(config.source),
        "--workspace",
        str(workspace),
        "--captions",
        "existing",
        "--offline",
        "--json",
    ]


def test_cli_preparation_registers_and_preserves_assigned_name(collection, capsys):
    config, workspace = collection
    assert main(arguments(config, workspace)) == 0
    result = json.loads(capsys.readouterr().out)
    registered = result["collection_registration"]
    assert registered["status"] == "registered"
    registry = CollectionRegistry()
    original = registry.resolve(registered["collection"]["id"])
    assert original["workspace"] == str(workspace)
    assert original["source"] == str(config.source)
    registry.register(workspace, name="My artwork [猫]")
    before = registry.path.read_bytes()
    assert main(arguments(config, workspace)) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["collection_registration"]["collection"]["name"] == "My artwork [猫]"
    assert repeated["job_id"] == result["job_id"]
    assert registry.path.read_bytes() == before


def test_interrupted_cli_job_is_findable_without_registering_preview(
    collection, capsys, monkeypatch
):
    config, workspace = collection
    registry = CollectionRegistry()
    assert main([*arguments(config, workspace), "--dryrun"]) == 0
    capsys.readouterr()
    assert not registry.path.exists() and not workspace.exists()
    original_execute = preparation._execute

    def fail_export(stage, *args):
        if stage == "export":
            raise OSError("Fixture interrupted publication")
        return original_execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", fail_export)
    assert main(arguments(config, workspace)) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "failed"
    assert failed["collection_registration"]["status"] == "registered"
    entry = registry.resolve(failed["collection_registration"]["collection"]["id"])
    assert entry["workspace"] == str(workspace)
    assert failed["saved_job"]["status"] == "failed"
    assert "policy" in failed["saved_job"]["outputs"]


def test_registry_failure_does_not_discard_completed_preparation(collection, capsys, monkeypatch):
    config, workspace = collection

    def unavailable_registry(*_args, **_kwargs):
        raise OSError("Fixture registry is read-only")

    monkeypatch.setattr(CollectionRegistry, "register", unavailable_registry)
    assert main(arguments(config, workspace)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed" and result["prepared"] is True
    assert result["collection_registration"]["status"] == "failed"
    assert "read-only" in result["collection_registration"]["error"]["message"]
    assert preparation.job_status(workspace, verify=True)["prepared"] is True
    assert result["outputs"]["export"]["summary"]["images"] == 3


def test_rejected_arguments_do_not_register_a_different_saved_source(collection, capsys):
    config, workspace = collection
    preparation.prepare_directory(config, workspace, captions="existing", progress=lambda _: None)
    another = workspace.parent / "another source"
    another.mkdir()
    assert (
        main(
            [
                "prepare",
                str(another),
                "--workspace",
                str(workspace),
                "--captions",
                "existing",
                "--json",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert "collection_registration" not in result
    assert not CollectionRegistry().path.exists()


@pytest.mark.parametrize("log_failure", ["construction", "write"])
@pytest.mark.parametrize("interrupted", [False, True], ids=["failed", "cancelled"])
def test_stage_error_and_recovery_survive_unavailable_log_and_registry(
    collection, capsys, monkeypatch, log_failure, interrupted
):
    config, workspace = collection
    source_before = {path.name: path.read_bytes() for path in config.source.iterdir()}
    execute = preparation._execute
    retained_outputs = {}
    retained_bytes = {}

    def fail_export(stage, *args):
        if stage == "export":
            retained_outputs.update(preparation.job_status(workspace)["outputs"])
            for output in retained_outputs.values():
                for path in Path(output["path"]).rglob("*"):
                    if path.is_file():
                        retained_bytes[path] = path.read_bytes()
            if interrupted:
                raise KeyboardInterrupt("Fixture caller cancellation during export")
            raise OSError("Fixture original export failure")
        return execute(stage, *args)

    def unavailable_write(*_args, **_kwargs):
        raise PermissionError("Fixture log write unavailable")

    def unavailable_log(*_args, **_kwargs):
        if log_failure == "construction":
            raise PermissionError("Fixture log construction unavailable")
        return SimpleNamespace(exception=unavailable_write)

    def unavailable_registry(*_args, **_kwargs):
        raise OSError("Fixture registry unavailable")

    monkeypatch.setattr(preparation, "_execute", fail_export)
    monkeypatch.setattr(preparation_cli, "EventLog", unavailable_log)
    monkeypatch.setattr(CollectionRegistry, "register", unavailable_registry)
    assert main(arguments(config, workspace)) == (130 if interrupted else 2)
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == ("cancelled" if interrupted else "failed")
    assert result["error"]["type"] == ("KeyboardInterrupt" if interrupted else "OSError")
    assert result["error"]["message"] == (
        "Fixture caller cancellation during export"
        if interrupted
        else "Fixture original export failure"
    )
    assert result["error"]["log"] is None
    assert result["log_unavailable"] == {
        "type": "PermissionError",
        "message": f"Fixture log {log_failure} unavailable",
    }
    assert result["collection_registration"]["status"] == "failed"
    assert result["collection_registration"]["error"]["message"] == "Fixture registry unavailable"
    assert result["saved_job"]["status"] == result["status"]
    assert result["saved_job"]["outputs"] == retained_outputs
    assert "policy" in retained_outputs and "export" not in retained_outputs
    assert result["next_action"] == "resume"
    resume = result["next_commands"][0]["argv"]
    assert resume[:3] == ["dataset", "resume", str(workspace)]
    assert resume[resume.index("--job") + 1] == result["saved_job"]["job_id"]
    assert result["prepared"] is False and result["human_accepted"] is False
    assert all(path.read_bytes() == content for path, content in retained_bytes.items())
    assert not CollectionRegistry().path.exists()

    # The advertised recovery must still work and reuse the retained successful stages.
    monkeypatch.setattr(preparation, "_execute", execute)
    assert main(resume[1:]) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["prepared"] is True and recovered["human_accepted"] is False
    assert all(recovered["outputs"][stage] == value for stage, value in retained_outputs.items())
    assert all(path.read_bytes() == content for path, content in retained_bytes.items())
    assert {path.name: path.read_bytes() for path in config.source.iterdir()} == source_before


def test_missing_registry_module_keeps_completed_artifacts_and_exit_success(
    collection, capsys, monkeypatch
):
    config, workspace = collection
    source_before = {path.name: path.read_bytes() for path in config.source.iterdir()}
    monkeypatch.setitem(sys.modules, "image_dataset_train.collection_registry", None)
    assert main(arguments(config, workspace)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed" and result["prepared"] is True
    assert result["human_accepted"] is False
    registration = result["collection_registration"]
    assert registration["status"] == "failed"
    assert registration["error"]["type"] == "ModuleNotFoundError"
    assert "collection_registry" in registration["error"]["message"]
    assert "collections" in registration["command"] and "add" in registration["command"]
    assert str(workspace) in registration["command"]
    assert preparation.job_status(workspace, verify=True)["prepared"] is True
    assert result["outputs"]["export"]["summary"]["images"] == 3
    assert {path.name: path.read_bytes() for path in config.source.iterdir()} == source_before
    assert not CollectionRegistry().path.exists()
