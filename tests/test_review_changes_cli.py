"""Exact report selection and stable paging for metadata-only review differences."""

import builtins
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run
from test_review_history_cli import history as history
from test_review_history_cli import result, snapshot

from image_dataset_train import review_history_cli
from image_dataset_train.cli import main
from image_dataset_train.preparation import read_preparation_job
from image_dataset_train.qa import create_qa
from image_dataset_train.review_history import preview_restore, restore_review
from image_dataset_train.reviews import review_image


def arguments(history, **options):
    _, workspace, prepared, _, _, _ = history
    args = [
        "review-history",
        "changes",
        "--workspace",
        str(workspace),
        "--job",
        prepared["job_id"],
        "--json",
    ]
    for name, value in options.items():
        args.extend(["--" + name.replace("_", "-"), str(value)])
    return args


def test_default_checkpoint_offline_named_pages_and_full_text_are_read_only(
    history, tmp_path, capsys, monkeypatch
):
    config, _, prepared, _, _, entry = history
    config.source.rename(config.source.with_name("offline source"))
    importer = builtins.__import__

    def no_runtime(name, *args, **kwargs):
        if name.split(".")[0] in {"onnxruntime", "numpy"}:
            pytest.fail("Changes inspection must not load the optional inference runtime")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_runtime)
    before = snapshot(tmp_path)
    assert (
        main(["review-history", "changes", "--collection", entry["name"], "--limit", "1", "--json"])
        == 0
    )
    view = result(capsys)
    assert view["report"] == prepared["outputs"]["qa"]["path"]
    assert view["state"] == "changed" and view["net_change_count"] == 2
    assert view["current_revision"] == 3 and view["snapshot_revision"] == 0
    assert view["source_revalidated"] is False and view["metadata_verified"] is True
    assert len(view["differences"]) == 1 and view["next_offset"] == 1
    next_page = view["next_commands"][0]["argv"]
    assert "--expected-inspection-sha256" in next_page and "--report" in next_page
    assert next_page[next_page.index("--collection") + 1] == entry["id"]
    assert next_page[next_page.index("--job") + 1] == prepared["job_id"]
    assert main([*next_page[1:], "--json"]) == 0
    page = result(capsys)
    assert page["offset"] == 1 and page["inspection_sha256"] == view["inspection_sha256"]
    assert snapshot(tmp_path) == before
    text_args = arguments(history)[:-1]
    assert main(text_args) == 0
    printed = capsys.readouterr().out
    assert "Snapshot revision: 0" in printed and "a.png" in printed and "b.png" in printed
    assert 'caption_override: <absent> -> "second caption"' in printed
    assert (
        "Selected inventory: compatible" in printed
        and "live source bytes are not validated" in printed
    )


def test_pagination_guard_rejects_a_new_review_without_writing(history, tmp_path, capsys):
    config, _, _, similarity, _, _ = history
    assert main(arguments(history, limit=1)) == 0
    view = result(capsys)
    command = view["next_commands"][0]["argv"]
    review_image(config, similarity, "c.png", caption="new correction", reason="fixture change")
    before = snapshot(tmp_path)
    assert main([*command[1:], "--json"]) == 2
    assert "between pages" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_explicit_run_requires_report_and_uses_guarded_group_publication(history, capsys):
    config, workspace, prepared, similarity, _, _ = history
    job, _ = read_preparation_job(workspace)
    args = [
        "review-history",
        "changes",
        "--run",
        str(similarity),
        "--config",
        str(job / "config.toml"),
        "--json",
    ]
    assert main(args) == 2
    assert "--report" in result(capsys)["error"]["message"]
    assert main([*args, "--report", prepared["outputs"]["qa"]["path"]]) == 0
    view = result(capsys)
    assert view["next_commands"][0]["argv"][1] == "groups"
    groups = Path(prepared["outputs"]["policy"]["path"])
    report, _ = create_qa(config, groups)
    assert main([*args, "--report", str(report)]) == 0
    assert result(capsys)["input_stage"] == "groups"


