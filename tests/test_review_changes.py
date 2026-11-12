"""Snapshot review differences require preserved lineage, never revision guesses."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_exports import reviewed as reviewed
from test_reviews import prepared as prepared

from image_dataset_train import review_changes
from image_dataset_train.exporting import export_dataset
from image_dataset_train.preparation_policy import prepare_groups
from image_dataset_train.qa import create_qa
from image_dataset_train.review_batch import apply_batch, preview_batch
from image_dataset_train.review_changes import inspect_review_changes
from image_dataset_train.review_history import (
    preview_restore,
    restore_review,
    validate_review_state,
)
from image_dataset_train.reviews import (
    ReviewConflict,
    ReviewStore,
    load_context,
    publish_groups,
    review_image,
    review_link,
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def published(prepared):
    config, run, _ = prepared
    review_image(config, run, "a.png", decision="include", caption="baseline", reason="original")
    groups, _ = publish_groups(config, run)
    report, _ = create_qa(config, groups)
    return config, run, groups, report


def inspect(published, **options):
    config, run, _, report = published
    return inspect_review_changes(config, run, report, **options)


def rehash_group_report(groups, report):
    meta = read(groups / "run.json")
    for name in meta["files"]:
        meta["files"][name] = hashlib.sha256((groups / name).read_bytes()).hexdigest()
    save(groups / "run.json", meta)
    qa = read(report / "run.json")
    qa["input_run_sha256"] = hashlib.sha256((groups / "run.json").read_bytes()).hexdigest()
    save(report / "run.json", qa)


def test_unchanged_offline_inspection_does_not_read_source_or_write(
    published, tmp_path, monkeypatch
):
    config, run, _, report = published
    config.source.rename(config.source.with_name("offline"))
    before = snapshot(tmp_path)
    original = Path.open

    def guarded(path, mode="r", *args, **kwargs):
        assert not path.absolute().is_relative_to(config.source)
        assert not any(value in mode for value in ("w", "a", "x", "+"))
        return original(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded)
        result = inspect_review_changes(config, run, report)
    assert result["state"] == "unchanged"
    assert result["snapshot_revision"] == result["current_revision"] == 1
    assert result["differences"] == [] and result["history_delta_count"] == 0
    assert result["metadata_verified"] and not result["source_revalidated"]
    assert result["report_sha256"] == hashlib.sha256((report / "run.json").read_bytes()).hexdigest()
    assert snapshot(tmp_path) == before


def test_empty_live_store_matches_frozen_initial_absence(prepared, tmp_path):
    config, run, _ = prepared
    groups, _ = publish_groups(config, run)
    report, _ = create_qa(config, groups)
    assert not config.reviews.exists()
    before = snapshot(tmp_path)
    result = inspect_review_changes(config, run, report)
    assert result["state"] == "unchanged" and result["current_store_sha256"] is None
    assert snapshot(tmp_path) == before and not config.reviews.exists()


def test_image_pair_changes_have_exact_fields_and_stable_pagination(published):
    config, run, _, _ = published
    review_image(config, run, "a.png", caption="new caption", reason="correction")
    review_image(config, run, "b.png", add_labels=["Portrait"], reason="reviewed label")
    review_link(config, run, ["a.png", "b.png"], "related", "reviewed relation")
    result = inspect(published, limit=2)
    assert result["state"] == "changed" and result["net_change_count"] == 3
    assert result["history_delta_count"] == 3 and result["counts"]["images"] == 2
    assert result["counts"]["pairs"] == 1 and result["counts"]["in_report"] == 3
    assert result["filtered_count"] == 3 and result["next_offset"] == 2
    assert [row["identity"]["source_path"] for row in result["differences"]] == ["a.png", "b.png"]
    first = result["differences"][0]
    assert first["before"]["caption_override"] == "baseline"
    assert first["after"]["caption_override"] == "new caption"
    assert {change["field"] for change in first["changes"]} == {"caption_override", "reason"}
    assert all(row["inventory_compatible"] for row in result["differences"])
    page = inspect(published, offset=2, limit=2)
    assert page["next_offset"] is None and page["differences"][0]["kind"] == "pairs"
    pairs = inspect(published, kind="pairs")
    assert pairs["net_change_count"] == 3 and pairs["filtered_count"] == 1
    assert pairs["differences"] == page["differences"]
    assert inspect(published, offset=100)["differences"] == []


def test_restore_to_original_is_history_only_and_batch_remains_compatible(published):
    config, run, _, _ = published
    review_image(config, run, "a.png", caption="temporary", reason="intermediate")
    plan = preview_restore(config, run, 1)
    restore_review(
        config,
        run,
        1,
        expected_revision=plan["current_revision"],
        expected_plan_sha256=plan["plan_sha256"],
        reason="Restore original",
        reviewer="fixture",
        reviewer_kind="assistant",
    )
    restored = inspect(published)
    assert restored["state"] == "history_only" and restored["net_change_count"] == 0
    assert restored["history_delta_count"] == 2
    batch = preview_batch(
        config, run, ["a.png", "b.png"], add_labels=["portrait"], reason="explicit batch"
    )
    apply_batch(
        config,
        run,
        ["a.png", "b.png"],
        add_labels=["portrait"],
        reason="explicit batch",
        expected_revision=batch["current_revision"],
        expected_plan_sha256=batch["plan_sha256"],
        reviewer="fixture",
        reviewer_kind="assistant",
    )
    changed = inspect(published)
    assert changed["state"] == "changed" and changed["net_change_count"] == 2
    assert changed["history_delta_count"] == 4
    newer_groups, _ = publish_groups(config, run)
    newer_report, _ = create_qa(config, newer_groups)
    assert inspect_review_changes(config, run, newer_report)["state"] == "unchanged"


def test_export_report_is_portable_metadata_only_and_exposes_outside_changes(
    reviewed, tmp_path, monkeypatch
):
    config, groups, drafts = reviewed
    run = Path(read(groups / "run.json")["similarity_run"])
    export, _ = export_dataset(config, groups, captions_run=drafts)
    report, _ = create_qa(config, export)
    review_image(config, run, "e.png", decision="include", reason="new inclusion")
    review_link(config, run, ["a.png", "e.png"], "distinct", "changed pair reason")
    groups.rename(groups.with_name("moved-original-groups"))
    config.source.rename(config.source.with_name("offline-source"))
    before = snapshot(tmp_path)
    original = Path.open

    def guarded(path, mode="r", *args, **kwargs):
        absolute = path.absolute()
        assert not absolute.is_relative_to(config.source)
        assert not any(absolute.is_relative_to(export / name) for name in ("train", "validation"))
        assert not any(value in mode for value in ("w", "a", "x", "+"))
        return original(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded)
        result = inspect_review_changes(config, run, report)
    assert result["input_stage"] == "export" and result["net_change_count"] == 2
    assert result["counts"]["outside_report"] == 1 and result["counts"]["partial_report"] == 1
    assert result["counts"]["incompatible"] == 0
    assert snapshot(tmp_path) == before


def test_changes_with_unknown_inventory_identity_are_visible(published):
    config, _, _, _ = published
    store = ReviewStore(config.reviews, config.source)
    state = store.read()
    event = copy.deepcopy(state["history"][0])
    event["record"].update(source_path="missing.png", sha256="1" * 64)
    from image_dataset_train.reviews import _image_key

    key = _image_key(event["record"])
    event.update(revision=2, key=key)
    state["revision"] = 2
    state["history"].append(event)
    state["images"][key] = event["record"]
    save(store.path, state)
    result = inspect(published)
    assert result["counts"]["outside_report"] == result["counts"]["incompatible"] == 1
    assert result["differences"][0]["identity"]["source_path"] == "missing.png"


@pytest.mark.parametrize("stage", ["groups", "export"])
def test_prepared_snapshot_keeps_saved_review_lineage_and_works_offline(reviewed, stage):
    config, base, drafts = reviewed
    run = Path(read(base / "run.json")["similarity_run"])
    groups, _ = prepare_groups(config, base, captions_run=drafts)
    if stage == "export":
        selected, _ = export_dataset(config, groups, captions_run=drafts, allow_prepared=True)
    else:
        selected = groups
    report, _ = create_qa(config, selected)
    base.rename(base.with_name("offline-base"))
    if stage == "export":
        groups.rename(groups.with_name("offline-prepared"))
    config.source.rename(config.source.with_name("offline-source"))
    result = inspect_review_changes(config, run, report)
    assert result["state"] == "unchanged" and result["input_stage"] == stage
    assert not result["source_revalidated"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason", "different"),
        ("caption_override", "different"),
        ("labels", ["different"]),
        ("review_decision", "exclude"),
    ],
)
def test_group_projection_must_match_captured_review_records(published, field, value):
    _, _, groups, report = published
    rows = [json.loads(line) for line in (groups / "groups.jsonl").read_text().splitlines()]
    next(
        member for group in rows for member in group["members"] if member["source_path"] == "a.png"
    )[field] = value
    (groups / "groups.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    rehash_group_report(groups, report)
    with pytest.raises(ValueError, match="annotations differ"):
        inspect(published)


def test_group_partition_must_match_captured_pair_reviews(published):
    from image_dataset_train.reviews import _identity

    _, _, groups, report = published
    rows = [json.loads(line) for line in (groups / "groups.jsonl").read_text().splitlines()]
    rows[0]["members"].extend(rows.pop()["members"])
    rows[0]["group_id"] = _identity(
        sorted([m["source_path"], m["sha256"]] for m in rows[0]["members"])
    )
    (groups / "groups.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    rehash_group_report(groups, report)
    with pytest.raises(ValueError, match="membership differs"):
        inspect(published)


@pytest.mark.parametrize("target", ["report", "input", "provenance"])
def test_linked_snapshot_paths_are_rejected_before_resolution(reviewed, tmp_path, target):
    config, groups, drafts = reviewed
    run = Path(read(groups / "run.json")["similarity_run"])
    export, _ = export_dataset(config, groups, captions_run=drafts)
    report, _ = create_qa(config, export)
    alias = tmp_path / "linked"
    destination = (
        report.parent
        if target == "report"
        else export.parent
        if target == "input"
        else export / "provenance"
    )
    try:
        alias.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    if target == "report":
        report = alias / report.name
    elif target == "input":
        meta = read(report / "run.json")
        meta["input_run"] = str(alias / export.name)
        save(report / "run.json", meta)
    else:
        alias.unlink()
        destination.rename(export / "original-provenance")
        destination.symlink_to(export / "original-provenance", target_is_directory=True)
    with pytest.raises(ValueError, match="Linked review history"):
        inspect_review_changes(config, run, report)


@pytest.mark.parametrize("value", [None, "", "not-a-sha", True])
def test_input_metadata_requires_exact_qa_checksum(published, value):
    _, _, _, report = published
    meta = read(report / "run.json")
    meta["input_run_sha256"] = value
    save(report / "run.json", meta)
    with pytest.raises(ValueError):
        inspect(published)


def test_missing_qa_input_digest_is_not_unchecked_lineage(published):
    _, _, _, report = published
    meta = read(report / "run.json")
    del meta["input_run_sha256"]
    save(report / "run.json", meta)
    with pytest.raises(ValueError):
        inspect(published)


@pytest.mark.parametrize("artifact", ["reviews.json", "groups.jsonl", "summary.json"])
def test_null_declared_group_digest_is_rejected(published, artifact):
    _, _, groups, report = published
    meta = read(groups / "run.json")
    meta["files"][artifact] = None
    save(groups / "run.json", meta)
    qa = read(report / "run.json")
    qa["input_run_sha256"] = hashlib.sha256((groups / "run.json").read_bytes()).hexdigest()
    save(report / "run.json", qa)
    with pytest.raises(ValueError):
        inspect(published)


@pytest.mark.parametrize(
    "target",
    ["source", "similarity_run", "inventory_run", "inventory_manifest_sha256", "review_revision"],
)
def test_group_metadata_joins_must_match_selected_context(published, target):
    _, _, groups, report = published
    meta = read(groups / "run.json")
    meta[target] = (
        5
        if target == "review_revision"
        else "0" * 64
        if target.endswith("sha256")
        else str(groups / "wrong")
    )
    save(groups / "run.json", meta)
    rehash_group_report(groups, report)
    with pytest.raises(ValueError):
        inspect(published)


@pytest.mark.parametrize(
    "target", ["source", "schema_version", "revision", "images", "pairs", "history"]
)
def test_pure_validator_checks_captured_top_level_without_store_reader(published, target):
    config, run, _, _ = published
    state = copy.deepcopy(ReviewStore(config.reviews, config.source).read())
    state[target] = (
        str(config.source / "different")
        if target == "source"
        else 99
        if target in {"schema_version", "revision"}
        else None
    )
    with pytest.raises(ValueError):
        validate_review_state(state, load_context(run))


@pytest.mark.parametrize("mode", ["truncated", "diverged", "same_revision_different_state"])
def test_live_history_must_preserve_frozen_prefix(published, mode):
    config, _, _, _ = published
    store = ReviewStore(config.reviews, config.source)
    state = store.read()
    if mode == "truncated":
        state.update(revision=0, history=[], images={})
    else:
        state["history"][0]["record"]["reason"] = "changed old event"
        if mode == "diverged":
            state["images"][state["history"][0]["key"]]["reason"] = "changed old event"
    save(store.path, state)
    with pytest.raises(ValueError):
        inspect(published)


@pytest.mark.parametrize("artifact", ["entries.jsonl", "summary.json", "coverage.json"])
def test_changed_report_payload_fails_checksums(published, artifact):
    _, _, _, report = published
    with (report / artifact).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        inspect(published)


def test_captured_bad_history_rejected_even_with_refreshed_artifact_digests(published):
    _, _, groups, report = published
    state = read(groups / "reviews.json")
    state["history"][0]["revision"] = 7
    save(groups / "reviews.json", state)
    rehash_group_report(groups, report)
    with pytest.raises(ValueError, match="complete sequence"):
        inspect(published)


@pytest.mark.parametrize("target", ["report", "current", "context"])
def test_concurrent_metadata_or_review_change_is_rejected(published, monkeypatch, target):
    config, run, _, report = published
    original = review_changes._loaded
    calls = 0

    def racing(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if target == "current":
                review_image(config, run, "a.png", caption="concurrent", reason="fixture")
            elif target == "report":
                meta = read(report / "run.json")
                meta["created_at"] = "changed during inspection"
                save(report / "run.json", meta)
            else:
                meta = read(run / "run.json")
                meta["fixture_change"] = True
                save(run / "run.json", meta)
        return original(*args, **kwargs)

    monkeypatch.setattr(review_changes, "_loaded", racing)
    with pytest.raises(ReviewConflict):
        inspect(published)


@pytest.mark.parametrize("target", ["current", "context"])
def test_live_change_during_final_metadata_check_is_rejected(published, monkeypatch, target):
    config, run, _, _ = published
    original = review_changes._Metadata.verify

    def racing(reader):
        original(reader)
        if target == "current":
            review_image(config, run, "a.png", caption="late change", reason="fixture")
        else:
            meta = read(run / "run.json")
            meta["fixture_change"] = True
            save(run / "run.json", meta)

    monkeypatch.setattr(review_changes._Metadata, "verify", racing)
    with pytest.raises(ReviewConflict, match="changed while inspecting snapshot"):
        inspect(published)


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": True},
        {"offset": -1},
        {"offset": False},
        {"kind": "other"},
    ],
)
def test_invalid_page_or_filter_is_rejected(published, options):
    with pytest.raises(ValueError):
        inspect(published, **options)
