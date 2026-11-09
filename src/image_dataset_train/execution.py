"""Measured stage work and portable receipts, independent of source availability."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

# Excluding these final presentation files avoids self-referential size/timing claims.
REPORT_FILES = {"run.json", "summary.json", "report.html"}


class RunClock:
    def __init__(self) -> None:
        self.started_at = datetime.now(UTC).isoformat()
        self.started = perf_counter()

    def measure(self, root: Path, *, scope: str = "stage_processing") -> dict:
        files = [
            p
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).as_posix() not in REPORT_FILES
        ]
        size = sum(p.stat().st_size for p in files)
        return {
            "started_at": self.started_at,
            "measured_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": max(0.0, perf_counter() - self.started),
            "timing_scope": scope,
            "payload_bytes": size,
            "payload_files": len(files),
            "excluded_root_files": sorted(REPORT_FILES),
        }


def processing_history(*metadata: dict | None) -> list[dict]:
    """Each referenced invocation appears once, even when two branches share intake."""
    receipts = {}
    for meta in metadata:
        if not meta:
            continue
        current = {key: meta.get(key) for key in ("run_id", "stage", "status", "metrics")}
        for item in [*meta.get("processing_history", []), current]:
            if item.get("run_id") and item.get("stage"):
                receipts.setdefault((item["stage"], item["run_id"]), item)
    return list(receipts.values())


def membership_digest(rows) -> str:
    identities = sorted((r["source_path"], r["sha256"]) for r in rows)
    return hashlib.sha256(json.dumps(identities, separators=(",", ":")).encode()).hexdigest()


def intake_counts(rows) -> dict:
    rows = list(rows)
    images = [r for r in rows if r["kind"] == "image"]
    eligible = [r for r in images if r["decision"] in {"candidate", "review", "duplicate"}]
    known = [r for r in rows if isinstance(r.get("size_bytes"), int)]
    return {
        "files": len(rows),
        "kinds": dict(sorted(Counter(r["kind"] for r in rows).items())),
        "images": len(images),
        "image_decisions": dict(sorted(Counter(r["decision"] for r in images).items())),
        "eligible_images": len(eligible),
        "ineligible_images": len(images) - len(eligible),
        "eligible_membership_sha256": membership_digest(eligible),
        "source_bytes": sum(r["size_bytes"] for r in known),
        "source_image_bytes": sum(r.get("size_bytes") or 0 for r in images),
        "files_without_size": len(rows) - len(known),
    }


def processing_report(receipts: list[dict], expected: set[str]) -> dict:
    missing = sorted(expected - {r["stage"] for r in receipts})
    measured = [r for r in receipts if r.get("metrics") is not None]
    return {
        "stages": receipts,
        "missing_stages": missing,
        "unmeasured_runs": [r["run_id"] for r in receipts if r.get("metrics") is None],
        "partial_scope_runs": [
            r["run_id"] for r in measured if r["metrics"]["timing_scope"] != "stage_processing"
        ],
        "recorded_processing_seconds": sum(r["metrics"]["elapsed_seconds"] for r in measured),
        "recorded_payload_bytes": sum(r["metrics"]["payload_bytes"] for r in measured),
        "recorded_payload_files": sum(r["metrics"]["payload_files"] for r in measured),
        "excluded_root_files": sorted(REPORT_FILES),
    }
