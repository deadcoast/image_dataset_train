"""Read and restore review versions without changing source files or past events."""

from __future__ import annotations

import copy
import hashlib
import stat
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.review_state import (
    _absolute as _absolute,
)
from image_dataset_train.review_state import (
    _changes as _changes,
)
from image_dataset_train.review_state import (
    _digest as _digest,
)
from image_dataset_train.review_state import (
    _json as _json,
)
from image_dataset_train.review_state import (
    _relative as _relative,
)
from image_dataset_train.review_state import (
    _text as _text,
)
from image_dataset_train.review_state import (
    validate_review_state as _validate_review_state,
)
from image_dataset_train.reviews import (
    ELIGIBLE,
    ReviewConflict,
    ReviewStore,
    _groups,
    _identity,
    _image_key,
    _verify_source,
    load_context,
    pair_for_paths,
)


def _unlinked(path: Path):
    for part in (path.absolute(), *path.absolute().parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Linked review history paths are not supported: {path}")


def _bytes(path: Path) -> bytes:
    _unlinked(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Review history requires a regular file: {path}")
    raw = path.read_bytes()
    _unlinked(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ReviewConflict("Review history inputs changed while reading; inspect again")
    return raw


def _context(config, run):
    for path in (config.source, config.reviews, run):
        _unlinked(path)
    run = run.resolve(strict=True)
    meta = _json(_bytes(run / "run.json"))
    inventory = Path(_absolute(meta.get("inventory_run")))
    inventory_meta = _json(_bytes(inventory / "run.json"))
    source = Path(_absolute(inventory_meta.get("source")))
    _unlinked(source)
    files = [run / name for name in ("run.json", "images.jsonl", "pairs.jsonl", "summary.json")]
    files.extend(inventory / name for name in ("run.json", "manifest.jsonl"))
    hashes = {str(path): hashlib.sha256(_bytes(path)).hexdigest() for path in files}
    context = load_context(run, require_source=False)
    if context.source != config.source.resolve():
        raise ValueError("Configuration source does not match the review history source")
    if hashes != {str(path): hashlib.sha256(_bytes(path)).hexdigest() for path in files}:
        raise ReviewConflict("Review context changed while reading; inspect again")
    store = ReviewStore(config.reviews, context.source)
    _unlinked(config.reviews)
    for path in (store.directory, store.path, store.directory / "reviews.lock"):
        _unlinked(path)
    return context, store, hashes


def _compatible(context, kind, key, record):
    if record is None:
        return False
    if kind == "images":
        row = context.rows.get(record["source_path"])
        return bool(
            row
            and row["kind"] == "image"
            and row["decision"] in ELIGIBLE
            and _image_key(row) == key
        )
    try:
        expected = pair_for_paths(
            context, [record["left_source_path"], record["right_source_path"]]
        )
        return expected["pair_id"] == key and all(
            record[name] == value for name, value in expected.items() if name != "pair_id"
        )
    except ValueError:
        return False


def _state(store, context):
    raw = _bytes(store.path) if store.path.exists() else None
    state = store.read()
    if raw is not None and _json(raw) != state or raw is None and store.path.exists():
        raise ReviewConflict("Review store changed while reading; inspect again")
    events = validate_review_state(state, context)
    return state, events, hashlib.sha256(raw).hexdigest() if raw is not None else None


def validate_review_state(state, context):
    """Apply shared replay validation, then describe current inventory compatibility."""
    events = _validate_review_state(state, context.source)
    for event in events:
        event["compatible"] = _compatible(
            context, event["kind"], event["key"], event["after"] or event["before"]
        )
    return events


def _loaded(config, run):
    context, store, hashes = _context(config, run)
    state, events, digest = _state(store, context)
    return context, store, hashes, state, events, digest


def inspect_history(
    config: Config, run: Path, *, image=None, pair=None, limit=20, offset=0
) -> dict:
    """List recorded corrections without source reads, locks, or artifact writes."""
    if image is not None and pair is not None:
        raise ValueError("Choose an image or a pair history filter, not both")
    if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
        raise ValueError("History limit must be 1..200 and offset must be nonnegative")
    if image is not None:
        _relative(image)
    if pair is not None:
        _digest(pair)
    context, store, _, state, events, digest = _loaded(config, run)
    matching = []
    for event in reversed(events):
        record = event["after"] or event["before"]
        if image is not None and (event["kind"] != "images" or record["source_path"] != image):
            continue
        if pair is not None and (event["kind"] != "pairs" or event["key"] != pair):
            continue
        matching.append(event)
    page = matching[offset : offset + limit]
    batch_ids = {event["batch"]["id"] for event in page if event["batch"]}
    batches = {
        event["batch"]["id"]: event["batch"]
        for event in events
        if event["batch"] and event["batch"]["index"] == 0 and event["batch"]["id"] in batch_ids
    }
    return {
        "schema_version": 1,
        "source": str(context.source),
        "similarity_run": str(context.run),
        "review_file": str(store.path),
        "current_revision": state["revision"],
        "revision": state["revision"],
        "store_sha256": digest,
        "total_events": len(events),
        "matching_events": len(matching),
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(matching) else None,
        "events": page,
        "batches": batches,
        "source_revalidated": False,
    }


def preview_restore(config: Config, run: Path, revision: int, *, before=False) -> dict:
    """Bind an exact historical target and complete current state, without writes."""
    if type(revision) is not int or revision < 1 or type(before) is not bool:
        raise ValueError("Choose a positive review revision and a boolean before selector")
    context, store, hashes, state, events, digest = _loaded(config, run)
    if revision > len(events):
        raise ValueError("The selected review revision does not exist")
    selected = events[revision - 1]
    current = state[selected["kind"]].get(selected["key"])
    target = selected["before" if before else "after"]
    plan = {
        "schema_version": 1,
        "source": str(context.source),
        "similarity_run": str(context.run),
        "review_file": str(store.path),
        "store_sha256": digest,
        "context_sha256": hashes,
        "current_revision": state["revision"],
        "target_revision": revision,
        "before": before,
        "selected_event": selected,
        "selected_batch": (
            events[revision - selected["batch"]["index"] - 1]["batch"]
            if selected["batch"]
            else None
        ),
        "current_record": current,
        "proposed_record": target,
        "changes": _changes(current, target),
        "applicable": selected["compatible"],
        "no_op": current == target,
        "source_revalidated": False,
    }
    return {**plan, "plan_sha256": _identity(plan)}


def restore_review(
    config: Config,
    run: Path,
    revision: int,
    *,
    before=False,
    expected_revision: int,
    expected_plan_sha256: str,
    reason: str,
    reviewer: str,
    reviewer_kind: str,
    guard=None,
) -> dict:
    """Restore one record under the shared lock, appending an attributed event."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected review revision must be a nonnegative integer")
    _digest(expected_plan_sha256)
    reason, reviewer = _text(reason).strip(), _text(reviewer).strip()
    if not isinstance(reviewer_kind, str) or reviewer_kind not in {"human", "assistant", "unknown"}:
        raise ValueError("Choose reviewer_kind: human, assistant or unknown")
    initial = preview_restore(config, run, revision, before=before)
    if (
        initial["current_revision"] != expected_revision
        or initial["plan_sha256"] != expected_plan_sha256
    ):
        raise ReviewConflict("Restoration preview changed; inspect and preview again")
    if not initial["applicable"]:
        raise ValueError("Historical target does not match the current inventory and pair policy")
    context, store, _ = _context(config, run)
    # A selected history event requires an existing store, so apply need not create one.
    if not store.path.is_file():
        raise ReviewConflict("Review store is unavailable; inspect again")
    try:
        with FileLock(str(store.directory / "reviews.lock"), timeout=0):
            plan = preview_restore(config, run, revision, before=before)
            if (
                plan["current_revision"] != expected_revision
                or plan["plan_sha256"] != expected_plan_sha256
            ):
                raise ReviewConflict("Restoration preview changed; inspect and preview again")
            context, store, _ = _context(config, run)
            state, _, _ = _state(store, context)
            selected = plan["selected_event"]
            kind, key = selected["kind"], selected["key"]
            identity = selected["after"] or selected["before"]
            prefixes = ("",) if kind == "images" else ("left_", "right_")
            for prefix in prefixes:
                _verify_source(
                    context,
                    context.rows[identity[prefix + "source_path"]],
                    config.validation.max_file_bytes,
                )
            updated = copy.deepcopy(state)
            target = plan["proposed_record"]
            if target is None:
                updated[kind].pop(key, None)
            else:
                updated[kind][key] = copy.deepcopy(target)
            _, conflicts = _groups(context, updated)
            if conflicts:
                raise ValueError("Restoration conflicts with current related/distinct groups")
            if guard is not None:
                guard()
            # Defend against changes not made through the cooperative review lock too.
            if (
                preview_restore(config, run, revision, before=before)["plan_sha256"]
                != expected_plan_sha256
            ):
                raise ReviewConflict("Restoration inputs changed before publication; preview again")
            _unlinked(context.source)
            for prefix in prefixes:
                _verify_source(
                    context,
                    context.rows[identity[prefix + "source_path"]],
                    config.validation.max_file_bytes,
                )
            if plan["no_op"]:
                return {
                    **plan,
                    "status": "unchanged",
                    "revision": state["revision"],
                    "previous_revision": state["revision"],
                    "event": None,
                    "source_revalidated": True,
                }
            event = {
                "revision": state["revision"] + 1,
                "at": datetime.now(UTC).isoformat(),
                "kind": kind,
                "key": key,
                "record": copy.deepcopy(target),
                "similarity_run": str(context.run),
                "action": "restore",
                "reason": reason,
                "reviewer": reviewer,
                "reviewer_kind": reviewer_kind,
                "restoration": {
                    "target_revision": revision,
                    "target_event_id": selected["event_id"],
                    "before": before,
                    "plan_sha256": expected_plan_sha256,
                },
            }
            updated["revision"] = event["revision"]
            updated["history"].append(event)
            _validate_review_state(updated, context.source)
            _unlinked(store.path)
            atomic_json(store.path, updated)
            return {
                **plan,
                "status": "restored",
                "revision": updated["revision"],
                "previous_revision": state["revision"],
                "event": event,
                "source_revalidated": True,
            }
    except Timeout as exc:
        raise ReviewConflict(
            "Another review update is running; inspect again after it finishes"
        ) from exc
