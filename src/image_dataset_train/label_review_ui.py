"""Local critical-label review, with deliberate and recorded model comparison."""

from __future__ import annotations

import io
import json
import secrets
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from image_dataset_train.config import Config
from image_dataset_train.exporting import _path, _source_bytes
from image_dataset_train.label_workspace import LabelWorkspace, _text
from image_dataset_train.reviews import ReviewConflict
from image_dataset_train.saved_caption_rules import resolve_saved_caption_rules
from image_dataset_train.scored_runs import ScoredRun


class LabelReviewSession:
    def __init__(self, config: Config, workspace: Path, scored_runs=()):
        self.config = config
        self.store = LabelWorkspace(workspace)
        self.source = Path(self.store.selection["source"])
        self.scored_runs = tuple(Path(path).absolute() for path in scored_runs)
        self.model_digests = {}
        if len(set(self.scored_runs)) != len(self.scored_runs) or len(self.scored_runs) > 6:
            raise ValueError("Choose up to six different saved model runs")
        self.store.read()
        for run in self.scored_runs:
            scored, _, _ = self._scored(run)
            self.model_digests[run] = scored.digest

    def _scored(self, run: Path):
        scored = ScoredRun(run)
        if run in self.model_digests and scored.digest != self.model_digests[run]:
            raise ValueError("Comparison run metadata changed during this review session")
        if Path(scored.metadata["source"]).resolve() != self.source.resolve():
            raise ValueError("Comparison run has a different source collection")
        vocabulary = {label.name: label for label in scored.labels}
        for label in self.store.selection["labels"]:
            if (
                label["name"] not in vocabulary
                or vocabulary[label["name"]].category != label["category"]
            ):
                raise ValueError("Comparison run differs from the frozen raw label vocabulary")
        rows = {
            (row["source_path"], row.get("sha256")): row
            for row in scored.rows
            if row.get("decision") == "tagged"
        }
        if any(
            (alias["source_path"], member["sha256"]) not in rows
            for member in self.store.members.values()
            for alias in member["aliases"]
        ):
            raise ValueError("Comparison scores must cover every frozen path/hash identity")
        return scored, vocabulary, rows

    def state(self):
        state = self.store.read()
        return {
            "revision": state["revision"],
            "judgments": state["judgments"],
            "summary": self.store.summary(state),
            "labels": sorted(self.store.labels),
            "members": [
                {
                    "sha256": member["sha256"],
                    "paths": [alias["source_path"] for alias in member["aliases"]],
                }
                for member in self.store.members.values()
            ],
            "comparison_models": len(self.scored_runs),
        }

    def _source(self, digest):
        if digest not in self.store.members:
            raise ValueError("Choose an image in this frozen workspace")
        self.store.read()
        first = None
        for alias in self.store.members[digest]["aliases"]:
            raw = _source_bytes(
                self.source,
                alias["source_path"],
                digest,
                self.config.validation.max_file_bytes,
            )
            if first is None:
                first = raw
        return first

    def image(self, digest):
        raw = self._source(digest)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > self.config.validation.max_decode_pixels:
                raise ValueError("Image exceeds the configured decode limit")
            oriented = ImageOps.exif_transpose(image)
            output = io.BytesIO()
            oriented.convert("RGBA").save(output, "PNG")
        return output.getvalue()

    def save(self, payload):
        if set(payload) != {"image", "expected_revision", "judgments"}:
            raise ValueError("Provide an image, expected revision and label judgments")
        digest = payload["image"]
        self._source(digest)
        judgments = payload["judgments"]
        allowed = {"label", "value", "reviewer", "reviewer_kind", "notes"}
        if not isinstance(judgments, list) or any(
            not isinstance(row, dict) or set(row) != allowed for row in judgments
        ):
            raise ValueError("Invalid label judgments")
        self.store.save_many(
            [{**row, "image": digest} for row in judgments],
            expected_revision=payload["expected_revision"],
        )
        return self.state()

    def compare(self, payload):
        if set(payload) != {"image", "expected_revision", "reviewer", "reviewer_kind"}:
            raise ValueError("Provide image, revision and explicit comparison viewer attribution")
        digest = payload["image"]
        self._source(digest)
        reviewer = _text(payload["reviewer"], "Comparison viewer")
        kind = payload["reviewer_kind"]
        if kind not in {"human", "assistant"}:
            raise ValueError("Choose human or assistant comparison viewer")
        state = self.store.read()
        if type(payload["expected_revision"]) is not int or (
            state["revision"] != payload["expected_revision"]
        ):
            raise ReviewConflict("Label judgments changed. Reload before comparing.")
        current = state["judgments"].get(digest, {})
        if set(current) != self.store.labels:
            raise ValueError("Save all labels for this image before revealing model predictions")
        if not self.scored_runs:
            raise ValueError("No saved model runs were selected for comparison")
        models, exposure = [], []
        at = datetime.now(UTC).isoformat()
        for run in self.scored_runs:
            scored, vocabulary, rows = self._scored(run)
            vector = scored.vector(digest)
            saved_rules = resolve_saved_caption_rules(scored.metadata, scored.labels)
            cutoffs = saved_rules.thresholds(vocabulary[name] for name in sorted(self.store.labels))
            captions = []
            for alias in self.store.members[digest]["aliases"]:
                row = rows[(alias["source_path"], digest)]
                caption = row.get("caption")
                if not isinstance(caption, str):
                    raise ValueError("Comparison run has no saved caption text")
                expected = (caption + "\n").encode("utf-8")
                with _path(scored.run, row.get("caption_path")).open("rb") as stream:
                    raw = stream.read(len(expected) + 1)
                if raw != expected:
                    raise ValueError("Saved caption file differs from its checked manifest")
                captions.append({"source_path": alias["source_path"], "caption": caption})
            models.append(
                {
                    "run": str(scored.run),
                    "model": scored.metadata.get("model", {}),
                    "captions": captions,
                    "scores": {
                        name: float(vector[vocabulary[name].index])
                        for name in sorted(self.store.labels)
                    },
                    "thresholds": cutoffs,
                    "caption_rules_sha256": scored.metadata["caption_rules_sha256"],
                }
            )
            exposure.append(
                {
                    "run": str(scored.run),
                    "run_sha256": scored.digest,
                    "at": at,
                    "reviewer": reviewer,
                    "reviewer_kind": kind,
                }
            )
        changes = []
        for label, record in current.items():
            seen = {
                (item["run_sha256"], item.get("reviewer"), item.get("reviewer_kind"))
                for item in record.get("comparison_exposure", [])
            }
            additions = [
                item for item in exposure if (item["run_sha256"], reviewer, kind) not in seen
            ]
            if additions:
                changes.append(
                    {**record, "image": digest, "label": label, "comparison_exposure": additions}
                )
        if changes:
            self.store.save_many(changes, expected_revision=state["revision"])
        return {"workspace": self.state(), "models": models}


