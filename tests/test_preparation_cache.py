"""Live cache evidence stays read-only and independent of saved dataset acceptance."""

import builtins
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run
from test_preparation_recovery import snapshot
from test_tagging import make_bundle

from image_dataset_train import preparation
from image_dataset_train.cli import main
from image_dataset_train.model_bundle import Label, bundle_path
from image_dataset_train.preparation import inspect_preparation, resume_preparation
from image_dataset_train.wd_tagger import WDTagger


@pytest.fixture
def model_collection(collection):
    config, workspace = collection
    config = replace(config, tagging=replace(config.tagging, device="cpu", batch_size=1))
    make_bundle(
        bundle_path(config.models, config.tagging.model, config.tagging.revision),
        [Label(0, "object", 0), Label(1, "scene", 0)],
    )
    return config, workspace


def interrupted(model_collection, monkeypatch):
    """Retain one actual cache vector before an inference crash, without a scored run."""
    config, workspace = model_collection
    predict = WDTagger.predict
    calls = 0

    def crash(tagger, batch):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic interruption during inference")
        return predict(tagger, batch)

    monkeypatch.setattr(WDTagger, "predict", crash)
    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        preparation.prepare_directory(
            config, workspace, captions="model", offline=True, progress=lambda _: None
        )
    monkeypatch.setattr(WDTagger, "predict", predict)
    return inspect_preparation(workspace)


def interrupted_publication(model_collection, monkeypatch):
    config, workspace = model_collection
    checkpoint = preparation._checkpoint

    def crash(job, state, stage, path, *, recovered):
        if stage == "tagging":
            raise OSError("Synthetic crash after tagging publication")
        return checkpoint(job, state, stage, path, recovered=recovered)

    monkeypatch.setattr(preparation, "_checkpoint", crash)
    with pytest.raises(OSError, match="after tagging publication"):
        preparation.prepare_directory(
            config, workspace, captions="model", offline=True, progress=lambda _: None
        )
    monkeypatch.setattr(preparation, "_checkpoint", checkpoint)
    return inspect_preparation(workspace)


def test_interrupted_cache_audit_predicts_real_resume_reuse_without_writes(
    model_collection, monkeypatch, tmp_path, capsys
):
    config, workspace = model_collection
    (config.source / "alias.png").write_bytes((config.source / "a.png").read_bytes())
    failed = interrupted(model_collection, monkeypatch)
    tagging = next(s for s in failed["stages"] if s["stage"] == "tagging")
    assert not tagging["published_outputs"]
    before = snapshot(tmp_path)
    predict = WDTagger.predict

    def forbidden(*args, **kwargs):
        pytest.fail("Cache inspection performed inference, a download or cache mutation")

    with monkeypatch.context() as patch:
        patch.setattr(WDTagger, "predict", forbidden)
        patch.setattr("image_dataset_train.model_bundle.fetch_bundle", forbidden)
        patch.setattr("image_dataset_train.score_cache.ScoreCache.put", forbidden)
        checked = inspect_preparation(workspace, verify_cache=True)
        cache = checked["cache_verification"]
        assert cache["status"] == "complete"
        assert cache["eligible_occurrences"] == 4 and cache["eligible_unique_contents"] == 3
        assert cache["counts"] == {"valid": 1, "missing": 2, "invalid": 0}
        assert cache["source_verification"]["status"] == "verified"
        assert cache["implementation_match"] is True and cache["cache_relevant_for_resume"]
        assert cache["runtime"]["providers"] == ["CPUExecutionProvider"]
        assert not cache["inference_performed"] and not cache["application_writes"]
        assert checked["source_revalidated"] is True
        assert checked["artifact_verification"] == "not_rechecked"
        assert main(["status", str(workspace), "--verify-cache"]) == 0
        text = capsys.readouterr().out
        assert "4 eligible image occurrences; 3 unique contents" in text
        assert "1 valid; 2 missing; 0 invalid" in text
    assert snapshot(tmp_path) == before
    assert WDTagger.predict is predict
    resumed = resume_preparation(workspace, progress=lambda _: None)
    counts = resumed["outputs"]["tagging"]["summary"]
    assert counts["cached_images"] == 1 and counts["inferred_images"] == 2
    assert counts["duplicate_score_reuse"] == 1
    assert resumed["human_accepted"] is False


