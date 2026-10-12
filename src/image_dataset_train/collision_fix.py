"""tf001: deterministic stem repair, with preserved captions and resumable intent.

Called under the same source-directory lock used by tagging and caption removal.
No image decoding or model loading is needed. Image bytes are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train.diagnostics import EventLog, atomic_json
from image_dataset_train.inventory import IMAGE_EXTENSIONS, _signature, _walk, file_sha256


@dataclass
class FixResult:
    actions: list[dict] = field(default_factory=list)
    renamed: int = 0
    archived: int = 0
    errors: list[str] = field(default_factory=list)
    reports: list[Path] = field(default_factory=list)
    log: Path | None = None


def _name(image: Path, reserved: set[str]) -> str:
    # Leave room for an extension/counter on Windows and UTF-8 filesystems.
    stem = image.stem
    if len(stem.encode("utf-8")) > 150:
        short = stem.encode("utf-8")[:120].decode("utf-8", errors="ignore")
        stem = short + "-" + hashlib.sha256(stem.encode()).hexdigest()[:10]
    base = stem + "-" + image.suffix[1:].lower()
    candidate, index = base, 2
    while candidate.casefold() in reserved:
        candidate = f"{base}-{index}"
        index += 1
    reserved.add(candidate.casefold())
    return candidate + image.suffix


def _digest(source: Path, relative: str) -> str:
    from image_dataset_train.operations import _safe_path

    path = _safe_path(source, relative)
    if not path.is_file():
        raise ValueError(f"Not a regular file: {relative}")
    before = _signature(path)
    digest = file_sha256(path)
    if before != _signature(path):
        raise ValueError(f"File changed during tf001 inspection: {relative}")
    return digest


def _plan(source: Path) -> tuple[list[dict], list[str]]:
    from image_dataset_train.operations import _safe_path

    directories = sorted(
        {p.parent for p in _walk(source) if p.suffix.lower() in IMAGE_EXTENSIONS},
        key=lambda p: (str(p).casefold(), str(p)),
    )
    groups, errors = [], []
    for directory in directories:
        # Linked directories found by _walk are never traversed here.
        _safe_path(source, directory.relative_to(source).as_posix())
        entries = sorted(directory.iterdir(), key=lambda p: (p.name.casefold(), p.name))
        reserved = {p.stem.casefold() for p in entries}
        pairs: dict[str, tuple[list[Path], list[Path]]] = defaultdict(lambda: ([], []))
        for entry in entries:
            if entry.suffix.lower() in IMAGE_EXTENSIONS | {".txt"}:
                pairs[entry.stem.casefold()][int(entry.suffix.lower() == ".txt")].append(entry)
        for stem, (images, captions) in pairs.items():
            if not images or len(images) == 1 and len(captions) < 2:
                continue
            try:
                actions = []
                retained = []
                # Retire ambiguous captions before moving any image; never guess ownership.
                for path in [*captions, *images]:
                    relative = path.relative_to(source).as_posix()
                    if path.is_symlink() or path.is_junction() or not path.is_file():
                        retained.append(relative)
                        continue
                    kind = "caption" if path.suffix.lower() == ".txt" else "image"
                    digest = _digest(source, relative)
                    target = (
                        path.with_name(_name(path, reserved)).relative_to(source).as_posix()
                        if kind == "image"
                        else relative
                    )
                    actions.append(
                        {
                            "kind": kind,
                            "source": relative,
                            "target": target,
                            "sha256": digest,
                            "done": False,
                        }
                    )
                if not any(a["kind"] == "image" for a in actions):
                    continue
                groups.append(
                    {
                        "directory": directory.relative_to(source).as_posix(),
                        "stem": stem,
                        "actions": actions,
                        "retained": retained,
                    }
                )
            except (OSError, ValueError) as exc:
                errors.append(f"[te001] [tf001] {directory / stem}: {exc}")
    return groups, errors


def pending_repairs(source: Path, home: Path) -> list[tuple[Path, dict]]:
    from image_dataset_train.operations import _safe_path

    pending = []
    for path in sorted((home / "operations").glob("*-tf001-*/fix.json")):
        _safe_path(home, path.relative_to(home).as_posix())
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("source") != str(source) or plan.get("status") == "completed":
            continue
        if plan.get("schema_version") != 1 or plan.get("fix_code") != "tf001":
            raise ValueError(f"Unsupported tf001 recovery plan: {path}")
        for group in plan["groups"]:
            parent = _safe_path(source, group["directory"])
            for action in group["actions"]:
                original = _safe_path(source, action["source"])
                if (
                    original.parent != parent
                    or original.stem.casefold() != group["stem"]
                    or not re.fullmatch(r"[a-f0-9]{64}", action["sha256"])
                    or not isinstance(action["done"], bool)
                    or action["kind"] not in {"image", "caption"}
                    or action["kind"] == "caption"
                    and (original.suffix.lower() != ".txt" or action["target"] != action["source"])
                    or action["kind"] == "image"
                    and original.suffix.lower() not in IMAGE_EXTENSIONS
                ):
                    raise ValueError(f"Invalid tf001 recovery action: {path}")
        pending.append((path.parent, plan))
    return pending


def _refresh_pending(source: Path, report: Path, plan: dict, *, save: bool = True) -> None:
    """A retry takes a fresh snapshot of remaining originals, retaining old evidence."""
    from image_dataset_train.operations import _journal, _safe_path

    for group in plan["groups"]:
        parent = _safe_path(source, group["directory"])
        entries = sorted(parent.iterdir(), key=lambda p: (p.name.casefold(), p.name))
        reserved = {p.stem.casefold() for p in entries}
        reserved.update(Path(a["target"]).stem.casefold() for a in group["actions"])
        remaining = {a["source"]: a for a in group["actions"] if not a["done"]}
        for path in entries:
            if path.stem.casefold() != group[
                "stem"
            ] or path.suffix.lower() not in IMAGE_EXTENSIONS | {".txt"}:
                continue
            relative = path.relative_to(source).as_posix()
            if path.is_symlink() or path.is_junction() or not path.is_file():
                if relative not in group.setdefault("retained", []):
                    group["retained"].append(relative)
                continue
            digest = _digest(source, relative)
            action = remaining.get(relative)
            if action is None:
                kind = "caption" if path.suffix.lower() == ".txt" else "image"
                action = {
                    "kind": kind,
                    "source": relative,
                    "sha256": digest,
                    "done": False,
                    "target": relative
                    if kind == "caption"
                    else path.with_name(_name(path, reserved)).relative_to(source).as_posix(),
                }
                group["actions"].append(action)
                if save:
                    _journal(report, {"event": "fix_snapshot_added", "fix_code": "tf001", **action})
            elif action["sha256"] != digest:
                if save:
                    _journal(
                        report,
                        {
                            "event": "fix_snapshot_changed",
                            "fix_code": "tf001",
                            "previous": action.copy(),
                            "current_sha256": digest,
                        },
                    )
                action["sha256"] = digest
        # A newly arrived ambiguous caption must be preserved before the next image move.
        group["actions"].sort(key=lambda a: (not a["done"], a["kind"] != "caption"))
    if save:
        atomic_json(report / "fix.json", plan)


def _check_members(source: Path, group: dict) -> None:
    """Detect a new ambiguous caption/image before continuing a saved group."""
    from image_dataset_train.operations import _safe_path

    parent = _safe_path(source, group["directory"])
    expected = {a["source"] for a in group["actions"] if not a["done"]} | set(
        group.get("retained", [])
    )
    for path in parent.iterdir():
        if (
            path.stem.casefold() == group["stem"]
            and (path.suffix.lower() in IMAGE_EXTENSIONS | {".txt"})
            and path.relative_to(source).as_posix() not in expected
        ):
            raise ValueError(
                f"Files changed during tf001: unexpected {path.name}; retry when stable."
            )


def _apply_action(source: Path, report: Path, plan: dict, action: dict) -> bool:
    from image_dataset_train.operations import _finish_commit, _journal, _safe_path

    original = _safe_path(source, action["source"])
    caption = action["kind"] == "caption"
    if action["kind"] not in {"image", "caption"}:
        raise ValueError("Invalid tf001 recovery action.")
    if caption:
        backup_root = _safe_path(report, "captions")
        backup_root.mkdir(exist_ok=True)
        target = _safe_path(backup_root, action["target"])
    else:
        target = _safe_path(source, action["target"])
        if original.parent != target.parent or original.suffix != target.suffix:
            raise ValueError("tf001 can only rename an image within its own directory.")
        if original.stem.casefold() == target.stem.casefold():
            raise ValueError("tf001 destination must have a new stem.")
    if not original.exists():
        if target.is_file() and file_sha256(target) == action["sha256"]:
            return False  # Publication finished before the prior process could journal it.
        raise ValueError(f"Files changed since tf001: cannot locate {action['source']}.")
    if _digest(source, action["source"]) != action["sha256"]:
        raise ValueError(f"Files changed since tf001: {action['source']}; original kept.")
    if caption:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with original.open("rb") as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                outgoing.flush()
                os.fsync(outgoing.fileno())
        if file_sha256(target) != action["sha256"]:
            # Keep an interrupted partial backup and make a complete one on this retry.
            target.rename(target.with_name(target.name + ".previous-" + uuid4().hex))
            return _apply_action(source, report, plan, action)
    else:
        # A concurrent file may occupy a planned stem. Allocate another free stem.
        occupied = [
            p for p in original.parent.iterdir() if p.stem.casefold() == target.stem.casefold()
        ]
        if occupied and not (
            os.name != "nt"
            and len(occupied) == 1
            and target.exists()
            and os.path.samefile(original, target)
        ):
            reserved = {p.stem.casefold() for p in original.parent.iterdir()}
            for group in plan["groups"]:
                reserved.update(Path(a["target"]).stem.casefold() for a in group["actions"])
            action["target"] = (
                original.with_name(_name(original, reserved)).relative_to(source).as_posix()
            )
            atomic_json(report / "fix.json", plan)
            target = _safe_path(source, action["target"])
    _journal(report, {"event": "fix_intent", "error_code": "te001", "fix_code": "tf001", **action})
    if _digest(source, action["source"]) != action["sha256"]:
        raise ValueError(f"Files changed before tf001 commit: {action['source']}.")
    with _finish_commit():
        if caption:
            original.unlink()  # Verified recovery copy already exists.
        elif os.name == "nt":
            original.rename(target)  # Fails instead of overwriting a raced destination.
        else:
            if not target.exists():
                os.link(original, target)  # Exclusive publication; same filesystem.
            if not os.path.samefile(original, target):
                raise FileExistsError(f"tf001 destination appeared: {target}")
            original.unlink()
        action["done"] = True
        atomic_json(report / "fix.json", plan)
        _journal(
            report,
            {
                "event": "caption_preserved" if caption else "image_renamed",
                "error_code": "te001",
                "fix_code": "tf001",
                **action,
            },
        )
    return True


def repair_collisions(source: Path, home: Path, *, dryrun: bool, progress) -> FixResult:
    result = FixResult()
    log = EventLog(home, enabled=not dryrun)
    pending = pending_repairs(source, home)

    def execute(report: Path, plan: dict, *, resume: bool = False) -> None:
        result.reports.append(report)
        plan["status"] = "running"
        atomic_json(report / "fix.json", plan)
        try:
            if resume:
                _refresh_pending(source, report, plan)
            for group in plan["groups"]:
                for action in group["actions"]:
                    if action["done"]:
                        continue
                    _check_members(source, group)
                    changed = _apply_action(source, report, plan, action)
                    action["done"] = True
                    atomic_json(report / "fix.json", plan)
                    result.renamed += changed and action["kind"] == "image"
                    result.archived += changed and action["kind"] == "caption"
                    progress(
                        f"[tf001] {result.renamed:,} images renamed; "
                        f"{result.archived:,} captions preserved"
                    )
            plan["status"] = "completed"
        except BaseException as exc:
            plan["status"] = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
            plan["error"] = str(exc)
            result.log = log.exception(
                exc, action="tf001", error_code="te001", fix_code="tf001", report=report
            )
            if not isinstance(exc, Exception):
                raise
            result.errors.append(
                f"[tf001] {exc} Retry the same --fix command to resume. Report: {report}"
            )
        finally:
            atomic_json(report / "fix.json", plan)
            result.log = (
                log.event(
                    "fix_completed" if plan["status"] == "completed" else "fix_incomplete",
                    error_code="te001",
                    fix_code="tf001",
                    source=source,
                    report=report,
                    renamed=result.renamed,
                    archived=result.archived,
                    status=plan["status"],
                )
                or result.log
            )

    for report, plan in pending:
        if dryrun:
            _refresh_pending(source, report, plan, save=False)
        result.actions.extend(
            a.copy() for g in plan["groups"] for a in g["actions"] if not a["done"]
        )
        if dryrun:
            result.reports.append(report)
        else:
            execute(report, plan, resume=True)
    if result.errors or pending and dryrun:
        return result
    groups, errors = _plan(source)
    result.errors.extend(errors)
    if errors:
        result.log = log.event(
            "fix_planning_failed",
            level="error",
            error_code="te001",
            fix_code="tf001",
            source=source,
            errors=errors,
        )
    result.actions.extend(a.copy() for g in groups for a in g["actions"])
    if groups and not dryrun:
        identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-tf001-" + uuid4().hex[:8]
        report = home / "operations" / identifier
        report.mkdir(parents=True)
        plan = {
            "schema_version": 1,
            "source": str(source),
            "error_code": "te001",
            "fix_code": "tf001",
            "status": "planned",
            "groups": groups,
        }
        atomic_json(report / "fix.json", plan)
        result.log = log.event(
            "fix_planned", error_code="te001", fix_code="tf001", source=source, report=report
        )
        execute(report, plan)
    return result
