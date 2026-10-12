"""Dependency-free diagnostics: usable even when the tagging/UI runtime is broken."""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train import __version__
from image_dataset_train.terror import TERROR, TERROR_FIX


def app_home() -> Path:
    override = os.environ.get("TRAINIME_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "trainime"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "trainime"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "trainime"


def redact(text: str) -> str:
    text = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s\"'&,;]+", r"\1[REDACTED]", text)
    return re.sub(
        r"(?i)((?:authorization|bearer|token|api[_-]?key|password|secret|signature)"
        r"[\s\"'=:\]]+)[^\s\"'&,;]+",
        r"\1[REDACTED]",
        text,
    )


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish_directory(source: Path, target: Path) -> None:
    """Publish a completed report, tolerating brief Windows file-sharing locks."""
    for attempt in range(6):
        if os.path.lexists(target):
            raise FileExistsError(f"Report destination already exists: {target}")
        try:
            source.rename(target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 5:
                exc.add_note(f"Completed report retained at {source}. Retry the same command.")
                raise
            EventLog(app_home()).event(
                "report_publish_retry",
                source=source,
                target=target,
                attempt=attempt + 1,
                error=str(exc),
            )
            time.sleep(0.05 * 2**attempt)


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        sensitive = {
            "authorization",
            "password",
            "secret",
            "token",
            "apikey",
            "api_key",
            "signature",
        }
        return {
            key: "[REDACTED]" if str(key).lower() in sensitive else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return redact(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class Diagnosis:
    code: str
    problem: str
    fix: str
    fix_code: str | None = None


def diagnose(error: BaseException | str) -> Diagnosis:
    text = str(error)
    lower = text.lower()
    number = getattr(error, "errno", None)
    if number == errno.ENOSPC or any(s in lower for s in ("disk full", "no space left")):
        return Diagnosis(
            "DISK_FULL",
            "The drive has no room for the next write.",
            "Free space on the drive shown in the error, then rerun the same action. "
            "Completed captions and recovery copies are kept.",
        )
    if isinstance(error, ImportError) or any(
        s in lower
        for s in (
            "runtime is missing",
            "dll load failed",
            "no module named",
            "dependencies missing",
        )
    ):
        return Diagnosis(
            "RUNTIME_BROKEN",
            "A required runtime component is missing or damaged.",
            "Run: trainime doctor --fix. If trainime cannot start, run install.cmd again.",
        )
    if "settings" in lower and any(s in lower for s in ("cannot read", "format", "json")):
        return Diagnosis(
            "SETTINGS_INVALID",
            "The saved settings cannot be read.",
            "Run: trainime doctor --fix. It preserves the broken settings before resetting them.",
        )
    if any(s in lower for s in ("same-stem", "ambiguous", "collision", "[te001]", "[tf001]")):
        return Diagnosis(
            "te001",
            TERROR["te001"],
            f"[tf001] {TERROR_FIX['tf001']} Apply: trainime tag <directory> --fix tf001. "
            "Add --dryrun to preview renames and caption recovery without changes.",
            "tf001",
        )
    if "caption" in lower and "not a regular file" in lower:
        return Diagnosis(
            "CAPTION_PATH_BLOCKED",
            "The .txt destination is occupied by a directory.",
            "Rename the directory at that .txt path, then rerun tagging.",
        )
    if any(s in lower for s in ("model bundle", "score cache", "checksum", "hash mismatch")):
        return Diagnosis(
            "ARTIFACT_DAMAGED",
            "A cached model or score artifact failed verification.",
            "Run: trainime doctor --fix. Damaged cache files are kept in recovery; "
            "models are fetched again and scores are recomputed on the next tag run.",
        )
    if any(s in lower for s in ("download", "connection", "timed out", "certificate", "proxy")):
        return Diagnosis(
            "NETWORK_UNAVAILABLE",
            "A required download could not finish.",
            "Reconnect, check your proxy and system clock, then run trainime doctor --fix. "
            "For installation, rerun install.cmd; cached downloads are reused.",
        )
    if "another trainime" in lower or "lock" in lower and "timeout" in lower:
        return Diagnosis(
            "JOB_BUSY",
            "Another process is using this directory or model.",
            "Finish or cancel the other Trainime job, then retry. "
            "A closed process releases its OS lock automatically.",
        )
    if isinstance(error, PermissionError) or any(
        s in lower
        for s in ("permission", "access is denied", "winerror 32", "being used by another process")
    ):
        return Diagnosis(
            "ACCESS_DENIED",
            "A file or directory is locked or not writable.",
            "Close the program holding the file, then retry. For a read-only location, "
            "use a writable image folder; run trainime doctor --path <folder> to check it.",
        )
    if "separate" in lower and ("director" in lower or "folder" in lower or "tree" in lower):
        return Diagnosis(
            "PATH_OVERLAP",
            "Images and application data overlap.",
            "Select the image subfolder, or set TRAINIME_HOME to a separate writable "
            "folder and rerun install.cmd. Do not select the application-data root.",
        )
    if isinstance(error, FileNotFoundError) or "not a directory" in lower:
        return Diagnosis(
            "PATH_MISSING",
            "The requested directory is unavailable.",
            "Reconnect the drive or enter the current folder path. "
            "Change a saved path in trainime > Settings.",
        )
    if any(s in lower for s in ("changed", "appeared after", "no longer present")):
        return Diagnosis(
            "FILES_CHANGED",
            "Files changed while the operation was running.",
            "Stop other editors or sync jobs writing to this folder, then repeat the action.",
        )
    if any(s in lower for s in ("link", "junction", "escapes")):
        return Diagnosis(
            "LINK_SKIPPED",
            "The path is a link or leaves the selected directory.",
            "Select the real image directory directly instead of its link, then retry.",
        )
    if any(
        s in lower
        for s in ("unidentifiedimageerror", "cannot identify image file", "image file is truncated")
    ):
        return Diagnosis(
            "IMAGE_UNREADABLE",
            "The image could not be decoded.",
            "Open the image to check it, then re-export it as PNG/JPEG or obtain a fresh copy.",
        )
    if any(
        s in lower for s in ("unreadable_image", "multiple_frames", "pixel_limit", "byte_limit")
    ):
        return Diagnosis(
            "IMAGE_INVALID",
            "The file cannot be processed as a bounded still image.",
            "Re-export it as a single-frame PNG/JPEG; reduce extreme dimensions if "
            "reported. Retry the exported file; the original remains untouched.",
        )
    if "no tags" in lower:
        return Diagnosis(
            "NO_CONFIDENT_TAGS",
            "The tagger did not produce a usable caption.",
            "Inspect that image and add a matching .txt caption manually; "
            "the report retains the model scores for review.",
        )
    return Diagnosis(
        "UNEXPECTED_ERROR",
        "The operation could not finish.",
        "Run: trainime doctor --fix. If it still fails, keep the error report "
        "shown below; it contains the traceback and recovery context.",
    )


class EventLog:
    """One JSONL pair per process, bounded size; no global logging configuration."""

    def __init__(self, home: Path, *, enabled: bool = True):
        self.home, self.enabled = home, enabled
        self.identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        self.directory: Path | None = None
        self.warning: str | None = None

    def _open_directory(self) -> Path | None:
        if self.directory:
            return self.directory
        for directory in (self.home / "logs", Path(tempfile.gettempdir()) / "trainime" / "logs"):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=directory):
                    pass
                self.directory = directory
                if directory != self.home / "logs":
                    self.warning = (
                        f"Application log folder is unavailable; logs saved to {directory}."
                    )
                return directory
            except OSError:
                continue
        self.warning = (
            "Logs could not be written. Set TRAINIME_HOME to a writable folder and retry."
        )
        return None

    def event(self, event: str, *, level: str = "info", **data: object) -> Path | None:
        if not self.enabled:
            return None
        directory = self._open_directory()
        if directory is None:
            return None
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session": self.identifier,
            "version": __version__,
            "pid": os.getpid(),
            "level": level,
            "event": event,
            **data,
        }
        line = json.dumps(_redact_value(record), ensure_ascii=False, default=str) + "\n"
        target = directory / f"{self.identifier}.jsonl"
        try:
            for path in (
                [target, directory / f"{self.identifier}.errors.jsonl"]
                if level == "error"
                else [target]
            ):
                # Rotate only this process's own log. Older session/error logs are retained.
                if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
                    path.rename(path.with_name(path.name + "." + uuid4().hex[:8]))
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line)
                    stream.flush()
            return target
        except OSError as exc:
            self.warning = f"Logging failed ({exc}). Set TRAINIME_HOME to a writable folder."
            return None

    def exception(self, error: BaseException, **context: object) -> Path | None:
        return self.event(
            "failure",
            level="error",
            diagnosis=asdict(diagnose(error)),
            exception_type=type(error).__name__,
            message=str(error),
            traceback="".join(traceback.format_exception(error)),
            **context,
        )


def failure_text(error: BaseException, log: EventLog, **context: object) -> str:
    report = log.exception(error, **context)
    diagnosis = diagnose(error)
    lines = [f"{diagnosis.code}: {diagnosis.problem}", redact(str(error)), f"Fix: {diagnosis.fix}"]
    if report:
        lines.append(f"Error report: {report}")
    if log.warning:
        lines.append(log.warning)
    return "\n".join(lines)
