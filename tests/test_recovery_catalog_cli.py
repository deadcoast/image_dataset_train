"""Recovery navigation keeps receipt selection and suggested operations explicit."""

from __future__ import annotations

import json
import shlex

import pytest

from image_dataset_train.operations import run_directory
from image_dataset_train.recovery_catalog_cli import browse_command, main


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def output(capsys):
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def removed(tmp_path):
    source = tmp_path / "Artist's 日本語 [images]"
    home = tmp_path / "Artist's 日本語 saved state"
    source.mkdir()
    (source / "one.png").write_bytes(b"original image bytes")
    (source / "one.txt").write_bytes(b"\xef\xbb\xbforiginal caption\r\n")
    original = snapshot(source)
    result = run_directory("remove", source, home)
    assert result.changed == 1
    return source, home, result.report / "operation.json", original


def selected(home, capsys):
    assert main(["--home", str(home), "--kind", "removal", "--json"]) == 0
    records = output(capsys)["records"]
    assert len(records) == 1
    return records[0]


def test_empty_and_invalid_read_only_navigation_create_no_application_state(
    tmp_path, monkeypatch, capsys
):
    home = tmp_path / "missing state"
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    before = snapshot(tmp_path)
    assert main([]) == 0
    assert "No saved recovery receipts" in capsys.readouterr().out
    assert main(["show", "not-a-record", "--json"]) == 2
    assert output(capsys)["status"] == "failed"
    assert snapshot(tmp_path) == before and not home.exists()


@pytest.mark.parametrize("placement", ["before", "after"])
def test_show_preserves_home_json_options_and_all_saved_bytes(removed, capsys, placement):
    source, home, receipt, _ = removed
    record = selected(home, capsys)
    before = snapshot(home), snapshot(source)
    common = ["--home", str(home), "--json"]
    action = ["show", record["id"], "--expected-sha256", record["receipt_sha256"]]
    assert main(common + action if placement == "before" else action + common) == 0
    shown = output(capsys)
    assert shown["receipt"] == str(receipt)
    assert shown["commands"][0]["argv"][-1] == "--dryrun"
    assert (snapshot(home), snapshot(source)) == before


def test_generated_removal_commands_preview_and_restore_exact_saved_caption(
    removed, monkeypatch, capsys
):
    from image_dataset_train.cli import main as dataset_main

    source, home, receipt, original = removed
    record = selected(home, capsys)
    assert main(record["show_command"]["argv"][2:] + ["--json"]) == 0
    shown = output(capsys)
    preview, apply = shown["commands"]
    assert preview["environment"] == apply["environment"] == {"TRAINIME_HOME": str(home)}
    assert "--expected-sha256" in preview["argv"]
    assert "--expected-plan-sha256" in preview["argv"]
    assert "Artist''s" in preview["powershell"] and "日本語" in preview["powershell"]
    assert shlex.split(preview["posix"])[1:] == preview["argv"]
    for key, value in preview["environment"].items():
        monkeypatch.setenv(key, value)
    before = snapshot(home), snapshot(source)
    assert dataset_main(preview["argv"][1:] + ["--json"]) == 0
    assert output(capsys)["counts"] == {"ready": 1}
    assert (snapshot(home), snapshot(source)) == before
    assert dataset_main(apply["argv"][1:] + ["--json"]) == 0
    assert output(capsys)["counts"] == {"restored": 1}
    assert snapshot(source) == original
    assert receipt.read_bytes() == before[0][receipt.relative_to(home).as_posix()]
    assert main(["--home", str(home), "--kind", "restore", "--json"]) == 0
    restored = output(capsys)["records"]
    assert len(restored) == 1
    assert main(["show", restored[0]["id"], "--home", str(home), "--json"]) == 0
    restore_record = output(capsys)
    assert restore_record["commands"] == []
    assert restore_record["original_receipt"] == str(receipt)


def test_filtered_listing_and_show_work_without_source_images(removed, capsys):
    source, home, _, _ = removed
    record = selected(home, capsys)
    source.rename(source.with_name("offline"))
    before = snapshot(home)
    assert main(["--home", str(home), "--source", str(source), "--json"]) == 0
    result = output(capsys)
    assert result["source_revalidated"] is False
    assert [r["id"] for r in result["records"]] == [record["id"]]
    assert main(["show", record["id"], "--home", str(home)]) == 0
    rendered = capsys.readouterr().out
    assert "Saved metadata only" in rendered and "Preview caption restoration" in rendered
    assert snapshot(home) == before


def test_posix_terminal_uses_posix_commands_and_preserves_both_json_forms(
    removed, monkeypatch, capsys
):
    import image_dataset_train.recovery_catalog_cli as command_cli

    _, home, _, _ = removed
    record = selected(home, capsys)
    monkeypatch.setattr(command_cli, "_shell", lambda: "posix")
    assert main(["--home", str(home)]) == 0
    listed = capsys.readouterr().out
    assert record["show_command"]["posix"] in listed
    assert "& 'dataset'" not in listed
    assert main(["show", record["id"], "--home", str(home), "--json"]) == 0
    shown = output(capsys)
    assert main(["show", record["id"], "--home", str(home)]) == 0
    rendered = capsys.readouterr().out
    for command in shown["commands"]:
        assert command["posix"] in rendered
        assert "$env:TRAINIME_HOME" in command["powershell"]
    assert "$env:TRAINIME_HOME" not in rendered
    assert "& 'dataset'" not in rendered


