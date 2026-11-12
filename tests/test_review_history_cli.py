"""History selection is explicit, read-only until apply, and guarded across races."""

from __future__ import annotations

import builtins
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run

from image_dataset_train import review_history_cli
from image_dataset_train.cli import main
from image_dataset_train.collection_registry import CollectionRegistry
from image_dataset_train.preparation import _write_config, read_preparation_job
from image_dataset_train.reviews import ReviewStore, _image_key, review_image


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def result(capsys):
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def history(collection, monkeypatch):
    config, workspace = collection
    prepared = run(config, workspace)
    similarity = Path(prepared["outputs"]["similarity"]["path"])
    first = review_image(
        config, similarity, "a.png", caption="first caption", reason="fixture first"
    )
    review_image(
        config,
        similarity,
        "a.png",
        caption="second caption",
        add_labels=["subject"],
        subset="portrait",
        reason="fixture second",
    )
    review_image(config, similarity, "b.png", decision="include", reason="unrelated fixture")
    entry = CollectionRegistry().register(workspace, name="Artist's collection 日本語")
    _, state = read_preparation_job(workspace)
    # Other agents may edit source during focused development tests; test the current-build
    # continuation branch against the fixture's recorded identity deterministically.
    monkeypatch.setattr(
        review_history_cli, "implementation_identity", lambda: state["implementation"]
    )
    return config, workspace, prepared, similarity, first, entry


def preview(history, capsys, *, before=False):
    _, workspace, _, _, first, _ = history
    arguments = [
        "review-history",
        "restore",
        "--workspace",
        str(workspace),
        "--revision",
        str(first["revision"]),
        "--json",
    ]
    if before:
        arguments.append("--before")
    assert main(arguments) == 0
    return result(capsys)


def apply_args(view, *, before=False):
    args = [
        "review-history",
        "restore",
        "--workspace",
        view["selection"]["workspace"],
        "--job",
        view["selection"]["job_id"],
        "--revision",
        str(view["target_revision"]),
        "--expected-revision",
        str(view["current_revision"]),
        "--expected-plan-sha256",
        view["plan_sha256"],
        "--apply",
        "--reason",
        "assistant fixture restoration",
        "--reviewer",
        "CLI test assistant",
        "--reviewer-kind",
        "assistant",
        "--json",
    ]
    if before:
        args.append("--before")
    return args


def test_offline_history_pages_and_preview_are_read_only(history, tmp_path, capsys, monkeypatch):
    config, workspace, prepared, _, _, entry = history
    config.source.rename(config.source.with_name("offline source"))
    importer = builtins.__import__

    def optional_runtime_forbidden(name, *args, **kwargs):
        if name.split(".")[0] in {"onnxruntime", "numpy"}:
            pytest.fail("History must not import optional inference dependencies")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", optional_runtime_forbidden)
    before = snapshot(tmp_path)
    assert (
        main(["review-history", "list", "--collection", entry["name"], "--limit", "1", "--json"])
        == 0
    )
    listed = result(capsys)
    assert listed["current_revision"] == 3 and listed["total_events"] == 3
    assert len(listed["events"]) == 1 and listed["next_offset"] == 1
    assert listed["events"][0]["reviewer_kind"] == "unknown"
    command = listed["next_commands"][0]["argv"]
    assert command[command.index("--collection") + 1] == entry["id"]
    assert command[command.index("--job") + 1] == prepared["job_id"]
    assert main([*command[1:], "--json"]) == 0
    assert result(capsys)["offset"] == 1
    view = preview(history, capsys)
    assert view["current_record"]["caption_override"] == "second caption"
    assert view["proposed_record"]["caption_override"] == "first caption"
    assert len(view["plan_sha256"]) == 64 and view["applicable"]
    assert snapshot(tmp_path) == before


