"""Discover and interpret CPU import evidence without changing published exports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from image_dataset_train.exporting import _checked, _json, _path, verify_export
from image_dataset_train.inventory import file_sha256
from image_dataset_train.trainer import TRAINER_RELEASE, TRAINER_REPOSITORY, TRAINER_REVISION


def trainer_pin() -> dict:
    return {
        "repository": TRAINER_REPOSITORY,
        "release": TRAINER_RELEASE,
        "revision": TRAINER_REVISION,
        "requirements_sha256": file_sha256(Path(__file__).with_name("trainer-requirements.txt")),
        "scope": "cpu-dataset-import",
    }


def receipt_artifact(directory: Path, name: str) -> bytes:
    """Read only the two recorded receipt artifacts, checking their saved hashes."""
    if name not in {"result.json", "loader.log"}:
        raise ValueError("Unknown trainer receipt artifact")
    meta = _json(_path(directory, "run.json"))
    if (
        directory.name.startswith(".pending-")
        or meta.get("schema_version") != 1
        or meta.get("stage") != "trainer-check"
        or meta.get("status") not in {"completed", "failed"}
    ):
        raise ValueError("Expected a published trainer receipt")
    return _checked(directory, name, meta["files"][name])


def trainer_status(export: Path, runs: Path, *, expected_export_sha256: str | None = None) -> dict:
    """Report the latest exact-export, current-pin result plus associated history.

    Content hashes allow relocated copies to retain their evidence. Same-path
    receipts for different bytes are visible as stale, never applied to this export.
    """
    export, runs = export.resolve(), runs.resolve()
    pin = trainer_pin()
    status = {
        "status": "not_checked",
        "export": str(export),
        "receipt_root": str(runs),
        "checked_at": datetime.now(UTC).isoformat(),
        "pin": pin,
        "verification": None,
        "receipts": [],
        "discovery_errors": [],
        "latest_receipt": None,
    }
    try:
        export_hash = file_sha256(export / "run.json")
        if expected_export_sha256 and export_hash != expected_export_sha256:
            raise ValueError("Export metadata changed since this QA snapshot")
        status["verification"] = verify_export(export)
        manifest_hash = file_sha256(export / "manifest.jsonl")
    except (ValueError, OSError) as exc:
        return {**status, "status": "export_invalid", "error": str(exc)}

    status["export_run_sha256"] = export_hash
    status["export_manifest_sha256"] = manifest_hash
    candidates = []
    for directory in sorted(runs.iterdir()) if runs.exists() else []:
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if not (directory / "run.json").exists():
            continue
        is_receipt = "-trainer-" in directory.name
        try:
            meta = _json(_path(directory, "run.json"))
            if meta.get("stage") != "trainer-check":
                continue
            is_receipt = True
            # Read identity before checking hashes so damaged associated receipts
            # can be shown as invalid instead of disappearing from the history.
            result = _json(_path(directory, "result.json"))
            exact = (
                result.get("export_run_sha256") == export_hash
                and result.get("export_manifest_sha256") == manifest_hash
            )
            same_path = (
                isinstance(result.get("export"), str) and Path(result["export"]).resolve() == export
            )
            if not exact and not same_path:
                continue
            current_pin = all(
                result.get(key) == pin[key]
                for key in ("repository", "revision", "requirements_sha256", "scope")
            )
            item = {
                "id": directory.name,
                "path": str(directory),
                "completed_at": meta.get("completed_at"),
                "exact_export": exact,
                "current_pin": current_pin,
                "result": result,
                "integrity": False,
            }
            timestamp = datetime.min.replace(tzinfo=UTC)
            try:
                timestamp = datetime.fromisoformat(meta["completed_at"])
                if timestamp.tzinfo is None:
                    raise ValueError("Receipt completion time needs a timezone")
                for name in ("result.json", "loader.log"):
                    receipt_artifact(directory, name)
                if type(result.get("qualified")) is not bool or meta["status"] != (
                    "completed" if result["qualified"] else "failed"
                ):
                    raise ValueError("Receipt outcome does not match its publication status")
                if result.get("training_step_executed") is not False:
                    raise ValueError("Receipt does not describe a dataset-only import")
                item["integrity"] = True
                item["status"] = (
                    "stale"
                    if not exact
                    else "other_pin"
                    if not current_pin
                    else "passed"
                    if result["qualified"]
                    else "failed"
                )
            except (ValueError, OSError, KeyError, TypeError) as exc:
                item.update(status="invalid", error=str(exc))
                # Unknown chronology must not allow an older pass to win.
                if timestamp.tzinfo is None or timestamp == datetime.min.replace(tzinfo=UTC):
                    timestamp = datetime.max.replace(tzinfo=UTC)
            candidates.append((timestamp, item))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            if is_receipt:
                status["discovery_errors"].append({"path": str(directory), "error": str(exc)})
    candidates.sort(key=lambda row: (row[0], row[1]["id"]), reverse=True)
    status["receipts"] = [item for _, item in candidates]
    applicable = [item for _, item in candidates if item["exact_export"] and item["current_pin"]]
    if applicable:
        status.update(status=applicable[0]["status"], latest_receipt=applicable[0]["id"])
    elif candidates:
        status["status"] = "no_current_receipt"
    if status["discovery_errors"]:
        status["status"] = "history_incomplete"
    return status
