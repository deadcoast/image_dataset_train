"""Recover the wheel's package payload without replacing a running launcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from image_dataset_train.diagnostics import app_home, atomic_json

PACKAGE = "image_dataset_train"
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 2048
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_path(target: Path, boundary: Path) -> None:
    if not target.is_relative_to(boundary):
        raise ValueError("Repair path escapes the installed package.")
    for part in (target, *target.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked package or recovery path cannot be repaired in place.")
        if part != target and part.exists() and not part.is_dir():
            raise ValueError("Repair parent path is not a directory.")
        if part == boundary:
            break
    if not target.resolve().is_relative_to(boundary.resolve()):
        raise ValueError("Repair path escapes the installed package.")


def _payload(wheel: Path) -> list[tuple[PurePosixPath, bytes]]:
    """Read/CRC-check the complete bounded payload before changing installed files."""
    result, names, total = [], set(), 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            # ZipInfo normalizes backslashes on Windows; inspect the original name too.
            name = member.orig_filename
            relative = PurePosixPath(name)
            if not relative.parts or relative.parts[0] != PACKAGE:
                continue
            parts = name.rstrip("/").split("/")
            mode = stat.S_IFMT(member.external_attr >> 16)
            if (
                relative.is_absolute()
                or any(p in {"", ".", ".."} for p in parts)
                or "\\" in name
                or ":" in name
                or any(ord(char) < 32 for char in name)
                or any(p.rstrip(". ") != p for p in parts)
                or any(p.split(".")[0].upper() in WINDOWS_RESERVED for p in parts)
                or mode not in {0, stat.S_IFREG, stat.S_IFDIR}
                or not 0 <= member.file_size <= MAX_MEMBER_BYTES
            ):
                raise ValueError("Invalid application file in repair wheel.")
            key = relative.as_posix().casefold()
            if key in names:
                raise ValueError("Duplicate application path in repair wheel.")
            names.add(key)
            if member.is_dir():
                continue
            total += member.file_size
            if len(result) >= MAX_MEMBERS or total > MAX_PAYLOAD_BYTES:
                raise ValueError("Repair wheel application payload exceeds the size limit.")
            raw = archive.read(member)
            if len(raw) != member.file_size:
                raise ValueError("Repair wheel member size mismatch.")
            result.append((relative, raw))
    if not any(p.as_posix() == f"{PACKAGE}/bootstrap.py" for p, _ in result):
        raise ValueError("Repair wheel does not contain Trainime's startup module.")
    files = {p.as_posix().casefold() for p, _ in result}
    if any(parent.as_posix().casefold() in files for p, _ in result for parent in p.parents):
        raise ValueError("Repair wheel has overlapping file and directory paths.")
    return sorted(result, key=lambda item: item[0].as_posix())


def _journal(directory: Path, event: str, **values) -> None:
    with (directory / "journal.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"event": event, **values}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def inspect_payload(wheel: Path, site_packages: Path) -> list[dict[str, str]]:
    """Compare only wheel-owned files; never classify unowned files as damage."""
    root = site_packages.resolve(strict=True) / PACKAGE
    _check_path(root, root.parent)
    issues = []
    for relative, raw in _payload(wheel):
        target = root.parent.joinpath(*relative.parts)
        _check_path(target, root)
        if not target.exists():
            issues.append({"path": relative.as_posix(), "problem": "missing"})
        elif not target.is_file() or _sha(target.read_bytes()) != _sha(raw):
            issues.append({"path": relative.as_posix(), "problem": "modified"})
    return issues


def _write_backup(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _sha(path.read_bytes()) != _sha(raw):
        raise ValueError("Application backup verification failed; installed file kept.")


def _publish(temporary: Path, target: Path, *, existed: bool) -> None:
    if existed:
        os.replace(temporary, target)
    elif os.name == "nt":
        temporary.rename(target)  # Exclusive on Windows: keep a raced new file.
    else:
        os.link(temporary, target)  # POSIX rename would overwrite a raced new file.
        temporary.unlink()


def restore(wheel: Path, site_packages: Path) -> int:
    """Restore package resources with verified backups and an interruption receipt.

    The installer serializes repairs. Stop other writers to the installed package;
    portable checks cannot make hostile external edits transactional.
    """
    site_packages = site_packages.resolve(strict=True)
    root = site_packages / PACKAGE
    _check_path(root, site_packages)
    wheel_bytes = wheel.read_bytes()
    payload = _payload(wheel)
    if _sha(wheel.read_bytes()) != _sha(wheel_bytes):
        raise ValueError("Repair wheel changed during inspection.")
    plan = []
    for relative, raw in payload:
        target = site_packages.joinpath(*relative.parts)
        _check_path(target, root)
        if target.exists() and not target.is_file():
            raise ValueError(f"Installed package path is not a regular file: {target}")
        before = target.read_bytes() if target.exists() else None
        if before != raw:
            plan.append((relative, raw, before))
    if not plan:
        return 0

    home = app_home().resolve()
    recovery = home / "recovery" / "application"
    _check_path(recovery, home)
    if recovery.is_relative_to(root) or root.is_relative_to(recovery):
        raise ValueError("Package and application recovery must be separate directory trees.")
    directory = recovery / uuid4().hex
    directory.mkdir(parents=True)
    receipt = {
        "schema_version": 1,
        "action": "repair_package",
        "status": "running",
        "wheel": str(wheel.resolve()),
        "wheel_sha256": _sha(wheel_bytes),
        "site_packages": str(site_packages),
        "started_at": datetime.now(UTC).isoformat(),
        "restored": 0,
        "files": [
            {
                "path": relative.as_posix(),
                "before_sha256": _sha(before) if before is not None else None,
                "expected_sha256": _sha(raw),
                "backup": relative.as_posix() if before is not None else None,
                "status": "pending",
            }
            for relative, raw, before in plan
        ],
    }
    atomic_json(directory / "repair.json", receipt)
    try:
        for (relative, raw, before), entry in zip(plan, receipt["files"], strict=True):
            target = site_packages.joinpath(*relative.parts)
            _check_path(target, root)
            if (target.read_bytes() if target.exists() else None) != before:
                raise ValueError(f"Installed package file changed after inspection: {target}")
            if before is not None:
                backup = directory.joinpath(*relative.parts)
                _journal(directory, "backup_intent", **entry)
                _write_backup(backup, before)
                _journal(directory, "backup_verified", **entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".repair-", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if _sha(temporary.read_bytes()) != entry["expected_sha256"]:
                    raise ValueError("Staged application file failed verification.")
                _check_path(target, root)
                if (target.read_bytes() if target.exists() else None) != before:
                    raise ValueError(f"Installed package file changed during backup: {target}")
                _journal(directory, "replace_intent", **entry)
                _publish(temporary, target, existed=before is not None)
                if _sha(target.read_bytes()) != entry["expected_sha256"]:
                    raise ValueError(f"Restored application file failed verification: {target}")
                entry["status"] = "restored"
                receipt["restored"] += 1
                _journal(directory, "restored", **entry)
                atomic_json(directory / "repair.json", receipt)
            finally:
                temporary.unlink(missing_ok=True)
        receipt["status"] = "completed"
    except BaseException as exc:
        receipt["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        receipt["error"] = str(exc) or type(exc).__name__
        exc.add_note(f"Application recovery receipt: {directory / 'repair.json'}")
        try:
            atomic_json(directory / "repair.json", receipt)
        except OSError as recording_error:
            exc.add_note(f"Could not update recovery receipt: {recording_error}")
        raise
    receipt["completed_at"] = datetime.now(UTC).isoformat()
    atomic_json(directory / "repair.json", receipt)
    return receipt["restored"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("site_packages", type=Path)
    args = parser.parse_args()
    print(f"Restored {restore(args.wheel, args.site_packages)} application files.")
    print(f"Recovery receipts: {app_home() / 'recovery' / 'application'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
