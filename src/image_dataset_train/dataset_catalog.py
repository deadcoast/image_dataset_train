"""Verified, portable export metadata and an immutable SQLite query index.

The index describes exported occurrences; it is never a mutable review store.
Embedded catalogs share the export's media. Standalone rebuilds preserve metadata
and provenance only, and explicitly do not package the referenced images.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from image_dataset_train.annotations import annotation_fields, annotation_name
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.implementation import (
    implementation_identity,
    validate_implementation_identity,
)
from image_dataset_train.inventory import file_sha256

FORMAT = "imagefolder-sqlite-v1"
APPLICATION_ID = 0x49445443
_NO_DIGEST = object()
_COLUMNS = (
    "id",
    "source_path",
    "source_sha256",
    "image_path",
    "image_sha256",
    "caption_path",
    "caption_sha256",
    "text",
    "width",
    "height",
    "group_id",
    "split",
    "caption_origin",
    "review_decision",
    "subset",
    "record_json",
)
_SCHEMA = """
CREATE TABLE images (
    id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    image_path TEXT NOT NULL UNIQUE, image_sha256 TEXT NOT NULL,
    caption_path TEXT NOT NULL UNIQUE, caption_sha256 TEXT NOT NULL,
    text TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
    group_id TEXT NOT NULL, split TEXT NOT NULL, caption_origin TEXT NOT NULL,
    review_decision TEXT NOT NULL, subset TEXT, record_json TEXT NOT NULL
);
CREATE TABLE annotations (
    image_id TEXT NOT NULL REFERENCES images(id), label TEXT NOT NULL,
    PRIMARY KEY (image_id, label)
);
CREATE INDEX images_split ON images(split);
CREATE INDEX images_group ON images(group_id);
CREATE INDEX images_source_hash ON images(source_sha256);
CREATE INDEX images_export_hash ON images(image_sha256);
CREATE INDEX images_subset ON images(subset);
CREATE INDEX annotations_label ON annotations(label, image_id);
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _root(directory: Path) -> Path:
    directory = directory.absolute()
    if any(path.is_symlink() or path.is_junction() for path in (directory, *directory.parents)):
        raise ValueError("Catalog directories must not traverse links or junctions")
    return directory.resolve()


def _path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\0" in name:
        raise ValueError("Invalid catalog artifact path")
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in name
        or ":" in name
        or relative.as_posix() != name
    ):
        raise ValueError(f"Unsafe catalog artifact path: {name}")
    path = root / name
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Linked catalog artifact: {name}")
        if part == root:
            break
    return path


def _checked(root: Path, name: str, expected: str) -> bytes:
    raw = _path(root, name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Catalog artifact hash mismatch: {name}")
    return raw


class _CatalogReads:
    """One captured metadata view, with a content fence before it is returned."""

    def __init__(self, directory: Path):
        self.directory = _root(directory)
        self.captured: dict[str, bytes] = {}
        self.members: set[str] | None = None

    def read(self, name: str, expected: object = _NO_DIGEST) -> bytes:
        if name not in self.captured:
            self.captured[name] = (
                _path(self.directory, name).read_bytes()
                if expected is _NO_DIGEST
                else _checked(self.directory, name, expected)
            )
        raw = self.captured[name]
        if expected is not _NO_DIGEST and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"Catalog artifact hash mismatch: {name}")
        return raw

    def membership(self) -> set[str]:
        actual = set()
        for path in self.directory.rglob("*"):
            if path.is_symlink() or path.is_junction():
                raise ValueError("Linked artifact in standalone catalog")
            if path.is_file():
                actual.add(path.relative_to(self.directory).as_posix())
        return actual

    def verify(self) -> None:
        _root(self.directory)
        if self.members is not None and self.membership() != self.members:
            raise ValueError("Catalog file membership changed during inspection; retry")
        # Check the controlling metadata last, after all of its captured payload.
        for name in sorted(self.captured, key=lambda name: name == "run.json"):
            try:
                actual = file_sha256(_path(self.directory, name))
            except OSError as exc:
                raise ValueError(
                    f"Catalog changed during inspection: {name}; retry ({exc})"
                ) from exc
            if actual != hashlib.sha256(self.captured[name]).hexdigest():
                raise ValueError(f"Catalog changed during inspection: {name}; retry")
        _root(self.directory)


def _rows(raw: bytes) -> list[dict]:
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Catalog requires nonempty export records")
    return rows


