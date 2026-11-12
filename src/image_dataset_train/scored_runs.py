"""Verified, source-independent access to one saved score vector at a time."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath

import numpy as np

from image_dataset_train.exporting import _checked, _path, _rows
from image_dataset_train.model_bundle import Label
from image_dataset_train.score_cache import score_checksum
from image_dataset_train.score_validation import validate_scores


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


class ScoredRun:
    """Load hashed metadata eagerly; validate score bytes only when requested."""

    def __init__(self, run: Path):
        # Check the supplied root before resolving it so a linked run is not hidden
        # by canonicalization; nested artifacts receive the same check on each read.
        self.run = run.absolute()
        raw = _path(self.run, "run.json").read_bytes()
        self.run = self.run.resolve(strict=True)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.metadata = json.loads(raw)
        if (
            not isinstance(self.metadata, dict)
            or type(self.metadata.get("schema_version")) is not int
            or self.metadata["schema_version"] != 1
            or self.metadata.get("stage") not in {"tagging", "recaption"}
            or self.metadata.get("status") not in {"completed", "completed_with_errors"}
            or self.run.name.startswith(".pending-")
        ):
            raise ValueError("Expected a published tagging or recaption run")
        source = self.metadata.get("source")
        if not isinstance(source, str) or not Path(source).is_absolute():
            raise ValueError("Scored run is missing its source identity")
        artifacts = {
            name: _checked(self.run, name, self.metadata.get(key))
            for name, key in (
                ("manifest.jsonl", "manifest_sha256"),
                ("labels.json", "labels_sha256"),
                ("score_index.json", "score_index_sha256"),
            )
        }
        records = json.loads(artifacts["labels.json"])
        if not isinstance(records, list) or not records:
            raise ValueError("Scored run requires a nonempty label index")
        self.labels = []
        names = set()
        for index, record in enumerate(records):
            if (
                not isinstance(record, dict)
                or set(record) != {"index", "name", "category"}
                or type(record["index"]) is not int
                or record["index"] != index
                or type(record["category"]) is not int
                or record["category"] not in {0, 4, 9}
                or not isinstance(record["name"], str)
                or not record["name"]
                or record["name"] in names
            ):
                raise ValueError("Invalid or repeated scored-run label index")
            self.labels.append(Label(**record))
            names.add(record["name"])
        self.index = json.loads(artifacts["score_index.json"])
        if not isinstance(self.index, dict):
            raise ValueError("Scored-run score index must be an object")
        for digest, artifact in self.index.items():
            if (
                not _sha256(digest)
                or not isinstance(artifact, dict)
                or artifact.get("path") != f"scores/{digest}.npy"
                or not _sha256(artifact.get("sha256"))
                or not _sha256(artifact.get("score_checksum"))
            ):
                raise ValueError("Invalid score artifact path or checksum")
        self.rows = _rows(artifacts["manifest.jsonl"])
        paths = set()
        for row in self.rows:
            path = row.get("source_path")
            if not isinstance(path, str) or not path or "\0" in path:
                raise ValueError("Invalid scored image source path")
            relative = PurePosixPath(path)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in path
                or ":" in path
                or relative.as_posix() != path
                or path in paths
            ):
                raise ValueError("Unsafe or repeated scored image source path")
            paths.add(path)
            if row.get("decision") == "tagged" and (
                not _sha256(row.get("sha256")) or row["sha256"] not in self.index
            ):
                raise ValueError("Missing score vector for tagged image")

    def vector(self, digest: str) -> np.ndarray:
        """Read a bounded NPY payload and validate its header before allocating its array."""
        artifact = self.index.get(digest)
        if artifact is None:
            raise ValueError(f"Missing score vector: {digest}")
        # Published vectors are float32. Permit earlier floating formats up to float64,
        # but never trust a file header to request an arbitrarily large allocation.
        limit = len(self.labels) * 8 + 10_256
        with _path(self.run, artifact["path"]).open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Score artifact exceeds its label-count byte limit")
        if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
            raise ValueError(f"score artifact hash mismatch: {digest}")
        stream = io.BytesIO(raw)
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise ValueError("Unsupported saved score array format")
        if (
            shape != (len(self.labels),)
            or not np.issubdtype(dtype, np.floating)
            or dtype.itemsize > 8
            or len(raw) - stream.tell() != len(self.labels) * dtype.itemsize
        ):
            raise ValueError("Invalid saved score array shape, type or payload size")
        vector = np.load(io.BytesIO(raw), allow_pickle=False)
        validate_scores(vector, len(self.labels))
        if score_checksum(vector) != artifact["score_checksum"]:
            raise ValueError("Score vector checksum mismatch")
        return vector
