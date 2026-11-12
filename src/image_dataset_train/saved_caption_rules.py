"""Validate recorded caption semantics without consulting current model settings."""

from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict, dataclass

from image_dataset_train.annotations import annotation_name
from image_dataset_train.captions import CAPTION_VERSION, check_rules, rules_identity
from image_dataset_train.config import CaptionConfig, SubsetRule, _caption_phrase, _probability
from image_dataset_train.model_bundle import Label


class SavedCaptionRulesUnavailable(ValueError):
    """Historical evidence is absent or belongs to an unsupported rule engine."""

    def __init__(self, reason_code: str, reason: str):
        self.reason_code = reason_code
        super().__init__(reason)


@dataclass(frozen=True)
class SavedCaptionRules:
    rules: CaptionConfig
    default_general_threshold: float
    rules_sha256: str
    caption_version: str

    def thresholds(self, labels: Iterable[Label]) -> dict[str, float]:
        """Raw-score cutoffs, independent of caption drop/keep decisions."""
        general = self.rules.general_threshold
        if general is None:
            general = self.default_general_threshold
        return {
            label.name: self.rules.tag_thresholds.get(
                label.name, self.rules.character_threshold if label.category == 4 else general
            )
            for label in labels
        }


def _raw_tags(values: object, name: str) -> None:
    if type(values) is not list or any(type(tag) is not str or not tag.strip() for tag in values):
        raise ValueError(f"Saved caption {name} must be an array of nonempty raw tag names")


def _recorded_rules(value: object) -> tuple[CaptionConfig | None, list[str]]:
    if type(value) is not dict:
        raise ValueError("Saved caption rules must be an object")
    fields = set(CaptionConfig.__dataclass_fields__)
    if value.keys() - fields:
        raise ValueError("Saved caption rules contain unsupported fields")
    missing = [f"caption_rules.{name}" for name in sorted(fields - value.keys())]
    # Validate present evidence before reporting omissions. Incomplete records may
    # never conceal malformed values or acquire semantics from constructor defaults.
    for name in ("general_threshold", "character_threshold", "uncertainty_margin"):
        if name in value and not (name == "general_threshold" and value[name] is None):
            _probability(value[name], f"saved caption {name}")
    if "keep_characters" in value and type(value["keep_characters"]) is not bool:
        raise ValueError("Saved caption keep_characters must be boolean")
    if "drop_tags" in value:
        _raw_tags(value["drop_tags"], "drop_tags")
    if "tag_thresholds" in value:
        thresholds = value["tag_thresholds"]
        if type(thresholds) is not dict:
            raise ValueError("Saved caption tag_thresholds must be an object")
        for tag, threshold in thresholds.items():
            if type(tag) is not str or not tag.strip():
                raise ValueError("Saved caption tag_thresholds keys must be raw tag names")
            _probability(threshold, f"saved caption tag_thresholds.{tag}")
    if (
        "trigger" in value
        and _caption_phrase(value["trigger"], "saved trigger", empty=True) != value["trigger"]
    ):
        raise ValueError("Saved caption trigger is not canonical")
    if "force_tags" in value:
        if type(value["force_tags"]) is not list:
            raise ValueError("Saved caption force_tags must be an array")
        for phrase in value["force_tags"]:
            if _caption_phrase(phrase, "saved force_tags") != phrase:
                raise ValueError("Saved caption force_tags are not canonical")
    if "subset_rules" in value:
        if type(value["subset_rules"]) is not list:
            raise ValueError("Saved caption subset_rules must be an array")
        subset_fields = set(SubsetRule.__dataclass_fields__)
        for index, subset in enumerate(value["subset_rules"]):
            if type(subset) is not dict or subset.keys() - subset_fields:
                raise ValueError("Saved caption subset rules must contain supported rule objects")
            missing.extend(
                f"caption_rules.subset_rules[{index}].{name}"
                for name in sorted(subset_fields - subset.keys())
            )
            if "name" in subset and annotation_name(subset["name"]) != subset["name"]:
                raise ValueError("Saved caption subset name is not canonical")
            for name in subset_fields - {"name"}:
                if name in subset:
                    _raw_tags(subset[name], f"subset_rules[{index}].{name}")
            if subset_fields <= subset.keys():
                SubsetRule(**subset)
    if missing:
        return None, missing
    rules = CaptionConfig(**deepcopy(value))
    if json.dumps(asdict(rules), sort_keys=True, allow_nan=False) != json.dumps(
        value, sort_keys=True, allow_nan=False
    ):
        raise ValueError("Saved caption rules are not in their recorded canonical form")
    return rules, []


def resolve_saved_caption_rules(metadata: dict, labels: list[Label]) -> SavedCaptionRules:
    """Check complete current evidence, or distinguish missing/unsupported history.

    Only the recorded version, complete rules, default threshold and vocabulary
    determine interpretation. Malformed present evidence is never a legacy fallback.
    """
    if type(metadata) is not dict:
        raise ValueError("Saved caption metadata must be an object")
    fields = {
        "caption_version",
        "caption_rules",
        "default_general_threshold",
        "caption_rules_sha256",
    }
    missing = sorted(fields - metadata.keys())
    if "caption_version" in metadata:
        version = metadata["caption_version"]
        if type(version) is not str or not version or version.strip() != version:
            raise ValueError("Saved caption_version must be a nonempty version string")
    if "default_general_threshold" in metadata:
        _probability(metadata["default_general_threshold"], "saved default_general_threshold")
    if "caption_rules_sha256" in metadata:
        digest = metadata["caption_rules_sha256"]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Saved caption rule identity must be a lowercase SHA-256 digest")
    if "caption_rules" in metadata and type(metadata["caption_rules"]) is not dict:
        raise ValueError("Saved caption rules must be an object")
    # A different engine may have a different grammar. Validate the shared
    # envelope, but never apply today's rule fields or normalization to it.
    if "caption_version" in metadata and metadata["caption_version"] != CAPTION_VERSION:
        raise SavedCaptionRulesUnavailable(
            "unsupported_caption_version",
            f"Saved caption version {metadata['caption_version']!r} cannot be interpreted "
            "by the current rule engine.",
        )
    rules = None
    if "caption_rules" in metadata:
        rules, omissions = _recorded_rules(metadata["caption_rules"])
        missing.extend(omissions)
    if rules is not None:
        check_rules(labels, rules)
    if missing:
        raise SavedCaptionRulesUnavailable(
            "missing_rules", "Saved caption rules are incomplete; missing: " + ", ".join(missing)
        )
    assert rules is not None
    default = metadata["default_general_threshold"]
    if rules_identity(rules, default) != metadata["caption_rules_sha256"]:
        raise ValueError("Saved caption rule identity does not match its rules")
    return SavedCaptionRules(rules, default, metadata["caption_rules_sha256"], CAPTION_VERSION)
