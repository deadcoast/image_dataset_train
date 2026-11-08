"""Publish perceptual-hash pair proposals from a verified inventory."""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, ImageOps

from image_dataset_train import __version__
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import publish_directory
from image_dataset_train.inventory import file_sha256
from image_dataset_train.inventory_data import read_inventory

PHASH_VERSION = "phash64-padded-white-gray-v1"
PHASH_SIZE = 32
PHASH_LOW_FREQUENCIES = 8


class _BKNode:
    def __init__(self, value: int, path: str, digest: str) -> None:
        self.value = value
        self.rows = [(path, digest)]
        self.children: dict[int, _BKNode] = {}


class _BKTree:
    """Hamming-distance index used to avoid a full all-pairs comparison."""

    def __init__(self) -> None:
        self.root: _BKNode | None = None

    @staticmethod
    def distance(left: int, right: int) -> int:
        return (left ^ right).bit_count()

    def add(self, value: int, path: str, digest: str) -> None:
        if self.root is None:
            self.root = _BKNode(value, path, digest)
            return

        node = self.root
        while True:
            distance = self.distance(value, node.value)
            if distance:
                child = node.children.get(distance)
                if child is None:
                    node.children[distance] = _BKNode(value, path, digest)
                    break
                node = child
            else:
                node.rows.append((path, digest))
                break

    def query(self, value: int, radius: int) -> list[tuple[int, str, str]]:
        matches: list[tuple[int, str, str]] = []
        if self.root is None:
            return matches
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = self.distance(value, node.value)
            if distance <= radius:
                matches.extend(
                    (distance, path, digest) for path, digest in node.rows
                )
            low, high = distance - radius, distance + radius
            stack.extend(
                child for edge, child in node.children.items() if low <= edge <= high
            )
        return matches

    def add_and_query(
        self, value: int, path: str, digest: str, radius: int
    ) -> list[tuple[int, str, str]]:
        matches = self.query(value, radius)
        self.add(value, path, digest)
        return matches


def _source_bytes(source: Path, row: dict, max_file_bytes: int) -> bytes:
    relative = PurePosixPath(row.get("source_path", ""))
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in str(relative)
        or ":" in str(relative)
    ):
        raise ValueError("unsafe inventory source path")
    path = source.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(source):
        raise ValueError("inventory source path escapes source directory")
    for part in (path, *path.parents):
        if part == source:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("source path became a link after inventory")
    with path.open("rb") as stream:
        raw = stream.read(max_file_bytes + 1)
    if len(raw) > max_file_bytes:
        raise ValueError("source exceeds configured byte limit")
    if hashlib.sha256(raw).hexdigest() != row.get("sha256"):
        raise ValueError("source_changed_since_inventory")
    return raw


