"""Atomic score vectors keyed by input bytes and the inference contract."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from image_dataset_train.score_validation import validate_scores


def score_checksum(scores: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(scores, dtype="<f4").tobytes()).hexdigest()


class ScoreCache:
    def __init__(self, root: Path, namespace: str, label_count: int):
        if (
            not isinstance(namespace, str)
            or not namespace
            or namespace in {".", ".."}
            or any(c in namespace for c in "/\\:")
            or namespace.rstrip(". ") != namespace
            or any(ord(c) < 32 for c in namespace)
        ):
            raise ValueError("invalid score cache namespace")
        if type(label_count) is not int or not 1 <= label_count <= 1_000_000:
            raise ValueError("invalid score cache label count")
        self.directory = root / namespace
        self.label_count = label_count

    @staticmethod
    def _unlinked(path: Path) -> None:
        for part in (path.absolute(), *path.absolute().parents):
            if part.is_symlink() or part.is_junction():
                raise ValueError(f"linked score cache paths are not supported: {path}")

    def path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid source SHA256")
        return self.directory / digest[:2] / f"{digest}.npz"

    def _load(self, digest: str) -> tuple[np.ndarray, str] | None:
        path = self.path(digest)
        self._unlinked(path)
        try:
            before = path.stat()
        except FileNotFoundError:
            return None
        # Cache vectors are small, fixed-label numeric records. Bound the compressed
        # input and all expanded members before NumPy can allocate from their headers.
        expanded_limit = self.label_count * 8 + 65_536
        stored_limit = expanded_limit + 65_536
        if not stat.S_ISREG(before.st_mode) or before.st_size > stored_limit:
            raise ValueError("score cache is not a bounded regular file")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                before.st_dev,
                before.st_ino,
            ):
                raise ValueError("score cache changed while opening")
            raw = stream.read(stored_limit + 1)
        self._unlinked(path)
        after = path.stat()
        if len(raw) > stored_limit or (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ):
            raise ValueError("score cache changed during inspection")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if (
                len(members) != 3
                or {member.filename for member in members}
                != {"scores.npy", "sha256.npy", "checksum.npy"}
                or sum(member.file_size for member in members) > expanded_limit
                or any(member.flag_bits & 1 for member in members)
            ):
                raise ValueError("invalid or oversized score cache archive")
            for member in members:
                with archive.open(member) as stream:
                    version = np.lib.format.read_magic(stream)
                    reader = {
                        (1, 0): np.lib.format.read_array_header_1_0,
                        (2, 0): np.lib.format.read_array_header_2_0,
                    }.get(version)
                    if reader is None:
                        raise ValueError("unsupported score cache array format")
                    shape, _, dtype = reader(stream)
                    if member.filename == "scores.npy":
                        valid = (
                            shape == (self.label_count,)
                            and dtype.kind == "f"
                            and dtype.itemsize <= 8
                        )
                        payload_bytes = self.label_count * dtype.itemsize
                    else:
                        valid = shape == () and dtype.kind in {"S", "U"} and dtype.itemsize <= 256
                        payload_bytes = dtype.itemsize
                    if not valid or member.file_size != stream.tell() + payload_bytes:
                        raise ValueError(
                            "score cache array shape/type/size does not match its contract"
                        )
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            scores = archive["scores"]
            validate_scores(scores, self.label_count)
            if str(archive["sha256"]) != digest or str(archive["checksum"]) != score_checksum(
                scores
            ):
                raise ValueError("score cache checksum/identity mismatch")
        return scores, hashlib.sha256(raw).hexdigest()

    def inspect(self, digest: str) -> dict:
        """Verify one expected entry without repairing, logging, or creating files."""
        path = self.path(digest)
        result = {"path": str(path), "sha256": digest}
        try:
            loaded = self._load(digest)
            if loaded is None:
                return {**result, "status": "missing"}
            scores, archive_hash = loaded
            return {
                **result,
                "status": "valid",
                "cache_sha256": archive_hash,
                "score_checksum": score_checksum(scores),
                "label_count": self.label_count,
            }
        except Exception as exc:
            return {
                **result,
                "status": "invalid",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }

    def get(self, digest: str, *, repair: bool = False) -> np.ndarray | None:
        path = self.path(digest)
        try:
            loaded = self._load(digest)
            return None if loaded is None else loaded[0]
        except Exception as exc:
            if repair:
                from image_dataset_train.diagnostics import EventLog
                from image_dataset_train.doctor import preserve

                self._unlinked(path)
                home = self.directory.parent.parent
                saved = preserve(path, home, "scores")
                EventLog(home).exception(
                    exc, action="score_cache_repair", preserved=saved, source_sha256=digest
                )
                return None
            raise ValueError(
                f"invalid score cache (preserved for inspection): {path}: {exc}"
            ) from exc

    def put(self, digest: str, scores: np.ndarray) -> Path:
        validate_scores(scores, self.label_count)
        path = self.path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(
                stream,
                scores=np.asarray(scores, dtype=np.float32),
                sha256=digest,
                checksum=score_checksum(scores),
            )
        os.replace(temporary, path)
        return path
