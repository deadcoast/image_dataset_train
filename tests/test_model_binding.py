"""Configured requests cannot execute or approve a self-consistent foreign bundle."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from filelock import FileLock, Timeout
from test_preparation import collection as collection
from test_preparation_cache import model_collection as model_collection
from test_tagging import labels as labels
from test_tagging import make_bundle
from test_tagging import setup as setup

from image_dataset_train import doctor, model_bundle, preparation, tagging, wd_tagger
from image_dataset_train.cache_inspection import inspect_inference_cache
from image_dataset_train.model_bundle import MODELS, bundle_path, fetch_bundle, load_bundle


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def metadata(path):
    return json.loads((path / "model.json").read_text(encoding="utf-8"))


def rewrite(path, changes, *, remove=None):
    value = metadata(path)
    value.update(changes)
    if remove:
        value.pop(remove)
    identity = {key: value.get(key) for key in ("repo", "revision", "files")}
    value["artifact_id"] = model_bundle.fingerprint(identity)
    (path / "model.json").write_text(json.dumps(value), encoding="utf-8")
    return value


def foreign(path):
    return rewrite(
        path,
        {
            "model": "eva02-large-v3",
            "repo": MODELS["eva02-large-v3"].repo,
            "revision": MODELS["eva02-large-v3"].revision,
        },
    )


def forbid(*args, **kwargs):
    pytest.fail("Mismatched model must be rejected before runtime, inference or download")


@pytest.mark.parametrize("model", sorted(MODELS))
@pytest.mark.parametrize("revision", [None, "a" * 40])
def test_matching_requested_model_and_explicit_revision(tmp_path, labels, model, revision):
    path = bundle_path(tmp_path / "models", model, revision)
    make_bundle(path, labels, model_name=model, revision=revision)
    before = snapshot(tmp_path)
    checked = load_bundle(path, model=model, revision=revision)
    assert checked.metadata["model"] == model
    assert checked.metadata["repo"] == MODELS[model].repo
    assert checked.metadata["revision"] == (revision or MODELS[model].revision)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "changes,remove,field",
    [
        ({"model": "eva02-large-v3"}, None, "model"),
        ({"repo": "fixture/another-repository"}, None, "repo"),
        ({"revision": "a" * 40}, None, "revision"),
        ({}, "model", "model"),
        ({}, "repo", "repo"),
        ({}, "revision", "revision"),
    ],
)
def test_independent_declared_field_mismatch_preserves_generic_inspection(
    tmp_path, labels, changes, remove, field
):
    path = bundle_path(tmp_path / "models", "swinv2-v3")
    make_bundle(path, labels)
    value = rewrite(path, changes, remove=remove)
    before = snapshot(tmp_path)
    # Generic inspection still verifies the artifact's own hashes and identity.
    assert load_bundle(path).metadata == value
    with pytest.raises(ValueError, match=f"selection mismatch.*{field}"):
        load_bundle(path, model="swinv2-v3")
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "model,revision",
    [("unknown", None), ("swinv2-v3", "main"), ("swinv2-v3", "A" * 40), (None, "a" * 40)],
)
def test_invalid_expected_selection_rejects_before_opening_artifact(tmp_path, model, revision):
    with pytest.raises(ValueError, match="unknown WD|40-character|expected model"):
        load_bundle(tmp_path / "missing", model=model, revision=revision)
    assert snapshot(tmp_path) == {}


@pytest.mark.parametrize("damage", ["file", "artifact_id"])
def test_matching_selection_does_not_replace_existing_integrity_checks(tmp_path, labels, damage):
    path = bundle_path(tmp_path, "swinv2-v3")
    make_bundle(path, labels)
    if damage == "file":
        (path / "model.onnx").write_bytes(b"changed")
    else:
        value = metadata(path)
        value["artifact_id"] = "0" * 64
        (path / "model.json").write_text(json.dumps(value), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="hash mismatch|identity mismatch"):
        load_bundle(path, model="swinv2-v3")
    assert snapshot(tmp_path) == before


def test_fetch_reuse_checks_configured_selection_without_download(tmp_path, labels, monkeypatch):
    root = tmp_path / "models"
    path = bundle_path(root, "swinv2-v3")
    make_bundle(path, labels)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=forbid))
    assert fetch_bundle(root, "swinv2-v3") == path
    foreign(path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="selection mismatch"):
        fetch_bundle(root, "swinv2-v3")
    assert snapshot(tmp_path) == before


def test_fresh_fetch_pins_and_checks_matching_custom_revision(tmp_path, labels, monkeypatch):
    source = make_bundle(tmp_path / "download-source", labels).directory
    revision = "b" * 40
    calls = []

    def download(**request):
        calls.append(request)
        destination = request["local_dir"] / request["filename"]
        destination.write_bytes((source / request["filename"]).read_bytes())
        return destination

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    path = fetch_bundle(tmp_path / "models", "eva02-large-v3", revision)
    assert [request["filename"] for request in calls] == ["model.onnx", "selected_tags.csv"]
    assert all(
        request["repo_id"] == MODELS["eva02-large-v3"].repo
        and request["revision"] == revision
        and request["token"] is False
        for request in calls
    )
    assert load_bundle(path, model="eva02-large-v3", revision=revision).metadata["model"] == (
        "eva02-large-v3"
    )


def test_fresh_fetch_verifies_final_publication_before_return(tmp_path, labels, monkeypatch):
    source = make_bundle(tmp_path / "download-source", labels).directory

    def download(**request):
        destination = request["local_dir"] / request["filename"]
        destination.write_bytes((source / request["filename"]).read_bytes())
        return destination

    write = model_bundle.atomic_json

    def changed_publication(path, value):
        write(path, value)
        foreign(path.parent)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    monkeypatch.setattr(model_bundle, "atomic_json", changed_publication)
    with pytest.raises(ValueError, match="selection mismatch"):
        fetch_bundle(tmp_path / "models", "swinv2-v3")
    retained = bundle_path(tmp_path / "models", "swinv2-v3")
    assert load_bundle(retained).metadata["model"] == "eva02-large-v3"


def test_tagging_and_cache_inspection_reject_foreign_slot_before_session(setup, monkeypatch):
    config, inventory = setup
    slot = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    foreign(slot)
    before = snapshot(config.source.parent)
    monkeypatch.setattr(tagging, "WDTagger", forbid)
    monkeypatch.setattr(wd_tagger, "WDTagger", forbid)
    with pytest.raises(ValueError, match="selection mismatch"):
        tagging.tag_inventory(config, inventory)
    result = inspect_inference_cache(config, inventory)
    assert result["status"] == "unavailable" and result["reason"] == "model_unavailable"
    assert "selection mismatch" in result["error"]["message"]
    assert result["inference_performed"] is False and result["application_writes"] is False
    assert result["runtime"] is None and result["model_artifact_id"] is None
    assert snapshot(config.source.parent) == before


def test_preparation_rejects_wrong_slot_before_recording_verified_model(setup, monkeypatch):
    config, _ = setup
    slot = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    foreign(slot)
    state = {"options": {"offline": True}, "stages": {}}
    before_state = copy.deepcopy(state)
    before_files = snapshot(config.source.parent)
    monkeypatch.setattr(preparation, "_save", forbid)
    monkeypatch.setattr(tagging, "tag_inventory", forbid)
    with pytest.raises(ValueError, match="selection mismatch"):
        preparation._execute("tagging", config, config.runs / "unused-job", state, lambda _: None)
    assert state == before_state
    assert snapshot(config.source.parent) == before_files


def test_generated_onnx_execution_uses_matching_custom_model_default(setup, labels):
    config, inventory = setup
    requested = replace(config.tagging, model="eva02-large-v3", revision="c" * 40)
    config = replace(config, tagging=requested)
    make_bundle(
        bundle_path(config.models, requested.model, requested.revision),
        labels,
        model_name=requested.model,
        revision=requested.revision,
    )
    before = snapshot(config.source)
    run, summary = tagging.tag_inventory(config, inventory)
    saved = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert summary["inferred_images"] == 2
    assert saved["model"]["model"] == requested.model
    assert saved["model"]["revision"] == requested.revision
    assert saved["default_general_threshold"] == MODELS[requested.model].suggested_general_threshold
    assert snapshot(config.source) == before


def test_checkpoint_binding_uses_frozen_config_without_requiring_live_model(
    model_collection, tmp_path, monkeypatch
):
    config, workspace = model_collection
    result = preparation.prepare_directory(
        config, workspace, captions="model", offline=True, progress=lambda _: None
    )
    job = Path(result["job"])
    state = json.loads((job / "job.json").read_text(encoding="utf-8"))
    run = Path(result["outputs"]["tagging"]["path"])
    slot = bundle_path(config.models, config.tagging.model, config.tagging.revision)
    offline = slot.with_name(slot.name + "-offline")
    assert slot.resolve().is_relative_to(tmp_path.resolve()) and not offline.exists()
    slot.rename(offline)
    monkeypatch.setattr(model_bundle, "load_bundle", forbid)
    before = snapshot(tmp_path)
    preparation._verify_input_identity(job, state, "tagging", run)
    assert snapshot(tmp_path) == before

    # A foreign identity consistently saved in both job and artifact must still
    # fail the original frozen configuration; comparing only the two is insufficient.
    declared = copy.deepcopy(state["model_identity"])
    declared.update(
        model="eva02-large-v3",
        repo=MODELS["eva02-large-v3"].repo,
        revision=MODELS["eva02-large-v3"].revision,
    )
    declared["artifact_id"] = model_bundle.fingerprint(
        {key: declared[key] for key in ("repo", "revision", "files")}
    )
    state["model_identity"] = declared
    report = json.loads((run / "run.json").read_text(encoding="utf-8"))
    report["model"] = declared
    (run / "run.json").write_text(json.dumps(report), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(preparation.PreparationRecoveryError, match="selection mismatch"):
        preparation._verify_input_identity(job, state, "tagging", run)
    assert snapshot(tmp_path) == before


def test_doctor_preserves_foreign_bundle_before_replacement(tmp_path, labels):
    home = tmp_path / "app"
    slot = bundle_path(home / "models", "swinv2-v3")
    make_bundle(slot, labels, model_name="eva02-large-v3")
    original = snapshot(slot)
    calls = []

    def fetch(root, requested):
        calls.append(requested)
        assert not slot.exists()
        make_bundle(slot, labels, model_name=requested)
        return slot

    assert doctor.repair_model(home, fetch=fetch) == slot
    assert calls == ["swinv2-v3"]
    backups = list((home / "recovery" / "models").iterdir())
    assert len(backups) == 1 and snapshot(backups[0]) == original
    assert load_bundle(slot, model="swinv2-v3").metadata["model"] == "swinv2-v3"


def test_doctor_rejects_mismatched_fetch_result_and_retains_backup(tmp_path, labels):
    home = tmp_path / "app"
    slot = bundle_path(home / "models", "swinv2-v3")
    make_bundle(slot, labels, model_name="eva02-large-v3")
    original = snapshot(slot)

    def fetch(root, requested):
        make_bundle(slot, labels, model_name="eva02-large-v3")
        return slot

    with pytest.raises(ValueError, match="selection mismatch"):
        doctor.repair_model(home, fetch=fetch)
    backup = next((home / "recovery" / "models").iterdir())
    assert snapshot(backup) == original
    assert load_bundle(slot).metadata["model"] == "eva02-large-v3"
    assert all(b'"model_ready"' not in raw for raw in snapshot(home / "logs").values())


def test_busy_model_lock_prevents_preservation_or_replacement(tmp_path, labels):
    home = tmp_path / "app"
    slot = bundle_path(home / "models", "swinv2-v3")
    make_bundle(slot, labels, model_name="eva02-large-v3")
    (home / "locks").mkdir()
    before = snapshot(slot)
    with FileLock(str(home / "locks" / "model.lock"), timeout=0):
        with pytest.raises(Timeout):
            doctor.repair_model(home, fetch=forbid)
    assert snapshot(slot) == before
    assert not (home / "recovery" / "models").exists()


def test_doctor_readonly_check_does_not_accept_foreign_slot(tmp_path, labels, monkeypatch):
    home = tmp_path / "app"
    slot = bundle_path(home / "models", "swinv2-v3")
    make_bundle(slot, labels, model_name="eva02-large-v3")
    before = snapshot(home)
    monkeypatch.setattr(doctor, "runtime_probe", lambda: (True, "fixture runtime"))
    checks = doctor.check_all(home)
    model = next(check for check in checks if check.name == "model")
    assert model.status == "error" and "selection mismatch" in model.detail
    assert snapshot(home) == before
