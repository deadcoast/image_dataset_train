"""Read-only caption previews preserve exact evidence, precedence, and review identity."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from image_dataset_train import caption_comparison as comparison
from image_dataset_train.caption_comparison import inspect_caption_comparison
from image_dataset_train.config import CaptionConfig, Config, ValidationConfig
from image_dataset_train.exporting import _caption, export_dataset
from image_dataset_train.model_bundle import Label
from image_dataset_train.qa import create_qa
from image_dataset_train.reviews import ReviewConflict, ReviewStore, publish_groups, review_image
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar
from image_dataset_train.tagging import _publish


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def build(
    tmp_path,
    *,
    sidecar=b"\xef\xbb\xbfsidecar, caf\xc3\xa9\nsecond line",
    override="saved, portrait, portrait",
    draft=True,
    export=False,
):
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (128, 192), "blue").save(source / "a.png")
    (source / "alias.png").write_bytes((source / "a.png").read_bytes())
    if sidecar is not None:
        (source / "a.txt").write_bytes(sidecar)
    (source / "alias.txt").write_text("alias-specific caption", encoding="utf-8")
    config = Config(
        source,
        tmp_path / "runs",
        ValidationConfig(),
        reviews=tmp_path / "reviews",
        exports=tmp_path / "exports",
    )
    inventory, _ = run_scan(config)
    run, _ = propose_similar(config, inventory)
    for name in ("a.png", "alias.png"):
        review_image(
            config,
            run,
            name,
            decision="include",
            caption=override if name == "a.png" else None,
            reason="fixture saved review",
        )
    groups, _ = publish_groups(config, run)
    meta = read(groups / "run.json")
    members = [
        m
        for line in (groups / "groups.jsonl").read_text().splitlines()
        for m in json.loads(line)["members"]
    ]
    drafts = None
    if draft:
        drafts = _publish(
            config.runs,
            [
                {"source_path": m["source_path"], "sha256": m["sha256"], "decision": "tagged"}
                for m in members
            ],
            {m["sha256"]: np.array([0.9], dtype=np.float32) for m in members},
            [Label(0, "blue_hair", 0)],
            {
                "stage": "recaption",
                "source": str(source),
                "inventory_manifest_sha256": meta["inventory_manifest_sha256"],
            },
            {},
            CaptionConfig(),
            0.35,
        )
    selected = export_dataset(config, groups, captions_run=drafts)[0] if export else groups
    report, _ = create_qa(config, selected, captions_run=None if export else drafts)
    entries = {
        row["source_path"]: row
        for row in (
            json.loads(line) for line in (report / "entries.jsonl").read_text().splitlines()
        )
    }
    return {
        "config": config,
        "run": run,
        "groups": groups,
        "drafts": drafts,
        "input": selected,
        "report": report,
        "entries": entries,
        "members": {m["source_path"]: m for m in members},
    }


@pytest.fixture
def prepared(tmp_path):
    return build(tmp_path)


def inspect(fixture, *, image="a.png", **options):
    return inspect_caption_comparison(
        fixture["config"],
        fixture["run"],
        fixture["report"],
        fixture["entries"][image]["id"],
        **options,
    )


def rehash_export_report(fixture):
    root = fixture["input"]
    meta = read(root / "run.json")
    for name in meta["files"]:
        if (root / name).is_file():
            meta["files"][name] = digest(root / name)
    save(root / "run.json", meta)
    qa = read(fixture["report"] / "run.json")
    qa["input_run_sha256"] = digest(root / "run.json")
    save(fixture["report"] / "run.json", qa)


def test_all_candidates_preserve_precedence_and_exact_full_text(prepared):
    result = inspect(prepared, action="clear")
    assert {name: value["status"] for name, value in result["candidates"].items()} == dict.fromkeys(
        ("override", "sidecar", "draft"), "present"
    )
    assert result["candidates"]["sidecar"]["text"] == "sidecar, café\nsecond line"
    assert result["candidates"]["sidecar"]["normalized_text"] == "sidecar, café second line"
    assert result["candidates"]["draft"]["text"] == "blue hair"
    assert result["effective"]["keep"]["text"] == "saved, portrait, portrait"
    assert result["effective"]["clear"]["text"] == "sidecar, café second line"
    assert result["effective"]["proposed"] == result["effective"]["clear"]
    assert result["snapshot"]["caption"] == "saved, portrait, portrait"
    assert result["current_revision"] == result["snapshot_revision"] == 2
    assert result["candidates"]["sidecar"]["provenance"]["source_checked"]
    assert result["candidates"]["draft"]["provenance"]["metadata_binding"] == "checked_current"
    assert result["report_sha256"] == digest(prepared["report"] / "run.json")
    assert len(result["comparison_sha256"]) == 64 and result["current_store_sha256"]
    assert not result["source_revalidated"] and not result["derivative_preview"]
    assert result["literal_changes_total"] == 5
    assert (
        sum(
            row["text"] == "portrait" and row["operation"] == "removed"
            for row in result["literal_changes"]
        )
        == 2
    )


@pytest.mark.parametrize(
    "action,caption",
    [("keep", None), ("clear", None), ("replace", "  replacement\n  café, portrait  ")],
)
def test_effective_text_agrees_with_authoritative_resolver(prepared, action, caption):
    result = inspect(prepared, action=action, caption=caption)
    member = dict(prepared["members"]["a.png"])
    if action == "clear":
        member.update(caption_override=None, caption_rule_version=None)
    elif action == "replace":
        member.update(caption_override=caption.strip(), caption_rule_version="manual-v1")
    expected, origin = _caption(member, (prepared["config"].source / "a.txt").read_bytes(), {})
    assert result["effective"]["proposed"]["text"] == expected
    assert result["effective"]["proposed"]["provenance"]["kind"] == origin["kind"]


def test_alias_candidates_remain_occurrence_specific(prepared):
    original, alias = inspect(prepared), inspect(prepared, image="alias.png")
    assert original["identity"]["sha256"] == alias["identity"]["sha256"]
    assert alias["effective"]["keep"]["text"] == "alias-specific caption"
    assert alias["candidates"]["override"]["status"] == "absent"
    assert alias["image_id"] != original["image_id"]


@pytest.mark.parametrize("sidecar", [b"", b" \n\t", b"invalid\xff", b"hello\0world"])
def test_invalid_sidecar_blocks_fallback_but_valid_override_still_wins(tmp_path, sidecar):
    fixture = build(tmp_path, sidecar=sidecar)
    result = inspect(fixture, action="clear")
    assert result["candidates"]["sidecar"]["status"] == "invalid"
    assert result["candidates"]["draft"]["status"] == "present"
    assert result["effective"]["keep"]["status"] == "present"
    assert result["effective"]["clear"]["status"] == "invalid"
    assert result["effective"]["clear"]["text"] is None
    assert result["evidence_warnings"][0]["candidate"] == "sidecar"


@pytest.mark.parametrize(
    "sidecar,draft,expected",
    [(None, True, "blue hair"), (b"source text", False, "source text"), (None, False, None)],
)
def test_absent_candidates_fall_through_only_when_proven_absent(tmp_path, sidecar, draft, expected):
    fixture = build(tmp_path, sidecar=sidecar, override=None, draft=draft)
    result = inspect(fixture)
    assert result["candidates"]["override"]["status"] == "absent"
    assert result["effective"]["keep"]["text"] == expected
    assert result["effective"]["keep"]["status"] == ("present" if expected else "absent")
    assert result["snapshot"]["status"] == ("present" if expected else "unavailable")


@pytest.mark.parametrize(
    "mode,status",
    [("missing", "unavailable"), ("changed", "invalid"), ("oversized", "unavailable")],
)
def test_recorded_sidecar_unavailability_never_becomes_draft_fallback(prepared, mode, status):
    path = prepared["config"].source / "a.txt"
    if mode == "missing":
        path.unlink()
    else:
        path.write_bytes(
            b"changed" if mode == "changed" else b"x" * (comparison.CANDIDATE_BYTES + 1)
        )
    result = inspect(prepared, action="clear")
    assert result["candidates"]["sidecar"]["status"] == status
    assert result["effective"]["keep"]["status"] == "present"
    assert result["effective"]["clear"]["status"] == status
    assert not result["candidates"]["sidecar"]["provenance"]["source_checked"]


def test_source_images_may_change_without_claiming_revalidation(prepared, monkeypatch):
    (prepared["config"].source / "a.png").write_bytes(b"different image")
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("image decode"))
    result = inspect(prepared)
    assert result["effective"]["keep"]["status"] == "present"
    assert not result["source_revalidated"]


@pytest.mark.parametrize("export", [False, True])
def test_offline_inspection_never_opens_images_or_writes(tmp_path, export, monkeypatch):
    fixture = build(tmp_path, export=export)
    fixture["config"].source.rename(tmp_path / "offline-source")
    if export:
        fixture["groups"].rename(fixture["groups"].with_name("offline-groups"))
        fixture["drafts"].rename(fixture["drafts"].with_name("offline-drafts"))
    before = tree(tmp_path)
    original = Path.open

    def guarded(path, mode="r", *args, **kwargs):
        assert not any(character in mode for character in "wax+")
        assert path.suffix.lower() not in {".png", ".jpg", ".webp"}
        if export:
            assert not any(
                path.is_relative_to(fixture["input"] / name) for name in ("train", "validation")
            )
        return original(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded)
        patch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("image decode"))
        result = inspect(fixture, action="clear")
    assert result["effective"]["clear"]["status"] == ("present" if export else "unavailable")
    assert result["candidates"]["sidecar"]["provenance"]["evidence"] == (
        "captured_export" if export else "source_sidecar"
    )
    assert tree(tmp_path) == before


@pytest.mark.parametrize("target", ["source", "inventory_manifest_sha256", "manifest_sha256"])
def test_mismatched_pinned_draft_metadata_is_invalid(prepared, target):
    meta = read(prepared["drafts"] / "run.json")
    meta[target] = str(prepared["drafts"] / "wrong") if target == "source" else "0" * 64
    save(prepared["drafts"] / "run.json", meta)
    result = inspect(prepared)
    assert result["candidates"]["draft"]["status"] == "invalid"
    assert result["effective"]["keep"]["status"] == "present"


def test_draft_manifest_is_pinned_and_loose_drafts_are_ignored(prepared):
    (prepared["drafts"] / "a.txt").write_text("unrelated loose text")
    assert inspect(prepared)["candidates"]["draft"]["text"] == "blue hair"
    with (prepared["drafts"] / "manifest.jsonl").open("ab") as stream:
        stream.write(b" ")
    assert inspect(prepared)["candidates"]["draft"]["status"] == "invalid"


def test_different_image_hash_in_pinned_manifest_is_not_the_selected_draft(prepared):
    path = prepared["drafts"] / "manifest.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    next(row for row in rows if row["source_path"] == "a.png")["sha256"] = "1" * 64
    path.write_text("\n".join(json.dumps(row) for row in rows))
    meta = read(prepared["drafts"] / "run.json")
    meta["manifest_sha256"] = digest(path)
    save(prepared["drafts"] / "run.json", meta)
    qa = read(prepared["report"] / "run.json")
    qa["caption_manifest_sha256"] = digest(path)
    save(prepared["report"] / "run.json", qa)
    assert inspect(prepared)["candidates"]["draft"]["status"] == "invalid"


@pytest.mark.parametrize("kind", ["sidecar", "draft"])
def test_legacy_export_missing_capture_is_unavailable_not_absent(tmp_path, kind):
    fixture = build(tmp_path, export=True)
    meta = read(fixture["input"] / "run.json")
    if kind == "sidecar":
        meta.pop("caption_source_version")
        sha = fixture["members"]["a.png"]["sidecar_sha256"]
        del meta["files"][f"provenance/sidecars/{sha}.txt"]
    else:
        meta.pop("caption_analysis_version")
        del meta["files"]["provenance/captions-manifest.jsonl"]
    save(fixture["input"] / "run.json", meta)
    rehash_export_report(fixture)
    result = inspect(fixture, action="clear")
    assert result["candidates"][kind]["status"] == "unavailable"
    if kind == "sidecar":
        assert result["effective"]["clear"]["status"] == "unavailable"


@pytest.mark.parametrize("kind", ["sidecar", "draft"])
def test_modern_export_missing_capture_declaration_is_invalid(tmp_path, kind):
    fixture = build(tmp_path, export=True)
    meta = read(fixture["input"] / "run.json")
    name = (
        f"provenance/sidecars/{fixture['members']['a.png']['sidecar_sha256']}.txt"
        if kind == "sidecar"
        else "provenance/captions-manifest.jsonl"
    )
    del meta["files"][name]
    save(fixture["input"] / "run.json", meta)
    rehash_export_report(fixture)
    assert inspect(fixture)["candidates"][kind]["status"] == "invalid"


def test_oversized_saved_override_is_unavailable_without_silent_truncation(prepared):
    review_image(
        prepared["config"],
        prepared["run"],
        "a.png",
        caption="a" * (comparison.CANDIDATE_BYTES + 1),
        reason="fixture",
    )
    result = inspect(prepared)
    assert result["candidates"]["override"]["status"] == "unavailable"
    assert result["candidates"]["override"]["text"] is None
    assert result["effective"]["keep"]["status"] == "unavailable"
    assert result["effective"]["clear"]["status"] == "present"


def test_metadata_bound_rejects_before_opening_oversized_file(tmp_path, monkeypatch):
    path = tmp_path / "metadata.json"
    path.write_bytes(b"0123456789")
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: pytest.fail("oversized read"))
    with pytest.raises(ValueError, match="byte inspection limit"):
        comparison._Reads().read(path, limit=5)


def test_linked_candidate_is_invalid_without_reading_target(prepared, monkeypatch):
    path = prepared["config"].source / "a.txt"
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda value: value == path or original(value))
    result = inspect(prepared, action="clear")
    assert result["candidates"]["sidecar"]["status"] == "invalid"
    assert result["effective"]["clear"]["status"] == "invalid"


@pytest.mark.parametrize("caption", ["", " \n", "not\0valid"])
def test_invalid_replacement_keeps_candidates_visible(prepared, caption):
    result = inspect(prepared, action="replace", caption=caption)
    assert result["effective"]["proposed"]["status"] == "invalid"
    assert result["effective"]["keep"]["status"] == "present"
    assert result["candidates"]["sidecar"]["status"] == "present"


def test_literal_changes_are_bounded_preserve_duplicates_and_expose_reordering(prepared):
    result = inspect(prepared, action="replace", caption="portrait, saved, portrait")
    assert result["literal_text_changed"] and result["literal_changes_total"] == 0
    result = inspect(prepared, action="replace", caption=", ".join(["z" * 300] * 100))
    assert result["literal_changes_total"] == 103
    assert len(result["literal_changes"]) == comparison.PHRASE_ITEMS
    assert result["literal_changes_truncated"]
    assert all(
        len(row["text"]) <= comparison.PHRASE_CHARACTERS for row in result["literal_changes"]
    )
    assert len(result["effective"]["proposed"]["text"]) > 30000


@pytest.mark.parametrize("target", ["current", "sidecar", "report", "draft"])
def test_concurrent_change_during_candidate_verification_is_rejected(prepared, monkeypatch, target):
    original = comparison._Reads.verify
    calls = 0

    def racing(reader):
        nonlocal calls
        calls += 1
        if calls == 1:
            if target == "current":
                review_image(
                    prepared["config"],
                    prepared["run"],
                    "a.png",
                    caption="concurrent",
                    reason="fixture",
                )
            else:
                path = (
                    prepared["config"].source / "a.txt"
                    if target == "sidecar"
                    else prepared[target] / "run.json"
                    if target == "report"
                    else prepared["drafts"] / "manifest.jsonl"
                )
                with path.open("ab") as stream:
                    stream.write(b" ")
        return original(reader)

    monkeypatch.setattr(comparison._Reads, "verify", racing)
    with pytest.raises(ReviewConflict):
        inspect(prepared)


def test_missing_sidecar_appearing_during_inspection_is_rejected(prepared, monkeypatch):
    sidecar = prepared["config"].source / "a.txt"
    raw = sidecar.read_bytes()
    sidecar.unlink()
    original = comparison._Reads.verify

    def racing(reader):
        sidecar.write_bytes(raw)
        return original(reader)

    monkeypatch.setattr(comparison._Reads, "verify", racing)
    with pytest.raises(ReviewConflict):
        inspect(prepared)


def test_current_review_history_must_preserve_exact_report_lineage(prepared):
    config = prepared["config"]
    store = ReviewStore(config.reviews, config.source)
    state = store.read()
    event = state["history"][0]
    event["record"]["reason"] = "rewritten"
    state["images"][event["key"]]["reason"] = "rewritten"
    save(store.path, state)
    with pytest.raises(ValueError, match="diverges"):
        inspect(prepared)


@pytest.mark.parametrize("target", ["input", "report"])
def test_changed_lineage_is_rejected(prepared, target):
    path = prepared[target] / ("run.json" if target == "input" else "entries.jsonl")
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        inspect(prepared)


@pytest.mark.parametrize(
    "options",
    [
        {"action": "other"},
        {"action": "replace"},
        {"action": "keep", "caption": "unexpected"},
        {"action": "replace", "caption": "a" * (comparison.CANDIDATE_BYTES + 1)},
    ],
)
def test_invalid_request_is_rejected_without_writes(prepared, tmp_path, options):
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        inspect(prepared, **options)
    assert tree(tmp_path) == before


def test_unknown_image_rejected(prepared):
    with pytest.raises(ValueError, match="Unknown report image"):
        inspect_caption_comparison(
            prepared["config"], prepared["run"], prepared["report"], "unknown"
        )
