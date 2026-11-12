"""Explain saved review changes since an exact immutable QA report."""

from __future__ import annotations

import hashlib
from pathlib import Path

from image_dataset_train.annotations import annotation_fields
from image_dataset_train.exporting import _validate_group_artifacts
from image_dataset_train.qa import _verify_pilot_selection
from image_dataset_train.review_history import (
    _absolute,
    _bytes,
    _changes,
    _compatible,
    _digest,
    _json,
    _loaded,
    _relative,
    _unlinked,
    validate_review_state,
)
from image_dataset_train.reviews import ELIGIBLE, ReviewConflict, _groups, _identity, _image_key


class _Metadata:
    def __init__(self):
        self.hashes = {}

    def read(self, path, expected=None):
        path = Path(path).absolute()
        raw = _bytes(path)
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != _digest(expected):
            raise ValueError(f"Review snapshot metadata hash mismatch: {path}")
        if self.hashes.setdefault(str(path), digest) != digest:
            raise ReviewConflict("Review snapshot metadata changed while inspecting")
        return raw

    def checked(self, root, meta, name):
        files = meta.get("files")
        if not isinstance(files, dict) or name not in files:
            raise ValueError(f"Review snapshot is missing declared evidence: {name}")
        return self.read(root / _relative(name), _digest(files[name]))

    def verify(self):
        for path, digest in self.hashes.items():
            if hashlib.sha256(_bytes(Path(path))).hexdigest() != digest:
                raise ReviewConflict("Review snapshot metadata changed while inspecting")


def _directory(value):
    path = Path(value).absolute()
    _unlinked(path)
    path = path.resolve(strict=True)
    if not path.is_dir() or path.name.startswith(".pending-"):
        raise ValueError("Review changes require a published artifact directory")
    return path


def _metadata(raw, stages):
    meta = _json(raw)
    if (
        not isinstance(meta, dict)
        or type(meta.get("schema_version")) is not int
        or meta.get("schema_version") != 1
        or not isinstance(meta.get("stage"), str)
        or meta.get("stage") not in stages
        or not isinstance(meta.get("status"), str)
        or meta.get("status") not in {"completed", "completed_with_errors"}
    ):
        raise ValueError("Invalid published review snapshot metadata")
    return meta


