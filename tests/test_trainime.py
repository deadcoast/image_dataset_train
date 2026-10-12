from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pytest
from filelock import FileLock
from PIL import Image
from rich.console import Console
from test_tagging import make_bundle

from image_dataset_train import operations
from image_dataset_train.inventory import file_sha256
from image_dataset_train.model_bundle import Label, bundle_path
from image_dataset_train.operations import Item, Result, run_directory
from image_dataset_train.preferences import Preferences, app_home, image_directory
from image_dataset_train.trainime import HOME_MENU, App, Terminal, command_text, main


def picture(path: Path, color: str = "white") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 40), color).save(path)
    return path


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): file_sha256(p) for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def collection(tmp_path: Path) -> tuple[Path, Path]:
    source, home = tmp_path / "画像 [test]", tmp_path / "app"
    picture(source / "first.png")
    picture(source / "sub" / "second.png", "gray")
    return source, home


def local_model(home: Path) -> None:
    make_bundle(
        bundle_path(home / "models", "swinv2-v3"),
        [Label(0, "general", 9), Label(1, "blue_hair", 0), Label(2, "solo", 0)],
    )


@pytest.mark.parametrize("action", ["tag", "remove"])
def test_dryrun_is_read_only_and_offline(collection, monkeypatch, action):
    source, home = collection
    (source / "first.txt").write_text("manual\n", encoding="utf-8")
    before = snapshot(source)
    monkeypatch.setattr(operations, "fetch_bundle", lambda *a, **kw: pytest.fail("download"))
    result = run_directory(action, source, home, dryrun=True)
    assert result.counts["ready"] == 1
    assert result.changed == 0 and result.report is None
    assert not home.exists()
    assert snapshot(source) == before


def test_tag_writes_missing_captions_and_reuses_scores(collection, monkeypatch):
    source, home = collection
    local_model(home)
    (source / "first.txt").write_bytes(b"manual\r\n")
    original = snapshot(source)
    first = run_directory("tag", source, home)
    caption = source / "sub" / "second.txt"
    assert first.changed == 1 and first.counts["existing"] == 1
    assert caption.read_text(encoding="utf-8").strip() == "solo, blue hair"
    assert all(file_sha256(source / p) == digest for p, digest in original.items())
    metadata = json.loads((first.report / "tagging.json").read_text(encoding="utf-8"))
    summary = json.loads((Path(metadata["tagging"]) / "summary.json").read_text())
    assert summary["inferred_images"] == 1  # Manual caption's image never reaches inference.
    run_directory("remove", source, home)
    # Both images can now be tagged; one should reuse the persisted score vector.
    second = run_directory("tag", source, home)
    metadata = json.loads((second.report / "tagging.json").read_text(encoding="utf-8"))
    summary = json.loads((Path(metadata["tagging"]) / "summary.json").read_text())
    assert second.changed == 2 and summary["cached_images"] == 1
    assert summary["inferred_images"] == 1
    monkeypatch.setattr(operations, "fetch_bundle", lambda *a, **kw: pytest.fail("model setup"))
    third = run_directory("tag", source, home)
    assert third.changed == 0 and third.counts["existing"] == 2


def test_remove_is_recoverable_and_leaves_unrelated_files(collection):
    source, home = collection
    (source / "first.TXT").write_bytes(b"manual\r\n")
    (source / "sub" / "second.txt").write_bytes("タグ\n".encode())
    (source / "notes.txt").write_text("not a caption")
    before = snapshot(source)
    result = run_directory("remove", source, home)
    assert result.changed == 2 and result.exit_code == 0
    assert snapshot(result.backup) == {p: before[p] for p in ("first.TXT", "sub/second.txt")}
    assert snapshot(source) == {
        p: digest for p, digest in before.items() if p not in ("first.TXT", "sub/second.txt")
    }
    events = [
        json.loads(line)["event"]
        for line in (result.report / "journal.jsonl").read_text().splitlines()
    ]
    assert events == ["backup_verified", "removed", "backup_verified", "removed"]
    assert run_directory("remove", source, home).changed == 0


@pytest.mark.parametrize("action", ["tag", "remove"])
def test_collisions_and_caption_directories_are_blocked(collection, action):
    source, home = collection
    picture(source / "first.jpg")
    (source / "first.txt").write_text("shared")
    (source / "sub" / "second.txt").mkdir()
    before = snapshot(source)
    result = run_directory(action, source, home)
    assert result.changed == 0 and result.counts["blocked"] == 3
    assert result.exit_code == 1
    assert result.report is not None
    assert len(json.loads((result.report / "plan.json").read_text(encoding="utf-8"))) == 3
    assert snapshot(source) == before


def test_remove_does_not_decode_images(collection, monkeypatch):
    source, home = collection
    (source / "first.png").write_bytes(b"broken")
    (source / "first.txt").write_text("caption")
    monkeypatch.setattr(Image, "open", lambda *a, **kw: pytest.fail("image decode"))
    assert run_directory("remove", source, home).changed == 1


