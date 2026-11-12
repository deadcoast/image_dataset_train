"""Ordinary review consumers reject the same history defects before using state."""

import copy
import json
from contextlib import contextmanager

import pytest
from filelock import FileLock
from test_reviews import prepared as prepared

from image_dataset_train import reviews
from image_dataset_train.review_history import inspect_history
from image_dataset_train.reviews import (
    ReviewConflict,
    ReviewStore,
    load_context,
    publish_groups,
    review_image,
    review_link,
    review_status,
)
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def seed(config, run):
    review_image(config, run, "a.png", add_labels=["portrait"], reason="first")
    review_link(config, run, ["a.png", "b.png"], "related", "relationship")
    store = ReviewStore(config.reviews, config.source)
    return store, store.read()


def corrupt(state, damage):
    state = copy.deepcopy(state)
    event = state["history"][0]
    current = state["images"][event["key"]]
    if damage == "current_only_caption":
        current["caption_override"] = "not in history"
    elif damage == "history_only_reason":
        event["record"]["reason"] = "not the saved reason"
    elif damage == "boolean_schema":
        state["schema_version"] = True
    elif damage == "boolean_revision":
        state["revision"] = True
    elif damage == "extra_state_field":
        state["unrecognized"] = 1
    elif damage == "boolean_event_revision":
        event["revision"] = True
    elif damage == "float_event_revision":
        event["revision"] = 1.0
    elif damage == "unsupported_action":
        event["action"] = "imported"
    elif damage == "naive_timestamp":
        event["at"] = "2026-11-12T12:00:00"
    elif damage == "partial_actor":
        event["reviewer"] = "assistant with no kind"
    elif damage == "null_actor":
        event.update(reviewer=None, reviewer_kind=None)
    elif damage == "invalid_actor_kind":
        event.update(reviewer="fixture", reviewer_kind="verified")
    elif damage == "current_boolean_type_confusion":
        # Python's dict equality alone considers this equal to historical True.
        event["record"]["labels_reviewed"] = True
        current["labels_reviewed"] = 1
    elif damage == "current_extra_field":
        current["unrecognized"] = "value"
    elif damage == "history_extra_field":
        event["record"]["unrecognized"] = "value"
    elif damage == "malformed_pair_key":
        pair_key = next(iter(state["pairs"]))
        state["pairs"]["not-a-content-key"] = state["pairs"].pop(pair_key)
    elif damage == "unsafe_historical_path":
        event["record"]["source_path"] = "../outside.png"
    else:
        raise AssertionError(damage)
    return state


@pytest.mark.parametrize(
    "damage",
    [
        "current_only_caption",
        "history_only_reason",
        "boolean_schema",
        "boolean_revision",
        "extra_state_field",
        "boolean_event_revision",
        "float_event_revision",
        "unsupported_action",
        "naive_timestamp",
        "partial_actor",
        "null_actor",
        "invalid_actor_kind",
        "current_boolean_type_confusion",
        "current_extra_field",
        "history_extra_field",
        "malformed_pair_key",
        "unsafe_historical_path",
    ],
)
def test_all_ordinary_consumers_reject_corruption_without_changing_bytes(prepared, damage):
    config, run, _ = prepared
    store, state = seed(config, run)
    store.path.write_text(json.dumps(corrupt(state, damage)), encoding="utf-8")
    before = snapshot(config.source), snapshot(config.reviews), snapshot(config.runs)
    consumers = [
        store.read,
        lambda: inspect_history(config, run),
        lambda: review_status(config, run),
        lambda: publish_groups(config, run),
        # A different record must not bypass or silently repair damaged history.
        lambda: review_image(config, run, "c.png", caption="new caption", reason="new"),
    ]
    for consume in consumers:
        with pytest.raises(ValueError, match="Invalid review state"):
            consume()
        assert before == (
            snapshot(config.source),
            snapshot(config.reviews),
            snapshot(config.runs),
        )


