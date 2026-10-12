from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from filelock import FileLock
from PIL import Image
from test_trainime import ScriptedTerminal, local_model, picture, snapshot

from image_dataset_train import collision_fix, doctor, operations
from image_dataset_train.diagnostics import diagnose
from image_dataset_train.operations import run_directory
from image_dataset_train.preferences import Preferences
from image_dataset_train.trainime import App, main


def collision(tmp_path, stem="arbitrary_42", caption=True):
    source, home = tmp_path / "images with spaces", tmp_path / "app"
    picture(source / f"{stem}.jpg", "white")
    picture(source / f"{stem}.png", "gray")
    if caption:
        (source / f"{stem}.txt").write_bytes(b"ambiguous manual caption\r\n")
    return source, home


@pytest.mark.parametrize("stem", ["arbitrary_42", "画像 [set]", "artist's $work", "x-jpg"])
def test_general_tf001_preserves_bytes_resolves_stems_and_is_idempotent(tmp_path, stem):
    source, home = collision(tmp_path, stem)
    picture(source / "other" / f"{stem}.jpg")
    picture(source / "other" / f"{stem}.webp")
    (source / "notes.txt").write_text("unrelated")
    picture(source / "already-tagged.png")
    (source / "already-tagged.txt").write_bytes(b"keep manual")
    before = snapshot(source)
    result = run_directory("fix", source, home)
    assert result.exit_code == 0 and result.repairs.runs[0].metrics["images renamed"] == 4
    assert result.repairs.runs[0].metrics["captions preserved"] == 1
    assert not (source / f"{stem}.txt").exists()
    report = result.repairs.reports[0]
    assert (report / "captions" / f"{stem}.txt").read_bytes() == b"ambiguous manual caption\r\n"
    plan = json.loads((report / "fix.json").read_text(encoding="utf-8"))
    assert plan["status"] == "completed" and plan["error_code"] == "te001"
    for group in plan["groups"]:
        for action in group["actions"]:
            assert action["done"] and action["sha256"] == before[action["source"]]
            if action["kind"] == "image":
                assert snapshot(source)[action["target"]] == before[action["source"]]
    assert (source / "already-tagged.txt").read_bytes() == b"keep manual"
    assert (source / "notes.txt").read_text() == "unrelated"
    after = snapshot(source)
    repeated = run_directory("fix", source, home)
    assert repeated.exit_code == 0 and not repeated.repairs.actions
    assert snapshot(source) == after


def test_te001_logs_and_output_identify_the_executable_fix(tmp_path, monkeypatch, capsys):
    source, home = collision(tmp_path)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    before = snapshot(source)
    assert main(["tag", str(source)]) == 1
    output = capsys.readouterr().out
    assert "[te001]" in output and "[tf001] Apply:" in output and "--fix tf001" in output
    assert "Give each image a unique filename stem" not in output
    assert snapshot(source) == before
    plan = json.loads(next((home / "operations").glob("*/plan.json")).read_text())
    assert all(i["error_code"] == "te001" and i["fix_code"] == "tf001" for i in plan)
    rows = [
        json.loads(line)
        for p in (home / "logs").glob("*.errors.jsonl")
        for line in p.read_text().splitlines()
    ]
    assert rows and all(row["error_code"] == "te001" and row["fix_code"] == "tf001" for row in rows)
    assert diagnose("Same-stem collision").fix_code == "tf001"


@pytest.mark.parametrize("action", ["fix", "tag", "remove"])
def test_fix_dryrun_has_no_writes_or_downloads(tmp_path, monkeypatch, action):
    source, home = collision(tmp_path)
    before = snapshot(source)
    monkeypatch.setattr(operations, "fetch_bundle", lambda *a, **kw: pytest.fail("download"))
    result = run_directory(action, source, home, dryrun=True, fix="tf001")
    assert len(result.repairs.actions) == 3
    assert result.repairs.runs[0].metrics == {"images renamed": 0, "captions preserved": 0}
    assert result.exit_code == 0
    assert snapshot(source) == before and not home.exists()


