"""Loopback graphical corrections using the same review functions as the CLI."""

from __future__ import annotations

import io
import json
import mimetypes
import secrets
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from image_dataset_train.assessments import PilotAssessment
from image_dataset_train.config import Config
from image_dataset_train.exporting import _checked, _rows, _source_bytes
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import _commands, _preview, render_qa
from image_dataset_train.review_publication import Publication
from image_dataset_train.reviews import (
    ReviewConflict,
    ReviewStore,
    _image_key,
    load_context,
    pair_for_paths,
    review_image,
    review_link,
    review_status,
)
from image_dataset_train.trainer_receipts import receipt_artifact, trainer_status


class ReviewSession:
    def __init__(self, config: Config, run: Path, *, config_path=None, reports=None):
        self.config = config
        self.assessments = PilotAssessment(config.reviews, run)
        self.run = self.assessments.run
        self.meta, self.data = self.assessments.meta, self.assessments.data
        self.entries = self.assessments.entries
        # Old QA artifacts already captured the exact similarity run in their command.
        args = self.data["entries"][0]["review_args"] if self.entries else []
        reference = self.meta.get("similarity_run") or (
            args[args.index("--run") + 1] if args else None
        )
        self.similarity = Path(reference) if reference else None
        self.config_path = Path(
            config_path
            or self.meta.get("config_path")
            or (args[args.index("--config") + 1] if args else "config.toml")
        )
        self.reports = reports if reports is not None else {}
        self.publication = Publication(self)
        self.pair_images = {}
        self.receipts = {}

    def training(self):
        if self.data["summary"]["split_state"] != "published":
            return {"status": "not_export", "receipts": []}
        result = trainer_status(
            Path(self.meta["input_run"]),
            self.config.runs,
            expected_export_sha256=self.meta["input_run_sha256"],
        )
        self.receipts = {item["id"]: Path(item["path"]) for item in result["receipts"]}
        args = [
            "dataset",
            "trainer-check",
            "--run",
            result["export"],
            "--config",
            str(self.config_path.resolve()),
        ]
        result["commands"] = _commands(args)
        result["pilot_assessment"] = self.assessments.summary()
        for item in result["receipts"]:
            if item["integrity"]:
                item["artifacts"] = {
                    name: "trainer-receipt/" + item["id"] + "/" + name
                    for name in ("result.json", "loader.log")
                }
        return result

    def trainer_artifact(self, identifier, name):
        return receipt_artifact(self.receipts[identifier], name)

    def page(self):
        return {
            **self.data,
            "session": True,
            "publication": {
                "export": asdict(self.config.export),
                "captions_run": self.meta.get("caption_run")
                or self.meta.get("publication_caption_run")
                or "",
                "runs": str(self.config.runs),
                "exports": str(self.config.exports),
            },
        }

    def _pair(self, pair):
        pair = dict(pair)
        for side in ("left", "right"):
            row = {"source_path": pair[f"{side}_source_path"], "sha256": pair[f"{side}_sha256"]}
            identifier = _image_key(row)
            self.pair_images[identifier] = row
            pair[f"{side}_image"] = "pair-image/" + identifier
        return pair

    def pairs(self, *, offset=0, decision="unreviewed"):
        result = review_status(
            self.config, self.similarity, limit=20, offset=offset, pair_decision=decision
        )
        result["pairs"] = [self._pair(pair) for pair in result["pairs"]]
        return result

    def compare(self, left, right):
        context = load_context(self.similarity)
        pair = pair_for_paths(context, [left, right])
        state = ReviewStore(self.config.reviews, context.source).read()
        saved = state["pairs"].get(pair["pair_id"], {})
        return {
            "revision": state["revision"],
            "pair": self._pair(
                {
                    **pair,
                    "decision": saved.get("decision", "unreviewed"),
                    "reason": saved.get("reason", ""),
                }
            ),
        }

    def save_pair(self, payload):
        if type(payload.get("expected_revision")) is not int or any(
            not isinstance(payload.get(name), str)
            for name in ("left", "right", "decision", "reason")
        ):
            raise ValueError("Reload the pair and supply a decision and reason")
        return review_link(
            self.config,
            self.similarity,
            [payload["left"], payload["right"]],
            payload["decision"],
            payload["reason"],
            expected_revision=payload["expected_revision"],
        )

    def pair_image(self, identifier):
        row = self.pair_images[identifier]
        raw = _source_bytes(
            self.assessments.source,
            row["source_path"],
            row["sha256"],
            self.config.validation.max_file_bytes,
        )
        preview = io.BytesIO()
        _preview(raw, preview, self.config.validation.max_decode_pixels)
        return preview.getvalue(), "image/jpeg"

    def image(self, identifier: str) -> tuple[bytes, str]:
        entry = self.entries[identifier]
        root, name, digest = self.assessments.source, entry["source_path"], entry["sha256"]
        if self.data["summary"]["split_state"] == "published":
            root = Path(self.meta["input_run"])
            if file_sha256(root / "run.json") != self.meta["input_run_sha256"]:
                raise ValueError("Export metadata changed since QA")
            metadata = json.loads((root / "run.json").read_text(encoding="utf-8"))
            rows = _rows(_checked(root, "manifest.jsonl", metadata["files"]["manifest.jsonl"]))
            row = next(row for row in rows if row["source_path"] == name)
            name, digest = row["image_path"], row["image_sha256"]
        return (
            _source_bytes(root, name, digest, self.config.validation.max_file_bytes),
            mimetypes.guess_type(name)[0] or "application/octet-stream",
        )

    def review(self, identifier: str, changes: dict | None = None) -> dict:
        entry = self.entries.get(identifier)
        if entry is None:
            raise ValueError("Unknown report image")
        context = load_context(self.similarity)
        row = context.rows.get(entry["source_path"])
        if row is None or row["sha256"] != entry["sha256"]:
            raise ValueError("QA image no longer matches its original review inventory")
        options = {}
        if changes is not None:
            allowed = {
                "decision",
                "reason",
                "caption",
                "clear_caption",
                "add_labels",
                "clear_labels",
                "subset",
                "clear_subset",
                "expected_revision",
                "accept_subset_proposal",
            }
            if changes.keys() - allowed or type(changes.get("expected_revision")) is not int:
                raise ValueError("Invalid correction; reload saved values")
            for field in ("reason", "decision", "caption", "subset"):
                if field in changes and not isinstance(changes[field], str):
                    raise ValueError(f"{field} must be text")
            for field in (
                "clear_caption",
                "clear_labels",
                "clear_subset",
                "accept_subset_proposal",
            ):
                if field in changes and type(changes[field]) is not bool:
                    raise ValueError(f"{field} must be true or false")
            options = dict(changes)
            if options.pop("accept_subset_proposal", False):
                caption_run = self.meta.get("caption_run") or self.meta.get(
                    "publication_caption_run"
                )
                analysis = entry.get("caption_analysis") or {}
                if not caption_run or not (analysis.get("subset_proposal") or {}).get("value"):
                    raise ValueError("This QA image has no subset proposal to accept")
                options.update(
                    subset_from=Path(caption_run),
                    subset_manifest_sha256=analysis["manifest_sha256"],
                )
        return review_image(self.config, self.similarity, entry["source_path"], **options)