def test_named_preview_command_quotes_exact_selection_and_does_not_apply(history, capsys):
    _, _, prepared, _, first, entry = history
    assert (
        main(
            [
                "review-history",
                "show",
                "--collection",
                entry["name"],
                "--job",
                prepared["job_id"],
                "--revision",
                str(first["revision"]),
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Preview SHA256:" in text and "second caption" in text and "first caption" in text
    assert "Published artifacts and human acceptance are unchanged" in text
    assert "'--collection' '" + entry["id"] + "'" in text
    assert "'--job' '" + prepared["job_id"] + "'" in text
    assert "'--expected-plan-sha256'" in text and "'--apply'" in text
    assert "Target: a.png" in text and "Actor: not recorded (unknown)" in text
    assert "Selected historical change:" in text and "Before: absent" in text
    assert 'caption_override: <absent> -> "first caption"' in text
    assert "Current-to-proposed changes:" in text
    assert 'caption_override: "second caption" -> "first caption"' in text
    assert main(["review-history", "show", "--collection", entry["name"], "--revision", "2"]) == 0
    current = capsys.readouterr().out
    assert 'caption_override: "first caption" -> "second caption"' in current
    assert "The selected state already matches; no revision is needed." in current


@pytest.mark.parametrize("before", [False, True])
def test_apply_restores_exact_record_and_emits_refresh_command(history, capsys, before):
    config, workspace, _, _, _, _ = history
    store = ReviewStore(config.reviews, config.source)
    original = store.read()
    original_source = snapshot(config.source)
    immutable = snapshot(workspace / "jobs")
    view = preview(history, capsys, before=before)
    assert main(apply_args(view, before=before)) == 0
    restored = result(capsys)
    assert restored["status"] == "restored" and restored["revision"] == 4
    state = store.read()
    assert state["history"][:-1] == original["history"]
    key = _image_key(view["selected_event"]["after"])
    if before:
        assert key not in state["images"]
    else:
        assert state["images"][key] == view["proposed_record"]
        assert "labels" not in state["images"][key] and "subset" not in state["images"][key]
    args = restored["next_commands"][0]["argv"]
    assert args[1] == "resume" and "--refresh-reviews" in args and "--job" in args
    assert snapshot(config.source) == original_source and snapshot(workspace / "jobs") == immutable


def test_stale_review_preview_rejects_without_logs_or_partial_changes(history, capsys, tmp_path):
    config, _, _, similarity, _, _ = history
    view = preview(history, capsys)
    review_image(config, similarity, "c.png", decision="exclude", reason="concurrent fixture")
    before = snapshot(tmp_path)
    assert main(apply_args(view)) == 2
    assert "preview" in result(capsys)["error"]["message"].lower()
    assert snapshot(tmp_path) == before


def test_current_job_change_cannot_redirect_saved_restore(history, capsys, tmp_path):
    config, workspace, _, _, _, _ = history
    view = preview(history, capsys)
    run(config, workspace, new=True)
    before = snapshot(tmp_path)
    assert main(apply_args(view)) == 2
    assert "Current preparation job" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_configuration_bytes_are_bound_even_when_effective_settings_match(
    history, capsys, tmp_path
):
    _, workspace, _, _, _, _ = history
    view = preview(history, capsys)
    job, state = read_preparation_job(workspace)
    path = job / "config.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# changed fixture metadata\n", encoding="utf-8"
    )
    state["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (job / "job.json").write_text(json.dumps(state), encoding="utf-8")
    before = snapshot(tmp_path)
    assert main(apply_args(view)) == 2
    assert "selection changed" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_job_binding_is_rechecked_inside_restore_lock(history, capsys, monkeypatch):
    from image_dataset_train import review_history

    config, workspace, _, _, _, _ = history
    view = preview(history, capsys)
    store = ReviewStore(config.reviews, config.source)
    before = store.path.read_bytes()
    original = review_history.restore_review

    def race(*args, **kwargs):
        job, state = read_preparation_job(workspace)
        state["updated_at"] = "2026-11-11T12:34:56+00:00"
        (job / "job.json").write_text(json.dumps(state), encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(review_history, "restore_review", race)
    assert main(apply_args(view)) == 2
    assert "selection changed" in result(capsys)["error"]["message"]
    assert store.path.read_bytes() == before


def test_old_build_restore_offers_new_job_without_rebinding(history, capsys, monkeypatch):
    _, _, _, _, _, _ = history
    view = preview(history, capsys)
    monkeypatch.setattr(review_history_cli, "implementation_identity", lambda: {"version": "newer"})
    assert main(apply_args(view)) == 0
    saved = result(capsys)
    command = saved["next_commands"][0]["argv"]
    assert command[1] == "prepare" and "--new" in command and "--refresh-reviews" not in command
    assert command[command.index("--config") + 1] == view["selection"]["config"]


def test_committed_restore_survives_continuation_guidance_failure(history, capsys, monkeypatch):
    config, workspace, _, _, _, _ = history
    view = preview(history, capsys)

    def unavailable(_):
        raise OSError("Synthetic package metadata unavailable")

    monkeypatch.setattr(review_history_cli, "_refresh_command", unavailable)
    assert main(apply_args(view)) == 0
    saved = result(capsys)
    assert saved["status"] == "restored" and saved["revision"] == 4
    assert saved["next_commands"] == []
    assert saved["guidance_error"]["type"] == "OSError"
    assert ReviewStore(config.reviews, config.source).read()["revision"] == 4
    assert main(["review-history", "list", "--workspace", str(workspace), "--limit", "1"]) == 0
    text = capsys.readouterr().out
    assert "Target: a.png" in text and "Actor: CLI test assistant (assistant)" in text
    assert 'caption_override: "second caption" -> "first caption"' in text
    assert "assistant fixture restoration" in text


def test_applied_text_uses_new_revision_and_previous_restored_labels(history, capsys):
    view = preview(history, capsys)
    arguments = apply_args(view)
    arguments.remove("--json")
    assert main(arguments) == 0
    text = capsys.readouterr().out
    assert "Current review revision: 4" in text and "Current review revision: 3" not in text
    assert "Previous record:" in text and "Restored record:" in text and "Applied changes:" in text


def test_unrelated_linked_model_root_does_not_block_offline_history(history, capsys, monkeypatch):
    config, workspace, _, _, _, _ = history
    original_is_junction = Path.is_junction
    original_resolve = Path.resolve
    replacement = config.models.with_name("moved-model-cache")

    def junction(path):
        return path == config.models or original_is_junction(path)

    def resolve(path, *args, **kwargs):
        return replacement if path == config.models else original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_junction", junction)
    monkeypatch.setattr(Path, "resolve", resolve)
    assert main(["review-history", "list", "--workspace", str(workspace), "--json"]) == 0
    assert result(capsys)["current_revision"] == 3


@pytest.mark.parametrize("case", ["uncheckpointed", "changed-artifact", "config"])
def test_invalid_preparation_contract_rejects_without_adopting_artifacts(
    history, capsys, tmp_path, case
):
    _, workspace, _, similarity, _, _ = history
    job, state = read_preparation_job(workspace)
    if case == "uncheckpointed":
        state["stages"]["similarity"]["status"] = "running"
        (job / "job.json").write_text(json.dumps(state), encoding="utf-8")
    elif case == "changed-artifact":
        (similarity / "summary.json").write_text("tampered", encoding="utf-8")
    else:
        (job / "config.toml").write_text("tampered", encoding="utf-8")
    before = snapshot(tmp_path)
    assert main(["review-history", "list", "--workspace", str(workspace), "--json"]) == 2
    assert result(capsys)["status"] == "failed"
    assert snapshot(tmp_path) == before


def test_explicit_run_requires_matching_configuration(history, capsys, tmp_path):
    config, _, prepared, similarity, _, _ = history
    assert (
        main(
            [
                "review-history",
                "list",
                "--run",
                str(similarity),
                "--config",
                prepared["config"],
                "--image",
                "a.png",
                "--json",
            ]
        )
        == 0
    )
    assert result(capsys)["matching_events"] == 2
    wrong = tmp_path / "wrong.toml"
    _write_config(wrong, replace(config, source=tmp_path / "different source"))
    before = snapshot(tmp_path)
    assert (
        main(["review-history", "list", "--run", str(similarity), "--config", str(wrong), "--json"])
        == 2
    )
    assert result(capsys)["status"] == "failed" and snapshot(tmp_path) == before


def test_apply_requires_explicit_guards_actor_and_reason(history, capsys, tmp_path):
    _, workspace, _, _, first, _ = history
    before = snapshot(tmp_path)
    assert (
        main(
            [
                "review-history",
                "restore",
                "--workspace",
                str(workspace),
                "--revision",
                str(first["revision"]),
                "--apply",
                "--json",
            ]
        )
        == 2
    )
    assert "expected-revision" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before
