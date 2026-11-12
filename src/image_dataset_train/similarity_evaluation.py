"""Evaluate saved pHashes against explicit pair judgments without repeating inference."""

from __future__ import annotations

import json
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train import __version__
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.execution import RunClock, processing_history
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reviews import ReviewStore, _active_pair, _separate, load_context


def threshold_sweep(pairs: list[dict]) -> list[dict]:
    """Only scored, explicitly judged unique content pairs enter the confusion matrices."""
    related, distinct = Counter(), Counter()
    for pair in pairs:
        if pair["status"] == "evaluated":
            (related if pair["decision"] == "related" else distinct)[pair["distance"]] += 1
    positive, negative = related.total(), distinct.total()
    tp = fp = 0
    rows = []
    for radius in range(65):
        tp += related[radius]
        fp += distinct[radius]
        fn, tn = positive - tp, negative - fp
        rows.append(
            {
                "max_distance": radius,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / positive if positive else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            }
        )
    return rows


def _split_summary(pairs: list[dict]) -> dict:
    evaluated = [pair for pair in pairs if pair["status"] == "evaluated" and pair["evaluation_set"]]
    by_set = {
        name: [pair for pair in evaluated if pair["evaluation_set"] == name]
        for name in ("calibration", "held_out")
    }
    calibration = threshold_sweep(by_set["calibration"])
    held_out = threshold_sweep(by_set["held_out"])
    calibration_classes = {
        "related": sum(pair["decision"] == "related" for pair in by_set["calibration"]),
        "distinct": sum(pair["decision"] == "distinct" for pair in by_set["calibration"]),
    }
    fit_radius = None
    if all(calibration_classes.values()):
        # Deterministic tie-break: prefer the stricter (smaller) radius.
        fit_radius = max(
            calibration,
            key=lambda row: (-1 if row["f1"] is None else row["f1"], -row["max_distance"]),
        )["max_distance"]
    return {
        "counts": {
            "calibration": len(by_set["calibration"]),
            "held_out": len(by_set["held_out"]),
            "calibration_related": calibration_classes["related"],
            "calibration_distinct": calibration_classes["distinct"],
            "held_out_related": sum(pair["decision"] == "related" for pair in by_set["held_out"]),
            "held_out_distinct": sum(pair["decision"] == "distinct" for pair in by_set["held_out"]),
        },
        "fit_radius": fit_radius,
        "calibration_thresholds": calibration,
        "held_out_at_fit": held_out[fit_radius] if fit_radius is not None else None,
        "held_out_thresholds": held_out,
        "fit_rule": "maximum calibration F1; ties choose the smaller radius",
    }


