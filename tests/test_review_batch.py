"""Explicit bulk corrections are one atomic action with replayable membership."""

import builtins
import copy
import json
from dataclasses import replace

import pytest
from filelock import FileLock
from test_reviews import prepared as prepared

from image_dataset_train import review_batch
from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.review_batch import apply_batch, preview_batch
from image_dataset_train.review_history import inspect_history, preview_restore, restore_review
from image_dataset_train.reviews import (
    ReviewConflict,
    ReviewStore,
    image_review_operations,
    image_review_proposal,
    review_image,
    review_link,
)


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def state(config):
    return ReviewStore(config.reviews, config.source).read()


def apply(config, run, paths, *, preview=None, reason="Reviewed fixture selection", **operations):
    plan = preview or preview_batch(config, run, paths, reason=reason, **operations)
    return apply_batch(
        config,
        run,
        paths,
        reason=reason,
        expected_revision=plan["current_revision"],
        expected_plan_sha256=plan["plan_sha256"],
        reviewer="Fixture assistant",
        reviewer_kind="assistant",
        **operations,
    )


def test_batch_is_atomic_and_history_retains_exact_selection_and_actor(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(
        config,
        run,
        "a.png",
        caption="keep this caption",
        add_labels=["art", "old"],
        subset="old",
        reason="previous correction",
    )
    review_image(config, run, "c.png", decision="exclude", reason="unrelated")
    before = copy.deepcopy(state(config))
    originals = snapshot(config.source)
    operations = dict(
        decision="include",
        add_labels=[" Portrait ", "portrait"],
        remove_labels=["old"],
        subset=" SOLO ",
    )
    plan = preview_batch(config, run, ["b.png", "a.png"], reason="selected", **operations)
    assert plan["selected_count"] == plan["changed_count"] == 2
    assert [row["source_path"] for row in plan["members"]] == ["a.png", "b.png"]
    assert plan["operations"]["add_labels"] == ["portrait"]
    assert plan["operations"]["subset"] == "solo"
    assert not plan["source_revalidated"]
    saves = []
    original_atomic = review_batch.atomic_json

    def atomic(path, value):
        saves.append(copy.deepcopy(value))
        original_atomic(path, value)

    monkeypatch.setattr(review_batch, "atomic_json", atomic)
    result = apply(config, run, ["a.png", "b.png"], preview=plan, reason="selected", **operations)
    assert result["status"] == "applied" and result["revision"] == before["revision"] + 2
    assert result["current_revision"] == before["revision"] and result["source_revalidated"]
    assert len(saves) == 1 and saves[0] == state(config)
    current = state(config)
    assert current["history"][:-2] == before["history"]
    assert current["images"][before["history"][1]["key"]] == before["history"][1]["record"]
    assert current["history"][-2]["record"]["caption_override"] == "keep this caption"
    assert current["history"][-2]["record"]["labels"] == ["art", "portrait"]
    assert all(event["reviewer_kind"] == "assistant" for event in current["history"][-2:])
    assert current["history"][-1]["batch"] == {"id": result["batch_id"], "index": 1, "count": 2}
    listing = inspect_history(config, run, limit=1)
    manifest = listing["batches"][result["batch_id"]]["manifest"]
    assert [row["source_path"] for row in manifest["members"]] == ["a.png", "b.png"]
    assert manifest["plan_sha256"] == plan["plan_sha256"]
    assert snapshot(config.source) == originals


def test_each_batch_member_is_restorable_and_normal_edits_remain_compatible(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", caption="original override", reason="original")
    before = state(config)
    result = apply(config, run, ["a.png", "b.png"], add_labels=["portrait"])
    restore = preview_restore(config, run, 2, before=True)
    assert restore["selected_batch"]["id"] == result["batch_id"]
    restore_review(
        config,
        run,
        2,
        before=True,
        expected_revision=3,
        expected_plan_sha256=restore["plan_sha256"],
        reason="undo one member",
        reviewer="Fixture assistant",
        reviewer_kind="assistant",
    )
    assert state(config)["images"][before["history"][0]["key"]] == before["history"][0]["record"]
    review_image(config, run, "b.png", caption="ordinary later correction", reason="later")
    listing = inspect_history(config, run)
    assert listing["current_revision"] == 5
    assert [event["action"] for event in listing["events"]] == [
        "edit",
        "restore",
        "batch",
        "batch",
        "edit",
    ]


def test_noop_preserves_bytes_and_mixed_batch_retains_unchanged_members(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(config, run, "a.png", add_labels=["portrait"], subset="solo", reason="original")
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    original_verify = review_batch._verify_source
    checked = []

    def verify(context, row, limit):
        checked.append(row["source_path"])
        original_verify(context, row, limit)

    monkeypatch.setattr(review_batch, "_verify_source", verify)
    plan = preview_batch(
        config, run, ["a.png"], add_labels=["portrait"], subset="solo", reason="new reason"
    )
    assert plan["no_op"] and not plan["members"][0]["changes"]
    result = apply(
        config,
        run,
        ["a.png"],
        preview=plan,
        add_labels=["portrait"],
        subset="solo",
        reason="new reason",
    )
    assert result["status"] == "unchanged" and result["batch_id"] is None
    assert result["events"] == [] and result["revision"] == 1
    assert checked == ["a.png", "a.png"] and store.path.read_bytes() == before
    checked.clear()
    mixed = apply(config, run, ["b.png", "a.png"], add_labels=["portrait"])
    assert mixed["selected_count"] == 2 and mixed["changed_count"] == 1
    assert checked == ["a.png", "b.png", "a.png", "b.png"]
    assert len(mixed["batch"]["manifest"]["members"]) == 2
    assert mixed["events"][0]["record"]["source_path"] == "b.png"
    assert inspect_history(config, run)["current_revision"] == 2


def test_changed_noop_member_and_late_failure_never_commit_a_partial_batch(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(config, run, "a.png", add_labels=["portrait"], reason="original")
    store = ReviewStore(config.reviews, config.source)
    plan = preview_batch(
        config, run, ["a.png", "b.png"], add_labels=["portrait"], reason="selected"
    )
    before = store.path.read_bytes()
    original = (config.source / "a.png").read_bytes()
    (config.source / "a.png").write_bytes(b"changed no-op source")
    with pytest.raises(ValueError, match="Source changed"):
        apply(
            config,
            run,
            ["a.png", "b.png"],
            preview=plan,
            add_labels=["portrait"],
            reason="selected",
        )
    assert store.path.read_bytes() == before
    (config.source / "a.png").write_bytes(original)

    def fail(path, value):
        assert value["revision"] == 2
        raise PermissionError("simulated publication failure")

    monkeypatch.setattr(review_batch, "atomic_json", fail)
    with pytest.raises(PermissionError, match="publication failure"):
        apply(
            config,
            run,
            ["a.png", "b.png"],
            preview=plan,
            add_labels=["portrait"],
            reason="selected",
        )
    assert store.path.read_bytes() == before


def test_preview_offline_and_absent_store_never_writes_or_imports_models(
    prepared, tmp_path, monkeypatch
):
    config, run, _ = prepared
    config.source.rename(config.source.with_name("offline"))
    before = snapshot(tmp_path)
    importer = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"onnxruntime", "numpy", "image_dataset_train.tagging"}:
            pytest.fail("Bulk review imported a model runtime")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    plan = preview_batch(config, run, ["b.png", "a.png"], clear_labels=True, reason="selected")
    assert plan["current_revision"] == 0 and plan["changed_count"] == 2
    assert not plan["source_revalidated"] and not config.reviews.exists()
    assert snapshot(tmp_path) == before
    with pytest.raises(FileNotFoundError):
        apply(config, run, ["a.png", "b.png"], preview=plan, clear_labels=True, reason="selected")
    assert snapshot(tmp_path) == before or all(
        name.endswith("reviews.lock") or name in before for name in snapshot(tmp_path)
    )
    assert not ReviewStore(config.reviews, config.source).path.exists()


@pytest.mark.parametrize(
    "paths",
    [
        [],
        "a.png",
        ["a.png"] * 1001,
        ["a.png", "a.png"],
        ["../a.png"],
        ["a\\b.png"],
        ["/a.png"],
        ["C:a.png"],
        ["./a.png"],
        ["a//b.png"],
        [None],
    ],
)
def test_invalid_selection_is_rejected_before_reading_or_writing(tmp_path, paths):
    config = Config(
        tmp_path / "source", tmp_path / "runs", ValidationConfig(), reviews=tmp_path / "reviews"
    )
    with pytest.raises(ValueError):
        preview_batch(
            config, tmp_path / "missing-run", paths, decision="include", reason="selected"
        )
    assert snapshot(tmp_path) == {}


@pytest.mark.parametrize(
    "operations",
    [
        {},
        {"decision": []},
        {"decision": "accepted"},
        {"clear_labels": 1},
        {"clear_subset": "yes"},
        {"add_labels": "portrait"},
        {"add_labels": ["same"], "remove_labels": [" SAME "]},
        {"subset": "solo", "clear_subset": True},
        {"subset": "\0"},
    ],
)
def test_invalid_operations_are_rejected_before_reading_or_writing(tmp_path, operations):
    config = Config(
        tmp_path / "source", tmp_path / "runs", ValidationConfig(), reviews=tmp_path / "reviews"
    )
    with pytest.raises(ValueError):
        preview_batch(config, tmp_path / "missing-run", ["a.png"], reason="selected", **operations)
    assert snapshot(tmp_path) == {}


def test_explicit_empty_and_false_review_flags_are_real_changes():
    row = {"source_path": "a.png", "sha256": "a" * 64}
    operations = image_review_operations(clear_labels=True, clear_subset=True)
    first = image_review_proposal(row, None, operations, "reviewed empty")
    assert first["labels"] == [] and first["subset"] is None
    assert first["labels_reviewed"] and first["subset_reviewed"]
    assert image_review_proposal(row, first, operations, "new reason") is first
    unreviewed = {**first, "labels_reviewed": False, "subset_reviewed": False}
    proposed = image_review_proposal(row, unreviewed, operations, "reviewed now")
    assert proposed["labels_reviewed"] and proposed["subset_reviewed"]
    assert proposed["reason"] == "reviewed now"
    assert not unreviewed["labels_reviewed"]
    assert (
        image_review_proposal(row, None, image_review_operations(decision="unreviewed"), "reset")
        is None
    )


def test_unrelated_caption_subset_and_review_flags_survive_label_changes():
    row = {"source_path": "a.png", "sha256": "a" * 64}
    original = {
        **row,
        "decision": "include",
        "reason": "previous",
        "labels": ["old"],
        "labels_reviewed": False,
        "subset": "solo",
        "subset_reviewed": False,
        "subset_origin": {"kind": "caption-rule"},
        "caption_override": "keep",
        "caption_rule_version": "manual-v1",
    }
    proposed = image_review_proposal(
        row, original, image_review_operations(add_labels=["new"]), "selected"
    )
    assert proposed["labels"] == ["new", "old"] and proposed["labels_reviewed"]
    for field in [
        "subset",
        "subset_reviewed",
        "subset_origin",
        "caption_override",
        "caption_rule_version",
    ]:
        assert proposed[field] == original[field]
    manual_subset = image_review_proposal(
        row, original, image_review_operations(subset="solo"), "manual"
    )
    assert manual_subset["subset_origin"] is None and manual_subset["subset_reviewed"]


def test_missing_ineligible_and_wrong_source_selection_are_rejected(prepared, tmp_path):
    config, run, _ = prepared
    before = snapshot(tmp_path)
    for paths in [["missing.png"], ["a.txt"]]:
        with pytest.raises(ValueError, match="missing or ineligible"):
            preview_batch(config, run, paths, decision="include", reason="selected")
    with pytest.raises(ValueError, match="source"):
        preview_batch(
            replace(config, source=tmp_path / "different"),
            run,
            ["a.png"],
            decision="include",
            reason="selected",
        )
    assert snapshot(tmp_path) == before


def test_stale_store_and_changed_reason_reject_before_publication(prepared):
    config, run, _ = prepared
    operations = dict(add_labels=["portrait"])
    plan = preview_batch(config, run, ["a.png", "b.png"], reason="selected", **operations)
    with pytest.raises(ReviewConflict, match="preview changed"):
        apply(config, run, ["a.png", "b.png"], preview=plan, reason="different", **operations)
    assert not config.reviews.exists()
    review_image(config, run, "c.png", caption="parallel edit", reason="other writer")
    before = state(config)
    with pytest.raises(ReviewConflict, match="preview changed"):
        apply(config, run, ["a.png", "b.png"], preview=plan, reason="selected", **operations)
    assert state(config) == before


def test_shared_writer_lock_and_selection_guard_preserve_state(prepared):
    config, run, _ = prepared
    review_image(config, run, "c.png", caption="seed", reason="seed")
    store = ReviewStore(config.reviews, config.source)
    plan = preview_batch(config, run, ["a.png", "b.png"], decision="include", reason="selected")
    before = store.path.read_bytes()
    with FileLock(str(store.directory / "reviews.lock"), timeout=0):
        with pytest.raises(ReviewConflict, match="Another review update"):
            apply(
                config, run, ["a.png", "b.png"], preview=plan, decision="include", reason="selected"
            )
    assert store.path.read_bytes() == before

    def failed_guard():
        raise ValueError("selected job changed")

    with pytest.raises(ValueError, match="selected job changed"):
        apply_batch(
            config,
            run,
            ["a.png", "b.png"],
            decision="include",
            reason="selected",
            expected_revision=plan["current_revision"],
            expected_plan_sha256=plan["plan_sha256"],
            reviewer="Fixture assistant",
            reviewer_kind="assistant",
            guard=failed_guard,
        )
    assert store.path.read_bytes() == before


def test_cross_member_source_change_during_verification_is_rejected(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(config, run, "c.png", caption="seed", reason="seed")
    before = state(config)
    original = review_batch._verify_source

    def verify(context, row, limit):
        original(context, row, limit)
        if row["source_path"] == "b.png":
            (config.source / "a.png").write_bytes(b"changed after first member verification")

    monkeypatch.setattr(review_batch, "_verify_source", verify)
    with pytest.raises(ReviewConflict, match="Selected source changed"):
        apply(config, run, ["a.png", "b.png"], decision="include")
    assert state(config) == before


def test_source_replacement_after_last_hash_cannot_become_the_final_stamp(prepared, monkeypatch):
    config, run, _ = prepared
    review_image(config, run, "c.png", caption="seed", reason="seed")
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    original = review_batch._verify_source
    calls = []

    def verify(context, row, limit):
        original(context, row, limit)
        calls.append(row["source_path"])
        if len(calls) == 2:
            (config.source / row["source_path"]).write_bytes(b"replaced after final hash")

    monkeypatch.setattr(review_batch, "_verify_source", verify)
    with pytest.raises(ReviewConflict, match="Selected source changed during batch verification"):
        apply(config, run, ["a.png"], clear_labels=True)
    assert calls == ["a.png", "a.png"] and store.path.read_bytes() == before


def test_final_guard_cannot_change_store_context_or_source_unobserved(prepared):
    config, run, _ = prepared
    review_image(config, run, "c.png", caption="seed", reason="seed")
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    plan = preview_batch(config, run, ["a.png", "b.png"], decision="include", reason="selected")
    calls = []

    def guard():
        calls.append(None)
        if len(calls) == 2:
            (config.source / "a.png").write_bytes(b"late drift")

    with pytest.raises(ReviewConflict, match="Selected source changed"):
        apply_batch(
            config,
            run,
            ["a.png", "b.png"],
            decision="include",
            reason="selected",
            expected_revision=plan["current_revision"],
            expected_plan_sha256=plan["plan_sha256"],
            reviewer="Fixture assistant",
            reviewer_kind="assistant",
            guard=guard,
        )
    assert len(calls) == 2 and store.path.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "truncated",
        "interleaved",
        "actor",
        "count",
        "record",
        "membership",
        "noop",
        "repeated_manifest",
    ],
)
def test_malformed_or_spliced_batches_are_rejected(prepared, damage):
    config, run, _ = prepared
    apply(config, run, ["a.png", "b.png"], add_labels=["portrait"])
    store = ReviewStore(config.reviews, config.source)
    data = state(config)
    first, second = data["history"]
    if damage == "truncated":
        data["history"].pop()
        data["revision"] -= 1
        data["images"].pop(second["key"])
    elif damage == "interleaved":
        second["action"] = "edit"
        second.pop("batch")
        second.pop("reason")
    elif damage == "actor":
        second["reviewer"] = "different actor"
    elif damage == "count":
        second["batch"]["count"] = 3
    elif damage == "record":
        second["record"]["labels"] = ["different"]
    elif damage == "membership":
        first["batch"]["manifest"]["members"].reverse()
    elif damage == "noop":
        first["batch"]["manifest"]["operations"]["add_labels"] = []
    else:
        second["batch"]["manifest"] = first["batch"]["manifest"]
    store.path.write_text(json.dumps(data), encoding="utf-8")
    damaged = store.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_history(config, run)
    with pytest.raises(ValueError):
        preview_batch(config, run, ["c.png"], decision="include", reason="selected")
    assert store.path.read_bytes() == damaged


def test_batch_descriptor_is_stored_once_and_cannot_be_reused_for_another_action(prepared):
    config, run, _ = prepared
    first = apply(config, run, ["a.png", "b.png", "c.png", "d.png"], clear_labels=True)
    data = state(config)
    assert sum("manifest" in event["batch"] for event in data["history"]) == 1
    second = apply(config, run, ["a.png", "b.png"], add_labels=["portrait"])
    assert first["batch_id"] != second["batch_id"]
    history = inspect_history(config, run, limit=1)
    assert len(history["batches"]) == 1 and second["batch_id"] in history["batches"]
    assert len(inspect_history(config, run)["batches"]) == 2


def test_existing_graph_conflict_blocks_all_batch_changes(prepared):
    config, run, _ = prepared
    review_link(config, run, ["a.png", "b.png"], "distinct", "existing")
    store = ReviewStore(config.reviews, config.source)
    data = state(config)
    # A valid legacy history can contain inconsistent related/distinct decisions.
    from image_dataset_train.reviews import load_context, pair_for_paths

    context = load_context(run)
    pair = pair_for_paths(context, ["b.png", "d.png"])
    record = {key: value for key, value in pair.items() if key != "pair_id"}
    record.update(decision="related", reason="legacy conflict")
    data["revision"] += 1
    data["pairs"][pair["pair_id"]] = record
    data["history"].append(
        {
            "revision": data["revision"],
            "at": data["history"][0]["at"],
            "kind": "pairs",
            "key": pair["pair_id"],
            "record": record,
            "similarity_run": str(run),
        }
    )
    store.path.write_text(json.dumps(data), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="conflicts"):
        apply(config, run, ["a.png", "b.png"], decision="include")
    assert store.path.read_bytes() == before