def _ordered(rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Catalog requires nonempty export records")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Catalog export records must be objects")
        for key in ("id", "sha256", "image_sha256", "caption_sha256", "group_id"):
            value = row.get(key)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise ValueError(f"Invalid catalog {key}")
        if row["id"] in seen:
            raise ValueError("Repeated catalog occurrence")
        seen.add(row["id"])
        if row.get("split") not in {"train", "validation"}:
            raise ValueError("Invalid catalog split")
        for name in ("source_path", "image_path", "caption_path"):
            # Validate spelling, not filesystem existence; metadata-only indexes have no media.
            value = row.get(name)
            if not isinstance(value, str) or not value or "\0" in value:
                raise ValueError(f"Invalid catalog {name}")
            relative = PurePosixPath(value)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in value
                or ":" in value
                or relative.as_posix() != value
            ):
                raise ValueError(f"Unsafe catalog {name}")
        image = PurePosixPath(row["image_path"])
        if (
            image.parent.as_posix() != row["split"]
            or image.stem != row["id"]
            or image.with_suffix(".txt").as_posix() != row["caption_path"]
        ):
            raise ValueError("Invalid catalog image/caption pairing")
        if (
            not isinstance(row.get("caption"), str)
            or not row["caption"].strip()
            or "\0" in row["caption"]
        ):
            raise ValueError("Catalog captions must be nonempty text")
        if any(type(row.get(key)) is not int or row[key] < 1 for key in ("width", "height")):
            raise ValueError("Invalid catalog dimensions")
        if row.get("review_decision") != "include" or not isinstance(
            row.get("caption_origin"), dict
        ):
            raise ValueError("Catalog requires exported inclusion and caption provenance")
        annotation_fields(row)
    return sorted(rows, key=lambda row: row["id"])


def _descriptor(rows: list[dict]) -> dict:
    counts = dict(sorted(Counter(row["split"] for row in rows).items()))
    return {
        "schema_version": 1,
        "format": FORMAT,
        "database": "catalog.sqlite",
        "metadata": {split: f"{split}/metadata.jsonl" for split in counts},
        "rows_sha256": hashlib.sha256(_json(rows).encode("utf-8")).hexdigest(),
        "images": len(rows),
        "split_images": counts,
    }


def _imagefolder(row: dict) -> dict:
    annotations = annotation_fields(row)
    record = {
        "file_name": PurePosixPath(row["image_path"]).name,
        "text": row["caption"],
        "id": row["id"],
        "source_path": row["source_path"],
        "source_sha256": row["sha256"],
        "image_sha256": row["image_sha256"],
        "caption_sha256": row["caption_sha256"],
        "width": row["width"],
        "height": row["height"],
        "group_id": row["group_id"],
        "split": row["split"],
        "caption_origin": str(row["caption_origin"].get("kind", "unspecified")),
        "caption_origin_json": _json(row["caption_origin"]),
        "review_decision": row["review_decision"],
        "decision_origin_json": _json(row.get("decision_origin")),
        "review_annotations_json": _json(
            {
                **annotations,
                "annotation_version": row.get("annotation_version"),
                "annotation_reason": row.get("annotation_reason"),
                "subset_origin": row.get("subset_origin"),
            }
        ),
        "model_observations_json": _json(row.get("caption_analysis")),
        "preparation_json": _json(
            {key: value for key, value in row.items() if key.startswith("preparation")}
        ),
    }
    # Earlier catalog-v1 exports predate derivative caption adjustments. Preserve
    # their exact projection while exposing the new export's explicit provenance.
    if "source_caption" in row:
        record["source_caption"] = row["source_caption"]
    if "caption_transforms" in row:
        record["caption_transforms_json"] = _json(row["caption_transforms"])
    return record


def _values(row: dict) -> tuple:
    return (
        row["id"],
        row["source_path"],
        row["sha256"],
        row["image_path"],
        row["image_sha256"],
        row["caption_path"],
        row["caption_sha256"],
        row["caption"],
        row["width"],
        row["height"],
        row["group_id"],
        row["split"],
        str(row["caption_origin"].get("kind", "unspecified")),
        row["review_decision"],
        annotation_fields(row)["subset"],
        _json(row),
    )


