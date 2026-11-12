from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest

from image_dataset_train.score_cache import ScoreCache, score_checksum

DIGEST = "a" * 64


def test_missing_and_valid_inspection_do_not_write(tmp_path):
    cache = ScoreCache(tmp_path / "cache", "test", 3)
    assert cache.inspect(DIGEST)["status"] == "missing"
    assert not cache.directory.parent.exists()
    scores = np.array([0.1, 0.5, 0.9], dtype=np.float32)
    path = cache.put(DIGEST, scores)
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = cache.inspect(DIGEST)
    assert result["status"] == "valid"
    assert result["score_checksum"] == score_checksum(scores)
    assert len(result["cache_sha256"]) == 64
    np.testing.assert_array_equal(cache.get(DIGEST), scores)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert list(cache.directory.rglob("*")) == [path.parent, path]


@pytest.mark.parametrize("damage", ["identity", "checksum", "nan", "shape", "object"])
def test_invalid_cache_is_preserved_and_matches_inference(tmp_path, damage):
    cache = ScoreCache(tmp_path / "cache", "test", 3)
    scores = np.array([0.1, 0.5, 0.9], dtype=np.float32)
    path = cache.put(DIGEST, scores)
    identity = DIGEST
    checksum = score_checksum(scores)
    if damage == "identity":
        identity = "b" * 64
    elif damage == "checksum":
        checksum = "b" * 64
    elif damage == "nan":
        scores[0] = np.nan
    elif damage == "shape":
        scores = scores[:2]
    else:
        scores = np.array([object(), object(), object()])
    np.savez_compressed(path, scores=scores, sha256=identity, checksum=checksum)
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert cache.inspect(DIGEST)["status"] == "invalid"
    with pytest.raises(ValueError, match="invalid score cache"):
        cache.get(DIGEST)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("damage", ["huge_shape", "expanded", "stored", "extra", "truncated"])
def test_resource_bounds_reject_before_numpy_load(tmp_path, monkeypatch, damage):
    cache = ScoreCache(tmp_path / "cache", "test", 3)
    path = cache.put(DIGEST, np.array([0.1, 0.5, 0.9], dtype=np.float32))
    with zipfile.ZipFile(path) as original:
        members = {name: original.read(name) for name in original.namelist()}
    if damage == "huge_shape":
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(
            stream, {"descr": "<f4", "fortran_order": False, "shape": (10**12,)}
        )
        members["scores.npy"] = stream.getvalue()
    elif damage == "expanded":
        members["scores.npy"] = b"x" * 200_000
    elif damage == "extra":
        members["unexpected.npy"] = b"x"
    elif damage == "truncated":
        members["scores.npy"] = members["scores.npy"][:-1]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    if damage == "stored":
        path.write_bytes(b"x" * 200_000)
    before = path.read_bytes()

    def unexpected_load(*args, **kwargs):
        pytest.fail("NumPy must not load an unbounded or malformed array")

    monkeypatch.setattr(np, "load", unexpected_load)
    assert cache.inspect(DIGEST)["status"] == "invalid"
    assert path.read_bytes() == before


def test_linked_parent_rejected_without_repair(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    cache = ScoreCache(link, "test", 3)
    assert cache.inspect(DIGEST)["status"] == "invalid"
    with pytest.raises(ValueError, match="linked score cache"):
        cache.get(DIGEST, repair=True)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("namespace", ["", "..", "x/y", "x\\y", "C:x", "x.", "x "])
def test_invalid_namespace_cannot_escape_cache_root(tmp_path, namespace):
    with pytest.raises(ValueError, match="namespace"):
        ScoreCache(tmp_path, namespace, 3)
