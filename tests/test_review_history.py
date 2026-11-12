"""Restoration is an exact, attributed new event, never a rewrite of history."""

import builtins
import copy
import json
import os
from dataclasses import replace

import pytest
from filelock import FileLock
from test_reviews import prepared as prepared

from image_dataset_train import review_history
from image_dataset_train.review_history import inspect_history, preview_restore, restore_review
from image_dataset_train.reviews import ReviewConflict, ReviewStore, review_image, review_link
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


def state(config):
    return ReviewStore(config.reviews, config.source).read()


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def apply(config, run, revision, *, before=False, preview=None, **extra):
    preview = preview or preview_restore(config, run, revision, before=before)
    return restore_review(
        config,
        run,
        revision,
        before=before,
        expected_revision=preview["current_revision"],
        expected_plan_sha256=preview["plan_sha256"],
        reason="Recover fixture correction",
        reviewer="Fixture assistant",
        reviewer_kind="assistant",
        **extra,
    )


def test_empty_and_offline_history_are_read_only_without_model_imports(
    prepared, tmp_path, monkeypatch
):
    config, run, _ = prepared
    before = snapshot(tmp_path)
    assert inspect_history(config, run)["events"] == []
    assert not config.reviews.exists()
    assert snapshot(tmp_path) == before
    review_image(config, run, "a.png", caption="first caption", reason="first")
    review_image(config, run, "a.png", caption="second caption", reason="second")
    config.source.rename(config.source.with_name("offline"))
    before = snapshot(tmp_path)
    importer = builtins.__import__

    def guard(name, *args, **kwargs):
        if name in {"numpy", "onnxruntime", "image_dataset_train.tagging"}:
            pytest.fail("History imported the model runtime")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    history = inspect_history(config, run, image="a.png", limit=1)
    assert history["total_events"] == 2 and history["next_offset"] == 1
    assert history["events"][0]["revision"] == 2
    assert history["events"][0]["reviewer_kind"] == "unknown"
    assert inspect_history(config, run, image="a.png", offset=1)["events"][0]["before"] is None
    plan = preview_restore(config, run, 1)
    assert plan["proposed_record"]["caption_override"] == "first caption"
    assert plan["applicable"] and not plan["source_revalidated"]
    assert snapshot(tmp_path) == before


