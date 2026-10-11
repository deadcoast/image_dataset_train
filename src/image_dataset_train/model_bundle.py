"""Pinned WD model artifacts. This is the only stage that accesses the network."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from image_dataset_train.inventory import file_sha256


@dataclass(frozen=True)
class ModelSpec:
    repo: str
    revision: str
    suggested_general_threshold: float


# Publisher revisions checked 2026-10-11. These are WD-compatible ONNX models only.
MODELS = {
    "swinv2-v3": ModelSpec(
        "SmilingWolf/wd-swinv2-tagger-v3", "627aef95638667ddcaa3ac8ae625e88ea5b02f51", 0.35
    ),
    "vit-large-v3": ModelSpec(
        "SmilingWolf/wd-vit-large-tagger-v3", "ae469aa2e4706a3af08d3673cf73a11d1add314c", 0.35
    ),
    "eva02-large-v3": ModelSpec(
        "SmilingWolf/wd-eva02-large-tagger-v3", "b25b82a03f7282e41aa2f257a52c7583b710bd1c", 0.5296
    ),
}


@dataclass(frozen=True)
class Label:
    index: int
    name: str
    category: int


def read_labels(path: Path) -> list[Label]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"name", "category"}.issubset(reader.fieldnames or []):
            raise ValueError("label CSV requires name and category columns")
        labels = []
        names = set()
        for index, row in enumerate(reader):
            name = row["name"]
            if not name or name in names or any(c in name for c in (",", "\n", "\r")):
                raise ValueError(f"empty, duplicate, or invalid label at CSV row {index + 2}")
            try:
                category = int(row["category"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid category at CSV row {index + 2}") from exc
            if category not in {0, 4, 9}:
                raise ValueError(f"unsupported WD category {category}")
            names.add(name)
            labels.append(Label(index, name, category))
    if not labels or not any(label.category == 0 for label in labels):
        raise ValueError("label CSV must contain general tags")
    return labels


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def bundle_path(root: Path, model: str, revision: str | None = None) -> Path:
    if model not in MODELS:
        raise ValueError(f"unknown WD model: {model}")
    revision = revision or MODELS[model].revision
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("model revision must be a full 40-character commit hash")
    return root / model / revision


def fetch_bundle(root: Path, model: str, revision: str | None = None) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError("install the tag-cpu or tag-gpu extra to fetch models") from exc
    destination = bundle_path(root, model, revision)
    if (destination / "model.json").exists():
        load_bundle(destination)
        return destination
    spec = MODELS[model]
    revision = revision or spec.revision
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for filename in ("model.onnx", "selected_tags.csv"):
        path = Path(hf_hub_download(
            repo_id=spec.repo, filename=filename, revision=revision,
            local_dir=destination, token=False,
        ))
        hashes[filename] = file_sha256(path)
    labels = read_labels(destination / "selected_tags.csv")
    identity = {"repo": spec.repo, "revision": revision, "files": hashes}
    atomic_json(destination / "model.json", {
        "schema_version": 1, "family": "wd-v3", "model": model,
        **identity, "artifact_id": fingerprint(identity), "label_count": len(labels),
    })
    return destination


@dataclass(frozen=True)
class ModelBundle:
    directory: Path
    metadata: dict
    labels: list[Label]


def load_bundle(directory: Path) -> ModelBundle:
    path = directory / "model.json"
    if not path.is_file():
        raise ValueError(f"model bundle missing; run fetch-model first: {directory}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 1 or metadata.get("family") != "wd-v3":
        raise ValueError("unsupported model bundle schema/family")
    hashes = {name: file_sha256(directory / name) for name in ("model.onnx", "selected_tags.csv")}
    if hashes != metadata.get("files"):
        raise ValueError("model bundle hash mismatch; model or labels have changed")
    identity = {"repo": metadata.get("repo"), "revision": metadata.get("revision"), "files": hashes}
    if fingerprint(identity) != metadata.get("artifact_id"):
        raise ValueError("model bundle identity mismatch")
    labels = read_labels(directory / "selected_tags.csv")
    if len(labels) != metadata.get("label_count"):
        raise ValueError("model bundle label count mismatch")
    return ModelBundle(directory, metadata, labels)
