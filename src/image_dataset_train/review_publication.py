"""Publish reviewed snapshots in a worker while the local reviewer stays responsive."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Lock, Thread

from image_dataset_train.config import ExportConfig
from image_dataset_train.exporting import export_dataset
from image_dataset_train.qa import create_qa
from image_dataset_train.reviews import ReviewConflict, publish_groups


class Publication:
    def __init__(self, session):
        self.session = session
        self.lock = Lock()
        self.worker = None
        self.result = {"status": "idle", "message": "No publication started", "outputs": {}}

    def read(self):
        with self.lock:
            return deepcopy(self.result)

    def update(self, **values):
        with self.lock:
            self.result.update(values)

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
        captions = Path(caption_path).resolve(strict=True) if caption_path else None
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ReviewConflict("Publication is already running")
            self.result = {
                "status": "running",
                "message": "Capturing reviewed groups…",
                "outputs": {},
            }
            self.worker = Thread(
                target=self._run,
                args=(config, captions, mode, revision),
                name="review-publication",
                daemon=False,
            )
            self.worker.start()
            return deepcopy(self.result)

    def _run(self, config, captions, mode, revision):
        outputs = {}
        try:
            groups, group_summary = publish_groups(
                config, self.session.similarity, expected_revision=revision
            )
            outputs["groups"] = {"path": str(groups), "summary": group_summary}
            self.update(outputs=deepcopy(outputs), message="Group snapshot published")
            target = groups
            if mode == "export":
                self.update(message="Copying and verifying training pairs…")
                target, summary = export_dataset(
                    config,
                    groups,
                    captions_run=captions,
                    progress=lambda message: self.update(message=message),
                )
                outputs["export"] = {"path": str(target), "summary": summary, "verified": True}
                self.update(outputs=deepcopy(outputs))
            self.update(message="Building QA previews for the published snapshot…")
            qa, summary = create_qa(
                config,
                target,
                captions_run=captions if mode == "groups" else None,
                sample_size=self.session.data["summary"]["requested_pilot_images"],
                seed=self.session.data["summary"]["seed"],
                config_path=self.session.config_path,
            )
            self.session.reports[qa.name] = (config, qa)
            outputs["qa"] = {"path": str(qa), "report_id": qa.name, "summary": summary}
            self.update(status="completed", outputs=outputs, message="Publication completed")
        except Exception as exc:
            # Preserve successful outputs when a later export/QA stage fails.
            self.update(status="failed", outputs=outputs, message=str(exc))

    def wait(self):
        if self.worker is not None:
            self.worker.join()
