"""Opinionated workflows behind Trainime's two directory actions.

Images are read-only. Caption creation never replaces an existing path. Removal
copies and verifies captions in a separate recovery directory before unlinking.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import tempfile
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.diagnostics import EventLog, diagnose
from image_dataset_train.inventory import (
    IMAGE_EXTENSIONS,
    Record,
    _signature,
    _walk,
    file_sha256,
    scan,
)
from image_dataset_train.model_bundle import atomic_json, bundle_path, fetch_bundle
from image_dataset_train.preferences import image_directory
from image_dataset_train.runs import publish_scan

Progress = Callable[[str], None]


@dataclass
class Item:
    image: str
    caption: str
    status: str
    reason: str = ""
    image_sha256: str | None = None
    caption_sha256: str | None = None


@dataclass
class Result:
    action: str
    source: Path
    dryrun: bool
    items: list[Item]
    changed: int = 0
    errors: list[str] = field(default_factory=list)
    report: Path | None = None
    backup: Path | None = None
    review: int = 0
    log: Path | None = None

    @property
    def counts(self) -> Counter:
        return Counter(item.status for item in self.items)

    @property
    def exit_code(self) -> int:
        return int(bool(self.errors or self.counts["blocked"] or self.counts["rejected"]))


def workflow_config(source: Path, home: Path) -> Config:
    source = image_directory(str(source))
    home = home.resolve()
    if source.is_relative_to(home) or home.is_relative_to(source):
        raise ValueError("Choose an image folder separate from Trainime's settings/cache folder.")
    return Config(
        source, home / "runs", ValidationConfig(), models=home / "models", scores=home / "scores"
    )


def _safe_path(source: Path, relative: str) -> Path:
    if source.resolve(strict=True) != source or source.is_symlink() or source.is_junction():
        raise ValueError("Image directory changed after inspection.")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe relative path in operation.")
    path = source.joinpath(*parts.parts)
    if not path.resolve().is_relative_to(source):
        raise ValueError("Path now escapes the image directory.")
    for part in (path, *path.parents):
        if part == source:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked files and directories are skipped.")
    return path


def _pair_entries(image: Path, entries: list[Path]) -> tuple[list[Path], list[Path]]:
    stem = image.stem.casefold()
    return (
        [p for p in entries if p.stem.casefold() == stem and p.suffix.lower() in IMAGE_EXTENSIONS],
        [p for p in entries if p.stem.casefold() == stem and p.suffix.lower() == ".txt"],
    )


def _removal_inventory(source: Path, progress: Progress) -> list[Record]:
    """Removal needs names and caption hashes, never image decoding or inference."""
    records = []
    for path in _walk(source):
        suffix = path.suffix.lower()
        kind = "image" if suffix in IMAGE_EXTENSIONS else "sidecar"
        if suffix not in IMAGE_EXTENSIONS | {".txt"}:
            continue
        row = Record(1, path.relative_to(source).as_posix(), kind, "candidate")
        records.append(row)
        try:
            _safe_path(source, row.source_path)
            if not path.is_file():
                raise ValueError("Not a regular file.")
            if kind == "sidecar":
                before = _signature(path)
                row.sha256 = file_sha256(path)
                if before != _signature(path):
                    raise ValueError("Caption changed during inspection.")
        except (OSError, ValueError) as exc:
            row.decision, row.error = "error", str(exc)
        if len(records) % 50 == 0:
            progress(f"Checking captions: {len(records):,} files")
    return records


def _plan(source: Path, records: list[Record], action: str, limits: ValidationConfig) -> list[Item]:
    by_name = {row.source_path: row for row in records}
    directories: dict[Path, dict[str, tuple[list[Path], list[Path]]]] = {}
    items = []
    for row in records:
        if row.kind != "image":
            continue
        image = source / row.source_path
        item = Item(
            row.source_path,
            str(Path(row.source_path).with_suffix(".txt")).replace("\\", "/"),
            "ready",
            image_sha256=row.sha256,
        )
        items.append(item)
        try:
            _safe_path(source, item.image)
            if image.parent not in directories:
                groups: dict[str, tuple[list[Path], list[Path]]] = {}
                for entry in image.parent.iterdir():
                    suffix = entry.suffix.lower()
                    if suffix not in IMAGE_EXTENSIONS | {".txt"}:
                        continue
                    pair = groups.setdefault(entry.stem.casefold(), ([], []))
                    pair[int(suffix == ".txt")].append(entry)
                directories[image.parent] = groups
            images, captions = directories[image.parent].get(image.stem.casefold(), ([], []))
            if len(images) != 1 or len(captions) > 1:
                raise ValueError("Same-stem image or caption collision.")
            if captions:
                caption = captions[0]
                item.caption = caption.relative_to(source).as_posix()
                _safe_path(source, item.caption)
                if not caption.is_file():
                    raise ValueError("Caption path is not a regular file.")
                caption_record = by_name.get(item.caption)
                if not caption_record or caption_record.decision == "error":
                    raise ValueError("Caption could not be inspected; retry when it is readable.")
                item.caption_sha256 = caption_record.sha256
                if action == "tag":
                    item.status = "existing"
            elif action == "remove":
                item.status = "missing"
            if row.decision in {"error", "rejected"}:
                item.status, item.reason = "rejected", row.error or ", ".join(row.reasons)
            elif (
                action == "tag"
                and item.status == "ready"
                and max(row.stored_width or 0, row.stored_height or 0) ** 2
                > limits.max_decode_pixels
            ):
                item.status, item.reason = "rejected", "Square preprocessing exceeds pixel limit."
        except (OSError, ValueError) as exc:
            item.status, item.reason = "blocked", str(exc)
    return items


def _recheck_pair(source: Path, item: Item, *, removing: bool) -> tuple[Path, Path]:
    image = _safe_path(source, item.image)
    caption = _safe_path(source, item.caption)
    if not image.is_file():
        raise ValueError("Image is no longer present.")
    images, captions = _pair_entries(image, list(image.parent.iterdir()))
    if len(images) != 1 or images[0].name != image.name:
        raise ValueError("Image stem changed or became ambiguous.")
    if removing:
        if len(captions) != 1 or captions[0].name != caption.name or not caption.is_file():
            raise ValueError("Caption changed or became ambiguous.")
    elif captions:
        raise ValueError("A caption appeared after inspection; keeping it.")
    if item.image_sha256 and file_sha256(image) != item.image_sha256:
        raise ValueError("Image changed after inspection; retry to tag its current contents.")
    return image, caption


@contextmanager
def _finish_commit() -> Iterator[None]:
    """Let one tiny publication + journal commit finish before handling Ctrl+C."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    interrupted = False
    previous = signal.getsignal(signal.SIGINT)

    def defer(signum: int, frame: object) -> None:
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, defer)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
    if interrupted:
        raise KeyboardInterrupt