def evaluate_similarity(config: Config, run: Path) -> tuple[Path, dict]:
    """Publish a reproducible threshold evaluation; source bytes and reviews stay untouched."""
    clock = RunClock()
    context = load_context(run, require_source=False)
    _separate(context.source, config.runs)
    root = config.runs.resolve()
    if root.is_relative_to(context.run):
        raise ValueError("Evaluations must not be published inside their similarity input")
    state = ReviewStore(config.reviews, context.source).read()
    hashes = {}
    with (context.run / "images.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            original = context.rows.get(row.get("source_path"))
            if original is None or original["sha256"] != row.get("sha256"):
                raise ValueError("Similarity image identity differs from its inventory")
            if row["decision"] != "indexed":
                continue
            value = row.get("phash")
            if (
                not isinstance(value, str)
                or len(value) != 16
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("Expected a recorded 64-bit pHash")
            if row["sha256"] in hashes and hashes[row["sha256"]] != value:
                raise ValueError("Conflicting pHashes for identical image bytes")
            hashes[row["sha256"]] = value
    counts = Counter(saved_decisions=len(state["pairs"]))
    grouped = defaultdict(list)
    for identifier, pair in sorted(state["pairs"].items()):
        if not _active_pair(context, pair):
            counts["stale_decisions"] += 1
        elif pair["decision"] == "unreviewed":
            counts["pending_decisions"] += 1
        elif pair["left_sha256"] == pair["right_sha256"]:
            counts["exact_byte_judgments"] += 1
        else:
            key = tuple(sorted((pair["left_sha256"], pair["right_sha256"])))
            grouped[key].append({"pair_id": identifier, **pair})
            counts["active_judgments"] += 1
    pairs = []
    for (left, right), judgments in sorted(grouped.items()):
        decisions = {j["decision"] for j in judgments}
        evaluation_sets = {j.get("evaluation_set") for j in judgments}
        conflict = len(decisions) != 1
        set_conflict = len(evaluation_sets) != 1
        missing = left not in hashes or right not in hashes
        distance = None if missing else (int(hashes[left], 16) ^ int(hashes[right], 16)).bit_count()
        status = (
            "conflicting_judgments"
            if conflict
            else "conflicting_evaluation_sets"
            if set_conflict
            else "hash_unavailable"
            if missing
            else "evaluated"
        )
        counts[status] += 1
        pairs.append(
            {
                "left_sha256": left,
                "right_sha256": right,
                "left_phash": hashes.get(left),
                "right_phash": hashes.get(right),
                "decision": None if conflict else next(iter(decisions)),
                "evaluation_set": None if set_conflict else next(iter(evaluation_sets)),
                "distance": distance,
                "status": status,
                "judgments": judgments,
            }
        )
    counts["alias_judgments_collapsed"] = counts["active_judgments"] - len(pairs)
    counts["indexed_unique_images"] = len(hashes)
    counts["unjudged_indexed_pairs"] = len(hashes) * (len(hashes) - 1) // 2 - counts["evaluated"]
    sweep = threshold_sweep(pairs)
    evaluation_sets = _split_summary(pairs)
    radius = context.metadata["max_hamming_distance"]
    if type(radius) is not int or not 0 <= radius <= 64:
        raise ValueError("Similarity radius must be between 0 and 64")
    current = sweep[radius]
    errors = []
    for pair in pairs:
        if pair["status"] != "evaluated":
            continue
        predicted = pair["distance"] <= radius
        if predicted != (pair["decision"] == "related"):
            errors.append({**pair, "finding": "false_match" if predicted else "known_miss"})
    positives = current["true_positive"] + current["false_negative"]
    negatives = current["true_negative"] + current["false_positive"]
    summary = {
        "schema_version": 1,
        "stage": "similarity-evaluation",
        "review_revision": state["revision"],
        "hash_version": context.metadata["hash_version"],
        "counts": dict(sorted(counts.items())),
        "related_pairs": positives,
        "distinct_pairs": negatives,
        "both_classes_reviewed": bool(positives and negatives),
        "current": current,
        "thresholds": sweep,
        "evaluation_sets": evaluation_sets,
        "error_examples": errors[:20],
        "error_examples_total": len(errors),
        "collection_qualified": False,
        "scope": "Explicitly reviewed unique content pairs only; unjudged pairs are not negatives.",
    }
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-similarity-evaluation-", dir=root))
    (staging / "pairs.jsonl").write_text(
        "".join(json.dumps(pair, ensure_ascii=False, sort_keys=True) + "\n" for pair in pairs),
        encoding="utf-8",
        newline="\n",
    )
    atomic_json(staging / "summary.json", summary)
    run_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-similarity-evaluation-" + uuid4().hex[:8]
    )
    atomic_json(
        staging / "run.json",
        {
            "schema_version": 1,
            "stage": "similarity-evaluation",
            "status": "completed",
            "run_id": run_id,
            "pipeline_version": __version__,
            "evaluation_version": "reviewed-phash-thresholds-v2",
            "source": str(context.source),
            "source_required": False,
            "similarity_run": str(context.run),
            "similarity_run_sha256": file_sha256(context.run / "run.json"),
            "inventory_manifest_sha256": context.inventory_hash,
            "review_revision": state["revision"],
            "hash_version": context.metadata["hash_version"],
            "metrics": clock.measure(staging),
            "processing_history": processing_history(context.inventory_metadata, context.metadata),
            "files": {
                name: file_sha256(staging / name) for name in ("pairs.jsonl", "summary.json")
            },
        },
    )
    final = root / run_id
    publish_directory(staging, final)
    return final, summary
