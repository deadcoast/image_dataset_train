"""Inventory and validate source files without modifying them."""

from __future__ import annotations

import hashlib
import os
import stat
import warnings
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from image_dataset_train.config import ValidationConfig

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Record:
    schema_version: int
    source_path: str
    kind: str
    decision: str = "skipped"
    reasons: list[str] = field(default_factory=list)
    sha256: str | None = None
    size_bytes: int | None = None
    format: str | None = None
    mode: str | None = None
    stored_width: int | None = None
    stored_height: int | None = None
    width: int | None = None
    height: int | None = None
    exif_orientation: int | None = None
    has_alpha: bool | None = None
    has_icc_profile: bool | None = None
    frames: int | None = None
    sidecar_path: str | None = None
    sidecar_sha256: str | None = None
    duplicate_of: str | None = None
    error: str | None = None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _walk(root: Path) -> Iterator[Path]:
    def on_error(error: OSError) -> None:
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        for name in sorted(dirs):
            path = Path(directory) / name
            if _is_link(path):
                dirs.remove(name)
                yield path
        dirs.sort()
        for name in sorted(files):
            yield Path(directory) / name


def _signature(path: Path) -> tuple[int, int, int, int]:
    info = path.stat(follow_symlinks=False)
    return info.st_size, info.st_mtime_ns, info.st_ino, info.st_mode


def _inspect_image(path: Path, row: Record, config: ValidationConfig) -> None:
    if row.size_bytes == 0:
        row.decision, row.reasons = "rejected", ["empty_file"]
        return
    if row.size_bytes is not None and row.size_bytes > config.max_file_bytes:
        row.decision, row.reasons = "rejected", ["file_byte_limit"]
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                row.format, row.mode = image.format, image.mode
                row.stored_width, row.stored_height = image.size
                row.width, row.height = image.size
                if image.width * image.height > config.max_decode_pixels:
                    row.decision, row.reasons = "rejected", ["decode_pixel_limit"]
                    return
                row.frames = getattr(image, "n_frames", 1)
                if row.frames != 1:
                    row.decision, row.reasons = "rejected", ["multiple_frames"]
                    return
                image.verify()
            # verify() checks file structure; a second open/load checks actual decoding.
            with Image.open(path) as image:
                image.load()
                row.exif_orientation = image.getexif().get(274, 1)
                if row.exif_orientation in {5, 6, 7, 8}:
                    row.width, row.height = image.height, image.width
                row.has_alpha = "A" in image.getbands() or "transparency" in image.info
                row.has_icc_profile = bool(image.info.get("icc_profile"))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        row.decision, row.reasons = "rejected", ["decoder_pixel_limit"]
        return
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        row.decision, row.reasons = "rejected", ["unreadable_image"]
        row.error = f"{type(exc).__name__}: {exc}"
        return

    row.decision = "candidate"
    assert row.width is not None and row.height is not None
    if min(row.width, row.height) < config.min_short_side:
        row.reasons.append("short_side_below_preference")
    if max(row.width, row.height) > config.max_long_side:
        row.reasons.append("long_side_above_preference")
    if row.has_alpha:
        row.reasons.append("alpha_needs_background_policy")
    if row.has_icc_profile:
        row.reasons.append("icc_profile_present")
    if row.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
        row.reasons.append("mode_needs_conversion")
    if row.exif_orientation not in range(1, 9):
        row.reasons.append("invalid_exif_orientation")
    if row.reasons:
        row.decision = "review"


def scan(
    source: Path,
    config: ValidationConfig,
    progress: Callable[[int], None] | None = None,
) -> list[Record]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"source must be a directory: {source}")
    records = []
    for path in _walk(source):
        relative = path.relative_to(source).as_posix()
        suffix = path.suffix.lower()
        kind = "image" if suffix in IMAGE_EXTENSIONS else "sidecar" if suffix == ".txt" else "other"
        row = Record(schema_version=1, source_path=relative, kind=kind)
        records.append(row)
        try:
            if _is_link(path):
                row.kind, row.reasons = "link", ["link_not_followed"]
                continue
            before = _signature(path)
            if not stat.S_ISREG(before[3]):
                row.kind, row.reasons = "other", ["not_regular_file"]
                continue
            row.size_bytes = before[0]
            row.sha256 = file_sha256(path)
            if kind == "image":
                _inspect_image(path, row, config)
            else:
                row.reasons = ["existing_sidecar" if kind == "sidecar" else "unsupported_extension"]
            if before != _signature(path):
                row.decision, row.reasons = "error", ["source_changed_during_scan"]
        except OSError as exc:
            row.decision, row.reasons = "error", ["file_read_error"]
            row.error = f"{type(exc).__name__}: {exc}"
        finally:
            if progress:
                progress(len(records))

    records.sort(key=lambda row: row.source_path)
    _associate_sidecars(records)
    _mark_exact_duplicates(records)
    return records


def _review(row: Record, reason: str) -> None:
    row.reasons.append(reason)
    if row.decision == "candidate":
        row.decision = "review"


def _associate_sidecars(records: list[Record]) -> None:
    sidecars: dict[str, list[Record]] = defaultdict(list)
    images: dict[str, list[Record]] = defaultdict(list)
    for row in records:
        key = str(Path(row.source_path).with_suffix("")).casefold()
        if row.kind == "sidecar":
            sidecars[key].append(row)
        elif row.kind == "image":
            images[key].append(row)
    for key, rows in images.items():
        matches = sidecars.get(key, [])
        for row in rows:
            if len(rows) > 1 or len(matches) > 1:
                _review(row, "ambiguous_sidecar_stem")
            elif matches:
                sidecar = matches[0]
                row.sidecar_path = sidecar.source_path
                row.sidecar_sha256 = sidecar.sha256
                if sidecar.decision == "error":
                    _review(row, "sidecar_read_error")
            # Existing captions are inventoried, never interpreted as generated captions.


def _mark_exact_duplicates(records: list[Record]) -> None:
    groups: dict[str, list[Record]] = defaultdict(list)
    for row in records:
        if row.kind == "image" and row.decision in {"candidate", "review"} and row.sha256:
            groups[row.sha256].append(row)
    for rows in groups.values():
        keeper = rows[0]
        if len({row.sidecar_sha256 for row in rows}) > 1:
            for row in rows:
                _review(row, "duplicate_sidecar_conflict")
        for row in rows[1:]:
            row.decision = "duplicate"
            row.duplicate_of = keeper.source_path
            row.reasons.append("exact_sha256")


def summarize(records: list[Record]) -> dict:
    images = [row for row in records if row.kind == "image"]
    return {
        "schema_version": 1,
        "stage": "inventory",
        "training_ready": False,
        "files_seen": len(records),
        "images_seen": len(images),
        "decisions": dict(sorted(Counter(row.decision for row in records).items())),
        "reasons": dict(sorted(Counter(r for row in records for r in row.reasons).items())),
        "image_formats": dict(sorted(Counter(row.format for row in images if row.format).items())),
        "images_with_sidecar": sum(row.sidecar_path is not None for row in images),
        "image_bytes": sum(row.size_bytes or 0 for row in images),
    }
