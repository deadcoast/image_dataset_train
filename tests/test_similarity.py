from __future__ import annotations

import errno
import io
import json
import os
import random
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from image_dataset_train import similarity
from image_dataset_train.cli import main
from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.inventory import file_sha256
from image_dataset_train.inventory_data import read_inventory
from image_dataset_train.runs import run_scan


def artwork(seed: int = 41) -> Image.Image:
    image = Image.new("RGB", (128, 96), "white")
    draw = ImageDraw.Draw(image)
    randomizer = random.Random(seed)
    for _ in range(30):
        x, y = randomizer.randrange(110), randomizer.randrange(80)
        color = tuple(randomizer.randrange(256) for _ in range(3))
        draw.rectangle((x, y, x + 17, y + 15), fill=color)
    return image


def encoded(image: Image.Image, **options) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", **options)
    return stream.getvalue()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def collection(tmp_path: Path) -> tuple[Config, Path]:
    source = tmp_path / "originals"
    source.mkdir()
    artwork().save(source / "a.png")
    artwork().save(source / "b.jpg", quality=93)
    artwork(2026).save(source / "c.png")
    (source / "duplicate.png").write_bytes((source / "a.png").read_bytes())
    (source / "a.txt").write_text("manual caption", encoding="utf-8")
    (source / "broken.png").write_bytes(b"not an image")
    config = Config(source, tmp_path / "inventory-runs", ValidationConfig())
    inventory, _ = run_scan(config)
    return replace(config, runs=tmp_path / "similarity-runs"), inventory


def test_real_images_propose_variants_preserve_sources_and_publish_provenance(collection):
    config, inventory = collection
    before = snapshot(config.source)
    first, summary = similarity.propose_similar(config, inventory)
    second, repeated = similarity.propose_similar(config, inventory)
    assert snapshot(config.source) == before
    assert first != second
    for filename in ("images.jsonl", "pairs.jsonl", "summary.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    proposals = rows(first / "pairs.jsonl")
    assert {(p["left_source_path"], p["right_source_path"]) for p in proposals} == {
        ("a.png", "b.jpg")
    }
    assert all(p["review_status"] == "unreviewed" for p in proposals)
    assert summary == repeated
    assert summary["images_hashed"] == 3
    assert summary["errors"] == 0
    assert summary["training_ready"] is False
    assert summary["images_seen"] == 5
    assert summary["exact_duplicates_skipped"] == 1
    assert summary["ineligible_images_skipped"] == 1
    metadata = json.loads((first / "run.json").read_text())
    assert metadata["status"] == "completed"
    assert metadata["validation"] == asdict(config.validation)
    assert metadata["inventory_manifest_sha256"] == file_sha256(inventory / "manifest.jsonl")
    assert metadata["python_version"] and metadata["pillow_version"]
    for filename, key in (
        ("images.jsonl", "images_sha256"),
        ("pairs.jsonl", "pairs_sha256"),
        ("summary.json", "summary_sha256"),
    ):
        assert file_sha256(first / filename) == metadata[key]


def test_hash_orientation_and_alpha_policy():
    image = artwork()
    original_hash = similarity._dct_hash(encoded(image), 100_000)
    exif = Image.Exif()
    exif[274] = 6
    rotated = image.transpose(Image.Transpose.ROTATE_90)
    assert similarity._dct_hash(encoded(rotated, exif=exif), 100_000) == original_hash
    transparent = image.convert("RGBA")
    transparent.putalpha(128)
    white = Image.new("RGBA", image.size, "white")
    composited = Image.alpha_composite(white, transparent).convert("RGB")
    assert similarity._dct_hash(encoded(transparent), 100_000) == similarity._dct_hash(
        encoded(composited), 100_000
    )


def test_square_limit_is_checked_before_loading_pixels(monkeypatch):
    raw = encoded(Image.new("RGB", (10, 100), "white"))

    def forbidden_load(*args, **kwargs):
        pytest.fail("pixel decoding began before the square limit was checked")

    monkeypatch.setattr(Image.Image, "load", forbidden_load)
    with pytest.raises(ValueError, match="square"):
        similarity._dct_hash(raw, 2_000)


def test_multiframe_inputs_are_not_hashed():
    stream = io.BytesIO()
    artwork().save(stream, format="GIF", save_all=True, append_images=[artwork(2)])
    with pytest.raises(ValueError, match="multiple-frame"):
        similarity._dct_hash(stream.getvalue(), 100_000)


@pytest.mark.parametrize("radius", [0, 1, 8, 32, 64])
def test_index_matches_exhaustive_hamming_oracle(radius):
    rng = random.Random(72)
    values = [rng.getrandbits(64) for _ in range(70)]
    values += [values[0], values[0] ^ 1, values[0] ^ 255, 0, 2**64 - 1]
    index = similarity._BKTree()
    for number, value in enumerate(values):
        index.add(value, str(number), str(number))
    for query in [*values[:10], 0, 2**64 - 1]:
        expected = {
            (bin(query ^ value).count("1"), str(number), str(number))
            for number, value in enumerate(values)
            if bin(query ^ value).count("1") <= radius
        }
        actual = list(index.query(query, radius))
        assert set(actual) == expected
        assert len(actual) == len(expected)


def test_pair_ids_are_stable_across_thresholds_and_stream_before_all_hashes(
    collection, monkeypatch
):
    config, inventory = collection
    hashes_done = 0
    writes_at = []
    original_hash, original_open = similarity._dct_hash, Path.open

    def counted_hash(*args):
        nonlocal hashes_done
        hashes_done += 1
        return original_hash(*args)

    class ObservedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, value):
            writes_at.append(hashes_done)
            return self.stream.write(value)

    def observed_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.name == "pairs.jsonl" and args and args[0] == "w":
            return ObservedWriter(stream)
        return stream

    monkeypatch.setattr(similarity, "_dct_hash", counted_hash)
    monkeypatch.setattr(Path, "open", observed_open)
    broad, summary = similarity.propose_similar(config, inventory, max_distance=64)
    assert writes_at[0] == 2
    assert summary["pairs_proposed"] == 3
    broad_pairs = rows(broad / "pairs.jsonl")
    narrow, _ = similarity.propose_similar(config, inventory, max_distance=8)
    narrow_pairs = rows(narrow / "pairs.jsonl")
    assert {p["pair_id"] for p in narrow_pairs} <= {p["pair_id"] for p in broad_pairs}
    assert all(p["left_source_path"] < p["right_source_path"] for p in broad_pairs)