def make_label_server(
    config: Config, workspace: Path, *, scored_runs=(), port: int = 0
) -> ThreadingHTTPServer:
    session = LabelReviewSession(config, workspace, scored_runs)
    prefix = "/" + secrets.token_urlsafe(24) + "/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, value, content_type="application/json"):
            raw = (
                json.dumps(value, ensure_ascii=False).encode()
                if (content_type == "application/json")
                else value
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(raw)

        def route(self):
            if self.headers.get("Host") != server.authority:
                raise PermissionError("Use the printed local label-review URL")
            path = urlsplit(self.path).path
            if not path.startswith(prefix):
                raise PermissionError("Unknown label-review session")
            return path[len(prefix) :]

        def do_GET(self):
            try:
                path = self.route()
                if path == "":
                    self.reply(
                        200, Path(__file__).with_name("label_review.html").read_bytes(), "text/html"
                    )
                elif path == "app.js":
                    self.reply(
                        200,
                        Path(__file__).with_name("label_review.js").read_bytes(),
                        "text/javascript",
                    )
                elif path == "api/state":
                    self.reply(200, session.state())
                elif path.startswith("image/"):
                    self.reply(200, session.image(path.removeprefix("image/")), "image/png")
                else:
                    self.reply(404, {"error": "Not found"})
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except (ValueError, OSError, KeyError, TypeError, Image.DecompressionBombError) as exc:
                self.reply(400, {"error": str(exc)})

        def do_POST(self):
            try:
                path = self.route()
                if (
                    self.headers.get("Origin") != f"http://{server.authority}"
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    raise PermissionError("Save from this local label-review page")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 262144:
                    raise ValueError("Request must be between one byte and 256 KiB")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if path == "api/save":
                    result = session.save(payload)
                elif path == "api/compare":
                    result = session.compare(payload)
                else:
                    self.reply(404, {"error": "Not found"})
                    return
                self.reply(200, result)
            except ReviewConflict as exc:
                self.reply(409, {"error": str(exc)})
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.authority = f"127.0.0.1:{server.server_port}"
    server.url = f"http://{server.authority}{prefix}"
    server.label_session = session
    return server


def serve_label_reviews(
    config: Config,
    workspace: Path,
    *,
    scored_runs=(),
    port: int = 0,
    open_browser: bool = True,
):
    with make_label_server(config, workspace, scored_runs=scored_runs, port=port) as server:
        print(f"Critical-label reviewer: {server.url}", flush=True)
        print("Judgments save to this workspace. Ctrl+C stops the local reviewer.", flush=True)
        if open_browser:
            webbrowser.open(server.url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Label reviewer stopped.", flush=True)