def _journal(directory: Path, event: dict) -> None:
    with (directory / "journal.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _create_caption(source: Path, item: Item, text: str, result: Result) -> None:
    assert result.report is not None
    _, target = _recheck_pair(source, item, removing=False)
    raw = (text.strip() + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    event = {"image": item.image, "caption": item.caption, "sha256": digest}
    _journal(result.report, {**event, "event": "create_intent"})
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".trainime-", suffix=".tmp", dir=target.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _recheck_pair(source, item, removing=False)
        with _finish_commit():
            if os.name == "nt":
                # Windows rename fails if the destination exists; os.replace would overwrite.
                temporary.rename(target)
            else:
                # POSIX rename overwrites; hard-link publication is atomic and exclusive.
                os.link(temporary, target)
                temporary.unlink()
            temporary = None
            result.changed += 1
            _journal(result.report, {**event, "event": "created"})
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _remove_caption(source: Path, item: Item, result: Result) -> None:
    assert result.backup is not None and result.report is not None
    _, target = _recheck_pair(source, item, removing=True)
    before = _signature(target)
    if file_sha256(target) != item.caption_sha256:
        raise ValueError("Caption changed after inspection; keeping it.")
    backup = result.backup / item.caption
    backup.parent.mkdir(parents=True, exist_ok=True)
    with target.open("rb") as original, backup.open("xb") as copy:
        shutil.copyfileobj(original, copy, length=1024 * 1024)
        copy.flush()
        os.fsync(copy.fileno())
    if file_sha256(backup) != item.caption_sha256:
        raise ValueError("Backup verification failed; original kept.")
    event = {"image": item.image, "caption": item.caption, "sha256": item.caption_sha256}
    _journal(result.report, {**event, "event": "backup_verified"})
    _recheck_pair(source, item, removing=True)
    if _signature(target) != before or file_sha256(target) != item.caption_sha256:
        raise ValueError("Caption changed during backup; original kept.")
    with _finish_commit():
        target.unlink()
        result.changed += 1
        _journal(result.report, {**event, "event": "removed"})


def _save_result(result: Result, status: str) -> None:
    assert result.report is not None
    atomic_json(
        result.report / "operation.json",
        {
            "schema_version": 1,
            "action": result.action,
            "source": str(result.source),
            "status": status,
            "changed": result.changed,
            "counts": dict(result.counts),
            "errors": result.errors,
            "review": result.review,
            "backup": str(result.backup) if result.backup else None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _execute(
    config: Config, home: Path, action: str, dryrun: bool, progress: Progress, log: EventLog
) -> Result:
    progress("Inspecting images…" if action == "tag" else "Checking captions…")
    records = (
        scan(
            config.source, config.validation, lambda n: progress(f"Inspecting images: {n:,} files")
        )
        if action == "tag"
        else (_removal_inventory(config.source, progress))
    )
    items = _plan(config.source, records, action, config.validation)
    result = Result(action, config.source, dryrun, items)
    result.log = log.event("plan", action=action, source=config.source, counts=dict(result.counts))
    for item in items:
        if item.status in {"blocked", "rejected"}:
            log.event(
                "image_skipped",
                level="error",
                image=item.image,
                reason=item.reason,
                diagnosis=asdict(diagnose(item.reason)),
            )
    ready = [item for item in items if item.status == "ready"]
    if dryrun or (not ready and not result.exit_code):
        return result

    identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + f"-{action}-" + uuid4().hex[:8]
    result.report = home / "operations" / identifier
    result.report.mkdir(parents=True)
    atomic_json(result.report / "plan.json", [asdict(item) for item in items])
    if not ready:
        _save_result(result, "completed_with_issues")
        return result
    if action == "remove":
        result.backup = result.report / "captions"
    _save_result(result, "running")
    try:
        if action == "tag":
            try:
                from image_dataset_train.tagging import tag_inventory
            except ImportError as exc:
                raise RuntimeError(
                    "Tagging runtime is missing. Run trainime doctor --fix, "
                    "or run install.cmd again if Trainime cannot start."
                ) from exc
            inventory, _ = publish_scan(config, records)
            model = bundle_path(config.models, config.tagging.model)
            progress(
                "Preparing tagger (first use downloads the model)…"
                if not (model / "model.json").exists()
                else "Checking tagger…"
            )
            from image_dataset_train.doctor import repair_model

            repair_model(home, progress, fetch=fetch_bundle)
            progress("Tagging images…")
            tagged, _ = tag_inventory(
                config,
                inventory,
                progress,
                only_sources={item.image for item in ready},
                repair_cache=True,
            )
            metadata = json.loads((tagged / "run.json").read_text(encoding="utf-8"))
            raw_manifest = (tagged / "manifest.jsonl").read_bytes()
            if hashlib.sha256(raw_manifest).hexdigest() != metadata["manifest_sha256"]:
                raise ValueError("Tagging report changed before caption publication.")
            rows = {row["source_path"]: row for row in map(json.loads, raw_manifest.splitlines())}
            atomic_json(
                result.report / "tagging.json",
                {"inventory": str(inventory), "tagging": str(tagged)},
            )
            for number, item in enumerate(ready, 1):
                row = rows[item.image]
                try:
                    if row["decision"] != "tagged":
                        raise ValueError(row.get("error", "No tags were produced."))
                    if not row["caption"].strip():
                        raise ValueError("No tags cleared the threshold; no empty caption written.")
                    _create_caption(config.source, item, row["caption"], result)
                    result.review += bool(row.get("review_flags"))
                except (OSError, ValueError) as exc:
                    result.errors.append(f"{item.image}: {exc}")
                    log.exception(exc, action=action, image=item.image, operation=result.report)
                progress(f"Writing captions: {number:,}/{len(ready):,}")
        else:
            for number, item in enumerate(ready, 1):
                try:
                    _remove_caption(config.source, item, result)
                except (OSError, ValueError) as exc:
                    result.errors.append(f"{item.caption}: {exc}")
                    log.exception(exc, action=action, caption=item.caption, operation=result.report)
                progress(f"Removing captions: {number:,}/{len(ready):,}")
    except BaseException as exc:
        result.errors.append(f"{type(exc).__name__}: {exc}")
        log.exception(exc, action=action, operation=result.report, completed=result.changed)
        _save_result(result, "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed")
        if isinstance(exc, KeyboardInterrupt):
            progress(f"Cancelled; {result.changed:,} captions completed. Report: {result.report}")
        else:
            progress(f"Stopped; {result.changed:,} captions completed. Report: {result.report}")
        raise
    _save_result(result, "completed_with_issues" if result.exit_code else "completed")
    log.event(
        "completed",
        action=action,
        changed=result.changed,
        issues=len(result.errors),
        operation=result.report,
    )
    return result


def run_directory(
    action: str, source: Path, home: Path, *, dryrun: bool = False, progress: Progress | None = None
) -> Result:
    if action not in {"tag", "remove"}:
        raise ValueError("Unknown directory action.")
    config = workflow_config(source, home)
    home = home.resolve()
    progress = progress or (lambda message: None)
    log = EventLog(home, enabled=not dryrun)
    if dryrun:
        return _execute(config, home, action, True, progress, log)
    locks = home / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(os.path.normcase(str(config.source)).encode("utf-8")).hexdigest()
    try:
        with FileLock(str(locks / f"{key}.lock"), timeout=0):
            log.event("started", action=action, source=config.source)
            return _execute(config, home, action, False, progress, log)
    except Timeout as exc:
        raise RuntimeError(
            "Another Trainime operation is using this directory or model. "
            "Let it finish, then retry."
        ) from exc
