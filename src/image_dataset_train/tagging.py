"""Tag a verified inventory and publish drafts separately from source captions."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import warnings
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

import numpy as np
from PIL import Image

from image_dataset_train import __version__
from image_dataset_train.captions import CAPTION_VERSION, caption_record, check_rules
from image_dataset_train.config import CaptionConfig, Config, ValidationConfig
from image_dataset_train.inventory import file_sha256
from image_dataset_train.model_bundle import (
    MODELS,
    Label,
    atomic_json,
    bundle_path,
    load_bundle,
)
from image_dataset_train.score_cache import ScoreCache, score_checksum
from image_dataset_train.wd_tagger import PREPROCESS_VERSION, WDTagger, prepare_image


def _read_inventory(directory: Path) -> tuple[dict, list[dict], str]:
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if metadata.get("stage") != "inventory" or metadata.get("schema_version") != 1:
        raise ValueError("tagging requires an inventory run with schema_version=1")
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


def _separate(source: Path, paths: list[Path]) -> None:
    for path in paths:
        resolved = path.resolve()
        if resolved.is_relative_to(source) or source.is_relative_to(resolved):
            raise ValueError("source and tagging output/cache directories must be separate trees")


def _verified_bytes(source: Path, row: dict, limits: ValidationConfig) -> bytes:
    width, height = row.get("stored_width"), row.get("stored_height")
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise ValueError("inventory is missing valid stored dimensions")
    if (
        width * height > limits.max_decode_pixels
        or max(width, height) ** 2 > limits.max_decode_pixels
    ):
        raise ValueError("decode or square preprocessing exceeds configured pixel limit")
    relative = PurePosixPath(row["source_path"])
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in str(relative)
        or ":" in str(relative)
    ):
        raise ValueError("unsafe inventory source path")
    path = source.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(source):
        raise ValueError("inventory source path escapes source directory")
    for part in (path, *path.parents):
        if part == source:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("source path became a link after inventory")
    with path.open("rb") as stream:
        raw = stream.read(limits.max_file_bytes + 1)
    if len(raw) > limits.max_file_bytes:
        raise ValueError("source exceeds configured tagging byte limit")
    if hashlib.sha256(raw).hexdigest() != row.get("sha256"):
        raise ValueError("source_changed_since_inventory")
    return raw


def _prepare(raw: bytes, size: int, limits: ValidationConfig) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if max(image.size) ** 2 > limits.max_decode_pixels:
                raise ValueError("square preprocessing exceeds configured pixel limit")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("multiple-frame image is not eligible for tagging")
            image.load()
            return prepare_image(image, size)


def _publish(
    root: Path,
    rows: list[dict],
    vectors: dict[str, np.ndarray],
    labels: list[Label],
    metadata: dict,
    summary: dict,
    rules: CaptionConfig,
    default_threshold: float,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stage = metadata["stage"]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + f"-{stage}-" + uuid4().hex[:8]
    pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    captions = pending / "captions"
    captions.mkdir()
    scores_dir = pending / "scores"
    scores_dir.mkdir()
    # Each run is self-contained for future recaptioning; cache cleanup cannot erase evidence.
    artifacts = {}
    for digest, vector in sorted(vectors.items()):
        relative = f"scores/{digest}.npy"
        with (pending / relative).open("wb") as stream:
            np.save(stream, np.asarray(vector, dtype=np.float32), allow_pickle=False)
        artifacts[digest] = {
            "path": relative,
            "sha256": file_sha256(pending / relative),
            "score_checksum": score_checksum(vector),
        }
    result_rows = []
    flags = Counter()
    tags = Counter()
    for item in rows:
        row = dict(item)
        if row.get("decision") == "tagged":
            record = caption_record(labels, vectors[row["sha256"]], rules, default_threshold)
            identifier = hashlib.sha256(row["source_path"].encode("utf-8")).hexdigest()
            row.update(record)
            row["caption_path"] = f"captions/{identifier}.txt"
            (pending / row["caption_path"]).write_text(
                record["caption"] + "\n", encoding="utf-8", newline="\n"
            )
            flags.update(record["review_flags"])
            tags.update(tag["name"] for tag in record["selected_tags"])
        result_rows.append(row)
    manifest = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in result_rows
    )
    (pending / "manifest.jsonl").write_text(manifest, encoding="utf-8", newline="\n")
    atomic_json(pending / "labels.json", [asdict(label) for label in labels])
    atomic_json(pending / "score_index.json", artifacts)
    summary.update(
        {
            "schema_version": 1,
            "stage": stage,
            "training_ready": False,
            "decisions": dict(Counter(row["decision"] for row in rows)),
            "review_flags": dict(flags),
            "top_tags": dict(tags.most_common(100)),
            "unique_scored_images": len(vectors),
        }
    )
    status = "completed_with_errors" if summary["decisions"].get("error") else "completed"
    metadata.update(
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "completed_at": datetime.now(UTC).isoformat(),
            "pipeline_version": __version__,
            "caption_version": CAPTION_VERSION,
            "caption_rules": asdict(rules),
            "default_general_threshold": default_threshold,
            "manifest_sha256": file_sha256(pending / "manifest.jsonl"),
            "labels_sha256": file_sha256(pending / "labels.json"),
            "score_index_sha256": file_sha256(pending / "score_index.json"),
        }
    )
    atomic_json(pending / "summary.json", summary)
    atomic_json(pending / "run.json", metadata)
    final = root / run_id
    pending.rename(final)
    return final


def tag_inventory(
    config: Config,
    inventory: Path,
    progress: Callable[[str], None] | None = None,
    *,
    only_sources: set[str] | None = None,
) -> tuple[Path, dict]:
    started = datetime.now(UTC).isoformat()
    inventory_meta, records, inventory_hash = _read_inventory(inventory)
    source = Path(inventory_meta["source"]).resolve(strict=True)
    _separate(source, [config.models, config.scores, config.runs])
    bundle = load_bundle(bundle_path(config.models, config.tagging.model, config.tagging.revision))
    check_rules(bundle.labels, config.captions)
    tagger = WDTagger(bundle, config.tagging.device)
    if progress:
        progress(f"Providers: {', '.join(tagger.runtime['providers'])}")
        if tagger.fallback:
            progress(tagger.fallback)
    cache = ScoreCache(config.scores, tagger.cache_namespace, len(bundle.labels))
    effective_batch = tagger.fixed_batch or config.tagging.batch_size
    vectors: dict[str, np.ndarray] = {}
    pending: dict[str, np.ndarray] = {}
    rows = []
    summary = {"inferred_images": 0, "cached_images": 0, "duplicate_score_reuse": 0}

    def flush() -> None:
        if not pending:
            return
        predicted = tagger.predict(np.stack(list(pending.values())))
        for digest, vector in zip(pending, predicted, strict=True):
            cache.put(digest, vector)
            vectors[digest] = vector
            summary["inferred_images"] += 1
        pending.clear()
        if progress:
            progress(f"Scored {len(vectors)} unique images; inferred {summary['inferred_images']}")

    for record in records:
        if record["kind"] != "image":
            continue
        row = {
            "source_path": record["source_path"],
            "sha256": record.get("sha256"),
            "intake_decision": record["decision"],
            "intake_reasons": record["reasons"],
            "duplicate_of": record.get("duplicate_of"),
            "source_sidecar_path": record.get("sidecar_path"),
            "source_sidecar_sha256": record.get("sidecar_sha256"),
            "decision": "skipped",
        }
        rows.append(row)
        if only_sources is not None and record["source_path"] not in only_sources:
            row["reason"] = "not_selected_for_caption_publication"
            continue
        if record["decision"] not in {"candidate", "review", "duplicate"}:
            row["reason"] = "not_eligible_at_intake"
            continue
        try:
            raw = _verified_bytes(source, record, config.validation)
            digest = record["sha256"]
            if digest in vectors or digest in pending:
                summary["duplicate_score_reuse"] += 1
            else:
                cached = cache.get(digest)
                if cached is not None:
                    vectors[digest] = cached
                    summary["cached_images"] += 1
                else:
                    pending[digest] = _prepare(raw, tagger.size, config.validation)
            row["decision"] = "tagged"
        except (
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ) as exc:
            row["decision"], row["error"] = "error", f"{type(exc).__name__}: {exc}"
        if len(pending) >= effective_batch:
            flush()
    flush()
    metadata = {
        "stage": "tagging",
        "started_at": started,
        "source": str(source),
        "source_revalidated": True,
        "inventory_run": str(inventory.resolve()),
        "inventory_manifest_sha256": inventory_hash,
        "model": bundle.metadata,
        "preprocessing": PREPROCESS_VERSION,
        "runtime": tagger.runtime,
        "requested_device": config.tagging.device,
        "provider_fallback": tagger.fallback,
        "cache_namespace": tagger.cache_namespace,
        "batch_size": effective_batch,
        "validation": asdict(config.validation),
    }
    default = MODELS[config.tagging.model].suggested_general_threshold
    directory = _publish(
        config.runs, rows, vectors, bundle.labels, metadata, summary, config.captions, default
    )
    return directory, summary


def recaption(config: Config, previous: Path) -> tuple[Path, dict]:
    """Rebuild caption drafts from a self-contained scored run, without loading an ONNX model."""
    from image_dataset_train.wd_tagger import validate_scores

    metadata = json.loads((previous / "run.json").read_text(encoding="utf-8"))
    if metadata.get("stage") not in {"tagging", "recaption"} or metadata.get("schema_version") != 1:
        raise ValueError("recaption requires a completed tagging or recaption run")
    if metadata.get("status") not in {"completed", "completed_with_errors"}:
        raise ValueError("scored run is incomplete")
    source = Path(metadata["source"]).resolve()
    _separate(source, [config.runs])
    for filename, key in (
        ("manifest.jsonl", "manifest_sha256"),
        ("labels.json", "labels_sha256"),
        ("score_index.json", "score_index_sha256"),
    ):
        if file_sha256(previous / filename) != metadata.get(key):
            raise ValueError(f"scored run integrity failure: {filename}")
    labels = [
        Label(**row) for row in json.loads((previous / "labels.json").read_text(encoding="utf-8"))
    ]
    check_rules(labels, config.captions)
    index = json.loads((previous / "score_index.json").read_text(encoding="utf-8"))
    vectors = {}
    for digest, artifact in index.items():
        expected = f"scores/{digest}.npy"
        if (
            len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or artifact["path"] != expected
        ):
            raise ValueError("invalid score artifact path")
        path = previous / expected
        if file_sha256(path) != artifact["sha256"]:
            raise ValueError(f"score artifact hash mismatch: {digest}")
        vector = np.load(path, allow_pickle=False)
        validate_scores(vector, len(labels))
        if score_checksum(vector) != artifact["score_checksum"]:
            raise ValueError("score vector checksum mismatch")
        vectors[digest] = vector
    rows = [
        json.loads(line)
        for line in (previous / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        for field in (
            "caption",
            "selected_tags",
            "ratings",
            "uncertain_tags",
            "review_flags",
            "effective_general_threshold",
            "caption_path",
        ):
            row.pop(field, None)
        if row["decision"] == "tagged" and row["sha256"] not in vectors:
            raise ValueError("missing score vector for tagged image")
    metadata = {
        **metadata,
        "stage": "recaption",
        "started_at": datetime.now(UTC).isoformat(),
        "parent_run": str(previous.resolve()),
        "source_revalidated": False,
    }
    summary = {"inferred_images": 0, "reused_score_vectors": len(vectors)}
    directory = _publish(
        config.runs,
        rows,
        vectors,
        labels,
        metadata,
        summary,
        config.captions,
        metadata["default_general_threshold"],
    )
    return directory, summary
