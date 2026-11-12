"""Derive reviewable caption drafts from retained WD scores."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict

import numpy as np

from image_dataset_train.config import CaptionConfig
from image_dataset_train.model_bundle import Label
from image_dataset_train.score_validation import validate_scores

# Preserve underscores in emoticons; all other conversion is only for rendered text.
KAOMOJI = {
    "0_0",
    "(o)_(o)",
    "+_+",
    "+_-",
    "._.",
    "<o>_<o>",
    "<|>_<|>",
    "=_=",
    ">_<",
    "3_3",
    "6_9",
    ">_o",
    "@_@",
    "^_^",
    "o_o",
    "u_u",
    "x_x",
    "|_|",
    "||_||",
}
CAPTION_VERSION = "wd-caption-v2"
CAPTION_FIELDS = (
    "caption",
    "selected_tags",
    "observed_tags",
    "ratings",
    "uncertain_tags",
    "review_flags",
    "effective_general_threshold",
    "caption_path",
    "composition",
    "subset_proposal",
    "caption_additions",
    "caption_version",
    "caption_rules_sha256",
)


def rules_identity(rules: CaptionConfig, default_threshold: float) -> str:
    policy = {
        "version": CAPTION_VERSION,
        "rules": asdict(rules),
        "default_general_threshold": default_threshold,
    }
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def display_name(name: str) -> str:
    return name if name in KAOMOJI else name.replace("_", " ")


def check_rules(labels: list[Label], rules: CaptionConfig) -> None:
    available = {label.name for label in labels}
    unknown = (set(rules.drop_tags) | rules.tag_thresholds.keys()) - available
    for rule in rules.subset_rules:
        unknown.update(
            set(rule.all_tags + rule.any_tags + rule.none_tags + rule.expect_tags) - available
        )
    if unknown:
        raise ValueError(f"caption rules reference unknown raw tags: {', '.join(sorted(unknown))}")
    ratings = {label.name for label in labels if label.category == 9}
    if any(
        ratings & set(rule.all_tags + rule.any_tags + rule.none_tags + rule.expect_tags)
        for rule in rules.subset_rules
    ):
        raise ValueError("Subset predicates require content tags, not rating scores")


def _composition(names: set[str], flags: list[str]) -> str:
    counts = []
    for noun in ("girl", "boy"):
        values = [
            int(match.group(1))
            for name in names
            if (match := re.fullmatch(rf"(\d+){noun}s?", name))
        ]
        if len(values) > 1 or (1 in values and f"multiple_{noun}s" in names):
            flags.append(f"conflicting_{noun}_counts")
        counts.extend(values)
    multiple = sum(counts) > 1 or bool({"multiple_girls", "multiple_boys"} & names)
    if "solo" in names and multiple:
        flags.append("solo_count_conflict")
    if any(flag.startswith("conflicting_") for flag in flags) or "solo_count_conflict" in flags:
        return "unknown"
    if multiple:
        return "multiple_subjects"
    return "single_subject" if sum(counts) == 1 or "solo" in names else "unknown"


def _subset_proposal(
    names: set[str], rules: CaptionConfig, flags: list[str], trace: dict | None = None
) -> dict:
    matches, missing = [], {}
    for rule in rules.subset_rules:
        all_match = set(rule.all_tags) <= names
        any_match = not rule.any_tags or bool(set(rule.any_tags) & names)
        none_match = not set(rule.none_tags) & names
        matched = bool(all_match and any_match and none_match)
        if trace is not None:
            trace["subset_rules"].append(
                {
                    "name": rule.name,
                    "matched": matched,
                    "all_tags": {
                        "required": rule.all_tags,
                        "present": sorted(set(rule.all_tags) & names),
                        "missing": sorted(set(rule.all_tags) - names),
                        "passed": all_match,
                    },
                    "any_tags": {
                        "required": rule.any_tags,
                        "present": sorted(set(rule.any_tags) & names),
                        "missing": sorted(set(rule.any_tags) - names),
                        "passed": any_match,
                    },
                    "none_tags": {
                        "forbidden": rule.none_tags,
                        "present": sorted(set(rule.none_tags) & names),
                        "passed": none_match,
                    },
                    "expect_tags": {
                        "expected": rule.expect_tags,
                        "present": sorted(set(rule.expect_tags) & names),
                        "missing": sorted(set(rule.expect_tags) - names),
                        "applies": matched,
                    },
                }
            )
        if matched:
            matches.append(rule.name)
            absent = sorted(set(rule.expect_tags) - names)
            if absent:
                missing[rule.name] = absent
    if len(matches) > 1:
        flags.append("subset_rule_conflict")
    if missing:
        flags.append("subset_missing_expected_tags")
    return {
        "value": matches[0] if len(matches) == 1 else None,
        "matches": sorted(matches),
        "missing_tags": missing,
    }


def caption_record(
    labels: list[Label],
    scores: np.ndarray,
    rules: CaptionConfig,
    default_threshold: float,
    *,
    trace: dict | None = None,
) -> dict:
    """Render one caption; optional derived trace follows these same decisions."""
    validate_scores(scores, len(labels))
    if trace is not None:
        trace.clear()
        trace.update(tags=[], subset_rules=[], phrases=[])
    threshold = default_threshold if rules.general_threshold is None else rules.general_threshold
    selected, observed, uncertain, ratings = [], [], [], {}
    for label in labels:
        score = float(scores[label.index])
        if label.category == 9:
            ratings[label.name] = score
            if trace is not None:
                trace["tags"].append(
                    {
                        **asdict(label),
                        "score": score,
                        "threshold": None,
                        "threshold_source": None,
                        "observed": False,
                        "selected": False,
                        "near_threshold": False,
                        "reasons": ["rating_only"],
                        "phrase_status": "rating_only",
                    }
                )
            continue
        cutoff = rules.tag_thresholds.get(
            label.name, rules.character_threshold if label.category == 4 else threshold
        )
        item = {**asdict(label), "score": score, "threshold": cutoff}
        # Strict > matches the publisher demo. Scores are evidence, not calibrated certainty.
        if score > cutoff:
            observed.append(item)
            if label.name not in rules.drop_tags and (label.category != 4 or rules.keep_characters):
                selected.append(item)
        if rules.uncertainty_margin and abs(score - cutoff) <= rules.uncertainty_margin:
            uncertain.append(item)
        if trace is not None:
            reasons = []
            if score <= cutoff:
                reasons.append("below_or_equal_threshold")
            if label.name in rules.drop_tags:
                reasons.append("explicit_drop")
            if label.category == 4 and not rules.keep_characters:
                reasons.append("characters_disabled")
            trace["tags"].append(
                {
                    **item,
                    "threshold_source": (
                        "tag_override"
                        if label.name in rules.tag_thresholds
                        else "character_threshold"
                        if label.category == 4
                        else "general_threshold"
                        if rules.general_threshold is not None
                        else "default_general_threshold"
                    ),
                    "observed": score > cutoff,
                    "selected": not reasons,
                    "near_threshold": bool(
                        rules.uncertainty_margin and abs(score - cutoff) <= rules.uncertainty_margin
                    ),
                    "reasons": reasons or ["selected"],
                    "phrase_status": "not_selected" if reasons else "emitted",
                }
            )
    selected.sort(key=lambda item: (-item["score"], item["index"]))
    observed.sort(key=lambda item: (-item["score"], item["index"]))
    names = {item["name"] for item in observed}
    flags = []
    composition = _composition(names, flags)
    proposal = _subset_proposal(names, rules, flags, trace)
    if not selected:
        flags.append("no_scored_caption_tags")
    if uncertain:
        flags.append("near_threshold_tags")
    rendered, seen = [], set()
    phrases = (
        ([{"kind": "trigger", "text": rules.trigger}] if rules.trigger else [])
        + [
            {"kind": "tag", "name": item["name"], "text": display_name(item["name"])}
            for item in selected
        ]
        + [{"kind": "forced", "text": name} for name in rules.force_tags]
    )
    first_phrases = {}
    traced_tags = {item["name"]: item for item in trace["tags"]} if trace is not None else {}
    for index, phrase in enumerate(phrases):
        name = phrase["text"]
        duplicate = name.casefold() in seen
        if trace is not None:
            trace["phrases"].append(
                {
                    **phrase,
                    "position": index,
                    "status": "duplicate_phrase" if duplicate else "emitted",
                    "duplicate_of": first_phrases.get(name.casefold()),
                }
            )
            if phrase["kind"] == "tag":
                traced_tags[phrase["name"]]["phrase_status"] = (
                    "duplicate_phrase" if duplicate else "emitted"
                )
        first_phrases.setdefault(name.casefold(), index)
        if name.casefold() not in seen:
            rendered.append(name)
            seen.add(name.casefold())
    if not rendered:
        flags.append("empty_caption")
    return {
        "caption": ", ".join(rendered),
        "selected_tags": selected,
        "observed_tags": observed,
        "composition": composition,
        "subset_proposal": proposal,
        "caption_additions": {"trigger": rules.trigger, "force_tags": rules.force_tags},
        "caption_version": CAPTION_VERSION,
        "caption_rules_sha256": rules_identity(rules, default_threshold),
        "ratings": ratings,
        "uncertain_tags": uncertain,
        "review_flags": flags,
        "effective_general_threshold": threshold,
    }
