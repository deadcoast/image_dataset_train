"""Inspect and repair Trainime without importing its UI or native runtime first."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from image_dataset_train import terror
from image_dataset_train.diagnostics import EventLog, app_home, diagnose, failure_text, redact

PROBE = r"""
import base64, importlib, json
modules = ['PIL', 'numpy', 'onnxruntime', 'huggingface_hub', 'rich', 'prompt_toolkit', 'filelock',
           'image_dataset_train.trainime', 'image_dataset_train.tagging']
versions = {}
for name in modules:
    module = importlib.import_module(name)
    versions[name] = getattr(module, '__version__', 'imported')
import numpy as np
import onnxruntime as ort
model = base64.b64decode(
    'CAo6SgoOCgF4CgF4EgF5IgNBZGQSFnRyYWluaW1lLXJ1bnRpbWUtcHJvYmVa'
    'DwoBeBIKCggIARIECgIIAWIPCgF5EgoKCAgBEgQKAggBQgQKABAN')
session = ort.InferenceSession(model, providers=['CPUExecutionProvider'])
output = session.run(None, {'x': np.array([2], dtype=np.float32)})[0]
assert output.tolist() == [4.0], 'native inference produced incorrect output'
print(json.dumps({'versions': versions, 'providers': ort.get_available_providers(),
                  'inference': 'passed'}))
