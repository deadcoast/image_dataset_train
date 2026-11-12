import json
from pathlib import Path

import pytest
from test_exports import reviewed as reviewed

from image_dataset_train.cli import main
from image_dataset_train.snapshot_comparison import read_comparison


def _args(groups):
    return ["snapshot-compare", "--before", str(groups), "--after", str(groups)]


def test_read_only_cli_is_config_independent_and_creates_no_files(
    reviewed, tmp_path, monkeypatch, capsys
):
    _, groups, _ = reviewed
    empty = tmp_path / "empty-cwd"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert main([*_args(groups), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["changed"] is False
    assert result["summary"]["common_occurrences"] == 5
    assert all(not changes for changes in result["changes"].values())
    assert not list(empty.iterdir())


def test_cli_human_output_discloses_group_caption_and_split_limits(reviewed, capsys):
    _, groups, _ = reviewed
    assert main(_args(groups)) == 0
    output = capsys.readouterr().out
    assert "groups; no changes" in output
    assert "Occurrences: 5 -> 5" in output
    assert "saved overrides" in output
    assert "effective captions and training splits are unavailable" in output


@pytest.mark.parametrize("configured", [False, True])
def test_cli_publishes_verifiable_receipt(reviewed, tmp_path, capsys, configured):
    config, groups, _ = reviewed
    if configured:
        config_file = tmp_path / "comparison.toml"
        config_file.write_text(
            "schema_version = 1\n[paths]\n"
            f'source = "{config.source.as_posix()}"\n'
            'runs = "configured-comparisons"\n',
            encoding="utf-8",
        )
        root = tmp_path / "configured-comparisons"
        arguments = ["--publish", "--config", str(config_file)]
    else:
        root = tmp_path / "explicit-comparisons"
        arguments = ["--output", str(root)]
    assert main([*_args(groups), *arguments, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    published = Path(result.pop("report"))
    assert published.parent == root
    assert read_comparison(published) == result


def test_cli_invalid_input_preserves_json_and_does_not_publish(tmp_path, capsys):
    root = tmp_path / "should-not-exist"
    assert main([*_args(tmp_path / "missing"), "--output", str(root), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert result["error"]["type"] == "FileNotFoundError"
    assert not root.exists()


def test_cli_rejects_ignored_configuration_without_writing(tmp_path, capsys):
    assert main([*_args(tmp_path), "--config", "missing.toml", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "--config requires --publish" in result["error"]["message"]