def _dct_hash(raw: bytes, max_decode_pixels: int) -> int:
    """Compute the low-frequency 64-bit DCT hash using a fixed input policy."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > max_decode_pixels:
                raise ValueError("image exceeds configured decode pixel limit")
            if getattr(opened, "n_frames", 1) != 1:
                raise ValueError("multiple-frame image is not eligible for similarity")
            image = ImageOps.exif_transpose(opened)
            image.load()
            if max(image.size) ** 2 > max_decode_pixels:
                raise ValueError("square similarity preparation exceeds configured pixel limit")
            rgba = image.convert("RGBA")
            side = max(rgba.size)
            canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
            canvas.alpha_composite(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
            pixels = list(
                canvas.convert("L")
                .resize((PHASH_SIZE, PHASH_SIZE), Image.Resampling.LANCZOS)
                .getdata()
            )

    # Separable 2D DCT-II, retaining only the top-left 8x8 coefficients.
    cosine = [
        [math.cos(math.pi * (2 * position + 1) * frequency / (2 * PHASH_SIZE))
         for position in range(PHASH_SIZE)]
        for frequency in range(PHASH_LOW_FREQUENCIES)
    ]
    horizontal = [[0.0] * PHASH_SIZE for _ in range(PHASH_SIZE)]
    for y in range(PHASH_SIZE):
        offset = y * PHASH_SIZE
        for frequency in range(PHASH_LOW_FREQUENCIES):
            basis = cosine[frequency]
            horizontal[y][frequency] = sum(
                pixels[offset + x] * basis[x] for x in range(PHASH_SIZE)
            )
    coefficients = [
        sum(horizontal[y][x_frequency] * cosine[y_frequency][y] for y in range(PHASH_SIZE))
        for y_frequency in range(PHASH_LOW_FREQUENCIES)
        for x_frequency in range(PHASH_LOW_FREQUENCIES)
    ]
    ordered = sorted(coefficients)
    median = (ordered[31] + ordered[32]) / 2
    result = 0
    for coefficient in coefficients:
        result = (result << 1) | int(coefficient >= median)
    return result


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def propose_similar(
    config: Config,
    inventory: Path,
    *,
    max_distance: int = 8,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict]:
    """Publish review-only perceptual-hash candidates without changing sources."""
    if type(max_distance) is not int or not 0 <= max_distance <= 64:
        raise ValueError("max_distance must be an integer between 0 and 64")
    inventory_meta, records, inventory_hash = read_inventory(inventory)
    source = Path(inventory_meta["source"]).resolve(strict=True)
    runs = config.runs.resolve()
    if source.is_relative_to(runs) or runs.is_relative_to(source):
        raise ValueError("source and similarity output directories must be separate trees")

    image_rows = [
        row
        for row in records
        if row.get("kind") == "image"
        and row.get("decision") in {"candidate", "review"}
        and isinstance(row.get("sha256"), str)
    ]
    tree = _BKTree()
    hashes: list[dict] = []
    pairs: list[dict] = []
    hash_by_path: dict[str, str] = {}
    errors = 0
    for number, row in enumerate(image_rows, 1):
        item = {
            "source_path": row["source_path"],
            "sha256": row["sha256"],
            "phash": None,
            "decision": "error",
            "error": None,
        }
        try:
            raw = _source_bytes(source, row, config.validation.max_file_bytes)
            value = _dct_hash(raw, config.validation.max_decode_pixels)
            item.update(phash=f"{value:016x}", decision="indexed")
            hash_by_path[row["source_path"]] = item["phash"]
            for distance, prior_path, prior_digest in tree.add_and_query(
                value, row["source_path"], row["sha256"], max_distance
            ):
                pairs.append(
                    {
                        "left_source_path": prior_path,
                        "left_sha256": prior_digest,
                        "left_phash": hash_by_path[prior_path],
                        "right_source_path": row["source_path"],
                        "right_sha256": row["sha256"],
                        "right_phash": f"{value:016x}",
                        "hamming_distance": distance,
                        "max_distance": max_distance,
                        "review_status": "unreviewed",
                    }
                )
        except (
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ) as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            errors += 1
        hashes.append(item)
        if progress and number % 100 == 0:
            progress(f"Hashed {number:,}/{len(image_rows):,} images; proposed {len(pairs):,} pairs")

    pairs.sort(key=lambda pair: (pair["left_source_path"], pair["right_source_path"]))
    summary = {
        "schema_version": 1,
        "stage": "similarity",
        "training_ready": False,
        "images_considered": len(image_rows),
        "images_hashed": sum(row["decision"] == "indexed" for row in hashes),
        "errors": errors,
        "pairs_proposed": len(pairs),
        "max_hamming_distance": max_distance,
        "hash_bits": 64,
        "hash_version": PHASH_VERSION,
        "review_required": True,
        "source_files_changed": False,
    }
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "stage": "similarity",
        "status": "completed_with_errors" if errors else "completed",
        "started_at": started.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "source": str(source),
        "inventory_run": str(inventory.resolve()),
        "inventory_manifest_sha256": inventory_hash,
        "pipeline_version": __version__,
        "hash_version": PHASH_VERSION,
        "hash_bits": 64,
        "max_hamming_distance": max_distance,
    }
    runs.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-similarity-", dir=runs))
    (staging / "images.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in hashes),
        encoding="utf-8",
        newline="\n",
    )
    (staging / "pairs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in pairs),
        encoding="utf-8",
        newline="\n",
    )
    (staging / "summary.json").write_text(_json(summary), encoding="utf-8", newline="\n")
    (staging / "run.json").write_text(_json(metadata), encoding="utf-8", newline="\n")
    final = runs / run_id
    publish_directory(staging, final)
    return final, summary
