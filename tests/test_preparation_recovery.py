"""Recovery inspection preserves evidence and binds continuation to exact jobs."""

import json
import shutil
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run
from test_tagging import make_bundle

from image_dataset_train import preparation, tagging
from image_dataset_train.cli import main
from image_dataset_train.collection_registry import CollectionRegistry
from image_dataset_train.model_bundle import Label, bundle_path
from image_dataset_train.preparation import (
    inspect_preparation,
    read_preparation_job,
    resume_preparation,
)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def stage(result, name):
    return next(item for item in result["stages"] if item["stage"] == name)


def fail_export(collection, monkeypatch, *, published=False):
    config, workspace = collection
    original = preparation._checkpoint if published else preparation._execute

    def stop(*args, **kwargs):
        name = args[2] if published else args[0]
        if name == "export":
            raise OSError("Synthetic interrupted export")
        return original(*args, **kwargs)

    target = "_checkpoint" if published else "_execute"
    monkeypatch.setattr(preparation, target, stop)
    with pytest.raises(OSError, match="Synthetic"):
        run(config, workspace)
    monkeypatch.setattr(preparation, target, original)
    return inspect_preparation(workspace)


def test_historical_job_read_and_expected_current_guard_preserve_binding(collection):
    config, workspace = collection
    first = run(config, workspace)
    second = run(config, workspace, new=True)
    before = snapshot(workspace)
    job, state = read_preparation_job(workspace, job_id=first["job_id"])
    assert job == Path(first["job"]) and state["job_id"] == first["job_id"]
    historical = inspect_preparation(workspace, job_id=first["job_id"], verify=True)
    assert historical["is_current_job"] is False
    assert historical["current_job_id"] == second["job_id"]
    assert historical["next_action"] == "select_current_job"
    assert historical["outputs"] == first["outputs"]
    with pytest.raises(ValueError, match="Current preparation job"):
        resume_preparation(workspace, expected_job_id=first["job_id"])
    assert snapshot(workspace) == before
    resumed = resume_preparation(
        workspace, expected_job_id=second["job_id"], progress=lambda _: None
    )
    assert resumed["job_id"] == second["job_id"]


@pytest.mark.parametrize(
    "identifier", ["../escape", "a/b", "a\\b", "C:outside", "", "..", ".hidden"]
)
def test_job_selection_rejects_paths_without_writes(collection, identifier):
    config, workspace = collection
    run(config, workspace)
    before = snapshot(workspace)
    with pytest.raises(ValueError, match="exact preparation job ID"):
        read_preparation_job(workspace, job_id=identifier)
    assert snapshot(workspace) == before


def test_selected_job_id_must_match_its_record(collection):
    config, workspace = collection
    result = run(config, workspace)
    original = Path(result["job"])
    copied = original.with_name("other-job")
    shutil.copytree(original, copied)
    before = snapshot(workspace)
    with pytest.raises(ValueError, match="preparation job contract"):
        read_preparation_job(workspace, job_id=copied.name)
    assert snapshot(workspace) == before


def test_expected_job_is_checked_after_acquiring_workspace_lock(collection, monkeypatch):
    config, workspace = collection
    first = run(config, workspace)
    second = run(config, workspace, new=True)
    binding = workspace / "collection.json"
    newest = binding.read_bytes()
    old = json.loads(newest)
    old["job"] = "jobs/" + first["job_id"]
    binding.write_text(json.dumps(old), encoding="utf-8")
    jobs_before = snapshot(workspace / "jobs")

    class WriterFinishesBeforeLock:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            binding.write_bytes(newest)

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(preparation, "FileLock", WriterFinishesBeforeLock)
    with pytest.raises(ValueError, match="Current preparation job"):
        resume_preparation(workspace, expected_job_id=first["job_id"])
    assert snapshot(workspace / "jobs") == jobs_before
    assert json.loads(binding.read_bytes())["job"] == "jobs/" + second["job_id"]