def write_catalog(directory: Path, rows: list[dict]) -> dict:
    """Write new catalog payload into unpublished staging; never replace existing files."""
    directory = _root(directory)
    if (directory / "run.json").exists():
        raise ValueError("Catalog writer requires unpublished staging without run.json")
    rows = _ordered(rows)
    descriptor = _descriptor(rows)
    files = [descriptor["database"], *descriptor["metadata"].values()]
    if any(_path(directory, name).exists() for name in files):
        raise ValueError("Catalog already exists; publish a new artifact instead")
    directory.mkdir(parents=True, exist_ok=True)
    for split, name in descriptor["metadata"].items():
        target = _path(directory, name)
        target.parent.mkdir(exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                if row["split"] == split:
                    stream.write(_json(_imagefolder(row)) + "\n")
    database = _path(directory, descriptor["database"])
    database.touch(exist_ok=False)
    connection = sqlite3.connect(database)
    try:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        with connection:
            connection.executemany(
                f"INSERT INTO images VALUES ({','.join('?' for _ in _COLUMNS)})",
                [_values(row) for row in rows],
            )
            connection.executemany(
                "INSERT INTO annotations VALUES (?, ?)",
                [(row["id"], label) for row in rows for label in annotation_fields(row)["labels"]],
            )
    finally:
        connection.close()
    return descriptor


def _connect(database: Path, *, captured: bytes | None = None) -> sqlite3.Connection:
    # The captured database is the same byte sequence whose checksum and contents
    # are verified. Later path replacement cannot change rows between validation
    # and querying, including a transient replacement restored before the fence.
    connection = sqlite3.connect(
        ":memory:" if captured is not None else database.as_uri() + "?mode=ro",
        uri=captured is None,
    )
    if captured is not None:
        try:
            connection.deserialize(captured)
        except sqlite3.Error:
            connection.close()
            raise
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA trusted_schema = OFF")
    return connection


def verify_catalog_payload(
    directory: Path,
    descriptor: dict,
    rows: list[dict],
    *,
    _captured: dict[str, bytes] | None = None,
) -> dict:
    """Reconcile every indexed field and metadata row with the authoritative export rows.

    The owning export/catalog verifier checks file hashes before calling this helper.
    This also detects an inconsistent derived index whose checksum was recomputed.
    """
    directory = _root(directory)
    rows = _ordered(rows)
    if descriptor != _descriptor(rows):
        raise ValueError("Catalog descriptor differs from export manifest")
    reads = _CatalogReads(directory) if _captured is None else None
    captured = (
        {
            name: reads.read(name)
            for name in [descriptor["database"], *descriptor["metadata"].values()]
        }
        if reads is not None
        else _captured
    )
    for split, name in descriptor["metadata"].items():
        expected = [_imagefolder(row) for row in rows if row["split"] == split]
        if _rows(captured[name]) != expected:
            raise ValueError(f"Catalog ImageFolder metadata differs from export manifest: {split}")
    try:
        connection = _connect(
            _path(directory, descriptor["database"]), captured=captured[descriptor["database"]]
        )
        try:
            if (
                connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise ValueError("Unsupported catalog database version")
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Catalog SQLite integrity check failed")
            schema = connection.execute(
                "SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            expected_schema = {
                ("table", "images"),
                ("table", "annotations"),
                *(
                    ("index", name)
                    for name in (
                        "images_split",
                        "images_group",
                        "images_source_hash",
                        "images_export_hash",
                        "images_subset",
                        "annotations_label",
                    )
                ),
            }
            if set(schema) != expected_schema:
                raise ValueError("Unexpected catalog database schema")
            if tuple(
                row[1] for row in connection.execute("PRAGMA table_info(images)")
            ) != _COLUMNS or tuple(
                row[1] for row in connection.execute("PRAGMA table_info(annotations)")
            ) != ("image_id", "label"):
                raise ValueError("Unexpected catalog database columns")
            actual = connection.execute(
                f"SELECT {','.join(_COLUMNS)} FROM images ORDER BY id"
            ).fetchall()
            if actual != [_values(row) for row in rows]:
                raise ValueError("Catalog database differs from export manifest")
            actual_labels = connection.execute(
                "SELECT image_id, label FROM annotations ORDER BY image_id, label"
            ).fetchall()
            expected_labels = [
                (row["id"], label) for row in rows for label in annotation_fields(row)["labels"]
            ]
            if actual_labels != expected_labels:
                raise ValueError("Catalog annotations differ from explicit review annotations")
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Invalid catalog database: {exc}") from exc
    if reads is not None:
        reads.verify()
    return {
        "images": len(rows),
        "groups": len({row["group_id"] for row in rows}),
        "split_images": descriptor["split_images"],
        "caption_origins": dict(
            sorted(
                Counter(row["caption_origin"].get("kind", "unspecified") for row in rows).items()
            )
        ),
        "decision_origins": dict(
            sorted(
                Counter(
                    (row.get("decision_origin") or {}).get("kind", "unspecified") for row in rows
                ).items()
            )
        ),
        "annotation_labels": dict(
            sorted(
                Counter(label for row in rows for label in annotation_fields(row)["labels"]).items()
            )
        ),
        "model_observations": sum(row.get("caption_analysis") is not None for row in rows),
    }


def build_catalog(export_run: Path, *, output_root: Path) -> tuple[Path, dict]:
    """Publish a metadata-only index of an existing verified export, without altering it."""
    from image_dataset_train.exporting import verify_export

    implementation = implementation_identity()
    export_run, output_root = _root(export_run), _root(output_root)
    export_reads = _CatalogReads(export_run)
    raw_meta = export_reads.read("run.json")
    metadata = json.loads(raw_meta)
    captured = {name: export_reads.read(name, digest) for name, digest in metadata["files"].items()}
    verify_export(export_run)
    export_reads.verify()
    if not isinstance(metadata.get("source"), str) or not Path(metadata["source"]).is_absolute():
        raise ValueError("Export is missing its absolute source identity")
    source = Path(metadata["source"]).resolve()
    if (
        output_root.is_relative_to(export_run)
        or output_root.is_relative_to(source)
        or source.is_relative_to(output_root)
    ):
        raise ValueError("Catalog output must be separate from source and frozen export artifacts")
    manifest = captured["manifest.jsonl"]
    provenance = {name: raw for name, raw in captured.items() if name.startswith("provenance/")}
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-catalog-", dir=output_root))
    descriptor = write_catalog(staging, _rows(manifest))
    (staging / "export-run.json").write_bytes(raw_meta)
    (staging / "export-manifest.jsonl").write_bytes(manifest)
    for name, raw in provenance.items():
        path = _path(staging, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-catalog-" + uuid4().hex[:8]
    meta = {
        "schema_version": 1,
        "stage": "dataset_catalog",
        "implementation": implementation,
        "status": "completed",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "export_run": str(export_run),
        "export_run_sha256": hashlib.sha256(raw_meta).hexdigest(),
        "media_packaged": False,
        "catalog": descriptor,
        "files": {
            path.relative_to(staging).as_posix(): file_sha256(path)
            for path in staging.rglob("*")
            if path.is_file()
        },
    }
    atomic_json(staging / "run.json", meta)
    # Verify the frozen metadata before publication, independent of source availability.
    summary = _read_catalog(staging, allow_staging=True)
    export_reads.verify()
    final = output_root / run_id
    publish_directory(staging, final)
    summary["catalog"] = str(final)
    return final, summary


def _load_catalog(directory: Path, *, allow_staging: bool = False) -> tuple[dict, _CatalogReads]:
    reads = _CatalogReads(directory)
    directory = reads.directory
    raw_meta = reads.read("run.json")
    meta = json.loads(raw_meta)
    if "implementation" in meta:
        validate_implementation_identity(meta["implementation"])
    if (
        not isinstance(meta, dict)
        or meta.get("schema_version") != 1
        or meta.get("status") != "completed"
        or meta.get("stage") not in {"export", "dataset_catalog"}
        or not allow_staging
        and directory.name.startswith(".pending-")
    ):
        raise ValueError("Expected a published export or dataset catalog")
    descriptor = meta.get("catalog")
    if not isinstance(descriptor, dict):
        raise ValueError(
            "Export has no catalog; use catalog-build to create a separate metadata index"
        )
    files = meta.get("files")
    if not isinstance(files, dict):
        raise ValueError("Catalog is missing artifact checksums")
    # Verify all frozen non-media metadata, including review and preparation provenance.
    captured = {name: reads.read(name, digest) for name, digest in files.items()}
    embedded = meta["stage"] == "export"
    if embedded:
        required = {
            "manifest.jsonl",
            "provenance/groups.jsonl",
            "provenance/reviews.json",
            "provenance/groups-run.json",
            "provenance/summary.json",
        }
        if not required <= files.keys():
            raise ValueError("Export catalog is missing frozen provenance")
        rows = _rows(captured["manifest.jsonl"])
        export_meta, export_digest = meta, hashlib.sha256(raw_meta).hexdigest()
    else:
        if meta.get("media_packaged") is not False:
            raise ValueError("Standalone catalog must declare that media is not packaged")
        export_raw = captured.get("export-run.json", b"")
        if hashlib.sha256(export_raw).hexdigest() != meta.get("export_run_sha256"):
            raise ValueError("Catalog export provenance hash mismatch")
        export_meta = json.loads(export_raw)
        if (
            export_meta.get("stage") != "export"
            or export_meta.get("schema_version") != 1
            or export_meta.get("status") != "completed"
        ):
            raise ValueError("Catalog requires published export provenance")
        expected = {
            "export-run.json",
            "export-manifest.jsonl",
            descriptor.get("database"),
            *descriptor.get("metadata", {}).values(),
        }
        expected.update(name for name in export_meta["files"] if name.startswith("provenance/"))
        if set(files) != expected:
            raise ValueError("Catalog provenance file membership mismatch")
        for name in expected - {
            "export-run.json",
            descriptor.get("database"),
            *descriptor.get("metadata", {}).values(),
        }:
            original_name = "manifest.jsonl" if name == "export-manifest.jsonl" else name
            if hashlib.sha256(captured[name]).hexdigest() != export_meta["files"][original_name]:
                raise ValueError(f"Catalog differs from frozen export provenance: {name}")
        actual = reads.membership()
        if actual != set(files) | {"run.json"}:
            raise ValueError("Catalog has untracked or missing files")
        reads.members = actual
        rows = _rows(captured["export-manifest.jsonl"])
        export_digest = meta["export_run_sha256"]
    required_payload = {
        "catalog.sqlite",
        *(f"{split}/metadata.jsonl" for split in {row["split"] for row in rows}),
    }
    if not required_payload <= files.keys():
        raise ValueError("Catalog payload is not checksum-bound")
    summary = verify_catalog_payload(directory, descriptor, rows, _captured=captured)
    return {
        "catalog": str(directory),
        "format": FORMAT,
        "media_packaged": embedded,
        "catalog_sha256": files["catalog.sqlite"],
        "export_run_id": export_meta.get("run_id"),
        "export_run_sha256": export_digest,
        "media_locator": "." if embedded else meta.get("export_run"),
        "verification_scope": "catalog_and_metadata",
        "media_reverified": False,
        "acceptance": "not established by catalog",
        **summary,
    }, reads


def _read_catalog(directory: Path, *, allow_staging: bool = False) -> dict:
    summary, reads = _load_catalog(directory, allow_staging=allow_staging)
    reads.verify()
    return summary


def read_catalog(directory: Path) -> dict:
    """Verify frozen metadata and return its summary without requiring a config or source."""
    try:
        return _read_catalog(directory)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed catalog: {exc}") from exc


def query_catalog(
    directory: Path,
    *,
    split: str | None = None,
    group_id: str | None = None,
    label: str | None = None,
    text: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return exact exported records using bounded filters, never caller-supplied SQL."""
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(offset) is not int
        or not 0 <= offset <= 2**63 - 1
    ):
        raise ValueError("Catalog limit must be 1..1000 and offset a nonnegative 64-bit integer")
    if split is not None and split not in {"train", "validation"}:
        raise ValueError("Catalog split must be train or validation")
    for value in (group_id, text):
        if value is not None and (not isinstance(value, str) or not value or "\0" in value):
            raise ValueError("Catalog filters must be nonempty text without NUL characters")
    if label is not None:
        label = annotation_name(label)
    try:
        _, reads = _load_catalog(directory)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed catalog: {exc}") from exc
    directory = reads.directory
    database = _path(directory, "catalog.sqlite")
    clauses, parameters = [], []
    for column, value in (("split", split), ("group_id", group_id)):
        if value is not None:
            clauses.append(f"i.{column} = ?")
            parameters.append(value)
    if label is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM annotations a WHERE a.image_id = i.id AND a.label = ?)"
        )
        parameters.append(label)
    if text is not None:
        clauses.append("instr(lower(i.text), lower(?)) > 0")
        parameters.append(text)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    try:
        connection = _connect(database, captured=reads.captured["catalog.sqlite"])
        try:
            result = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT i.record_json FROM images i"
                    + where
                    + " ORDER BY i.id LIMIT ? OFFSET ?",
                    [*parameters, limit, offset],
                )
            ]
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Invalid catalog database: {exc}") from exc
    reads.verify()
    return result