def test_source_changes_become_errors_without_stopping_other_images(collection):
    config, inventory = collection
    (config.source / "a.png").write_bytes(encoded(artwork(55)))
    result, summary = similarity.propose_similar(config, inventory)
    records = {row["source_path"]: row for row in rows(result / "images.jsonl")}
    assert records["a.png"]["decision"] == "error"
    assert "source_changed_since_inventory" in records["a.png"]["error"]
    assert summary["errors"] == 1
    assert summary["images_hashed"] == 2
    assert json.loads((result / "run.json").read_text())["status"] == "completed_with_errors"


@pytest.mark.parametrize("limit", ["max_file_bytes", "max_decode_pixels"])
def test_current_limits_are_respected_and_recorded(collection, limit):
    config, inventory = collection
    config = replace(config, validation=replace(config.validation, **{limit: 1}))
    result, summary = similarity.propose_similar(config, inventory)
    assert summary["images_hashed"] == 0
    assert summary["errors"] == 3
    assert not (result / "pairs.jsonl").read_bytes()


@pytest.mark.parametrize("radius", [-1, 65, 1.5, True])
def test_invalid_radius_has_no_output(collection, radius):
    config, inventory = collection
    with pytest.raises(ValueError, match="max_distance"):
        similarity.propose_similar(config, inventory, max_distance=radius)
    assert not config.runs.exists()


def test_overlap_refused_before_output(collection):
    config, inventory = collection
    output = config.source / "reports"
    with pytest.raises(ValueError, match="separate trees"):
        similarity.propose_similar(replace(config, runs=output), inventory)
    assert not output.exists()


def test_empty_inventory_and_source_root_validation(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    config = Config(source, tmp_path / "inventories", ValidationConfig())
    inventory, _ = run_scan(config)
    config = replace(config, runs=tmp_path / "results")
    result, summary = similarity.propose_similar(config, inventory)
    assert summary["images_hashed"] == summary["pairs_proposed"] == 0
    assert not (result / "images.jsonl").read_bytes()
    source.rmdir()
    source.write_text("directory replaced by a file")
    with pytest.raises(ValueError, match="directory"):
        similarity.propose_similar(config, inventory)
    assert len(list(config.runs.iterdir())) == 1


def test_output_failure_aborts_without_publishing_partial_success(collection, monkeypatch):
    config, inventory = collection
    before = snapshot(config.source)
    original_open = Path.open

    class BrokenWriter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, value):
            raise OSError(errno.ENOSPC, "simulated report disk full")

    def broken_open(path, *args, **kwargs):
        if path.name == "pairs.jsonl" and args and args[0] == "w":
            return BrokenWriter()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(OSError, match="report disk full"):
        similarity.propose_similar(config, inventory, max_distance=64)
    assert all(p.name.startswith(".pending-") for p in config.runs.iterdir())
    assert not list(config.runs.rglob("run.json"))
    assert snapshot(config.source) == before


