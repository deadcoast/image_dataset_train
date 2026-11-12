"""Trainer status and downloads refer to one checked export/receipt observation."""

import hashlib
import json
import os
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import pytest
from test_exports import _receipt
from test_exports import reviewed as reviewed

from image_dataset_train import trainer_receipts
from image_dataset_train.cli import main
from image_dataset_train.exporting import export_dataset
from image_dataset_train.qa import create_qa
from image_dataset_train.review_ui import ReviewSession, make_server
from image_dataset_train.trainer_receipts import receipt_artifact, trainer_status


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tree(root):
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def rewrite_failed(receipt):
    result = json.loads((receipt / "result.json").read_bytes())
    result.update(qualified=False, error="Same-ID replacement failed")
    (receipt / "result.json").write_text(json.dumps(result), encoding="utf-8")
    meta = json.loads((receipt / "run.json").read_bytes())
    meta["status"] = "failed"
    meta["files"]["result.json"] = sha((receipt / "result.json").read_bytes())
    (receipt / "run.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture
def exported(reviewed):
    config, groups, drafts = reviewed
    export, _ = export_dataset(config, groups, captions_run=drafts)
    receipt = _receipt(config, export, 1)
    return config, export, receipt


def assert_export_invalid(result):
    assert result["status"] == "export_invalid"
    assert result["verification"] is None
    assert result["latest_receipt"] is None and result["receipts"] == []
    assert "export_run_sha256" not in result and "export_manifest_sha256" not in result
    assert result["error"]


@pytest.mark.parametrize("name", ["run.json", "manifest.jsonl", "summary.json", "train.toml"])
def test_export_changes_after_verification_never_return_old_pass(exported, monkeypatch, name):
    config, export, receipt = exported
    target = export / name
    original, stamp = target.read_bytes(), target.stat()
    verify = trainer_receipts._verify_export
    protected = tree(receipt), tree(config.source)

    def mutate(directory, meta):
        result = verify(directory, meta)
        target.write_bytes(original + b" ")
        os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        return result

    monkeypatch.setattr(trainer_receipts, "_verify_export", mutate)
    result = trainer_status(
        export, config.runs, expected_export_sha256=sha((export / "run.json").read_bytes())
    )
    assert_export_invalid(result)
    assert target.read_bytes() == original + b" "  # Inspection does not repair the fault.
    assert (tree(receipt), tree(config.source)) == protected


def test_verifier_uses_the_metadata_that_was_captured_and_hashed(exported, monkeypatch):
    config, export, _ = exported
    original = (export / "run.json").read_bytes()
    before = json.loads(original)
    read = trainer_receipts._ReadSet.read
    verify = trainer_receipts._verify_export
    received = []

    def replace_metadata(snapshot, name):
        raw = read(snapshot, name)
        if snapshot.directory == export and name == "run.json":
            changed = {**before, "completed_at": "2026-11-12T00:00:00+00:00"}
            (export / "run.json").write_text(json.dumps(changed), encoding="utf-8")
        return raw

    def inspect(directory, metadata):
        received.append(metadata)
        return verify(directory, metadata)

    monkeypatch.setattr(trainer_receipts._ReadSet, "read", replace_metadata)
    monkeypatch.setattr(trainer_receipts, "_verify_export", inspect)
    assert_export_invalid(trainer_status(export, config.runs))
    assert received == [before]


@pytest.mark.parametrize("name", ["run.json", "manifest.jsonl"])
def test_export_changes_during_receipt_discovery_clear_verified_ui_state(
    exported, monkeypatch, name
):
    config, export, _ = exported
    payload = trainer_receipts._receipt_payload

    def mutate(*args):
        result = payload(*args)
        target = export / name
        target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", mutate)
    assert_export_invalid(trainer_status(export, config.runs))


@pytest.mark.parametrize("damage", ["image", "caption", "extra", "removed"])
def test_media_and_export_membership_are_fenced_after_receipt_discovery(
    exported, monkeypatch, damage
):
    config, export, _ = exported
    row = json.loads((export / "manifest.jsonl").read_bytes().splitlines()[0])
    payload = trainer_receipts._receipt_payload

    def mutate(*args):
        result = payload(*args)
        if damage == "extra":
            (export / "untracked.txt").write_text("Untracked member", encoding="utf-8")
        elif damage == "removed":
            (export / row["caption_path"]).unlink()
        else:
            target = export / row["image_path" if damage == "image" else "caption_path"]
            target.write_bytes(target.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", mutate)
    assert_export_invalid(trainer_status(export, config.runs))


def test_export_metadata_is_checked_after_final_payload_reads(exported, monkeypatch):
    config, export, _ = exported
    checked = trainer_receipts._checked
    manifest_checks = 0

    def mutate_after_manifest(directory, name, digest):
        nonlocal manifest_checks
        raw = checked(directory, name, digest)
        if directory == export and name == "manifest.jsonl":
            manifest_checks += 1
            if manifest_checks == 2:
                path = export / "run.json"
                path.write_bytes(path.read_bytes() + b" ")
        return raw

    monkeypatch.setattr(trainer_receipts, "_checked", mutate_after_manifest)
    assert_export_invalid(trainer_status(export, config.runs))
    assert manifest_checks == 2


def test_receipt_metadata_is_checked_after_its_result(exported, monkeypatch):
    config, export, receipt = exported
    checked = trainer_receipts._checked

    def mutate_after_result(directory, name, digest):
        raw = checked(directory, name, digest)
        if directory == receipt and name == "result.json":
            path = receipt / "run.json"
            path.write_bytes(path.read_bytes() + b" ")
        return raw

    monkeypatch.setattr(trainer_receipts, "_checked", mutate_after_result)
    result = trainer_status(export, config.runs)
    assert result["status"] == "history_incomplete" and result["latest_receipt"] is None


@pytest.mark.parametrize("name", ["run.json", "result.json", "loader.log", "complete_rewrite"])
def test_receipt_changes_after_capture_do_not_inherit_pass(exported, monkeypatch, name):
    config, export, receipt = exported
    old_meta, old_result = (
        (receipt / "run.json").read_bytes(),
        (receipt / "result.json").read_bytes(),
    )
    payload = trainer_receipts._receipt_payload
    protected = tree(export), tree(config.source)

    def mutate(*args):
        result = payload(*args)
        if name == "complete_rewrite":
            rewrite_failed(receipt)
        else:
            target = receipt / name
            target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", mutate)
    result = trainer_status(export, config.runs)
    assert result["status"] == "history_incomplete" and result["latest_receipt"] is None
    item = result["receipts"][0]
    assert item["status"] == "invalid" and item["integrity"] is False
    assert item["receipt_run_sha256"] == sha(old_meta)
    assert item["receipt_result_sha256"] == sha(old_result)
    assert item["result"] == json.loads(old_result)
    assert (tree(export), tree(config.source)) == protected


def test_same_id_rewrite_between_association_and_integrity_cannot_mix_bytes(exported, monkeypatch):
    config, export, receipt = exported
    payload = trainer_receipts._receipt_payload
    before = json.loads((receipt / "result.json").read_bytes())

    def rewrite_before_check(*args):
        rewrite_failed(receipt)
        return payload(*args)

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", rewrite_before_check)
    result = trainer_status(export, config.runs)
    assert result["status"] == "history_incomplete"
    assert result["receipts"][0]["result"] == before
    assert result["receipts"][0]["integrity"] is False
    assert result["latest_receipt"] is None


def test_final_fence_covers_earlier_receipts_even_when_a_later_receipt_passes(
    exported, monkeypatch
):
    config, export, first = exported
    second = _receipt(config, export, 2)
    read = trainer_receipts._ReadSet.read

    def mutate_earlier(snapshot, name):
        raw = read(snapshot, name)
        if snapshot.directory == second and name == "result.json":
            rewrite_failed(first)
        return raw

    monkeypatch.setattr(trainer_receipts._ReadSet, "read", mutate_earlier)
    result = trainer_status(export, config.runs)
    assert result["status"] == "history_incomplete" and result["latest_receipt"] is None
    items = {item["id"]: item for item in result["receipts"]}
    assert items[first.name]["status"] == "invalid"
    assert items[second.name]["status"] == "passed"  # Checked historical evidence survives.


def test_new_receipt_during_discovery_requires_refresh(exported, monkeypatch):
    config, export, _ = exported
    payload = trainer_receipts._receipt_payload

    def publish_new(*args):
        result = payload(*args)
        _receipt(config, export, 2, qualified=False)
        return result

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", publish_new)
    result = trainer_status(export, config.runs)
    assert result["status"] == "history_incomplete" and result["latest_receipt"] is None
    assert any("history changed" in row["error"] for row in result["discovery_errors"])


@pytest.mark.parametrize("change", ["rewrite", "arrival", "removal"])
def test_receipt_changes_during_final_export_media_pass_are_checked(exported, monkeypatch, change):
    config, export, receipt = exported
    verify = trainer_receipts._ReadSet.verify
    export_passes = 0

    def change_receipt(snapshot):
        nonlocal export_passes
        if snapshot.directory == export:
            export_passes += 1
            if export_passes == 2:
                if change == "rewrite":
                    rewrite_failed(receipt)
                elif change == "arrival":
                    _receipt(config, export, 2, qualified=False)
                else:
                    for name in ("run.json", "result.json", "loader.log"):
                        (receipt / name).unlink()
                    receipt.rmdir()
        return verify(snapshot)

    monkeypatch.setattr(trainer_receipts._ReadSet, "verify", change_receipt)
    result = trainer_status(export, config.runs)
    assert export_passes == 2
    assert result["status"] == "history_incomplete" and result["latest_receipt"] is None
    assert result["discovery_errors"]


def test_discovery_failure_does_not_skip_export_return_fence(exported, monkeypatch):
    config, export, _ = exported

    def fail(_):
        target = export / "run.json"
        target.write_bytes(target.read_bytes() + b" ")
        raise OSError("Injected receipt discovery failure")

    monkeypatch.setattr(trainer_receipts, "_directories", fail)
    assert_export_invalid(trainer_status(export, config.runs))


def test_relocation_offline_legacy_and_history_remain_read_only(exported, monkeypatch):
    config, export, receipt = exported
    _receipt(config, export, 2, revision="historical-trainer")
    _receipt(config, export, 3, export_run_sha256="0" * 64)
    relocated = export.with_name("relocated export")
    export.rename(relocated)
    config.source.rename(config.source.with_name("offline-source"))
    before = tree(relocated), tree(config.runs)
    opened = Path.open

    def read_only(path, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        assert not path.is_relative_to(config.source)
        return opened(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", read_only)
        result = trainer_status(relocated, config.runs)
        raw = receipt_artifact(receipt, "result.json")  # No optional pin in historical callers.
    assert result["status"] == "passed" and result["latest_receipt"] == receipt.name
    assert [item["status"] for item in result["receipts"]] == ["other_pin", "passed"]
    assert json.loads(raw)["qualified"] is True
    assert result["export_run_sha256"] == sha((relocated / "run.json").read_bytes())
    assert result["export_manifest_sha256"] == sha((relocated / "manifest.jsonl").read_bytes())
    assert (tree(relocated), tree(config.runs)) == before


@pytest.mark.parametrize("name", ["result.json", "loader.log"])
def test_artifact_download_fences_metadata_and_payload_before_return(exported, monkeypatch, name):
    _, _, receipt = exported
    payload = trainer_receipts._receipt_payload

    def mutate(*args):
        result = payload(*args)
        rewrite_failed(receipt)
        return result

    monkeypatch.setattr(trainer_receipts, "_receipt_payload", mutate)
    with pytest.raises(ValueError, match="changed during inspection"):
        receipt_artifact(receipt, name)


def test_session_pin_survives_same_id_rewrite_and_status_refresh(exported):
    config, export, receipt = exported
    report, _ = create_qa(config, export)
    session = ReviewSession(config, report)
    first = session.training()
    digest = first["receipts"][0]["receipt_run_sha256"]
    assert digest in first["receipts"][0]["artifacts"]["result.json"]
    rewrite_failed(receipt)
    with pytest.raises(ValueError, match="changed since it was displayed"):
        session.trainer_artifact(receipt.name, "result.json")
    assert session.training()["status"] == "failed"
    with pytest.raises(ValueError, match="changed since it was displayed"):
        session.trainer_artifact(receipt.name, "result.json", expected_receipt_sha256=digest)
    assert json.loads(session.trainer_artifact(receipt.name, "result.json"))["qualified"] is False


def test_http_links_keep_the_displayed_pin_after_another_refresh(exported):
    config, export, receipt = exported
    report, _ = create_qa(config, export)
    with make_server(config, report) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        prefix = urlsplit(server.url).path

        def get(path):
            connection = HTTPConnection(server.authority)
            connection.request("GET", prefix + path)
            response = connection.getresponse()
            result = response.status, response.read()
            connection.close()
            return result

        try:
            first = json.loads(get("api/training")[1])
            old_link = first["receipts"][0]["artifacts"]["result.json"]
            assert get(old_link)[0] == 200
            rewrite_failed(receipt)
            assert get(old_link)[0] == 400
            second = json.loads(get("api/training")[1])
            assert second["status"] == "failed"
            new_link = second["receipts"][0]["artifacts"]["result.json"]
            assert new_link != old_link
            assert get(old_link)[0] == 400
            status, raw = get(new_link)
            assert status == 200 and json.loads(raw)["qualified"] is False
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_cli_reports_export_drift_as_failed_inspection(exported, monkeypatch, capsys):
    config, export, _ = exported
    settings = config.runs.parent / "trainer-status.toml"
    settings.write_text('schema_version=1\n[paths]\nruns="runs"\n', encoding="utf-8")
    verify = trainer_receipts._verify_export

    def mutate(directory, meta):
        result = verify(directory, meta)
        path = export / "manifest.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(trainer_receipts, "_verify_export", mutate)
    assert main(["trainer-status", "--run", str(export), "--config", str(settings), "--json"]) == 1
    assert_export_invalid(json.loads(capsys.readouterr().out))
