"""Report-scoped browsing preferences, separate from all review evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

from filelock import FileLock, Timeout

from image_dataset_train.diagnostics import app_home, atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reviews import ReviewConflict

MAX_BYTES = 64 * 1024
FILTER_FIELDS = {
    "finding": "findings",
    "label": "labels",
    "subset": "subset",
    "split": "split",
    "decision": "decision",
}
FILTER_KEYS = {*FILTER_FIELDS, "search", "pilot", "group"}
PAIR_DECISIONS = {"all", "unreviewed", "related", "distinct"}


def empty_filters() -> dict:
    return {**dict.fromkeys(FILTER_FIELDS, ""), "search": "", "pilot": False, "group": ""}


def _object(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"Invalid {name} fields")


def _integer(value, name, *, maximum=1_000_000_000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Invalid {name}")


def _text(value, maximum, name):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise ValueError(f"Invalid {name}")


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _unlinked(path: Path) -> Path:
    path = path.expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked browsing preference paths are not supported")
    if path.is_file() and path.stat().st_nlink > 1:
        raise ValueError("Linked browsing preference files are not supported")
    return path.resolve()


class ReviewPreferences:
    def __init__(self, config, run: Path, report_sha256: str, data: dict, root=None):
        if not _identifier(report_sha256):
            raise ValueError("Invalid browsing report digest")
        self.run = Path(run).absolute()
        self.report_sha256 = report_sha256
        identity = os.path.normcase(str(self.run.resolve())) + "\0" + report_sha256
        self.report_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        home = root if root is not None else os.environ.get("TRAINIME_HOME") or app_home()
        self.directory = Path(home).expanduser().absolute() / "review-preferences"
        self.path = self.directory / (self.report_id + ".json")
        self.lock_path = self.directory / (self.report_id + ".lock")
        self.protected = tuple(
            Path(p).resolve()
            for p in (
                config.source,
                config.runs,
                config.reviews,
                config.exports,
                config.scores,
                config.models,
                self.run,
            )
        )
        self.image_ids = {entry["id"] for entry in data["entries"]}
        self.groups = {entry["group_id"] for entry in data["entries"]}
        self.values = {name: set() for name in FILTER_FIELDS}
        for entry in data["entries"]:
            for name, field in FILTER_FIELDS.items():
                value = entry[field]
                self.values[name].update(value if isinstance(value, list) else [value])

    def empty(self) -> dict:
        return {
            "schema_version": 1,
            "report_id": self.report_id,
            "revision": 0,
            "last": {
                "filters": empty_filters(),
                "image_id": None,
                "position": 0,
                "pair": {"decision": "unreviewed", "offset": 0, "pair_id": None},
            },
            "views": [],
        }

    def _paths(self):
        directory = _unlinked(self.directory)
        if any(directory.is_relative_to(path) for path in self.protected):
            raise ValueError("Browsing preferences must be outside source and dataset artifacts")
        _unlinked(self.path)
        _unlinked(self.lock_path)
        report = _unlinked(self.run / "run.json")
        if file_sha256(report) != self.report_sha256:
            raise ValueError("QA report identity changed; reopen its verified report")

    def _filters(self, value):
        _object(value, FILTER_KEYS, "browsing filter")
        for name in FILTER_FIELDS:
            _text(value[name], 4096, "browsing filter")
            if value[name] and value[name] not in self.values[name]:
                raise ValueError(f"Unknown report {name} filter")
        _text(value["search"], 512, "browsing search (maximum 512 characters)")
        if type(value["pilot"]) is not bool:
            raise ValueError("Invalid pilot filter")
        _text(value["group"], 4096, "group filter")
        if value["group"] and value["group"] not in self.groups:
            raise ValueError("Unknown report group filter")

    def validate(self, state):
        _object(
            state, {"schema_version", "report_id", "revision", "last", "views"}, "browsing state"
        )
        if type(state["schema_version"]) is not int or state["schema_version"] != 1:
            raise ValueError("Unsupported browsing preference version")
        if state["report_id"] != self.report_id:
            raise ValueError("Browsing preferences belong to another report")
        _integer(state["revision"], "browsing revision")
        last = state["last"]
        _object(last, {"filters", "image_id", "position", "pair"}, "resume state")
        self._filters(last["filters"])
        if last["image_id"] is not None and (
            not isinstance(last["image_id"], str) or last["image_id"] not in self.image_ids
        ):
            raise ValueError("Unknown report image in browsing preferences")
        _integer(last["position"], "image position", maximum=max(0, len(self.image_ids) - 1))
        pair = last["pair"]
        _object(pair, {"decision", "offset", "pair_id"}, "pair resume state")
        if not isinstance(pair["decision"], str) or pair["decision"] not in PAIR_DECISIONS:
            raise ValueError("Invalid pair decision filter")
        _integer(pair["offset"], "pair offset")
        if pair["offset"] % 20:
            raise ValueError("Pair offset must be a multiple of 20")
        if pair["pair_id"] is not None and not _identifier(pair["pair_id"]):
            raise ValueError("Invalid pair identity")
        if not isinstance(state["views"], list) or len(state["views"]) > 20:
            raise ValueError("At most 20 named browsing views are supported")
        names = set()
        for view in state["views"]:
            _object(view, {"name", "filters"}, "named view")
            name = view["name"]
            _text(name, 80, "view name (maximum 80 characters)")
            if not name or name != unicodedata.normalize("NFC", name.strip()) or name in names:
                raise ValueError("View names must be unique, nonempty and normalized")
            names.add(name)
            self._filters(view["filters"])
        # Match atomic_json's on-disk representation, including indentation/newline.
        raw = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        if len(raw) > MAX_BYTES:
            raise ValueError("Browsing preferences must be at most 64 KiB")

    def read(self) -> dict:
        self._paths()
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        except FileNotFoundError:
            self._paths()
            return self.empty()
        if len(raw) > MAX_BYTES:
            raise ValueError(
                "Browsing preferences exceed 64 KiB; preserve the file before recovery"
            )
        try:
            state = json.loads(raw)
            self.validate(state)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(
                f"Invalid saved browsing preferences; preserve the file: {exc}"
            ) from exc
        self._paths()
        return state

    def save(self, payload: dict) -> dict:
        _object(payload, {"expected_revision", "last", "views"}, "browsing update")
        expected = payload["expected_revision"]
        _integer(expected, "expected browsing revision", maximum=999_999_999)
        proposed = {
            "schema_version": 1,
            "report_id": self.report_id,
            "revision": expected + 1,
            "last": payload["last"],
            "views": payload["views"],
        }
        self.validate(proposed)
        # Validate before creating a directory or lock. Corrupt evidence is retained.
        self.read()
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self._paths()
            with FileLock(str(self.lock_path), timeout=0):
                current = self.read()
                if current["revision"] != expected:
                    raise ReviewConflict(
                        "Browsing preferences changed in another session; "
                        "reload saved browsing settings"
                    )
                if current["last"] == proposed["last"] and current["views"] == proposed["views"]:
                    return current
                self._paths()
                atomic_json(self.path, proposed)
        except Timeout as exc:
            raise ReviewConflict(
                "Browsing preferences are being saved; retry saved browsing settings"
            ) from exc
        return proposed
