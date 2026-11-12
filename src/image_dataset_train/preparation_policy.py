"""Attributed, source-preserving preparation decisions, separate from human review."""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train import __version__
from image_dataset_train.annotations import annotation_summary
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.execution import RunClock, processing_history
from image_dataset_train.exporting import (
    _caption,
    _caption_for_derivative,
    _drafts,
    _identity,
    _load_groups,
    _source_bytes,
)
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reviews import _review_pairs, load_context

POLICY = "conservative-v1"


def prepare_groups(
    config: Config,
    groups_run: Path,
    *,
    captions_run: Path | None = None,
) -> tuple[Path, dict]:
    """Resolve structural eligibility and split constraints without editing review stores."""
    clock = RunClock()
    meta, original, artifacts = _load_groups(groups_run, require_reviewed=False)
    if meta.get("preparation_policy"):
        raise ValueError("Prepare from a reviewed group snapshot, not a previous policy result")
    source = Path(meta["source"]).resolve(strict=True)
    root = config.runs.resolve()
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("Source and preparation output directories must be separate trees")
    context = load_context(Path(meta["similarity_run"]))
    if context.inventory_hash != meta["inventory_manifest_sha256"]:
        raise ValueError("Preparation groups and similarity inventory differ")
    drafts, draft_meta = _drafts(captions_run, meta)
    state = json.loads(artifacts["reviews.json"])
    original_summary = json.loads(artifacts["summary.json"])
    groups = deepcopy(original)
    members = {m["source_path"]: m for g in groups for m in g["members"]}
    parent = {path: path for path in members}

    def find(path):
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    def join(left, right):
        a, b = find(left), find(right)
        parent[max(a, b)] = min(a, b)

    for group in groups:
        first = group["members"][0]["source_path"]
        for member in group["members"][1:]:
            join(first, member["source_path"])
    distinct = [
        (record["left_source_path"], record["right_source_path"])
        for record in state["pairs"].values()
        if record["decision"] == "distinct"
        and record["left_source_path"] in members
        and record["right_source_path"] in members
        and record["left_sha256"] == members[record["left_source_path"]]["sha256"]
        and record["right_sha256"] == members[record["right_source_path"]]["sha256"]
    ]
    constraints, blockers = [], []
    # These edges constrain splits only; they are not saved as related-pair judgments.
    for pair in _review_pairs(context, state):
        reviewed = state["pairs"].get(pair["pair_id"], {}).get("decision", "unreviewed")
        if reviewed != "unreviewed":
            continue
        left, right = pair["left_source_path"], pair["right_source_path"]
        a, b = find(left), find(right)
        conflicts = [(x, y) for x, y in distinct if a != b and {find(x), find(y)} == {a, b}]
        item = {
            "pair_id": pair["pair_id"],
            "left_source_path": left,
            "right_source_path": right,
            "kind": "provisional_split_constraint",
            "semantic_relation_confirmed": False,
        }
        if conflicts:
            item.update(applied=False, conflicting_distinct_pairs=conflicts)
            blockers.append({"code": "review_constraint_conflict", **item})
        else:
            join(left, right)
            item["applied"] = True
        constraints.append(item)

    effective_captions = {}
    decisions = []
    # Prefer explicit inclusion as the keeper; preserve all explicit decisions.
    ordered = sorted(
        members.values(), key=lambda m: (m["review_decision"] != "include", m["source_path"])
    )
    seen = {}
    for member in ordered:
        path = member["source_path"]
        row = context.rows[path]
        _source_bytes(source, path, member["sha256"], config.validation.max_file_bytes)
        saved = member["review_decision"]
        origin = {"kind": "saved_review", "reason": member.get("reason", "")}
        reason = "retained_saved_decision"
        decision = saved
        caption = None
        if saved != "exclude":
            width, height = row["width"], row["height"]
            scale = min(1, config.export.resolution / (width * height) ** 0.5)
            problem = None
            if min(width, height) * scale < 64:
                problem = "below_trainer_bucket_minimum"
            sidecar = (
                _source_bytes(
                    source,
                    member["sidecar_path"],
                    member["sidecar_sha256"],
                    config.validation.max_file_bytes,
                )
                if member.get("sidecar_path")
                else None
            )
            try:
                caption, caption_origin = _caption(member, sidecar, drafts)
                effective_captions[path] = {"text": caption, "origin": caption_origin}
                conversion = (
                    row.get("has_alpha")
                    or row.get("exif_orientation", 1) != 1
                    or Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
                )
                prepared_caption, adjustments = _caption_for_derivative(
                    caption, "png-exif-white-v1" if conversion else "copy-v1"
                )
                effective_captions[path].update(
                    prepared_text=prepared_caption, adjustments=adjustments
                )
            except (UnicodeError, ValueError) as exc:
                problem = problem or "caption_unavailable"
                effective_captions[path] = {"error": str(exc)}
            if saved == "include" and problem:
                blockers.append({"code": problem, "source_path": path, "saved_include": True})
            elif saved == "unreviewed":
                decision = "exclude" if problem else "include"
                reason = problem or "readable_with_nonempty_caption"
                explicit_intent = (
                    member.get("caption_override") is not None
                    or member.get("labels_reviewed")
                    or member.get("subset_reviewed")
                )
                if (
                    decision == "include"
                    and not explicit_intent
                    and (member["sha256"], caption) in seen
                ):
                    decision, reason = "exclude", "exact_bytes_and_caption_already_represented"
                    member["prepared_duplicate_of"] = seen[(member["sha256"], caption)]
                origin = {"kind": "policy", "policy": POLICY, "reason": reason}
            if decision == "include" and caption:
                seen.setdefault((member["sha256"], caption), path)
        member["review_decision"] = decision
        member["decision_origin"] = origin
        decisions.append(
            {
                "source_path": path,
                "sha256": member["sha256"],
                "previous_decision": saved,
                "decision": decision,
                "origin": origin,
                "duplicate_of": member.get("prepared_duplicate_of"),
            }
        )

    grouped = {}
    for path, member in sorted(members.items()):
        grouped.setdefault(find(path), []).append(member)
    prepared = [
        {
            "group_id": _identity([[m["source_path"], m["sha256"]] for m in values]),
            "members": values,
        }
        for values in grouped.values()
    ]
    prepared.sort(key=lambda g: g["group_id"])
    counts = Counter(m["review_decision"] for m in members.values())
    if original_summary.get("conflicts") or context.similarity_errors:
        blockers.append({"code": "unresolved_group_integrity", "summary": original_summary})
    if not counts["include"]:
        blockers.append({"code": "no_usable_images"})
    summary = {
        **original_summary,
        "groups": len(prepared),
        "image_decisions": dict(counts),
        "review_complete": original_summary["review_complete"],
        "preparation_complete": not blockers,
        "preparation_policy": POLICY,
        "provisional_split_constraints": sum(x["applied"] for x in constraints),
        "policy_exclusions": dict(
            Counter(
                d["origin"]["reason"]
                for d in decisions
                if d["decision"] == "exclude" and d["origin"]["kind"] == "policy"
            )
        ),
        "blockers": blockers,
        "human_accepted": False,
        "training_ready": False,
        "annotations": annotation_summary(members.values()),
    }
    evidence = {
        "schema_version": 1,
        "policy": POLICY,
        "source": str(source),
        "base_groups_run": str(groups_run.resolve()),
        "base_groups_sha256": file_sha256(groups_run / "run.json"),
        "caption_run": str(captions_run.resolve()) if captions_run else None,
        "caption_manifest_sha256": draft_meta["manifest_sha256"] if draft_meta else None,
        "decisions": decisions,
        "split_constraints": constraints,
        "captions": effective_captions,
        "human_accepted": False,
        "review_store_modified": False,
    }
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-preparation-", dir=root))
    (staging / "groups.jsonl").write_text(
        "".join(json.dumps(g, ensure_ascii=False, sort_keys=True) + "\n" for g in prepared),
        encoding="utf-8",
        newline="\n",
    )
    (staging / "reviews.json").write_bytes(artifacts["reviews.json"])
    atomic_json(staging / "summary.json", summary)
    atomic_json(staging / "preparation.json", evidence)
    (staging / "base-groups.jsonl").write_bytes(artifacts["groups.jsonl"])
    (staging / "base-groups-run.json").write_bytes((groups_run / "run.json").read_bytes())
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-prepared-" + uuid4().hex[:8]
    metadata = {
        **meta,
        "run_id": run_id,
        "preparation_policy": POLICY,
        "human_accepted": False,
        "pipeline_version": __version__,
        "started_at": clock.started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "processing_history": processing_history(meta, draft_meta),
        "metrics": clock.measure(staging),
        "files": {p.name: file_sha256(p) for p in staging.iterdir() if p.is_file()},
    }
    atomic_json(staging / "run.json", metadata)
    final = root / run_id
    publish_directory(staging, final)
    return final, summary


