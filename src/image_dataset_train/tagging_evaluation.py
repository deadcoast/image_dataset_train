"""Compare verified saved scores with frozen, independent critical-label judgments."""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train import __version__
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.execution import RunClock
from image_dataset_train.exporting import _checked
from image_dataset_train.inventory import file_sha256
from image_dataset_train.label_workspace import LabelWorkspace
from image_dataset_train.reviews import _separate
from image_dataset_train.saved_caption_rules import resolve_saved_caption_rules
from image_dataset_train.scored_runs import ScoredRun

SETS = ("calibration", "held_out")


def _metrics(cases: list[dict], threshold: float) -> dict:
    counts = Counter()
    for case in cases:
        actual, predicted = case["actual"] == "present", case["score"] > threshold
        counts[
            "tp" if actual and predicted else "fn" if actual else "fp" if predicted else "tn"
        ] += 1
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "specificity": tn / (tn + fp) if tn + fp else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def _errors(cases: list[dict], threshold: float | None) -> list[dict]:
    if threshold is None:
        return []
    return [
        {**case, "predicted": "present" if case["score"] > threshold else "absent"}
        for case in cases
        if (case["actual"] == "present") != (case["score"] > threshold)
    ]


def _label_result(cases: dict, counts: dict, baseline: float) -> dict:
    calibration = cases["calibration"]
    fitted = None
    if {case["actual"] for case in calibration} == {"present", "absent"}:
        candidates = sorted({baseline, *(index / 100 for index in range(101))})
        fitted = max(
            candidates,
            key=lambda threshold: (
                _metrics(calibration, threshold)["f1"],
                threshold == baseline,
                -abs(threshold - baseline),
                threshold,
            ),
        )
    metrics = {
        f"{split}_{name}": _metrics(cases[split], threshold) if threshold is not None else None
        for split in SETS
        for name, threshold in (("baseline", baseline), ("fitted", fitted))
    }
    return {
        "baseline_threshold": baseline,
        "fit_threshold": fitted,
        "fit_status": "fitted" if fitted is not None else "needs_positive_and_negative_calibration",
        "counts": counts,
        **metrics,
        "errors": {
            f"{split}_{name}": _errors(cases[split], threshold)
            for split in SETS
            for name, threshold in (("baseline", baseline), ("fitted", fitted))
        },
    }


def _evaluate_model(
    saved: ScoredRun, selection: dict, state: dict, include_assistant: bool
) -> tuple:
    if Path(saved.metadata["source"]).resolve() != Path(selection["source"]).resolve():
        raise ValueError("Scored run source differs from the frozen label population")
    vocabulary = {label.name: label for label in saved.labels}
    labels = [item["name"] for item in selection["labels"]]
    if any(
        item["name"] not in vocabulary or vocabulary[item["name"]].category != item["category"]
        for item in selection["labels"]
    ):
        raise ValueError("Scored run must contain every selected raw label with the same category")
    identities = {
        (row["source_path"], row.get("sha256"))
        for row in saved.rows
        if row.get("decision") == "tagged"
    }
    missing = {
        (alias["source_path"], member["sha256"])
        for member in selection["members"]
        for alias in member["aliases"]
    } - identities
    if missing:
        path, digest = min(missing)
        raise ValueError(
            f"Scored run is missing {len(missing)} selected path/hash identities; "
            f"first: {path} ({digest})"
        )
    saved_rules = resolve_saved_caption_rules(saved.metadata, saved.labels)
    baseline = saved_rules.thresholds(vocabulary[name] for name in labels)
    cases = {name: {split: [] for split in SETS} for name in labels}
    counts = {
        name: {
            split: {
                key: 0
                for key in ("present", "absent", "uncertain", "assistant_excluded", "unreviewed")
            }
            for split in SETS
        }
        for name in labels
    }
    evidence = []
    for member in selection["members"]:
        digest, split = member["sha256"], member["evaluation_set"]
        vector = saved.vector(digest)
        scores = {name: float(vector[vocabulary[name].index]) for name in labels}
        evidence.append(
            {
                "sha256": digest,
                "evaluation_set": split,
                "score_artifact": saved.index[digest],
                "scores": scores,
                "baseline_predictions": {
                    name: "present" if score > baseline[name] else "absent"
                    for name, score in scores.items()
                },
            }
        )
        judgments = state["judgments"].get(digest, {})
        for name, score in scores.items():
            judgment = judgments.get(name)
            if judgment is None:
                counts[name][split]["unreviewed"] += 1
                continue
            if judgment["reviewer_kind"] == "assistant" and not include_assistant:
                counts[name][split]["assistant_excluded"] += 1
                continue
            actual = judgment["value"]
            counts[name][split][actual] += 1
            if actual != "uncertain":
                cases[name][split].append({"sha256": digest, "score": score, "actual": actual})
    return (
        {
            "run": str(saved.run),
            "run_sha256": saved.digest,
            "model": saved.metadata.get("model"),
            "preprocessing": saved.metadata.get("preprocessing"),
            "runtime": saved.metadata.get("runtime"),
            "manifest_sha256": saved.metadata["manifest_sha256"],
            "labels_sha256": saved.metadata["labels_sha256"],
            "score_index_sha256": saved.metadata["score_index_sha256"],
            "caption_rules_sha256": saved.metadata.get("caption_rules_sha256"),
            "labels": {
                name: _label_result(cases[name], counts[name], baseline[name]) for name in labels
            },
        },
        evidence,
    )


