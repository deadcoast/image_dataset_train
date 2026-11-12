import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_preparation import collection as collection
from test_preparation import run

from image_dataset_train.cli import build_parser, main
from image_dataset_train.collection_catalog_cli import _commands
from image_dataset_train.collection_registry import CollectionRegistry
from image_dataset_train.preparation import _write_config
from image_dataset_train.qa import create_qa


def _files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def registered(collection):
    config, workspace = collection
    result = run(config, workspace)
    entry = CollectionRegistry().register(workspace, name="Fixture collection")
    return config, workspace, result, entry


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def _run_records(entry, capsys, *filters):
    assert main(["runs", "--collection", entry["id"], *filters, "--json"]) == 0
    return _json(capsys)["runs"]


def test_empty_list_is_read_only_and_suggests_concrete_start_commands(
    tmp_path, monkeypatch, capsys
):
    outside = tmp_path / "outside checkout"
    outside.mkdir()
    monkeypatch.chdir(outside)
    before = _files(tmp_path)
    assert main(["collections"]) == 0
    text = capsys.readouterr().out
    assert "No registered collections" in text
    assert "dataset prepare <directory>" in text and "dataset collections add <workspace>" in text
    assert main(["collections", "--json"]) == 0
    assert _json(capsys) == {"collections": []}
    assert _files(tmp_path) == before


def test_add_name_source_filter_and_remove_only_change_registration(collection, capsys):
    config, workspace = collection
    run(config, workspace)
    original = _files(workspace)
    sources = _files(config.source)
    name = "Artist's collection 日本語"
    assert main(["collections", "add", str(workspace), "--name", name, "--json"]) == 0
    result = _json(capsys)
    assert result["action"] == "registered" and result["collection"]["name"] == name
    entry = result["collection"]
    assert main(["collections", "--source", str(config.source), "--json"]) == 0
    assert _json(capsys)["collections"] == [entry]
    assert main(["collections", "--source", str(config.source.parent / "other"), "--json"]) == 0
    assert _json(capsys)["collections"] == []
    assert main(["collections", "add", str(workspace), "--json"]) == 0
    assert _json(capsys)["collection"]["name"] == name
    assert main(["collections", "remove", name, "--json"]) == 0
    assert _json(capsys)["action"] == "unregistered"
    assert CollectionRegistry().list() == []
    assert _files(workspace) == original and _files(config.source) == sources


def test_catalog_browsing_never_constructs_publication_or_requires_source_online(
    registered, monkeypatch, capsys
):
    import image_dataset_train.review_publication as publication

    config, workspace, _, entry = registered

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only catalog browsing must not construct Publication")

    monkeypatch.setattr(publication.Publication, "__init__", forbidden)
    config.source.rename(config.source.with_name("source offline"))
    protected = _files(workspace)
    assert main(["collections", "show", entry["id"], "--json"]) == 0
    shown = _json(capsys)
    assert shown["collection"]["id"] == entry["id"] and shown["runs"]
    records = _run_records(entry, capsys)
    assert all(row["metadata_verification"] == "metadata_only" for row in records)
    assert all(row["source"] == entry["source"] for row in records)
    assert _files(workspace) == protected


def test_run_filters_exact_selection_and_digest_guarded_next_command(registered, capsys):
    _, _, _, entry = registered
    today = datetime.now(UTC).date().isoformat()
    records = _run_records(
        entry, capsys, "--stage", "qa", "--status", "completed", "--since", today, "--until", today
    )
    assert len(records) == 1
    record = records[0]
    selected = _run_records(entry, capsys, "--run", record["id"])
    assert len(selected) == 1
    assert {key: selected[0][key] for key in record} == record
    args = record["commands"]["args"]
    assert args[:4] == ["dataset", "collections", "review", entry["id"]]
    assert args[args.index("--run") + 1] == record["id"]
    assert args[args.index("--expected-sha256") + 1] == record["run_sha256"]
    assert "--expected-sha256" in record["commands"]["powershell"]
    assert _run_records(entry, capsys, "--stage", "no-such-stage") == []


