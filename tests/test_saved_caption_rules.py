"""One checked saved-rule interpretation across evaluation, comparison and replay."""

import copy
import json
from dataclasses import asdict, replace

import pytest
from test_label_evaluation import evaluation_pilot as evaluation_pilot
from test_label_review_ui import changes, reveal

from image_dataset_train.caption_explanations import explain_caption
from image_dataset_train.captions import CAPTION_VERSION, rules_identity
from image_dataset_train.config import CaptionConfig, SubsetRule
from image_dataset_train.label_review_ui import LabelReviewSession
from image_dataset_train.model_bundle import Label
from image_dataset_train.saved_caption_rules import (
    SavedCaptionRulesUnavailable,
    resolve_saved_caption_rules,
)
from image_dataset_train.tagging_evaluation import evaluate_labels

LABELS = [Label(0, "blue_hair", 0), Label(1, "character", 4), Label(2, "general", 9)]


def metadata(rules=None, default=0.5):
    rules = rules or CaptionConfig(
        drop_tags=["blue_hair", "blue_hair"],
        force_tags=["literal phrase", "literal phrase"],
        subset_rules=[{"name": "blue", "all_tags": ["blue_hair"]}],
    )
    return {
        "caption_version": CAPTION_VERSION,
        "caption_rules": asdict(rules),
        "default_general_threshold": default,
        "caption_rules_sha256": rules_identity(rules, default),
    }


def test_complete_rules_preserve_publisher_order_duplicates_and_saved_default():
    saved = metadata()
    before = copy.deepcopy(saved)
    resolved = resolve_saved_caption_rules(saved, LABELS)
    assert asdict(resolved.rules) == saved["caption_rules"]
    assert resolved.thresholds(LABELS[:2]) == {"blue_hair": 0.5, "character": 0.85}
    assert resolved.rules_sha256 == saved["caption_rules_sha256"]
    assert resolved.caption_version == CAPTION_VERSION
    assert saved == before
    saved["caption_rules"]["drop_tags"].clear()
    assert resolved.rules.drop_tags == before["caption_rules"]["drop_tags"]


@pytest.mark.parametrize("field", list(metadata()))
def test_absent_top_level_evidence_is_explicitly_unavailable(field):
    saved = metadata()
    saved.pop(field)
    with pytest.raises(SavedCaptionRulesUnavailable, match=field) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert caught.value.reason_code == "missing_rules"


@pytest.mark.parametrize("field", list(CaptionConfig.__dataclass_fields__))
def test_missing_caption_field_never_acquires_current_default(field):
    saved = metadata()
    saved["caption_rules"].pop(field)
    with pytest.raises(SavedCaptionRulesUnavailable, match=field):
        resolve_saved_caption_rules(saved, LABELS)