def evaluate_labels(
    config: Config,
    workspace: Path,
    scored_runs: list[Path],
    *,
    include_assistant: bool = False,
) -> tuple[Path, dict]:
    """Freeze judgments and publish a same-population comparison, without changing thresholds."""
    clock = RunClock()
    if not scored_runs:
        raise ValueError("Select at least one scored run")
    if type(include_assistant) is not bool:
        raise ValueError("include_assistant must be boolean")
    store = LabelWorkspace(workspace)
    selection, state = store.selection, store.read()
    root = config.runs.resolve()
    _separate(Path(selection["source"]).resolve(), root)
    frozen_inputs = (
        [store.directory]
        + [Path(selection[key]).resolve() for key in ("qa_run", "input_run", "reference_run")]
        + [Path(path).resolve() for path in selection.get("lineage_inputs", [])]
    )
    if any(root.is_relative_to(path) for path in frozen_inputs):
        raise ValueError("Evaluations cannot be published inside their frozen input artifacts")
    models, evidence, snapshots = [], [], []
    seen = set()
    for run in scored_runs:
        saved = ScoredRun(run)
        if root.is_relative_to(saved.run):
            raise ValueError("Evaluations cannot be published inside their scored input")
        if saved.digest in seen:
            raise ValueError("Choose distinct scored runs for a comparison")
        seen.add(saved.digest)
        result, records = _evaluate_model(saved, selection, state, include_assistant)
        number = len(models)
        result["scores_file"] = f"model-{number:03d}-scores.jsonl"
        result["metadata_file"] = f"model-{number:03d}-run.json"
        snapshots.append(_checked(saved.run, "run.json", saved.digest))
        models.append(result)
        evidence.append(records)
    workspace_provenance = (
        {
            name: f"workspace-{name}"
            for name in ("parent-run.json", "parent-selection.json", "parent-judgments.json")
        }
        if "refresh" in selection
        else {}
    )
    provenance_raw = {
        destination: _checked(store.directory, name, store.metadata["files"].get(name))
        for name, destination in workspace_provenance.items()
    }
    result = {
        "schema_version": 1,
        "stage": "label_evaluation",
        "workspace": str(store.directory),
        "workspace_sha256": store.digest,
        "selection_sha256": store.selection_sha256,
        "judgment_revision": state["revision"],
        "workspace_provenance": workspace_provenance,
        "judgment_policy": "human_and_assistant_diagnostic" if include_assistant else "human_only",
        "include_assistant": include_assistant,
        "human_accepted": False,
        "representative_acceptance": False,
        "selected_unique_images": len(selection["members"]),
        "selected_aliases": sum(len(member["aliases"]) for member in selection["members"]),
        "groups": len({member["group_id"] for member in selection["members"]}),
        "evaluation_sets": dict(
            Counter(member["evaluation_set"] for member in selection["members"])
        ),
        "method": {
            "prediction": (
                "raw model score > saved threshold, independent of caption drop/keep flags"
            ),
            "weighting": (
                "one observation per unique content SHA256; known frozen groups never cross sets"
            ),
            "candidate_thresholds": "0.00 through 1.00 in steps of 0.01 plus the saved baseline",
            "fit": (
                "require present and absent calibration judgments; maximize calibration F1; "
                "ties prefer baseline, then nearest baseline, then larger threshold"
            ),
            "held_out": "evaluated only after fitting; never used to select a cutoff",
            "uncertain": "excluded from confusion counts and fitting",
            "adoption": "no configuration or caption changes; fitted cutoffs are proposals",
        },
        "models": models,
    }
    # Validate and copy exactly the immutable selection and workspace provenance used above.
    selection_raw = _checked(store.directory, "selection.json", store.selection_sha256)
    workspace_raw = _checked(store.directory, "run.json", store.digest)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-label-evaluation-", dir=root))
    (staging / "selection.json").write_bytes(selection_raw)
    (staging / "workspace-run.json").write_bytes(workspace_raw)
    for name, raw in provenance_raw.items():
        (staging / name).write_bytes(raw)
    atomic_json(staging / "judgments.json", state)
    result["judgments_sha256"] = file_sha256(staging / "judgments.json")
    for model, records, metadata in zip(models, evidence, snapshots, strict=True):
        (staging / model["metadata_file"]).write_bytes(metadata)
        (staging / model["scores_file"]).write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
            newline="\n",
        )
    atomic_json(staging / "result.json", result)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-label-evaluation-" + uuid4().hex[:8]
    atomic_json(
        staging / "run.json",
        {
            "schema_version": 1,
            "stage": "label_evaluation",
            "status": "completed",
            "run_id": run_id,
            "pipeline_version": __version__,
            "source": selection["source"],
            "source_revalidated": False,
            "created_at": datetime.now(UTC).isoformat(),
            "workspace": str(store.directory),
            "workspace_sha256": store.digest,
            "selection_sha256": store.selection_sha256,
            "judgment_revision": state["revision"],
            "judgments_sha256": result["judgments_sha256"],
            "files": {path.name: file_sha256(path) for path in sorted(staging.iterdir())},
            "metrics": clock.measure(staging),
        },
    )
    output = root / run_id
    publish_directory(staging, output)
    return output, result
