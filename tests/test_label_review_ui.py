"""Local reviewer behavior, input integrity, atomic edits and exposure provenance."""

import io
import json
from http.client import HTTPConnection
from threading import Thread
from urllib.parse import urlsplit

import pytest
from PIL import Image
from test_label_evaluation import evaluation_pilot as evaluation_pilot

from image_dataset_train.label_review_ui import LabelReviewSession, make_label_server
from image_dataset_train.label_workspace import LabelWorkspace
from image_dataset_train.reviews import ReviewConflict


def changes(session, digest, *, value="present", expected=None):
    return {
        "image": digest,
        "expected_revision": session.store.read()["revision"] if expected is None else expected,
        "judgments": [
            {
                "label": label,
                "value": value,
                "reviewer": "Fixture assistant",
                "reviewer_kind": "assistant",
                "notes": "Visible synthetic fixture evidence",
            }
            for label in sorted(session.store.labels)
        ],
    }


def reveal(session, digest):
    return session.compare(
        {
            "image": digest,
            "expected_revision": session.store.read()["revision"],
            "reviewer": "Fixture comparison viewer",
            "reviewer_kind": "human",
        }
    )


def test_review_first_then_comparison_retains_exposure_after_reopen_and_clear(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    session = LabelReviewSession(config, path, [scored])
    digest = next(iter(session.store.members))
    state = session.state()
    assert all(set(member) == {"sha256", "paths"} for member in state["members"])
    assert "scores" not in json.dumps(state)
    with pytest.raises(ValueError, match="Save all labels"):
        reveal(session, digest)
    session.save(changes(session, digest))
    initial = session.store.read()
    result = reveal(session, digest)
    assert result["models"][0]["scores"] == {"blue_hair": 0.5, "red_eyes": 0.5}
    state = session.store.read()
    assert state["history"][:2] == initial["history"]
    for label, record in state["judgments"][digest].items():
        assert record["value"] == initial["judgments"][digest][label]["value"]
        assert record["reviewer_kind"] == "assistant"
        assert record["comparison_exposure"][0]["reviewer_kind"] == "human"
    revision = state["revision"]
    reveal(session, digest)
    assert session.store.read()["revision"] == revision  # Same viewer/run already disclosed.
    session = LabelReviewSession(config, path, [scored])
    session.save(changes(session, digest, value="unreviewed"))
    session.save(changes(session, digest, value="absent"))
    assert all(
        record["comparison_exposure"]
        for record in session.store.read()["judgments"][digest].values()
    )


def test_caption_or_score_corruption_never_records_comparison(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    session = LabelReviewSession(config, path, [scored])
    digest = next(iter(session.store.members))
    session.save(changes(session, digest))
    before = (path / "judgments.json").read_bytes()
    model, _, rows = session._scored(scored)
    row = next(row for (_, sha), row in rows.items() if sha == digest)
    caption = scored / row["caption_path"]
    original = caption.read_bytes()
    caption.write_bytes(b"changed caption")
    with pytest.raises(ValueError, match="caption file"):
        reveal(session, digest)
    assert (path / "judgments.json").read_bytes() == before
    caption.write_bytes(original)
    (scored / model.index[digest]["path"]).write_bytes(b"broken scores")
    with pytest.raises(ValueError, match="hash mismatch"):
        reveal(session, digest)
    assert (path / "judgments.json").read_bytes() == before


def test_model_comparison_requires_full_frozen_identity_coverage(evaluation_pilot):
    config, _, _, path, factory = evaluation_pilot
    missing = next(iter(LabelWorkspace(path).members))
    incomplete = factory(omit=missing)
    with pytest.raises(ValueError, match="every frozen"):
        LabelReviewSession(config, path, [incomplete])


def test_model_metadata_change_after_session_open_is_rejected(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    session = LabelReviewSession(config, path, [scored])
    digest = next(iter(session.store.members))
    session.save(changes(session, digest))
    before = (path / "judgments.json").read_bytes()
    metadata = json.loads((scored / "run.json").read_text(encoding="utf-8"))
    metadata["model"]["revision"] = "b" * 40
    (scored / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata changed"):
        reveal(session, digest)
    assert (path / "judgments.json").read_bytes() == before


def test_stale_save_and_changed_source_preserve_judgments(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    session = LabelReviewSession(config, path, [scored])
    digest = next(iter(session.store.members))
    session.save(changes(session, digest))
    before = (path / "judgments.json").read_bytes()
    with pytest.raises(ReviewConflict):
        session.save(changes(session, digest, expected=0))
    source = config.source / session.store.members[digest]["aliases"][0]["source_path"]
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError):
        session.save(changes(session, digest, value="absent"))
    assert (path / "judgments.json").read_bytes() == before


def test_http_origin_token_guards_and_image_save_roundtrip(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    with make_label_server(config, path, scored_runs=[scored]) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        parts = urlsplit(server.url)

        def request(method, target, payload=None, **headers):
            connection = HTTPConnection(parts.hostname, parts.port)
            body = json.dumps(payload) if payload is not None else None
            connection.request(method, target, body, headers)
            response = connection.getresponse()
            result = response.status, response.read(), dict(response.getheaders())
            connection.close()
            return result

        try:
            status, html, headers = request("GET", parts.path)
            assert status == 200 and b"Critical-label review" in html
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
            assert request("GET", "/api/state")[0] == 403
            assert request("GET", parts.path + "api/state", Host="attacker.invalid")[0] == 403
            digest = next(iter(server.label_session.store.members))
            payload = changes(server.label_session, digest)
            assert (
                request(
                    "POST", parts.path + "api/save", payload, **{"Content-Type": "application/json"}
                )[0]
                == 403
            )
            status, raw, _ = request("GET", parts.path + "image/" + digest)
            assert status == 200
            with Image.open(io.BytesIO(raw)) as image:
                assert image.mode == "RGBA"
            post_headers = {
                "Content-Type": "application/json",
                "Origin": "http://" + server.authority,
            }
            status, raw, _ = request("POST", parts.path + "api/save", payload, **post_headers)
            assert status == 200 and json.loads(raw)["revision"] == 2
            assert request("POST", parts.path + "api/save", payload, **post_headers)[0] == 409
            status, raw, _ = request("GET", parts.path + "api/state")
            assert json.loads(raw)["judgments"][digest]["blue_hair"]["reviewer_kind"] == "assistant"
        finally:
            server.shutdown()
            worker.join(timeout=5)