@pytest.mark.parametrize(
    "filters",
    [
        ["--since", "20261109"],
        ["--since", "2026-02-30"],
        ["--until", "yesterday"],
        ["--since", "2026-11-10", "--until", "2026-11-09"],
    ],
)
def test_invalid_date_filters_report_json_without_writes(registered, capsys, filters):
    _, workspace, _, entry = registered
    protected = _files(workspace)
    assert main(["runs", "--collection", entry["id"], *filters, "--json"]) == 2
    result = _json(capsys)
    assert result["status"] == "failed" and result["error"]["type"] == "ValueError"
    assert _files(workspace) == protected


def test_terminal_output_keeps_status_verification_and_acceptance_distinct(registered, capsys):
    _, _, _, entry = registered
    assert main(["collections", "show", entry["id"]]) == 0
    output = capsys.readouterr().out
    assert "Current job:" in output and "Current review revision:" in output
    assert "Metadata only" in output
    assert "not process liveness" in output and "dataset acceptance" in output
    assert "Record ID:" not in output and "SHA256:" not in output
    assert "Inspect:" in output and "Continue:" in output and "QA reports:" in output
    assert "'--job'" in output and "'--stage' 'qa'" in output
    assert "\x1b" not in output


def test_review_launch_checks_qa_and_matching_configuration_before_existing_server(
    registered, monkeypatch, capsys
):
    import image_dataset_train.review_ui as reviewer

    config, workspace, _, entry = registered
    record = _run_records(entry, capsys, "--stage", "qa")[0]
    calls = []

    def serve(selected_config, selected_run, port, *, open_browser, config_path):
        calls.append((selected_config, selected_run, port, open_browser, config_path))

    monkeypatch.setattr(reviewer, "serve_reviews", serve)
    protected = _files(workspace)
    assert (
        main(
            [
                "collections",
                "review",
                entry["id"],
                "--run",
                record["id"],
                "--expected-sha256",
                record["run_sha256"],
                "--no-open",
                "--port",
                "8123",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Opening checked QA:" in output and "no acceptance" in output
    assert len(calls) == 1
    selected_config, selected_run, port, opened, config_path = calls[0]
    assert selected_config.source == config.source and selected_config.reviews == config.reviews
    assert selected_run == Path(record["path"]) and port == 8123 and opened is False
    assert config_path == Path(record["config_path"])
    assert _files(workspace) == protected


@pytest.mark.parametrize("failure", ["wrong_stage", "stale_checksum", "damaged_qa", "bad_port"])
def test_review_rejects_invalid_selection_before_server(registered, monkeypatch, capsys, failure):
    import image_dataset_train.review_ui as reviewer

    _, workspace, _, entry = registered
    record = _run_records(entry, capsys, "--stage", "export" if failure == "wrong_stage" else "qa")[
        0
    ]

    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected selection must not start the reviewer")

    monkeypatch.setattr(reviewer, "serve_reviews", forbidden)
    extra = []
    if failure == "stale_checksum":
        extra = ["--expected-sha256", "0" * 64]
    elif failure == "damaged_qa":
        run_path = Path(record["path"])
        metadata = json.loads((run_path / "run.json").read_text(encoding="utf-8"))
        artifact = next(name for name in metadata["files"] if name.endswith(".json"))
        path = run_path / artifact
        path.write_bytes(path.read_bytes() + b"changed")
    elif failure == "bad_port":
        extra = ["--port", "65536"]
    protected = _files(workspace)
    assert main(["collections", "review", entry["id"], "--run", record["id"], *extra]) == 2
    assert "failed" in capsys.readouterr().out.lower()
    assert _files(workspace) == protected


def test_record_ids_cannot_be_replaced_with_filenames_or_changed_metadata(registered, capsys):
    _, workspace, _, entry = registered
    record = _run_records(entry, capsys, "--stage", "qa")[0]
    assert (
        main(["runs", "--collection", entry["id"], "--run", Path(record["path"]).name, "--json"])
        == 2
    )
    assert _json(capsys)["status"] == "failed"
    path = Path(record["path"]) / "run.json"
    path.write_bytes(path.read_bytes() + b"\n")
    protected = _files(workspace)
    assert main(["runs", "--collection", entry["id"], "--run", record["id"], "--json"]) == 2
    assert _json(capsys)["status"] == "failed"
    assert _files(workspace) == protected


@pytest.mark.parametrize("stage", ["qa", "export", "groups", "tagging", "recaption", "similarity"])
def test_generated_stage_commands_parse_with_exact_literal_paths(tmp_path, stage):
    record = {
        "path": str(tmp_path / "artist's run with spaces"),
        "stage": stage,
        "config_path": str(tmp_path / "config with spaces.toml"),
        "id": "a" * 64,
        "run_sha256": "b" * 64,
    }
    commands = _commands({"id": "c" * 64}, record)
    parsed = build_parser().parse_args(commands["args"][1:])
    assert parsed.run == (record["id"] if stage == "qa" else Path(record["path"]))
    if stage == "qa":
        assert parsed.expected_sha256 == record["run_sha256"]
    else:
        assert "artist''s run with spaces" in commands["powershell"]


@pytest.mark.parametrize("change", ["none", "source", "reviews"])
def test_standalone_qa_requires_collection_source_and_registered_write_roots(
    registered, monkeypatch, capsys, change
):
    import image_dataset_train.review_ui as reviewer

    config, workspace, result, entry = registered
    changed = config if change == "none" else replace(config, **{change: workspace / "foreign"})
    config_path = workspace / "standalone.toml"
    _write_config(config_path, changed)
    qa, _ = create_qa(config, Path(result["outputs"]["export"]["path"]), config_path=config_path)
    record = next(r for r in _run_records(entry, capsys, "--stage", "qa") if r["path"] == str(qa))
    assert record["config_sha256"] is None
    calls = []
    monkeypatch.setattr(reviewer, "serve_reviews", lambda *args, **kwargs: calls.append(args))
    protected = _files(workspace)
    code = main(["collections", "review", entry["id"], "--run", record["id"], "--no-open"])
    output = capsys.readouterr().out
    assert code == (0 if change == "none" else 2)
    assert len(calls) == (1 if change == "none" else 0)
    if change != "none":
        assert "configuration" in output and ("source" in output or "root" in output)
    assert _files(workspace) == protected


def test_review_rechecks_config_after_qa_verification_before_server(
    registered, monkeypatch, capsys
):
    import image_dataset_train.qa as qa_module
    import image_dataset_train.review_ui as reviewer

    _, _, _, entry = registered
    record = _run_records(entry, capsys, "--stage", "qa")[0]
    original = qa_module.read_qa

    def changed_after_read(path):
        result = original(path)
        config = Path(record["config_path"])
        config.write_bytes(config.read_bytes() + b"\n")
        return result

    def forbidden(*args, **kwargs):
        raise AssertionError("A changed configuration must not start the server")

    monkeypatch.setattr(qa_module, "read_qa", changed_after_read)
    monkeypatch.setattr(reviewer, "serve_reviews", forbidden)
    assert main(["collections", "review", entry["id"], "--run", record["id"]]) == 2
    assert "hash mismatch" in capsys.readouterr().out


def test_compact_show_preserves_failed_job_and_historical_context(registered, monkeypatch, capsys):
    from image_dataset_train import preparation

    config, workspace, _, entry = registered
    execute = preparation._execute

    def fail(stage, *args):
        if stage == "qa":
            raise OSError("fixture late QA failure")
        return execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", fail)
    with pytest.raises(OSError, match="fixture late QA failure"):
        run(config, workspace, new=True)
    protected = _files(workspace)
    assert main(["collections", "show", entry["id"]]) == 0
    output = capsys.readouterr().out
    assert "current:" in output and "recorded failed" in output
    assert "historical:" in output and "recorded completed" in output
    assert "fixture late QA failure" in output
    assert "Record ID:" not in output
    assert "Current-job retained artifacts:" in output
    assert _files(workspace) == protected