@pytest.mark.parametrize("action", ["tag", "remove"])
def test_source_state_overlap_fails_before_writes(collection, action):
    source, home = collection
    before = snapshot(source)
    with pytest.raises(ValueError, match="separate"):
        run_directory(action, source, source / "app")
    assert snapshot(source) == before and not home.exists()


def test_concurrent_directory_job_is_rejected(collection):
    source, home = collection
    locks = home / "locks"
    locks.mkdir(parents=True)
    key = hashlib.sha256(os.path.normcase(str(source.resolve())).encode()).hexdigest()
    with FileLock(str(locks / f"{key}.lock")):
        with pytest.raises(RuntimeError, match="Another Trainime operation"):
            run_directory("remove", source, home)


def test_tag_rechecks_image_and_keeps_new_caption(collection, monkeypatch):
    source, home = collection
    local_model(home)
    original = operations._create_caption

    def race(source, item, text, result):
        if item.image == "first.png":
            picture(source / item.image, "black")
        else:
            (source / item.caption).write_text("concurrent manual caption")
        return original(source, item, text, result)

    monkeypatch.setattr(operations, "_create_caption", race)
    result = run_directory("tag", source, home)
    assert result.changed == 0 and len(result.errors) == 2
    assert not (source / "first.txt").exists()
    assert (source / "sub" / "second.txt").read_text() == "concurrent manual caption"


def test_remove_rechecks_changed_caption(collection, monkeypatch):
    source, home = collection
    (source / "first.txt").write_text("before")
    original = operations._remove_caption

    def race(source, item, result):
        (source / item.caption).write_text("after")
        return original(source, item, result)

    monkeypatch.setattr(operations, "_remove_caption", race)
    result = run_directory("remove", source, home)
    assert result.changed == 0 and len(result.errors) == 1
    assert (source / "first.txt").read_text() == "after"


def test_remove_backup_failure_keeps_original(collection, monkeypatch):
    source, home = collection
    (source / "first.txt").write_text("keep")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(operations.shutil, "copyfileobj", fail)
    result = run_directory("remove", source, home)
    assert result.changed == 0 and "disk full" in result.errors[0]
    assert (source / "first.txt").read_text() == "keep"


def test_cancel_mid_remove_leaves_a_report_and_releases_lock(collection):
    source, home = collection
    (source / "first.txt").write_text("first")
    (source / "sub" / "second.txt").write_text("second")

    def stop(message):
        if message == "Removing captions: 1/2":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_directory("remove", source, home, progress=stop)
    report = next((home / "operations").glob("*/operation.json"))
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "cancelled" and result["changed"] == 1
    assert (Path(result["backup"]) / "first.txt").read_text() == "first"
    assert run_directory("remove", source, home).changed == 1


def test_tag_empty_caption_is_not_published(collection):
    source, home = collection
    local_model(home)
    picture(source / "first.png", "black")
    picture(source / "sub" / "second.png", "black")
    # White padding raises the mean; use square black fixtures for all-zero scores.
    for path in source.rglob("*.png"):
        Image.new("RGB", (20, 20), "black").save(path)
    result = run_directory("tag", source, home)
    assert result.changed == 0 and len(result.errors) == 2
    assert not list(source.rglob("*.txt"))


def test_preferences_session_never_persists(collection):
    source, home = collection
    preferences = Preferences.load(home)
    assert not home.exists()
    preferences.save_default(source)
    preferences.session_path = source / "sub"
    assert preferences.selected_path == source / "sub"
    reloaded = Preferences.load(home)
    assert reloaded.selected_path == source and reloaded.session_path is None
    assert "session_path" not in json.loads(preferences.settings_file.read_text(encoding="utf-8"))
    preferences.save_default(None)
    assert Preferences.load(home).default_path is None


def test_path_normalization_and_environment(collection, monkeypatch):
    source, home = collection
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert app_home() == home.resolve()
    assert image_directory(' "' + str(source) + '" ') == source.resolve()
    assert image_directory("'" + str(source) + "'") == source.resolve()
    with pytest.raises(ValueError, match="directory"):
        image_directory("")


class ScriptedTerminal(Terminal):
    def __init__(self, answers):
        self.output = io.StringIO()
        super().__init__(Console(file=self.output, width=80, color_system=None))
        self.answers = iter(answers)
        self.prompts = []

    def ask(self, label, *, path=False):
        self.prompts.append(label)
        answer = next(self.answers)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def test_home_uses_exact_choices_and_only_essential_questions(collection):
    source, home = collection
    terminal = ScriptedTerminal(["1", str(source), "y", "2", "", "q"])
    calls = []

    def worker(action, source, home, dryrun):
        calls.append((action, source, dryrun))
        return Result(action, source, dryrun, [])

    preferences = Preferences(home)
    assert App(preferences, terminal, worker).run() == 0
    menu = terminal.output.getvalue()
    positions = [menu.index(choice) for choice in HOME_MENU.splitlines()]
    assert positions == sorted(positions)
    assert calls == [("tag", source, True), ("remove", source, False)]
    assert terminal.prompts == [
        "> ",
        "Path: ",
        "Preview only? --dryrun [y/N]: ",
        "> ",
        "Preview only? --dryrun [y/N]: ",
        "> ",
    ]
    assert not home.exists()


