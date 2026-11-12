"""Live preference endpoints remain portable between local reviewer launches."""

import copy
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image, ImageDraw
from test_review_preferences import tree

from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.qa import create_qa
from image_dataset_train.review_ui import ReviewSession, make_server
from image_dataset_train.reviews import publish_groups, review_image
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


@pytest.fixture
def report_fixture(tmp_path, monkeypatch):
    home = tmp_path / "application"
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    source = tmp_path / "source"
    source.mkdir()
    for index, name in enumerate(("first.png", "second.png")):
        image = Image.new("RGB", (32, 48), "white")
        ImageDraw.Draw(image).rectangle((2 + index * 8, 3, 6 + index * 8, 30), fill="black")
        image.save(source / name)
        (source / Path(name).with_suffix(".txt")).write_text(
            "a generated fixture", encoding="utf-8"
        )
    (source / "alias.png").write_bytes((source / "first.png").read_bytes())
    config = Config(
        source,
        tmp_path / "runs",
        ValidationConfig(),
        models=tmp_path / "models",
        scores=tmp_path / "scores",
        reviews=tmp_path / "reviews",
        exports=tmp_path / "exports",
    )
    inventory, _ = run_scan(config)
    similarity, _ = propose_similar(config, inventory, max_distance=64)
    review_image(
        config,
        similarity,
        "first.png",
        decision="include",
        reason="generated test",
        add_labels=["portrait"],
        subset="solo",
    )
    review_image(
        config,
        similarity,
        "alias.png",
        decision="include",
        reason="generated alias",
        caption="alias saved caption",
    )
    groups, _ = publish_groups(config, similarity)
    report, _ = create_qa(config, groups, sample_size=2)
    return {"config": config, "report": report, "home": home, "similarity": similarity}


@contextmanager
def serving(fixture, *, report=None):
    with make_server(fixture["config"], report or fixture["report"]) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join(timeout=5)


def request(server, path="api/browsing-preferences", *, payload=None, headers=None, url=None):
    header_values = {"Origin": "http://" + server.authority, "Content-Type": "application/json"}
    header_values.update(headers or {})
    raw = json.dumps(payload).encode() if payload is not None else None
    req = Request(url or server.url + path, data=raw, headers=header_values)
    with urlopen(req, timeout=10) as response:
        assert response.headers["Cache-Control"] == "no-store"
        if response.headers["Content-Type"].startswith("text/html"):
            return response.read().decode()
        return json.load(response)


def proposed(server, state):
    session = server.review_sessions[""]
    entry = next(row for row in session.data["entries"] if row["source_path"] == "alias.png")
    payload = {
        "expected_revision": state["revision"],
        "last": copy.deepcopy(state["last"]),
        "views": [],
    }
    payload["last"].update(image_id=entry["id"], position=1)
    payload["last"]["filters"].update(search="alias", pilot=True)
    payload["last"]["pair"].update(decision="all", offset=20, pair_id="e" * 64)
    payload["views"] = [{"name": "aliases", "filters": copy.deepcopy(payload["last"]["filters"])}]
    return payload


def test_get_page_and_preferences_create_nothing_and_keep_decisions_separate(
    report_fixture, tmp_path
):
    with serving(report_fixture) as server:
        session = server.review_sessions[""]
        before = tree(tmp_path)
        state = request(server)
        page = request(server, "")
        assert (
            state["revision"] == 0 and state["report_id"] == session.browsing_preferences.report_id
        )
        assert "browsing" in page and "qa_preferences" not in state
        assert session.page()["browsing"] == {
            "report_id": state["report_id"],
            "state": state,
            "error": None,
        }
        assert tree(tmp_path) == before and not session.browsing_preferences.directory.exists()
        saved = request(server, payload=proposed(server, state))
        after = tree(tmp_path)
        assert saved["revision"] == 1 and request(server) == saved
        assert all(after[path] == digest for path, digest in before.items())
        assert all(
            path.replace("\\", "/").startswith("application/review-preferences/")
            for path in after.keys() - before.keys()
        )
        assert session.assessments.read()["revision"] == 0


def test_relaunch_on_a_different_port_restores_exact_report_and_alias(report_fixture):
    with serving(report_fixture) as first:
        saved = request(first, payload=proposed(first, request(first)))
        # Keep the first socket reserved so the second launch must use a distinct port.
        first.shutdown()
        with serving(report_fixture) as second:
            assert second.server_port != first.server_port and second.url != first.url
            assert request(second) == saved
            session = second.review_sessions[""]
            alias = session.entries[saved["last"]["image_id"]]
            original = next(
                row for row in session.data["entries"] if row["source_path"] == "first.png"
            )
            assert alias["source_path"] == "alias.png" and alias["sha256"] == original["sha256"]
            assert alias["id"] != original["id"]


