"""Durable human decisions and related-image groups, bound to source content."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train import __version__
from image_dataset_train.annotations import (
    annotation_fields,
    annotation_name,
    annotation_summary,
    label_names,
)
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.inventory import file_sha256
from image_dataset_train.inventory_data import read_inventory

ELIGIBLE = {"candidate", "review", "duplicate"}
PAIR_DECISIONS = {"related", "distinct", "unreviewed"}
IMAGE_DECISIONS = {"include", "exclude", "unreviewed"}


class ReviewConflict(ValueError):
    """A saved review changed after an editor loaded it."""


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _separate(source: Path, destination: Path) -> None:
    destination = destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("source and review/output directories must be separate trees")


@dataclass
class ReviewContext:
    run: Path
    source: Path
    inventory: Path
    inventory_hash: str
    rows: dict[str, dict]
    metadata: dict
    similarity_errors: int

    def pairs(self):
        with (self.run / "pairs.jsonl").open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    pair = json.loads(line)
                    left, right = pair["left_source_path"], pair["right_source_path"]
                    a, b = self.rows[left], self.rows[right]
                    identity = "\0".join(
                        (self.metadata["hash_version"], left, a["sha256"], right, b["sha256"])
                    )
                    if (
                        left >= right
                        or pair["left_sha256"] != a["sha256"]
                        or pair["right_sha256"] != b["sha256"]
                        or pair["pair_id"] != hashlib.sha256(identity.encode("utf-8")).hexdigest()
                        or a["decision"] not in ELIGIBLE
                        or b["decision"] not in ELIGIBLE
                    ):
                        raise ValueError("pair references do not match the inventory")
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid similarity pair at line {number}: {exc}") from exc
                yield pair


def load_context(run: Path) -> ReviewContext:
    run = run.resolve(strict=True)
    metadata = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("stage") != "similarity"
        or type(metadata.get("schema_version")) is not int
        or metadata.get("schema_version") != 1
        or metadata.get("status") not in ("completed", "completed_with_errors")
        or run.name.startswith(".pending-")
    ):
        raise ValueError("review requires a published similarity run")
    for name in ("images", "pairs", "summary"):
        suffix = "json" if name == "summary" else "jsonl"
        if file_sha256(run / f"{name}.{suffix}") != metadata.get(f"{name}_sha256"):
            raise ValueError(f"similarity artifact integrity failure: {name}")
    if (
        not isinstance(metadata.get("inventory_run"), str)
        or not Path(metadata["inventory_run"]).is_absolute()
    ):
        raise ValueError("similarity run is missing its inventory reference")
    inventory = Path(metadata["inventory_run"])
    inventory_meta, rows, digest = read_inventory(inventory)
    source = Path(inventory_meta["source"]).resolve(strict=True)
    if (
        not source.is_dir()
        or digest != metadata.get("inventory_manifest_sha256")
        or str(source) != metadata.get("source")
        or not isinstance(metadata.get("hash_version"), str)
    ):
        raise ValueError("similarity run and inventory source identities do not match")
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if (
        not isinstance(summary, dict)
        or type(summary.get("errors")) is not int
        or summary["errors"] < 0
    ):
        raise ValueError("Invalid similarity error count")
    return ReviewContext(
        run,
        source,
        inventory,
        digest,
        {r["source_path"]: r for r in rows},
        metadata,
        summary["errors"],
    )


def _verify_source(context: ReviewContext, row: dict, max_bytes: int) -> None:
    path = context.source / row["source_path"]
    for part in (path, *path.parents):
        if part == context.source:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Source became a link: {row['source_path']}")
    if not path.resolve().is_relative_to(context.source):
        raise ValueError("review source path escapes its directory")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise ValueError(f"Source is not a regular file within limits: {row['source_path']}")
    digest = file_sha256(path)
    after = path.stat()
    if digest != row["sha256"] or (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"Source changed since inventory: {row['source_path']}. Scan it again.")


class ReviewStore:
    def __init__(self, root: Path, source: Path):
        self.source = source
        root = root.resolve()
        _separate(source, root)
        self.directory = root / _identity(os.path.normcase(str(source)))
        self.path = self.directory / "reviews.json"

    def _check_paths(self):
        for path in (self.directory, self.path, self.directory / "reviews.lock"):
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Review storage must not be a link: {path}")

    def read(self) -> dict:
        self._check_paths()
        if not self.path.exists():
            return {
                "schema_version": 1,
                "source": str(self.source),
                "revision": 0,
                "pairs": {},
                "images": {},
                "history": [],
            }
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or value.get("source") != str(self.source)
            or type(value.get("revision")) is not int
            or not isinstance(value.get("pairs"), dict)
            or not isinstance(value.get("images"), dict)
            or not isinstance(value.get("history"), list)
            or value["revision"] != len(value["history"])
        ):
            raise ValueError(f"Invalid review state: {self.path}. Preserve it before recovery.")
        for kind, decisions in (("pairs", PAIR_DECISIONS), ("images", IMAGE_DECISIONS)):
            for key, record in value[kind].items():
                if (
                    not isinstance(record, dict)
                    or not isinstance(record.get("decision"), str)
                    or record["decision"] not in decisions
                ):
                    raise ValueError(f"Invalid {kind} decision in {self.path}")
                prefixes = ("left_", "right_") if kind == "pairs" else ("",)
                for prefix in prefixes:
                    path, digest = record.get(prefix + "source_path"), record.get(prefix + "sha256")
                    if (
                        not isinstance(path, str)
                        or not path
                        or not isinstance(digest, str)
                        or len(digest) != 64
                        or any(c not in "0123456789abcdef" for c in digest)
                    ):
                        raise ValueError(f"Invalid review content identity in {self.path}")
                if kind == "images" and (
                    key != _image_key(record)
                    or record.get("caption_override") is not None
                    and not isinstance(record["caption_override"], str)
                ):
                    raise ValueError(f"Invalid image review or caption in {self.path}")
                if kind == "images":
                    annotation_fields(record)
        return value

    def update(
        self,
        context: ReviewContext,
        kind: str,
        key: str,
        record: dict,
        *,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        clear_labels: bool = False,
        expected_revision: int | None = None,
    ) -> dict:
        self._check_paths()
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(self.directory / "reviews.lock"), timeout=0):
                state = self.read()
                if expected_revision is not None and state["revision"] != expected_revision:
                    raise ReviewConflict(
                        "Reviews changed. Reload saved values before saving again."
                    )
                if kind == "images":
                    record = {**state[kind].get(key, {"decision": "unreviewed"}), **record}
                    if add_labels is not None or remove_labels is not None or clear_labels:
                        labels = set() if clear_labels else set(record.get("labels", []))
                        labels.update(add_labels or [])
                        labels.difference_update(remove_labels or [])
                        record["labels"] = sorted(labels)
                if state[kind].get(key) == record:
                    return state
                state[kind][key] = record
                _, conflicts = _groups(context, state)
                if conflicts:
                    first = conflicts[0]
                    raise ValueError(
                        f"Decision conflicts with an existing group: {first['left']} and "
                        f"{first['right']} are marked distinct but connected by related decisions "
                        "or identical bytes. Reset the conflicting decision to unreviewed first."
                    )
                state["revision"] += 1
                state["history"].append(
                    {
                        "revision": state["revision"],
                        "at": datetime.now(UTC).isoformat(),
                        "kind": kind,
                        "key": key,
                        "record": record,
                        "similarity_run": str(context.run),
                    }
                )
                atomic_json(self.path, state)
                return state
        except Timeout as exc:
            raise RuntimeError("Another review update is running. Retry this command.") from exc


def _image_key(row: dict) -> str:
    return _identity([row["source_path"], row["sha256"]])


def _active_pair(context: ReviewContext, pair: dict) -> bool:
    return all(
        (row := context.rows.get(pair.get(f"{side}_source_path"))) is not None
        and row["kind"] == "image"
        and row["decision"] in ELIGIBLE
        and row["sha256"] == pair.get(f"{side}_sha256")
        for side in ("left", "right")
    )


def _groups(context: ReviewContext, state: dict) -> tuple[list[list[str]], list[dict]]:
    parents = {
        path: path
        for path, row in context.rows.items()
        if row["kind"] == "image" and row["decision"] in ELIGIBLE
    }

    def find(path):
        while parents[path] != path:
            parents[path] = parents[parents[path]]
            path = parents[path]
        return path

    def union(left, right):
        a, b = find(left), find(right)
        if a != b:
            parents[max(a, b)] = min(a, b)

    hashes = {}
    for path in sorted(parents):
        digest = context.rows[path]["sha256"]
        if digest in hashes:
            union(path, hashes[digest])
        else:
            hashes[digest] = path
    active = [p for p in state["pairs"].values() if _active_pair(context, p)]
    for pair in active:
        if pair["decision"] == "related":
            union(pair["left_source_path"], pair["right_source_path"])
    conflicts = [
        {"left": p["left_source_path"], "right": p["right_source_path"]}
        for p in active
        if p["decision"] == "distinct"
        and find(p["left_source_path"]) == find(p["right_source_path"])
    ]
    groups = defaultdict(list)
    for path in sorted(parents):
        groups[find(path)].append(path)
    return sorted(groups.values()), conflicts


def _review_pairs(context: ReviewContext, state: dict):
    """Stream proposals plus active manual links without retaining the proposal list."""
    manual = {key: pair for key, pair in state["pairs"].items() if _active_pair(context, pair)}
    for pair in context.pairs():
        manual.pop(pair["pair_id"], None)
        yield pair
    for key, pair in sorted(manual.items()):
        yield {**pair, "pair_id": key, "hamming_distance": None, "manual": True}


def review_status(
    config: Config,
    run: Path,
    *,
    limit=20,
    show_all=False,
    image_view=False,
    unannotated=False,
    offset=0,
    pair_decision=None,
) -> dict:
    if limit < 1 or offset < 0:
        raise ValueError("review limit must be positive and offset nonnegative")
    if pair_decision not in {None, "all", *PAIR_DECISIONS}:
        raise ValueError("Invalid pair decision filter")
    context = load_context(run)
    store = ReviewStore(config.reviews, context.source)
    state = store.read()
    queue = []
    counts = Counter()
    total = 0
    for pair in _review_pairs(context, state):
        saved = state["pairs"].get(pair["pair_id"], {})
        decision = saved.get("decision", "unreviewed")
        counts[decision] += 1
        matches = (
            (pair_decision == "all" or decision == pair_decision)
            if pair_decision
            else (show_all or decision == "unreviewed")
        )
        if matches:
            if total >= offset and len(queue) < limit:
                queue.append({**pair, "decision": decision, "reason": saved.get("reason", "")})
            total += 1
    groups, conflicts = _groups(context, state)
    eligible = [
        r for r in context.rows.values() if r["kind"] == "image" and r["decision"] in ELIGIBLE
    ]
    image_counts = Counter(
        state["images"].get(_image_key(row), {}).get("decision", "unreviewed") for row in eligible
    )
    current_keys = {_image_key(row) for row in eligible}
    result = {
        "source": str(context.source),
        "review_file": str(store.path),
        "revision": state["revision"],
        "pairs": queue,
        "pair_total": total,
        "pair_offset": offset,
        "pair_next_offset": offset + limit if offset + limit < total else None,
        "pair_counts": dict(counts),
        "image_counts": dict(image_counts),
        "groups": len(groups),
        "conflicts": conflicts,
        "stale_pair_decisions": sum(not _active_pair(context, p) for p in state["pairs"].values()),
        "stale_image_decisions": len(state["images"].keys() - current_keys),
        "similarity_errors": context.similarity_errors,
        "annotations": annotation_summary(
            state["images"].get(_image_key(row), {}) for row in eligible
        ),
    }
    if image_view or unannotated:
        result.pop("pairs")
        result["images"] = []
        for row in sorted(eligible, key=lambda r: r["source_path"]):
            saved = state["images"].get(_image_key(row), {"decision": "unreviewed"})
            annotations = annotation_fields(saved)
            pending = (
                saved["decision"] == "include"
                and not (annotations["labels_reviewed"] and annotations["subset_reviewed"])
                if unannotated
                else show_all or saved["decision"] == "unreviewed"
            )
            if pending:
                result["images"].append(
                    {
                        "source_path": row["source_path"],
                        "sha256": row["sha256"],
                        "intake_reasons": row["reasons"],
                        "sidecar_path": row.get("sidecar_path"),
                        **saved,
                        **annotations,
                    }
                )
                if len(result["images"]) >= limit:
                    break
    return result


def review_pair(
    config: Config,
    run: Path,
    selector: str,
    decision: str,
    reason: str,
    *,
    expected_revision: int | None = None,
) -> dict:
    if decision not in PAIR_DECISIONS or not reason.strip():
        raise ValueError("Pair decisions are related, distinct, or unreviewed; provide --reason.")
    if len(selector) < 8 or any(c not in "0123456789abcdef" for c in selector):
        raise ValueError(
            "Use a pair ID or an unambiguous hexadecimal prefix of at least 8 characters."
        )
    context = load_context(run)
    found = None
    state = ReviewStore(config.reviews, context.source).read()
    for pair in _review_pairs(context, state):
        if pair["pair_id"].startswith(selector):
            if found is not None:
                raise ValueError("Pair prefix is ambiguous; use more characters.")
            found = pair
    if found is None:
        raise ValueError("Pair ID was not found in this similarity run.")
    return _save_pair(config, context, found, decision, reason, expected_revision)


def _save_pair(config, context, found, decision, reason, expected_revision=None):
    for side in ("left", "right"):
        _verify_source(
            context, context.rows[found[f"{side}_source_path"]], config.validation.max_file_bytes
        )
    record = {
        key: found[key]
        for key in ("left_source_path", "right_source_path", "left_sha256", "right_sha256")
    }
    record.update(decision=decision, reason=reason.strip())
    store = ReviewStore(config.reviews, context.source)
    state = store.update(
        context, "pairs", found["pair_id"], record, expected_revision=expected_revision
    )
    return {
        "review_file": str(store.path),
        "revision": state["revision"],
        "pair_id": found["pair_id"],
        **record,
    }


def pair_for_paths(context: ReviewContext, paths: list[str]) -> dict:
    if len(paths) != 2 or paths[0] == paths[1]:
        raise ValueError("Choose two different image paths.")
    left, right = sorted(paths)
    if any(
        path not in context.rows
        or context.rows[path]["kind"] != "image"
        or context.rows[path]["decision"] not in ELIGIBLE
        for path in (left, right)
    ):
        raise ValueError("Both paths must identify eligible images in the inventory.")
    a, b = context.rows[left]["sha256"], context.rows[right]["sha256"]
    identity = "\0".join((context.metadata["hash_version"], left, a, right, b))
    return {
        "pair_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "left_source_path": left,
        "left_sha256": a,
        "right_source_path": right,
        "right_sha256": b,
    }


def review_link(
    config: Config,
    run: Path,
    paths: list[str],
    decision: str,
    reason: str,
    *,
    expected_revision: int | None = None,
) -> dict:
    """Record a relationship even when pHash did not propose the pair."""
    if decision not in PAIR_DECISIONS or not reason.strip():
        raise ValueError("Pair decisions are related, distinct, or unreviewed; provide --reason.")
    context = load_context(run)
    return _save_pair(
        config,
        context,
        pair_for_paths(context, paths),
        decision,
        reason,
        expected_revision,
    )


def review_image(
    config: Config,
    run: Path,
    path: str,
    *,
    decision: str | None = None,
    reason: str = "",
    caption: str | None = None,
    clear_caption: bool = False,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    clear_labels: bool = False,
    subset: str | None = None,
    clear_subset: bool = False,
    subset_from: Path | None = None,
    subset_manifest_sha256: str | None = None,
    expected_revision: int | None = None,
) -> dict:
    context = load_context(run)
    row = context.rows.get(path)
    if row is None or row["kind"] != "image":
        raise ValueError("Use the exact relative image path from this inventory.")
    if row["decision"] not in ELIGIBLE:
        raise ValueError("This image failed intake. Repair it and scan again before reviewing.")
    if decision is not None and decision not in IMAGE_DECISIONS:
        raise ValueError("Image decisions are include, exclude, or unreviewed.")
    if caption is not None and (not caption.strip() or "\0" in caption or clear_caption):
        raise ValueError("Provide a nonempty caption or use --clear-caption.")
    add_labels = label_names(add_labels) if add_labels is not None else None
    remove_labels = label_names(remove_labels) if remove_labels is not None else None
    if set(add_labels or []) & set(remove_labels or []):
        raise ValueError("Cannot add and remove the same label in one edit")
    if subset is not None and clear_subset:
        raise ValueError("Choose a subset or clear it, not both")
    subset_origin = None
    if subset_from is not None:
        from image_dataset_train.exporting import _drafts

        if subset is not None or clear_subset:
            raise ValueError("Accept a proposed subset or enter a manual subset, not both")
        drafts, draft_meta = _drafts(
            subset_from,
            {"source": str(context.source), "inventory_manifest_sha256": context.inventory_hash},
        )
        if subset_manifest_sha256 and draft_meta["manifest_sha256"] != subset_manifest_sha256:
            raise ValueError("Subset proposal changed since QA; generate a new report")
        proposal = drafts.get((path, row["sha256"]), {}).get("subset_proposal") or {}
        subset = proposal.get("value")
        if not subset or proposal.get("matches") != [subset]:
            raise ValueError("This image has no unambiguous subset proposal to accept")
        subset_origin = {
            "kind": "caption-rule",
            "run": str(subset_from.resolve()),
            "manifest_sha256": draft_meta["manifest_sha256"],
            "caption_version": draft_meta["caption_version"],
            "rules_sha256": draft_meta["caption_rules_sha256"],
        }
    if subset is not None:
        subset = annotation_name(subset)
    store = ReviewStore(config.reviews, context.source)
    key = _image_key(row)
    annotations_changed = (
        add_labels is not None
        or remove_labels is not None
        or clear_labels
        or subset is not None
        or clear_subset
    )
    mutation = decision is not None or caption is not None or clear_caption or annotations_changed
    if not mutation:
        state = store.read()
        saved = state["images"].get(key, {"decision": "unreviewed"})
        return {
            "revision": state["revision"],
            "source_path": path,
            "sha256": row["sha256"],
            **saved,
            **annotation_fields(saved),
        }
    if not reason.strip():
        raise ValueError("Provide --reason when changing an image review.")
    _verify_source(context, row, config.validation.max_file_bytes)
    # Merge inside the store lock so concurrent caption/decision edits cannot be lost.
    record = {"source_path": path, "sha256": row["sha256"], "reason": reason.strip()}
    if decision is not None:
        record["decision"] = decision
    if caption is not None:
        record.update(caption_override=caption.strip(), caption_rule_version="manual-v1")
    if clear_caption:
        record.update(caption_override=None, caption_rule_version=None)
    if subset is not None or clear_subset:
        record["subset"] = subset
        record["subset_origin"] = subset_origin
    if annotations_changed:
        record.update(annotation_version="manual-v1", annotation_reason=reason.strip())
    state = store.update(
        context,
        "images",
        key,
        record,
        add_labels=add_labels,
        remove_labels=remove_labels,
        clear_labels=clear_labels,
        expected_revision=expected_revision,
    )
    saved = state["images"][key]
    return {
        "review_file": str(store.path),
        "revision": state["revision"],
        **saved,
        **annotation_fields(saved),
    }


def publish_groups(
    config: Config,
    run: Path,
    *,
    expected_revision: int | None = None,
) -> tuple[Path, dict]:
    context = load_context(run)
    _separate(context.source, config.runs)
    store = ReviewStore(config.reviews, context.source)
    state = store.read()
    if expected_revision is not None and state["revision"] != expected_revision:
        raise ReviewConflict("Reviews changed. Refresh publication status and try again.")
    groups, conflicts = _groups(context, state)
    unresolved_pairs = sum(
        state["pairs"].get(pair["pair_id"], {}).get("decision", "unreviewed") == "unreviewed"
        for pair in _review_pairs(context, state)
    )
    records = []
    image_counts = Counter()
    for members in groups:
        group_id = _identity([[path, context.rows[path]["sha256"]] for path in members])
        images = []
        for path in members:
            row = context.rows[path]
            _verify_source(context, row, config.validation.max_file_bytes)
            reviewed = state["images"].get(_image_key(row), {})
            decision = reviewed.get("decision", "unreviewed")
            image_counts[decision] += 1
            images.append(
                {
                    "source_path": path,
                    "sha256": row["sha256"],
                    "intake_decision": row["decision"],
                    "intake_reasons": row["reasons"],
                    "sidecar_path": row.get("sidecar_path"),
                    "sidecar_sha256": row.get("sidecar_sha256"),
                    "review_decision": decision,
                    "reason": reviewed.get("reason", ""),
                    "caption_override": reviewed.get("caption_override"),
                    "caption_rule_version": reviewed.get("caption_rule_version"),
                    **annotation_fields(reviewed),
                    "annotation_version": reviewed.get("annotation_version"),
                    "annotation_reason": reviewed.get("annotation_reason"),
                    "subset_origin": reviewed.get("subset_origin"),
                }
            )
        records.append({"group_id": group_id, "members": images})
    summary = {
        "schema_version": 1,
        "stage": "groups",
        "groups": len(records),
        "images": sum(image_counts.values()),
        "image_decisions": dict(image_counts),
        "unresolved_pairs": unresolved_pairs,
        "conflicts": conflicts,
        "review_complete": not unresolved_pairs
        and not image_counts["unreviewed"]
        and not conflicts
        and not context.similarity_errors,
        "similarity_errors": context.similarity_errors,
        "training_ready": False,
        "review_revision": state["revision"],
        "annotations": annotation_summary(
            member for group in records for member in group["members"]
        ),
    }
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    config.runs.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-groups-", dir=config.runs))
    with (staging / "groups.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    atomic_json(staging / "reviews.json", state)
    atomic_json(staging / "summary.json", summary)
    atomic_json(
        staging / "run.json",
        {
            "schema_version": 1,
            "stage": "groups",
            "status": "completed",
            "run_id": run_id,
            "source": str(context.source),
            "source_revalidated": True,
            "source_sidecars_revalidated": False,
            "similarity_run": str(context.run),
            "inventory_run": str(context.inventory),
            "inventory_manifest_sha256": context.inventory_hash,
            "review_revision": state["revision"],
            "pipeline_version": __version__,
            "completed_at": datetime.now(UTC).isoformat(),
            "files": {
                name: file_sha256(staging / name)
                for name in ("groups.jsonl", "reviews.json", "summary.json")
            },
        },
    )
    final = config.runs / run_id
    publish_directory(staging, final)
    return final, summary