@pytest.mark.parametrize("field", list(SubsetRule.__dataclass_fields__))
def test_missing_nested_subset_field_never_acquires_current_default(field):
    saved = metadata()
    saved["caption_rules"]["subset_rules"][0].pop(field)
    with pytest.raises(SavedCaptionRulesUnavailable, match=field):
        resolve_saved_caption_rules(saved, LABELS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("caption_version", None),
        ("caption_version", True),
        ("caption_version", 2),
        ("caption_version", ""),
        ("caption_version", " wd-caption-v2"),
        ("caption_rules", None),
        ("caption_rules", []),
        ("caption_rules", "{}"),
        ("default_general_threshold", None),
        ("default_general_threshold", True),
        ("default_general_threshold", "0.5"),
        ("default_general_threshold", float("nan")),
        ("default_general_threshold", float("inf")),
        ("default_general_threshold", -0.01),
        ("default_general_threshold", 1.01),
        ("caption_rules_sha256", None),
        ("caption_rules_sha256", True),
        ("caption_rules_sha256", "A" * 64),
        ("caption_rules_sha256", "x" * 64),
        ("caption_rules_sha256", "0" * 63),
        ("caption_rules_sha256", "0" * 64),
    ],
)
def test_present_malformed_evidence_rejects_instead_of_legacy_fallback(field, value):
    saved = metadata()
    saved[field] = value
    with pytest.raises(ValueError) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert not isinstance(caught.value, SavedCaptionRulesUnavailable)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("general_threshold", True),
        ("character_threshold", None),
        ("uncertainty_margin", "0.05"),
        ("uncertainty_margin", float("nan")),
        ("keep_characters", 1),
        ("drop_tags", None),
        ("drop_tags", ("blue_hair",)),
        ("drop_tags", [None]),
        ("drop_tags", ["unknown"]),
        ("tag_thresholds", []),
        ("tag_thresholds", {"blue_hair": False}),
        ("tag_thresholds", {"unknown": 0.5}),
        ("trigger", None),
        ("trigger", "not, a phrase"),
        ("trigger", " padded "),
        ("force_tags", "phrase"),
        ("force_tags", ["two  spaces"]),
        ("force_tags", [True]),
        ("subset_rules", None),
        ("subset_rules", [None]),
        ("unknown_field", False),
    ],
)
def test_malformed_present_rule_fields_reject(field, value):
    saved = metadata()
    saved["caption_rules"][field] = value
    with pytest.raises(ValueError) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert not isinstance(caught.value, SavedCaptionRulesUnavailable)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", None),
        ("name", "Blue"),
        ("name", " two spaces "),
        ("all_tags", None),
        ("all_tags", "blue_hair"),
        ("any_tags", [False]),
        ("none_tags", ["blue_hair"]),
        ("expect_tags", ["unknown"]),
        ("expect_tags", ["general"]),
        ("unknown_field", []),
    ],
)
def test_malformed_nested_subset_fields_reject(field, value):
    saved = metadata()
    saved["caption_rules"]["subset_rules"][0][field] = value
    with pytest.raises(ValueError) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert not isinstance(caught.value, SavedCaptionRulesUnavailable)


def test_omission_cannot_hide_present_malformed_values():
    saved = metadata()
    saved.pop("caption_rules_sha256")
    saved["caption_rules"].pop("general_threshold")
    saved["caption_rules"]["keep_characters"] = 0
    with pytest.raises(ValueError, match="boolean") as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert not isinstance(caught.value, SavedCaptionRulesUnavailable)


@pytest.mark.parametrize("version", ["wd-caption-v1", "future-caption-v999"])
def test_unsupported_recorded_engine_is_not_replayed(version):
    saved = metadata()
    saved["caption_version"] = version
    with pytest.raises(SavedCaptionRulesUnavailable) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert caught.value.reason_code == "unsupported_caption_version"


def test_future_engine_grammar_is_not_checked_against_current_rule_fields():
    saved = metadata()
    saved["caption_version"] = "future-caption-v999"
    saved["caption_rules"] = {"future_field": {"policy": ["new semantics"]}}
    with pytest.raises(SavedCaptionRulesUnavailable) as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert caught.value.reason_code == "unsupported_caption_version"


@pytest.mark.parametrize("missing", ["caption_rules_sha256", "default_general_threshold"])
def test_missing_identity_cannot_hide_invalid_present_vocabulary(missing):
    saved = metadata()
    saved.pop(missing)
    saved["caption_rules"]["drop_tags"] = ["unknown"]
    with pytest.raises(ValueError, match="unknown raw tags") as caught:
        resolve_saved_caption_rules(saved, LABELS)
    assert not isinstance(caught.value, SavedCaptionRulesUnavailable)


def test_saved_default_is_part_of_digest_even_with_explicit_general_cutoff():
    saved = metadata(CaptionConfig(general_threshold=0.75))
    saved["default_general_threshold"] = 0.25
    with pytest.raises(ValueError, match="identity does not match"):
        resolve_saved_caption_rules(saved, LABELS)


def test_content_cutoffs_are_independent_from_caption_suppression():
    rules = CaptionConfig(
        general_threshold=0.75,
        character_threshold=0.875,
        keep_characters=False,
        drop_tags=["blue_hair", "character"],
        tag_thresholds={"character": 0.25},
    )
    resolved = resolve_saved_caption_rules(metadata(rules, default=0.125), LABELS)
    assert resolved.thresholds(LABELS[:2]) == {"blue_hair": 0.75, "character": 0.25}