@pytest.mark.parametrize("selection", ["short_id", "checksum", "changed_receipt"])
def test_invalid_or_stale_selection_rejects_without_logging(removed, capsys, selection):
    source, home, receipt, _ = removed
    record = selected(home, capsys)
    chosen, checksum = record["id"], record["receipt_sha256"]
    if selection == "short_id":
        chosen = chosen[:12]
    elif selection == "checksum":
        checksum = "0" * 64
    else:
        receipt.write_bytes(receipt.read_bytes() + b"\n")
    before = snapshot(home), snapshot(source)
    assert main(["show", chosen, "--home", str(home), "--expected-sha256", checksum, "--json"]) == 2
    assert output(capsys)["status"] == "failed"
    assert (snapshot(home), snapshot(source)) == before


@pytest.mark.parametrize(
    "flag,value", [("--source", "missing"), ("--kind", "removal"), ("--status", "completed")]
)
def test_list_filters_cannot_be_silently_ignored_by_show(removed, capsys, flag, value):
    _, home, _, _ = removed
    record = selected(home, capsys)
    before = snapshot(home)
    assert main(["--home", str(home), flag, value, "show", record["id"], "--json"]) == 2
    assert "filter the list" in output(capsys)["error"]["message"]
    assert snapshot(home) == before


def test_browse_command_retains_alternate_home_and_exact_unicode_source(tmp_path):
    home, source = tmp_path / "state ' 日本語", tmp_path / "source [1]"
    command = browse_command(home, source)
    assert command["argv"] == ["dataset", "recovery", "--home", str(home), "--source", str(source)]
    assert command["environment"] == {}
    assert shlex.split(command["posix"]) == command["argv"]
    assert "''" in command["powershell"] and "日本語" in command["powershell"]


def test_unsupported_or_interrupted_reader_returns_locally_without_logging(
    tmp_path, monkeypatch, capsys
):
    import image_dataset_train.recovery_catalog as backend

    home = tmp_path / "home"
    before = snapshot(tmp_path)
    for error, code, state in [
        (OSError("unavailable"), 2, "failed"),
        (KeyboardInterrupt(), 130, "cancelled"),
    ]:

        def fail(*args, failure=error, **kwargs):
            raise failure

        monkeypatch.setattr(backend, "list_recovery", fail)
        assert main(["--home", str(home), "--json"]) == code
        assert output(capsys)["status"] == state
        assert snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["collision", "package"])
def test_nonremoval_commands_preserve_operation_scope_and_do_not_execute(
    tmp_path, monkeypatch, capsys, kind
):
    import image_dataset_train.recovery_catalog as backend

    home = tmp_path / "private home"
    record = {
        "id": "a" * 64,
        "receipt_sha256": "b" * 64,
        "receipt": str(home / "receipt.json"),
        "kind": kind,
        "status": "failed",
        "home": str(home),
        "source": str(tmp_path / "images"),
        "affected_count": 1,
        "items": [{"path": "one.png", "recorded_status": "pending"}],
        "recovery_locations": [],
        "warnings": [],
    }
    monkeypatch.setattr(backend, "select_recovery", lambda *a, **k: record)
    before = snapshot(tmp_path)
    assert main(["show", record["id"], "--home", str(home), "--json"]) == 0
    shown = output(capsys)
    assert len(shown["commands"]) == 1
    command = shown["commands"][0]
    assert command["environment"] == {"TRAINIME_HOME": str(home)}
    if kind == "collision":
        assert command["argv"] == ["trainime", "fix", record["source"], "--fix", "1", "--dryrun"]
        assert "all pending" in command["scope"] and "not only this receipt" in command["scope"]
    else:
        assert command["argv"] == ["trainime", "doctor", "--dryrun"]
        assert "current installation" in command["scope"]
        assert "historical wheel" in command["scope"]
    assert snapshot(tmp_path) == before


def test_terminal_escapes_untrusted_control_characters(monkeypatch, capsys):
    import image_dataset_train.recovery_catalog as backend

    record = {
        "id": "a" * 64,
        "receipt_sha256": "b" * 64,
        "receipt": "receipt\x1b[2J.json",
        "kind": "removal",
        "status": "failed",
        "home": "state\rhome",
        "source": "image\tsource",
        "affected_count": 1,
        "items": [{"path": "caption\x07.txt"}],
        "recovery_locations": ["saved\x9bbytes"],
        "warnings": ["pending\x1b[0m"],
        "metadata_inputs": {"plan.json": "c" * 64},
    }
    monkeypatch.setattr(backend, "select_recovery", lambda *a, **k: record)
    assert main(["show", record["id"]]) == 0
    text = capsys.readouterr().out
    assert all(character not in text for character in ["\x1b", "\x07", "\x9b", "\r", "\t"])
    assert "\\x1b" in text and "\\x07" in text
