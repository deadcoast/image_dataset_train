"""Verified occurrence-level differences between immutable dataset snapshots."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from image_dataset_train.annotations import annotation_fields
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.exporting import (
    _checked,
    _load_groups,
    _path,
    _published,
    _rows,
    verify_export,
)
from image_dataset_train.implementation import implementation_identity
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reviews import _separate


def _identity(row: dict) -> tuple[str, str]:
    return row["source_path"], row["sha256"]


def _key(row: dict) -> dict:
    return {"source_path": row["source_path"], "sha256": row["sha256"]}


def _normalize(row: dict, kind: str) -> dict:
    exported = kind == "export"
    override = row.get("caption_override")
    caption = (
        {
            "text": row["caption"],
            "origin": row["caption_origin"],
            "source_text": row.get("source_caption", row["caption"]),
            "transforms": row.get("caption_transforms", []),
        }
        if exported
        else {
            "text": override,
            "origin": (
                {"kind": "saved_override", "rule_version": row.get("caption_rule_version")}
                if override is not None
                else None
            ),
        }
    )
    return {
        **_key(row),
        "group_id": row["group_id"],
        "caption": caption,
        "annotations": {**annotation_fields(row), "subset_origin": row.get("subset_origin")},
        "decision": {
            "value": row["review_decision"],
            "origin": row.get("decision_origin"),
            "reason": row.get("reason"),
            "duplicate_of": row.get("prepared_duplicate_of"),
        },
        "split": row["split"] if exported else None,
        "media": (
            {
                "sha256": row["image_sha256"],
                "transform": row.get("image_transform", "copy-v1"),
                "width": row["width"],
                "height": row["height"],
            }
            if exported
            else None
        ),
    }


def _snapshot(directory: Path) -> tuple[dict, bytes]:
    directory = directory.absolute()
    # Check links before canonicalization, including the supplied artifact root.
    checksum = file_sha256(_path(directory, "run.json"))
    directory = directory.resolve(strict=True)
    meta = _published(directory, {"groups", "export"})
    source = meta.get("source")
    if not isinstance(source, str) or not Path(source).is_absolute():
        raise ValueError("Snapshot is missing its absolute source identity")
    kind = meta["stage"]
    if kind == "export":
        verify_export(directory)
        rows = _rows(_checked(directory, "manifest.jsonl", meta["files"]["manifest.jsonl"]))
    else:
        _, groups, _ = _load_groups(directory, require_reviewed=False)
        rows = [
            {**member, "group_id": group["group_id"]}
            for group in groups
            for member in group["members"]
        ]
    normalized = sorted((_normalize(row, kind) for row in rows), key=_identity)
    for row in normalized:
        path = row["source_path"]
        relative = PurePosixPath(path)
        if (
            not path
            or not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or any(part.endswith((" ", ".")) for part in relative.parts)
            or "\\" in path
            or ":" in path
            or "\0" in path
            or relative.as_posix() != path
        ):
            raise ValueError("Unsafe snapshot source path")
    if len({row["source_path"] for row in normalized}) != len(normalized):
        raise ValueError("Snapshot contains repeated source paths")
    captured = _checked(directory, "run.json", checksum)
    return {
        "kind": kind,
        "source": str(Path(source).resolve()),
        "input": {
            "run": str(directory),
            "run_sha256": checksum,
            "status": meta["status"],
            "verification": "full_export" if kind == "export" else "group_snapshot",
        },
        "members": normalized,
    }, captured


def _compare(before: dict, after: dict) -> dict:
    if before["kind"] != after["kind"]:
        raise ValueError(
            "Compare snapshots of the same kind; groups and exports have different scopes"
        )
    if before["source"] != after["source"]:
        raise ValueError("Snapshot source identities differ")
    left = {_identity(row): row for row in before["members"]}
    right = {_identity(row): row for row in after["members"]}
    common = sorted(left.keys() & right.keys())
    changes = {
        "added": [right[key] for key in sorted(right.keys() - left.keys())],
        "removed": [left[key] for key in sorted(left.keys() - right.keys())],
    }
    left_paths = {row["source_path"]: row["sha256"] for row in left.values()}
    right_paths = {row["source_path"]: row["sha256"] for row in right.values()}
    changes["changed_content"] = [
        {"source_path": path, "before_sha256": left_paths[path], "after_sha256": right_paths[path]}
        for path in sorted(left_paths.keys() & right_paths.keys())
        if left_paths[path] != right_paths[path]
    ]
    changes["caption_changes"] = [
        {**_key(left[key]), "before": left[key]["caption"], "after": right[key]["caption"]}
        for key in common
        if left[key]["caption"]["text"] != right[key]["caption"]["text"]
    ]
    caption_provenance = [
        {
            key: {name: value for name, value in row["caption"].items() if name != "text"}
            for key, row in snapshot.items()
        }
        for snapshot in (left, right)
    ]
    changes["caption_provenance_changes"] = [
        {
            **_key(left[key]),
            "before": caption_provenance[0][key],
            "after": caption_provenance[1][key],
        }
        for key in common
        if caption_provenance[0][key] != caption_provenance[1][key]
    ]
    for field, category in (
        ("annotations", "annotation_changes"),
        ("decision", "decision_changes"),
        ("group_id", "group_changes"),
        ("split", "split_moves"),
        ("media", "media_changes"),
    ):
        changes[category] = [
            {**_key(left[key]), "before": left[key][field], "after": right[key][field]}
            for key in common
            if left[key][field] != right[key][field]
        ]
    aliases = []
    for snapshot in (left, right):
        by_hash = defaultdict(list)
        for row in snapshot.values():
            by_hash[row["sha256"]].append(row["source_path"])
        aliases.append({sha: sorted(paths) for sha, paths in by_hash.items()})
    changes["alias_changes"] = [
        {"sha256": sha, "before": aliases[0].get(sha, []), "after": aliases[1].get(sha, [])}
        for sha in sorted(aliases[0].keys() | aliases[1].keys())
        if aliases[0].get(sha, []) != aliases[1].get(sha, [])
    ]
    for destination, origin, category, destination_name, origin_name in (
        (right, left, "group_merges", "after_group_id", "before_group_ids"),
        (left, right, "group_splits", "before_group_id", "after_group_ids"),
    ):
        related = defaultdict(lambda: defaultdict(list))
        for key in common:
            related[destination[key]["group_id"]][origin[key]["group_id"]].append(key)
        changes[category] = [
            {
                destination_name: group,
                origin_name: sorted(previous),
                "occurrences": [
                    _key(destination[key])
                    for key in sorted(key for keys in previous.values() for key in keys)
                ],
            }
            for group, previous in sorted(related.items())
            if len(previous) > 1
        ]
    return {
        "schema_version": 1,
        "stage": "snapshot_comparison",
        "kind": before["kind"],
        "source": before["source"],
        "inputs": {"before": before["input"], "after": after["input"]},
        "availability": {
            "effective_captions": before["kind"] == "export",
            "exported_splits": before["kind"] == "export",
            "source_revalidated": False,
        },
        "summary": {
            "before_occurrences": len(left),
            "after_occurrences": len(right),
            "before_unique_contents": len(aliases[0]),
            "after_unique_contents": len(aliases[1]),
            "before_groups": len({row["group_id"] for row in left.values()}),
            "after_groups": len({row["group_id"] for row in right.values()}),
            "common_occurrences": len(common),
            **{name: len(items) for name, items in changes.items()},
        },
        "changed": any(changes.values()),
        "changes": changes,
    }


def compare_snapshots(before: Path, after: Path) -> dict:
    """Verify and compare frozen inputs without reading original image/caption bytes."""
    left, _ = _snapshot(before)
    right, _ = _snapshot(after)
    return _compare(left, right)


def publish_comparison(before: Path, after: Path, *, output_root: Path) -> tuple[Path, dict]:
    """Publish a self-contained comparison receipt without copying training media."""
    left, left_meta = _snapshot(before)
    right, right_meta = _snapshot(after)
    result = _compare(left, right)
    root = output_root.absolute()
    _path(root, "comparison-location-check")
    root = root.resolve()
    _separate(Path(result["source"]), root)
    if any(root.is_relative_to(Path(value["run"])) for value in result["inputs"].values()):
        raise ValueError("Comparison output must not be inside either input snapshot")
    root.mkdir(parents=True, exist_ok=True)
    pending = Path(tempfile.mkdtemp(prefix=".pending-comparison-", dir=root))
    atomic_json(pending / "comparison.json", result)
    for name, snapshot, metadata in (("before", left, left_meta), ("after", right, right_meta)):
        atomic_json(pending / f"{name}-snapshot.json", snapshot)
        (pending / f"{name}-run.json").write_bytes(metadata)
    identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-comparison-" + uuid4().hex[:8]
    atomic_json(
        pending / "run.json",
        {
            "schema_version": 1,
            "stage": "snapshot_comparison",
            "status": "completed",
            "run_id": identifier,
            "created_at": datetime.now(UTC).isoformat(),
            "source": result["source"],
            "inputs": result["inputs"],
            "implementation": implementation_identity(),
            "files": {path.name: file_sha256(path) for path in sorted(pending.iterdir())},
        },
    )
    destination = root / identifier
    publish_directory(pending, destination)
    return destination, result


def read_comparison(directory: Path) -> dict:
    """Check the published receipt and replay its differences from captured records."""
    directory = directory.absolute()
    meta = _published(directory, {"snapshot_comparison"})
    files = meta.get("files", {})
    required = {
        "comparison.json",
        "before-snapshot.json",
        "after-snapshot.json",
        "before-run.json",
        "after-run.json",
    }
    if set(files) != required:
        raise ValueError("Comparison receipt has missing or unrecognized artifacts")
    raw = {name: _checked(directory, name, files[name]) for name in required}
    snapshots = [json.loads(raw[f"{name}-snapshot.json"]) for name in ("before", "after")]
    result = json.loads(raw["comparison.json"])
    if (
        result != _compare(*snapshots)
        or result["inputs"] != meta["inputs"]
        or result["source"] != meta["source"]
    ):
        raise ValueError("Comparison receipt differs from its captured snapshot records")
    for name in ("before", "after"):
        if (
            hashlib.sha256(raw[f"{name}-run.json"]).hexdigest()
            != result["inputs"][name]["run_sha256"]
        ):
            raise ValueError("Comparison input metadata checksum mismatch")
    return result
