"""Exercise recovery against real saved removal operations and fault boundaries."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from filelock import FileLock

from image_dataset_train import caption_restore as recovery
from image_dataset_train.caption_restore_cli import register_commands, run_command
from image_dataset_train.operations import run_directory


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def removed(tmp_path):
    source, home = tmp_path / "images [猫]", tmp_path / "state"
    source.mkdir()
    (source / "nested").mkdir()
    for name in ["one", "nested/two"]:
        (source / f"{name}.png").write_bytes(b"image bytes " + name.encode())
        (source / f"{name}.txt").write_bytes(b"\xef\xbb\xbfmanual caption\r\n" + name.encode())
    (source / "notes.txt").write_bytes(b"unrelated")
    original = snapshot(source)
    result = run_directory("remove", source, home)
    assert result.changed == 2
    return source, home, result.report / "operation.json", original


def test_preview_is_read_only_restore_exact_bytes_and_repeat_is_idempotent(removed):
    source, home, receipt, original = removed
    before = snapshot(home)
    preview = recovery.restore_captions(receipt, dryrun=True)
    assert preview["counts"] == {"ready": 2} and preview["report"] is None
    assert snapshot(home) == before
    result = recovery.restore_captions(receipt.parent)
    assert result["counts"] == {"restored": 2} and snapshot(source) == original
    assert json.loads(Path(result["report"]).read_text(encoding="utf-8"))["status"] == "completed"
    again = recovery.restore_captions(receipt)
    assert again["counts"] == {"already_present": 2} and snapshot(source) == original
    # Removal and backup evidence stays byte-for-byte untouched.
    assert snapshot(receipt.parent) == {
        k.split(receipt.parent.name + "/", 1)[1]: v
        for k, v in before.items()
        if k.startswith("operations/" + receipt.parent.name + "/")
    }


@pytest.mark.parametrize("change", ["caption", "image", "collision", "directory"])
def test_newer_destination_or_image_is_preserved_and_other_rows_continue(removed, change):
    source, _, receipt, original = removed
    if change == "caption":
        (source / "one.txt").write_bytes(b"newer manual caption")
    elif change == "image":
        (source / "one.png").write_bytes(b"new image content")
    elif change == "collision":
        (source / "one.jpg").write_bytes(b"another image with the same stem")
    else:
        (source / "one.txt").mkdir()
    changed = snapshot(source)
    result = recovery.restore_captions(receipt)
    assert result["counts"] == {"restored": 1, "conflict": 1}
    assert result["status"] == "completed_with_conflicts"
    assert (source / "nested/two.txt").read_bytes() == original["nested/two.txt"]
    for name, raw in changed.items():
        assert (source / name).read_bytes() == raw


@pytest.mark.parametrize("tamper", ["backup", "plan", "journal", "backup_root", "source"])
def test_tampered_evidence_is_rejected_before_restoring_any_caption(removed, tamper, tmp_path):
    source, home, receipt, _ = removed
    if tamper == "backup":
        (receipt.parent / "captions/one.txt").write_bytes(b"tampered")
    elif tamper == "plan":
        p = receipt.parent / "plan.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data[0]["caption"] = "../escape.txt"
        p.write_text(json.dumps(data))
    elif tamper == "journal":
        p = receipt.parent / "journal.jsonl"
        p.write_text(p.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    else:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if tamper == "backup_root":
            data["backup"] = str(tmp_path / "unrelated")
        else:
            alternate = tmp_path / "alternate"
            alternate.mkdir()
            (alternate / "one.png").write_bytes((source / "one.png").read_bytes())
            data["source"] = str(alternate)
        receipt.write_text(json.dumps(data))
    before = snapshot(home)
    with pytest.raises(ValueError):
        recovery.restore_captions(receipt)
    assert snapshot(home) == before
    assert not (source / "one.txt").exists() and not (source / "nested/two.txt").exists()


def test_legacy_receipt_without_image_binding_stays_manual(removed):
    source, _, receipt, _ = removed
    metadata = json.loads(receipt.read_text(encoding="utf-8"))
    metadata.pop("plan_sha256")
    metadata.pop("journal_sha256")
    receipt.write_text(json.dumps(metadata))
    path = receipt.parent / "plan.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        row["image_sha256"] = None
    path.write_text(json.dumps(rows))
    path = receipt.parent / "journal.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for event in events:
        event.pop("image_sha256")
        event.pop("source")
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    result = recovery.restore_captions(receipt)
    assert result["counts"] == {"unverifiable": 2}
    assert not (source / "one.txt").exists()


def test_backup_verified_before_crash_is_sufficient_without_removed_event(removed):
    source, _, receipt, original = removed
    metadata = json.loads(receipt.read_text(encoding="utf-8"))
    metadata["journal_sha256"] = None
    metadata["status"] = "running"
    receipt.write_text(json.dumps(metadata))
    journal = receipt.parent / "journal.jsonl"
    events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    journal.write_text(
        "".join(json.dumps(e) + "\n" for e in events if e["event"] == "backup_verified")
        + '{"event":'
    )
    result = recovery.restore_captions(receipt)
    assert result["counts"] == {"restored": 2} and result["warnings"]
    assert snapshot(source) == original


def test_restore_uses_the_original_source_lock(removed):
    source, home, receipt, _ = removed
    key = hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()
    with FileLock(str(home / "locks" / f"{key}.lock")):
        with pytest.raises(RuntimeError, match="Another Trainime"):
            recovery.restore_captions(receipt)
    assert not (source / "one.txt").exists()


def test_raced_destination_is_not_overwritten(removed, monkeypatch):
    source, _, receipt, _ = removed
    publish = recovery._publish

    def race(temporary, target):
        target.write_bytes(b"new race caption")
        publish(temporary, target)

    monkeypatch.setattr(recovery, "_publish", race)
    result = recovery.restore_captions(receipt)
    assert result["counts"] == {"conflict": 2}
    assert (source / "one.txt").read_bytes() == b"new race caption"
    assert not list(source.rglob(".trainime-restore-*"))


def test_interrupt_after_publication_can_be_retried(removed, monkeypatch):
    source, home, receipt, original = removed
    publish = recovery._publish

    def stop(temporary, target):
        publish(temporary, target)
        raise KeyboardInterrupt()

    monkeypatch.setattr(recovery, "_publish", stop)
    with pytest.raises(KeyboardInterrupt):
        recovery.restore_captions(receipt)
    interrupted = next((home / "operations").glob("*-restore-*/restore.json"))
    assert json.loads(interrupted.read_text(encoding="utf-8"))["status"] == "cancelled"
    monkeypatch.setattr(recovery, "_publish", publish)
    result = recovery.restore_captions(receipt)
    assert result["counts"] == {"already_present": 1, "restored": 1}
    assert snapshot(source) == original


def test_backup_links_are_rejected(removed, tmp_path):
    source, _, receipt, _ = removed
    backup = receipt.parent / "captions/one.txt"
    outside = tmp_path / "outside.txt"
    outside.write_bytes(backup.read_bytes())
    backup.unlink()
    try:
        backup.symlink_to(outside)
    except OSError:
        pytest.skip("Creating links requires Windows developer mode or privilege")
    with pytest.raises(ValueError, match="Linked"):
        recovery.restore_captions(receipt)
    assert not (source / "one.txt").exists()


def test_cli_adapter_returns_conflicts_and_does_not_require_config(removed, capsys):
    import argparse

    source, _, receipt, _ = removed
    parser = argparse.ArgumentParser()
    register_commands(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["restore-captions", "--receipt", str(receipt), "--dryrun", "--json"])
    assert run_command(args) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == {"ready": 2}
    (source / "one.txt").write_text("new caption")
    assert run_command(args) == 1


def test_receipt_source_cannot_switch_between_preflight_and_lock(removed, monkeypatch):
    source, _, receipt, _ = removed
    load = recovery._load
    calls = []

    def changed(path, **kwargs):
        data = load(path, **kwargs)
        calls.append(1)
        if len(calls) > 1:
            data["source"] = str(source / "other")
        return data

    monkeypatch.setattr(recovery, "_load", changed)
    with pytest.raises(ValueError, match="before acquiring"):
        recovery.restore_captions(receipt)
    assert not (source / "one.txt").exists()


def test_unsafe_plan_path_is_rejected_even_without_optional_hashes(removed):
    _, _, receipt, _ = removed
    metadata = json.loads(receipt.read_text(encoding="utf-8"))
    metadata.pop("plan_sha256")
    receipt.write_text(json.dumps(metadata))
    path = receipt.parent / "plan.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["caption"] = "../escape.txt"
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="Unsafe relative"):
        recovery.restore_captions(receipt)


@pytest.mark.parametrize("dryrun", [True, False])
def test_selected_receipt_checksum_rejects_changes_without_writes(removed, dryrun):
    source, home, receipt, _ = removed
    selected = hashlib.sha256(receipt.read_bytes()).hexdigest()
    receipt.write_bytes(receipt.read_bytes() + b"\n")
    before_source, before_home = snapshot(source), snapshot(home)
    with pytest.raises(ValueError, match="Selected removal receipt changed"):
        recovery.restore_captions(receipt, dryrun=dryrun, expected_sha256=selected)
    assert snapshot(source) == before_source and snapshot(home) == before_home


def test_selected_receipt_rechecked_inside_source_lock(removed, monkeypatch):
    source, _, receipt, _ = removed
    selected = hashlib.sha256(receipt.read_bytes()).hexdigest()
    load = recovery._load
    calls = []

    def changed(path, **kwargs):
        data = load(path, **kwargs)
        calls.append(1)
        if len(calls) == 1:
            receipt.write_bytes(receipt.read_bytes() + b"\n")
        return data

    monkeypatch.setattr(recovery, "_load", changed)
    with pytest.raises(ValueError, match="Selected removal receipt changed"):
        recovery.restore_captions(receipt, expected_sha256=selected)
    assert not (source / "one.txt").exists()
    assert not list(receipt.parent.parent.glob("*-restore-*/restore.json"))


def test_selected_receipt_checksum_accepts_preview_and_restoration(removed):
    source, _, receipt, original = removed
    selected = hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert recovery.restore_captions(receipt, dryrun=True, expected_sha256=selected)["counts"] == {
        "ready": 2
    }
    assert recovery.restore_captions(receipt, expected_sha256=selected)["counts"] == {"restored": 2}
    assert snapshot(source) == original


@pytest.mark.parametrize("value", ["", "a" * 63, "A" * 64, "not-a-checksum"])
def test_invalid_expected_receipt_checksum_rejected_before_reading(tmp_path, value):
    with pytest.raises(ValueError, match="full lowercase SHA256"):
        recovery.restore_captions(tmp_path / "not-created", expected_sha256=value)
    assert not list(tmp_path.iterdir())


def test_stale_selected_preview_cli_does_not_create_error_logs(removed, monkeypatch, capsys):
    from image_dataset_train.cli import main

    source, home, receipt, _ = removed
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    source_before, home_before = snapshot(source), snapshot(home)
    assert (
        main(
            [
                "restore-captions",
                "--receipt",
                str(receipt),
                "--expected-sha256",
                "0" * 64,
                "--dryrun",
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["error"]["type"] == "ValueError"
    assert snapshot(source) == source_before and snapshot(home) == home_before


@pytest.mark.parametrize("dryrun", [True, False])
def test_legacy_plan_change_rejects_selected_guard_without_writes(removed, dryrun):
    source, home, receipt, _ = removed
    metadata = json.loads(receipt.read_bytes())
    metadata.pop("plan_sha256")
    receipt.write_text(json.dumps(metadata), encoding="utf-8")
    plan = receipt.with_name("plan.json")
    expected = hashlib.sha256(plan.read_bytes()).hexdigest()
    plan.write_bytes(plan.read_bytes() + b"\n")
    source_before, home_before = snapshot(source), snapshot(home)
    with pytest.raises(ValueError, match="Selected removal plan changed"):
        recovery.restore_captions(
            receipt,
            dryrun=dryrun,
            expected_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
            expected_plan_sha256=expected,
        )
    assert snapshot(source) == source_before and snapshot(home) == home_before


@pytest.mark.parametrize("malformed", ["source", "journal"])
def test_malformed_preview_cli_is_nonmutating(removed, monkeypatch, capsys, malformed):
    from image_dataset_train.cli import main

    source, home, receipt, _ = removed
    data = json.loads(receipt.read_bytes())
    if malformed == "source":
        data["source"] = {"not": "a path"}
    else:
        data.pop("journal_sha256")
        journal = receipt.with_name("journal.jsonl")
        rows = [json.loads(line) for line in journal.read_text().splitlines()]
        rows[0]["image"] = []
        journal.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    receipt.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    source_before, home_before = snapshot(source), snapshot(home)
    assert main(["restore-captions", "--receipt", str(receipt), "--dryrun", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["type"] == "ValueError"
    assert snapshot(source) == source_before and snapshot(home) == home_before