def _rows(raw):
    values = [_json(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in values):
        raise ValueError("Review snapshot rows must be objects")
    return values


def _identities(rows):
    identities = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Review snapshot members must be objects")
        path, digest = _relative(row.get("source_path")), _digest(row.get("sha256"))
        if path in identities:
            raise ValueError("Review snapshot contains repeated source paths")
        identities[path] = digest
    return identities


def _group_members(groups, context):
    members, identifiers = [], set()
    for group in groups:
        rows = group.get("members")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Snapshot groups must contain image members")
        identities = _identities(rows)
        identifier = _digest(group.get("group_id"))
        if identifier in identifiers or identifier != _identity(
            sorted(map(list, identities.items()))
        ):
            raise ValueError("Snapshot group identity or membership is invalid")
        identifiers.add(identifier)
        members.extend(rows)
    if _identities(members) != {
        path: row["sha256"]
        for path, row in context.rows.items()
        if row["kind"] == "image" and row["decision"] in ELIGIBLE
    }:
        raise ValueError("Snapshot groups do not match their selected inventory")
    return members


def _join(context, meta):
    if (
        Path(_absolute(meta.get("source"))) != context.source
        or Path(_absolute(meta.get("similarity_run"))) != context.run
        or Path(_absolute(meta.get("inventory_run"))) != context.inventory
        or meta.get("inventory_manifest_sha256") != context.inventory_hash
    ):
        raise ValueError("Report snapshot differs from the selected review inventory or source")


def _captured_groups(context, meta, groups, artifacts, captured):
    """Reconcile the saved-review projection, before any preparation policy decisions."""
    if meta.get("preparation_policy"):
        base_meta = _metadata(artifacts["base-groups-run.json"], {"groups"})
        _join(context, base_meta)
        if (
            base_meta.get("preparation_policy")
            or type(base_meta.get("review_revision")) is not int
            or base_meta["review_revision"] != captured["revision"]
        ):
            raise ValueError("Prepared groups have inconsistent base review lineage")
        groups = _rows(artifacts["base-groups.jsonl"])
    members = _group_members(groups, context)
    expected, _ = _groups(context, captured)
    if (
        sorted(sorted(member["source_path"] for member in group["members"]) for group in groups)
        != expected
    ):
        raise ValueError("Frozen group membership differs from the captured review state")
    for member in members:
        saved = captured["images"].get(_image_key(member), {})
        expected_fields = {
            "review_decision": saved.get("decision", "unreviewed"),
            "reason": saved.get("reason", ""),
            "caption_override": saved.get("caption_override"),
            "caption_rule_version": saved.get("caption_rule_version"),
            "annotation_version": saved.get("annotation_version"),
            "annotation_reason": saved.get("annotation_reason"),
            "subset_origin": saved.get("subset_origin"),
            **annotation_fields(saved),
        }
        actual_fields = {
            **{field: member.get(field) for field in expected_fields},
            "reason": member.get("reason", ""),
            **annotation_fields(member),
        }
        if _identity(expected_fields) != _identity(actual_fields):
            raise ValueError("Frozen group annotations differ from the captured review state")


def _snapshot(context, report, reader):
    report_meta = _metadata(reader.read(report / "run.json"), {"qa"})
    if (
        Path(_absolute(report_meta.get("source"))) != context.source
        or Path(_absolute(report_meta.get("similarity_run"))) != context.run
    ):
        raise ValueError("QA report differs from the selected review source or similarity run")
    data = {
        "entries": _rows(reader.checked(report, report_meta, "entries.jsonl")),
        "summary": _json(reader.checked(report, report_meta, "summary.json")),
        "coverage": _json(reader.checked(report, report_meta, "coverage.json")),
    }
    if not isinstance(data["summary"], dict) or not isinstance(data["coverage"], dict):
        raise ValueError("Invalid QA summary or coverage metadata")
    _verify_pilot_selection(report_meta, data)
    members = _identities(data["entries"])
    input_run = _directory(_absolute(report_meta.get("input_run")))
    input_meta = _metadata(
        reader.read(input_run / "run.json", _digest(report_meta.get("input_run_sha256"))),
        {"groups", "export"},
    )
    if Path(_absolute(input_meta.get("source"))) != context.source:
        raise ValueError("QA input snapshot source differs from the selected source")
    if input_meta["stage"] == "groups":
        group_meta = input_meta
        names = ["groups.jsonl", "reviews.json", "summary.json"]
        if group_meta.get("preparation_policy"):
            names += ["preparation.json", "base-groups.jsonl", "base-groups-run.json"]
        artifacts = {name: reader.checked(input_run, input_meta, name) for name in names}
        for name, raw in artifacts.items():
            _rows(raw) if name.endswith(".jsonl") else _json(raw)
        _group_members(_rows(artifacts["groups.jsonl"]), context)
        # Reuse the group/preparation metadata contract; it does not read source media.
        _, groups, _ = _validate_group_artifacts(group_meta, artifacts, require_reviewed=False)
        input_members = _identities(member for group in groups for member in group["members"])
        captured_raw = artifacts["reviews.json"]
        group_summary = _json(artifacts["summary.json"])
    else:
        group_meta = _metadata(
            reader.checked(input_run, input_meta, "provenance/groups-run.json"), {"groups"}
        )
        captured_raw = reader.checked(input_run, input_meta, "provenance/reviews.json")
        # Captured review bytes must also match the frozen group metadata, not only the export.
        files = group_meta.get("files")
        if not isinstance(files, dict) or hashlib.sha256(captured_raw).hexdigest() != _digest(
            files.get("reviews.json")
        ):
            raise ValueError("Export captured reviews differ from the frozen group snapshot")
        group_raw = reader.checked(input_run, input_meta, "provenance/groups.jsonl")
        summary_raw = reader.checked(input_run, input_meta, "provenance/summary.json")
        for name, raw in [("groups.jsonl", group_raw), ("summary.json", summary_raw)]:
            if hashlib.sha256(raw).hexdigest() != _digest(files.get(name)):
                raise ValueError("Export group evidence differs from its frozen metadata")
        groups = _rows(group_raw)
        group_rows = _group_members(groups, context)
        manifest = _rows(reader.checked(input_run, input_meta, "manifest.jsonl"))
        input_members = _identities(manifest)
        if input_members != _identities(
            row for row in group_rows if row.get("review_decision") == "include"
        ):
            raise ValueError("Export membership differs from its captured groups")
        group_summary = _json(summary_raw)
        artifacts = {
            "groups.jsonl": group_raw,
            "summary.json": summary_raw,
            "reviews.json": captured_raw,
        }
        if group_meta.get("preparation_policy"):
            from image_dataset_train.preparation_policy import verify_preparation

            for name in ("preparation.json", "base-groups.jsonl", "base-groups-run.json"):
                raw = reader.checked(input_run, input_meta, "provenance/" + name)
                if hashlib.sha256(raw).hexdigest() != _digest(files.get(name)):
                    raise ValueError("Export preparation evidence differs from frozen groups")
                _rows(raw) if name.endswith(".jsonl") else _json(raw)
                artifacts[name] = raw
            verify_preparation(group_meta, groups, artifacts)
        if type(input_meta.get("review_revision")) is not int or input_meta.get(
            "review_revision"
        ) != group_meta.get("review_revision"):
            raise ValueError("Export and captured groups have different review revisions")
    _join(context, group_meta)
    captured = _json(captured_raw)
    validate_review_state(captured, context)
    _captured_groups(context, group_meta, groups, artifacts, captured)
    revision = captured["revision"]
    if (
        type(group_meta.get("review_revision")) is not int
        or group_meta["review_revision"] != revision
        or not isinstance(group_summary, dict)
        or type(group_summary.get("review_revision")) is not int
        or group_summary.get("review_revision") != revision
        or type(data["summary"].get("review_revision")) is not int
        or data["summary"].get("review_revision") != revision
        or type(data["summary"].get("images")) is not int
        or data["summary"]["images"] != len(members)
        or data["summary"].get("split_state")
        != ("published" if input_meta["stage"] == "export" else "preview")
        or members != input_members
    ):
        raise ValueError("QA membership or captured review revisions are inconsistent")
    return captured, members, input_run, input_meta["stage"]


def _difference(context, report_members, kind, key, before, after):
    record = after if after is not None else before
    fields = (
        ("source_path", "sha256")
        if kind == "images"
        else ("left_source_path", "left_sha256", "right_source_path", "right_sha256")
    )
    identity = {field: record[field] for field in fields}
    prefixes = ("",) if kind == "images" else ("left_", "right_")
    matches = [
        report_members.get(record[prefix + "source_path"]) == record[prefix + "sha256"]
        for prefix in prefixes
    ]
    membership = (
        "in_report" if all(matches) else "partial_report" if any(matches) else "outside_report"
    )
    return {
        "kind": kind,
        "key": key,
        "identity": identity,
        "before": before,
        "after": after,
        "changes": _changes(before, after),
        "report_membership": membership,
        "inventory_compatible": _compatible(context, kind, key, record),
    }


def inspect_review_changes(config, similarity_run, report, *, limit=20, offset=0, kind=None):
    """Compare saved records, without reading source media or claiming export effects."""
    if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
        raise ValueError("Use a limit from 1 to 200 and a nonnegative offset")
    if kind not in (None, "images", "pairs"):
        raise ValueError("Review changes kind must be images or pairs")
    report = _directory(report)
    context, store, context_hashes, current, _, current_digest = _loaded(config, similarity_run)
    reader = _Metadata()
    captured, report_members, input_run, input_stage = _snapshot(context, report, reader)
    revision = captured["revision"]
    if current["revision"] < revision or current["history"][:revision] != captured["history"]:
        raise ValueError("Current review history is truncated or diverges from the report snapshot")
    differences = []
    for target in ("images", "pairs"):
        for key in sorted(captured[target].keys() | current[target].keys()):
            before, after = captured[target].get(key), current[target].get(key)
            if before != after:
                differences.append(_difference(context, report_members, target, key, before, after))
    differences.sort(key=lambda row: (row["kind"], tuple(row["identity"].values()), row["key"]))
    counts = {
        name: 0
        for name in (
            "images",
            "pairs",
            "in_report",
            "outside_report",
            "partial_report",
            "incompatible",
        )
    }
    for difference in differences:
        counts[difference["kind"]] += 1
        counts[difference["report_membership"]] += 1
        counts["incompatible"] += not difference["inventory_compatible"]
    filtered = [row for row in differences if kind is None or row["kind"] == kind]
    delta = current["revision"] - revision
    # Re-read all compared inputs, including live review bytes, before returning a view.
    final_context, final_store, final_hashes, final_current, _, final_digest = _loaded(
        config, similarity_run
    )
    if (
        final_context.source != context.source
        or final_store.path != store.path
        or final_hashes != context_hashes
        or final_current != current
        or final_digest != current_digest
    ):
        raise ReviewConflict("Review context or current state changed while inspecting")
    reader.verify()
    # The selected context/store may advance during the immutable metadata recheck.
    if any(
        hashlib.sha256(_bytes(Path(path))).hexdigest() != digest
        for path, digest in context_hashes.items()
    ):
        raise ReviewConflict("Review context changed while inspecting snapshot metadata")
    final_raw = _bytes(store.path) if store.path.exists() else None
    if (hashlib.sha256(final_raw).hexdigest() if final_raw is not None else None) != current_digest:
        raise ReviewConflict("Current review state changed while inspecting snapshot metadata")
    return {
        "state": "changed" if differences else "history_only" if delta else "unchanged",
        "snapshot_revision": revision,
        "current_revision": current["revision"],
        "history_delta_count": delta,
        "net_change_count": len(differences),
        "counts": counts,
        "differences": filtered[offset : offset + limit],
        "filtered_count": len(filtered),
        "kind": kind,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(filtered) else None,
        "report": str(report),
        "report_sha256": reader.hashes[str(report / "run.json")],
        "input_run": str(input_run),
        "input_stage": input_stage,
        "similarity_run": str(context.run),
        "review_file": str(store.path),
        "source": str(context.source),
        "source_revalidated": False,
        "metadata_verified": True,
        "metadata_sha256": {**context_hashes, **reader.hashes},
        "current_store_sha256": current_digest,
    }
