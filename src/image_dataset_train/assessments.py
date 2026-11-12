"""Attributed pilot judgments bound to immutable QA reports, separate from corrections."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from filelock import FileLock, Timeout

from image_dataset_train.annotations import annotation_name
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import read_qa
from image_dataset_train.reviews import ReviewConflict, _separate

VERDICTS = {"accepted", "needs_changes", "rejected", "unreviewed"}
CAPTION_CHECKS = {"correct", "incorrect", "not_checked"}
LABEL_CHECKS = {"correct", "missing", "spurious", "absent", "not_checked"}


def _text(value, description: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError(f"Pilot assessment {description} must be nonempty text without NUL")
    return value


def _json(raw: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate keys in pilot assessment")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError(f"Non-finite value in pilot assessment: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def _record(record: dict, entry: dict | None) -> None:
    required = {"verdict", "reviewer", "notes", "at"}
    if entry is not None:
        required |= {"source_path", "sha256", "caption_check", "label_checks"}
    if (
        not isinstance(record, dict)
        or not required <= record.keys()
        or record.keys() - (required | {"reviewer_kind"})
    ):
        raise ValueError("Unsupported pilot assessment record fields")
    if not isinstance(record["verdict"], str) or record["verdict"] not in VERDICTS:
        raise ValueError("Invalid pilot assessment verdict")
    for field in ("reviewer", "notes", "at"):
        _text(record[field], field)
    if "reviewer_kind" in record and record["reviewer_kind"] not in ("human", "assistant"):
        raise ValueError("Invalid pilot assessment reviewer_kind")
    try:
        timestamp = datetime.fromisoformat(record["at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Missing timezone")
    except ValueError as exc:
        raise ValueError("Invalid pilot assessment timestamp") from exc
    if entry is None:
        return
    if record["source_path"] != entry["source_path"] or record["sha256"] != entry["sha256"]:
        raise ValueError("Pilot assessment image identity differs from its report")
    checks = record["label_checks"]
    if not isinstance(checks, dict) or not set(entry["labels"]) <= checks.keys():
        raise ValueError("Pilot assessment must retain checks for every listed label")
    if any(annotation_name(label) != label for label in checks):
        raise ValueError("Pilot assessment label names must be normalized")
    if (
        not isinstance(record["caption_check"], str)
        or record["caption_check"] not in CAPTION_CHECKS
        or any(not isinstance(check, str) or check not in LABEL_CHECKS for check in checks.values())
    ):
        raise ValueError("Invalid pilot assessment caption or label check")
    if record["verdict"] == "accepted" and (
        record["caption_check"] != "correct"
        or any(check not in {"correct", "absent"} for check in checks.values())
    ):
        raise ValueError("Accepted pilot assessment requires completed caption and label checks")


def _validate(state: dict, digest: str, entries: dict) -> dict:
    """Validate saved evidence without normalizing, repairing or inferring attribution."""
    if not isinstance(state, dict) or state.keys() != {
        "schema_version",
        "qa_run",
        "qa_sha256",
        "revision",
        "images",
        "conclusion",
        "history",
    }:
        raise ValueError("Unsupported pilot assessment state fields")
    if (
        type(state["schema_version"]) is not int
        or state["schema_version"] != 1
        or state["qa_sha256"] != digest
        or type(state["revision"]) is not int
        or state["revision"] < 0
        or not isinstance(state["images"], dict)
        or not isinstance(state["history"], list)
        or state["revision"] != len(state["history"])
    ):
        raise ValueError("Invalid pilot assessment schema, report identity or revision")
    # The digest is authoritative; a byte-identical copied QA report keeps its evidence.
    if not Path(_text(state["qa_run"], "report path")).is_absolute():
        raise ValueError("Pilot assessment report path must be absolute")
    pilot = {identifier: entry for identifier, entry in entries.items() if entry["pilot"]}
    images, conclusion = {}, None
    for revision, event in enumerate(state["history"], 1):
        if (
            not isinstance(event, dict)
            or event.keys() != {"revision", "image_id", "record"}
            or type(event["revision"]) is not int
            or event["revision"] != revision
        ):
            raise ValueError("Invalid pilot assessment history event or revision")
        identifier = event["image_id"]
        if identifier is not None and (not isinstance(identifier, str) or identifier not in pilot):
            raise ValueError("Pilot assessment history image is outside this report's pilot")
        record = event["record"]
        _record(record, pilot.get(identifier))
        if identifier is not None:
            images[identifier] = record
            conclusion = None
        else:
            if record["verdict"] == "accepted" and (
                not pilot
                or images.keys() != pilot.keys()
                or any(image["verdict"] != "accepted" for image in images.values())
            ):
                raise ValueError("Pilot conclusion requires every pilot image to be accepted")
            conclusion = None if record["verdict"] == "unreviewed" else record
    # Exact equality also preserves legacy absent attribution instead of upgrading it.
    if state["images"] != images or state["conclusion"] != conclusion:
        raise ValueError("Pilot assessment current state differs from its history")
    return state


def _reviewer_kind(record: dict) -> str:
    """Historical names do not establish whether a reviewer was human or an assistant."""
    kind = record.get("reviewer_kind")
    return kind if kind in ("human", "assistant") else "unknown"


class PilotAssessment:
    def __init__(self, root: Path, run: Path):
        self.run = run.resolve(strict=True)
        self.digest = file_sha256(self.run / "run.json")
        self.meta, self.data = read_qa(self.run)
        self._check_report()
        self.entries = {entry["id"]: entry for entry in self.data["entries"]}
        for entry in self.entries.values():
            path = PurePosixPath(_text(entry["source_path"], "source path"))
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry["source_path"]
                or ":" in entry["source_path"]
                or path.as_posix() != entry["source_path"]
                or not isinstance(entry["sha256"], str)
                or len(entry["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in entry["sha256"])
                or not isinstance(entry["labels"], list)
                or any(annotation_name(label) != label for label in entry["labels"])
                or len(set(entry["labels"])) != len(entry["labels"])
            ):
                raise ValueError("Invalid pilot assessment report image identity or labels")
        source = self.meta.get("source")
        if source is None:  # Reports produced before the graphical reviewer.
            source = json.loads((Path(self.meta["input_run"]) / "run.json").read_text())["source"]
        self.source = Path(source).resolve()
        _separate(self.source, root)
        _separate(self.run, root)
        self.directory = root.resolve() / "pilot-assessments" / self.digest
        self.path = self.directory / "assessment.json"

    def _check_report(self) -> None:
        if file_sha256(self.run / "run.json") != self.digest or any(
            file_sha256(self.run / name) != self.meta["files"].get(name)
            for name in ("entries.jsonl", "summary.json", "coverage.json")
        ):
            raise ReviewConflict(
                "QA report changed. Restore its immutable files before assessment."
            )

    def read(self) -> dict:
        self._check_report()
        if not self.path.exists():
            return {
                "schema_version": 1,
                "qa_run": str(self.run),
                "qa_sha256": self.digest,
                "revision": 0,
                "images": {},
                "conclusion": None,
                "history": [],
            }
        value = _validate(_json(self.path.read_text(encoding="utf-8")), self.digest, self.entries)
        self._check_report()
        return value

    def summary(self, state: dict | None = None) -> dict:
        state = self.read() if state is None else state
        self._check_report()
        _validate(state, self.digest, self.entries)
        pilot = set(self.data["summary"]["pilot_ids"])
        records = {key: record for key, record in state["images"].items() if key in pilot}
        verdicts = Counter(record["verdict"] for record in records.values())
        checked = sum(value for key, value in verdicts.items() if key != "unreviewed")
        labels = defaultdict(Counter)
        captions = Counter()
        reviewer_kinds, accepted_kinds = Counter(), Counter()
        for record in records.values():
            if record["verdict"] == "unreviewed":
                continue
            reviewer_kinds[_reviewer_kind(record)] += 1
            if record["verdict"] == "accepted":
                accepted_kinds[_reviewer_kind(record)] += 1
            captions[record["caption_check"]] += 1
            for label, check in record["label_checks"].items():
                labels[label][check] += 1
        return {
            "qa_run": str(self.run),
            "assessment_file": str(self.path),
            "revision": state["revision"],
            "pilot_images": len(pilot),
            "assessed_images": checked,
            "remaining_images": len(pilot) - checked,
            "verdicts": dict(verdicts),
            "reviewer_kinds": {
                kind: reviewer_kinds[kind] for kind in ("human", "assistant", "unknown")
            },
            "accepted_reviewer_kinds": {
                kind: accepted_kinds[kind] for kind in ("human", "assistant", "unknown")
            },
            "caption_checks": dict(captions),
            "critical_labels": {
                label: {
                    **dict(counts),
                    "checked": sum(n for key, n in counts.items() if key != "not_checked"),
                    "errors": counts["missing"] + counts["spurious"],
                    "tp": counts["correct"],
                    "fp": counts["spurious"],
                    "fn": counts["missing"],
                    "tn": counts["absent"],
                    "precision": (
                        counts["correct"] / (counts["correct"] + counts["spurious"])
                        if counts["correct"] + counts["spurious"]
                        else None
                    ),
                    "recall": (
                        counts["correct"] / (counts["correct"] + counts["missing"])
                        if counts["correct"] + counts["missing"]
                        else None
                    ),
                    "specificity": (
                        counts["absent"] / (counts["absent"] + counts["spurious"])
                        if counts["absent"] + counts["spurious"]
                        else None
                    ),
                }
                for label, counts in sorted(labels.items())
            },
            "conclusion": state["conclusion"],
            "conclusion_reviewer_kind": (
                _reviewer_kind(state["conclusion"]) if state["conclusion"] else None
            ),
            "human_accepted": bool(
                pilot
                and state["conclusion"]
                and state["conclusion"]["verdict"] == "accepted"
                and _reviewer_kind(state["conclusion"]) == "human"
                and accepted_kinds["human"] == len(pilot)
            ),
        }

    def save(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Pilot assessment request must be an object")
        reviewer, notes = payload.get("reviewer", ""), payload.get("notes", "")
        kind = payload.get("reviewer_kind")
        if kind not in ("human", "assistant"):
            raise ValueError("Choose reviewer_kind explicitly: human or assistant")
        if not isinstance(reviewer, str) or not reviewer.strip() or "\0" in reviewer:
            raise ValueError("Enter the reviewer's name")
        if not isinstance(notes, str) or not notes.strip() or "\0" in notes:
            raise ValueError("Record a reason or assessment note")
        verdict = payload.get("verdict")
        identifier = payload.get("image_id")
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            raise ValueError("Choose an assessment verdict")
        record = {
            "verdict": verdict,
            "reviewer": reviewer.strip(),
            "reviewer_kind": kind,
            "notes": notes.strip(),
            "at": datetime.now(UTC).isoformat(),
        }
        if identifier is not None:
            if not isinstance(identifier, str):
                raise ValueError("Assess an image in this report's pilot selection")
            entry = self.entries.get(identifier)
            if entry is None or not entry["pilot"]:
                raise ValueError("Assess an image in this report's pilot selection")
            checks = payload.get("label_checks", {})
            if not isinstance(checks, dict):
                raise ValueError("Critical-label checks must be a mapping")
            checks = {annotation_name(label): check for label, check in checks.items()}
            for label in entry["labels"]:
                checks.setdefault(label, "not_checked")
            caption = payload.get("caption_check", "not_checked")
            if (
                not isinstance(caption, str)
                or caption not in CAPTION_CHECKS
                or any(
                    not isinstance(check, str) or check not in LABEL_CHECKS
                    for check in checks.values()
                )
            ):
                raise ValueError("Invalid caption or critical-label judgment")
            if verdict == "accepted" and (
                caption != "correct" or any(v not in {"correct", "absent"} for v in checks.values())
            ):
                raise ValueError("Accept only after checking the caption and all listed labels")
            record.update(
                source_path=entry["source_path"],
                sha256=entry["sha256"],
                caption_check=caption,
                label_checks=checks,
            )
        if type(payload.get("expected_revision")) is not int or payload["expected_revision"] < 0:
            raise ValueError("Reload the assessment before saving")
        # Diagnose invalid evidence before allocating a lock, and validate again under it.
        self.read()
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(self.directory / "assessment.lock"), timeout=0):
                state = self.read()
                if state["revision"] != payload["expected_revision"]:
                    raise ReviewConflict("Assessment changed. Reload it before saving again.")
                if identifier is None:
                    summary = self.summary(state)
                    if verdict == "accepted" and (
                        not summary["pilot_images"]
                        or summary["remaining_images"]
                        or summary["verdicts"].get("accepted", 0) != summary["pilot_images"]
                    ):
                        raise ValueError("Assess and accept every pilot image before accepting it")
                    state["conclusion"] = None if verdict == "unreviewed" else record
                else:
                    state["images"][identifier] = record
                    state["conclusion"] = None  # A revised judgment needs a new conclusion.
                state["revision"] += 1
                state["history"].append(
                    {"revision": state["revision"], "image_id": identifier, "record": record}
                )
                _validate(state, self.digest, self.entries)
                self._check_report()
                atomic_json(self.path, state)
        except Timeout as exc:
            raise ReviewConflict("Another assessment save is running; retry.") from exc
        return {"state": state, "summary": self.summary(state)}
