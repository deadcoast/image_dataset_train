"""Loopback graphical corrections using the same review functions as the CLI."""

from __future__ import annotations

import hashlib
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
from image_dataset_train.review_preferences import ReviewPreferences
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
        self.browsing_preferences = ReviewPreferences(
            config, self.run, self.assessments.digest, self.data
        )
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
        self.receipts = {
            item["id"]: (Path(item["path"]), item.get("receipt_run_sha256"))
            for item in result["receipts"]
            if item["integrity"]
        }
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
                    name: "trainer-receipt/"
                    + item["id"]
                    + "/"
                    + name
                    + "?receipt_sha256="
                    + item["receipt_run_sha256"]
                    for name in ("result.json", "loader.log")
                }
        return result

    def trainer_artifact(self, identifier, name, *, expected_receipt_sha256=None):
        directory, digest = self.receipts[identifier]
        return receipt_artifact(
            directory,
            name,
            expected_receipt_sha256=(
                digest if expected_receipt_sha256 is None else expected_receipt_sha256
            ),
        )

    def page(self):
        try:
            browsing_state = self.browsing_preferences.read()
            browsing_error = None
        except (ValueError, OSError) as exc:
            browsing_state = None
            browsing_error = str(exc)
        return {
            **self.data,
            "session": True,
            "browsing": {
                "report_id": self.browsing_preferences.report_id,
                "state": browsing_state,
                "error": browsing_error,
            },
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
                    "evaluation_set": saved.get("evaluation_set"),
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
            evaluation_set=payload.get("evaluation_set", ""),
            expected_revision=payload["expected_revision"],
        )

    def evaluate_pairs(self):
        from image_dataset_train.similarity_evaluation import evaluate_similarity

        directory, summary = evaluate_similarity(self.config, self.similarity)
        return {"run": str(directory), **summary}

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

    def review_changes(self, *, limit=20, offset=0, kind=None) -> dict:
        from image_dataset_train.review_changes import inspect_review_changes
        from image_dataset_train.review_selection import fingerprint

        result = inspect_review_changes(
            self.config, self.similarity, self.run, limit=limit, offset=offset, kind=kind
        )
        if result["report_sha256"] != self.assessments.digest:
            raise ReviewConflict("This report changed after the page opened; reopen the report")
        result["inspection_sha256"] = fingerprint(
            {
                "report_sha256": result["report_sha256"],
                "current_store_sha256": result["current_store_sha256"],
                "metadata_sha256": result["metadata_sha256"],
            }
        )
        return result

    def caption_comparison(self, identifier: str, proposed: dict | None = None) -> dict:
        from image_dataset_train.caption_comparison import inspect_caption_comparison

        entry = self.entries.get(identifier)
        if entry is None:
            raise ValueError("Unknown report image")
        options = {}
        if proposed is not None:
            if (
                not isinstance(proposed, dict)
                or proposed.keys() - {"action", "caption"}
                or proposed.get("action") not in {"keep", "replace", "clear"}
                or ("caption" in proposed and not isinstance(proposed["caption"], str))
            ):
                raise ValueError("Expected a caption preview action and optional caption text")
            options = proposed
        result = inspect_caption_comparison(
            self.config, self.similarity, self.run, identifier, **options
        )
        if result["report_sha256"] != self.assessments.digest:
            raise ReviewConflict("This report changed after the page opened; reopen the report")
        if result["identity"] != {
            "source_path": entry["source_path"],
            "sha256": entry["sha256"],
        }:
            raise ReviewConflict("This image changed after the page opened; reopen the report")
        return result

    def caption_explanation(
        self, identifier: str, *, tags=None, limit=20, offset=0, expected_run_sha256=None
    ) -> dict:
        from image_dataset_train.review_selection import read_metadata_bytes

        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError("Choose an explanation page with a limit between 1 and 200")
        if tags is not None and (
            not isinstance(tags, list)
            or not 1 <= len(tags) <= 200
            or any(not isinstance(tag, str) or not tag or "\0" in tag for tag in tags)
            or len(set(tags)) != len(tags)
        ):
            raise ValueError("Choose unique exact model tag names")
        # The comparison validates the exact report/input/image and its pinned draft.
        # It remains usable when source images are offline and never changes a review.
        comparison = self.caption_comparison(identifier)
        candidate = comparison["candidates"]["draft"]
        provenance = candidate["provenance"]
        binding = {
            "report": comparison["report"],
            "report_sha256": comparison["report_sha256"],
            "image_id": identifier,
            "identity": comparison["identity"],
        }
        if candidate["status"] == "absent":
            return {
                **binding,
                "status": "unavailable",
                "reason_code": "no_draft",
                "reason": "No model draft was recorded for this image in this report.",
            }
        if candidate["status"] == "unavailable":
            return {
                **binding,
                "status": "unavailable",
                "reason_code": "draft_unavailable",
                "reason": candidate["error"],
            }
        if candidate["status"] == "invalid" and candidate["text"] is None:
            raise ValueError(candidate["error"])
        run = Path(provenance["run"])
        metadata = (
            Path(comparison["input_run"]) / "provenance/captions-run.json"
            if comparison["input_stage"] == "export"
            else run / "run.json"
        )
        run_digest = comparison["read_sha256"].get(str(metadata))
        if run_digest is None:
            raise ValueError("The report has no verified caption rule metadata")
        if expected_run_sha256 is not None and expected_run_sha256 != run_digest:
            raise ReviewConflict(
                "Saved draft evidence changed; explain it again from the first page"
            )
        try:
            from image_dataset_train.caption_explanations import explain_caption

            result = explain_caption(
                run,
                binding["identity"]["source_path"],
                tags=tags,
                limit=limit,
                offset=offset,
                expected_run_sha256=run_digest,
                expected_manifest_sha256=provenance["manifest_sha256"],
                expected_source=str(self.assessments.source),
                expected_sha256=binding["identity"]["sha256"],
            )
        except FileNotFoundError:
            result = {
                "status": "unavailable",
                "reason_code": "scored_run_unavailable",
                "reason": (
                    "The original saved scores are unavailable. "
                    "Restore the recorded caption run to explain its rules."
                ),
                "run": str(run),
            }
        except ModuleNotFoundError as exc:
            if exc.name != "numpy":
                raise
            result = {
                "status": "unavailable",
                "reason_code": "score_reader_unavailable",
                "reason": (
                    "Saved-score inspection needs NumPy. Install the tagging support "
                    "to inspect this draft; no model inference is required."
                ),
                "run": str(run),
            }
        # Do not make the explanation depend on fresh source sidecars or current
        # review revisions; only its verified saved report/draft evidence is pinned.
        for name, digest in comparison["read_sha256"].items():
            path = Path(name)
            if path.is_relative_to(self.assessments.source):
                continue
            if hashlib.sha256(read_metadata_bytes(path)).hexdigest() != digest:
                raise ReviewConflict(
                    "Saved caption evidence changed while explaining; inspect again"
                )
        if result.get("status") == "available" and result.get("caption") != candidate["text"]:
            raise ValueError("Explained caption differs from the report's pinned draft")
        return {**result, **binding}


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
                elif path == "api/browsing-preferences":
                    self.reply(200, selected.browsing_preferences.read())
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
                elif path == "api/review-changes":
                    query = parse_qs(urlsplit(self.path).query)
                    self.reply(
                        200,
                        selected.review_changes(
                            limit=int(query.get("limit", ["20"])[0]),
                            offset=int(query.get("offset", ["0"])[0]),
                            kind=query.get("kind", [None])[0],
                        ),
                    )
                elif path == "api/training":
                    self.reply(200, selected.training())
                elif path.startswith("trainer-receipt/"):
                    _, identifier, name = path.split("/", 2)
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    self.reply(
                        200,
                        selected.trainer_artifact(
                            identifier,
                            name,
                            expected_receipt_sha256=query.get("receipt_sha256", [None])[0],
                        ),
                        "text/plain",
                    )
                elif path == "api/assessment":
                    state = selected.assessments.read()
                    self.reply(
                        200, {"state": state, "summary": selected.assessments.summary(state)}
                    )
                elif path.startswith("api/caption-comparison/"):
                    self.reply(
                        200,
                        selected.caption_comparison(path.removeprefix("api/caption-comparison/")),
                    )
                elif path.startswith("api/caption-explanation/"):
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if query.keys() - {"tag", "limit", "offset", "expected_run_sha256"} or any(
                        len(values) != 1 for key, values in query.items() if key != "tag"
                    ):
                        raise ValueError("Choose exact tags and one explanation page")
                    self.reply(
                        200,
                        selected.caption_explanation(
                            path.removeprefix("api/caption-explanation/"),
                            tags=query.get("tag"),
                            limit=int(query.get("limit", ["20"])[0]),
                            offset=int(query.get("offset", ["0"])[0]),
                            expected_run_sha256=query.get("expected_run_sha256", [None])[0],
                        ),
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
                if path == "api/browsing-preferences":
                    result = selected.browsing_preferences.save(payload)
                elif path == "api/pairs":
                    result = selected.save_pair(payload)
                elif path == "api/similarity-evaluation":
                    result = selected.evaluate_pairs()
                elif path == "api/publication":
                    result = selected.publication.start(payload)
                elif path == "api/assessment":
                    result = selected.assessments.save(payload)
                elif path.startswith("api/caption-comparison/"):
                    result = selected.caption_comparison(
                        path.removeprefix("api/caption-comparison/"), payload
                    )
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