"""


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def runtime_probe(python: Path | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [str(python or sys.executable), "-I", "-c", PROBE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        if result.returncode:
            return False, redact(
                (
                    result.stderr
                    or result.stdout
                    or f"Native runtime exited with code {result.returncode}"
                ).strip()
            )
        return True, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def preserve(path: Path, home: Path, kind: str) -> Path:
    """Move only owned application artifacts into recovery, never source images."""
    home = home.resolve()
    resolved = path.resolve()
    if (
        resolved == home
        or not resolved.is_relative_to(home)
        or path.is_symlink()
        or path.is_junction()
    ):
        raise ValueError("Recovery refuses to move files outside the application-data directory.")
    destination = home / "recovery" / kind / (uuid4().hex + "-" + path.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    path.rename(destination)
    return destination


def repair_settings(home: Path) -> Path:
    from image_dataset_train.preferences import Preferences

    backup = preserve(home / "settings.json", home, "settings")
    Preferences(home).save_default(None)
    return backup


def repair_model(home: Path, progress=None, fetch=None) -> Path:
    from filelock import FileLock

    from image_dataset_train.model_bundle import bundle_path, fetch_bundle, load_bundle

    log = EventLog(home)
    root = home / "models"
    fetch = fetch or fetch_bundle
    destination = bundle_path(root, "swinv2-v3")
    (home / "locks").mkdir(parents=True, exist_ok=True)
    with FileLock(str(home / "locks" / "model.lock"), timeout=0):
        if (destination / "model.json").exists():
            try:
                load_bundle(destination)
                return destination
            except (OSError, ValueError) as exc:
                backup = preserve(destination, home, "models")
                log.exception(exc, action="model_repair", preserved=backup)
                if progress:
                    progress("Damaged model preserved; downloading its replacement…")
        for attempt in range(2):
            try:
                result = fetch(root, "swinv2-v3") or destination
                load_bundle(result)
                log.event("model_ready", model=result)
                return result
            except RuntimeError as exc:
                log.exception(exc, action="model_download", attempt=attempt + 1)
                if attempt:
                    raise
                if progress:
                    progress("Model download interrupted; retrying once…")
    raise AssertionError("unreachable")


def repair_runtime(home: Path) -> str:
    installer = home / "installer" / "install.ps1"
    if not installer.is_file():
        raise RuntimeError(
            "Repair installer is not available here. Run install.cmd from the "
            "downloaded Trainime folder; it will install and retain the repair tools."
        )
    receipt = json.loads((home / "install.json").read_text(encoding="utf-8"))
    import hashlib

    if hashlib.sha256(installer.read_bytes()).hexdigest() != receipt.get("installer_sha256"):
        raise ValueError(
            "The repair installer changed. Run the original install.cmd to refresh it."
        )
    shell = shutil.which("powershell") if os.name == "nt" else None
    if shell is None:
        raise RuntimeError(
            "Automatic runtime repair uses the Windows installer. "
            "Run install.cmd on Windows, or reinstall this package on your platform."
        )
    # The doctor process deliberately has not imported DLL-backed packages.
    command = [
        shell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(installer),
        "-Repair",
        "-RuntimeOnly",
        "-NoPause",
    ]
    if receipt.get("path_registered") is False:
        command.append("-NoPath")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env={**os.environ, "TRAINIME_HOME": str(home)},
    )
    EventLog(home).event(
        "runtime_repair",
        exit_code=result.returncode,
        output=redact(result.stdout),
        error=redact(result.stderr),
    )
    if result.returncode:
        raise RuntimeError(
            "Runtime repair did not finish. " + (result.stderr or result.stdout)[-2000:]
        )
    return "Reinstalled and verified the runtime."


def register_user_path(directory: Path) -> None:
    directory = directory.resolve()
    if os.name != "nt":
        raise RuntimeError(
            f"Add {directory} to PATH in your shell profile, then open a new terminal."
        )
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        entries = [entry for entry in value.split(";") if entry]

        def is_target(entry: str) -> bool:
            return os.path.normcase(os.path.expandvars(entry).rstrip("\\/")) == os.path.normcase(
                str(directory)
            )

        updated = ";".join([str(directory), *(e for e in entries if not is_target(e))])
        if updated != value:
            winreg.SetValueEx(key, "Path", 0, kind, updated)
    os.environ["PATH"] = os.pathsep.join(
        [str(directory), *(entry for entry in os.get_exec_path() if not is_target(entry))]
    )
    # Notify Explorer/new terminals. A stale parent shell still needs reopening.
    import ctypes

    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF, 0x1A, 0, "Environment", 2, 1000, ctypes.byref(result)
    )


def _settings_check(home: Path, fix: bool) -> Check:
    path = home / "settings.json"
    if not path.exists():
        return Check("settings", "ok", "No saved default; the menu will ask for an image folder.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("unsupported settings format")
        selected = raw.get("default_path")
        if selected is not None and (
            not isinstance(selected, str) or not Path(selected).is_absolute()
        ):
            raise ValueError("default_path is not an absolute path")
        if selected and not Path(selected).is_dir():
            raise ValueError(f"Saved directory is unavailable: {selected}")
        return Check("settings", "ok", "Saved settings are readable.")
    except (ValueError, OSError) as exc:
        if fix:
            backup = repair_settings(home)
            return Check("settings", "fixed", f"Reset saved path; original settings: {backup}")
        return Check(
            "settings",
            "error",
            str(exc),
            "Run trainime doctor --fix to preserve the file and reset the saved path.",
        )


def _cache_check(home: Path, fix: bool) -> Check:
    import numpy as np

    from image_dataset_train.score_cache import score_checksum
    from image_dataset_train.wd_tagger import validate_scores

    damaged, repaired, checked = 0, 0, 0
    for path in (home / "scores").glob("*/*/*.npz"):
        checked += 1
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
                raise ValueError("cache link outside application data")
            with np.load(path, allow_pickle=False) as data:
                scores = data["scores"]
                if scores.ndim != 1:
                    raise ValueError("invalid vector shape")
                validate_scores(scores, len(scores))
                if str(data["sha256"]) != path.stem or str(data["checksum"]) != score_checksum(
                    scores
                ):
                    raise ValueError("cache identity/checksum mismatch")
        except Exception as exc:
            damaged += 1
            EventLog(home, enabled=fix).exception(exc, action="cache_check", path=path)
            if fix:
                preserve(path, home, "scores")
                repaired += 1
    if damaged:
        return Check(
            "score_cache",
            "fixed" if repaired == damaged else "error",
            f"Checked {checked} vectors; {damaged} damaged, {repaired} preserved for recovery.",
            "Run trainime doctor --fix; tagging will recompute only missing scores.",
        )
    return Check("score_cache", "ok", f"Verified {checked} cached score vectors.")


def _path_check(
    path: Path,
    home: Path,
    *,
    probe_write: bool = False,
    repair: str | bool = False,
    dryrun: bool = False,
) -> Check:
    from image_dataset_train.config import ValidationConfig
    from image_dataset_train.operations import (
        _plan,
        _removal_inventory,
        run_directory,
        workflow_config,
    )
    from image_dataset_train.preferences import image_directory

    source = image_directory(str(path))
    workflow_config(source, home)
    repaired = None
    if repair:
        result = run_directory("fix", source, home, dryrun=dryrun, fix=repair)
        repaired = result.repairs
        if result.errors:
            return Check(
                "image_directory",
                "error",
                "; ".join(result.errors[:3]),
                f'Retry: trainime fix "{source}"{terror.fix_arguments(repair)}',
            )
        if dryrun and repaired and repaired.actions:
            preview = "; ".join(
                f"[{run.fix_code}] {a.get('description', str(a))}"
                for run in repaired.runs
                for a in run.actions[:3]
            )
            return Check(
                "image_directory",
                "warning",
                f"{len(repaired.actions)} planned repair actions. {preview}",
                f'Apply: trainime doctor --path "{source}"{terror.fix_arguments(repair)}',
            )
    if probe_write:
        with tempfile.TemporaryFile(dir=source):
            pass
    records = _removal_inventory(source, lambda message: None)
    items = _plan(source, records, "remove", ValidationConfig())
    problems = [item for item in items if item.status in {"blocked", "rejected"}]
    if problems:
        details = "; ".join(f"{item.image}: {item.reason}" for item in problems[:3])
        return Check(
            "image_directory",
            "error",
            f"[{diagnose(problems[0].reason).code}] {len(problems)} association issues: {details}",
            f'[{problems[0].fix_code}] Apply: trainime doctor --path "{source}"'
            + terror.fix_arguments(problems[0].fix_code)
            if problems[0].fix_code
            else diagnose(problems[0].reason).fix,
        )
    if repaired and repaired.runs:
        details = "; ".join(
            f"[{run.fix_code}] " + ", ".join(f"{n} {label}" for label, n in run.metrics.items())
            for run in repaired.runs
        )
        return Check(
            "image_directory",
            "fixed",
            f"{details}. Directory rechecked: no association issues. "
            f"Recovery: {', '.join(map(str, repaired.reports))}",
        )
    return Check(
        "image_directory", "ok", f"Readable: {source}; {len(items)} image associations checked."
    )


def check_all(
    home: Path, *, fix: bool = False, runtime_only: bool = False, path: Path | None = None
) -> list[Check]:
    checks = []
    healthy, detail = runtime_probe()
    if not healthy and fix:
        try:
            repair_runtime(home)
            healthy, detail = runtime_probe()
            checks.append(
                Check(
                    "runtime",
                    "fixed" if healthy else "error",
                    detail,
                    "Run install.cmd again; inspect the installation log it prints.",
                )
            )
        except Exception as exc:
            checks.append(Check("runtime", "error", str(exc), "Run install.cmd again."))
    else:
        checks.append(
            Check(
                "runtime",
                "ok" if healthy else "error",
                detail,
                "Run trainime doctor --fix, or run install.cmd if startup is broken.",
            )
        )
    if runtime_only:
        return checks

    def attempt(name, operation):
        try:
            checks.append(operation())
        except Exception as exc:
            checks.append(Check(name, "error", str(exc), diagnose(exc).fix))

    attempt("settings", lambda: _settings_check(home, fix))
    try:
        closest = home
        while not closest.exists():
            closest = closest.parent
        free = shutil.disk_usage(closest).free
        if fix:
            home.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=home):
                pass
        writable = os.access(closest, os.W_OK)
        checks.append(
            Check(
                "storage",
                "ok" if writable and free >= 1024**3 else "warning",
                f"{free / 1024**3:.1f} GiB free at {home}; writable={writable}.",
                "Free space, or set TRAINIME_HOME to a writable folder on another drive "
                "and rerun install.cmd.",
            )
        )
    except OSError as exc:
        checks.append(Check("storage", "error", str(exc), diagnose(exc).fix))

    def launcher():
        receipt_file = home / "install.json"
        if not receipt_file.exists():
            return Check(
                "installation",
                "warning",
                "No installer recovery receipt is present.",
                "Run install.cmd once to register the installation and retain repair files.",
            )
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        directory = Path(receipt["bin"])
        executable = directory / ("trainime.exe" if os.name == "nt" else "trainime")
        if not executable.is_file():
            if fix:
                repair_runtime(home)
            if not executable.is_file():
                return Check(
                    "command", "error", f"Missing command: {executable}", "Run install.cmd."
                )
        found = shutil.which("trainime")
        if receipt.get("path_registered") is False:
            return Check(
                "command", "ok", f"Direct launcher: {executable}; PATH registration was skipped."
            )
        if not found or Path(found).resolve() != executable.resolve():
            if fix:
                register_user_path(directory)
                selected = shutil.which("trainime")
                if not selected or Path(selected).resolve() != executable.resolve():
                    return Check(
                        "command",
                        "error",
                        "Another command still takes precedence in this shell.",
                        f'Launch directly: & "{executable}". Remove the older Trainime '
                        "entry from PATH, then open a new terminal.",
                    )
                return Check("command", "fixed", f"Registered {directory}. Open a new terminal.")
            return Check(
                "command",
                "error",
                "PATH does not select this Trainime installation.",
                "Run trainime doctor --fix, then open a new terminal.",
            )
        return Check("command", "ok", str(executable))

    attempt("command", launcher)

    if healthy:

        def model():
            from image_dataset_train.model_bundle import bundle_path, load_bundle

            destination = bundle_path(home / "models", "swinv2-v3")
            if fix:
                repair_model(home)
                return Check("model", "ok", "Pinned tagger verified and ready.")
            if not (destination / "model.json").exists():
                return Check(
                    "model",
                    "warning",
                    "Model has not finished downloading.",
                    "Run trainime doctor --fix to prepare it, or start Tag Image Directory.",
                )
            load_bundle(destination)
            return Check("model", "ok", "Pinned model and label hashes verified.")

        attempt("model", model)
        attempt("score_cache", lambda: _cache_check(home, fix))
        if path is not None:
            attempt("image_directory", lambda: _path_check(path, home, probe_write=fix, repair=fix))
    return checks


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="trainime " + argv[0])
    if argv[0] == "logs":
        parser.add_argument("--tail", type=int, default=20)
        args = parser.parse_args(argv[1:])
        if not 1 <= args.tail <= 200:
            parser.error("--tail must be between 1 and 200")
        directories = [app_home() / "logs", Path(tempfile.gettempdir()) / "trainime" / "logs"]
        print("Logs: " + str(directories[0]))
        files = [p for root in directories for p in root.glob("*.errors.jsonl")]
        if not files:
            print(
                "No application error logs yet. Installer logs use install-*.log in the log folder."
            )
            return 0
        newest = max(files, key=lambda p: p.stat().st_mtime_ns)
        print("Latest errors: " + str(newest))
        from collections import deque

        with newest.open(encoding="utf-8") as stream:
            print("".join(deque(stream, maxlen=args.tail)), end="")
        return 0
    parser.add_argument(
        "--fix",
        nargs="?",
        const="all",
        action="append",
        type=terror.selector_argument,
        metavar="N[,N...]",
        help="repair runtime and detected --path errors; numbers select registered directory fixes",
    )
    parser.add_argument(
        "--dryrun", "--dry-run", action="store_true", help="diagnose without writes or downloads"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    parser.add_argument(
        "--path",
        type=Path,
        help="inspect a directory; --fix applies its detected registered repairs",
    )
    parser.add_argument("--runtime-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(terror.normalize_fix_argv(argv[1:]))
    selection = terror.normalize_selector(args.fix)
    home = app_home()
    log = EventLog(home, enabled=not args.dryrun)
    try:
        if selection and selection != "all":
            from image_dataset_train.preferences import Preferences

            selected = args.path or Preferences.load(home).default_path
            if selected is None:
                parser.error(
                    'Supply --path "D:\\images" for selected repairs, '
                    "or save a default in Settings."
                )
            checks = [_path_check(selected, home, repair=selection, dryrun=args.dryrun)]
        else:
            checks = check_all(
                home,
                fix=bool(selection) and not args.dryrun,
                runtime_only=args.runtime_only,
                path=None if selection and args.dryrun else args.path,
            )
            if selection and args.dryrun and args.path and not args.runtime_only:
                checks.append(_path_check(args.path, home, repair=selection, dryrun=True))
        result = [asdict(check) for check in checks]
        report = log.event(
            "doctor",
            fix=bool(selection) and not args.dryrun,
            fix_selection=selection,
            checks=result,
        )
        if args.json:
            print(json.dumps({"checks": result, "log": str(report) if report else None}, indent=2))
        else:
            for check in checks:
                detail = (
                    "Imports and native CPU inference passed."
                    if check.name == "runtime" and (check.status in {"ok", "fixed"})
                    else check.detail
                )
                print(f"[{check.status.upper()}] {check.name}: {detail}")
                if check.status in {"error", "warning"} and check.fix:
                    print("  Fix: " + check.fix)
            if report:
                print("Diagnostic report: " + str(report))
            if log.warning:
                print(log.warning)
        return int(any(check.status == "error" for check in checks))
    except Exception as exc:
        print(failure_text(exc, log, action="doctor"), file=sys.stderr)
        return 2
