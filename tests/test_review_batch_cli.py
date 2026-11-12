"""Bulk CLI binds explicit membership and exact saved collection context."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_review_history_cli import history as history
from test_review_history_cli import result, snapshot

from image_dataset_train import review_batch_cli
from image_dataset_train.cli import main
from image_dataset_train.preparation import read_preparation_job
from image_dataset_train.reviews import ReviewStore, review_image


@pytest.fixture
def batch(history, monkeypatch):
    _, workspace, _, _, _, _ = history
    _, state = read_preparation_job(workspace)
    monkeypatch.setattr(
        review_batch_cli, "implementation_identity", lambda: state["implementation"]
    )
    return history


def preview_args(batch, *, members=None, changes=None, named=False):
    _, workspace, _, _, _, entry = batch
    selector = ["--collection", entry["name"]] if named else ["--workspace", str(workspace)]
    return [
        "review-batch",
        *selector,
        *(members or ["--image", "b.png", "--image", "a.png"]),
        *(changes or ["--add-label", "reviewed", "--subset", "portrait"]),
        "--reason",
        "Reviewer's explicit correction 日本語",
        "--json",
    ]


def apply_args(arguments, preview):
    return [
        *arguments,
        "--apply",
        "--expected-revision",
        str(preview["current_revision"]),
        "--expected-plan-sha256",
        preview["plan_sha256"],
        "--reviewer",
        "CLI test assistant",
        "--reviewer-kind",
        "assistant",
    ]


def test_preview_shows_all_members_including_unchanged_and_creates_nothing(batch, capsys, tmp_path):
    args = preview_args(batch, changes=["--decision", "include"], named=True)
    before = snapshot(tmp_path)
    assert main(args) == 0
    view = result(capsys)
    assert view["selected_count"] == 2 and view["changed_count"] == 1
    assert [row["source_path"] for row in view["members"]] == ["a.png", "b.png"]
    assert view["members"][1]["changes"] == []
    assert view["source_revalidated"] is False
    assert len(view["plan_sha256"]) == 64
    assert snapshot(tmp_path) == before
    command = view["next_commands"][0]
    assert command["argv"][command["argv"].index("--collection") + 1] == batch[-1]["id"]
    assert command["argv"][command["argv"].index("--job") + 1] == batch[2]["job_id"]
    assert "Reviewer's explicit correction 日本語" in command["argv"]
    assert "Reviewer''s explicit correction 日本語" in command["powershell"]


def test_atomic_apply_preserves_captions_other_reviews_and_published_artifacts(batch, capsys):
    config, workspace, _, _, _, _ = batch
    store = ReviewStore(config.reviews, config.source)
    original = store.read()
    source, published = snapshot(config.source), snapshot(workspace / "jobs")
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)
    generated = view["next_commands"][0]["argv"][1:]
    generated[generated.index("--reviewer") + 1] = "CLI test assistant"
    generated[generated.index("--reviewer-kind") + 1] = "assistant"
    assert main([*generated, "--json"]) == 0
    saved = result(capsys)
    assert saved["status"] == "applied" and saved["revision"] == 5
    assert saved["current_revision"] == 3 and saved["changed_count"] == 2
    current = store.read()
    assert current["history"][:3] == original["history"]
    events = current["history"][3:]
    assert [event["revision"] for event in events] == [4, 5]
    assert {event["action"] for event in events} == {"batch"}
    assert {event["reviewer_kind"] for event in events} == {"assistant"}
    assert {event["batch"]["id"] for event in events} == {saved["batch_id"]}
    assert saved["members"][0]["proposed_record"]["caption_override"] == "second caption"
    assert snapshot(config.source) == source and snapshot(workspace / "jobs") == published
    command = saved["next_commands"][0]["argv"]
    assert command[1] == "resume" and "--refresh-reviews" in command and "--job" in command
    assert main(["review-history", "list", "--workspace", str(workspace), "--json"]) == 0
    history = result(capsys)
    assert history["current_revision"] == 5 and saved["batch_id"] in history["batches"]
    assert main(["review-history", "list", "--workspace", str(workspace)]) == 0
    text = capsys.readouterr().out
    assert "Batch: " + saved["batch_id"] in text
    assert "change 1 of 2" in text and "change 2 of 2" in text


def test_file_preview_binds_bytes_and_retains_file_in_generated_command(batch, capsys, tmp_path):
    path = tmp_path / "selection [日本語].json"
    path.write_text('["b.png", "a.png"]', encoding="utf-8")
    args = preview_args(batch, members=["--images-file", str(path)])
    assert main(args) == 0
    view = result(capsys)
    command = view["next_commands"][0]["argv"]
    assert "--images-file" in command and "--image" not in command
    assert command[command.index("--images-file") + 1] == str(path)
    path.write_text('[ "b.png", "a.png" ]', encoding="utf-8")
    before = snapshot(tmp_path)
    assert main(apply_args(args, view)) == 2
    assert "preview" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_selection_file_is_rechecked_inside_atomic_apply(batch, capsys, tmp_path, monkeypatch):
    from image_dataset_train import review_batch

    config, _, _, _, _, _ = batch
    path = tmp_path / "selected.json"
    path.write_text('["a.png", "b.png"]', encoding="utf-8")
    args = preview_args(batch, members=["--images-file", str(path)])
    assert main(args) == 0
    view = result(capsys)
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    original = review_batch.apply_batch

    def race(*values, **options):
        path.write_text('["a.png", "b.png"]\n', encoding="utf-8")
        return original(*values, **options)

    monkeypatch.setattr(review_batch, "apply_batch", race)
    assert main(apply_args(args, view)) == 2
    assert "Image selection changed" in result(capsys)["error"]["message"]
    assert store.path.read_bytes() == before


def test_job_is_rechecked_inside_atomic_apply(batch, capsys, monkeypatch):
    from image_dataset_train import review_batch

    config, workspace, _, _, _, _ = batch
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    original = review_batch.apply_batch

    def race(*values, **options):
        job, state = read_preparation_job(workspace)
        state["updated_at"] = "2026-11-11T22:15:00+00:00"
        (job / "job.json").write_text(json.dumps(state), encoding="utf-8")
        return original(*values, **options)

    monkeypatch.setattr(review_batch, "apply_batch", race)
    assert main(apply_args(args, view)) == 2
    assert "Review selection changed" in result(capsys)["error"]["message"]
    assert store.path.read_bytes() == before


def test_stale_preview_and_source_drift_never_partially_save(batch, capsys, tmp_path):
    config, _, _, similarity, _, _ = batch
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)
    review_image(config, similarity, "c.png", decision="exclude", reason="concurrent review")
    before = snapshot(tmp_path)
    assert main(apply_args(args, view)) == 2
    assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before
    assert main(args) == 0
    view = result(capsys)
    (config.source / "b.png").write_bytes(b"changed source")
    before = snapshot(tmp_path)
    assert main(apply_args(args, view)) == 2
    assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before


def test_offline_preview_is_read_only_and_apply_rejects_missing_sources(
    batch, capsys, tmp_path, monkeypatch
):
    config, _, _, _, _, _ = batch
    config.source.rename(config.source.with_name("offline source"))
    importer = builtins.__import__

    def optional_runtime_forbidden(name, *values, **options):
        if name.split(".")[0] in {"onnxruntime", "numpy"}:
            pytest.fail("Bulk preview must not import inference dependencies")
        return importer(name, *values, **options)

    monkeypatch.setattr(builtins, "__import__", optional_runtime_forbidden)
    args = preview_args(batch)
    before = snapshot(tmp_path)
    assert main(args) == 0
    view = result(capsys)
    assert view["source_revalidated"] is False and snapshot(tmp_path) == before
    assert main(apply_args(args, view)) == 2
    assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before


def test_invalid_selection_files_fail_without_creating_state(batch, capsys, tmp_path):
    path = tmp_path / "selected.json"
    args = preview_args(batch, members=["--images-file", str(path)])
    for raw in ['{"image":"a.png"}', '["a.png", 1]', '["a.png", "a.png"]', "[]", '["missing.png"]']:
        path.write_text(raw, encoding="utf-8")
        before = snapshot(tmp_path)
        assert main(args) == 2
        assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before
    path.write_bytes(b" " * (review_batch_cli.SELECTION_FILE_LIMIT + 1))
    before = snapshot(tmp_path)
    assert main(args) == 2
    assert "bounded regular metadata" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_linked_selection_file_is_rejected_without_following(batch, capsys, tmp_path, monkeypatch):
    path = tmp_path / "selected.json"
    path.write_text('["a.png"]', encoding="utf-8")
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda value: value == path or original(value))
    before = snapshot(tmp_path)
    assert main(preview_args(batch, members=["--images-file", str(path)])) == 2
    assert "link" in result(capsys)["error"]["message"].lower()
    assert snapshot(tmp_path) == before


def test_apply_requires_preview_guards_and_actor(batch, capsys, tmp_path):
    args = preview_args(batch)
    before = snapshot(tmp_path)
    variants = [
        ["--apply"],
        ["--apply", "--expected-revision", "3"],
        ["--apply", "--expected-revision", "3", "--expected-plan-sha256", "f" * 64],
    ]
    for flags in variants:
        assert main([*args, *flags]) == 2
        assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before


def test_unchanged_apply_does_not_append_history_and_still_checks_sources(batch, capsys):
    config, _, _, _, _, _ = batch
    args = preview_args(batch, members=["--image", "b.png"], changes=["--decision", "include"])
    assert main(args) == 0
    view = result(capsys)
    assert view["changed_count"] == 0 and view["next_commands"] == []
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    assert main(apply_args(args, view)) == 0
    saved = result(capsys)
    assert saved["status"] == "unchanged" and saved["revision"] == 3
    assert saved["batch_id"] is None and store.path.read_bytes() == before
    text_args = apply_args(args, view)
    text_args.remove("--json")
    assert main(text_args) == 0
    text = capsys.readouterr().out
    assert "Bulk review: unchanged" in text and "no changes or history revisions saved" in text
    assert "Preview SHA256:" not in text
    assert store.path.read_bytes() == before
    (config.source / "b.png").write_bytes(b"changed")
    assert main(apply_args(args, view)) == 2
    assert result(capsys)["status"] == "failed" and store.path.read_bytes() == before


def test_committed_batch_survives_guidance_failure(batch, capsys, monkeypatch):
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)

    def unavailable(_):
        raise OSError("Synthetic guidance failure")

    monkeypatch.setattr(review_batch_cli, "_refresh_command", unavailable)
    assert main(apply_args(args, view)) == 0
    saved = result(capsys)
    assert saved["status"] == "applied" and saved["revision"] == 5
    assert saved["next_commands"] == [] and saved["guidance_error"]["type"] == "OSError"
    config = batch[0]
    assert ReviewStore(config.reviews, config.source).read()["revision"] == 5


def test_different_build_uses_new_job_with_original_settings(batch, capsys, monkeypatch):
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)
    monkeypatch.setattr(
        review_batch_cli, "implementation_identity", lambda: {"version": "different"}
    )
    assert main(apply_args(args, view)) == 0
    command = result(capsys)["next_commands"][0]["argv"]
    assert command[1] == "prepare" and "--new" in command and "--refresh-reviews" not in command
    assert command[command.index("--config") + 1] == view["selection"]["config"]


def test_explicit_run_preview_and_text_show_complete_selection(batch, capsys):
    _, _, prepared, similarity, _, _ = batch
    args = preview_args(batch, changes=["--decision", "include"])
    args[1:3] = ["--run", str(similarity), "--config", prepared["config"]]
    assert main(args) == 0
    view = result(capsys)
    assert view["selection"]["kind"] == "run" and view["selected_count"] == 2
    args.remove("--json")
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "Selected images: 2; changed images: 1" in text
    assert "1. a.png" in text and "2. b.png" in text and "Unchanged." in text
    assert "Current:" in text and "Proposed:" in text and "second caption" in text
    assert "Published artifacts and human acceptance are unchanged." in text
    assert "--expected-plan-sha256" in text
    position = args.index("--decision")
    args[position : position + 2] = ["--clear-subset"]
    assert main(args) == 0
    cleared = capsys.readouterr().out
    assert 'subset: "portrait" -> null' in cleared and "subset: <absent> -> null" in cleared


def test_applied_text_labels_saved_revision_and_records(batch, capsys):
    args = preview_args(batch)
    assert main(args) == 0
    view = result(capsys)
    command = apply_args(args, view)
    command.remove("--json")
    assert main(command) == 0
    text = capsys.readouterr().out
    assert "Current review revision: 5" in text
    assert "Previous:" in text and "Saved:" in text and "Saved batch:" in text
