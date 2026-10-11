"""Derive reviewable caption drafts from retained WD scores."""

from __future__ import annotations

import re
from dataclasses import asdict

import numpy as np

from image_dataset_train.config import CaptionConfig
from image_dataset_train.model_bundle import Label
from image_dataset_train.wd_tagger import validate_scores

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
CAPTION_VERSION = "wd-caption-v1"


def display_name(name: str) -> str:
    return name if name in KAOMOJI else name.replace("_", " ")


def check_rules(labels: list[Label], rules: CaptionConfig) -> None:
    available = {label.name for label in labels}
    unknown = (set(rules.drop_tags) | rules.tag_thresholds.keys()) - available
    if unknown:
        raise ValueError(f"caption rules reference unknown raw tags: {', '.join(sorted(unknown))}")


def caption_record(
    labels: list[Label], scores: np.ndarray, rules: CaptionConfig, default_threshold: float
) -> dict:
    validate_scores(scores, len(labels))
    threshold = default_threshold if rules.general_threshold is None else rules.general_threshold
    selected, uncertain, ratings = [], [], {}
    for label in labels:
        score = float(scores[label.index])
        if label.category == 9:
            ratings[label.name] = score
            continue
        if label.category == 4 and not rules.keep_characters:
            continue
        if label.name in rules.drop_tags:
            continue
        cutoff = rules.tag_thresholds.get(
            label.name, rules.character_threshold if label.category == 4 else threshold
        )
        item = {**asdict(label), "score": score, "threshold": cutoff}
        # Strict > matches the publisher demo. Scores are evidence, not calibrated certainty.
        if score > cutoff:
            selected.append(item)
        if rules.uncertainty_margin and abs(score - cutoff) <= rules.uncertainty_margin:
            uncertain.append(item)
    selected.sort(key=lambda item: (-item["score"], item["index"]))
    names = {item["name"] for item in selected}
    flags = []
    for noun in ("girl", "boy"):
        counts = [name for name in names if re.fullmatch(rf"\d+{noun}s?", name)]
        if len(counts) > 1:
            flags.append(f"conflicting_{noun}_counts")
    counts = [
        int(match.group(1))
        for name in names
        if (match := re.fullmatch(r"(\d+)(?:girls?|boys?)", name))
    ]
    if "solo" in names and (sum(counts) > 1 or {"multiple_girls", "multiple_boys"} & names):
        flags.append("solo_count_conflict")
    if not selected:
        flags.append("empty_caption")
    if uncertain:
        flags.append("near_threshold_tags")
    rendered, seen = [], set()
    for item in selected:
        name = display_name(item["name"])
        if name not in seen:
            rendered.append(name)
            seen.add(name)
    return {
        "caption": ", ".join(rendered),
        "selected_tags": selected,
        "ratings": ratings,
        "uncertain_tags": uncertain,
        "review_flags": flags,
        "effective_general_threshold": threshold,
    }
