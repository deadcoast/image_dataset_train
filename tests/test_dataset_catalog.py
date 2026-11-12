import argparse
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from test_exports import reviewed as reviewed

from image_dataset_train.dataset_catalog import (
    build_catalog,
    query_catalog,
    read_catalog,
    verify_catalog_payload,
    write_catalog,
)
from image_dataset_train.dataset_catalog_cli import register_commands, run_command
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import export_dataset, verify_export
from image_dataset_train.inventory import file_sha256


@pytest.fixture
def exported(reviewed):
    config, groups, drafts = reviewed
    export, _ = export_dataset(config, groups, captions_run=drafts)
    rows = [json.loads(line) for line in (export / "manifest.jsonl").read_text().splitlines()]
    return config, export, sorted(rows, key=lambda row: row["id"])


def hashes(root):
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def rehash(export, name):
    metadata = json.loads((export / "run.json").read_text())
    metadata["files"][name] = file_sha256(export / name)
    atomic_json(export / "run.json", metadata)


def test_embedded_catalog_is_portable_and_queries_only_explicit_annotations(exported, tmp_path):
    config, export, rows = exported
    before = hashes(export)
    moved = tmp_path / "moved dataset"
    export.rename(moved)
    config.source.rename(tmp_path / "unavailable source")
    config.runs.rename(tmp_path / "unavailable runs")
    summary = read_catalog(moved)
    assert summary["images"] == 4 and summary["groups"] == 2
    assert summary["media_packaged"] is True
    assert summary["media_reverified"] is False
    assert summary["verification_scope"] == "catalog_and_metadata"
    assert summary["annotation_labels"] == {"portrait": 3, "scenery": 1}
    assert summary["decision_origins"] == {"unspecified": 4}
    assert summary["model_observations"] == 1
    assert query_catalog(moved) == rows
    assert {row["source_path"] for row in query_catalog(moved, label="PORTRAIT")} == {
        "a.png",
        "alias.png",
        "b.png",
    }
    assert query_catalog(moved, label="blue_hair") == []
    assert [row["source_path"] for row in query_catalog(moved, text="BLUE HAIR")] == ["c.png"]
    assert query_catalog(moved, text="' OR 1=1 --") == []
    assert len(query_catalog(moved, split="validation")) == 1
    assert query_catalog(moved, group_id=rows[0]["group_id"]) == [
        row for row in rows if row["group_id"] == rows[0]["group_id"]
    ]
    assert query_catalog(moved, limit=1, offset=1) == rows[1:2]
    for split in ("train", "validation"):
        metadata = [
            json.loads(line) for line in (moved / split / "metadata.jsonl").read_text().splitlines()
        ]
        selected = {row["id"]: row for row in rows if row["split"] == split}
        for record in metadata:
            row = selected[record["id"]]
            image = moved / split / record["file_name"]
            assert image.is_file() and file_sha256(image) == record["image_sha256"]
            assert record["text"] == row["caption"]
            assert record["source_sha256"] == row["sha256"]
            assert (record["width"], record["height"]) == (row["width"], row["height"])
            assert json.loads(record["model_observations_json"]) == row["caption_analysis"]
    assert verify_export(moved)["verified"]
    assert hashes(moved) == before  # Reading/querying creates no SQLite journal or altered files.


def test_writer_preserves_policy_attribution_without_creating_reviewed_tags(exported, tmp_path):
    _, _, rows = exported
    row = dict(next(row for row in rows if row["source_path"] == "c.png"))
    row["decision_origin"] = {"kind": "policy", "policy": "conservative-v1", "reason": "decodable"}
    row["preparation_flags"] = ["unreviewed_caption"]
    row["source_caption"] = row["caption"] + ", transparent background"
    row["caption_transforms"] = [
        {
            "policy": "opaque-alpha-caption-v1",
            "reason": "training derivative is opaque RGB",
            "removed_phrases": ["transparent background"],
        }
    ]
    stage = tmp_path / ".pending-test-catalog"
    descriptor = write_catalog(stage, [row])
    summary = verify_catalog_payload(stage, descriptor, [row])
    assert summary["decision_origins"] == {"policy": 1}
    metadata = json.loads((stage / descriptor["metadata"][row["split"]]).read_text())
    assert json.loads(metadata["decision_origin_json"]) == row["decision_origin"]
    assert json.loads(metadata["preparation_json"]) == {"preparation_flags": ["unreviewed_caption"]}
    assert metadata["source_caption"] == row["source_caption"]
    assert json.loads(metadata["caption_transforms_json"]) == row["caption_transforms"]
    assert json.loads(metadata["review_annotations_json"])["labels"] == ["scenery"]
    assert (
        json.loads(metadata["model_observations_json"])["observed_tags"][0]["name"] == "blue_hair"
    )
    with sqlite3.connect(stage / "catalog.sqlite") as connection:
        assert json.loads(connection.execute("SELECT record_json FROM images").fetchone()[0]) == row
    with pytest.raises(ValueError, match="already exists"):
        write_catalog(stage, [row])


@pytest.mark.parametrize(
    "target",
    ["catalog.sqlite", "train/metadata.jsonl", "manifest.jsonl", "provenance/reviews.json"],
)
def test_catalog_read_rejects_tampered_metadata_and_provenance(exported, target):
    _, export, _ = exported
    with (export / target).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        query_catalog(export)


