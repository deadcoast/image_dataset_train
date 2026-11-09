"""Snapshot-scoped content summaries from saved observations, never caption guesses."""

from __future__ import annotations

import math
from collections import Counter

from image_dataset_train.annotations import annotation_summary
from image_dataset_train.execution import membership_digest


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


def reconcile_counts(
    groups: list[dict],
    members: list[dict],
    entries: list[dict],
    drafts: dict,
    group_meta: dict,
    group_summary: dict,
    draft_meta: dict | None,
    *,
    exported: bool,
) -> dict:
    """Compare populations by occurrence identity as well as counts; expose every loss."""
    grouped = [{**m, "group_id": g["group_id"]} for g in groups for m in g["members"]]
    included = [m for m in grouped if m["review_decision"] == "include"]
    decisions = Counter(m["review_decision"] for m in grouped)
    intake = group_meta.get("intake")
    checks, unavailable = [], []

    def check(name, expected, actual):
        checks.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "difference": actual - expected if type(expected) is int else None,
                "matches": expected == actual,
            }
        )

    if intake is None:
        unavailable.append(
            "Intake counts and eligible membership were not captured in this snapshot"
        )
    else:
        check("Intake file kinds", intake["files"], sum(intake["kinds"].values()))
        check("Intake image decisions", intake["images"], sum(intake["image_decisions"].values()))
        check(
            "Eligible + ineligible intake images",
            intake["images"],
            intake["eligible_images"] + intake["ineligible_images"],
        )
        check("Eligible intake → grouped images", intake["eligible_images"], len(grouped))
        check(
            "Eligible intake → grouped identities",
            intake["eligible_membership_sha256"],
            membership_digest(grouped),
        )
    check("Group summary images", group_summary["images"], len(grouped))
    check("Group summary groups", group_summary["groups"], len(groups))
    for decision in ("include", "exclude", "unreviewed"):
        check(
            "Review decision: " + decision,
            group_summary["image_decisions"].get(decision, 0),
            decisions[decision],
        )
    expected = included if exported else grouped
    check("Reviewed population → snapshot images", len(expected), len(members))
    check(
        "Reviewed population → snapshot identities",
        membership_digest(expected),
        membership_digest(members),
    )
    check("Snapshot → QA images", len(members), len(entries))
    check("Snapshot → QA identities", membership_digest(members), membership_digest(entries))
    splits = Counter(e["split"] for e in entries if e["decision"] == "include")
    check(
        "Included images → train + validation",
        len(included),
        splits["train"] + splits["validation"],
    )
    tagged = sum((m["source_path"], m["sha256"]) in drafts for m in members)
    tag_counts = (draft_meta or {}).get("counts")
    if tag_counts:
        check(
            "Tagging run decisions", tag_counts["image_rows"], sum(tag_counts["decisions"].values())
        )
        check("Tagging run tagged rows", tag_counts["decisions"].get("tagged", 0), len(drafts))
    elif draft_meta is not None:
        unavailable.append("Tagging-run decision totals were not captured in this snapshot")
    captions = sum(bool(e["caption"].strip()) for e in entries)
    if exported:
        check("Export image paths", len(included), len({m["image_path"] for m in members}))
        check("Export caption paths", len(included), len({m["caption_path"] for m in members}))
        check("Export nonempty captions", len(included), captions)
    return {
        "status": "mismatch"
        if any(not c["matches"] for c in checks)
        else "partial"
        if unavailable
        else "reconciled",
        "intake": intake,
        "review": {"images": len(grouped), "groups": len(groups), "decisions": dict(decisions)},
        "snapshot": {
            "images": len(members),
            "unique_images": len({m["sha256"] for m in members}),
            "tagged_images": tagged,
            "without_tagged_evidence": len(members) - tagged,
            "tagged_outside_snapshot": len(drafts) - tagged,
            "captions": captions,
            "missing_captions": len(entries) - captions,
            "split_images": dict(splits),
            "exported_pairs": len(members) if exported else None,
        },
        "tagging_run": tag_counts,
        "checks": checks,
        "unavailable": unavailable,
    }