def test_published_output_is_visible_verified_and_recovered_once(collection, monkeypatch):
    _, workspace = collection
    failed = fail_export(collection, monkeypatch, published=True)
    export = stage(failed, "export")
    assert export["continuation"] == "verify_then_recover_publication"
    published = Path(export["published_outputs"][0]["path"])
    before = snapshot(workspace)
    checked = inspect_preparation(workspace, verify=True)
    assert stage(checked, "export")["continuation"] == "recover_publication"
    assert stage(checked, "export")["integrity"] == "verified"
    assert snapshot(workspace) == before
    resumed = resume_preparation(
        workspace, expected_job_id=failed["job_id"], progress=lambda _: None
    )
    assert Path(resumed["outputs"]["export"]["path"]) == published
    assert len(list(Path(resumed["job"]).glob("attempts/export-*"))) == 1


def test_pending_and_prior_attempts_are_visible_without_writes(collection, monkeypatch):
    _, workspace = collection
    failed = fail_export(collection, monkeypatch)
    attempt = Path(stage(failed, "export")["attempt"])
    pending = attempt / "exports/.pending-synthetic"
    pending.mkdir(parents=True)
    (pending / "partial.bin").write_bytes(b"retained evidence")
    before = snapshot(workspace)
    checked = inspect_preparation(workspace, verify=True)
    assert stage(checked, "export")["pending_outputs"] == [str(pending)]
    assert stage(checked, "export")["continuation"] == "retry_stage"
    assert stage(checked, "tagging")["status"] == "skipped"
    assert snapshot(workspace) == before
    resumed = resume_preparation(workspace, progress=lambda _: None)
    assert len(resumed["retained_attempts"]) == 1
    assert resumed["retained_attempts"][0]["pending_outputs"] == [str(pending)]
    assert (pending / "partial.bin").read_bytes() == b"retained evidence"


def test_untrusted_attempt_path_is_reported_without_hiding_healthy_stages(collection, monkeypatch):
    _, workspace = collection
    failed = fail_export(collection, monkeypatch)
    job = Path(failed["job"]) / "job.json"
    state = json.loads(job.read_text(encoding="utf-8"))
    state["stages"]["export"]["attempt"] = "../../outside"
    job.write_text(json.dumps(state), encoding="utf-8")
    before = snapshot(workspace)
    checked = inspect_preparation(workspace, verify=True)
    assert checked["next_action"] == "inspect_artifacts"
    assert stage(checked, "export")["attempt"] is None
    assert stage(checked, "export")["integrity"] == "invalid"
    assert stage(checked, "inventory")["integrity"] == "verified"
    assert snapshot(workspace) == before