@pytest.mark.parametrize("flag", [[], ["tf001"], ["te001"]])
def test_tag_fix_repairs_then_generates_independent_captions(tmp_path, monkeypatch, flag):
    source, home = collision(tmp_path)
    local_model(home)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main(["tag", str(source), "--fix", *flag]) == 0
    assert sorted(p.name for p in source.glob("*.txt")) == [
        "arbitrary_42-jpg.txt",
        "arbitrary_42-png.txt",
    ]
    assert all("ambiguous manual" not in p.read_text() for p in source.glob("*.txt"))
    assert main(["tag", str(source), "--fix", *flag]) == 0


def test_occupied_destinations_casefold_and_subfolders(tmp_path):
    source, home = collision(tmp_path, "PICTURE")
    picture(source / "picture-jpg.PNG")
    (source / "picture-jpg-2.txt").write_text("reserve this stem")
    (source / "PICTURE-png").mkdir()
    before = snapshot(source)
    result = run_directory("fix", source, home)
    assert result.exit_code == 0
    assert (source / "PICTURE-jpg-3.jpg").is_file()
    assert (source / "PICTURE-png-2.png").is_file()
    assert snapshot(source)["picture-jpg.PNG"] == before["picture-jpg.PNG"]
    assert (source / "picture-jpg-2.txt").read_text() == "reserve this stem"


def test_case_variant_image_collision(tmp_path):
    source, home = collision(tmp_path, "CaSe", caption=False)
    (source / "CaSe.png").rename(source / "case.PNG")
    result = run_directory("fix", source, home)
    assert result.exit_code == 0 and result.repairs.runs[0].metrics["images renamed"] == 2
    assert (source / "CaSe-jpg.jpg").exists() and (source / "case-png.PNG").exists()


@pytest.mark.skipif(
    os.name == "nt", reason="Standard Windows directories cannot hold case-only captions"
)
def test_multiple_case_variant_captions_are_all_preserved(tmp_path):
    source, home = tmp_path / "images", tmp_path / "app"
    picture(source / "a.png")
    (source / "a.txt").write_bytes(b"first")
    (source / "A.TXT").write_bytes(b"second")
    result = run_directory("fix", source, home)
    assert result.exit_code == 0 and result.repairs.runs[0].metrics["captions preserved"] == 2
    recovery = result.repairs.reports[0] / "captions"
    assert (recovery / "a.txt").read_bytes() == b"first"
    assert (recovery / "A.TXT").read_bytes() == b"second"
    assert (source / "a-png.png").exists()


@pytest.mark.parametrize("after", ["0 images renamed; 1", "1 images renamed"])
def test_cancel_and_resume_finishes_the_saved_group(tmp_path, after):
    source, home = collision(tmp_path)

    def cancel(message):
        if after in message:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_directory("fix", source, home, progress=cancel)
    assert (
        run_directory("tag", source, home).exit_code == 1
    )  # Must finish partial association repair.
    completed = run_directory("fix", source, home)
    assert completed.exit_code == 0
    assert (source / "arbitrary_42-jpg.jpg").is_file()
    assert (source / "arbitrary_42-png.png").is_file()
    assert not (source / "arbitrary_42.txt").exists()
    assert not collision_fix.pending_repairs(source, home)


