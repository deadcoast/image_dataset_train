"""Inspect expected inference scores using a verified local runtime, without inference."""

from __future__ import annotations

import stat
from pathlib import Path

from image_dataset_train.config import Config
from image_dataset_train.inventory_data import read_inventory
from image_dataset_train.model_bundle import bundle_path, load_bundle


def _unlinked(path: Path) -> None:
    for part in (path.absolute(), *path.absolute().parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"linked paths are not supported for cache verification: {path}")


def _file_state(path: Path) -> tuple[int, int, int, int]:
    _unlinked(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"cache verification requires a regular file: {path}")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _error(exc: Exception) -> dict:
    return {"type": type(exc).__name__, "message": str(exc)}


def inspect_inference_cache(
    config: Config, inventory: Path, *, expected_model: dict | None = None
) -> dict:
    """Verify only the inventory's eligible content in the current session namespace.

    Session creation verifies the ONNX contract and resolves actual providers/options.
    It never predicts, downloads, repairs, or publishes artifacts. Valid cache scores
    and current source-byte checks are separate evidence; neither establishes that a
    preparation job can resume. Missing vectors are ordinary remaining inference work.
    """
    result = {
        "status": "unavailable",
        "scope": "current_session_cache_verification",
        "source": str(config.source),
        "inventory": str(inventory),
        "cache_root": str(config.scores),
        "eligible_occurrences": None,
        "eligible_unique_contents": None,
        "counts": None,
        "source_counts": None,
        "entries": [],
        "runtime": None,
        "requested_device": config.tagging.device,
        "provider_fallback": None,
        "cache_namespace": None,
        "model_artifact_id": None,
        "inference_performed": False,
        "application_writes": False,
    }

    def unavailable(reason: str, exc: Exception) -> dict:
        return {**result, "status": "unavailable", "reason": reason, "error": _error(exc)}

    try:
        inventory_files = [inventory / name for name in ("run.json", "manifest.jsonl")]
        before_inventory = [_file_state(path) for path in inventory_files]
        metadata, rows, _ = read_inventory(inventory)
        if before_inventory != [_file_state(path) for path in inventory_files]:
            raise ValueError("inventory changed during cache verification")
        source = Path(metadata["source"])
        if source.resolve() != config.source.resolve():
            raise ValueError("configuration source does not match the inventory source")
        eligible = [
            row
            for row in rows
            if row["kind"] == "image" and row["decision"] in {"candidate", "review", "duplicate"}
        ]
        by_digest: dict[str, list[dict]] = {}
        for row in eligible:
            by_digest.setdefault(row["sha256"], []).append(row)
        result["eligible_occurrences"] = len(eligible)
        result["eligible_unique_contents"] = len(by_digest)
    except Exception as exc:
        return unavailable("inventory_unavailable", exc)

    try:
        roots = [source.resolve(), config.models.resolve(), config.scores.resolve()]
        for index, root in enumerate(roots):
            for other in roots[index + 1 :]:
                if root.is_relative_to(other) or other.is_relative_to(root):
                    raise ValueError("source, model, and score cache must be separate trees")
        _unlinked(config.models)
        _unlinked(config.scores)
    except Exception as exc:
        return unavailable("unsafe_paths", exc)

    try:
        directory = bundle_path(config.models, config.tagging.model, config.tagging.revision)
        model_files = [
            directory / name for name in ("model.json", "model.onnx", "selected_tags.csv")
        ]
        before_model = [_file_state(path) for path in model_files]
        bundle = load_bundle(
            directory, model=config.tagging.model, revision=config.tagging.revision
        )
        if before_model != [_file_state(path) for path in model_files]:
            raise ValueError("local model changed during verification")
        result["model_artifact_id"] = bundle.metadata["artifact_id"]
        if expected_model is not None and bundle.metadata != expected_model:
            return unavailable(
                "model_identity_changed",
                ValueError("local model differs from the job model identity"),
            )
    except Exception as exc:
        return unavailable("model_unavailable", exc)

    try:
        # Optional tagging dependencies remain lazy so missing runtimes are diagnostic
        # results, rather than preventing preparation status from loading at all.
        from image_dataset_train.score_cache import ScoreCache
        from image_dataset_train.tagging import _verified_bytes
        from image_dataset_train.wd_tagger import WDTagger

        tagger = WDTagger(bundle, config.tagging.device)
        if before_model != [_file_state(path) for path in model_files]:
            return unavailable(
                "model_unavailable", ValueError("local model changed while creating the session")
            )
        cache = ScoreCache(config.scores, tagger.cache_namespace, len(bundle.labels))
        result.update(
            runtime=tagger.runtime,
            provider_fallback=tagger.fallback,
            cache_namespace=tagger.cache_namespace,
        )
    except Exception as exc:
        return unavailable("runtime_unavailable", exc)

    source_root_error = None
    try:
        _unlinked(source)
        _unlinked(config.source)
    except Exception as exc:
        source_root_error = _error(exc)

    counts = {"valid": 0, "missing": 0, "invalid": 0}
    source_counts = {"verified": 0, "invalid": 0}
    entries = []
    for digest, occurrences in sorted(by_digest.items()):
        entry = cache.inspect(digest)
        entry["aliases"] = [row["source_path"] for row in occurrences]
        entry["source_errors"] = []
        for row in occurrences:
            error = source_root_error
            if error is None:
                try:
                    _verified_bytes(source, row, config.validation)
                except Exception as exc:
                    error = _error(exc)
            if error is not None:
                entry["source_errors"].append({"source_path": row["source_path"], **error})
                source_counts["invalid"] += 1
            else:
                source_counts["verified"] += 1
        counts[entry["status"]] += 1
        entries.append(entry)
    result.update(
        status="partial" if counts["invalid"] or source_counts["invalid"] else "complete",
        counts=counts,
        source_counts=source_counts,
        entries=entries,
    )
    return result