def test_linked_attempt_output_root_is_never_followed(collection, monkeypatch, tmp_path):
    _, workspace = collection
    failed = fail_export(collection, monkeypatch)
    root = Path(stage(failed, "export")["attempt"]) / "exports"
    foreign = tmp_path / "unrelated artifacts"
    foreign.mkdir()
    try:
        root.symlink_to(foreign, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlink creation unavailable: {exc}")
    iterdir = Path.iterdir

    def reject_follow(path):
        if path == root:
            pytest.fail("Inspection followed a linked artifact root")
        return iterdir(path)

    monkeypatch.setattr(Path, "iterdir", reject_follow)
    checked = inspect_preparation(workspace, verify=True)
    assert stage(checked, "export")["integrity"] == "invalid"
    assert "Linked" in stage(checked, "export")["error"]["message"]
    assert not list(foreign.iterdir())


@pytest.mark.parametrize("damage", ["ambiguous", "malformed"])
def test_invalid_publication_candidates_request_inspection_not_repeat_resume(
    collection, monkeypatch, damage
):
    _, workspace = collection
    failed = fail_export(collection, monkeypatch, published=True)
    published = Path(stage(failed, "export")["published_outputs"][0]["path"])
    if damage == "ambiguous":
        shutil.copytree(published, published.with_name("second-candidate"))
    else:
        (published / "run.json").write_text("broken json", encoding="utf-8")
    before = snapshot(workspace)
    checked = inspect_preparation(workspace, verify=True)
    assert checked["next_action"] == "inspect_artifacts"
    assert stage(checked, "export")["integrity"] == "invalid"
    assert snapshot(workspace) == before
    with pytest.raises(preparation.PreparationRecoveryError) as error:
        resume_preparation(workspace, progress=lambda _: None)
    assert error.value.action == "inspect_artifacts"
    assert len(list(Path(failed["job"]).glob("attempts/export-*"))) == 1


def test_status_verification_retains_healthy_checks_and_is_read_only(collection, capsys):
    config, workspace = collection
    result = run(config, workspace)
    export = Path(result["outputs"]["export"]["path"])
    (export / "summary.json").write_text("corrupt", encoding="utf-8")
    before = snapshot(workspace)
    assert main(["status", str(workspace), "--verify", "--json"]) == 2
    status = json.loads(capsys.readouterr().out)
    assert status["prepared"] is False and status["artifact_verification"] == "failed"
    assert stage(status, "export")["integrity"] == "invalid"
    assert stage(status, "inventory")["integrity"] == "verified"
    assert status["verification_errors"][0]["stage"] == "export"
    assert status["next_commands"][0]["argv"][-3:] == ["--job", result["job_id"], "--json"]
    assert snapshot(workspace) == before


def test_source_validation_failure_records_the_active_stage(collection):
    config, workspace = collection
    run(config, workspace)
    (config.source / "added.txt").write_text("changed membership", encoding="utf-8")
    with pytest.raises(ValueError, match="membership changed"):
        resume_preparation(workspace, progress=lambda _: None)
    status = inspect_preparation(workspace)
    assert status["current_stage"] == "similarity"
    assert status["next_action"] == "new_job"


def test_verified_status_uses_frozen_artifacts_with_source_offline(collection, capsys):
    config, workspace = collection
    result = run(config, workspace)
    config.source.rename(config.source.with_name("offline originals"))
    before = snapshot(workspace)
    assert main(["status", str(workspace), "--job", result["job_id"], "--verify", "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["artifact_verification"] == "full" and checked["source_revalidated"] is False
    assert not checked["verification_errors"]
    assert all(
        item["integrity"] == "verified"
        for item in checked["stages"]
        if item["status"] == "completed"
    )
    assert snapshot(workspace) == before


def test_collection_selectors_and_source_guard_are_explicit(collection, capsys):
    config, workspace = collection
    result = run(config, workspace)
    registry = CollectionRegistry()
    registry.register(workspace, "fixture")
    before = snapshot(workspace)
    assert main(["status", "--collection", "fixture", "--job", result["job_id"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == result["job_id"]
    assert main(["status", str(workspace), "--collection", "fixture", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["next_action"] == "correct_arguments"
    document = json.loads(registry.path.read_text(encoding="utf-8"))
    document["collections"][0]["source"] = str(config.source.parent / "other-source")
    registry.path.write_text(json.dumps(document), encoding="utf-8")
    registry_before = registry.path.read_bytes()
    assert main(["status", "--collection", "fixture", "--json"]) == 2
    assert "source differs" in json.loads(capsys.readouterr().out)["error"]["message"]
    with pytest.raises(ValueError, match="Registered collection source"):
        resume_preparation(
            workspace,
            expected_job_id=result["job_id"],
            expected_source=config.source.parent / "wrong",
        )
    assert snapshot(workspace) == before and registry.path.read_bytes() == registry_before


def test_partial_tagging_reports_verified_saved_vectors_without_cache_claim(
    collection, monkeypatch, capsys
):
    config, workspace = collection
    make_bundle(
        bundle_path(config.models, config.tagging.model, config.tagging.revision),
        [Label(0, "object", 0)],
    )
    original = tagging._verified_bytes

    def fail_one(source, row, limits):
        if row["source_path"] == "a.png":
            raise OSError("Synthetic image read failure")
        return original(source, row, limits)

    monkeypatch.setattr(tagging, "_verified_bytes", fail_one)
    with pytest.raises(ValueError, match="completed with errors"):
        preparation.prepare_directory(config, workspace, captions="model", progress=lambda _: None)
    before = snapshot(workspace)
    status = inspect_preparation(workspace, verify=True)
    tagging_view = stage(status, "tagging")
    assert tagging_view["continuation"] == "retry_inference"
    evidence = tagging_view["published_outputs"][0]
    assert evidence["integrity"] == "verified_partial"
    assert evidence["verified_retained_score_vectors"] == 2
    assert evidence["inference_cache_reuse"] == "validated_during_resume"
    assert main(["status", str(workspace), "--verify"]) == 0
    rendered = capsys.readouterr().out
    assert (
        "Verified retained score vectors: 2; inference cache reuse checked during resume"
        in rendered
    )
    assert snapshot(workspace) == before
