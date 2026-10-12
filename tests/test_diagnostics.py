from __future__ import annotations

import builtins
import errno
import io
import json
import os
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest
from rich.console import Console
from test_tagging import make_bundle

from image_dataset_train import bootstrap, diagnostics, doctor
from image_dataset_train.diagnostics import EventLog, diagnose, failure_text
from image_dataset_train.model_bundle import Label, bundle_path, load_bundle
from image_dataset_train.preferences import Preferences
from image_dataset_train.score_cache import ScoreCache
from image_dataset_train.trainime import Terminal, main


@pytest.mark.parametrize(
    "error,code",
    [
        (OSError(errno.ENOSPC, "full"), "DISK_FULL"),
        (PermissionError("denied"), "ACCESS_DENIED"),
        (FileNotFoundError("gone"), "PATH_MISSING"),
        (ImportError("missing"), "RUNTIME_BROKEN"),
        ("Cannot read settings: invalid JSON", "SETTINGS_INVALID"),
        ("Same-stem image collision", "CAPTION_COLLISION"),
        ("model bundle hash mismatch", "ARTIFACT_DAMAGED"),
        ("model download failed", "NETWORK_UNAVAILABLE"),
        ("Another Trainime operation is using this directory", "JOB_BUSY"),
        ("Image changed after inspection", "FILES_CHANGED"),
        ("Linked files are skipped", "LINK_SKIPPED"),
        ("unreadable_image", "IMAGE_INVALID"),
        ("No tags cleared the threshold", "NO_CONFIDENT_TAGS"),
        ("Something new", "UNEXPECTED_ERROR"),
    ],
)
def test_each_error_has_a_specific_recovery(error, code):
    result = diagnose(error)
    assert result.code == code and len(result.fix) > 30


def test_log_contains_traceback_context_and_redacts_credentials(tmp_path):
    log = EventLog(tmp_path)
    try:
        raise RuntimeError(
            "https://alice:secret@example.org/?token=hidden Authorization: Bearer abc123"
        )
    except RuntimeError as exc:
        text = failure_text(exc, log, action="tag", operation="example-operation")
    assert "Fix:" in text and "Error report:" in text
    files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(files) == 2
    for path in files:
        raw = path.read_text(encoding="utf-8")
        assert "abc123" not in raw and "hidden" not in raw and "alice:secret" not in raw
        record = json.loads(raw)
        assert "raise RuntimeError" in record["traceback"]
        assert record["operation"] == "example-operation" and record["level"] == "error"
        assert record["pid"] == os.getpid()


def test_readonly_home_falls_back_to_a_reportable_log_directory(tmp_path, monkeypatch):
    home = tmp_path / "not-a-directory"
    home.write_text("occupied")
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(diagnostics.tempfile, "gettempdir", lambda: str(fallback))
    log = EventLog(home)
    report = log.exception(ValueError("failure"))
    assert report and report.is_relative_to(fallback)
    assert "logs saved to" in log.warning


def test_disabled_logging_creates_nothing(tmp_path):
    home = tmp_path / "app"
    log = EventLog(home, enabled=False)
    assert log.exception(ValueError("dry run")) is None
    assert not home.exists()


def test_settings_repair_preserves_original_bytes(tmp_path):
    home = tmp_path / "app"
    home.mkdir()
    original = b'{"schema_version":1, incomplete\n'
    (home / "settings.json").write_bytes(original)
    result = doctor._settings_check(home, fix=True)
    assert result.status == "fixed"
    backup = next((home / "recovery" / "settings").iterdir())
    assert backup.read_bytes() == original
    assert Preferences.load(home).default_path is None


def test_stale_default_repair_preserves_setting(tmp_path):
    home = tmp_path / "app"
    Preferences(home).save_default(tmp_path / "missing")
    result = doctor._settings_check(home, fix=True)
    assert result.status == "fixed" and "Reset saved path" in result.detail
    assert Preferences.load(home).default_path is None
    assert len(list((home / "recovery" / "settings").iterdir())) == 1