def verify_preparation(meta: dict, groups: list[dict], artifacts: dict[str, bytes]) -> None:
    """Check policy attribution and membership independently of mutable source/review stores."""
    from hashlib import sha256

    summary = json.loads(artifacts["summary.json"])
    evidence = json.loads(artifacts["preparation.json"])
    base_meta = json.loads(artifacts["base-groups-run.json"])
    base = [json.loads(line) for line in artifacts["base-groups.jsonl"].splitlines()]
    if (
        meta.get("preparation_policy") != POLICY
        or meta.get("human_accepted") is not False
        or summary.get("human_accepted") is not False
        or evidence.get("policy") != POLICY
        or evidence.get("human_accepted") is not False
        or evidence.get("review_store_modified") is not False
        or evidence.get("source") != meta.get("source")
        or sha256(artifacts["base-groups-run.json"]).hexdigest()
        != evidence.get("base_groups_sha256")
        or sha256(artifacts["base-groups.jsonl"]).hexdigest()
        != base_meta.get("files", {}).get("groups.jsonl")
        or sha256(artifacts["reviews.json"]).hexdigest()
        != base_meta.get("files", {}).get("reviews.json")
    ):
        raise ValueError("Invalid preparation policy provenance")
    original = {m["source_path"]: m for g in base for m in g["members"]}
    current = {m["source_path"]: m for g in groups for m in g["members"]}
    decisions = {d["source_path"]: d for d in evidence["decisions"]}
    if original.keys() != current.keys() or current.keys() != decisions.keys():
        raise ValueError("Preparation membership differs from its original snapshot")
    for path, member in current.items():
        before, decision = original[path], decisions[path]
        if (
            member["sha256"] != before["sha256"]
            or decision["sha256"] != member["sha256"]
            or decision["previous_decision"] != before["review_decision"]
            or decision["decision"] != member["review_decision"]
            or decision["origin"] != member.get("decision_origin")
            or before["review_decision"] != "unreviewed"
            and before["review_decision"] != member["review_decision"]
        ):
            raise ValueError("Preparation decision differs from its frozen evidence")
        for key in ("caption_override", "labels", "subset", "subset_origin"):
            if member.get(key) != before.get(key):
                raise ValueError("Preparation changed an existing annotation or caption override")
        origin = member["decision_origin"]
        if before["review_decision"] != "unreviewed":
            if origin != {"kind": "saved_review", "reason": before.get("reason", "")}:
                raise ValueError("Preparation misattributed a saved review")
        elif origin.get("kind") != "policy" or origin.get("policy") != POLICY:
            raise ValueError("Preparation decision lacks its automatic policy attribution")
    assignments = {m["source_path"]: g["group_id"] for g in groups for m in g["members"]}
    if any(len({assignments[m["source_path"]] for m in g["members"]}) != 1 for g in base):
        raise ValueError("Preparation split an existing related group")
    for edge in evidence["split_constraints"]:
        if edge["applied"] and (
            assignments[edge["left_source_path"]] != assignments[edge["right_source_path"]]
        ):
            raise ValueError("Preparation split a provisional constraint")
    if summary["image_decisions"] != dict(Counter(m["review_decision"] for m in current.values())):
        raise ValueError("Preparation decision counts do not reconcile")