@pytest.mark.parametrize("damage", ["duplicate_object_key", "nonfinite"])
def test_ordinary_reads_and_saves_reject_ambiguous_json(prepared, damage):
    config, run, _ = prepared
    store, _ = seed(config, run)
    raw = store.path.read_text(encoding="utf-8")
    if damage == "duplicate_object_key":
        raw = raw.replace('"revision": 2', '"revision": 2, "revision": 2', 1)
    else:
        raw = raw.replace('"reason": "first"', '"reason": NaN', 1)
    store.path.write_text(raw, encoding="utf-8")
    before = store.path.read_bytes()
    for consume in (
        store.read,
        lambda: review_image(config, run, "c.png", caption="new", reason="new"),
    ):
        with pytest.raises(ValueError, match="Duplicate|Non-finite"):
            consume()
        assert store.path.read_bytes() == before


def test_ordinary_write_revalidates_changed_state_under_lock(prepared, monkeypatch):
    config, run, _ = prepared
    store, state = seed(config, run)
    damaged = json.dumps(corrupt(state, "history_only_reason")).encode("utf-8")
    acquired = []

    @contextmanager
    def intervening_lock(path, timeout):
        with FileLock(path, timeout=timeout):
            acquired.append(True)
            store.path.write_bytes(damaged)
            yield

    monkeypatch.setattr(reviews, "FileLock", intervening_lock)
    with pytest.raises(ValueError, match="replay differs"):
        review_image(config, run, "c.png", caption="new", reason="new")
    assert acquired == [True]
    assert store.path.read_bytes() == damaged


@pytest.mark.parametrize("expected", [True, 2.0, -1, "2"])
def test_ordinary_revision_guard_requires_an_integer(prepared, expected):
    config, run, _ = prepared
    store, _ = seed(config, run)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="nonnegative integer"):
        review_image(config, run, "c.png", caption="new", reason="new", expected_revision=expected)
    assert store.path.read_bytes() == before


def test_valid_legacy_and_attributed_events_remain_unchanged_on_new_edit(prepared):
    config, run, _ = prepared
    store, state = seed(config, run)
    # Older ordinary events have no actor; an explicitly attributed supported
    # event must retain its attribution and exact historical fields.
    state["history"][1].update(reviewer="fixture assistant", reviewer_kind="assistant")
    store.path.write_text(json.dumps(state), encoding="utf-8")
    events = inspect_history(config, run)["events"]
    assert [event["reviewer_kind"] for event in events] == ["assistant", "unknown"]
    review_image(config, run, "c.png", caption="new", reason="new", expected_revision=2)
    after = store.read()
    assert after["history"][:2] == state["history"]
    assert after["revision"] == 3
    before = store.path.read_bytes()
    with pytest.raises(ReviewConflict):
        review_image(config, run, "c.png", caption="stale", reason="stale", expected_revision=2)
    assert store.path.read_bytes() == before


def test_stale_historical_identities_do_not_block_new_valid_edits(prepared):
    config, run, _ = prepared
    store, old = seed(config, run)
    (config.source / "a.png").unlink()
    inventory, _ = run_scan(config)
    newer, _ = propose_similar(config, inventory, max_distance=64)
    assert store.read() == old
    assert all(not event["compatible"] for event in inspect_history(config, newer)["events"])
    review_image(config, newer, "c.png", caption="new", reason="new")
    assert store.read()["history"][:2] == old["history"]
    offline = config.source.with_name("offline")
    config.source.rename(offline)
    before = store.path.read_bytes()
    assert store.read()["revision"] == 3
    assert inspect_history(config, newer)["total_events"] == 3
    assert store.path.read_bytes() == before


def test_direct_invalid_record_cannot_be_published_by_store_update(prepared):
    config, run, _ = prepared
    store, state = seed(config, run)
    event = state["history"][0]
    proposed = {**event["record"], "labels_reviewed": 1}
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="boolean"):
        store.update(load_context(run), "images", event["key"], proposed)
    assert store.path.read_bytes() == before
