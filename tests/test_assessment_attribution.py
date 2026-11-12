import json

import pytest
from test_exports import reviewed as reviewed

from image_dataset_train.assessments import PilotAssessment
from image_dataset_train.qa import create_qa, list_qa
from image_dataset_train.reviews import ReviewConflict


@pytest.fixture
def pilot(reviewed):
    config, groups, drafts = reviewed
    qa, _ = create_qa(config, groups, captions_run=drafts, sample_size=100)
    store = PilotAssessment(config.reviews, qa)
    entries = list_qa(qa, pilot=True)["entries"]
    assert len(entries) > 1
    return store, entries


def _judgment(store, entry=None, *, kind="human", **changes):
    payload = {
        "expected_revision": store.read()["revision"],
        "reviewer": "Fixture reviewer",
        "reviewer_kind": kind,
        "notes": "Synthetic attribution regression; not production acceptance",
        "verdict": "accepted",
    }
    if entry is not None:
        payload.update(
            image_id=entry["id"],
            caption_check="correct",
            label_checks={label: "correct" for label in entry["labels"]},
        )
    return {**payload, **changes}


def _accept_images(store, entries, *, kind):
    for entry in entries:
        store.save(_judgment(store, entry, kind=kind))


def _files(directory):
    return {
        path.relative_to(directory): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _kinds(summary):
    return {
        kind: summary["reviewer_kinds"].get(kind, 0) for kind in ("human", "assistant", "unknown")
    }


@pytest.mark.parametrize("kind", [None, "", "unknown", ["human"]])
@pytest.mark.parametrize("conclusion", [False, True])
def test_missing_or_invalid_kind_rejects_without_writing(pilot, kind, conclusion):
    store, entries = pilot
    if conclusion:
        _accept_images(store, entries, kind="human")
    payload = _judgment(store, None if conclusion else entries[0], kind=kind)
    if kind is None:
        payload.pop("reviewer_kind")
    before = _files(store.directory)
    with pytest.raises(ValueError, match="(?i)(reviewer|kind|human|assistant)"):
        store.save(payload)
    assert _files(store.directory) == before


def test_all_assistant_acceptances_retain_attribution_without_human_acceptance(pilot):
    store, entries = pilot
    for entry in entries:
        store.save(_judgment(store, entry, kind="assistant", reviewer="Human reviewer"))
    result = store.save(_judgment(store, kind="assistant", reviewer="Human reviewer"))
    assert result["summary"]["human_accepted"] is False
    assert _kinds(result["summary"]) == {"human": 0, "assistant": len(entries), "unknown": 0}
    reopened = PilotAssessment(store.directory.parent.parent, store.run).read()
    assert reopened == result["state"]
    assert {record["reviewer_kind"] for record in reopened["images"].values()} == {"assistant"}
    assert reopened["conclusion"]["reviewer_kind"] == "assistant"
    assert {event["record"]["reviewer_kind"] for event in reopened["history"]} == {"assistant"}


def test_human_conclusion_cannot_promote_mixed_image_judgments(pilot):
    store, entries = pilot
    _accept_images(store, entries, kind="human")
    store.save(_judgment(store, entries[-1], kind="assistant"))
    result = store.save(_judgment(store, kind="human"))
    assert result["summary"]["conclusion"]["reviewer_kind"] == "human"
    assert result["summary"]["human_accepted"] is False
    assert _kinds(result["summary"]) == {"human": len(entries) - 1, "assistant": 1, "unknown": 0}
    assert result["state"]["history"][-3]["record"]["reviewer_kind"] == "human"
    assert result["state"]["history"][-2]["record"]["reviewer_kind"] == "assistant"


def test_legacy_judgments_remain_unknown_without_rewriting_history(pilot):
    store, entries = pilot
    _accept_images(store, entries, kind="human")
    legacy = store.save(_judgment(store, kind="human"))["state"]
    for record in [*legacy["images"].values(), legacy["conclusion"]]:
        record.pop("reviewer_kind")
        record["reviewer"] = "Human reviewer"
    for event in legacy["history"]:
        event["record"].pop("reviewer_kind", None)
        event["record"]["reviewer"] = "Human reviewer"
    store.path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
    before = store.path.read_bytes()
    reopened = PilotAssessment(store.directory.parent.parent, store.run)
    assert reopened.read() == legacy
    summary = reopened.summary()
    assert summary["human_accepted"] is False
    assert _kinds(summary) == {"human": 0, "assistant": 0, "unknown": len(entries)}
    assert store.path.read_bytes() == before
    result = reopened.save(_judgment(reopened, kind="human"))
    assert result["summary"]["human_accepted"] is False
    assert result["state"]["images"] == legacy["images"]
    assert result["state"]["history"][:-1] == legacy["history"]
    assert result["state"]["history"][-1]["record"]["reviewer_kind"] == "human"


def test_only_explicit_all_human_acceptance_is_human_accepted(pilot):
    store, entries = pilot
    for entry in entries:
        store.save(_judgment(store, entry, kind="human", reviewer="Assistant-like display name"))
    assert store.summary()["human_accepted"] is False
    assert store.save(_judgment(store, kind="assistant"))["summary"]["human_accepted"] is False
    result = store.save(_judgment(store, kind="human"))
    assert result["summary"]["human_accepted"] is True
    assert _kinds(result["summary"]) == {"human": len(entries), "assistant": 0, "unknown": 0}
    assert result["summary"]["remaining_images"] == 0
    assert (
        PilotAssessment(store.directory.parent.parent, store.run).summary()["human_accepted"]
        is True
    )


def test_stale_revision_cannot_relabel_an_assistant_record_as_human(pilot):
    store, entries = pilot
    stale = _judgment(store, entries[0], kind="human")
    store.save(_judgment(store, entries[0], kind="assistant"))
    before = store.path.read_bytes()
    with pytest.raises(ReviewConflict):
        store.save(stale)
    assert store.path.read_bytes() == before
    assert store.read()["images"][entries[0]["id"]]["reviewer_kind"] == "assistant"
    assert _kinds(store.summary()) == {"human": 0, "assistant": 1, "unknown": 0}


def test_attribution_does_not_bypass_image_checks_or_complete_pilot_gate(pilot):
    store, entries = pilot
    with pytest.raises(ValueError, match="checking the caption"):
        store.save(_judgment(store, entries[0], caption_check="not_checked"))
    store.save(_judgment(store, entries[0]))
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="every pilot image"):
        store.save(_judgment(store))
    assert store.path.read_bytes() == before
    assert store.summary()["human_accepted"] is False
