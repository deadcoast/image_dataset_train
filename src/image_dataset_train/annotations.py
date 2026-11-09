"""Explicit human labels and subset choices; never inferred from captions or paths."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable


def annotation_name(value: str) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Annotation names must be text without control characters")
    name = unicodedata.normalize("NFC", " ".join(value.split()).casefold())
    if not name:
        raise ValueError("Annotation names cannot be empty")
    return name


def label_names(values: list[str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("Labels must be a list of names")
    return sorted({annotation_name(value) for value in values})


def annotation_fields(record: dict) -> dict:
    """Old records remain unannotated; explicit empty choices remain reviewed."""
    return {
        "labels": label_names(record.get("labels", [])),
        "subset": annotation_name(record["subset"]) if record.get("subset") is not None else None,
        "labels_reviewed": record.get("labels_reviewed", "labels" in record),
        "subset_reviewed": record.get("subset_reviewed", "subset" in record),
    }


def annotation_summary(records: Iterable[dict]) -> dict:
    labels, subsets = Counter(), Counter()
    images = labels_reviewed = subset_reviewed = unassigned = 0
    for record in records:
        fields = annotation_fields(record)
        images += 1
        labels_reviewed += bool(fields["labels_reviewed"])
        subset_reviewed += bool(fields["subset_reviewed"])
        labels.update(fields["labels"])
        if fields["subset"] is None:
            unassigned += 1
        else:
            subsets[fields["subset"]] += 1
    return {
        "images": images,
        "labels_reviewed": labels_reviewed,
        "subset_reviewed": subset_reviewed,
        "labels": dict(sorted(labels.items())),
        "subsets": dict(sorted(subsets.items())),
        "unassigned_subset": unassigned,
    }