def test_changed_build_guidance_and_failed_guidance_remain_read_only(
    history, tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(review_history_cli, "implementation_identity", lambda: {"different": True})
    before = snapshot(tmp_path)
    assert main(arguments(history)) == 0
    view = result(capsys)
    assert view["next_commands"][0]["argv"][1] == "prepare"
    assert "--new" in view["next_commands"][0]["argv"]

    def unavailable(_selected):
        raise ValueError("fixture unavailable guidance")

    monkeypatch.setattr(review_history_cli, "_refresh_command", unavailable)
    assert main(arguments(history)) == 0
    view = result(capsys)
    assert view["state"] == "changed" and view["next_commands"] == []
    assert "guidance" in view["guidance_error"]["message"]
    assert snapshot(tmp_path) == before


def test_unchanged_and_restored_history_do_not_request_republication(collection, capsys):
    config, workspace = collection
    prepared = run(config, workspace)
    args = ["review-history", "changes", "--workspace", str(workspace), "--json"]
    assert main(args) == 0
    initial = result(capsys)
    assert initial["state"] == "unchanged" and initial["next_commands"] == []
    similarity = Path(prepared["outputs"]["similarity"]["path"])
    review_image(config, similarity, "a.png", caption="new caption", reason="temporary correction")
    plan = preview_restore(config, similarity, 1, before=True)
    restore_review(
        config,
        similarity,
        1,
        before=True,
        expected_revision=plan["current_revision"],
        expected_plan_sha256=plan["plan_sha256"],
        reason="Restore original",
        reviewer="fixture assistant",
        reviewer_kind="assistant",
    )
    assert main(args) == 0
    restored = result(capsys)
    assert restored["state"] == "history_only" and restored["history_delta_count"] == 2
    assert restored["net_change_count"] == 0 and restored["next_commands"] == []


@pytest.mark.parametrize(
    "options", [{"job": "stale-job"}, {"kind": "pairs", "limit": 0}, {"offset": -1}]
)
def test_rejected_selections_and_ranges_preserve_all_bytes(history, tmp_path, capsys, options):
    before = snapshot(tmp_path)
    assert main(arguments(history, **options)) == 2
    assert result(capsys)["status"] == "failed"
    assert snapshot(tmp_path) == before


def test_missing_qa_checkpoint_is_not_replaced_by_a_latest_directory(history, capsys, monkeypatch):
    original = review_history_cli._select

    def without_qa(args):
        selected = original(args)
        state = json.loads(json.dumps(selected.state))
        state["stages"]["qa"] = {"status": "pending"}
        return replace(selected, state=state)

    monkeypatch.setattr(review_history_cli, "_select", without_qa)
    assert main(arguments(history)) == 2
    assert "no completed QA checkpoint" in result(capsys)["error"]["message"]


def test_default_report_selection_never_reads_previews_or_report_assets(
    history, tmp_path, capsys, monkeypatch
):
    _, _, prepared, _, _, _ = history
    report = Path(prepared["outputs"]["qa"]["path"])
    original = Path.open
    before = snapshot(tmp_path)

    def metadata_only(path, *args, **kwargs):
        if path.is_relative_to(report) and path.name not in {
            "run.json",
            "entries.jsonl",
            "summary.json",
            "coverage.json",
        }:
            raise AssertionError(f"Read-only changes opened a QA asset: {path}")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", metadata_only)
        assert main(arguments(history)) == 0
        assert result(capsys)["state"] == "changed"
    assert snapshot(tmp_path) == before


def test_default_report_selection_rejects_checkpoint_metadata_changes(history, tmp_path, capsys):
    _, _, prepared, _, _, _ = history
    entries = Path(prepared["outputs"]["qa"]["path"]) / "entries.jsonl"
    entries.write_bytes(entries.read_bytes() + b"\n")
    before = snapshot(tmp_path)
    assert main(arguments(history)) == 2
    assert "checkpoint metadata changed: entries.jsonl" in result(capsys)["error"]["message"]
    assert snapshot(tmp_path) == before


def test_default_report_selection_rejects_output_from_a_different_attempt(
    history, capsys, monkeypatch
):
    original = review_history_cli._select

    def wrong_attempt(args):
        selected = original(args)
        state = json.loads(json.dumps(selected.state))
        state["stages"]["qa"]["output"] = state["stages"]["export"]["output"]
        return replace(selected, state=state)

    monkeypatch.setattr(review_history_cli, "_select", wrong_attempt)
    assert main(arguments(history)) == 2
    assert "outside its recorded attempt" in result(capsys)["error"]["message"]


def test_selector_drift_during_inspection_is_rejected(history, capsys, monkeypatch):
    original = review_history_cli._select
    calls = 0

    def drift(args):
        nonlocal calls
        calls += 1
        selected = original(args)
        return (
            selected
            if calls == 1
            else replace(selected, identity={**selected.identity, "job_id": "changed"})
        )

    monkeypatch.setattr(review_history_cli, "_select", drift)
    assert main(arguments(history)) == 2
    assert "selection changed" in result(capsys)["error"]["message"]
