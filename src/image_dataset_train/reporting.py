"""Snapshot-scoped content summaries from saved observations, never caption guesses."""

from __future__ import annotations

import math
from collections import Counter

from image_dataset_train.annotations import annotation_summary


def _tags(rows: list[dict], field: str, images: int) -> dict:
    available = [row for row in rows if isinstance(row.get(field), list)]
    counts = Counter()
    for row in available:
        # An occurrence contributes at most once per tag; exact-byte aliases remain occurrences.
        counts.update({(tag["name"], tag["category"]) for tag in row[field]})
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "available_images": len(available),
        "unavailable_images": images - len(available),
        "distinct_tags": len(counts),
        "top_tags": [
            {"name": name, "category": category, "images": count}
            for (name, category), count in ranked[:100]
        ],
    }


def _ratings(rows: list[dict], images: int) -> dict:
    counts = Counter()
    available = tied = 0
    for row in rows:
        scores = row.get("ratings")
        if (
            not isinstance(scores, dict)
            or not scores
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 1
                for value in scores.values()
            )
        ):
            continue
        available += 1
        maximum = max(scores.values())
        winners = [name for name, score in scores.items() if score == maximum]
        if len(winners) == 1:
            counts[winners[0]] += 1
        else:
            tied += 1
    return {
        "available_images": available,
        "unavailable_images": images - available,
        "tied_images": tied,
        "counts": dict(sorted(counts.items())),
    }


def _scope(members: list[dict], drafts: dict) -> dict:
    rows = [
        drafts[(m["source_path"], m["sha256"])]
        for m in members
        if (m["source_path"], m["sha256"]) in drafts
    ]
    compositions = Counter(row["composition"] for row in rows if "composition" in row)
    proposals, unmatched, ambiguous, available = Counter(), 0, 0, 0
    for row in rows:
        proposal = row.get("subset_proposal")
        if not isinstance(proposal, dict):
            continue
        available += 1
        if proposal.get("value") is not None:
            proposals[proposal["value"]] += 1
        elif proposal.get("matches"):
            ambiguous += 1
        else:
            unmatched += 1
    return {
        "images": len(members),
        "unique_images": len({m["sha256"] for m in members}),
        "decisions": dict(sorted(Counter(m["review_decision"] for m in members).items())),
        "tagged_images": len(rows),
        "untagged_images": len(members) - len(rows),
        "reviewed_annotations": annotation_summary(members),
        "composition": {
            "counts": dict(sorted(compositions.items())),
            "unavailable_images": len(members) - compositions.total(),
        },
        "subset_proposals": {
            "counts": dict(sorted(proposals.items())),
            "unmatched_images": unmatched,
            "ambiguous_images": ambiguous,
            "unavailable_images": len(members) - available,
        },
        "ratings": _ratings(rows, len(members)),
        "observed_tags": _tags(rows, "observed_tags", len(members)),
        "selected_tags": _tags(rows, "selected_tags", len(members)),
    }


def content_report(
    members: list[dict],
    drafts: dict,
    metadata: dict | None,
    *,
    evidence_source: str,
    manifest_available: bool,
) -> dict:
    """Keep whole-snapshot and explicitly included populations separate and reproducible."""
    provenance = None
    if metadata is not None:
        provenance = {
            key: metadata[key]
            for key in (
                "run_id",
                "stage",
                "parent_run",
                "pipeline_version",
                "manifest_sha256",
                "model",
                "runtime",
                "requested_device",
                "provider_fallback",
                "preprocessing",
                "cache_namespace",
                "labels_sha256",
                "score_index_sha256",
                "caption_version",
                "caption_rules_sha256",
                "caption_rules",
                "default_general_threshold",
            )
            if key in metadata
        }
    return {
        "schema_version": 1,
        "count_unit": "source_occurrence",
        "evidence_source": evidence_source,
        "manifest_available": manifest_available,
        "provenance": provenance,
        "scopes": {
            "snapshot": _scope(members, drafts),
            "included": _scope([m for m in members if m["review_decision"] == "include"], drafts),
        },
    }
