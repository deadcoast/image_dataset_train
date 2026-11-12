"""Restore verified removed captions without overwriting newer source content."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import IMAGE_EXTENSIONS, file_sha256
from image_dataset_train.operations import _finish_commit, _pair_entries, _safe_path

MAX_METADATA_BYTES = 64 * 1024 * 1024
MAX_CAPTION_BYTES = 268_435_456


def _hash(value) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _unlinked(path: Path, boundary: Path) -> Path:
    if not path.is_relative_to(boundary):
        raise ValueError("Recovery path escapes its recorded directory")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked recovery paths are not supported")
        if part == boundary:
            break
    if path.resolve() != path:
        raise ValueError("Recovery directory changed or contains linked parents")
    return path


def _read(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError(f"Missing or oversized recovery metadata: {path}")
    return path.read_bytes()


def _relative(value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid relative path in removal plan")
    parts = PurePosixPath(value)
    if (
        parts.is_absolute()
        or "\\" in value
        or ":" in value
        or any(p in {"", ".", ".."} for p in value.split("/"))
        or any(p.rstrip(". ") != p for p in parts.parts)
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Unsafe relative path in removal plan")
    return value


def _load(
    receipt: Path,
    *,
    expected_sha256: str | None = None,
    expected_plan_sha256: str | None = None,
) -> dict:
    if expected_sha256 is not None and not _hash(expected_sha256):
        raise ValueError("Expected removal receipt checksum must be a full lowercase SHA256")
    if expected_plan_sha256 is not None and not _hash(expected_plan_sha256):
        raise ValueError("Expected removal plan checksum must be a full lowercase SHA256")
    path = receipt.absolute()
    if path.is_dir():
        path /= "operation.json"
    if path.name != "operation.json" or path.parent.parent.name != "operations":
        raise ValueError("Choose operation.json from a saved Trainime removal operation")
    operation, home = path.parent, path.parent.parent.parent
    _unlinked(path, home)
    raw = _read(path)
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(
            "Selected removal receipt changed; refresh recovery history before retrying"
        )
    metadata = json.loads(raw)
    if (
        not isinstance(metadata, dict)
        or metadata.get("schema_version") != 1
        or metadata.get("action") != "remove"
    ):
        raise ValueError("Receipt is not a supported caption removal operation")
    if not isinstance(metadata.get("source"), str):
        raise ValueError("Invalid source directory in removal receipt")
    source = Path(metadata["source"])
    if not source.is_absolute() or not source.is_dir() or source.resolve() != source:
        raise ValueError("Recorded source directory is unavailable or linked")
    if source.is_relative_to(home) or home.is_relative_to(source):
        raise ValueError("Source and recovery directories must be separate trees")
    backup_root = operation / "captions"
    if metadata.get("backup") not in (None, str(backup_root)):
        raise ValueError("Backup directory does not match the removal operation")
    plan_path, journal_path = operation / "plan.json", operation / "journal.jsonl"
    for candidate in (plan_path, journal_path, backup_root):
        _unlinked(candidate, home)
    plan_raw = _read(plan_path)
    if (
        expected_plan_sha256 is not None
        and hashlib.sha256(plan_raw).hexdigest() != expected_plan_sha256
    ):
        raise ValueError("Selected removal plan changed; refresh recovery history before retrying")
    if (
        metadata.get("plan_sha256") is not None
        and hashlib.sha256(plan_raw).hexdigest() != metadata["plan_sha256"]
    ):
        raise ValueError("Removal plan hash mismatch")
    plan = json.loads(plan_raw)
    if not isinstance(plan, list) or any(not isinstance(row, dict) for row in plan):
        raise ValueError("Invalid removal plan")
    indexed, seen_images = {}, set()
    for row in plan:
        image, caption = _relative(row.get("image")), _relative(row.get("caption"))
        image_path, caption_path = PurePosixPath(image), PurePosixPath(caption)
        if (
            image_path.suffix.lower() not in IMAGE_EXTENSIONS
            or caption_path.suffix.lower() != ".txt"
            or image_path.parent != caption_path.parent
            or image_path.stem.casefold() != caption_path.stem.casefold()
            or image.casefold() in seen_images
        ):
            raise ValueError("Removal plan has an invalid or duplicate image/caption association")
        seen_images.add(image.casefold())
        for key in ("image_sha256", "caption_sha256"):
            if row.get(key) is not None and not _hash(row[key]):
                raise ValueError("Invalid content hash in removal plan")
        indexed[image, caption] = row
    journal_raw = _read(journal_path) if journal_path.exists() else b""
    if (
        metadata.get("journal_sha256") is not None
        and hashlib.sha256(journal_raw).hexdigest() != metadata["journal_sha256"]
    ):
        raise ValueError("Removal journal hash mismatch")
    verified, removed, warnings = set(), set(), []
    lines = journal_raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                warnings.append(
                    "Incomplete final journal entry retained; using verified earlier entries"
                )
                break
            raise ValueError("Removal journal contains malformed entries") from None
        if not isinstance(event, dict):
            raise ValueError("Invalid removal journal entry")
        if event.get("event") not in {"backup_verified", "removed"}:
            raise ValueError("Unexpected event in removal journal")
        key = _relative(event.get("image")), _relative(event.get("caption"))
        row = indexed.get(key)
        if (
            row is None
            or row.get("status") != "ready"
            or not _hash(event.get("sha256"))
            or event["sha256"] != row.get("caption_sha256")
            or event.get("image_sha256") != row.get("image_sha256")
            or event.get("source") not in (None, str(source))
        ):
            raise ValueError("Removal journal does not match the saved plan")
        if event["event"] == "backup_verified":
            if key in verified:
                raise ValueError("Repeated backup identity in removal journal")
            verified.add(key)
        else:
            if key not in verified or key in removed:
                raise ValueError("Removal lacks a unique verified backup event")
            removed.add(key)
    items = []
    if verified and metadata.get("backup") != str(backup_root):
        raise ValueError("Verified backups are not bound to the removal receipt")
    for key in sorted(verified):
        row = indexed[key]
        backup = _unlinked(backup_root / row["caption"], home)
        if not backup.is_file() or backup.stat().st_size > MAX_CAPTION_BYTES:
            raise ValueError(f"Caption backup is unavailable or oversized: {backup}")
        if file_sha256(backup) != row["caption_sha256"]:
            raise ValueError(f"Caption backup hash mismatch: {backup}")
        items.append(
            {
                "image": row["image"],
                "caption": row["caption"],
                "image_sha256": row.get("image_sha256"),
                "caption_sha256": row["caption_sha256"],
                "backup": str(backup),
                "removal_journal_completed": key in removed,
            }
        )
    return {
        "source": str(source),
        "home": str(home),
        "removal_receipt": str(path),
        "inputs": {
            str(path): hashlib.sha256(raw).hexdigest(),
            str(plan_path): hashlib.sha256(plan_raw).hexdigest(),
            **(
                {str(journal_path): hashlib.sha256(journal_raw).hexdigest()}
                if journal_path.exists()
                else {}
            ),
        },
        "items": items,
        "warnings": warnings,
    }


def _status(source: Path, item: dict) -> tuple[str, str]:
    if not item["image_sha256"]:
        return "unverifiable", "Legacy receipt has no image hash; inspect and recover manually"
    try:
        image = _safe_path(source, item["image"])
        target = _safe_path(source, item["caption"])
        if not image.is_file() or file_sha256(image) != item["image_sha256"]:
            return "conflict", "Image is missing or changed since removal; destination kept"
        images, captions = _pair_entries(image, list(image.parent.iterdir()))
        if len(images) != 1 or images[0].name != image.name:
            return "conflict", "Image association is now ambiguous; destination kept"
        if target.exists() or captions:
            if (
                len(captions) == 1
                and captions[0].name == target.name
                and target.is_file()
                and file_sha256(target) == item["caption_sha256"]
            ):
                return "already_present", "Exact saved caption is already present"
            return "conflict", "A newer or ambiguous caption path exists; destination kept"
        return "ready", "Verified backup and unchanged image; caption is missing"
    except (OSError, ValueError) as exc:
        return "conflict", str(exc)


def _publish(temporary: Path, target: Path) -> None:
    if os.name == "nt":
        temporary.rename(target)
    else:
        os.link(temporary, target)
        temporary.unlink()


def _journal(directory: Path, event: dict) -> None:
    with (directory / "journal.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _execute(data: dict, *, dryrun: bool) -> dict:
    source, home = Path(data["source"]), Path(data["home"])
    result = {
        "schema_version": 1,
        "action": "restore_captions",
        **data,
        "dryrun": dryrun,
        "status": "preview" if dryrun else "running",
        "report": None,
    }
    for item in result["items"]:
        item["status"], item["reason"] = _status(source, item)
    result["counts"] = dict(Counter(item["status"] for item in result["items"]))
    if dryrun:
        return result
    directory = (
        home
        / "operations"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-restore-" + uuid4().hex[:8])
    )
    _unlinked(directory, home)
    directory.mkdir()
    result["report"] = str(directory / "restore.json")
    atomic_json(directory / "restore.json", result)
    try:
        for item in result["items"]:
            if item["status"] != "ready":
                continue
            for path, expected in data["inputs"].items():
                _unlinked(Path(path), home)
                if file_sha256(Path(path)) != expected:
                    raise ValueError("Removal evidence changed during restoration")
            backup = _unlinked(Path(item["backup"]), home)
            raw = backup.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["caption_sha256"]:
                raise ValueError("Caption backup changed during restoration")
            item["status"], item["reason"] = _status(source, item)
            if item["status"] != "ready":
                continue
            target = _safe_path(source, item["caption"])
            descriptor, name = tempfile.mkstemp(prefix=".trainime-restore-", dir=target.parent)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if file_sha256(temporary) != item["caption_sha256"]:
                    raise ValueError("Staged caption restoration failed verification")
                item["status"], item["reason"] = _status(source, item)
                if item["status"] != "ready":
                    continue
                _journal(directory, {"event": "restore_intent", **item})
                with _finish_commit():
                    try:
                        _publish(temporary, target)
                    except FileExistsError:
                        item["status"], item["reason"] = _status(source, item)
                    else:
                        item["status"], item["reason"] = (
                            "restored",
                            "Verified saved caption restored",
                        )
                        _journal(directory, {"event": "restored", **item})
            finally:
                temporary.unlink(missing_ok=True)
            result["counts"] = dict(Counter(i["status"] for i in result["items"]))
            atomic_json(directory / "restore.json", result)
        result["status"] = (
            "completed_with_conflicts"
            if any(i["status"] in {"conflict", "unverifiable"} for i in result["items"])
            else "completed"
        )
    except BaseException as exc:
        result["status"] = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
        result["error"] = str(exc) or type(exc).__name__
        result["counts"] = dict(Counter(i["status"] for i in result["items"]))
        try:
            atomic_json(directory / "restore.json", result)
        except OSError as recording_error:
            exc.add_note(f"Could not update restoration receipt: {recording_error}")
        exc.add_note(f"Caption restoration receipt: {directory / 'restore.json'}")
        raise
    result["counts"] = dict(Counter(i["status"] for i in result["items"]))
    atomic_json(directory / "restore.json", result)
    return result


def restore_captions(
    receipt: Path,
    *,
    dryrun: bool = False,
    expected_sha256: str | None = None,
    expected_plan_sha256: str | None = None,
) -> dict:
    expected = {"expected_sha256": expected_sha256, "expected_plan_sha256": expected_plan_sha256}
    data = _load(receipt, **expected)
    if dryrun:
        return _execute(data, dryrun=True)
    home = Path(data["home"])
    locks = _unlinked(home / "locks", home)
    locks.mkdir(exist_ok=True)
    key = hashlib.sha256(os.path.normcase(data["source"]).encode("utf-8")).hexdigest()
    lock = _unlinked(locks / f"{key}.lock", home)
    try:
        with FileLock(str(lock), timeout=0):
            current = _load(receipt, **expected)
            if any(current[key] != data[key] for key in ("source", "home", "inputs")):
                raise ValueError("Removal evidence changed before acquiring the source lock")
            return _execute(current, dryrun=False)
    except Timeout as exc:
        raise RuntimeError(
            "Another Trainime operation is using this directory; retry when it finishes"
        ) from exc
