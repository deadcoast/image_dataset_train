"""Discover and interpret CPU import evidence without changing published exports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from image_dataset_train.exporting import _checked, _path, _rows, _verify_export
from image_dataset_train.implementation import validate_implementation_identity
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


class _ReadSet:
    """Keep identities for the exact bytes inspected, then reject observed drift."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.hashes: dict[str, str] = {}
        self.streamed: set[str] = set()
        self.membership: set[str] | None = None

    def read(self, name: str) -> bytes:
        raw = _path(self.directory, name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if name in self.hashes and self.hashes[name] != digest:
            raise ValueError(f"Trainer evidence changed during inspection: {name}; refresh again")
        self.hashes[name] = digest
        return raw

    def object(self, name: str) -> dict:
        value = json.loads(self.read(name))
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object: {name}")
        return value

    def verify(self) -> None:
        # Payloads first, then parsed result/manifest, and controlling metadata last.
        # This catches metadata changed while the potentially large payload is read.
        ordered = sorted(
            self.hashes,
            key=lambda name: (
                {"result.json": 1, "manifest.jsonl": 2, "run.json": 3}.get(name, 0),
                name,
            ),
        )
        for name in ordered:
            digest = self.hashes[name]
            try:
                if name == "run.json" and self.membership is not None:
                    current = set()
                    for path in self.directory.rglob("*"):
                        if path.is_symlink() or path.is_junction():
                            raise ValueError("Linked file in export")
                        if path.is_file():
                            current.add(path.relative_to(self.directory).as_posix())
                    if current != self.membership:
                        raise ValueError("Export file membership changed")
                if name in self.streamed:
                    if file_sha256(_path(self.directory, name)) != digest:
                        raise ValueError(f"Export file hash mismatch: {name}")
                else:
                    _checked(self.directory, name, digest)
            except (ValueError, OSError) as exc:
                raise ValueError(
                    f"Trainer evidence changed during inspection: {name}; refresh again"
                ) from exc

    def verify_controls(self) -> None:
        """Finish cross-artifact inspection with the small export identity controls."""
        for name in ("manifest.jsonl", "run.json"):
            try:
                _checked(self.directory, name, self.hashes[name])
            except (ValueError, OSError) as exc:
                raise ValueError(
                    f"Trainer evidence changed during inspection: {name}; refresh again"
                ) from exc


def _receipt_metadata(snapshot: _ReadSet) -> dict:
    meta = snapshot.object("run.json")
    if (
        snapshot.directory.name.startswith(".pending-")
        or meta.get("schema_version") != 1
        or meta.get("stage") != "trainer-check"
        or meta.get("status") not in {"completed", "failed"}
    ):
        raise ValueError("Expected a published trainer receipt")
    if "implementation" in meta:
        validate_implementation_identity(meta["implementation"])
    return meta


def _receipt_payload(snapshot: _ReadSet, meta: dict, result: dict, raw_result: bytes) -> dict:
    payload = {"result.json": raw_result, "loader.log": snapshot.read("loader.log")}
    for name, raw in payload.items():
        if hashlib.sha256(raw).hexdigest() != meta["files"][name]:
            raise ValueError(f"Artifact hash mismatch: {name}")
    if "implementation" in result:
        validate_implementation_identity(result["implementation"])
    if result.get("implementation") != meta.get("implementation"):
        raise ValueError("Trainer receipt implementation identity differs from its result")
    return payload


def receipt_artifact(
    directory: Path, name: str, *, expected_receipt_sha256: str | None = None
) -> bytes:
    """Read a coherent receipt, optionally pinned to a previously displayed snapshot."""
    if name not in {"result.json", "loader.log"}:
        raise ValueError("Unknown trainer receipt artifact")
    snapshot = _ReadSet(directory)
    try:
        meta = _receipt_metadata(snapshot)
        if (
            expected_receipt_sha256 is not None
            and snapshot.hashes["run.json"] != expected_receipt_sha256
        ):
            raise ValueError(
                "Trainer receipt changed since it was displayed; refresh trainer status"
            )
        raw = snapshot.read("result.json")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Trainer receipt result must be a JSON object")
        payload = _receipt_payload(snapshot, meta, result, raw)
        snapshot.verify()
        return payload[name]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed trainer receipt: {exc}") from exc


def _export_snapshot(directory: Path, expected: str | None) -> tuple[_ReadSet, dict]:
    snapshot = _ReadSet(directory)
    meta = snapshot.object("run.json")
    if expected is not None and snapshot.hashes["run.json"] != expected:
        raise ValueError("Export metadata changed since this QA snapshot")
    if (
        meta.get("schema_version") != 1
        or meta.get("stage") != "export"
        or meta.get("status") not in {"completed", "completed_with_errors"}
        or directory.name.startswith(".pending-")
    ):
        raise ValueError("Expected a published export run")
    manifest = None
    for name, digest in meta["files"].items():
        raw = snapshot.read(name)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Artifact hash mismatch: {name}")
        if name == "manifest.jsonl":
            manifest = raw
    # The verifier receives the captured metadata, rather than reopening run.json.
    verification = _verify_export(directory, meta)
    for row in _rows(manifest):
        for name, digest in (
            (row["image_path"], row["image_sha256"]),
            (row["caption_path"], row["caption_sha256"]),
        ):
            snapshot.hashes[name] = digest
            snapshot.streamed.add(name)
    snapshot.membership = set(snapshot.hashes)
    snapshot.verify()
    return snapshot, verification


def _export_invalid(status: dict, error: Exception) -> dict:
    result = {
        **status,
        "status": "export_invalid",
        "error": str(error),
        "verification": None,
        "receipts": [],
        "latest_receipt": None,
    }
    for name in ("export_run_sha256", "export_manifest_sha256"):
        result.pop(name, None)
    return result


def _directories(runs: Path) -> list[Path]:
    return (
        sorted(
            directory
            for directory in runs.iterdir()
            if directory.is_dir()
            and not directory.name.startswith(".")
            and (directory / "run.json").exists()
        )
        if runs.exists()
        else []
    )


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
        export_snapshot, status["verification"] = _export_snapshot(export, expected_export_sha256)
        export_hash = export_snapshot.hashes["run.json"]
        manifest_hash = export_snapshot.hashes["manifest.jsonl"]
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        return _export_invalid(status, exc)

    status["export_run_sha256"] = export_hash
    status["export_manifest_sha256"] = manifest_hash
    candidates = []
    snapshots = []
    try:
        directories = _directories(runs)
    except OSError as exc:
        directories = []
        status["discovery_errors"].append({"path": str(runs), "error": str(exc)})
    for directory in directories:
        snapshot = _ReadSet(directory)
        snapshots.append((snapshot, directory))
        is_receipt = "-trainer-" in directory.name
        try:
            meta = snapshot.object("run.json")
            if meta.get("stage") != "trainer-check":
                continue
            is_receipt = True
            # Read identity before checking hashes so damaged associated receipts
            # can be shown as invalid instead of disappearing from the history.
            raw_result = snapshot.read("result.json")
            result = json.loads(raw_result)
            if not isinstance(result, dict):
                raise ValueError("Trainer receipt result must be a JSON object")
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
                "receipt_run_sha256": snapshot.hashes["run.json"],
                "receipt_result_sha256": snapshot.hashes["result.json"],
            }
            timestamp = datetime.min.replace(tzinfo=UTC)
            try:
                timestamp = datetime.fromisoformat(meta["completed_at"])
                if timestamp.tzinfo is None:
                    raise ValueError("Receipt completion time needs a timezone")
                # Validate publication and artifacts from the already captured bytes.
                if meta.get("schema_version") != 1 or meta.get("status") not in {
                    "completed",
                    "failed",
                }:
                    raise ValueError("Expected a published trainer receipt")
                if "implementation" in meta:
                    validate_implementation_identity(meta["implementation"])
                _receipt_payload(snapshot, meta, result, raw_result)
                snapshot.verify()
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
    # Finish the expensive media pass before the final receipt/history checks.
    # A receipt can be published or replaced while those export bytes are hashed.
    try:
        export_snapshot.verify()
    except (ValueError, OSError) as exc:
        return _export_invalid(status, exc)
    for snapshot, directory in snapshots:
        try:
            snapshot.verify()
        except (ValueError, OSError) as exc:
            for _, item in candidates:
                if item["path"] == str(directory):
                    item.update(status="invalid", integrity=False, error=str(exc))
            status["discovery_errors"].append({"path": str(directory), "error": str(exc)})
    try:
        if _directories(runs) != directories:
            raise ValueError("Trainer receipt history changed during inspection; refresh again")
    except (ValueError, OSError) as exc:
        status["discovery_errors"].append({"path": str(runs), "error": str(exc)})
    try:
        export_snapshot.verify_controls()
    except (ValueError, OSError) as exc:
        return _export_invalid(status, exc)
    candidates.sort(key=lambda row: (row[0], row[1]["id"]), reverse=True)
    status["receipts"] = [item for _, item in candidates]
    applicable = [item for _, item in candidates if item["exact_export"] and item["current_pin"]]
    if applicable:
        status.update(status=applicable[0]["status"], latest_receipt=applicable[0]["id"])
    elif candidates:
        status["status"] = "no_current_receipt"
    if status["discovery_errors"]:
        status["status"] = "history_incomplete"
        status["latest_receipt"] = None
    return status
