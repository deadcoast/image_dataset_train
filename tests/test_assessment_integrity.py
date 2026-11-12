"""Report-bound assessment replay and corruption-preserving write boundaries."""

import copy
import json
import shutil

import pytest
from test_exports import reviewed as reviewed

from image_dataset_train import assessments
from image_dataset_train.assessments import PilotAssessment
from image_dataset_train.qa import create_qa
from image_dataset_train.reviews import ReviewConflict


@pytest.fixture
def assessed(reviewed):
    config, groups, drafts = reviewed
    report, _ = create_qa(config, groups, captions_run=drafts, sample_size=1)
    store = PilotAssessment(config.reviews, report)
    entry = next(entry for entry in store.entries.values() if entry["pilot"])
    store.save(_payload(entry, 0))
    store.save(_payload(None, 1))
    return store, entry, config


def _payload(entry, revision, **changes):
    payload = {
        "expected_revision": revision,
        "reviewer": "Generated fixture reviewer",
        "reviewer_kind": "assistant",
        "notes": "Synthetic integrity test, not dataset acceptance",
        "verdict": "accepted",
    }
    if entry is not None:
        payload.update(
            image_id=entry["id"],
            caption_check="correct",
            label_checks={label: "correct" for label in entry["labels"]},
        )
    return {**payload, **changes}


def _write(store, state):
    store.path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return store.path.read_bytes()


def _reject_every_boundary(store, entry, state):
    original = _write(store, state)
    supplied = copy.deepcopy(state)
    paths = set(store.directory.iterdir())
    for action in (
        store.read,
        store.summary,
        lambda: store.summary(supplied),
        lambda: store.save(_payload(entry, 2)),
    ):
        with pytest.raises(ValueError):
            action()
        assert store.path.read_bytes() == original
        assert set(store.directory.iterdir()) == paths
    assert state == supplied


def test_current_only_attribution_cannot_create_human_acceptance(assessed):
    store, entry, _ = assessed
    state = store.read()
    assert not store.summary(state)["human_accepted"]
    for record in [*state["images"].values(), state["conclusion"]]:
        record["reviewer_kind"] = "human"
    assert {event["record"]["reviewer_kind"] for event in state["history"]} == {"assistant"}
    _reject_every_boundary(store, entry, state)


@pytest.mark.parametrize(
    "change",
    [
        lambda state: state.update(schema_version=True),
        lambda state: state.update(schema_version=1.0),
        lambda state: state.update(revision=2.0),
        lambda state: state.update(revision=-1),
        lambda state: state.update(qa_sha256="0" * 64),
        lambda state: state.update(qa_run="relative/report"),
        lambda state: state.pop("conclusion"),
        lambda state: state.update(extra="unsupported"),
        lambda state: state.update(images=[]),
        lambda state: state.update(history={}),
        lambda state: state.update(conclusion=None),
        lambda state: state["images"].clear(),
        lambda state: state["history"][0].update(revision=True),
        lambda state: state["history"][1].update(revision=1),
        lambda state: state["history"][0].update(image_id=[]),
        lambda state: state["history"][0].update(image_id="0" * 64),
        lambda state: state["history"][0].update(extra="unsupported"),
        lambda state: state["history"][1].pop("image_id"),
    ],
)
def test_invalid_state_and_history_are_rejected_without_rewriting(assessed, change):
    store, entry, _ = assessed
    state = store.read()
    change(state)
    _reject_every_boundary(store, entry, state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", ["accepted"]),
        ("verdict", "unknown"),
        ("reviewer", True),
        ("reviewer", ""),
        ("notes", "bad\0note"),
        ("reviewer_kind", "unknown"),
        ("reviewer_kind", None),
        ("reviewer_kind", ["human"]),
        ("at", "2026-11-12T12:00:00"),
        ("at", "not a date"),
        ("source_path", "other.png"),
        ("sha256", "0" * 64),
        ("caption_check", "not_checked"),
        ("caption_check", []),
        ("label_checks", []),
        ("label_checks", {"normalized": True}),
        ("label_checks", {"Not normalized": "correct"}),
        ("label_checks", {"unchecked": "not_checked"}),
        ("unsupported", "field"),
    ],
)
def test_invalid_replayed_image_records_are_not_hidden_by_matching_current_state(
    assessed, field, value
):
    store, entry, _ = assessed
    state = store.read()
    state["history"][0]["record"][field] = value
    state["images"][entry["id"]] = copy.deepcopy(state["history"][0]["record"])
    _reject_every_boundary(store, entry, state)