@pytest.mark.parametrize("target", ["catalog.sqlite", "train/metadata.jsonl", "manifest.jsonl"])
def test_catalog_reconciles_derived_fields_even_if_file_checksum_is_updated(exported, target):
    _, export, _ = exported
    if target == "catalog.sqlite":
        with sqlite3.connect(export / target) as connection:
            connection.execute("UPDATE images SET text = 'invented caption'")
    else:
        records = [json.loads(line) for line in (export / target).read_text().splitlines()]
        records[0]["text" if target.endswith("metadata.jsonl") else "caption"] = "invented caption"
        (export / target).write_text("".join(json.dumps(row) + "\n" for row in records))
    rehash(export, target)
    with pytest.raises(ValueError, match="differs from export manifest"):
        read_catalog(export)


def test_catalog_annotation_index_cannot_promote_a_model_prediction(exported):
    _, export, _ = exported
    with sqlite3.connect(export / "catalog.sqlite") as connection:
        image_id = connection.execute(
            "SELECT id FROM images WHERE source_path = 'c.png'"
        ).fetchone()[0]
        connection.execute("INSERT INTO annotations VALUES (?, ?)", (image_id, "blue_hair"))
    rehash(export, "catalog.sqlite")
    with pytest.raises(ValueError, match="explicit review annotations"):
        query_catalog(export, label="blue_hair")


def test_historical_export_rebuild_freezes_metadata_without_media_or_mutating_inputs(
    exported, tmp_path
):
    config, export, rows = exported
    # Reproduce the existing schema-1 export contract from before catalogs were added.
    legacy = tmp_path / "historical export"
    shutil.copytree(export, legacy)
    meta = json.loads((legacy / "run.json").read_text())
    descriptor = meta.pop("catalog")
    for name in (descriptor["database"], *descriptor["metadata"].values()):
        (legacy / name).unlink()
        del meta["files"][name]
    atomic_json(legacy / "run.json", meta)
    assert verify_export(legacy)["verified"]
    with pytest.raises(ValueError, match="no catalog"):
        read_catalog(legacy)
    before = hashes(legacy)
    catalog, summary = build_catalog(legacy, output_root=tmp_path / "indexes")
    assert hashes(legacy) == before
    assert summary["media_packaged"] is False
    assert (catalog / "export-run.json").read_bytes() == (legacy / "run.json").read_bytes()
    for name in meta["files"]:
        if name.startswith("provenance/"):
            assert (catalog / name).read_bytes() == (legacy / name).read_bytes()
    assert not list(catalog.rglob("*.png"))
    legacy.rename(tmp_path / "offline export")
    config.source.rename(tmp_path / "offline source")
    config.runs.rename(tmp_path / "offline runs")
    assert read_catalog(catalog)["images"] == 4
    assert query_catalog(catalog) == rows
    (catalog / "extra.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="untracked"):
        read_catalog(catalog)


@pytest.mark.parametrize("destination", ["source", "export", "export-child", "source-ancestor"])
def test_rebuild_refuses_protected_output_overlap(exported, tmp_path, destination):
    config, export, _ = exported
    output = {
        "source": config.source,
        "export": export,
        "export-child": export / "catalogs",
        "source-ancestor": tmp_path,
    }[destination]
    original = hashes(export)
    with pytest.raises(ValueError, match="separate"):
        build_catalog(export, output_root=output)
    assert hashes(export) == original


def test_writer_refuses_a_published_export(exported):
    _, export, rows = exported
    original = hashes(export)
    with pytest.raises(ValueError, match="unpublished staging"):
        write_catalog(export, rows)
    assert hashes(export) == original


@pytest.mark.parametrize(
    "filters",
    [
        {"limit": 0},
        {"limit": 1001},
        {"offset": -1},
        {"limit": True},
        {"split": "test"},
        {"text": "\0"},
    ],
)
def test_query_rejects_unbounded_or_invalid_filters(exported, filters):
    _, export, _ = exported
    with pytest.raises(ValueError):
        query_catalog(export, **filters)


def test_catalog_cli_is_config_independent(exported, tmp_path, monkeypatch, capsys):
    _, export, _ = exported
    outside = tmp_path / "outside project"
    outside.mkdir()
    monkeypatch.chdir(outside)
    parser = argparse.ArgumentParser()
    register_commands(parser.add_subparsers(dest="command", required=True))
    assert run_command(parser.parse_args(["catalog-info", "--run", str(export), "--json"])) == 0
    assert json.loads(capsys.readouterr().out)["images"] == 4
    assert (
        run_command(
            parser.parse_args(["catalog-query", "--run", str(export), "--text", "blue hair"])
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)[0]["source_path"] == "c.png"
    assert (
        run_command(
            parser.parse_args(
                [
                    "catalog-build",
                    "--run",
                    str(export),
                    "--output",
                    str(tmp_path / "catalogs"),
                    "--json",
                ]
            )
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["media_packaged"] is False
    assert Path(created["catalog"]).is_dir()


def test_catalog_query_rejects_linked_database(exported, tmp_path):
    _, export, _ = exported
    target = tmp_path / "catalog.sqlite"
    (export / "catalog.sqlite").rename(target)
    try:
        (export / "catalog.sqlite").symlink_to(target)
    except OSError:
        pytest.skip("Creating Windows symlinks requires host permission")
    with pytest.raises(ValueError, match="Linked"):
        query_catalog(export)
