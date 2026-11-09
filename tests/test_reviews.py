import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from image_dataset_train.cli import main
from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.reviews import (
    publish_groups,
    review_image,
    review_link,
    review_pair,
    review_status,
)
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


@pytest.fixture
def prepared(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for i, name in enumerate(("a", "b", "c")):
        image = Image.new("RGB", (32, 32), "white")
        ImageDraw.Draw(image).rectangle((i * 5, 2, i * 5 + 10, 20), fill="black")
        image.save(source / f"{name}.png")
    (source / "d.png").write_bytes((source / "a.png").read_bytes())
    (source / "a.txt").write_text("original manual caption")
    config = Config(source, tmp_path / "runs", ValidationConfig(), reviews=tmp_path / "reviews")
    inventory, _ = run_scan(config)
    run, _ = propose_similar(config, inventory, max_distance=64)
    pairs = {
        p["left_source_path"] + p["right_source_path"]: p["pair_id"]
        for p in review_status(config, run)["pairs"]
    }
    return config, run, pairs


def test_reviews_persist_form_groups_detect_conflicts_and_keep_captions(prepared):
    config, run, pairs = prepared
    before = {p.name: p.read_bytes() for p in config.source.iterdir()}
    assert not config.reviews.exists()
    for names in ("a.pngb.png", "b.pngc.png"):
        review_pair(config, run, pairs[names][:12], "related", "same artwork")
    with pytest.raises(ValueError, match="conflicts"):
        review_pair(config, run, pairs["a.pngc.png"], "distinct", "different")
    assert review_status(config, run)["revision"] == 2
    result = review_pair(config, run, pairs["a.pngc.png"], "related", "same artwork")
    assert review_pair(config, run, pairs["a.pngc.png"], "related", "same artwork") == result
    for name in ("a", "b", "c", "d"):
        review_image(config, run, f"{name}.png", decision="include", reason="reviewed")
    review_image(config, run, "a.png", caption="approved, caption", reason="corrected")
    result = review_image(config, run, "a.png", decision="exclude", reason="alternate")
    assert result["caption_override"] == "approved, caption"
    snapshot, summary = publish_groups(config, run)
    assert summary["review_complete"] and not summary["training_ready"]
    groups = [json.loads(line) for line in (snapshot / "groups.jsonl").read_text().splitlines()]
    assert len(groups) == 1 and len(groups[0]["members"]) == 4
    assert groups[0]["members"][0]["caption_override"] == "approved, caption"
    result = review_image(config, run, "a.png", clear_caption=True, reason="return to automatic")
    assert result["decision"] == "exclude" and result["caption_override"] is None
    assert before == {p.name: p.read_bytes() for p in config.source.iterdir()}
    inventory, _ = run_scan(config)
    repeated, _ = propose_similar(config, inventory, max_distance=64)
    assert review_status(config, repeated)["pair_counts"] == {"related": 3}


def test_changed_sources_cannot_inherit_approval_or_mutate_old_reviews(prepared):
    config, run, pairs = prepared
    result = review_image(
        config,
        run,
        "a.png",
        decision="include",
        reason="reviewed",
        add_labels=["portrait"],
        subset="solo",
    )
    saved = Path(result["review_file"]).read_bytes()
    (config.source / "a.png").write_bytes((config.source / "c.png").read_bytes())
    with pytest.raises(ValueError, match="changed"):
        review_pair(config, run, pairs["a.pngb.png"], "related", "same")
    with pytest.raises(ValueError, match="changed"):
        publish_groups(config, run)
    assert Path(result["review_file"]).read_bytes() == saved
    inventory, _ = run_scan(config)
    new_run, _ = propose_similar(config, inventory, max_distance=64)
    assert review_image(config, new_run, "a.png")["decision"] == "unreviewed"
    assert not review_image(config, new_run, "a.png")["labels_reviewed"]
    assert review_image(config, new_run, "a.png")["subset"] is None
    assert review_status(config, new_run)["stale_image_decisions"] == 1


def test_cli_review_and_group_snapshot_are_usable(prepared, tmp_path, capsys):
    config, run, _ = prepared
    settings = tmp_path / "config.toml"
    settings.write_text(
        f'schema_version=1\n[paths]\nreviews="{config.reviews.as_posix()}"\n'
        f'runs="{config.runs.as_posix()}"\n'
    )
    args = ["--run", str(run), "--config", str(settings)]
    assert main(["review", *args, "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["pairs"]) == 3
    assert main(["review", *args, "--images", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["images"]) == 4
    assert (
        main(
            [
                "review",
                *args,
                "--link",
                "b.png",
                "c.png",
                "--decision",
                "related",
                "--reason",
                "same artwork",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["decision"] == "related"
    assert (
        main(
            [
                "review",
                *args,
                "--image",
                "a.png",
                "--decision",
                "include",
                "--caption",
                "human caption",
                "--reason",
                "checked",
                "--label",
                "Portrait",
                "--subset",
                "Solo",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["caption_override"] == "human caption"
    assert main(["review", *args, "--unannotated", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["images"] == []
    assert main(["groups", *args]) == 1  # The unfinished review still has a useful snapshot.
    assert "Group snapshot:" in capsys.readouterr().out
    with pytest.raises(ValueError, match="separate trees"):
        review_status(replace(config, reviews=config.source / "reviews"), run)


def test_annotation_edits_preserve_captions_and_survive_new_snapshots(prepared):
    config, run, _ = prepared
    original = {p.name: p.read_bytes() for p in config.source.iterdir()}
    review_image(
        config,
        run,
        "a.png",
        decision="include",
        caption="manual caption",
        add_labels=[" Portrait ", "portrait", "BLUE hair"],
        subset="Solo",
        reason="inspected",
    )
    edited = review_image(
        config,
        run,
        "a.png",
        remove_labels=["blue hair"],
        add_labels=["outdoors"],
        reason="corrected",
    )
    assert edited["labels"] == ["outdoors", "portrait"] and edited["subset"] == "solo"
    assert edited["caption_override"] == "manual caption" and edited["decision"] == "include"
    assert (
        review_image(
            config,
            run,
            "a.png",
            add_labels=["OUTDOORS"],
            remove_labels=["blue hair"],
            reason="corrected",
        )["revision"]
        == edited["revision"]
    )
    inventory, _ = run_scan(config)
    repeated, _ = propose_similar(config, inventory)
    snapshot, _ = publish_groups(config, repeated)
    members = [
        m
        for line in (snapshot / "groups.jsonl").read_text().splitlines()
        for m in json.loads(line)["members"]
    ]
    saved = next(m for m in members if m["source_path"] == "a.png")
    assert saved["labels"] == ["outdoors", "portrait"] and saved["subset"] == "solo"
    cleared = review_image(
        config,
        repeated,
        "a.png",
        clear_labels=True,
        clear_subset=True,
        reason="reviewed with no categories",
    )
    assert cleared["labels"] == [] and cleared["subset"] is None
    assert cleared["labels_reviewed"] and cleared["subset_reviewed"]
    assert saved["labels"] == ["outdoors", "portrait"]  # Published snapshot remains unchanged.
    assert original == {p.name: p.read_bytes() for p in config.source.iterdir()}


def test_manual_pairs_are_navigable_and_count_toward_completion(prepared):
    config, run, _ = prepared
    linked = review_link(config, run, ["a.png", "d.png"], "related", "Exact alias reviewed")
    listing = review_status(config, run, show_all=True, limit=1, offset=3)
    assert listing["pair_total"] == 4 and listing["pair_next_offset"] is None
    assert listing["pairs"][0]["pair_id"] == linked["pair_id"]
    assert review_status(config, run, pair_decision="related")["pair_total"] == 1
    reset = review_pair(config, run, linked["pair_id"], "unreviewed", "Revisit alias")
    _, summary = publish_groups(config, run, expected_revision=reset["revision"])
    assert summary["unresolved_pairs"] == 4
    with pytest.raises(ValueError, match="changed"):
        publish_groups(config, run, expected_revision=linked["revision"])
