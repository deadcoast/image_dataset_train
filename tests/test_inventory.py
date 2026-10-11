from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from image_dataset_train import inventory
from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.inventory import file_sha256, scan
from image_dataset_train.runs import run_scan


@pytest.fixture
def source(tmp_path: Path) -> Path:
    result = tmp_path / "originals"
    result.mkdir()
    return result


@pytest.fixture
def preferences() -> ValidationConfig:
    return ValidationConfig(min_short_side=16, max_long_side=128)


def picture(path: Path, size: tuple[int, int] = (32, 48), color: str = "blue") -> None:
    Image.new("RGB", size, color).save(path)


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_preservation_and_deterministic_runs(source: Path, preferences: ValidationConfig) -> None:
    picture(source / "original.png")
    (source / "original.txt").write_text("existing manual caption", encoding="utf-8")
    shutil.copy2(source / "original.png", source / "copy.png")
    (source / "unrelated.json").write_text('{"keep": true}', encoding="utf-8")
    before = snapshot(source)
    config = Config(source, source.parent / "runs", preferences)

    first, summary = run_scan(config)
    second, _ = run_scan(config)

    assert first != second
    assert snapshot(source) == before
    assert (first / "manifest.jsonl").read_bytes() == (second / "manifest.jsonl").read_bytes()
    assert (first / "summary.json").read_bytes() == (second / "summary.json").read_bytes()
    assert summary["files_seen"] == 4
    assert summary["images_seen"] == 2
    assert summary["decisions"]["duplicate"] == 1
    assert summary["training_ready"] is False
    manifest = (first / "manifest.jsonl").read_bytes()
    metadata = json.loads((first / "run.json").read_text(encoding="utf-8"))
    assert metadata["manifest_sha256"] == hashlib.sha256(manifest).hexdigest()
    assert metadata["status"] == "completed"
    assert set(p.name for p in first.iterdir()) == {"manifest.jsonl", "summary.json", "run.json"}


def test_hash_covers_bytes_beyond_first_megabyte(tmp_path: Path) -> None:
    first, second = tmp_path / "a.bin", tmp_path / "b.bin"
    prefix = b"x" * (1024 * 1024)
    first.write_bytes(prefix + b"a")
    second.write_bytes(prefix + b"b")
    assert file_sha256(first) != file_sha256(second)
    assert file_sha256(first) == hashlib.sha256(first.read_bytes()).hexdigest()


