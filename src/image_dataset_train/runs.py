"""Publish complete inventory reports in a new directory per invocation."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import __version__ as pillow_version

from image_dataset_train import __version__
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import publish_directory
from image_dataset_train.execution import RunClock, intake_counts
from image_dataset_train.inventory import Record, scan, summarize


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def run_scan(config: Config, progress: Callable[[int], None] | None = None) -> tuple[Path, dict]:
    clock = RunClock()
    return publish_scan(config, scan(config.source, config.validation, progress), clock=clock)


def publish_scan(
    config: Config, records: list[Record], *, clock: RunClock | None = None
) -> tuple[Path, dict]:
    """Publish an already inspected inventory without decoding the collection twice."""
    scope = "stage_processing" if clock is not None else "inventory_publication_only"
    clock = clock or RunClock()
    source = config.source.resolve(strict=True)
    runs = config.runs.resolve()
    if not source.is_dir():
        raise ValueError(f"source must be a directory: {source}")
    if source.is_relative_to(runs) or runs.is_relative_to(source):
        raise ValueError("source and runs must be separate directory trees")

    started = datetime.now(UTC)
    summary = summarize(records)
    manifest = "".join(
        json.dumps(asdict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in records
    )
    manifest_bytes = manifest.encode("utf-8")
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "stage": "inventory",
        "status": "completed_with_errors" if summary["decisions"].get("error") else "completed",
        "started_at": clock.started_at,
        "source": str(source),
        "validation": asdict(config.validation),
        "pipeline_version": __version__,
        "python_version": platform.python_version(),
        "pillow_version": pillow_version,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "intake": intake_counts(asdict(row) for row in records),
    }
    runs.mkdir(parents=True, exist_ok=True)
    # An interrupted staging directory is not a published run. Never replace an old run.
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=runs))
    (staging / "manifest.jsonl").write_bytes(manifest_bytes)
    (staging / "summary.json").write_text(_json(summary), encoding="utf-8", newline="\n")
    metadata["metrics"] = clock.measure(staging, scope=scope)
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    (staging / "run.json").write_text(_json(metadata), encoding="utf-8", newline="\n")
    final = runs / run_id
    publish_directory(staging, final)
    return final, summary
