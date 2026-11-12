"""Portable package identity, independent of installation paths and dependencies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from image_dataset_train import __version__

PAYLOAD_SUFFIXES = frozenset({".py", ".html", ".js", ".txt", ".in"})


def _digest(files: dict[str, str]) -> str:
    raw = json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def validate_implementation_identity(value: object) -> None:
    """Validate recorded evidence without comparing it with today's installed build."""
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "version", "payload_sha256", "files"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["version"], str)
        or not value["version"].strip()
        or len(value["version"]) > 128
        or not isinstance(value["files"], dict)
        or not value["files"]
        or not _hash(value["payload_sha256"])
    ):
        raise ValueError("Invalid implementation identity")
    names = set()
    for name, digest in value["files"].items():
        if not isinstance(name, str):
            raise ValueError("Invalid implementation payload path")
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or "\\" in name
            or ":" in name
            or any(part in {"", ".", "..", "__pycache__"} for part in name.split("/"))
            or any(part.rstrip(". ") != part for part in path.parts)
            or any(ord(character) < 32 for character in name)
            or path.suffix not in PAYLOAD_SUFFIXES
            or name.casefold() in names
            or not _hash(digest)
        ):
            raise ValueError("Invalid implementation payload path or hash")
        names.add(name.casefold())
    if _digest(value["files"]) != value["payload_sha256"]:
        raise ValueError("Implementation payload identity hash mismatch")


def implementation_identity() -> dict:
    """Hash the exact executable/resource payload using only relative package paths."""
    package = Path(__file__).parent
    files = {}
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        if "__pycache__" in relative.parts:
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError("Linked implementation payload paths are not supported")
        if not path.is_file() or path.suffix not in PAYLOAD_SUFFIXES:
            continue
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ):
            raise ValueError("Implementation payload changed while its identity was captured")
        files[relative.as_posix()] = digest.hexdigest()
    identity = {
        "schema_version": 1,
        "version": __version__,
        "payload_sha256": _digest(files),
        "files": files,
    }
    validate_implementation_identity(identity)
    return identity
