"""Publish perceptual-hash pair proposals from a verified inventory."""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
import warnings
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from platform import python_version
from uuid import uuid4

from PIL import Image, ImageOps
from PIL import __version__ as pillow_version

from image_dataset_train import __version__
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import publish_directory
from image_dataset_train.execution import RunClock, processing_history
from image_dataset_train.inventory import file_sha256
from image_dataset_train.inventory_data import read_inventory

PHASH_VERSION = "phash64-padded-white-gray-v1"
PHASH_SIZE = 32
PHASH_LOW_FREQUENCIES = 8
_DCT_COSINE = tuple(
    tuple(
        math.cos(math.pi * (2 * position + 1) * frequency / (2 * PHASH_SIZE))
        for position in range(PHASH_SIZE)
    )
    for frequency in range(PHASH_LOW_FREQUENCIES)
)


class _BKNode:
    def __init__(self, value: int, path: str, digest: str) -> None:
        self.value = value
        self.rows = [(path, digest)]
        self.children: dict[int, _BKNode] = {}


class _BKTree:
    """Hamming-distance index that prunes comparisons outside the query radius."""

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

    def query(self, value: int, radius: int) -> Iterator[tuple[int, str, str]]:
        """Yield matching hashes in deterministic tree traversal order."""
        if self.root is None:
            return
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = self.distance(value, node.value)
            if distance <= radius:
                for path, digest in node.rows:
                    yield distance, path, digest
            low, high = distance - radius, distance + radius
            for edge, child in sorted(node.children.items(), reverse=True):
                if low <= edge <= high:
                    stack.append(child)


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
            if max(opened.size) ** 2 > max_decode_pixels:
                raise ValueError("square similarity preparation exceeds configured pixel limit")
            if getattr(opened, "n_frames", 1) != 1:
                raise ValueError("multiple-frame image is not eligible for similarity")
            image = ImageOps.exif_transpose(opened)
            image.load()
            rgba = image.convert("RGBA")
            side = max(rgba.size)
            canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
            canvas.alpha_composite(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
            pixels = (
                canvas.convert("L")
                .resize((PHASH_SIZE, PHASH_SIZE), Image.Resampling.LANCZOS)
                .tobytes()
            )

    # Separable 2D DCT-II, retaining only the top-left 8x8 coefficients.
    horizontal = [[0.0] * PHASH_LOW_FREQUENCIES for _ in range(PHASH_SIZE)]
    for y in range(PHASH_SIZE):
        offset = y * PHASH_SIZE
        for frequency in range(PHASH_LOW_FREQUENCIES):
            basis = _DCT_COSINE[frequency]
            horizontal[y][frequency] = sum(pixels[offset + x] * basis[x] for x in range(PHASH_SIZE))
    coefficients = [
        sum(horizontal[y][x_frequency] * _DCT_COSINE[y_frequency][y] for y in range(PHASH_SIZE))
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
    clock = RunClock()
    if type(max_distance) is not int or not 0 <= max_distance <= 64:
        raise ValueError("max_distance must be an integer between 0 and 64")
    started = datetime.now(UTC)
    inventory_meta, records, inventory_hash = read_inventory(inventory)
    source = Path(inventory_meta["source"]).resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"source must be a directory: {source}")
    runs = config.runs.resolve()
    if source.is_relative_to(runs) or runs.is_relative_to(source):
        raise ValueError("source and similarity output directories must be separate trees")

    images = [row for row in records if row["kind"] == "image"]
    image_rows = [row for row in images if row["decision"] in {"candidate", "review"}]
    exact_duplicates = sum(row["decision"] == "duplicate" for row in images)
    image_rows.sort(key=lambda row: row["source_path"])
    tree = _BKTree()
    hash_by_path: dict[str, str] = {}
    errors = 0
    pairs_proposed = 0
    images_hashed = 0
    runs.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-similarity-", dir=runs))
    images_path, pairs_path = staging / "images.jsonl", staging / "pairs.jsonl"
    with (
        images_path.open("w", encoding="utf-8", newline="\n") as images_file,
        pairs_path.open("w", encoding="utf-8", newline="\n") as pairs_file,
    ):
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
            except (
                OSError,
                ValueError,
                SyntaxError,
                Image.DecompressionBombWarning,
                Image.DecompressionBombError,
            ) as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
                errors += 1
            else:
                item.update(phash=f"{value:016x}", decision="indexed")
                hash_by_path[row["source_path"]] = item["phash"]
                images_hashed += 1
                for distance, prior_path, prior_digest in tree.query(value, max_distance):
                    pair_identity = "\0".join(
                        (
                            PHASH_VERSION,
                            prior_path,
                            prior_digest,
                            row["source_path"],
                            row["sha256"],
                        )
                    )
                    proposal = {
                        "pair_id": hashlib.sha256(pair_identity.encode("utf-8")).hexdigest(),
                        "left_source_path": prior_path,
                        "left_sha256": prior_digest,
                        "left_phash": hash_by_path[prior_path],
                        "right_source_path": row["source_path"],
                        "right_sha256": row["sha256"],
                        "right_phash": item["phash"],
                        "hamming_distance": distance,
                        "max_distance": max_distance,
                        "review_status": "unreviewed",
                    }
                    pairs_file.write(
                        json.dumps(proposal, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                    pairs_proposed += 1
                tree.add(value, row["source_path"], row["sha256"])
            images_file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            if progress and number % 100 == 0:
                progress(
                    f"Hashed {number:,}/{len(image_rows):,} images; "
                    f"proposed {pairs_proposed:,} pairs"
                )

    summary = {
        "schema_version": 1,
        "stage": "similarity",
        "training_ready": False,
        "images_seen": len(images),
        "exact_duplicates_skipped": exact_duplicates,
        "ineligible_images_skipped": len(images) - len(image_rows) - exact_duplicates,
        "images_considered": len(image_rows),
        "images_hashed": images_hashed,
        "errors": errors,
        "pairs_proposed": pairs_proposed,
        "max_hamming_distance": max_distance,
        "hash_bits": 64,
        "hash_version": PHASH_VERSION,
        "review_required": True,
        "source_write_attempted": False,
    }
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
        "python_version": python_version(),
        "pillow_version": pillow_version,
        "hash_version": PHASH_VERSION,
        "hash_bits": 64,
        "max_hamming_distance": max_distance,
        "validation": asdict(config.validation),
    }
    (staging / "summary.json").write_text(_json(summary), encoding="utf-8", newline="\n")
    metadata["images_sha256"] = file_sha256(staging / "images.jsonl")
    metadata["pairs_sha256"] = file_sha256(staging / "pairs.jsonl")
    metadata["summary_sha256"] = file_sha256(staging / "summary.json")
    metadata["processing_history"] = processing_history(inventory_meta)
    metadata["metrics"] = clock.measure(staging)
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    (staging / "run.json").write_text(_json(metadata), encoding="utf-8", newline="\n")
    final = runs / run_id
    publish_directory(staging, final)
    return final, summary
