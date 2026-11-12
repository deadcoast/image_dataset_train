"""Explain a pinned draft from saved scores and rules, without inference or writes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from image_dataset_train.caption_comparison import _Reads
from image_dataset_train.captions import CAPTION_FIELDS, caption_record
from image_dataset_train.saved_caption_rules import (
    SavedCaptionRulesUnavailable,
    resolve_saved_caption_rules,
)
from image_dataset_train.scored_runs import ScoredRun

MAX_EXPLANATION_BYTES = 2 * 1024 * 1024


def explain_caption(
    run: Path,
    source_path: str,
    *,
    tags: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
    expected_run_sha256: str | None = None,
    expected_manifest_sha256: str | None = None,
    expected_source: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict:
    """Return a bounded tag trace; all conclusions describe the saved draft only.

    Omitted tag selectors return relevant evidence (observed/near-threshold tags,
    configured drops/overrides, subset inputs and ratings). Explicit selectors can
    inspect any raw label, including low-scoring labels omitted from that default.
    Historical rule versions are never replayed using today's defaults.
    """
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Caption explanation limit must be an integer between 1 and 200")
    if type(offset) is not int or offset < 0:
        raise ValueError("Caption explanation offset must be a nonnegative integer")
    if not isinstance(source_path, str) or not source_path:
        raise ValueError("Select an exact relative image path from the saved run")
    if tags is not None and (
        not isinstance(tags, list)
        or not 1 <= len(tags) <= 200
        or any(not isinstance(tag, str) or not tag or "\0" in tag for tag in tags)
        or len(set(tags)) != len(tags)
        or sum(len(tag) for tag in tags) > 65_536
    ):
        raise ValueError("Select between 1 and 200 unique exact raw tag names")

    reader = _Reads()
    run = Path(run).expanduser().absolute()
    raw = reader.read(run / "run.json", expected_run_sha256)
    meta = json.loads(raw)
    if not isinstance(meta, dict):
        raise ValueError("Caption explanation requires saved run metadata")
    for name, key in (
        ("manifest.jsonl", "manifest_sha256"),
        ("labels.json", "labels_sha256"),
        ("score_index.json", "score_index_sha256"),
    ):
        reader.read(run / name, meta.get(key))
    scored = ScoredRun(run)
    if scored.digest != hashlib.sha256(raw).hexdigest():
        raise ValueError("Caption run changed during inspection; inspect again")
    if (
        expected_manifest_sha256 is not None
        and scored.metadata["manifest_sha256"] != expected_manifest_sha256
    ):
        raise ValueError("Caption manifest differs from the selected snapshot")
    if expected_source is not None and scored.metadata["source"] != str(expected_source):
        raise ValueError("Caption run belongs to another source")
    row = next((item for item in scored.rows if item["source_path"] == source_path), None)
    if row is None:
        raise ValueError("Image is not in the selected caption run; use its exact relative path")
    if expected_sha256 is not None and row.get("sha256") != expected_sha256:
        raise ValueError("Caption image content differs from the selected snapshot")
    labels = {label.name for label in scored.labels}
    if tags is not None and (unknown := set(tags) - labels):
        raise ValueError("Unknown raw tag name(s): " + ", ".join(sorted(unknown)))
    result = {
        "schema_version": 1,
        "scope": "saved_draft",
        "run": str(scored.run),
        "run_sha256": scored.digest,
        "manifest_sha256": scored.metadata["manifest_sha256"],
        "source": scored.metadata["source"],
        "identity": {"source_path": source_path, "sha256": row.get("sha256")},
        "caption_version": meta.get("caption_version"),
        "rules_sha256": meta.get("caption_rules_sha256"),
        "inference_performed": False,
        "source_files_read": False,
        "human_accepted": False,
    }
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 65_536:
        raise ValueError("Saved caption identity exceeds the 64 KiB inspection limit")
    if not isinstance(row.get("decision"), str) or len(row["decision"]) > 128:
        raise ValueError("Invalid saved caption decision")

    def unavailable(code: str, reason: str) -> dict:
        reader.verify()
        return {
            **result,
            "status": "unavailable",
            "reason_code": code,
            "reason": reason,
            "evidence_sha256": dict(reader.hashes),
        }

    if row.get("decision") != "tagged":
        return unavailable(
            "not_scored", f"This saved image has no draft scores (decision: {row.get('decision')})."
        )
    try:
        saved_rules = resolve_saved_caption_rules(meta, scored.labels)
    except SavedCaptionRulesUnavailable as exc:
        return unavailable(exc.reason_code, str(exc))
    rules, default = saved_rules.rules, saved_rules.default_general_threshold
    artifact = scored.index[row["sha256"]]
    reader.read(run / artifact["path"], artifact["sha256"], limit=len(scored.labels) * 8 + 10_256)
    vector = scored.vector(row["sha256"])
    trace = {}
    replay = caption_record(scored.labels, vector, rules, default, trace=trace)
    missing = set(CAPTION_FIELDS) - {"caption_path"} - row.keys()
    if missing:
        return unavailable("missing_analysis", "The run did not retain complete caption analysis.")
    if any(
        json.dumps(row[field], sort_keys=True, ensure_ascii=False, allow_nan=False)
        != json.dumps(replay[field], sort_keys=True, ensure_ascii=False, allow_nan=False)
        for field in CAPTION_FIELDS
        if field != "caption_path"
    ):
        raise ValueError("Saved caption analysis does not match its pinned scores and rules")
    # The hashed manifest is authoritative. Loose draft TXT files are editable
    # conveniences; export also ignores their current contents when resolving drafts.
    configured = set(rules.drop_tags) | rules.tag_thresholds.keys()
    for rule in rules.subset_rules:
        configured.update(rule.all_tags + rule.any_tags + rule.none_tags + rule.expect_tags)
    requested = set(tags) if tags is not None else None
    relevant = [
        item
        for item in trace["tags"]
        if (
            item["name"] in requested
            if requested is not None
            else item["observed"]
            or item["near_threshold"]
            or item["category"] == 9
            or item["name"] in configured
        )
    ]
    # Stable label-index order makes repeated pages and explicit raw-tag lookups reproducible.
    summary = {
        "labels": len(trace["tags"]),
        "observed": len(replay["observed_tags"]),
        "selected": len(replay["selected_tags"]),
        "near_threshold": len(replay["uncertain_tags"]),
        "ratings": len(replay["ratings"]),
        "omitted": sum(not item["selected"] and item["category"] != 9 for item in trace["tags"]),
    }
    reader.verify()
    explanation = {
        **result,
        "status": "available",
        "caption": replay["caption"],
        "summary": summary,
        "tag_scope": "requested" if requested is not None else "relevant",
        "tags": relevant[offset : offset + limit],
        "total": len(relevant),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(relevant),
        "subset_rules": trace["subset_rules"],
        "subset_proposal": replay["subset_proposal"],
        "phrases": trace["phrases"],
        "additions": replay["caption_additions"],
        "composition": replay["composition"],
        "review_flags": replay["review_flags"],
        "uncertainty_margin": rules.uncertainty_margin,
        "evidence_sha256": dict(reader.hashes),
    }
    if len(json.dumps(explanation, ensure_ascii=False).encode("utf-8")) > MAX_EXPLANATION_BYTES:
        return unavailable(
            "explanation_too_large",
            "The complete rule explanation exceeds the 2 MiB response limit. "
            "Inspect the saved rules and manifest directly; no partial explanation is inferred.",
        )
    return explanation