def test_partial_backup_is_kept_and_retry_creates_verified_backup(tmp_path, monkeypatch):
    source, home = collision(tmp_path)
    original_copy = collision_fix.shutil.copyfileobj

    def incomplete(incoming, outgoing, *args):
        outgoing.write(b"partial")
        raise OSError("fixture interrupted copy")

    monkeypatch.setattr(collision_fix.shutil, "copyfileobj", incomplete)
    first = run_directory("fix", source, home)
    assert first.exit_code == 1 and (source / "arbitrary_42.txt").exists()
    monkeypatch.setattr(collision_fix.shutil, "copyfileobj", original_copy)
    second = run_directory("fix", source, home)
    assert second.exit_code == 0
    backup = first.repairs.reports[0] / "captions"
    assert (backup / "arbitrary_42.txt").read_bytes() == b"ambiguous manual caption\r\n"
    assert next(backup.glob("*.previous-*")).read_bytes() == b"partial"


def test_raced_destination_is_never_overwritten_and_retry_reallocates(tmp_path, monkeypatch):
    source, home = collision(tmp_path, caption=False)
    original_rename = Path.rename
    original_link = os.link
    raced = []

    def race(original, target, **kwargs):
        if original.suffix == ".jpg" and not raced:
            target = Path(target)
            target.write_bytes(b"concurrent file")
            raced.append(target)
        return (
            original_rename(original, target)
            if os.name == "nt"
            else original_link(original, target, **kwargs)
        )

    if os.name == "nt":
        monkeypatch.setattr(Path, "rename", race)
    else:
        monkeypatch.setattr(os, "link", race)
    first = run_directory("fix", source, home)
    assert first.exit_code == 1 and (source / "arbitrary_42.jpg").exists()
    assert raced[0].read_bytes() == b"concurrent file"
    second = run_directory("fix", source, home)
    assert second.exit_code == 0 and raced[0].read_bytes() == b"concurrent file"
    assert (source / "arbitrary_42-jpg-2.jpg").exists()


def test_retry_refreshes_changed_remaining_files_without_losing_old_caption(tmp_path):
    source, home = collision(tmp_path)

    def cancel(message):
        if "0 images renamed; 1" in message:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_directory("fix", source, home, progress=cancel)
    picture(source / "arbitrary_42.jpg", "blue")
    edited = (source / "arbitrary_42.jpg").read_bytes()
    (source / "arbitrary_42.txt").write_bytes(b"new ambiguous caption")
    result = run_directory("fix", source, home)
    assert result.exit_code == 0
    assert (source / "arbitrary_42-jpg.jpg").read_bytes() == edited
    backup = result.repairs.reports[0] / "captions"
    assert (backup / "arbitrary_42.txt").read_bytes() == b"new ambiguous caption"
    assert next(backup.glob("*.previous-*")).read_bytes() == b"ambiguous manual caption\r\n"


def test_tf001_shares_tag_remove_lock_and_does_not_decode(tmp_path, monkeypatch):
    source, home = collision(tmp_path)
    monkeypatch.setattr(Image, "open", lambda *a, **kw: pytest.fail("image decoding"))
    (home / "locks").mkdir(parents=True)
    key = hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()
    with FileLock(str(home / "locks" / f"{key}.lock")):
        with pytest.raises(RuntimeError, match="Another Trainime"):
            run_directory("fix", source, home)
    assert run_directory("fix", source, home).exit_code == 0


def test_doctor_targeted_fix_and_preview_do_not_require_model(tmp_path, monkeypatch, capsys):
    source, home = collision(tmp_path)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    monkeypatch.setattr(doctor, "repair_model", lambda *a, **kw: pytest.fail("model download"))
    before = snapshot(source)
    args = ["doctor", "--path", str(source), "--fix", "tf001", "--json"]
    assert doctor.main([*args, "--dryrun"]) == 0
    assert "[tf001]" in capsys.readouterr().out
    assert snapshot(source) == before and not home.exists()
    assert doctor.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"][0]["status"] == "fixed"
    assert "Directory rechecked: no association issues" in result["checks"][0]["detail"]


