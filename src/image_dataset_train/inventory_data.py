"""Read and validate the immutable on-disk inventory manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def read_inventory(directory: Path) -> tuple[dict, list[dict], str]:
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if metadata.get("stage") != "inventory" or metadata.get("schema_version") != 1:
        raise ValueError("stage requires an inventory run with schema_version=1")
    if metadata.get("status") not in {"completed", "completed_with_errors"}:
        raise ValueError("inventory is incomplete")
    raw = (directory / "manifest.jsonl").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != metadata.get("manifest_sha256"):
        raise ValueError("inventory manifest hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    paths = [row.get("source_path") for row in rows]
    if any(not isinstance(path, str) for path in paths) or len(set(paths)) != len(paths):
        raise ValueError("inventory contains invalid or duplicate source paths")
    return metadata, rows, digest
