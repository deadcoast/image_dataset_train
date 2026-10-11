"""Atomic score vectors keyed by input bytes and the inference contract."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np

from image_dataset_train.wd_tagger import validate_scores


def score_checksum(scores: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(scores, dtype="<f4").tobytes()).hexdigest()


class ScoreCache:
    def __init__(self, root: Path, namespace: str, label_count: int):
        self.directory = root / namespace
        self.label_count = label_count

    def path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid source SHA256")
        return self.directory / digest[:2] / f"{digest}.npz"

    def get(self, digest: str) -> np.ndarray | None:
        path = self.path(digest)
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as archive:
                scores = archive["scores"]
                validate_scores(scores, self.label_count)
                if str(archive["sha256"]) != digest or str(archive["checksum"]) != score_checksum(
                    scores
                ):
                    raise ValueError("score cache checksum/identity mismatch")
                return scores
        except Exception as exc:
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
