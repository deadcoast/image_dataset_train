import json
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest
from test_preparation import collection as collection

from image_dataset_train import preparation, preparation_cli
from image_dataset_train.cli import build_parser, main
from image_dataset_train.config import load_config
from image_dataset_train.diagnostics import app_home
from image_dataset_train.reviews import review_image


def _prepare(config, workspace, **options):
    return preparation.prepare_directory(
        config,
        workspace,
        captions="existing",
        offline=True,
        max_distance=0,
        sample_size=3,
        progress=lambda _: None,
        **options,
    )


def _parse_commands(result):
    for command in result["next_commands"]:
        assert command["argv"][0] == "dataset"
        build_parser().parse_args(command["argv"][1:])


def test_default_workspace_failure_keeps_json_and_usable_resume_command(
    collection, monkeypatch, capsys
):
    config, original_workspace = collection
    workspace = original_workspace.parent / "job with ' quotes"
    execute = preparation._execute

    def temporary_failure(stage, *args):
        if stage == "export":
            raise OSError("Temporary output failure")
        return execute(stage, *args)

    monkeypatch.setattr(preparation_cli, "default_workspace", lambda _: workspace)
    monkeypatch.setattr(preparation, "_execute", temporary_failure)
    assert main(["prepare", str(config.source), "--captions", "existing", "--json"]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "failed" and result["prepared"] is False
    assert result["workspace"] == str(workspace)
    assert result["saved_job"]["status"] == "failed"
    assert "policy" in result["saved_job"]["outputs"]
    assert "export" not in result["saved_job"]["outputs"]
    assert result["next_action"] == "resume"
    assert result["next_commands"][0]["argv"] == [
        "dataset",
        "resume",
        str(workspace),
        "--job",
        result["saved_job"]["job_id"],
        "--json",
    ]
    assert "''" in result["next_commands"][0]["command"]
    assert Path(result["error"]["log"]).is_file()
    assert "trainime doctor" not in captured.out + captured.err
    _parse_commands(result)


def test_current_argument_failure_is_separate_from_saved_completed_job(collection, capsys):
    config, workspace = collection
    previous = _prepare(config, workspace)
    assert (
        main(
            [
                "prepare",
                str(config.source),
                "--workspace",
                str(workspace),
                "--resolution",
                "65",
                "--json",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed" and result["prepared"] is False
    assert result["next_action"] == "correct_arguments"
    assert result["saved_job"]["status"] == "completed"
    assert result["saved_job"]["outputs"] == previous["outputs"]
    assert preparation.job_status(workspace)["status"] == "completed"


def test_completed_human_output_points_to_report_and_review_command(collection, capsys):
    config, workspace = collection
    completed = _prepare(config, workspace)
    assert main(["status", str(workspace)]) == 0
    output = capsys.readouterr().out
    assert str(Path(completed["outputs"]["qa"]["path"]) / "report.html") in output
    assert "review-ui" in output and completed["config"] in output
    assert "--verify" in output and "catalog.sqlite" in output


def test_source_drift_provides_new_job_command_with_exact_saved_options(collection, capsys):
    config, workspace = collection
    previous = _prepare(config, workspace)
    (config.source / "a.txt").write_text("changed caption", encoding="utf-8")
    assert main(["resume", str(workspace), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["next_action"] == "new_job"
    argv = result["next_commands"][0]["argv"]
    assert argv[:3] == ["dataset", "prepare", str(config.source)]
    for flag, expected in (
        ("--workspace", str(workspace)),
        ("--config", previous["config"]),
        ("--captions", "existing"),
        ("--max-distance", "0"),
        ("--sample-size", "3"),
    ):
        assert argv[argv.index(flag) + 1] == expected
    assert "--offline" in argv and "--new" in argv
    assert result["saved_job"]["outputs"] == previous["outputs"]
    _parse_commands(result)


def test_new_job_command_retains_requested_resolution_and_runs_it(collection, capsys):
    config, workspace = collection
    config = replace(config, export=replace(config.export, resolution=1024))
    previous = _prepare(config, workspace)
    original_job = Path(previous["job"]) / "job.json"
    original_bytes = original_job.read_bytes()
    assert (
        main(
            [
                "prepare",
                str(config.source),
                "--workspace",
                str(workspace),
                "--captions",
                "existing",
                "--resolution",
                "512",
                "--json",
            ]
        )
        == 2
    )
    failure = json.loads(capsys.readouterr().out)
    assert failure["next_action"] == "new_job"
    argv = failure["next_commands"][0]["argv"]
    assert argv[argv.index("--resolution") + 1] == "512"
    assert "--new" in argv
    _parse_commands(failure)
    assert main(argv[1:]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed" and result["job"] != previous["job"]
    assert load_config(Path(result["config"])).export.resolution == 512
    exported = Path(result["outputs"]["export"]["path"])
    with (exported / "train.toml").open("rb") as stream:
        training = tomllib.load(stream)
    assert training["datasets"][0]["resolution"] == 512
    assert original_job.read_bytes() == original_bytes


def test_offline_missing_model_provides_valid_fetch_and_resume_commands(collection, capsys):
    config, workspace = collection
    assert (
        main(["prepare", str(config.source), "--workspace", str(workspace), "--offline", "--json"])
        == 2
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["next_action"] == "fetch_model"
    assert result["next_commands"][0]["argv"] == [
        "dataset",
        "fetch-model",
        "--config",
        result["saved_job"]["config"],
    ]
    assert result["next_commands"][1]["argv"] == [
        "dataset",
        "resume",
        str(workspace),
        "--job",
        result["saved_job"]["job_id"],
        "--json",
    ]
    assert "trainime doctor" not in captured.out + captured.err
    _parse_commands(result)


def test_stale_reviews_directly_offer_refresh(collection, capsys):
    config, workspace = collection
    previous = _prepare(config, workspace)
    review_image(
        config,
        Path(previous["outputs"]["similarity"]["path"]),
        "a.png",
        caption="new override",
        reason="new review",
    )
    assert main(["resume", str(workspace), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["next_action"] == "refresh_reviews"
    assert result["next_commands"][0]["argv"] == [
        "dataset",
        "resume",
        str(workspace),
        "--refresh-reviews",
        "--job",
        result["saved_job"]["job_id"],
        "--json",
    ]
    _parse_commands(result)


@pytest.mark.parametrize("option,value", [("--max-distance", "65"), ("--sample-size", "0")])
def test_invalid_preview_options_fail_before_inspection_without_writes(
    collection, monkeypatch, capsys, option, value
):
    config, workspace = collection
    monkeypatch.setattr(
        preparation_cli,
        "preview_preparation",
        lambda *args, **kwargs: pytest.fail("Invalid preview reached source inspection"),
    )
    assert (
        main(
            [
                "prepare",
                str(config.source),
                "--workspace",
                str(workspace),
                "--dryrun",
                option,
                value,
                "--json",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed" and result["saved_job"] is None
    assert result["next_action"] == "correct_arguments" and result["error"]["log"] is None
    assert not workspace.exists() and not (app_home() / "logs").exists()


def test_readonly_status_failure_preserves_bad_record_and_does_not_log(collection, capsys):
    _, workspace = collection
    workspace.mkdir()
    binding = workspace / "collection.json"
    binding.write_text("invalid json", encoding="utf-8")
    assert main(["status", str(workspace), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed" and result["saved_job"] is None
    assert result["next_action"] == "inspect_artifacts"
    assert result["error"]["log"] is None and not (app_home() / "logs").exists()
    assert binding.read_text() == "invalid json"


def test_cancellation_keeps_json_and_checkpoint_location(collection, monkeypatch, capsys):
    config, workspace = collection
    execute = preparation._execute

    def cancel(stage, *args):
        if stage == "similarity":
            raise KeyboardInterrupt
        return execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", cancel)
    assert (
        main(
            [
                "prepare",
                str(config.source),
                "--workspace",
                str(workspace),
                "--captions",
                "existing",
                "--json",
            ]
        )
        == 130
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "cancelled" and result["saved_job"]["status"] == "cancelled"
    assert "inventory" in result["saved_job"]["outputs"]
    assert result["next_commands"][0]["argv"][:3] == ["dataset", "resume", str(workspace)]