def test_doctor_fix_dryrun_never_changes_settings(tmp_path, monkeypatch, capsys):
    home = tmp_path / "app"
    home.mkdir()
    settings = home / "settings.json"
    settings.write_bytes(b"invalid settings")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    monkeypatch.setattr(doctor, "runtime_probe", lambda: (False, "test missing runtime"))
    assert bootstrap.main(["doctor", "--fix", "--dryrun", "--json"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["log"] is None
    assert settings.read_bytes() == b"invalid settings"
    assert sorted(p.name for p in home.iterdir()) == ["settings.json"]


def test_doctor_survives_missing_ui_and_native_dependencies(monkeypatch, capsys):
    original = builtins.__import__

    def reject(name, *args, **kwargs):
        if name.split(".")[0] in {"rich", "numpy", "onnxruntime", "PIL"}:
            pytest.fail("The doctor imported a broken runtime in its own process")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject)
    monkeypatch.setattr(doctor, "runtime_probe", lambda: (False, "No module named numpy"))
    assert bootstrap.main(["doctor", "--runtime-only", "--dryrun"]) == 1
    assert "trainime doctor --fix" in capsys.readouterr().out


def test_runtime_probe_executes_native_onnx():
    healthy, detail = doctor.runtime_probe()
    assert healthy, detail
    assert json.loads(detail)["inference"] == "passed"


def test_broken_settings_do_not_lock_out_interactive_menu(tmp_path, monkeypatch, capsys):
    home = tmp_path / "app"
    home.mkdir()
    (home / "settings.json").write_text("broken")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    monkeypatch.setattr(Terminal, "ask", lambda *a, **kw: "q")
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "SETTINGS_INVALID" in output and "[1] Tag Image Directory" in output
    assert (home / "settings.json").read_text() == "broken"


def test_doctor_model_repair_preserves_damaged_bundle(tmp_path, monkeypatch):
    home = tmp_path / "app"
    destination = bundle_path(home / "models", "swinv2-v3")
    labels = [Label(0, "solo", 0)]
    make_bundle(destination, labels)
    (destination / "model.onnx").write_bytes(b"damaged model")
    calls = []

    def fetch(root, profile):
        calls.append(profile)
        make_bundle(destination, labels)
        return destination

    repaired = doctor.repair_model(home, fetch=fetch)
    assert calls == ["swinv2-v3"]
    assert load_bundle(repaired).labels == labels
    backup = next((home / "recovery" / "models").iterdir())
    assert (backup / "model.onnx").read_bytes() == b"damaged model"


def test_model_download_retries_once_and_reports_both_failures(tmp_path):
    calls = []

    def fail(*args):
        calls.append(1)
        raise RuntimeError("download connection refused")

    with pytest.raises(RuntimeError, match="connection refused"):
        doctor.repair_model(tmp_path, fetch=fail)
    assert len(calls) == 2
    rows = [
        json.loads(line)
        for file in (tmp_path / "logs").glob("*.errors.jsonl")
        for line in file.read_text(encoding="utf-8").splitlines()
    ]
    assert [r["attempt"] for r in rows] == [1, 2]


def test_damaged_score_repair_preserves_then_recomputes(tmp_path):
    cache = ScoreCache(tmp_path / "scores", "namespace", 2)
    digest = "a" * 64
    path = cache.put(digest, np.array([0.1, 0.9], dtype=np.float32))
    path.write_bytes(b"broken vector")
    assert cache.get(digest, repair=True) is None
    backup = next((tmp_path / "recovery" / "scores").iterdir())
    assert backup.read_bytes() == b"broken vector" and not path.exists()
    cache.put(digest, np.array([0.2, 0.8], dtype=np.float32))
    np.testing.assert_array_equal(cache.get(digest), np.array([0.2, 0.8], dtype=np.float32))


def test_doctor_cache_check_and_fix(tmp_path):
    cache = ScoreCache(tmp_path / "scores", "namespace", 2)
    path = cache.put("a" * 64, np.array([0.1, 0.9], dtype=np.float32))
    path.write_bytes(b"bad npz")
    assert doctor._cache_check(tmp_path, False).status == "error"
    assert path.exists()
    assert doctor._cache_check(tmp_path, True).status == "fixed"
    assert not path.exists()


def test_recovery_never_moves_outside_owned_home(tmp_path):
    outside = tmp_path / "original.png"
    outside.write_bytes(b"original")
    with pytest.raises(ValueError, match="outside"):
        doctor.preserve(outside, tmp_path / "app", "models")
    assert outside.read_bytes() == b"original"


def test_logs_command_shows_actual_error_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRAINIME_HOME", str(tmp_path))
    monkeypatch.setattr(doctor.tempfile, "gettempdir", lambda: str(tmp_path / "fallback"))
    EventLog(tmp_path).exception(ValueError("fixture failure"), action="tag")
    assert bootstrap.main(["logs", "--tail", "1"]) == 0
    output = capsys.readouterr().out
    assert "Latest errors:" in output and "fixture failure" in output


def test_runtime_fix_failure_still_checks_other_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "runtime_probe", lambda: (False, "bad runtime"))

    def fail(home):
        raise RuntimeError("installer not available")

    monkeypatch.setattr(doctor, "repair_runtime", fail)
    checks = doctor.check_all(tmp_path, fix=True)
    assert any(c.name == "runtime" and c.status == "error" for c in checks)
    assert any(c.name == "storage" for c in checks)