def test_equal_metadata_at_another_report_path_has_independent_preferences(
    report_fixture, tmp_path
):
    copied = tmp_path / "copied-qa"
    shutil.copytree(report_fixture["report"], copied)
    with serving(report_fixture) as original, serving(report_fixture, report=copied) as other:
        saved = request(original, payload=proposed(original, request(original)))
        separate = request(other)
        assert separate["report_id"] != saved["report_id"]
        assert separate["revision"] == 0 and separate["views"] == []
        assert request(original) == saved


def test_stale_tab_returns_409_without_rolling_back_saved_views(report_fixture):
    with serving(report_fixture) as first, serving(report_fixture) as second:
        stale = proposed(second, request(second))
        current = proposed(first, request(first))
        current["views"][0]["name"] = "newer view"
        saved = request(first, payload=current)
        with pytest.raises(HTTPError) as error:
            request(second, payload=stale)
        assert error.value.code == 409
        assert "another session" in json.load(error.value)["error"]
        assert request(second) == saved


@pytest.mark.parametrize(
    "change", ["image", "caption", "reason", "assessment", "unknown-filter", "missing-key"]
)
def test_invalid_http_payload_never_writes_preferences_or_evidence(
    report_fixture, tmp_path, change
):
    with serving(report_fixture) as server:
        payload = proposed(server, request(server))
        if change == "image":
            payload["last"]["image_id"] = "0" * 64
        elif change == "caption":
            payload["caption"] = "unsaved correction"
        elif change == "reason":
            payload["last"]["reason"] = "unsaved pair reason"
        elif change == "assessment":
            payload["assessment"] = {"human_acceptance": True}
        elif change == "unknown-filter":
            payload["last"]["filters"]["label"] = "not in snapshot"
        else:
            del payload["views"]
        before = tree(tmp_path)
        with pytest.raises(HTTPError) as error:
            request(server, payload=payload)
        assert error.value.code == 400 and tree(tmp_path) == before


@pytest.mark.parametrize("guard", ["origin", "host", "token", "content-type"])
def test_preference_write_uses_existing_session_security_guards(report_fixture, tmp_path, guard):
    with serving(report_fixture) as server:
        payload = proposed(server, request(server))
        headers = {}
        address = None
        if guard == "origin":
            headers["Origin"] = "http://external.example"
        elif guard == "host":
            headers["Host"] = "external.example"
        elif guard == "token":
            address = "http://" + server.authority + "/wrong-session/api/browsing-preferences"
        else:
            headers["Content-Type"] = "text/plain"
        before = tree(tmp_path)
        with pytest.raises(HTTPError) as error:
            request(server, payload=payload, headers=headers, url=address)
        assert error.value.code == 403 and tree(tmp_path) == before


def test_corrupt_preferences_do_not_block_page_or_review_and_cannot_be_reset(
    report_fixture, tmp_path
):
    with serving(report_fixture) as server:
        session = server.review_sessions[""]
        payload = proposed(server, request(server))
        request(server, payload=payload)
        store = session.browsing_preferences
        store.path.write_bytes(b"{preserve damaged preferences")
        before = tree(tmp_path)
        page = request(server, "")
        assert "preserve the file" in page
        assert session.page()["browsing"]["state"] is None
        identifier = next(iter(session.entries))
        review = request(server, "api/review/" + identifier)
        assert "revision" in review
        for kwargs in ({}, {"payload": payload}):
            with pytest.raises(HTTPError) as error:
                request(server, **kwargs)
            assert error.value.code == 400
        assert tree(tmp_path) == before


def test_source_offline_preserves_resume_and_never_creates_decisions(report_fixture, tmp_path):
    with serving(report_fixture) as server:
        saved = request(server, payload=proposed(server, request(server)))
    report_fixture["config"].source.rename(tmp_path / "offline-source")
    with serving(report_fixture) as reopened:
        before = tree(tmp_path)
        assert request(reopened) == saved
        assert "browsing" in request(reopened, "")
        assert tree(tmp_path) == before


def test_changed_exact_report_identity_rejects_preferences_without_overwriting(report_fixture):
    with serving(report_fixture) as server:
        payload = proposed(server, request(server))
        request(server, payload=payload)
        store = server.review_sessions[""].browsing_preferences
        before = store.path.read_bytes()
        metadata = report_fixture["report"] / "run.json"
        metadata.write_bytes(metadata.read_bytes() + b"\n")
        for kwargs in ({}, {"payload": payload}):
            with pytest.raises(HTTPError) as error:
                request(server, **kwargs)
            assert error.value.code == 400
            assert "identity changed" in json.load(error.value)["error"]
        assert store.path.read_bytes() == before


def test_unsafe_application_home_isolated_to_browsing_panel(report_fixture, monkeypatch):
    config = report_fixture["config"]
    monkeypatch.setenv("TRAINIME_HOME", str(config.source / "unsafe-home"))
    session = ReviewSession(config, report_fixture["report"])
    page = session.page()
    assert page["browsing"]["state"] is None
    assert "outside source" in page["browsing"]["error"]
    assert not (config.source / "unsafe-home").exists()
    assert session.review(next(iter(session.entries)))["revision"] >= 0
