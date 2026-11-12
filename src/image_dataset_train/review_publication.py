"""Durable publication attempts behind the loopback reviewer's existing API."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock, Thread
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train.config import ExportConfig
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import (
    _adapter,
    _checked,
    _drafts,
    _load_groups,
    _path,
    _published,
    export_dataset,
    verify_export,
)
from image_dataset_train.implementation import implementation_identity
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import create_qa, read_qa
from image_dataset_train.reviews import (
    ELIGIBLE,
    ReviewConflict,
    ReviewStore,
    _separate,
    _verify_source,
    load_context,
    publish_groups,
)


def _now():
    return datetime.now(UTC).isoformat()


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _tree(directory):
    """Hash immutable artifacts, including payloads outside metadata.files."""
    _path(directory, "run.json")
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked publication artifact is not supported: {path}")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = file_sha256(path)
    return result


class Publication:
    def __init__(self, session):
        self.session = session
        self.lock = RLock()
        self.worker = None
        self.process_lock = None
        self.binding = {
            "report": str(session.run.resolve()),
            "report_sha256": file_sha256(_path(session.run, "run.json")),
            "source": str(Path(session.meta["source"]).resolve()),
        }
        self.identifier = _digest(self.binding)
        self.root = _path(session.config.reviews.absolute(), "publications")
        self.directory = _path(self.root, self.identifier)
        self.path = _path(self.directory, "job.json")
        self.lock_path = _path(
            self.root, "source-" + _digest(os.path.normcase(self.binding["source"])) + ".lock"
        )
        _separate(Path(self.binding["source"]), self.root)
        _separate(session.run.resolve(), self.directory)
        self.document = {"schema_version": 1, "binding": self.binding, "attempts": []}
        if self.path.exists():
            guard = FileLock(self.lock_path, timeout=0, thread_local=False)
            try:
                with guard:
                    self.document = self._load()
                    self._recover()
            except Timeout:
                self.document = self._load()
            self._register()

    def _load(self):
        value = json.loads(_path(self.directory, "job.json").read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or value.get("binding") != self.binding
            or not isinstance(value.get("attempts"), list)
        ):
            raise ValueError("Invalid publication job. Preserve it before recovery.")
        seen = set()
        for attempt in value["attempts"]:
            identifier = attempt.get("id", "")
            if (
                len(identifier) != 32
                or any(c not in "0123456789abcdef" for c in identifier)
                or identifier in seen
                or attempt.get("fingerprint") != _digest(attempt.get("request"))
                or attempt.get("status") not in {"running", "failed", "completed"}
                or not isinstance(attempt.get("outputs"), dict)
            ):
                raise ValueError("Invalid publication attempt. Preserve it before recovery.")
            seen.add(identifier)
        return value

    def _persist(self):
        _path(self.directory, "job.json")
        atomic_json(self.path, self.document)

    @staticmethod
    def _stages(attempt):
        return (
            ("groups", "export", "qa")
            if attempt["request"]["mode"] == "export"
            else ("groups", "qa")
        )

    def _stage_root(self, attempt, stage):
        name = "exports" if stage == "export" else "runs"
        relative = f"reviewer-publications/{self.identifier}/{attempt['id']}/{stage}"
        return _path(Path(attempt["request"]["destinations"][name]), relative)

    def _verify_output(self, attempt, stage, output, earlier):
        owner = next(a for a in self.document["attempts"] if a["id"] == output["owner_attempt"])
        directory = Path(output["path"])
        if (
            owner["fingerprint"] != attempt["fingerprint"]
            or directory.parent != self._stage_root(owner, stage)
            or directory.name.startswith(".pending-")
        ):
            raise ValueError("Publication output is outside its matching attempt")
        meta = _published(directory, {stage})
        request = attempt["request"]
        if meta["status"] != "completed" or meta.get("source") != request["source"]:
            raise ValueError("Publication output is incomplete or belongs to another source")
        files = _tree(directory)
        if output.get("files") is not None and files != output["files"]:
            raise ValueError("Publication output changed after its checkpoint")
        for name, digest in meta.get("files", {}).items():
            _checked(directory, name, digest)
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        if stage == "groups":
            _, groups, artifacts = _load_groups(directory, require_reviewed=False)
            identities = sorted(
                [m["source_path"], m["sha256"]] for g in groups for m in g["members"]
            )
            if (
                identities != request["image_identities"]
                or meta.get("similarity_run") != request["similarity"]
                or meta.get("inventory_manifest_sha256") != request["inventory_manifest_sha256"]
                or meta.get("review_revision") != request["review_revision"]
                or _digest(json.loads(artifacts["reviews.json"])) != request["review_state_sha256"]
            ):
                raise ValueError("Group snapshot does not match the captured review inputs")
        elif stage == "export":
            verify_export(directory)
            groups = earlier["groups"]
            if (
                meta.get("groups_run") != groups["path"]
                or meta.get("review_revision") != request["review_revision"]
                or meta.get("caption_run") != request["captions_run"]
                or file_sha256(directory / "provenance/groups-run.json") != groups["run_sha256"]
            ):
                raise ValueError("Export does not match the captured groups and caption inputs")
            settings = ExportConfig(**request["export"])
            splits = json.loads((directory / "splits.json").read_text(encoding="utf-8"))
            if any(
                splits[key] != expected
                for key, expected in {
                    "strategy": settings.split_strategy,
                    "seed": settings.seed,
                    "validation_ratio": settings.validation_ratio,
                }.items()
            ) or any(
                (directory / f"{split}.toml").read_text(encoding="utf-8")
                != _adapter(split, settings)
                for split in summary["split_images"]
            ):
                raise ValueError("Export settings do not match the publication attempt")
            if (
                request["captions_run"]
                and _digest(
                    json.loads(
                        (directory / "provenance/captions-run.json").read_text(encoding="utf-8")
                    )
                )
                != request["caption_metadata_sha256"]
            ):
                raise ValueError("Export caption provenance does not match the publication attempt")
        else:
            _, data = read_qa(directory)
            selection = request["pilot"].get("selection")
            actual_selection = data["summary"].get("pilot_selection")
            if (
                selection is not None
                and actual_selection != selection
                or selection is None
                and actual_selection is not None
                and actual_selection.get("method") == "explicit_source_paths"
            ):
                raise ValueError("QA pilot selection does not match the publication request")
            parent = earlier["export" if request["mode"] == "export" else "groups"]
            if (
                meta.get("input_run") != parent["path"]
                or meta.get("input_run_sha256") != parent["run_sha256"]
                or meta.get("caption_run")
                != (request["captions_run"] if request["mode"] == "groups" else None)
                or summary.get("review_revision") != request["review_revision"]
                or summary.get("requested_pilot_images") != request["pilot"]["size"]
                or summary.get("seed") != request["pilot"]["seed"]
            ):
                raise ValueError("QA does not match its publication inputs")
            if request["mode"] == "export":
                expected = sorted(
                    [row["source_path"], row["sha256"]]
                    for line in (Path(parent["path"]) / "manifest.jsonl").read_bytes().splitlines()
                    if (row := json.loads(line))
                )
            else:
                expected = request["image_identities"]
            if sorted([e["source_path"], e["sha256"]] for e in data["entries"]) != expected:
                raise ValueError("QA image identities do not match its publication inputs")
        result = {
            "path": str(directory),
            "owner_attempt": owner["id"],
            "run_sha256": files["run.json"],
            "files": files,
            "summary": summary,
        }
        if stage == "export":
            result["verified"] = True
        if stage == "qa":
            result["report_id"] = directory.name
        return result

    def _reconcile(self, attempt):
        valid, invalid = {}, {}
        for stage in self._stages(attempt):
            try:
                output = attempt["outputs"].get(stage)
                if output is None:
                    root = self._stage_root(attempt, stage)
                    candidates = (
                        [
                            p
                            for p in root.iterdir()
                            if p.is_dir() and not p.name.startswith(".pending-")
                        ]
                        if root.exists()
                        else []
                    )
                    if not candidates:
                        break
                    if len(candidates) != 1:
                        raise ValueError("Ambiguous unpublished checkpoint; preserve its outputs")
                    output = {"path": str(candidates[0]), "owner_attempt": attempt["id"]}
                valid[stage] = self._verify_output(attempt, stage, output, valid)
                attempt["outputs"][stage] = valid[stage]
            except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
                invalid[stage] = str(exc)
                break
        attempt["invalid_outputs"] = invalid
        return valid

    def _recover(self):
        if not self.document["attempts"]:
            return
        attempt = self.document["attempts"][-1]
        valid = self._reconcile(attempt)
        if len(valid) == len(self._stages(attempt)):
            attempt.update(status="completed", message="Publication completed", error=None)
        elif attempt["status"] == "running" or attempt["invalid_outputs"]:
            attempt.update(
                status="failed",
                message="Publication interrupted or an output changed. Retry to continue safely.",
                error=attempt["invalid_outputs"] or {"interrupted": "Worker no longer running"},
            )
        attempt.setdefault("finished_at", _now())
        self._persist()

    def _public(self):
        if not self.document["attempts"]:
            return {"status": "idle", "message": "No publication started", "outputs": {}}
        attempt = self.document["attempts"][-1]
        outputs = {}
        for stage in self._stages(attempt):
            if stage in attempt.get("invalid_outputs", {}) or stage not in attempt["outputs"]:
                break
            outputs[stage] = {
                key: value
                for key, value in attempt["outputs"][stage].items()
                if key not in {"files", "owner_attempt"}
            }
        return deepcopy(
            {
                "status": attempt["status"],
                "message": attempt["message"],
                "outputs": outputs,
                "job_path": str(self.path),
                "attempt_id": attempt["id"],
                "reused_stages": attempt.get("reused_stages", []),
                "error": attempt.get("error"),
                "settings": {
                    "mode": attempt["request"]["mode"],
                    "captions_run": attempt["request"]["captions_run"],
                    "export": attempt["request"]["export"],
                },
                "attempts": [
                    {
                        key: a.get(key)
                        for key in ("id", "status", "started_at", "finished_at", "error")
                    }
                    for a in self.document["attempts"]
                ],
            }
        )

    def _register(self):
        qa = self._public()["outputs"].get("qa")
        if qa:
            settings = self.document["attempts"][-1]["request"]["export"]
            self.session.reports[qa["report_id"]] = (
                replace(self.session.config, export=ExportConfig(**settings)),
                Path(qa["path"]),
            )

    def read(self):
        with self.lock:
            # Polling must not replace the dictionary owned by the live worker.
            if self.path.exists() and not (self.worker and self.worker.is_alive()):
                self.document = self._load()
            self._register()
            return self._public()

    def update(self, **values):
        with self.lock:
            self.document["attempts"][-1].update(values)
            self._persist()

    def _locations(self, config, captions, context):
        inputs = [self.session.run, context.run, context.inventory]
        if captions:
            inputs.append(captions)
        destinations = [
            self.directory,
            config.runs / "reviewer-publications" / self.identifier,
            config.exports / "reviewer-publications" / self.identifier,
        ]
        for destination in destinations:
            _path(destination.absolute(), "path-check")
            for source in [context.source, *inputs, Path(self.session.meta["input_run"])]:
                _separate(source.resolve(), destination)
        return inputs

    def _request(self, config, captions, mode, revision):
        if file_sha256(_path(self.session.run, "run.json")) != self.binding["report_sha256"]:
            raise ValueError("Original QA report changed; reopen a verified report")
        _, qa_data = read_qa(self.session.run)
        selection = qa_data["summary"].get("pilot_selection")
        context = load_context(self.session.similarity)
        if str(context.source) != self.binding["source"]:
            raise ValueError("Report and similarity source identities do not match")
        state = ReviewStore(config.reviews, context.source).read()
        if state["revision"] != revision:
            raise ReviewConflict("Reviews changed. Refresh publication status and try again.")
        identities = []
        for row in context.rows.values():
            if row["kind"] == "image" and row["decision"] in ELIGIBLE:
                _verify_source(context, row, config.validation.max_file_bytes)
                identities.append([row["source_path"], row["sha256"]])
                if row.get("sidecar_path"):
                    _verify_source(
                        context,
                        {"source_path": row["sidecar_path"], "sha256": row["sidecar_sha256"]},
                        config.validation.max_file_bytes,
                    )
        _, caption_meta = _drafts(captions, context.metadata)
        if caption_meta and caption_meta["status"] != "completed":
            raise ValueError("Publication requires a completed caption run without errors")
        inputs = self._locations(config, captions, context)
        return {
            "source": str(context.source),
            "mode": mode,
            "review_revision": revision,
            "review_state_sha256": _digest(state),
            "image_identities": sorted(identities),
            "similarity": str(context.run),
            "inventory_manifest_sha256": context.inventory_hash,
            "inputs": {str(path.resolve()): _tree(path) for path in inputs},
            "captions_run": str(captions) if captions else None,
            "caption_metadata_sha256": _digest(caption_meta) if caption_meta else None,
            "export": asdict(config.export),
            "validation": asdict(config.validation),
            "destinations": {
                key: str(getattr(config, key).resolve()) for key in ("runs", "exports")
            },
            "pilot": {
                "size": qa_data["summary"]["requested_pilot_images"],
                "seed": qa_data["summary"]["seed"],
                **(
                    {"selection": deepcopy(selection)}
                    if selection and selection["method"] == "explicit_source_paths"
                    else {}
                ),
            },
            "config_path": str(self.session.config_path.resolve()),
            "implementation": implementation_identity(),
        }

    def start(self, payload: dict) -> dict:
        mode, revision = payload.get("mode"), payload.get("expected_revision")
        if mode not in {"groups", "export"} or type(revision) is not int:
            raise ValueError("Choose a publication action after refreshing review status")
        options = payload.get("export", {})
        if (
            not isinstance(options, dict)
            or options.keys() - ExportConfig.__dataclass_fields__.keys()
        ):
            raise ValueError("Invalid export settings")
        config = replace(self.session.config, export=replace(self.session.config.export, **options))
        caption_path = payload.get(
            "captions_run",
            self.session.meta.get("caption_run")
            or self.session.meta.get("publication_caption_run"),
        )
        if caption_path is not None and not isinstance(caption_path, str):
            raise ValueError("Caption run must be a local directory path")
        captions = Path(caption_path).absolute() if caption_path else None
        if captions:
            _path(captions, "run.json")
            captions = captions.resolve(strict=True)
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ReviewConflict("Publication is already running")
            context = load_context(self.session.similarity)
            self._locations(config, captions, context)  # Before creating the lock directory.
            self.root.mkdir(parents=True, exist_ok=True)
            guard = FileLock(self.lock_path, timeout=0, thread_local=False)
            try:
                guard.acquire()
            except Timeout as exc:
                raise ReviewConflict("Publication is already running for this source") from exc
            try:
                if self.path.exists():
                    self.document = self._load()
                    self._recover()
                request = self._request(config, captions, mode, revision)
                fingerprint = _digest(request)
                reused = {}
                previous = self.document["attempts"][-1] if self.document["attempts"] else None
                if previous and previous["fingerprint"] == fingerprint:
                    reused = self._reconcile(previous)
                    if previous["status"] == "completed" and len(reused) == len(
                        self._stages(previous)
                    ):
                        self._persist()
                        self._register()
                        guard.release()
                        return self._public()
                attempt = {
                    "id": uuid4().hex,
                    "request": request,
                    "fingerprint": fingerprint,
                    "status": "running",
                    "message": "Continuing verified publication…"
                    if reused
                    else "Capturing reviewed groups…",
                    "started_at": _now(),
                    "outputs": deepcopy(reused),
                    "reused_stages": list(reused),
                    "error": None,
                }
                self.document["attempts"].append(attempt)
                self._persist()
                self.process_lock = guard
                self.worker = Thread(
                    target=self._run,
                    args=(config, captions, attempt),
                    name="review-publication",
                    daemon=False,
                )
                self.worker.start()
                return self._public()
            except BaseException:
                guard.release()
                raise

    def _checkpoint(self, attempt, stage, path):
        output = self._verify_output(
            attempt, stage, {"path": str(path), "owner_attempt": attempt["id"]}, attempt["outputs"]
        )
        with self.lock:
            attempt["outputs"][stage] = output
            self._persist()

    def _run(self, config, captions, attempt):
        try:
            request = attempt["request"]
            for stage in self._stages(attempt):
                if stage in attempt["outputs"]:
                    continue
                for path, hashes in request["inputs"].items():
                    if _tree(Path(path)) != hashes:
                        raise ValueError("Publication input changed during this attempt")
                root = self._stage_root(attempt, stage)
                if stage == "groups":
                    path, _ = publish_groups(
                        replace(config, runs=root),
                        self.session.similarity,
                        expected_revision=request["review_revision"],
                    )
                elif stage == "export":
                    self.update(message="Copying and verifying training pairs…")
                    path, _ = export_dataset(
                        replace(config, exports=root),
                        Path(attempt["outputs"]["groups"]["path"]),
                        captions_run=captions,
                        progress=lambda message: self.update(message=message),
                    )
                else:
                    self.update(message="Building QA previews for the published snapshot…")
                    target = attempt["outputs"][
                        "export" if request["mode"] == "export" else "groups"
                    ]
                    selection = request["pilot"].get("selection")
                    path, _ = create_qa(
                        replace(config, runs=root),
                        Path(target["path"]),
                        captions_run=captions if request["mode"] == "groups" else None,
                        sample_size=request["pilot"]["size"],
                        seed=request["pilot"]["seed"],
                        config_path=self.session.config_path,
                        pilot_source_paths=selection["source_paths"] if selection else None,
                        selection_reason=selection["reason"] if selection else None,
                    )
                self._checkpoint(attempt, stage, path)
            self.update(status="completed", message="Publication completed", finished_at=_now())
            with self.lock:
                self._register()
        except Exception as exc:
            self.update(
                status="failed",
                message=str(exc),
                finished_at=_now(),
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        finally:
            self.process_lock.release()

    def wait(self):
        if self.worker is not None:
            self.worker.join()
