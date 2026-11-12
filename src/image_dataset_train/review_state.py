"""Pure review record/history validation shared by every persistence consumer.

Artifact compatibility is assessed separately by the history inspector. Validation
never opens source images, historical runs or current inventory metadata.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath

from image_dataset_train.annotations import annotation_fields, annotation_name, label_names

ELIGIBLE = {"candidate", "review", "duplicate"}
PAIR_DECISIONS = {"related", "distinct", "unreviewed"}
PAIR_EVALUATION_SETS = {"calibration", "held_out"}
IMAGE_DECISIONS = {"include", "exclude", "unreviewed"}


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _image_key(row: dict) -> str:
    return _identity([row["source_path"], row["sha256"]])


def image_review_operations(
    *,
    decision=None,
    add_labels=None,
    remove_labels=None,
    clear_labels=False,
    subset=None,
    clear_subset=False,
) -> dict:
    """Canonical explicit operations shared by bulk preview and history replay."""
    if decision is not None and (not isinstance(decision, str) or decision not in IMAGE_DECISIONS):
        raise ValueError("Image decisions are include, exclude, or unreviewed")
    if type(clear_labels) is not bool or type(clear_subset) is not bool:
        raise ValueError("Annotation clear options must be boolean")
    add_labels = label_names(add_labels) if add_labels is not None else None
    remove_labels = label_names(remove_labels) if remove_labels is not None else None
    if set(add_labels or []) & set(remove_labels or []):
        raise ValueError("Cannot add and remove the same label in one edit")
    if subset is not None and clear_subset:
        raise ValueError("Choose a subset or clear it, not both")
    subset = annotation_name(subset) if subset is not None else None
    if (
        decision is None
        and add_labels is None
        and remove_labels is None
        and not clear_labels
        and subset is None
        and not clear_subset
    ):
        raise ValueError("Choose at least one label, subset or inclusion operation")
    return {
        "decision": decision,
        "add_labels": add_labels,
        "remove_labels": remove_labels,
        "clear_labels": clear_labels,
        "subset": subset,
        "clear_subset": clear_subset,
    }


def image_review_proposal(row: dict, current: dict | None, operations: dict, reason: str):
    """Apply reviewed values, preserving unrelated fields and true no-op records.

    A changed reason alone is not an edit. Explicit empty labels/subsets are
    reviewed values, including when a prior record explicitly marked them unreviewed.
    Resetting an already absent inclusion decision preserves its absence.
    """
    proposed = dict(
        current
        or {
            "source_path": row["source_path"],
            "sha256": row["sha256"],
            "decision": "unreviewed",
        }
    )
    changed = annotation_changed = False
    decision = operations["decision"]
    if decision is not None and decision != proposed["decision"]:
        proposed["decision"] = decision
        changed = True
    fields = annotation_fields(proposed)
    if (
        operations["add_labels"] is not None
        or operations["remove_labels"] is not None
        or operations["clear_labels"]
    ):
        labels = set() if operations["clear_labels"] else set(fields["labels"])
        labels.update(operations["add_labels"] or [])
        labels.difference_update(operations["remove_labels"] or [])
        labels = sorted(labels)
        if labels != fields["labels"] or not fields["labels_reviewed"]:
            proposed.update(labels=labels, labels_reviewed=True)
            changed = annotation_changed = True
    if operations["subset"] is not None or operations["clear_subset"]:
        subset = operations["subset"]
        if (
            subset != fields["subset"]
            or not fields["subset_reviewed"]
            or proposed.get("subset_origin") is not None
        ):
            proposed.update(subset=subset, subset_origin=None, subset_reviewed=True)
            changed = annotation_changed = True
    if not changed:
        return current
    proposed["reason"] = reason
    if annotation_changed:
        proposed.update(annotation_version="manual-v1", annotation_reason=reason)
    return proposed


def _text(value, *, empty=False):
    if not isinstance(value, str) or "\0" in value or not empty and not value.strip():
        raise ValueError("Review history requires nonempty text without NUL characters")
    return value


def _digest(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("Review history requires full lowercase SHA256 identities")
    return value


def _relative(value):
    value = _text(value)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or path.as_posix() != value
    ):
        raise ValueError("Unsafe review history source path")
    return value


def _absolute(value):
    if not Path(_text(value)).is_absolute():
        raise ValueError("Review history requires an absolute artifact path")
    return value


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate object keys in review history metadata")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite numeric value in review history metadata: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def _record(kind, key, record):
    _digest(key)
    if not isinstance(record, dict):
        raise ValueError("Review history record must be an object")
    image_fields = {
        "source_path",
        "sha256",
        "decision",
        "reason",
        "caption_override",
        "caption_rule_version",
        "labels",
        "subset",
        "subset_origin",
        "annotation_version",
        "annotation_reason",
        "labels_reviewed",
        "subset_reviewed",
    }
    pair_fields = {
        "left_source_path",
        "right_source_path",
        "left_sha256",
        "right_sha256",
        "decision",
        "reason",
        "evaluation_set",
    }
    if record.keys() - (image_fields if kind == "images" else pair_fields):
        raise ValueError("Unsupported review history record fields")
    if not isinstance(record.get("decision"), str) or record["decision"] not in (
        IMAGE_DECISIONS if kind == "images" else PAIR_DECISIONS
    ):
        raise ValueError("Invalid review history decision")
    _text(record.get("reason"))
    for prefix in ("",) if kind == "images" else ("left_", "right_"):
        _relative(record.get(prefix + "source_path"))
        _digest(record.get(prefix + "sha256"))
    if kind == "pairs":
        if record["left_source_path"] >= record["right_source_path"] or record.get(
            "evaluation_set"
        ) not in (None, *PAIR_EVALUATION_SETS):
            raise ValueError("Invalid historical pair ordering or evaluation set")
        return
    if _image_key(record) != key:
        raise ValueError("Historical image key does not match its content identity")
    if record.get("caption_override") is not None:
        _text(record["caption_override"])
    for field in ("caption_rule_version", "annotation_version", "annotation_reason"):
        if field in record and record[field] is not None:
            _text(record[field])
    for field in ("labels_reviewed", "subset_reviewed"):
        if field in record and type(record[field]) is not bool:
            raise ValueError("Historical annotation review flags must be boolean")
    if "labels" in record and label_names(record["labels"]) != record["labels"]:
        raise ValueError("Historical labels must be canonical names")
    if record.get("subset") is not None and annotation_name(record["subset"]) != record["subset"]:
        raise ValueError("Historical subset must be a canonical name")
    origin = record.get("subset_origin")
    if origin is not None:
        fields = {"kind", "run", "manifest_sha256", "caption_version", "rules_sha256"}
        if (
            not isinstance(origin, dict)
            or origin.keys() != fields
            or origin["kind"] != "caption-rule"
        ):
            raise ValueError("Invalid historical subset provenance")
        _absolute(origin["run"])
        _digest(origin["manifest_sha256"])
        _digest(origin["rules_sha256"])
        _text(origin["caption_version"])


def _changes(before, after):
    left, right = before or {}, after or {}
    return [
        {
            "field": field,
            "before_present": field in left,
            "before": left.get(field),
            "after_present": field in right,
            "after": right.get(field),
        }
        for field in sorted(left.keys() | right.keys())
        if (field in left, left.get(field)) != (field in right, right.get(field))
    ]


def _batch_event(event, revision, replay, pending, seen):
    """Validate one contiguous atomic batch, keeping full membership only once."""
    batch = event.get("batch")
    if not isinstance(batch, dict):
        raise ValueError("Missing batch provenance")
    identifier = _digest(batch.get("id"))
    index, count = batch.get("index"), batch.get("count")
    if type(index) is not int or type(count) is not int or not 0 <= index < count <= 1000:
        raise ValueError("Invalid batch event index or count")
    common = {
        field: event[field]
        for field in ("at", "similarity_run", "reviewer", "reviewer_kind", "reason")
    }
    if pending is None:
        if index != 0 or batch.keys() != {"id", "index", "count", "manifest"}:
            raise ValueError("Batch must begin with its complete selection manifest")
        if identifier in seen:
            raise ValueError("Batch identity cannot be reused")
        manifest = batch["manifest"]
        if not isinstance(manifest, dict) or manifest.keys() != {
            "schema_version",
            "base_revision",
            "plan_sha256",
            "operations",
            "members",
        }:
            raise ValueError("Malformed batch selection manifest")
        if (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or type(manifest["base_revision"]) is not int
            or manifest["base_revision"] != revision - 1
        ):
            raise ValueError("Invalid batch starting revision")
        _digest(manifest["plan_sha256"])
        operations = manifest["operations"]
        if (
            not isinstance(operations, dict)
            or operations.keys()
            != {
                "decision",
                "add_labels",
                "remove_labels",
                "clear_labels",
                "subset",
                "clear_subset",
            }
            or image_review_operations(**operations) != operations
        ):
            raise ValueError("Batch operations must be canonical")
        members = manifest["members"]
        if not isinstance(members, list) or not 1 <= len(members) <= 1000:
            raise ValueError("Invalid batch selection size")
        paths, expected = [], []
        for member in members:
            if not isinstance(member, dict) or member.keys() != {"source_path", "sha256"}:
                raise ValueError("Malformed batch member identity")
            paths.append(_relative(member["source_path"]))
            _digest(member["sha256"])
            key = _image_key(member)
            current = replay["images"].get(key)
            proposed = image_review_proposal(member, current, operations, event["reason"])
            if proposed != current:
                expected.append((key, proposed))
        if paths != sorted(set(paths)):
            raise ValueError("Batch selection must contain unique paths in canonical order")
        if len(expected) != count:
            raise ValueError("Batch event count differs from the inspected changes")
        if identifier != _identity({"manifest": manifest, **common}):
            raise ValueError("Batch identity does not match its operation and selection")
        seen.add(identifier)
        pending = {
            "id": identifier,
            "next_index": 0,
            "count": count,
            "common": common,
            "expected": expected,
            "base_revision": revision - 1,
        }
    elif batch.keys() != {"id", "index", "count"}:
        raise ValueError("Only the first batch event may contain a selection manifest")
    if (
        identifier != pending["id"]
        or index != pending["next_index"]
        or count != pending["count"]
        or common != pending["common"]
        or revision != pending["base_revision"] + index + 1
        or event["kind"] != "images"
        or (event["key"], event["record"]) != pending["expected"][index]
    ):
        raise ValueError("Batch events must match their complete contiguous operation")
    pending["next_index"] += 1
    return pending if pending["next_index"] < count else None


def validate_review_state(state, source):
    """Validate live or captured review state with the same complete history grammar."""
    if (
        not isinstance(state, dict)
        or state.keys() != {"schema_version", "source", "revision", "images", "pairs", "history"}
        or type(state["schema_version"]) is not int
        or state["schema_version"] != 1
        or state["source"] != str(source)
        or type(state["revision"]) is not int
        or not isinstance(state["images"], dict)
        or not isinstance(state["pairs"], dict)
        or not isinstance(state["history"], list)
        or state["revision"] != len(state["history"])
    ):
        raise ValueError("Unsupported review history state")
    for kind in ("images", "pairs"):
        for key, record in state[kind].items():
            _record(kind, key, record)
    replay = {"images": {}, "pairs": {}}
    events = []
    identities = {}
    pending_batch, seen_batches = None, set()
    for revision, event in enumerate(state["history"], 1):
        if (
            not isinstance(event, dict)
            or type(event.get("revision")) is not int
            or event["revision"] != revision
        ):
            raise ValueError("Review history revisions must form a complete sequence")
        kind, key = event.get("kind"), _digest(event.get("key"))
        if not isinstance(kind, str) or kind not in replay:
            raise ValueError("Invalid review history target kind")
        try:
            at = datetime.fromisoformat(_text(event.get("at")))
            if at.tzinfo is None or at.utcoffset() is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise ValueError("Invalid review history timestamp") from exc
        _absolute(event.get("similarity_run"))
        base_fields = {"revision", "at", "kind", "key", "record", "similarity_run"}
        action = event.get("action", "edit")
        if not isinstance(action, str) or action not in {"edit", "restore", "batch"}:
            raise ValueError("Unsupported review history action")
        if pending_batch is not None and action != "batch":
            raise ValueError("A batch history operation is incomplete")
        allowed = base_fields | {"action", "reviewer", "reviewer_kind"}
        if action == "restore":
            allowed |= {"reason", "restoration"}
        if action == "batch":
            allowed |= {"reason", "batch"}
        if not base_fields <= event.keys() or event.keys() - allowed:
            raise ValueError("Malformed review history event fields")
        if "reviewer" in event or "reviewer_kind" in event or action in {"restore", "batch"}:
            _text(event.get("reviewer"))
            if not isinstance(event.get("reviewer_kind"), str) or event["reviewer_kind"] not in {
                "human",
                "assistant",
                "unknown",
            }:
                raise ValueError("Invalid review history actor kind")
        before = replay[kind].get(key)
        record = event["record"]
        if record is not None:
            _record(kind, key, record)
            identity = {
                field: value
                for field, value in record.items()
                if field.endswith(("source_path", "sha256"))
            }
            if identities.setdefault((kind, key), identity) != identity:
                raise ValueError("History target identity changed within one key")
        elif action != "restore":
            raise ValueError("Only restoration may remove a review record")
        if action == "batch":
            _text(event.get("reason"))
            pending_batch = _batch_event(event, revision, replay, pending_batch, seen_batches)
        if action == "restore":
            if record == before:
                raise ValueError("A restoration event must change the target record")
            _text(event.get("reason"))
            restore = event.get("restoration")
            if not isinstance(restore, dict) or restore.keys() != {
                "target_revision",
                "target_event_id",
                "before",
                "plan_sha256",
            }:
                raise ValueError("Malformed restoration provenance")
            target_revision = restore["target_revision"]
            if (
                type(target_revision) is not int
                or not 1 <= target_revision < revision
                or type(restore["before"]) is not bool
            ):
                raise ValueError("Invalid restoration target revision")
            selected = events[target_revision - 1]
            _digest(restore["plan_sha256"])
            if (
                selected["event_id"] != restore["target_event_id"]
                or selected["kind"] != kind
                or selected["key"] != key
                or selected["before" if restore["before"] else "after"] != record
            ):
                raise ValueError("Restoration does not match its selected historical state")
        if record is None:
            replay[kind].pop(key, None)
        else:
            replay[kind][key] = record
        events.append(
            {
                "revision": revision,
                "event_id": _identity(event),
                "at": event["at"],
                "kind": kind,
                "key": key,
                "action": action,
                "reviewer": event.get("reviewer"),
                "reviewer_kind": event.get("reviewer_kind", "unknown"),
                "reason": event.get("reason", (record or {}).get("reason")),
                "similarity_run": event["similarity_run"],
                "restoration": event.get("restoration"),
                "batch": event.get("batch"),
                "before": before,
                "after": record,
                "changes": _changes(before, record),
            }
        )
    if pending_batch is not None:
        raise ValueError("A batch history operation is incomplete")
    if replay != {kind: state[kind] for kind in replay}:
        raise ValueError("Review history replay differs from the saved current state")
    return events