def test_cancelled_stage_is_not_published_and_rerun_completes(collection, monkeypatch):
    config, inventory = collection
    original_hash = similarity._dct_hash
    count = 0

    def interrupt(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt
        return original_hash(*args)

    monkeypatch.setattr(similarity, "_dct_hash", interrupt)
    with pytest.raises(KeyboardInterrupt):
        similarity.propose_similar(config, inventory)
    pending = list(config.runs.iterdir())
    assert len(pending) == 1 and pending[0].name.startswith(".pending-")
    assert not (pending[0] / "run.json").exists()
    monkeypatch.setattr(similarity, "_dct_hash", original_hash)
    result, summary = similarity.propose_similar(config, inventory)
    assert summary["images_hashed"] == 3
    assert result.exists() and pending[0].exists()


def rewrite_manifest(inventory: Path, records: list) -> None:
    manifest = inventory / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    metadata_path = inventory / "run.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["manifest_sha256"] = file_sha256(manifest)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        7,
        {"stage": "inventory", "schema_version": True, "status": "completed"},
        {"stage": "inventory", "schema_version": 1, "status": "incomplete"},
        {"stage": "inventory", "schema_version": 1, "status": []},
        {"stage": "inventory", "schema_version": 1, "status": "completed", "source": ""},
    ],
)
def test_malformed_metadata_is_actionable(collection, invalid):
    config, inventory = collection
    (inventory / "run.json").write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        similarity.propose_similar(config, inventory)
    assert not config.runs.exists()


@pytest.mark.parametrize(
    "change",
    ["nonobject", "missing_hash", "bad_hash", "bad_path", "missing_kind", "duplicate_path"],
)
def test_malformed_inventory_rows_fail_before_outputs(collection, change):
    config, inventory = collection
    records = rows(inventory / "manifest.jsonl")
    image = next(row for row in records if row["source_path"] == "a.png")
    if change == "nonobject":
        records.append([])
    elif change == "missing_hash":
        image["sha256"] = None
    elif change == "bad_hash":
        image["sha256"] = "not-a-digest"
    elif change == "bad_path":
        image["source_path"] = "../outside.png"
    elif change == "duplicate_path":
        records.append(dict(image))
    else:
        image.pop("kind")
    rewrite_manifest(inventory, records)
    with pytest.raises(ValueError, match="inventory"):
        similarity.propose_similar(config, inventory)
    assert not config.runs.exists()


def test_publication_failure_retains_completed_staging(collection, monkeypatch):
    config, inventory = collection

    def fail_publish(*args):
        raise PermissionError("simulated publish failure")

    monkeypatch.setattr(similarity, "publish_directory", fail_publish)
    with pytest.raises(PermissionError, match="publish failure"):
        similarity.propose_similar(config, inventory)
    pending = list(config.runs.iterdir())
    assert len(pending) == 1 and pending[0].name.startswith(".pending-")
    assert len(rows(pending[0] / "pairs.jsonl")) == 1
    assert (pending[0] / "run.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_junction_introduced_since_inventory_is_not_followed(collection):
    config, _ = collection
    nested = config.source / "nested"
    nested.mkdir()
    artwork(52).save(nested / "new.png")
    inventory, _ = run_scan(replace(config, runs=config.runs.parent / "junction-inventory"))
    relocated = config.source / "relocated"
    nested.rename(relocated)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(nested), str(relocated)],
        check=True,
        capture_output=True,
    )
    try:
        assert nested.is_junction()
        result, summary = similarity.propose_similar(config, inventory)
        record = next(
            row for row in rows(result / "images.jsonl") if row["source_path"].startswith("nested/")
        )
        assert summary["errors"] == 1
        assert record["decision"] == "error"
        assert "link after inventory" in record["error"]
        assert (relocated / "new.png").is_file()
    finally:
        nested.rmdir()


def test_inventory_tampering_is_rejected(collection):
    config, inventory = collection
    with (inventory / "manifest.jsonl").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        read_inventory(inventory)
    assert not config.runs.exists()


def test_cli_exit_status_and_no_tagging_dependencies(collection, tmp_path, capsys):
    config, inventory = collection
    config_file = tmp_path / "settings.toml"
    config_file.write_text(
        f'schema_version = 1\n[paths]\nruns = "{config.runs.as_posix()}"\n', encoding="utf-8"
    )
    args = ["similarity", "--config", str(config_file), "--inventory", str(inventory)]
    script = """
import importlib.abc
import sys
class BlockTagging(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"numpy", "onnxruntime", "huggingface_hub"}:
            raise AssertionError("unexpected tagging dependency: " + fullname)
sys.meta_path.insert(0, BlockTagging())
from image_dataset_train.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, *args], capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert "pairs to review: 1" in completed.stdout
    (config.source / "a.png").write_bytes(b"changed")
    assert main(args) == 1
    assert "errors: 1" in capsys.readouterr().out
    (inventory / "run.json").write_text("null")
    assert main(args) == 2
    assert "inventory" in capsys.readouterr().err.lower()
