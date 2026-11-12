"""Preview and atomically apply reviewed annotations to an explicit image set."""

from __future__ import annotations

import copy
import stat
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.review_history import (
    _changes,
    _digest,
    _loaded,
    _relative,
    _text,
    _unlinked,
)
from image_dataset_train.reviews import (
    ELIGIBLE,
    ReviewConflict,
    _groups,
    _identity,
    _image_key,
    _verify_source,
    image_review_operations,
    image_review_proposal,
)


def _selection(paths):
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= 1000:
        raise ValueError("Select between 1 and 1000 exact image paths")
    values = [_relative(path) for path in paths]
    if len(values) != len(set(values)):
        raise ValueError("Bulk selection contains duplicate image paths")
    return sorted(values)


def _preview(config, run, paths, operations, reason):
    context, store, hashes, state, _, digest = _loaded(config, run)
    members = []
    for path in paths:
        row = context.rows.get(path)
        if row is None or row["kind"] != "image" or row["decision"] not in ELIGIBLE:
            raise ValueError(f"Bulk target is missing or ineligible in this inventory: {path}")
        key = _image_key(row)
        current = state["images"].get(key)
        proposed = image_review_proposal(row, current, operations, reason)
        members.append(
            {
                "source_path": path,
                "sha256": row["sha256"],
                "key": key,
                "current_record": current,
                "proposed_record": proposed,
                "changes": _changes(current, proposed),
            }
        )
    changed = sum(member["current_record"] != member["proposed_record"] for member in members)
    plan = {
        "schema_version": 1,
        "source": str(context.source),
        "similarity_run": str(context.run),
        "review_file": str(store.path),
        "store_sha256": digest,
        "context_sha256": hashes,
        "current_revision": state["revision"],
        "reason": reason,
        "operations": operations,
        "selected_count": len(members),
        "changed_count": changed,
        "members": members,
        "no_op": changed == 0,
        "source_revalidated": False,
    }
    return {**plan, "plan_sha256": _identity(plan)}, context, store, state


def preview_batch(
    config: Config,
    run: Path,
    paths,
    *,
    reason: str,
    decision=None,
    add_labels=None,
    remove_labels=None,
    clear_labels=False,
    subset=None,
    clear_subset=False,
) -> dict:
    """Inspect complete membership and changes without source reads or writes."""
    paths, reason = _selection(paths), _text(reason).strip()
    operations = image_review_operations(
        decision=decision,
        add_labels=add_labels,
        remove_labels=remove_labels,
        clear_labels=clear_labels,
        subset=subset,
        clear_subset=clear_subset,
    )
    return _preview(config, run, paths, operations, reason)[0]


def _source_stamp(path):
    _unlinked(path)
    value = path.stat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError(f"Selected source is not a regular file: {path}")
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _stable_sources(stamps):
    for path, expected in stamps.items():
        if _source_stamp(path) != expected:
            raise ReviewConflict("Selected source changed before batch publication; scan again")


def _verify_members(config, context, paths):
    stamps = {}
    _unlinked(context.source)
    for path in paths:
        before = _source_stamp(context.source / path)
        _verify_source(context, context.rows[path], config.validation.max_file_bytes)
        if _source_stamp(context.source / path) != before:
            raise ReviewConflict("Selected source changed during batch verification; scan again")
        stamps[context.source / path] = before
    # Detect an earlier member changing while a later member is being verified.
    _stable_sources(stamps)
    return stamps


def _matches(plan, revision, digest):
    if plan["current_revision"] != revision or plan["plan_sha256"] != digest:
        raise ReviewConflict("Bulk preview changed; inspect and preview again")


def apply_batch(
    config: Config,
    run: Path,
    paths,
    *,
    reason: str,
    expected_revision: int,
    expected_plan_sha256: str,
    reviewer: str,
    reviewer_kind: str,
    decision=None,
    add_labels=None,
    remove_labels=None,
    clear_labels=False,
    subset=None,
    clear_subset=False,
    guard=None,
) -> dict:
    """Commit one attributed batch or nothing, including verification of no-op members.

    A batch is one atomic store replacement with contiguous per-image history
    revisions. Its first event retains the full selection and operation, including
    unchanged members. Individual image events remain restorable through history.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected review revision must be a nonnegative integer")
    _digest(expected_plan_sha256)
    reviewer = _text(reviewer).strip()
    if not isinstance(reviewer_kind, str) or reviewer_kind not in {"human", "assistant", "unknown"}:
        raise ValueError("Choose reviewer_kind: human, assistant or unknown")
    paths, reason = _selection(paths), _text(reason).strip()
    operations = image_review_operations(
        decision=decision,
        add_labels=add_labels,
        remove_labels=remove_labels,
        clear_labels=clear_labels,
        subset=subset,
        clear_subset=clear_subset,
    )
    initial, _, store, _ = _preview(config, run, paths, operations, reason)
    _matches(initial, expected_revision, expected_plan_sha256)
    _unlinked(store.directory)
    store.directory.mkdir(parents=True, exist_ok=True)
    _unlinked(store.directory)
    try:
        with FileLock(str(store.directory / "reviews.lock"), timeout=0):
            plan, context, store, state = _preview(config, run, paths, operations, reason)
            _matches(plan, expected_revision, expected_plan_sha256)
            if guard is not None:
                guard()
            _verify_members(config, context, paths)
            changed = [member for member in plan["members"] if member["changes"]]
            updated = copy.deepcopy(state)
            for member in changed:
                updated["images"][member["key"]] = copy.deepcopy(member["proposed_record"])
            _, conflicts = _groups(context, updated)
            if conflicts:
                raise ValueError("Bulk review conflicts with current related/distinct groups")
            manifest = {
                "schema_version": 1,
                "base_revision": state["revision"],
                "plan_sha256": expected_plan_sha256,
                "operations": operations,
                "members": [
                    {"source_path": member["source_path"], "sha256": member["sha256"]}
                    for member in plan["members"]
                ],
            }
            common = {
                "at": datetime.now(UTC).isoformat(),
                "similarity_run": str(context.run),
                "reviewer": reviewer,
                "reviewer_kind": reviewer_kind,
                "reason": reason,
            }
            identifier = _identity({"manifest": manifest, **common}) if changed else None
            events = []
            for index, member in enumerate(changed):
                batch = {"id": identifier, "index": index, "count": len(changed)}
                if index == 0:
                    batch["manifest"] = manifest
                events.append(
                    {
                        **common,
                        "revision": state["revision"] + index + 1,
                        "kind": "images",
                        "key": member["key"],
                        "record": copy.deepcopy(member["proposed_record"]),
                        "action": "batch",
                        "batch": batch,
                    }
                )
            updated["history"].extend(events)
            updated["revision"] += len(events)
            stamps = _verify_members(config, context, paths)
            if guard is not None:
                guard()
            final, _, final_store, _ = _preview(config, run, paths, operations, reason)
            _matches(final, expected_revision, expected_plan_sha256)
            if final_store.path != store.path:
                raise ReviewConflict("Review storage changed before batch publication")
            _stable_sources(stamps)
            _unlinked(store.path)
            if events:
                atomic_json(store.path, updated)
            return {
                **plan,
                "status": "applied" if events else "unchanged",
                "revision": updated["revision"],
                "previous_revision": state["revision"],
                "batch_id": identifier,
                "batch": events[0]["batch"] if events else None,
                "events": events,
                "source_revalidated": True,
            }
    except Timeout as exc:
        raise ReviewConflict(
            "Another review update is running; inspect again after it finishes"
        ) from exc
