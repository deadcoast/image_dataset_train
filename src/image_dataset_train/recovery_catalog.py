"""Read owned recovery metadata without opening workers or inspecting source files."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime
from pathlib import Path, PurePosixPath

from image_dataset_train.diagnostics import app_home

KINDS = frozenset({"removal", "collision", "restore", "package"})
MAX_METADATA_BYTES = 64 * 1024 * 1024


def _key(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _hash(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {label} in recovery metadata")
    return value


def _absolute(value: object, label: str) -> Path:
    path = Path(_text(value, label))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected an absolute {label} in recovery metadata")
    return path


def _relative(value: object, *, directory: bool = False) -> str:
    if value == "." and directory:
        return "."
    value = _text(value, "relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} or part.rstrip(". ") != part for part in value.split("/"))
    ):
        raise ValueError("Unsafe relative path in recovery metadata")
    return value


def _unlinked(path: Path, home: Path) -> None:
    if not path.is_relative_to(home):
        raise ValueError("Recovery metadata escapes the application home")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Linked recovery path is not supported: {path}")


def _read(path: Path, home: Path) -> tuple[object, str]:
    _unlinked(path, home)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_METADATA_BYTES:
        raise ValueError(f"Recovery metadata is not a bounded regular file: {path}")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise ValueError("Recovery metadata changed while opening")
        raw = stream.read(MAX_METADATA_BYTES + 1)
    _unlinked(path, home)
    after = path.stat()
    if len(raw) > MAX_METADATA_BYTES or (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise ValueError("Recovery metadata changed or exceeded its size bound")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _rows(value: object) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Invalid recovery item list")
    return value


def _optional_hash(value: object) -> str | None:
    if value is not None and not _hash(value):
        raise ValueError("Invalid recorded recovery content hash")
    return value


def _source(document: dict, home: Path) -> Path:
    source = _absolute(document.get("source"), "source")
    if source.is_relative_to(home) or home.is_relative_to(source):
        raise ValueError("Source and application recovery must be separate trees")
    return source


def _removal(document: dict, receipt: Path, home: Path, inputs: dict) -> tuple[list, list]:
    source = _source(document, home)
    backup = receipt.parent / "captions"
    if document.get("backup") not in (None, str(backup)):
        raise ValueError("Removal backup does not match its operation directory")
    plan = receipt.parent / "plan.json"
    rows, digest = _read(plan, home)
    expected = _optional_hash(document.get("plan_sha256"))
    if expected is not None and expected != digest:
        raise ValueError("Removal plan hash mismatch")
    _optional_hash(document.get("journal_sha256"))
    inputs[str(plan)] = digest
    items, seen = [], set()
    for row in _rows(rows):
        image, caption = _relative(row.get("image")), _relative(row.get("caption"))
        image_path, caption_path = PurePosixPath(image), PurePosixPath(caption)
        if (
            image_path.parent != caption_path.parent
            or image_path.stem.casefold() != caption_path.stem.casefold()
            or caption_path.suffix.lower() != ".txt"
            or image.casefold() in seen
        ):
            raise ValueError("Invalid or duplicate removal association")
        seen.add(image.casefold())
        items.append(
            {
                "path": caption,
                "image": image,
                "target": str(source / caption),
                "backup": str(backup / caption) if document.get("backup") else None,
                "recorded_status": _text(row.get("status"), "item status"),
                "sha256": _optional_hash(row.get("caption_sha256")),
                "image_sha256": _optional_hash(row.get("image_sha256")),
            }
        )
    warnings = [
        "Plan status is historical; journal progress and backup contents were not verified."
    ]
    if expected is None:
        warnings.append(
            "Legacy removal receipt has no saved plan hash; "
            "current plan bytes identify this listing."
        )
    return items, warnings


def _collision(document: dict, receipt: Path, home: Path) -> list[dict]:
    source = _source(document, home)
    if document.get("fix_code") != "tf001":
        raise ValueError("Unsupported collision repair code")
    items, seen = [], set()
    for group in _rows(document.get("groups")):
        directory = PurePosixPath(_relative(group.get("directory"), directory=True))
        _text(group.get("stem"), "collision stem")
        for action in _rows(group.get("actions")):
            original, target = _relative(action.get("source")), _relative(action.get("target"))
            kind = action.get("kind")
            if (
                kind not in {"caption", "image"}
                or type(action.get("done")) is not bool
                or not _hash(action.get("sha256"))
                or PurePosixPath(original).parent != directory
                or original in seen
                or (
                    kind == "caption"
                    and (target != original or PurePosixPath(original).suffix.lower() != ".txt")
                )
                or (
                    kind == "image"
                    and (
                        PurePosixPath(target).parent != directory
                        or PurePosixPath(target).suffix != PurePosixPath(original).suffix
                        or PurePosixPath(target).stem.casefold()
                        == PurePosixPath(original).stem.casefold()
                    )
                )
            ):
                raise ValueError("Invalid collision recovery action")
            seen.add(original)
            backup = receipt.parent / "captions" / target if kind == "caption" else None
            items.append(
                {
                    "path": original,
                    "target": str(backup or source / target),
                    "backup": str(backup) if backup else None,
                    "kind": kind,
                    "sha256": action["sha256"],
                    "recorded_status": "done" if action["done"] else "pending",
                }
            )
        retained = group.get("retained", [])
        if not isinstance(retained, list):
            raise ValueError("Invalid retained collision paths")
        for path in retained:
            relative = _relative(path)
            if PurePosixPath(relative).parent != directory:
                raise ValueError("Retained collision path is outside its group")
            items.append(
                {
                    "path": relative,
                    "target": str(source / relative),
                    "backup": None,
                    "recorded_status": "retained",
                }
            )
    return items


def _restore(document: dict, receipt: Path, home: Path) -> tuple[list, str]:
    source = _source(document, home)
    if _key(_absolute(document.get("home"), "restoration home")) != _key(home):
        raise ValueError("Restoration home does not match the selected application home")
    original = _absolute(document.get("removal_receipt"), "removal receipt")
    if original.name != "operation.json" or original.parent.parent != home / "operations":
        raise ValueError("Restoration does not reference an owned removal receipt")
    items = []
    for row in _rows(document.get("items")):
        image, caption = _relative(row.get("image")), _relative(row.get("caption"))
        backup = original.parent / "captions" / caption
        if row.get("backup") != str(backup):
            raise ValueError("Restoration backup does not match its removal operation")
        items.append(
            {
                "path": caption,
                "image": image,
                "target": str(source / caption),
                "backup": str(backup),
                "recorded_status": _text(row.get("status"), "item status"),
                "sha256": _optional_hash(row.get("caption_sha256")),
                "image_sha256": _optional_hash(row.get("image_sha256")),
            }
        )
    return items, str(original)


def _package(document: dict, receipt: Path) -> list[dict]:
    site = _absolute(document.get("site_packages"), "package location")
    _absolute(document.get("wheel"), "repair wheel")
    if not _hash(document.get("wheel_sha256")):
        raise ValueError("Invalid repair wheel hash")
    items, seen = [], set()
    for row in _rows(document.get("files")):
        path = _relative(row.get("path"))
        if (
            len(PurePosixPath(path).parts) < 2
            or PurePosixPath(path).parts[0] != "image_dataset_train"
            or path.casefold() in seen
        ):
            raise ValueError("Invalid or duplicate package recovery path")
        seen.add(path.casefold())
        backup = row.get("backup")
        if backup not in (None, path) or not _hash(row.get("expected_sha256")):
            raise ValueError("Invalid package backup or expected hash")
        items.append(
            {
                "path": path,
                "target": str(site / path),
                "backup": str(receipt.parent / path) if backup else None,
                "recorded_status": _text(row.get("status"), "item status"),
                "before_sha256": _optional_hash(row.get("before_sha256")),
                "expected_sha256": row["expected_sha256"],
            }
        )
    return items


def _record(receipt: Path, home: Path) -> dict | None:
    document, digest = _read(receipt, home)
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("Unsupported recovery receipt schema")
    kind = {
        "operation.json": "removal",
        "fix.json": "collision",
        "restore.json": "restore",
        "repair.json": "package",
    }[receipt.name]
    if kind == "removal" and document.get("action") != "remove":
        return None
    if (
        kind in {"restore", "package"}
        and document.get("action")
        != {"restore": "restore_captions", "package": "repair_package"}[kind]
    ):
        raise ValueError("Receipt action does not match its recovery layout")
    inputs = {str(receipt): digest}
    warnings = ["Recorded status does not establish process liveness or current recovery need."]
    extra = {}
    if kind == "removal":
        items, additional = _removal(document, receipt, home, inputs)
        warnings.extend(additional)
    elif kind == "collision":
        items = _collision(document, receipt, home)
        extra["fix_code"] = document["fix_code"]
        warnings.append(
            "Collision retry may inspect all pending repairs and new collisions in the source; "
            "it is not an undo."
        )
    elif kind == "restore":
        items, extra["original_receipt"] = _restore(document, receipt, home)
    else:
        items = _package(document, receipt)
        extra.update(wheel=document["wheel"], site_packages=document["site_packages"])
    created = next(
        (
            document[key]
            for key in ("started_at", "updated_at", "completed_at")
            if document.get(key) is not None
        ),
        None,
    )
    if created is not None:
        if not isinstance(created, str) or datetime.fromisoformat(created).tzinfo is None:
            raise ValueError("Invalid recorded recovery timestamp")
    identity = json.dumps(
        {"receipt": _key(receipt), "inputs": {_key(path): value for path, value in inputs.items()}},
        sort_keys=True,
        separators=(",", ":"),
    )
    locations = {str(receipt.parent)}
    locations.update(str(Path(item["backup"]).parent) for item in items if item.get("backup"))
    return {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "receipt": str(receipt),
        "receipt_sha256": digest,
        "metadata_inputs": inputs,
        "kind": kind,
        "status": _text(document.get("status"), "status"),
        "source": str(_source(document, home)) if kind != "package" else None,
        "created_at": created,
        "affected_count": len(items),
        "items": items,
        "recovery_locations": sorted(locations),
        "warnings": warnings,
        "home": str(home),
        "metadata_verification": "metadata_only",
        "source_revalidated": False,
        **extra,
    }


def list_recovery(home: Path | None = None, *, source=None, kind=None, status=None) -> dict:
    """List only known application-owned receipt layouts; never inspect source bytes."""
    if kind is not None and kind not in KINDS:
        raise ValueError("Unknown recovery kind")
    if status is not None:
        _text(status, "status filter")
    home = (
        Path(home if home is not None else os.environ.get("TRAINIME_HOME") or app_home())
        .expanduser()
        .absolute()
    )
    source_key = _key(Path(source).expanduser().absolute()) if source is not None else None
    records, errors = [], []

    def error(path, exc):
        errors.append({"path": str(path), "error": str(exc), "type": type(exc).__name__})

    for root, names in [
        (home / "operations", ("operation.json", "fix.json", "restore.json")),
        (home / "recovery" / "application", ("repair.json",)),
    ]:
        try:
            _unlinked(root, home)
            if not root.exists():
                continue
            children = sorted(root.iterdir(), key=lambda p: (p.name.casefold(), p.name))
        except (OSError, ValueError) as exc:
            error(root, exc)
            continue
        for child in children:
            try:
                _unlinked(child, home)
                if not child.is_dir():
                    continue
            except (OSError, ValueError) as exc:
                error(child, exc)
                continue
            for name in names:
                receipt = child / name
                try:
                    _unlinked(receipt, home)
                    if not receipt.exists():
                        continue
                    record = _record(receipt, home)
                    if (
                        record is None
                        or (kind is not None and record["kind"] != kind)
                        or (status is not None and record["status"] != status)
                        or (source_key is not None and _key(record["source"] or "") != source_key)
                    ):
                        continue
                    records.append(record)
                except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
                    error(receipt, exc)
    records.sort(key=lambda r: (r["created_at"] or "", r["receipt"]), reverse=True)
    return {
        "home": str(home),
        "records": records,
        "errors": errors,
        "metadata_verification": "metadata_only",
        "source_revalidated": False,
    }


def select_recovery(
    home: Path | None, record_id: str, *, expected_sha256: str | None = None
) -> dict:
    """Select exact current metadata, including the removal plan when applicable."""
    if not _hash(record_id) or (expected_sha256 is not None and not _hash(expected_sha256)):
        raise ValueError("Choose an exact recovery record ID and valid expected checksum")
    snapshot = list_recovery(home)
    matches = [record for record in snapshot["records"] if record["id"] == record_id]
    if len(matches) != 1:
        raise ValueError("Recovery record is missing, changed or unavailable; refresh the listing")
    record = _record(Path(matches[0]["receipt"]), Path(snapshot["home"]))
    if (
        record is None
        or record["id"] != record_id
        or (expected_sha256 is not None and record["receipt_sha256"] != expected_sha256)
    ):
        raise ValueError("Recovery metadata changed; refresh the listing")
    return record
