"""Explicit local preparation collections; registration never discovers image trees."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from image_dataset_train.diagnostics import app_home, atomic_json


def path_key(path: str | Path) -> str:
    """Compare recorded absolute locations without requiring their source to exist."""
    return os.path.normcase(os.path.normpath(str(path)))


def unlinked_path(path: Path) -> Path:
    path = path.expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Linked collection path is not supported: {path}")
    return path.resolve()


def read_object(path: Path) -> tuple[dict, str]:
    path = unlinked_path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(f"Collection metadata is too large: {path}")
    raw = path.read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError(f"Collection metadata is too large: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected collection metadata object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def collection_id(workspace: str | Path) -> str:
    return hashlib.sha256(path_key(workspace).encode("utf-8")).hexdigest()


def _name(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 120
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("Collection name must be nonempty text of at most 120 characters")
    if len(value.strip()) == 64 and all(c in "0123456789abcdef" for c in value.strip().lower()):
        raise ValueError("Collection name must not resemble a collection identifier")
    return value.strip()


def validate_entry(entry: object) -> None:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"id", "name", "workspace", "source", "registered_at"}
        or any(
            not isinstance(entry.get(key), str) or not Path(entry[key]).is_absolute()
            for key in ("workspace", "source")
        )
        or entry["id"] != collection_id(entry["workspace"])
        or _name(entry["name"]) != entry["name"]
        or not isinstance(entry["registered_at"], str)
    ):
        raise ValueError("Invalid collection registry entry; preserve the registry before recovery")
    try:
        if datetime.fromisoformat(entry["registered_at"]).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Invalid collection registration timestamp") from exc


class CollectionRegistry:
    def __init__(self, root: Path | None = None):
        self.root = (Path(root) if root is not None else app_home()).expanduser().absolute()
        self.path = self.root / "collections.json"

    def read(self) -> dict:
        path = unlinked_path(self.path)
        if not path.exists():
            return {"schema_version": 1, "revision": 0, "collections": []}
        document, _ = read_object(path)
        if (
            set(document) != {"schema_version", "revision", "collections"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or type(document["revision"]) is not int
            or document["revision"] < 0
            or not isinstance(document["collections"], list)
        ):
            raise ValueError("Invalid collection registry; preserve it before recovery")
        identifiers, names = set(), set()
        for entry in document["collections"]:
            validate_entry(entry)
            name = entry["name"].casefold() if entry["name"] else None
            if entry["id"] in identifiers or (name and name in names):
                raise ValueError("Duplicate collection identity or name in registry")
            identifiers.add(entry["id"])
            if name:
                names.add(name)
        if identifiers & names:
            raise ValueError("Collection names and identifiers are ambiguous")
        return document

    def list(self, source: str | Path | None = None) -> list[dict]:
        entries = self.read()["collections"]
        if source is not None:
            source = Path(source).expanduser().absolute()
            entries = [entry for entry in entries if path_key(entry["source"]) == path_key(source)]
        return sorted(entries, key=lambda entry: ((entry["name"] or "").casefold(), entry["id"]))

    @staticmethod
    def _resolve(entries: list[dict], selector: str) -> dict:
        if not isinstance(selector, str) or not selector:
            raise ValueError("Choose an exact collection ID or registered name")
        matches = [
            entry
            for entry in entries
            if selector == entry["id"]
            or (entry["name"] is not None and selector.casefold() == entry["name"].casefold())
        ]
        if len(matches) != 1:
            raise ValueError("Collection selector is unknown or ambiguous")
        return matches[0]

    def resolve(self, selector: str) -> dict:
        return self._resolve(self.read()["collections"], selector)

    def _guard(self) -> FileLock:
        root = unlinked_path(self.root)
        unlinked_path(root / "collections.lock")
        self.read()  # Fail before creating anything when an existing registry is corrupt.
        root.mkdir(parents=True, exist_ok=True)
        return FileLock(str(root / "collections.lock"), timeout=0)

    def register(self, workspace: Path, name: str | None = None) -> dict:
        from image_dataset_train.preparation import read_preparation_job

        workspace = unlinked_path(Path(workspace))
        _, state = read_preparation_job(workspace)
        name = _name(name)
        root = unlinked_path(self.root)
        source = Path(state["source"])
        if root.is_relative_to(workspace) or root.is_relative_to(source):
            raise ValueError("Collection registry must be outside source and preparation artifacts")
        identifier = collection_id(workspace)
        try:
            with self._guard():
                document = self.read()
                entries = document["collections"]
                existing = next((entry for entry in entries if entry["id"] == identifier), None)
                if existing and path_key(existing["source"]) != path_key(source):
                    raise ValueError("Registered workspace source identity changed")
                selected_name = name if name is not None else existing["name"] if existing else None
                if selected_name and any(
                    selected_name.casefold() in {entry["id"], (entry["name"] or "").casefold()}
                    for entry in entries
                    if entry["id"] != identifier
                ):
                    raise ValueError("Collection name is already registered")
                if selected_name and selected_name.casefold() == identifier:
                    raise ValueError("Collection name must differ from its identifier")
                entry = {
                    "id": identifier,
                    "name": selected_name,
                    "workspace": str(workspace),
                    "source": str(source),
                    "registered_at": existing["registered_at"]
                    if existing
                    else datetime.now(UTC).isoformat(),
                }
                if existing == entry:
                    return entry
                document["collections"] = [e for e in entries if e["id"] != identifier] + [entry]
                document["revision"] += 1
                atomic_json(self.path, document)
                return entry
        except Timeout as exc:
            raise ValueError("Another collection registration is running; retry") from exc

    def remove(self, selector: str) -> dict:
        # Removing a registration never opens or changes the registered workspace.
        self.resolve(selector)
        try:
            with self._guard():
                document = self.read()
                entry = self._resolve(document["collections"], selector)
                document["collections"] = [
                    item for item in document["collections"] if item["id"] != entry["id"]
                ]
                document["revision"] += 1
                atomic_json(self.path, document)
                return entry
        except Timeout as exc:
            raise ValueError("Another collection registration is running; retry") from exc