def make_server(
    config: Config, run: Path, port: int = 0, *, config_path=None
) -> ThreadingHTTPServer:
    session = ReviewSession(config, run, config_path=config_path)
    sessions = {"": session}
    prefix = "/" + secrets.token_urlsafe(24) + "/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Session URLs are not access-log entries.

        def reply(self, status: int, value, content_type="application/json"):
            raw = (
                json.dumps(value, ensure_ascii=False).encode()
                if content_type == "application/json"
                else value
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(raw)

        def route(self):
            if self.headers.get("Host") != server.authority:
                raise PermissionError("Use the printed local reviewer URL")
            path = urlsplit(self.path).path
            if not path.startswith(prefix):
                raise PermissionError("Unknown review session")
            path = path[len(prefix) :]
            selected = session
            if path.startswith("reports/"):
                _, report_id, path = path.split("/", 2)
                if report_id not in session.reports:
                    raise ValueError("Unknown published report")
                if report_id not in sessions:
                    report_config, report_path = session.reports[report_id]
                    sessions.setdefault(
                        report_id,
                        ReviewSession(
                            report_config,
                            report_path,
                            config_path=session.config_path,
                            reports=session.reports,
                        ),
                    )
                selected = sessions[report_id]
            return selected, path

        def publication_state(self, selected):
            result = selected.publication.read()
            qa = result["outputs"].get("qa")
            if qa:
                qa["url"] = prefix + "reports/" + qa["report_id"] + "/"
            return result

        def do_GET(self):
            try:
                selected, path = self.route()
                if path == "":
                    self.reply(200, render_qa(selected.page()).encode(), "text/html")
                elif path == "api/pairs":
                    query = parse_qs(urlsplit(self.path).query)
                    self.reply(
                        200,
                        selected.pairs(
                            offset=int(query.get("offset", ["0"])[0]),
                            decision=query.get("decision", ["unreviewed"])[0],
                        ),
                    )
                elif path == "api/compare":
                    query = parse_qs(urlsplit(self.path).query)
                    self.reply(
                        200,
                        selected.compare(query.get("left", [""])[0], query.get("right", [""])[0]),
                    )
                elif path == "api/publication":
                    self.reply(200, self.publication_state(selected))
                elif path == "api/training":
                    self.reply(200, selected.training())
                elif path.startswith("trainer-receipt/"):
                    _, identifier, name = path.split("/", 2)
                    self.reply(200, selected.trainer_artifact(identifier, name), "text/plain")
                elif path == "api/assessment":
                    state = selected.assessments.read()
                    self.reply(
                        200, {"state": state, "summary": selected.assessments.summary(state)}
                    )
                elif path.startswith("api/review/"):
                    self.reply(200, selected.review(path.removeprefix("api/review/")))
                elif path.startswith("pair-image/"):
                    raw, content_type = selected.pair_image(path.removeprefix("pair-image/"))
                    self.reply(200, raw, content_type)
                elif path.startswith("image/") and path.removeprefix("image/") in selected.entries:
                    raw, content_type = selected.image(path.removeprefix("image/"))
                    self.reply(200, raw, content_type)
                elif path.startswith("previews/") and path in selected.meta["files"]:
                    self.reply(
                        200,
                        _checked(selected.run, path, selected.meta["files"][path]),
                        "image/jpeg",
                    )
                else:
                    self.reply(404, {"error": "Not found"})
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})

        def do_POST(self):
            try:
                selected, path = self.route()
                if (
                    self.headers.get("Origin") != f"http://{server.authority}"
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    raise PermissionError("Save from this local review page")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 262144:
                    raise ValueError("Correction payload must be at most 256 KiB")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if path == "api/pairs":
                    result = selected.save_pair(payload)
                elif path == "api/publication":
                    result = selected.publication.start(payload)
                elif path == "api/assessment":
                    result = selected.assessments.save(payload)
                elif path.startswith("api/review/"):
                    result = selected.review(path.removeprefix("api/review/"), payload)
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
    server.review_sessions = sessions
    return server


def serve_reviews(
    config: Config, run: Path, port: int = 0, *, open_browser: bool = True, config_path=None
):
    with make_server(config, run, port, config_path=config_path) as server:
        print(f"Graphical reviewer: {server.url}", flush=True)
        print("Edits save to the review store. Ctrl+C stops the local reviewer.", flush=True)
        if open_browser:
            webbrowser.open(server.url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping reviewer; waiting for any publication already in progress…", flush=True)
        finally:
            for active in list(server.review_sessions.values()):
                active.publication.wait()