@pytest.mark.skipif(os.name != "nt", reason="Windows command registration")
def test_path_repair_prioritizes_command_without_losing_other_entries(tmp_path, monkeypatch):
    import ctypes

    target = tmp_path / "current bin"
    old = str(tmp_path / "old bin")
    user_path = old + ";%TRAINIME_TEST_BIN%\\;C:\\other"
    saved = {}
    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        REG_EXPAND_SZ=2,
        CreateKey=lambda *args: nullcontext("key"),
        QueryValueEx=lambda *args: (user_path, 2),
        SetValueEx=lambda key, name, reserved, kind, value: saved.update(value=value, kind=kind),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(SendMessageTimeoutW=lambda *args: 1)),
    )
    monkeypatch.setenv("TRAINIME_TEST_BIN", str(target))
    monkeypatch.setenv("PATH", user_path)
    doctor.register_user_path(target)
    expected = [str(target), old, "C:\\other"]
    assert saved == {"value": ";".join(expected), "kind": 2}
    assert os.get_exec_path() == expected


def test_terminal_error_shows_recovery_and_log(tmp_path):
    stream = io.StringIO()
    terminal = Terminal(Console(file=stream, width=80))
    terminal.home = tmp_path
    terminal.failure(PermissionError("locked image"), action="tag")
    text = stream.getvalue()
    assert "ACCESS_DENIED" in text and "Fix:" in text and "Error report:" in text


def test_changing_settings_preserves_a_previously_broken_file(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_bytes(b"broken settings")
    Preferences(tmp_path).save_default(tmp_path)
    assert Preferences.load(tmp_path).default_path == tmp_path
    assert next((tmp_path / "recovery" / "settings").iterdir()).read_bytes() == b"broken settings"


def test_structured_secret_redaction_keeps_valid_json(tmp_path):
    log = EventLog(tmp_path)
    path = log.event(
        "test", nested={"token": 'quote"slash\\', "password": "p@ss"}, message='token=first"second'
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["nested"] == {"token": "[REDACTED]", "password": "[REDACTED]"}


def test_application_repair_retains_original_and_leaves_launcher_alone(tmp_path, monkeypatch):
    import zipfile

    from image_dataset_train.repair_package import restore

    home, site = tmp_path / "app", tmp_path / "site-packages"
    package = site / "image_dataset_train"
    package.mkdir(parents=True)
    (package / "bootstrap.py").write_bytes(b"damaged source")
    launcher = tmp_path / "trainime.exe"
    launcher.write_bytes(b"running executable")
    wheel = tmp_path / "repair.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("image_dataset_train/bootstrap.py", "# good source\n")
        archive.writestr("unrelated.py", "# must not be installed")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert restore(wheel, site) == 1
    assert (package / "bootstrap.py").read_bytes() == b"# good source\n"
    assert launcher.read_bytes() == b"running executable" and not (site / "unrelated.py").exists()
    backups = list((home / "recovery" / "application").rglob("bootstrap.py"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"damaged source"
    assert restore(wheel, site) == 0


def test_application_repair_rejects_path_escape_before_writes(tmp_path):
    import zipfile

    from image_dataset_train.repair_package import restore

    site = tmp_path / "site"
    site.mkdir()
    wheel = tmp_path / "bad.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("image_dataset_train/bootstrap.py", "# valid\n")
        archive.writestr("image_dataset_train/../../escape.py", "# unsafe\n")
    with pytest.raises(ValueError, match="Invalid application file"):
        restore(wheel, site)
    assert not list(site.iterdir()) and not (tmp_path / "escape.py").exists()