def test_invalid_images_do_not_abort_remaining_files(
    source: Path, preferences: ValidationConfig
) -> None:
    (source / "empty.png").touch()
    (source / "broken.jpg").write_bytes(b"not an image")
    picture(source / "valid.png")
    picture(source / "truncated.bmp")
    data = (source / "truncated.bmp").read_bytes()
    (source / "truncated.bmp").write_bytes(data[: len(data) // 2])
    rows = {r.source_path: r for r in scan(source, preferences)}
    assert rows["empty.png"].reasons == ["empty_file"]
    assert rows["broken.jpg"].reasons == ["unreadable_image"]
    assert rows["truncated.bmp"].decision == "rejected"
    assert rows["valid.png"].decision == "candidate"


def test_animation_is_rejected_without_changing_file(
    source: Path, preferences: ValidationConfig
) -> None:
    path = source / "animated.png"
    with Image.new("RGB", (32, 32), "red") as first:
        with Image.new("RGB", (32, 32), "blue") as second:
            first.save(path, save_all=True, append_images=[second], duration=100, loop=0)
    before = path.read_bytes()
    row = scan(source, preferences)[0]
    assert row.decision == "rejected"
    assert row.reasons == ["multiple_frames"]
    assert row.frames == 2
    assert path.read_bytes() == before


def test_exif_display_dimensions(source: Path, preferences: ValidationConfig) -> None:
    with Image.new("RGB", (24, 40), "green") as image:
        exif = Image.Exif()
        exif[274] = 6
        image.save(source / "rotated.jpg", exif=exif)
    row = scan(source, preferences)[0]
    assert (row.stored_width, row.stored_height) == (24, 40)
    assert (row.width, row.height) == (40, 24)
    assert row.exif_orientation == 6


def test_resolution_and_transparency_are_review_flags(source: Path) -> None:
    with Image.new("RGBA", (8, 200), (255, 0, 0, 0)) as image:
        image.save(source / "small-transparent.png")
    row = scan(source, ValidationConfig(min_short_side=16, max_long_side=128))[0]
    assert row.decision == "review"
    assert set(row.reasons) == {
        "short_side_below_preference",
        "long_side_above_preference",
        "alpha_needs_background_policy",
    }


def test_pixel_limit_precedes_decode(
    source: Path, preferences: ValidationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    picture(source / "large.png", (40, 40))

    def unexpected_decode(*args, **kwargs):
        pytest.fail("decoded before checking configured pixel limit")

    monkeypatch.setattr(Image.Image, "load", unexpected_decode)
    row = scan(source, replace(preferences, max_decode_pixels=1000))[0]
    assert row.reasons == ["decode_pixel_limit"]


def test_file_limit(source: Path, preferences: ValidationConfig) -> None:
    picture(source / "limited.png")
    row = scan(source, replace(preferences, max_file_bytes=10))[0]
    assert row.reasons == ["file_byte_limit"]
    assert row.sha256 == file_sha256(source / "limited.png")


def test_same_stem_captions_are_not_silently_assigned(
    source: Path, preferences: ValidationConfig
) -> None:
    picture(source / "same.jpg")
    picture(source / "same.png", color="red")
    (source / "same.txt").write_text("ambiguous", encoding="utf-8")
    rows = [r for r in scan(source, preferences) if r.kind == "image"]
    assert len(rows) == 2
    assert all(r.decision == "review" and r.sidecar_path is None for r in rows)
    assert all("ambiguous_sidecar_stem" in r.reasons for r in rows)


def test_duplicate_caption_conflicts_remain_visible(
    source: Path, preferences: ValidationConfig
) -> None:
    picture(source / "a.png")
    shutil.copy2(source / "a.png", source / "b.png")
    (source / "a.txt").write_text("first caption", encoding="utf-8")
    (source / "b.txt").write_text("second caption", encoding="utf-8")
    rows = {r.source_path: r for r in scan(source, preferences)}
    assert rows["a.png"].decision == "review"
    assert rows["b.png"].duplicate_of == "a.png"
    assert rows["a.png"].sidecar_sha256 != rows["b.png"].sidecar_sha256
    assert "duplicate_sidecar_conflict" in rows["a.png"].reasons
    assert "duplicate_sidecar_conflict" in rows["b.png"].reasons


def test_nested_unicode_and_uppercase_sidecars(source: Path, preferences: ValidationConfig) -> None:
    nested = source / "素材"
    nested.mkdir()
    picture(nested / "絵.PNG")
    (nested / "絵.TXT").write_text("preserve", encoding="utf-8")
    rows = {r.source_path: r for r in scan(source, preferences)}
    assert rows["素材/絵.PNG"].sidecar_path == "素材/絵.TXT"


@pytest.mark.parametrize("nested", ["runs_inside_source", "source_inside_runs", "same"])
def test_overlapping_directories_refused(
    source: Path, preferences: ValidationConfig, nested: str
) -> None:
    runs = {
        "runs_inside_source": source / "reports",
        "source_inside_runs": source.parent,
        "same": source,
    }[nested]
    with pytest.raises(ValueError, match="separate directory trees"):
        run_scan(Config(source, runs, preferences))
    assert not list(source.iterdir())


def test_missing_source_does_not_create_output(
    tmp_path: Path, preferences: ValidationConfig
) -> None:
    runs = tmp_path / "runs"
    with pytest.raises(FileNotFoundError):
        run_scan(Config(tmp_path / "missing", runs, preferences))
    assert not runs.exists()


def test_read_failure_is_reported_and_other_images_continue(
    source: Path, preferences: ValidationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    picture(source / "locked.png")
    picture(source / "okay.png", color="red")
    original = inventory.file_sha256

    def fail_one(path: Path) -> str:
        if path.name == "locked.png":
            raise PermissionError("fixture file unavailable")
        return original(path)

    monkeypatch.setattr(inventory, "file_sha256", fail_one)
    directory, summary = run_scan(Config(source, source.parent / "runs", preferences))
    assert summary["decisions"]["error"] == 1
    assert summary["decisions"]["candidate"] == 1
    assert json.loads((directory / "run.json").read_text())["status"] == "completed_with_errors"


def test_mutation_during_scan_cannot_be_a_candidate(
    source: Path, preferences: ValidationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    picture(source / "changing.png")
    original = inventory.file_sha256

    def change_after_hash(path: Path) -> str:
        digest = original(path)
        with path.open("ab") as stream:
            stream.write(b"changed")
        return digest

    monkeypatch.setattr(inventory, "file_sha256", change_after_hash)
    row = scan(source, preferences)[0]
    assert row.decision == "error"
    assert row.reasons == ["source_changed_during_scan"]


def test_links_are_not_followed(source: Path, preferences: ValidationConfig) -> None:
    outside = source.parent / "outside"
    outside.mkdir()
    picture(outside / "private.png")
    try:
        (source / "linked-folder").symlink_to(outside, target_is_directory=True)
        (source / "linked.png").symlink_to(outside / "private.png")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable in this environment: {exc}")
    rows = scan(source, preferences)
    assert len(rows) == 2
    assert all(row.kind == "link" and row.sha256 is None for row in rows)


def test_empty_scan_is_explicitly_not_training_ready(
    source: Path, preferences: ValidationConfig
) -> None:
    _, summary = run_scan(Config(source, source.parent / "runs", preferences))
    assert summary["files_seen"] == 0
    assert summary["training_ready"] is False


def test_publication_failure_leaves_no_completed_run(
    source: Path, preferences: ValidationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    picture(source / "a.png")
    runs = source.parent / "runs"
    before = snapshot(source)

    def fail_rename(*args, **kwargs):
        raise PermissionError("publication unavailable")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(PermissionError):
        run_scan(Config(source, runs, preferences))
    assert all(p.name.startswith(".pending-") for p in runs.iterdir())
    assert snapshot(source) == before
