from pathlib import Path

import pytest

from image_dataset_train.cli import main
from image_dataset_train.config import load_config


def test_config_paths_are_relative_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "settings"
    directory.mkdir()
    config_file = directory / "config.toml"
    config_file.write_text(
        'schema_version = 1\n[paths]\nsource = "../originals"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(config_file)
    assert config.source == tmp_path / "originals"
    assert config.runs == directory / "data" / "runs"


@pytest.mark.parametrize(
    "content",
    [
        "schema_version = true",
        "schema_version = 2",
        "schema_version = 1\nunknown = 1",
        'schema_version = 1\n[paths]\nsource = ""',
        "schema_version = 1\n[validation]\nmin_short_side = true",
        "schema_version = 1\n[validation]\nmax_decode_pixels = -1",
        "schema_version = 1\n[validation]\nmin_short_side = 5000",
        "schema_version = 1\n[validation]\nmax_pixels = 123",
        "schema_version = 1\npaths = []",
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_cli_runs_and_reports_missing_source(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    path = tmp_path / "config.toml"
    path.write_text("schema_version = 1\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    args = [
        "scan",
        "--config",
        str(path),
        "--source",
        str(source),
        "--runs",
        str(tmp_path / "runs"),
    ]
    assert main(args) == 0
    assert "Inventory only" in capsys.readouterr().out
    assert main(["scan", "--config", str(path), "--source", str(tmp_path / "absent")]) == 2
    assert "error:" in capsys.readouterr().err