def test_settings_and_saved_path_skip_path_prompt(collection):
    source, home = collection
    terminal = ScriptedTerminal(
        ["0", "1", str(source), "2", str(source / "sub"), "0", "1", "--dryrun", "q"]
    )
    calls = []

    def worker(action, source, home, dryrun):
        calls.append(source)
        return Result(action, source, dryrun, [])

    assert App(Preferences(home), terminal, worker).run() == 0
    assert calls == [source / "sub"]
    assert "Path: " not in terminal.prompts
    assert Preferences.load(home).selected_path == source


def test_ctrl_c_returns_home_and_ctrl_d_exits(collection):
    _, home = collection
    terminal = ScriptedTerminal(["1", KeyboardInterrupt(), EOFError()])
    assert App(Preferences(home), terminal).run() == 0
    assert "Cancelled. Back at Home." in terminal.output.getvalue()
    assert not home.exists()


def test_stale_default_prompts_for_replacement(collection):
    source, home = collection
    terminal = ScriptedTerminal(["1", str(source), "y", "q"])
    preferences = Preferences(home, default_path=source / "gone")
    assert App(preferences, terminal, lambda a, p, h, d: Result(a, p, d, [])).run() == 0
    assert preferences.session_path == source


@pytest.mark.parametrize("action", ["tag", "remove"])
def test_direct_cli_dryrun_and_missing_path(collection, monkeypatch, capsys, action):
    source, home = collection
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main([action]) == 2
    assert "Supply an image directory" in capsys.readouterr().out
    assert main([action, str(source), "--dryrun"]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert not home.exists()


def test_saved_cli_default_and_global_dryrun(collection, monkeypatch):
    source, home = collection
    preferences = Preferences(home)
    preferences.save_default(source)
    before = snapshot(home)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main(["--dryrun", "tag"]) == 0
    assert snapshot(home) == before


def test_terminal_text_is_literal_and_issues_bounded(collection):
    source, _ = collection
    output = io.StringIO()
    terminal = Terminal(
        Console(
            file=output,
            width=40,
            height=25,
            color_system=None,
            force_terminal=True,
            legacy_windows=False,
        )
    )
    terminal.say(HOME_MENU)
    terminal.result(
        Result(
            "tag",
            source,
            True,
            [Item(f"[bold]{i}.png", f"{i}.txt", "blocked", "collision") for i in range(8)],
        )
    )
    text = output.getvalue()
    assert "[1] Tag Image Directory" in text and "[bold]0.png" in text
    assert "and 5 more" in text and "[bold]7.png" not in text
    assert max(map(len, text.splitlines())) <= 40


def test_command_echo_quotes_powershell_literals():
    command = command_text("tag", Path("a'b $foo [x]"), True)
    if os.name == "nt":
        assert "'a''b $foo [x]'" in command
    assert command.endswith(" --dryrun")


def test_caption_access_time_changes_do_not_block_removal(collection, monkeypatch):
    source, home = collection
    (source / "first.txt").write_text("caption")
    original_hash = operations.file_sha256

    def update_access_time(path):
        digest = original_hash(path)
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns + 1_000_000_000, info.st_mtime_ns))
        return digest

    monkeypatch.setattr(operations, "file_sha256", update_access_time)
    result = run_directory("remove", source, home)
    assert result.changed == 1 and result.exit_code == 0
    assert (result.backup / "first.txt").read_text() == "caption"


def test_redirected_output_keeps_copyable_commands_and_paths(collection):
    source, _ = collection
    output = io.StringIO()
    terminal = Terminal(Console(file=output, width=30, color_system=None))
    command = command_text("tag", source, True)
    terminal.say(command)
    assert output.getvalue() == command + "\n"


def test_tag_automatically_fetches_first_model(collection, monkeypatch):
    source, home = collection
    calls = []

    def fetch(root, model):
        calls.append((root, model))
        local_model(home)

    monkeypatch.setattr(operations, "fetch_bundle", fetch)
    result = run_directory("tag", source, home)
    assert result.changed == 2 and calls == [(home / "models", "swinv2-v3")]


def test_caption_created_at_final_commit_is_not_overwritten(collection, monkeypatch):
    source, home = collection
    local_model(home)
    original_rename = Path.rename
    original_link = os.link

    def race_rename(path, target):
        if path.name.startswith(".trainime-"):
            Path(target).write_text("concurrent caption")
        return original_rename(path, target)

    def race_link(path, target, **kwargs):
        Path(target).write_text("concurrent caption")
        return original_link(path, target, **kwargs)

    monkeypatch.setattr(Path, "rename", race_rename)
    monkeypatch.setattr(os, "link", race_link)
    result = run_directory("tag", source, home)
    assert result.changed == 0 and len(result.errors) == 2
    assert (source / "first.txt").read_text() == "concurrent caption"
    assert not list(source.rglob(".trainime-*"))
