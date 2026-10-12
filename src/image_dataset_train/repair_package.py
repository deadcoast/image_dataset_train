"""Restore this package's exact Python files without replacing a running launcher."""

from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from image_dataset_train.diagnostics import app_home


def restore(wheel: Path, site_packages: Path) -> int:
    root = site_packages.resolve(strict=True) / "image_dataset_train"
    if root.is_symlink() or root.is_junction():
        raise ValueError(
            "Package directory is a link; run install.cmd to create a clean installation."
        )
    restored = 0
    backup_root = app_home() / "recovery" / "application" / uuid4().hex
    with zipfile.ZipFile(wheel) as archive:
        members = []
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if not relative.parts or relative.parts[0] != "image_dataset_train":
                continue
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.filename
                or ":" in member.filename
                or member.file_size > 5 * 1024 * 1024
            ):
                raise ValueError("Invalid application file in repair wheel.")
            if not member.is_dir() and relative.suffix == ".py":
                members.append((member, relative))
        if not members or not any(p.name == "bootstrap.py" for _, p in members):
            raise ValueError("Repair wheel does not contain Trainime's startup module.")
        for member, relative in members:
            target = site_packages.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(root):
                raise ValueError("Repair path escapes the installed package.")
            for parent in (target, *target.parents):
                if parent == site_packages:
                    break
                if parent.is_symlink() or parent.is_junction():
                    raise ValueError("Linked package file cannot be repaired in place.")
            raw = archive.read(member)  # ZIP CRC is checked before any replacement.
            if target.exists():
                previous = target.read_bytes()
                if previous == raw:
                    continue
                backup = backup_root.joinpath(*relative.parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(previous)
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".repair-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            restored += 1
    return restored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("site_packages", type=Path)
    args = parser.parse_args()
    print(f"Restored {restore(args.wheel, args.site_packages)} application files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