def test_default_and_artifact_status_do_not_import_cache_inspection_or_read_sources(
    model_collection, monkeypatch
):
    _, workspace = model_collection
    interrupted(model_collection, monkeypatch)
    importer = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "image_dataset_train.cache_inspection":
            pytest.fail("Ordinary status imported live cache inspection")
        return importer(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Ordinary status revalidated sources")

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(preparation, "_assert_sources", forbidden)
    for verify in (False, True):
        checked = inspect_preparation(workspace, verify=verify)
        assert "cache_verification" not in checked
        assert checked["source_revalidated"] is False


def test_existing_caption_cache_check_has_no_source_or_model_dependency(
    collection, monkeypatch, tmp_path, capsys
):
    config, workspace = collection
    run(config, workspace)
    config.source.rename(config.source.with_name("offline"))

    def forbidden(*args, **kwargs):
        pytest.fail("Existing-caption cache inspection touched the model or sources")

    monkeypatch.setattr(preparation, "_assert_sources", forbidden)
    monkeypatch.setattr(preparation, "_implementation_identity", forbidden)
    monkeypatch.setattr(WDTagger, "__init__", forbidden)
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["cache_verification"]["status"] == "not_applicable"
    assert checked["prepared"] and checked["source_revalidated"] is False
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("change", ["sidecar", "offline"])
def test_cache_source_conflicts_preserve_saved_artifact_verification(
    model_collection, monkeypatch, tmp_path, capsys, change
):
    config, workspace = model_collection
    failed = interrupted(model_collection, monkeypatch)
    if change == "sidecar":
        (config.source / "a.txt").write_text("changed sidecar", encoding="utf-8")
    else:
        config.source.rename(config.source.with_name("offline"))
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify", "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    cache = checked["cache_verification"]
    expected = "changed" if change == "sidecar" else "offline"
    assert cache["source_verification"]["status"] == expected
    assert cache["has_diagnostics"] and checked["source_revalidated"] is False
    assert checked["artifact_verification"] == "full" and not checked["verification_errors"]
    commands = checked["next_commands"]
    if change == "sidecar":
        assert commands[0]["argv"][1] == "prepare" and "--new" in commands[0]["argv"]
    for command in commands:
        if command["argv"][1] in {"status", "resume"}:
            assert command["argv"][command["argv"].index("--job") + 1] == failed["job_id"]
    assert snapshot(tmp_path) == before


def test_invalid_inventory_prevents_cache_counts_and_native_session_loading(
    model_collection, monkeypatch, tmp_path
):
    _, workspace = model_collection
    failed = interrupted(model_collection, monkeypatch)
    inventory = Path(failed["outputs"]["inventory"]["path"])
    (inventory / "summary.json").write_text("corrupt", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid inventory initialized a native model session")

    monkeypatch.setattr(WDTagger, "__init__", forbidden)
    before = snapshot(tmp_path)
    checked = inspect_preparation(workspace, verify_cache=True)
    cache = checked["cache_verification"]
    assert cache["reason"] == "inventory_invalid" and cache["counts"] is None
    assert cache["inventory_verification"] == "invalid"
    assert checked["artifact_verification"] == "not_rechecked"
    assert snapshot(tmp_path) == before


def test_historical_cache_audit_does_not_claim_current_job_or_change_binding(
    model_collection, monkeypatch, tmp_path, capsys
):
    config, workspace = model_collection
    first = interrupted(model_collection, monkeypatch)
    current = preparation.prepare_directory(
        config, workspace, captions="model", offline=True, new=True, progress=lambda _: None
    )
    before = snapshot(tmp_path)
    assert (
        main(["status", str(workspace), "--job", first["job_id"], "--verify-cache", "--json"]) == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["cache_verification"]["is_current_job"] is False
    assert "historical_job" in checked["cache_verification"]["continuation_constraints"]
    assert checked["next_action"] == "select_current_job"
    assert checked["next_commands"][0]["argv"][-3:] == ["--job", current["job_id"], "--json"]
    assert snapshot(tmp_path) == before


def test_implementation_drift_is_separate_from_valid_cache_entries(
    model_collection, monkeypatch, capsys
):
    _, workspace = model_collection
    interrupted(model_collection, monkeypatch)
    identity = preparation._implementation_identity()
    monkeypatch.setattr(
        preparation, "_implementation_identity", lambda: {**identity, "version": "old"}
    )
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    cache = checked["cache_verification"]
    assert cache["counts"]["valid"] == 1 and cache["implementation_match"] is False
    assert "implementation_changed_or_unavailable" in cache["continuation_constraints"]
    assert "--new" in checked["next_commands"][0]["argv"]


def test_completed_dataset_remains_prepared_when_its_cache_disappears(model_collection, tmp_path):
    config, workspace = model_collection
    result = preparation.prepare_directory(
        config, workspace, captions="model", offline=True, progress=lambda _: None
    )
    assert result["prepared"]
    config.scores.rename(config.scores.with_name("retained-cache"))
    before = snapshot(tmp_path)
    checked = inspect_preparation(workspace, verify=True, verify_cache=True)
    cache = checked["cache_verification"]
    assert checked["prepared"] and checked["artifact_verification"] == "full"
    assert cache["counts"] == {"valid": 0, "missing": 3, "invalid": 0}
    assert cache["cache_relevant_for_resume"] is False and not cache["has_diagnostics"]
    assert checked["human_accepted"] is False
    assert snapshot(tmp_path) == before


def test_missing_model_is_an_unavailable_audit_not_zero_cached(
    model_collection, monkeypatch, tmp_path, capsys
):
    config, workspace = model_collection
    interrupted(model_collection, monkeypatch)
    model = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    model.rename(model.with_name("offline-model"))
    before = snapshot(tmp_path)
    checked = inspect_preparation(workspace, verify_cache=True)
    assert checked["cache_verification"]["status"] == "unavailable"
    assert checked["cache_verification"]["counts"] is None
    assert checked["cache_verification"]["has_diagnostics"]
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["next_action"] == "fetch_model"
    assert rendered["next_commands"][0]["argv"][1] == "fetch-model"
    assert rendered["config"] in rendered["next_commands"][0]["argv"]
    assert snapshot(tmp_path) == before


def test_runtime_unavailable_offers_recheck_without_unusable_resume(
    model_collection, monkeypatch, tmp_path, capsys
):
    _, workspace = model_collection
    interrupted(model_collection, monkeypatch)

    def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic provider unavailable")

    monkeypatch.setattr(WDTagger, "__init__", unavailable)
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    assert checked["cache_verification"]["reason"] == "runtime_unavailable"
    assert checked["cache_verification"]["counts"] is None
    assert checked["next_action"] == "inspect_cache"
    assert all(command["argv"][1] != "resume" for command in checked["next_commands"])
    assert "--verify-cache" in checked["next_commands"][0]["argv"]
    assert snapshot(tmp_path) == before


def test_corrupt_cache_paths_are_bounded_and_preserved_in_human_status(
    model_collection, tmp_path, capsys
):
    config, workspace = model_collection
    (config.source / "fourth.png").write_bytes((config.source / "a.png").read_bytes() + b"extra")
    preparation.prepare_directory(
        config, workspace, captions="model", offline=True, progress=lambda _: None
    )
    paths = sorted(config.scores.rglob("*.npz"))
    assert len(paths) == 4
    for path in paths:
        path.write_bytes(b"corrupt retained evidence")
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify-cache"]) == 1
    text = capsys.readouterr().out
    assert "0 valid; 0 missing; 4 invalid" in text
    assert text.count("Invalid cache:") == 3
    assert "1 additional invalid cache entries; use --json" in text
    checked = inspect_preparation(workspace, verify=True, verify_cache=True)
    assert checked["prepared"] and checked["artifact_verification"] == "full"
    assert len(checked["cache_verification"]["entries"]) == 4
    assert snapshot(tmp_path) == before


def test_changed_model_cannot_use_a_job_bound_to_other_model_content(
    model_collection, monkeypatch, capsys
):
    config, workspace = model_collection
    interrupted(model_collection, monkeypatch)
    model = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    model.rename(model.with_name("retained-model"))
    make_bundle(model, [Label(0, "replacement", 0), Label(1, "changed", 0)])
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    assert checked["cache_verification"]["reason"] == "model_identity_changed"
    assert checked["cache_verification"]["counts"] is None
    assert checked["next_action"] == "new_job"
    assert "--new" in checked["next_commands"][0]["argv"]


@pytest.mark.parametrize("model_state", ["missing", "changed"])
def test_completed_tagging_publication_recovers_without_local_model_or_cache_dependency(
    model_collection, monkeypatch, tmp_path, capsys, model_state
):
    config, workspace = model_collection
    interrupted_publication(model_collection, monkeypatch)
    model = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    model.rename(model.with_name("retained-model"))
    if model_state == "changed":
        make_bundle(model, [Label(0, "replacement", 0), Label(1, "changed", 0)])
    config.scores.rename(config.scores.with_name("retained-cache"))
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    cache = checked["cache_verification"]
    assert cache["status"] == "unavailable"
    assert cache["cache_relevant_for_resume"] is False
    assert cache["tagging_continuation"] == "recover_publication"
    assert cache["tagging_verification"]["integrity"] == "verified"
    assert checked["next_action"] == "resume"
    assert checked["next_commands"][0]["argv"][1] == "resume"
    assert all(command["argv"][1] != "fetch-model" for command in checked["next_commands"])
    assert main(["status", str(workspace), "--verify-cache"]) == 1
    text = capsys.readouterr().out
    assert "Verified tagging publication can be recovered" in text
    assert "Missing entries need inference" not in text
    assert snapshot(tmp_path) == before
    resumed = resume_preparation(workspace, progress=lambda _: None)
    assert resumed["prepared"]
    assert not config.scores.exists()


def test_missing_publication_runtime_is_unavailable_evidence_not_invalid_artifact(
    model_collection, monkeypatch, tmp_path, capsys
):
    _, workspace = model_collection
    interrupted_publication(model_collection, monkeypatch)
    importer = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name in {
            "image_dataset_train.scored_runs",
            "image_dataset_train.score_cache",
        }:
            raise ModuleNotFoundError("Synthetic missing optional tagging dependency")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    before = snapshot(tmp_path)
    assert main(["status", str(workspace), "--verify-cache", "--json"]) == 1
    checked = json.loads(capsys.readouterr().out)
    cache = checked["cache_verification"]
    assert cache["status"] == "unavailable" and cache["reason"] == "runtime_unavailable"
    assert cache["tagging_verification"]["integrity"] == "unavailable"
    assert "tagging_artifacts_invalid" not in cache["continuation_constraints"]
    assert checked["artifact_verification"] == "not_rechecked"
    assert checked["next_action"] == "inspect_cache"
    assert not checked["verification_errors"]
    assert snapshot(tmp_path) == before


def test_corrupt_tagging_publication_remains_a_separate_continuation_failure(
    model_collection, monkeypatch, tmp_path
):
    _, workspace = model_collection
    failed = interrupted_publication(model_collection, monkeypatch)
    tagging = next(stage for stage in failed["stages"] if stage["stage"] == "tagging")
    publication = Path(tagging["published_outputs"][0]["path"])
    (publication / "summary.json").write_text("corrupt retained publication", encoding="utf-8")
    before = snapshot(tmp_path)
    checked = inspect_preparation(workspace, verify_cache=True)
    cache = checked["cache_verification"]
    assert cache["counts"] == {"valid": 3, "missing": 0, "invalid": 0}
    assert cache["tagging_verification"]["integrity"] == "invalid"
    assert cache["cache_relevant_for_resume"] is True
    assert "tagging_artifacts_invalid" in cache["continuation_constraints"]
    assert checked["next_action"] == "inspect_artifacts" and cache["has_diagnostics"]
    assert snapshot(tmp_path) == before
