"""Read and validate the immutable on-disk inventory manifest."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def _validate_row(row: object, line_number: int) -> dict:
    context = f"inventory row {line_number}"
    if not isinstance(row, dict):
        raise ValueError(f"{context} must be an object")
    if type(row.get("schema_version")) is not int or row["schema_version"] != 1:
        raise ValueError(f"{context} requires schema_version=1")
    path = row.get("source_path")
    if not isinstance(path, str) or not path or "\0" in path:
        raise ValueError(f"{context} has an invalid source path")
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in path
        or ":" in path
        or relative.as_posix() != path
    ):
        raise ValueError(f"{context} has an unsafe inventory source path: {path!r}")
    if row.get("kind") not in ("image", "sidecar", "other", "link"):
        raise ValueError(f"{context} has an invalid kind")
    if row.get("decision") not in (
        "candidate",
        "review",
        "duplicate",
        "rejected",
        "skipped",
        "error",
    ):
        raise ValueError(f"{context} has an invalid decision")
    reasons = row.get("reasons")
    if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
        raise ValueError(f"{context} requires a reasons array of strings")
    digest = row.get("sha256")
    eligible = row["kind"] == "image" and row["decision"] in ("candidate", "review", "duplicate")
    if (digest is not None or eligible) and (
        not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)
    ):
        raise ValueError(f"{context} requires a valid SHA256")
    return row


def read_inventory(directory: Path) -> tuple[dict, list[dict], str]:
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("inventory run.json must be an object")
    if (
        metadata.get("stage") != "inventory"
        or type(metadata.get("schema_version")) is not int
        or metadata["schema_version"] != 1
    ):
        raise ValueError("stage requires an inventory run with schema_version=1")
    if metadata.get("status") not in ("completed", "completed_with_errors"):
        raise ValueError("inventory is incomplete")
    source = metadata.get("source")
    if not isinstance(source, str) or "\0" in source or not Path(source).is_absolute():
        raise ValueError("inventory requires an absolute source directory path")
    raw = (directory / "manifest.jsonl").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != metadata.get("manifest_sha256"):
        raise ValueError("inventory manifest hash mismatch")
    rows = []
    seen = set()
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = _validate_row(json.loads(line), number)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"inventory row {number} contains invalid JSON") from exc
        if row["source_path"] in seen:
            raise ValueError("inventory contains duplicate source paths")
        seen.add(row["source_path"])
        rows.append(row)
    return metadata, rows, digest