def test_exact_restore_removes_later_fields_and_preserves_unrelated_state(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", decision="include", reason="first")
    first = copy.deepcopy(state(config))
    review_image(
        config,
        run,
        "a.png",
        caption="later caption",
        add_labels=["portrait"],
        subset="solo",
        reason="later",
    )
    review_image(config, run, "b.png", decision="exclude", reason="unrelated")
    saved = copy.deepcopy(state(config))
    originals = snapshot(config.source)
    result = apply(config, run, 1)
    current = state(config)
    assert result["status"] == "restored" and result["revision"] == 4
    key = first["history"][0]["key"]
    assert current["images"][key] == first["images"][key]
    other = saved["history"][2]["key"]
    assert current["images"][other] == saved["images"][other]
    assert current["history"][:-1] == saved["history"]
    assert current["history"][-1]["reviewer_kind"] == "assistant"
    assert current["history"][-1]["reason"] == "Recover fixture correction"
    assert current["images"][key]["reason"] == "first"
    assert snapshot(config.source) == originals
    assert inspect_history(config, run)["current_revision"] == 4


def test_first_edit_removal_restore_of_restore_and_normal_edit(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", clear_labels=True, clear_subset=True, reason="empty choices")
    old = copy.deepcopy(state(config))
    key = old["history"][0]["key"]
    removed = apply(config, run, 1, before=True)
    assert removed["proposed_record"] is None and state(config)["images"] == {}
    history = inspect_history(config, run, image="a.png")
    assert history["events"][0]["after"] is None
    assert history["events"][0]["before"]["labels"] == []
    restored = apply(config, run, 2, before=True)
    assert restored["revision"] == 3 and state(config)["images"][key] == old["images"][key]
    review_image(config, run, "a.png", caption="new caption", reason="ordinary edit after restore")
    assert inspect_history(config, run)["current_revision"] == 4
    assert state(config)["history"][:1] == old["history"]


def test_pair_restore_removes_evaluation_set_and_checks_graph_conflict(prepared):
    config, run, pairs = prepared
    review_link(config, run, ["a.png", "b.png"], "related", "first")
    first = copy.deepcopy(state(config))
    review_link(config, run, ["a.png", "b.png"], "related", "assigned", evaluation_set="held_out")
    result = apply(config, run, 1)
    assert "evaluation_set" not in result["event"]["record"]
    assert inspect_history(config, run, pair=pairs["a.pngb.png"])["matching_events"] == 3
    apply(config, run, 1, before=True)
    review_link(config, run, ["a.png", "c.png"], "related", "new relation")
    review_link(config, run, ["b.png", "c.png"], "distinct", "new distinction")
    before = state(config)
    with pytest.raises(ValueError, match="conflicts"):
        apply(config, run, 1)
    assert state(config) == before
    assert first["history"] == before["history"][:1]


@pytest.mark.parametrize("change", ["edit", "whitespace", "same_revision_history"])
def test_stale_preview_rejects_concurrent_and_unversioned_changes(prepared, change):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    review_image(config, run, "a.png", caption="second", reason="second")
    plan = preview_restore(config, run, 1)
    store = ReviewStore(config.reviews, config.source)
    if change == "edit":
        review_image(config, run, "b.png", decision="include", reason="another writer")
    elif change == "whitespace":
        store.path.write_text(store.path.read_text() + "\n", encoding="utf-8")
    else:
        data = state(config)
        data["history"][0]["record"]["reason"] = "edited without revision"
        store.path.write_text(json.dumps(data), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ReviewConflict, match="preview changed"):
        apply(config, run, 1, preview=plan)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "damage", ["sequence", "time", "record", "replay", "image_key", "annotation", "unknown_field"]
)
def test_malformed_history_is_preserved_and_never_a_restore_target(prepared, damage):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    store = ReviewStore(config.reviews, config.source)
    data = state(config)
    event = data["history"][0]
    if damage == "sequence":
        event["revision"] = True
    elif damage == "time":
        event["at"] = "2026-11-11"
    elif damage == "record":
        event["record"]["decision"] = []
    elif damage == "replay":
        event["record"]["reason"] = "different from current map"
    elif damage == "image_key":
        event["key"] = "a" * 64
    elif damage == "annotation":
        event["record"]["labels_reviewed"] = "yes"
    else:
        event["record"]["accepted"] = True
    store.path.write_text(json.dumps(data), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_history(config, run)
    with pytest.raises(ValueError):
        preview_restore(config, run, 1)
    assert store.path.read_bytes() == before


def test_changed_source_after_preview_and_during_selection_guard_rejects(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    review_image(config, run, "a.png", caption="second", reason="second")
    plan = preview_restore(config, run, 1)
    before = state(config)
    with pytest.raises(ValueError, match="Source changed"):
        apply(
            config,
            run,
            1,
            preview=plan,
            guard=lambda: (config.source / "a.png").write_bytes(b"changed"),
        )
    assert state(config) == before
    with pytest.raises(ValueError, match="Source changed"):
        apply(config, run, 1, preview=plan)
    assert state(config) == before


def test_changed_inventory_content_and_pair_policy_stays_readable_but_not_restorable(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    review_link(config, run, ["b.png", "c.png"], "related", "relation")
    original = state(config)
    (config.source / "a.png").write_bytes((config.source / "b.png").read_bytes())
    inventory, _ = run_scan(config)
    new_run, _ = propose_similar(config, inventory)
    assert not preview_restore(config, new_run, 1)["applicable"]
    with pytest.raises(ValueError, match="does not match"):
        apply(config, new_run, 1)
    # A different versioned policy changes pair IDs, not the retained history record.
    metadata = json.loads((new_run / "run.json").read_text())
    metadata["hash_version"] = "future-hash-policy"
    (new_run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert not preview_restore(config, new_run, 2)["applicable"]
    assert inspect_history(config, new_run)["total_events"] == 2
    assert state(config) == original


def test_atomic_failure_noop_and_busy_writer_preserve_history(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    before = state(config)
    result = apply(config, run, 1)
    assert result["status"] == "unchanged" and result["event"] is None
    assert state(config) == before
    store = ReviewStore(config.reviews, config.source)
    with FileLock(str(store.directory / "reviews.lock"), timeout=0):
        with pytest.raises(ReviewConflict, match="Another review"):
            apply(config, run, 1, before=True)

    def fail(source, destination):
        raise OSError("Synthetic atomic publication failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="Synthetic"):
        apply(config, run, 1, before=True)
    assert state(config) == before
    assert not list(store.directory.glob(".pending-*"))


@pytest.mark.parametrize("damage", ["duplicate_key", "nonfinite"])
def test_ambiguous_json_is_rejected_before_history_interpretation(prepared, damage):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    store = ReviewStore(config.reviews, config.source)
    raw = store.path.read_text()
    if damage == "duplicate_key":
        raw = raw.replace('"revision": 1', '"revision": 1, "revision": 1', 1)
    else:
        raw = raw.replace('"reason": "first"', '"reason": NaN', 1)
    store.path.write_text(raw, encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="Duplicate|Non-finite"):
        inspect_history(config, run)
    assert store.path.read_bytes() == before


def test_pair_identity_cannot_change_under_a_reused_history_key(prepared):
    config, run, _ = prepared
    review_link(config, run, ["a.png", "b.png"], "related", "first")
    review_link(config, run, ["a.png", "b.png"], "unreviewed", "second")
    store = ReviewStore(config.reviews, config.source)
    data = state(config)
    context = review_history.load_context(run)
    first = data["history"][0]["record"]
    first.update(right_source_path="c.png", right_sha256=context.rows["c.png"]["sha256"])
    store.path.write_text(json.dumps(data), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="identity changed within one key"):
        preview_restore(config, run, 2, before=True)
    assert store.path.read_bytes() == before


def test_apply_rechecks_store_bytes_after_under_lock_selection_guard(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    store = ReviewStore(config.reviews, config.source)
    raw = store.path.read_bytes()

    def alter():
        store.path.write_bytes(raw + b"\n")

    with pytest.raises(ReviewConflict, match="changed before publication"):
        apply(config, run, 1, before=True, guard=alter)
    assert store.path.read_bytes() == raw + b"\n"
    assert state(config)["revision"] == 1


def test_offline_apply_never_erases_a_live_review(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    before = state(config)
    config.source.rename(config.source.with_name("offline"))
    plan = preview_restore(config, run, 1, before=True)
    with pytest.raises(OSError):
        apply(config, run, 1, before=True, preview=plan)
    assert state(config) == before


def test_under_lock_guard_and_configuration_mismatch_reject(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="first", reason="first")
    before = state(config)

    def reject():
        raise ReviewConflict("Selection changed")

    with pytest.raises(ReviewConflict, match="Selection changed"):
        apply(config, run, 1, before=True, guard=reject)
    assert state(config) == before
    with pytest.raises(ValueError, match="Configuration source"):
        inspect_history(replace(config, source=config.source.with_name("unrelated")), run)


def test_linked_ancestor_is_rejected_without_creating_store(prepared, tmp_path):
    config, run, _ = prepared
    target = tmp_path / "other"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    before = snapshot(target)
    with pytest.raises(ValueError, match="Linked review history"):
        inspect_history(replace(config, reviews=alias / "reviews"), run)
    assert snapshot(target) == before


@pytest.mark.parametrize(
    "options",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"image": "../x"},
        {"pair": "abc"},
        {"image": "a.png", "pair": "a" * 64},
    ],
)
def test_invalid_history_selection_has_no_writes(prepared, tmp_path, options):
    config, run, _ = prepared
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        inspect_history(config, run, **options)
    assert snapshot(tmp_path) == before