def damage_rules(meta, damage):
    if damage == "absent":
        meta.pop("caption_rules")
    elif damage == "incomplete":
        meta["caption_rules"].pop("character_threshold")
    elif damage == "null":
        meta["caption_rules"] = None
    elif damage == "unsupported":
        meta["caption_version"] = "wd-caption-v1"
    elif damage == "null_version":
        meta["caption_version"] = None
    elif damage == "default_boolean":
        meta["default_general_threshold"] = False
    elif damage == "digest":
        meta["caption_rules_sha256"] = "0" * 64
    elif damage == "canonical":
        meta["caption_rules"]["trigger"] = " hidden normalization "
    elif damage == "vocabulary":
        meta["caption_rules"]["drop_tags"] = ["not_in_the_saved_labels"]


@pytest.mark.parametrize(
    "damage",
    [
        "absent",
        "incomplete",
        "null",
        "unsupported",
        "null_version",
        "default_boolean",
        "digest",
        "canonical",
        "vocabulary",
    ],
)
def test_consumers_agree_and_failures_preserve_judgments_and_outputs(evaluation_pilot, damage):
    config, _, good, workspace, factory = evaluation_pilot
    broken = factory(model="second-saved-model")
    initial = LabelReviewSession(config, workspace)
    content = next(iter(initial.store.members))
    initial.save(changes(initial, content))
    meta = json.loads((broken / "run.json").read_bytes())
    damage_rules(meta, damage)
    (broken / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    session = LabelReviewSession(config, workspace, [good, broken])
    before = (workspace / "judgments.json").read_bytes()
    outputs = set(config.runs.iterdir())
    with pytest.raises(ValueError) as evaluation_error:
        evaluate_labels(config, workspace, [good, broken], include_assistant=True)
    with pytest.raises(ValueError) as comparison_error:
        reveal(session, content)
    assert str(evaluation_error.value) == str(comparison_error.value)
    source_path = session.store.members[content]["aliases"][0]["source_path"]
    if damage in {"absent", "incomplete", "unsupported"}:
        result = explain_caption(broken, source_path)
        assert result["status"] == "unavailable"
        assert result["reason"] == str(evaluation_error.value)
        assert result["reason_code"] == evaluation_error.value.reason_code
    else:
        with pytest.raises(ValueError) as explanation_error:
            explain_caption(broken, source_path)
        assert str(explanation_error.value) == str(evaluation_error.value)
    assert (workspace / "judgments.json").read_bytes() == before
    assert set(config.runs.iterdir()) == outputs


def test_consumer_threshold_parity_uses_saved_rules_even_when_current_settings_differ(
    evaluation_pilot,
):
    config, _, _, workspace, factory = evaluation_pilot
    saved = factory(
        rules=CaptionConfig(tag_thresholds={"blue_hair": 0.25}, drop_tags=["blue_hair"])
    )
    current = replace(config, captions=CaptionConfig(general_threshold=0.99))
    session = LabelReviewSession(current, workspace, [saved])
    content = next(iter(session.store.members))
    session.save(changes(session, content))
    result = reveal(session, content)
    assert result["models"][0]["thresholds"] == {"blue_hair": 0.25, "red_eyes": 0.5}
    source_path = session.store.members[content]["aliases"][0]["source_path"]
    explanation = explain_caption(saved, source_path, tags=["blue_hair", "red_eyes"])
    tags = {tag["name"]: tag for tag in explanation["tags"]}
    assert tags["blue_hair"]["observed"] and not tags["blue_hair"]["selected"]
    assert tags["blue_hair"]["reasons"] == ["explicit_drop"]
    assert tags["red_eyes"]["observed"] is False  # Equality is absent, not >=.
    config.source.rename(config.source.with_name("offline-originals"))
    _, measured = evaluate_labels(current, workspace, [saved], include_assistant=True)
    for name, label in measured["models"][0]["labels"].items():
        assert label["baseline_threshold"] == tags[name]["threshold"]
    assert explanation["source_files_read"] is False
