import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image
from test_exports import reviewed as reviewed

from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import export_dataset
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reviews import publish_groups, review_image, review_link
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar
from image_dataset_train.snapshot_comparison import (
    compare_snapshots,
    publish_comparison,
    read_comparison,
)
from image_dataset_train.tagging import recaption


def _meta(path):
    return json.loads((path / "run.json").read_text(encoding="utf-8"))


def _rows(path, name="groups.jsonl"):
    return [json.loads(line) for line in (path / name).read_text(encoding="utf-8").splitlines()]


def _bytes(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def _rewrite_jsonl(path, name, rows):
    (path / name).write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    metadata = _meta(path)
    metadata["files"][name] = file_sha256(path / name)
    atomic_json(path / "run.json", metadata)


def _similarity(groups):
    return Path(_meta(groups)["similarity_run"])


def test_same_and_reordered_group_snapshots_have_no_semantic_changes(reviewed, tmp_path):
    config, groups, _ = reviewed
    protected = {path: _bytes(path) for path in (groups, config.source, config.reviews)}
    same = compare_snapshots(groups, groups)
    assert not same["changed"] and all(not values for values in same["changes"].values())
    assert same["summary"]["before_occurrences"] == 5
    assert same["summary"]["before_unique_contents"] == 4
    assert same["summary"]["common_occurrences"] == 5
    assert same["availability"] == {
        "effective_captions": False,
        "exported_splits": False,
        "source_revalidated": False,
    }

    reordered = tmp_path / "reordered"
    shutil.copytree(groups, reordered)
    rows = _rows(reordered)[::-1]
    for row in rows:
        row["members"].reverse()
    _rewrite_jsonl(reordered, "groups.jsonl", rows)
    result = compare_snapshots(groups, reordered)
    assert result == compare_snapshots(groups, reordered)
    assert not result["changed"]
    assert result["inputs"]["before"]["run_sha256"] == file_sha256(groups / "run.json")
    assert all(_bytes(path) == before for path, before in protected.items())


def test_group_changes_are_occurrence_scoped_and_do_not_invent_effective_captions(reviewed):
    config, before, _ = reviewed
    similarity = _similarity(before)
    review_image(
        config, similarity, "alias.png", caption="assistant corrected alias", reason="fixture audit"
    )
    review_image(
        config,
        similarity,
        "b.png",
        add_labels=["corrected"],
        subset="reviewed-portraits",
        reason="fixture annotation correction",
    )
    review_image(config, similarity, "c.png", decision="exclude", reason="fixture exclusion")
    after, _ = publish_groups(config, similarity)
    result = compare_snapshots(before, after)
    changes = result["changes"]
    assert result["changed"] and not changes["added"] and not changes["removed"]
    assert [row["source_path"] for row in changes["caption_changes"]] == ["alias.png"]
    caption = changes["caption_changes"][0]
    assert caption["before"] == {"text": None, "origin": None}
    assert caption["after"]["text"] == "assistant corrected alias"
    assert caption["after"]["origin"]["kind"] == "saved_override"
    assert [row["source_path"] for row in changes["annotation_changes"]] == ["b.png"]
    assert changes["annotation_changes"][0]["after"]["subset"] == "reviewed-portraits"
    decisions = {row["source_path"]: row for row in changes["decision_changes"]}
    assert decisions["c.png"]["before"]["value"] == "include"
    assert decisions["c.png"]["after"]["value"] == "exclude"
    assert not changes["group_changes"] and not changes["split_moves"]
    assert not changes["alias_changes"]


def test_real_group_merges_and_splits_use_retained_occurrence_membership(reviewed):
    config, before, _ = reviewed
    similarity = _similarity(before)
    for path in ("a.png", "alias.png", "b.png"):
        review_link(config, similarity, [path, "c.png"], "unreviewed", "fixture reopen family")
    for path in ("a.png", "alias.png", "b.png"):
        review_link(config, similarity, [path, "c.png"], "related", "fixture related family")
    merged, summary = publish_groups(config, similarity)
    assert not summary["conflicts"]
    result = compare_snapshots(before, merged)
    assert result["summary"]["group_merges"] == 1
    assert result["summary"]["group_splits"] == 0
    merge = result["changes"]["group_merges"][0]
    assert len(merge["before_group_ids"]) == 2
    assert {row["source_path"] for row in merge["occurrences"]} == {
        "a.png",
        "alias.png",
        "b.png",
        "c.png",
    }
    assert result["summary"]["group_changes"] == 4
    for path in ("a.png", "alias.png", "b.png"):
        review_link(config, similarity, [path, "c.png"], "unreviewed", "fixture reopen family")
    for path in ("a.png", "alias.png", "b.png"):
        review_link(config, similarity, [path, "c.png"], "distinct", "fixture distinct families")
    split, _ = publish_groups(config, similarity)
    reverse = compare_snapshots(merged, split)
    assert reverse["summary"]["group_splits"] == 1
    assert reverse["summary"]["group_merges"] == 0
    assert len(reverse["changes"]["group_splits"][0]["after_group_ids"]) == 2


def test_scan_changes_preserve_path_and_content_identity_and_alias_deltas(reviewed):
    config, before, _ = reviewed
    original = {m["source_path"]: m["sha256"] for g in _rows(before) for m in g["members"]}
    Image.new("RGB", (128, 192), "red").save(config.source / "a.png")
    (config.source / "c.png").unlink()
    Image.new("RGB", (128, 192), "blue").save(config.source / "new.png")
    (config.source / "new-alias.png").write_bytes((config.source / "b.png").read_bytes())
    inventory, _ = run_scan(config)
    similarity, _ = propose_similar(config, inventory, max_distance=64)
    after, _ = publish_groups(config, similarity)
    result = compare_snapshots(before, after)
    assert result["summary"]["before_occurrences"] == 5
    assert result["summary"]["after_occurrences"] == 6
    changed = result["changes"]["changed_content"]
    assert changed == [
        {
            "source_path": "a.png",
            "before_sha256": original["a.png"],
            "after_sha256": file_sha256(config.source / "a.png"),
        }
    ]
    # A replaced source path is both a removed and added exact occurrence.
    assert {r["source_path"] for r in result["changes"]["added"]} == {
        "a.png",
        "new.png",
        "new-alias.png",
    }
    assert {r["source_path"] for r in result["changes"]["removed"]} == {"a.png", "c.png"}
    aliases = {r["sha256"]: r for r in result["changes"]["alias_changes"]}
    assert aliases[original["a.png"]]["before"] == ["a.png", "alias.png"]
    assert aliases[original["a.png"]]["after"] == ["alias.png"]
    assert aliases[original["b.png"]]["after"] == ["b.png", "new-alias.png"]
    assert all(r["source_path"] != "a.png" for r in result["changes"]["caption_changes"])


def test_exports_compare_effective_alias_captions_and_actual_split_moves_offline(reviewed):
    config, groups, drafts = reviewed
    all_train = replace(config, export=replace(config.export, validation_ratio=0))
    before, _ = export_dataset(all_train, groups, captions_run=drafts)
    review_image(
        config,
        _similarity(groups),
        "alias.png",
        caption="new alias caption",
        reason="fixture audit",
    )
    changed_groups, _ = publish_groups(config, _similarity(groups))
    after, _ = export_dataset(config, changed_groups, captions_run=drafts)
    protected = {path: _bytes(path) for path in (before, after)}
    config.source.rename(config.source.with_name("source-offline"))
    result = compare_snapshots(before, after)
    assert result["kind"] == "export"
    assert result["availability"] == {
        "effective_captions": True,
        "exported_splits": True,
        "source_revalidated": False,
    }
    changes = result["changes"]
    assert [r["source_path"] for r in changes["caption_changes"]] == ["alias.png"]
    caption = changes["caption_changes"][0]
    assert caption["before"]["text"] == "alias caption"
    assert caption["before"]["origin"]["kind"] == "sidecar"
    assert caption["after"]["text"] == "new alias caption"
    assert caption["after"]["origin"]["kind"] == "override"
    assert [r["source_path"] for r in changes["split_moves"]] == ["c.png"]
    assert changes["split_moves"][0]["before"] == "train"
    assert changes["split_moves"][0]["after"] == "validation"
    assert not changes["media_changes"]
    assert all(_bytes(path) == snapshot for path, snapshot in protected.items())


def test_group_compare_and_published_receipt_survive_originals_going_offline(reviewed, tmp_path):
    config, before, _ = reviewed
    after, _ = publish_groups(config, _similarity(before))
    config.source.rename(config.source.with_name("source-offline"))
    expected = compare_snapshots(before, after)
    report, result = publish_comparison(before, after, output_root=tmp_path / "comparisons")
    assert result == expected and not result["changed"]
    metadata = _meta(report)
    assert metadata["stage"] == "snapshot_comparison" and metadata["status"] == "completed"
    assert set(metadata["files"]) == {
        "comparison.json",
        "before-snapshot.json",
        "after-snapshot.json",
        "before-run.json",
        "after-run.json",
    }
    assert all(file_sha256(report / name) == digest for name, digest in metadata["files"].items())
    assert (report / "before-run.json").read_bytes() == (before / "run.json").read_bytes()
    assert (report / "after-run.json").read_bytes() == (after / "run.json").read_bytes()
    before.rename(before.with_name("before-offline"))
    after.rename(after.with_name("after-offline"))
    assert read_comparison(report) == expected
    (report / "before-snapshot.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_comparison(report)


def test_unchanged_effective_caption_with_new_draft_rules_is_only_a_provenance_change(reviewed):
    config, groups, drafts = reviewed
    before, _ = export_dataset(config, groups, captions_run=drafts)
    # The retained score is 0.9, so this new rule changes provenance but not selected text.
    revised_config = replace(config, captions=replace(config.captions, general_threshold=0.4))
    revised_drafts, _ = recaption(revised_config, drafts)
    assert revised_drafts != drafts
    after, _ = export_dataset(revised_config, groups, captions_run=revised_drafts)
    result = compare_snapshots(before, after)
    assert result["changed"]
    assert result["summary"]["caption_changes"] == 0
    assert result["changes"]["caption_changes"] == []
    provenance = result["changes"]["caption_provenance_changes"]
    assert [row["source_path"] for row in provenance] == ["c.png"]
    assert result["summary"]["caption_provenance_changes"] == 1
    assert provenance[0]["before"]["origin"]["kind"] == "draft"
    assert provenance[0]["after"]["origin"]["kind"] == "draft"
    assert (
        provenance[0]["before"]["origin"]["rules_sha256"]
        != provenance[0]["after"]["origin"]["rules_sha256"]
    )
    before_rows = {row["source_path"]: row for row in _rows(before, "manifest.jsonl")}
    after_rows = {row["source_path"]: row for row in _rows(after, "manifest.jsonl")}
    assert before_rows["c.png"]["caption"] == after_rows["c.png"]["caption"] == "blue hair"
    assert not result["changes"]["split_moves"] and not result["changes"]["media_changes"]


@pytest.mark.parametrize("artifact", ["groups.jsonl", "reviews.json", "summary.json"])
def test_group_tampering_is_rejected_before_output_creation(reviewed, tmp_path, artifact):
    _, groups, _ = reviewed
    (groups / artifact).write_bytes((groups / artifact).read_bytes() + b"\n")
    protected = _bytes(groups)
    output = tmp_path / "comparison-output"
    with pytest.raises(ValueError, match="hash mismatch"):
        publish_comparison(groups, groups, output_root=output)
    assert not output.exists() and _bytes(groups) == protected


@pytest.mark.parametrize("artifact", ["image", "caption", "manifest"])
def test_export_tampering_is_rejected_before_output_creation(reviewed, tmp_path, artifact):
    config, groups, drafts = reviewed
    output, _ = export_dataset(config, groups, captions_run=drafts)
    row = _rows(output, "manifest.jsonl")[0]
    target = output / ("manifest.jsonl" if artifact == "manifest" else row[f"{artifact}_path"])
    target.write_bytes(target.read_bytes() + b"modified")
    protected = _bytes(output)
    comparisons = tmp_path / "comparisons"
    with pytest.raises(ValueError, match="hash mismatch"):
        publish_comparison(output, output, output_root=comparisons)
    assert not comparisons.exists() and _bytes(output) == protected


@pytest.mark.parametrize(
    "location", ["input", "inside_input", "source", "inside_source", "source_parent"]
)
def test_publication_rejects_protected_output_trees_without_mutation(reviewed, location):
    config, groups, _ = reviewed
    root = {
        "input": groups,
        "inside_input": groups / "comparisons",
        "source": config.source,
        "inside_source": config.source / "comparisons",
        "source_parent": config.source.parent,
    }[location]
    protected = _bytes(config.source.parent)
    with pytest.raises(ValueError, match="separate|inside"):
        publish_comparison(groups, groups, output_root=root)
    assert _bytes(config.source.parent) == protected


def test_mixed_kinds_and_different_source_identities_are_rejected(reviewed, tmp_path):
    config, groups, drafts = reviewed
    export, _ = export_dataset(config, groups, captions_run=drafts)
    with pytest.raises(ValueError, match="same kind"):
        compare_snapshots(groups, export)
    other = tmp_path / "other-source-groups"
    shutil.copytree(groups, other)
    metadata = _meta(other)
    metadata["source"] = str(tmp_path / "different-source")
    atomic_json(other / "run.json", metadata)
    with pytest.raises(ValueError, match="source identities"):
        compare_snapshots(groups, other)