def test_interactive_fix_option_only_after_collision_and_retains_home_menu(tmp_path):
    source, home = collision(tmp_path)
    local_model(home)
    terminal = ScriptedTerminal(["1", str(source), "", "--fix", "q"])
    assert App(Preferences(home), terminal).run() == 0
    assert terminal.prompts == [
        "> ",
        "Path: ",
        "Preview only? --dryrun [y/N]: ",
        "Apply tf001? --fix [y/N]: ",
        "> ",
    ]
    assert "[te001]" in terminal.output.getvalue()
    assert (source / "arbitrary_42-jpg.txt").exists()


def test_image_or_caption_directory_is_not_moved_as_a_file(tmp_path):
    source, home = collision(tmp_path, caption=False)
    (source / "arbitrary_42.txt").mkdir()
    before = snapshot(source)
    result = run_directory("fix", source, home)
    assert result.exit_code == 0 and result.repairs.runs[0].metrics["images renamed"] == 2
    assert sorted(snapshot(source).values()) == sorted(before.values())
    assert (source / "arbitrary_42.txt").is_dir()


def test_dryrun_apply_command_keeps_fix_flag(tmp_path, monkeypatch, capsys):
    source, home = collision(tmp_path)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main(["tag", str(source), "--fix", "--dryrun"]) == 0
    text = capsys.readouterr().out
    assert "2 images" in text
    apply_command = text.split("Run to apply")[-1]
    assert "--fix" in apply_command and "--dryrun" not in apply_command


def test_resume_handles_rename_before_journal_update(tmp_path, monkeypatch):
    source, home = collision(tmp_path, caption=False)
    persist = collision_fix.atomic_json

    def crash_after_move(path, value):
        if (source / "arbitrary_42-jpg.jpg").exists():
            raise SystemExit("fixture process exit before journal update")
        persist(path, value)

    monkeypatch.setattr(collision_fix, "atomic_json", crash_after_move)
    with pytest.raises(SystemExit):
        run_directory("fix", source, home)
    monkeypatch.setattr(collision_fix, "atomic_json", persist)
    result = run_directory("fix", source, home)
    assert result.exit_code == 0
    assert (source / "arbitrary_42-jpg.jpg").exists()
    assert (source / "arbitrary_42-png.png").exists()
    assert not collision_fix.pending_repairs(source, home)


def test_long_names_leave_room_for_unique_suffix(tmp_path):
    source, home = collision(tmp_path, "a" * 151, caption=False)
    result = run_directory("fix", source, home)
    assert result.exit_code == 0 and result.repairs.runs[0].metrics["images renamed"] == 2
    assert len({p.stem.casefold() for p in source.iterdir()}) == 2
    assert all(len(p.name.encode()) < 200 for p in source.iterdir())


def test_repair_caption_backup_cannot_follow_junction_outside_home(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction regression")
    import subprocess

    source, home = collision(tmp_path)

    def cancel(message):
        if "0 images renamed; 1" in message:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_directory("fix", source, home, progress=cancel)
    report, _ = collision_fix.pending_repairs(source, home)[0]
    saved = report / "captions.saved"
    (report / "captions").rename(saved)
    outside = tmp_path / "outside"
    outside.mkdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(report / "captions"), str(outside)],
        check=True,
        capture_output=True,
    )
    (source / "arbitrary_42.txt").write_bytes(b"new caption")
    result = run_directory("fix", source, home)
    assert result.exit_code == 1 and not list(outside.iterdir())
    assert (source / "arbitrary_42.txt").read_bytes() == b"new caption"


def test_planning_failure_has_error_codes_and_an_actual_log(tmp_path, monkeypatch):
    source, home = collision(tmp_path)

    def denied(*args):
        raise PermissionError("fixture locked file")

    monkeypatch.setattr(collision_fix, "_digest", denied)
    result = run_directory("fix", source, home)
    assert result.exit_code == 1 and result.log.is_file()
    record = json.loads(result.log.read_text(encoding="utf-8"))
    assert record["error_code"] == "te001" and record["fix_code"] == "tf001"
    assert record["event"] == "fix_planning_failed" and record["level"] == "error"