def test_omitted_report_labels_are_invalid_even_for_nonaccepted_judgments(assessed):
    store, entry, _ = assessed
    assert entry["labels"]
    state = store.read()
    # Construct an otherwise coherent historical nonaccepted record without its required checks.
    state["history"] = state["history"][:1]
    state["revision"] = 1
    state["conclusion"] = None
    record = state["history"][0]["record"]
    record.update(verdict="needs_changes", label_checks={})
    state["images"][entry["id"]] = copy.deepcopy(record)
    _reject_every_boundary(store, entry, state)


def test_history_cannot_assess_a_report_image_outside_frozen_pilot(assessed):
    store, entry, _ = assessed
    outside = next(item for item in store.entries.values() if not item["pilot"])
    state = store.read()
    record = state["history"][0]["record"]
    record.update(source_path=outside["source_path"], sha256=outside["sha256"])
    state["history"][0]["image_id"] = outside["id"]
    state["images"] = {outside["id"]: copy.deepcopy(record)}
    _reject_every_boundary(store, entry, state)


def test_accepted_conclusion_must_have_been_eligible_at_its_event(assessed):
    store, entry, _ = assessed
    state = store.read()
    first, last = state["history"]
    state["history"] = [{**last, "revision": 1}, {**first, "revision": 2}]
    state["conclusion"] = None  # Match final replay, but the first event was never eligible.
    _reject_every_boundary(store, entry, state)


def test_image_edit_and_unreviewed_conclusion_clear_prior_acceptance(assessed):
    store, entry, _ = assessed
    result = store.save(_payload(entry, 2, verdict="unreviewed", caption_check="not_checked"))
    assert result["state"]["conclusion"] is None
    assert result["summary"]["remaining_images"] == 1
    assert not result["summary"]["human_accepted"]
    store.save(_payload(entry, 3))
    accepted = store.save(_payload(None, 4))["state"]
    result = store.save(_payload(None, 5, verdict="unreviewed"))
    assert result["state"]["conclusion"] is None
    assert result["state"]["history"][-1]["record"]["verdict"] == "unreviewed"
    bad = copy.deepcopy(result["state"])
    bad["conclusion"] = accepted["conclusion"]
    _reject_every_boundary(store, entry, bad)


def test_write_revalidates_evidence_after_acquiring_lock(assessed, monkeypatch):
    store, entry, _ = assessed
    changed = store.read()
    changed["images"][entry["id"]]["notes"] = "Changed while waiting for lock"
    original = json.dumps(changed).encode("utf-8")

    class Lock:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            store.path.write_bytes(original)

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(assessments, "FileLock", Lock)
    with pytest.raises(ValueError, match="history"):
        store.save(_payload(entry, 2))
    assert store.path.read_bytes() == original


@pytest.mark.parametrize("name", ["run.json", "entries.jsonl", "summary.json", "coverage.json"])
def test_changed_report_blocks_cached_assessment_reads_and_writes(assessed, name):
    store, entry, _ = assessed
    original = store.path.read_bytes()
    target = store.run / name
    target.write_bytes(target.read_bytes() + b"\n")
    for action in (store.read, store.summary, lambda: store.save(_payload(entry, 2))):
        with pytest.raises(ReviewConflict, match="report changed"):
            action()
        assert store.path.read_bytes() == original


def test_copied_report_and_offline_source_keep_exact_historical_evidence(assessed):
    store, _, config = assessed
    original = store.path.read_bytes()
    copied = store.run.with_name("copied-qa")
    shutil.copytree(store.run, copied)
    store.run.rename(store.run.with_name("old-qa-offline"))
    config.source.rename(config.source.with_name("source-offline"))
    reopened = PilotAssessment(config.reviews, copied)
    assert reopened.path == store.path
    assert reopened.read()["qa_run"] == str(store.run)
    assert reopened.summary()["assessed_images"] == 1
    assert reopened.summary()["conclusion_reviewer_kind"] == "assistant"
    assert not reopened.summary()["human_accepted"]
    assert reopened.path.read_bytes() == original


@pytest.mark.parametrize("raw", [b"[]", b"null", b'{"revision":0,"revision":1}', b'{"n":NaN}'])
def test_invalid_json_shape_and_duplicate_keys_are_not_rewritten(assessed, raw):
    store, entry, _ = assessed
    store.path.write_bytes(raw)
    for action in (store.read, store.summary, lambda: store.save(_payload(entry, 2))):
        with pytest.raises(ValueError):
            action()
        assert store.path.read_bytes() == raw


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_revision": True},
        {"expected_revision": -1},
        {"image_id": []},
        {"verdict": []},
        {"caption_check": []},
        {"label_checks": {"label": []}},
        {"notes": "bad\0note"},
    ],
)
def test_invalid_requests_fail_before_touching_saved_evidence(assessed, changes):
    store, entry, _ = assessed
    original = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save(_payload(entry, 2, **changes))
    assert store.path.read_bytes() == original
