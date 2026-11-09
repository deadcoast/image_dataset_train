"""Human pilot judgments bound to immutable QA reports, separate from corrections."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from image_dataset_train.annotations import annotation_name
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import read_qa
from image_dataset_train.reviews import ReviewConflict, _separate


class PilotAssessment:
    def __init__(self, root: Path, run: Path):
        self.run = run.resolve(strict=True)
        self.meta, self.data = read_qa(self.run)
        self.digest = file_sha256(self.run / "run.json")
        self.entries = {entry["id"]: entry for entry in self.data["entries"]}
        source = self.meta.get("source")
        if source is None:  # Reports produced before the graphical reviewer.
            source = json.loads((Path(self.meta["input_run"]) / "run.json").read_text())["source"]
        self.source = Path(source).resolve()
        _separate(self.source, root)
        _separate(self.run, root)
        self.directory = root.resolve() / "pilot-assessments" / self.digest
        self.path = self.directory / "assessment.json"

    def read(self) -> dict:
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
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            value.get("schema_version") != 1
            or value.get("qa_sha256") != self.digest
            or not isinstance(value.get("images"), dict)
            or not isinstance(value.get("history"), list)
            or value.get("revision") != len(value["history"])
        ):
            raise ValueError(f"Invalid pilot assessment: {self.path}")
        return value

    def summary(self, state: dict | None = None) -> dict:
        state = self.read() if state is None else state
        pilot = set(self.data["summary"]["pilot_ids"])
        records = {key: record for key, record in state["images"].items() if key in pilot}
        verdicts = Counter(record["verdict"] for record in records.values())
        checked = sum(value for key, value in verdicts.items() if key != "unreviewed")
        labels = defaultdict(Counter)
        captions = Counter()
        for record in records.values():
            if record["verdict"] == "unreviewed":
                continue
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
            "caption_checks": dict(captions),
            "critical_labels": {
                label: {
                    **dict(counts),
                    "checked": sum(n for key, n in counts.items() if key != "not_checked"),
                    "errors": counts["missing"] + counts["spurious"],
                }
                for label, counts in sorted(labels.items())
            },
            "conclusion": state["conclusion"],
            "human_accepted": bool(
                state["conclusion"] and state["conclusion"]["verdict"] == "accepted"
            ),
        }

    def save(self, payload: dict) -> dict:
        reviewer, notes = payload.get("reviewer", ""), payload.get("notes", "")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Enter the reviewer's name")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("Record a reason or assessment note")
        verdict = payload.get("verdict")
        identifier = payload.get("image_id")
        if verdict not in {"accepted", "needs_changes", "rejected", "unreviewed"}:
            raise ValueError("Choose an assessment verdict")
        record = {
            "verdict": verdict,
            "reviewer": reviewer.strip(),
            "notes": notes.strip(),
            "at": datetime.now(UTC).isoformat(),
        }
        if identifier is not None:
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
            if caption not in {"correct", "incorrect", "not_checked"} or any(
                check not in {"correct", "missing", "spurious", "not_checked"}
                for check in checks.values()
            ):
                raise ValueError("Invalid caption or critical-label judgment")
            if verdict == "accepted" and (
                caption != "correct" or any(v != "correct" for v in checks.values())
            ):
                raise ValueError("Accept only after checking the caption and all listed labels")
            record.update(
                source_path=entry["source_path"],
                sha256=entry["sha256"],
                caption_check=caption,
                label_checks=checks,
            )
        if type(payload.get("expected_revision")) is not int:
            raise ValueError("Reload the assessment before saving")
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
                atomic_json(self.path, state)
        except Timeout as exc:
            raise ReviewConflict("Another assessment save is running; retry.") from exc
        return {"state": state, "summary": self.summary(state)}
