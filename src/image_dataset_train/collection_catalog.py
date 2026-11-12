"""Metadata-only run discovery within explicitly registered preparation collections."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from image_dataset_train.collection_registry import (
    path_key,
    read_object,
    unlinked_path,
    validate_entry,
)
from image_dataset_train.preparation import read_preparation_job
from image_dataset_train.reviews import ReviewStore


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _hash(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _identifier(path: Path, checksum: str) -> str:
    return _digest({"path": path_key(path), "run_sha256": checksum})


def _date(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid artifact timestamp")
    try:
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Artifact timestamp must include a timezone") from exc
    return value


def _children(path: Path, errors: list, *, missing_ok: bool = False) -> list[Path]:
    try:
        path = unlinked_path(path)
        if not path.exists() and missing_ok:
            return []
        if not path.is_dir():
            raise ValueError("Registered metadata directory is unavailable")
        children = []
        for child in sorted(path.iterdir()):
            try:
                unlinked_path(child)
                if child.is_dir():
                    children.append(child)
            except (OSError, ValueError) as exc:
                errors.append({"path": str(child), "error": str(exc)})
        return children
    except (OSError, ValueError) as exc:
        errors.append({"path": str(path), "error": str(exc)})
        return []


def _run(
    path: Path, source: str, *, job_id=None, config_path=None, config_sha256=None, ownership=None
) -> dict | None:
    path = unlinked_path(path)
    metadata, checksum = read_object(path / "run.json")
    if metadata.get("source") is not None and (
        not isinstance(metadata["source"], str) or not Path(metadata["source"]).is_absolute()
    ):
        raise ValueError("Invalid run source identity")
    if metadata.get("source") is not None and path_key(metadata["source"]) != path_key(source):
        return None
    if (
        metadata.get("schema_version") != 1
        or not isinstance(metadata.get("stage"), str)
        or not isinstance(metadata.get("status"), str)
        or not isinstance(metadata.get("files", {}), dict)
    ):
        raise ValueError("Invalid published run metadata")
    if metadata.get("stage") != "trainer-check" and metadata.get("source") is None:
        raise ValueError("Run metadata has no source identity")
    config_path = str(config_path) if config_path else metadata.get("config_path")
    if config_path is not None and (
        not isinstance(config_path, str) or not Path(config_path).is_absolute()
    ):
        raise ValueError("Run config locator must be an absolute path")
    input_fields = (
        "input_run",
        "input_run_sha256",
        "inventory_run",
        "inventory_manifest_sha256",
        "groups_run",
        "groups_run_sha256",
        "caption_run",
        "caption_run_sha256",
        "similarity_run",
        "similarity_run_sha256",
        "review_revision",
        "inputs",
    )
    return {
        "id": _identifier(path, checksum),
        "path": str(path),
        "run_sha256": checksum,
        "source": source,
        "stage": metadata["stage"],
        "status": metadata["status"],
        "created_at": _date(
            metadata.get("created_at") or metadata.get("started_at") or metadata.get("completed_at")
        ),
        "input": {key: metadata[key] for key in input_fields if key in metadata},
        "job_id": job_id,
        "ownership": ownership,
        "config_path": config_path,
        "config_sha256": config_sha256,
        "metadata_verification": "metadata_only",
        "manifest_sha256": metadata.get("files", {}).get("manifest.jsonl"),
    }


def _publication(path: Path, source: str, roots: set[str]) -> dict | None:
    document, checksum = read_object(path)
    binding = document.get("binding", {})
    if not isinstance(binding, dict):
        raise ValueError("Invalid publication binding")
    if path_key(binding.get("source", "")) != path_key(source):
        return None
    if (
        document.get("schema_version") != 1
        or not isinstance(document.get("attempts"), list)
        or not _hash(binding.get("report_sha256"))
        or not isinstance(binding.get("report"), str)
        or not Path(binding["report"]).is_absolute()
        or path.parent.name != _digest(binding)
    ):
        raise ValueError("Invalid publication job identity")
    attempts, identifiers = [], set()
    for attempt in document["attempts"]:
        if not isinstance(attempt, dict):
            raise ValueError("Invalid publication attempt")
        identifier = attempt.get("id", "")
        request = attempt.get("request")
        if (
            not isinstance(identifier, str)
            or len(identifier) != 32
            or any(c not in "0123456789abcdef" for c in identifier)
            or identifier in identifiers
            or not isinstance(request, dict)
            or attempt.get("fingerprint") != _digest(request)
            or path_key(request.get("source", "")) != path_key(source)
            or request.get("mode") not in {"groups", "export"}
            or attempt.get("status") not in {"running", "failed", "completed"}
            or not isinstance(attempt.get("outputs"), dict)
            or not isinstance(request.get("destinations"), dict)
        ):
            raise ValueError("Invalid publication attempt contract")
        identifiers.add(identifier)
        destinations = request["destinations"]
        if any(
            not isinstance(destinations.get(name), str) or path_key(destinations[name]) not in roots
            for name in ("runs", "exports")
        ):
            raise ValueError("Publication destinations are outside registered collection roots")
        attempts.append(
            {
                "id": identifier,
                "status": attempt["status"],
                "started_at": attempt.get("started_at"),
                "finished_at": attempt.get("finished_at"),
                "error": attempt.get("error"),
                "reused_stages": attempt.get("reused_stages", []),
                "request": request,
                "outputs": attempt["outputs"],
            }
        )
    return {
        "path": str(path),
        "sha256": checksum,
        "binding": binding,
        "attempts": attempts,
        "metadata_verification": "metadata_only",
        "process_liveness": "unknown",
    }


def collection_snapshot(entry: dict) -> dict:
    """Inspect known artifact layouts, never source images, live workers or model caches."""
    validate_entry(entry)
    source, workspace = entry["source"], Path(entry["workspace"])
    result = {
        "collection": dict(entry),
        "current_job_id": None,
        "current_review_revision": None,
        "review_revisions": [],
        "jobs": [],
        "runs": [],
        "publications": [],
        "errors": [],
        "source_revalidated": False,
        "registered_roots": {"runs": [], "exports": [], "reviews": []},
        "unavailable_roots": [],
        "artifact_verification": "metadata_only",
    }
    errors = result["errors"]
    roots, review_roots, candidates = {}, set(), {}
    typed_roots = {"runs": set(), "exports": set(), "reviews": set()}
    current_review_root = None

    def error(path, exc):
        errors.append({"path": str(path), "error": str(exc)})

    def candidate(path, **context):
        try:
            path = unlinked_path(path)
            if path.name.startswith(".pending-"):
                return
            if (path / "run.json").exists():
                candidates.setdefault(path_key(path), (path, context))
        except (OSError, ValueError) as exc:
            error(path, exc)

    try:
        workspace = unlinked_path(workspace)
        _, current = read_preparation_job(workspace)
        if path_key(current["source"]) != path_key(source):
            raise ValueError("Registered collection source differs from its workspace")
        result["current_job_id"] = current["job_id"]
        current_review_root = current["settings"]["reviews"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error(workspace, exc)
    for job in _children(workspace / "jobs", errors):
        try:
            _, state = read_preparation_job(workspace, job_id=job.name)
            if path_key(state["source"]) != path_key(source):
                raise ValueError("Historical job belongs to another source")
            created_at, updated_at = _date(state["created_at"]), _date(state["updated_at"])
            if created_at is None or updated_at is None:
                raise ValueError("Preparation job timestamps are required")
            config = job / "config.toml"
            result["jobs"].append(
                {
                    "id": state["job_id"],
                    "path": str(job),
                    "source": source,
                    "status": state["status"],
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "current_stage": state.get("current_stage"),
                    "next_action": state.get("next_action"),
                    "error": state.get("error"),
                    "current": state["job_id"] == result["current_job_id"],
                    "config_path": str(config),
                    "metadata_verification": "job_contract",
                }
            )
            for key in ("runs", "exports"):
                root = unlinked_path(Path(state["settings"][key]))
                if root.is_relative_to(Path(source)) or Path(source).is_relative_to(root):
                    raise ValueError("Artifact root overlaps source images")
                roots.setdefault(path_key(root), root)
                typed_roots[key].add(str(root))
            review_root = unlinked_path(Path(state["settings"]["reviews"]))
            if review_root.is_relative_to(Path(source)) or Path(source).is_relative_to(review_root):
                raise ValueError("Review root overlaps source images")
            review_roots.add(str(review_root))
            typed_roots["reviews"].add(str(review_root))
            context = {
                "job_id": job.name,
                "config_path": config,
                "config_sha256": state["config_sha256"],
                "ownership": "preparation",
            }
            # Inspect attempts even if a crash prevented the final checkpoint.
            for attempt in _children(job / "attempts", errors, missing_ok=True):
                for directory in (attempt / "runs", attempt / "exports"):
                    for published in _children(directory, errors, missing_ok=True):
                        candidate(published, **context)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error(job, exc)
    result["registered_roots"] = {key: sorted(paths) for key, paths in typed_roots.items()}
    for root in roots.values():
        if not root.exists():
            result["unavailable_roots"].append(str(root))
        for published in _children(root, errors, missing_ok=True):
            candidate(published, ownership="configured_root")
    for review_root in sorted(review_roots):
        try:
            review_root = unlinked_path(Path(review_root))
            try:
                state = ReviewStore(review_root, Path(source)).read()
                record = {"root": str(review_root), "revision": state["revision"]}
                result["review_revisions"].append(record)
                if current_review_root and path_key(current_review_root) == path_key(review_root):
                    result["current_review_revision"] = state["revision"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                error(review_root, exc)
            for directory in _children(review_root / "publications", errors, missing_ok=True):
                try:
                    publication = _publication(directory / "job.json", source, set(roots))
                    if publication is None:
                        continue
                    result["publications"].append(publication)
                    for attempt in publication["attempts"]:
                        request = attempt["request"]
                        for stage in ("groups", "export", "qa"):
                            key = "exports" if stage == "export" else "runs"
                            root = Path(request["destinations"][key])
                            stage_root = (
                                root
                                / "reviewer-publications"
                                / directory.name
                                / attempt["id"]
                                / stage
                            )
                            for published in _children(stage_root, errors, missing_ok=True):
                                candidate(
                                    published,
                                    config_path=request.get("config_path"),
                                    ownership="publication",
                                )
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    error(directory, exc)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error(review_root, exc)
    receipts = []
    for path, context in candidates.values():
        try:
            record = _run(path, source, **context)
            if record:
                (receipts if record["stage"] == "trainer-check" else result["runs"]).append(record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error(path, exc)
    exports = [record for record in result["runs"] if record["stage"] == "export"]
    for record in receipts:
        try:
            path = Path(record["path"])
            meta, checksum = read_object(path / "run.json")
            receipt, receipt_checksum = read_object(path / "result.json")
            if (
                checksum != record["run_sha256"]
                or meta.get("files", {}).get("result.json") != receipt_checksum
            ):
                raise ValueError("Trainer receipt metadata checksum mismatch")
            if (
                not _hash(receipt.get("export_run_sha256"))
                or not _hash(receipt.get("export_manifest_sha256"))
                or not isinstance(receipt.get("export"), str)
                or not Path(receipt["export"]).is_absolute()
            ):
                raise ValueError("Trainer receipt lacks an exact export identity")
            exact = [
                export
                for export in exports
                if export["run_sha256"] == receipt.get("export_run_sha256")
                and export["manifest_sha256"] == receipt.get("export_manifest_sha256")
            ]
            same_path = [
                export
                for export in exports
                if path_key(export["path"]) == path_key(receipt.get("export", ""))
            ]
            if not exact and not same_path:
                continue
            record["input"] = {
                "export": receipt.get("export"),
                "export_run_sha256": receipt.get("export_run_sha256"),
                "export_manifest_sha256": receipt.get("export_manifest_sha256"),
            }
            record["receipt_binding"] = "exact_export" if exact else "stale_same_path"
            record["export_ids"] = [export["id"] for export in exact or same_path]
            result["runs"].append(record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error(record["path"], exc)
    result["jobs"].sort(key=lambda row: (str(row["created_at"] or ""), row["id"]))
    result["runs"].sort(key=lambda row: (str(row["created_at"] or ""), row["id"]))
    result["errors"] = sorted(errors, key=lambda row: (row["path"], row["error"]))
    return result


def select_run(entry: dict, selector: str, expected_sha256: str | None = None) -> dict:
    """Resolve an exact path-and-content record; never choose by basename or latest time."""
    if not _hash(selector) or (expected_sha256 is not None and not _hash(expected_sha256)):
        raise ValueError("Choose an exact catalog run ID and valid expected checksum")
    snapshot = collection_snapshot(entry)
    matches = [record for record in snapshot["runs"] if record["id"] == selector]
    if len(matches) != 1:
        raise ValueError(
            "Selected run is missing, changed, or outside this collection; refresh the catalog"
        )
    selected = matches[0]
    selected["registered_roots"] = snapshot["registered_roots"]
    _, checksum = read_object(Path(selected["path"]) / "run.json")
    if checksum != selected["run_sha256"] or expected_sha256 not in (None, checksum):
        raise ValueError("Selected run metadata changed; refresh the catalog")
    return selected
