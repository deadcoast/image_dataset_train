import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from test_exports import reviewed as reviewed

import image_dataset_train.review_publication as publication_module
from image_dataset_train.exporting import verify_export
from image_dataset_train.qa import create_qa
from image_dataset_train.review_ui import ReviewSession
from image_dataset_train.reviews import ReviewConflict, review_image, review_status


@pytest.fixture
def publication(reviewed):
    config, groups, drafts = reviewed
    qa, _ = create_qa(config, groups, captions_run=drafts)
    session = ReviewSession(config, qa)
    revision = review_status(config, session.similarity)["revision"]
    return session, {"mode": "export", "expected_revision": revision}


def _finish(session, payload):
    session.publication.start(payload)
    session.publication.wait()
    return session.publication.read()


def _bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _failed_qa(session, payload, monkeypatch):
    original = publication_module.create_qa

    def fail(*args, **kwargs):
        raise OSError("fixture disk interruption")

    monkeypatch.setattr(publication_module, "create_qa", fail)
    result = _finish(session, payload)
    assert result["status"] == "failed" and set(result["outputs"]) == {"groups", "export"}
    monkeypatch.setattr(publication_module, "create_qa", original)
    return result


def test_completed_job_recovers_report_and_identical_submit_is_idempotent(publication):
    session, payload = publication
    protected = {root: _bytes(root) for root in (session.config.source, session.run)}
    completed = _finish(session, payload)
    assert completed["status"] == "completed", completed
    restarted = ReviewSession(session.config, session.run)
    assert restarted.publication.read()["outputs"] == completed["outputs"]
    qa = completed["outputs"]["qa"]
    assert restarted.reports[qa["report_id"]][1] == Path(qa["path"])
    again = _finish(restarted, payload)
    assert again["attempt_id"] == completed["attempt_id"] and len(again["attempts"]) == 1
    assert verify_export(Path(completed["outputs"]["export"]["path"]))["verified"]
    # Reports created inside an earlier publication can themselves publish sibling jobs.
    child = ReviewSession(session.config, Path(qa["path"]))
    assert _finish(child, payload)["status"] == "completed"
    assert all(_bytes(root) == before for root, before in protected.items())


def test_failed_later_stage_reuses_verified_outputs_after_restart(publication, monkeypatch):
    session, payload = publication
    payload["export"] = {
        "repeats": 3,
        "seed": 47,
        "resolution": 512,
        "validation_ratio": 0.4,
        "split_strategy": "size",
    }
    failed = _failed_qa(session, payload, monkeypatch)
    snapshots = {Path(o["path"]): _bytes(Path(o["path"])) for o in failed["outputs"].values()}
    restarted = ReviewSession(session.config, session.run)
    settings = restarted.publication.read()["settings"]
    assert settings["mode"] == "export"
    assert settings["captions_run"] == session.meta["caption_run"]
    assert all(settings["export"][key] == value for key, value in payload["export"].items())

    def duplicate(*args, **kwargs):
        raise AssertionError("A verified output must not be republished")

    monkeypatch.setattr(publication_module, "publish_groups", duplicate)
    monkeypatch.setattr(publication_module, "export_dataset", duplicate)
    result = _finish(restarted, payload)
    assert result["status"] == "completed", result
    assert result["reused_stages"] == ["groups", "export"]
    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][0]["error"]["message"] == "fixture disk interruption"
    assert result["attempts"][1]["id"] != failed["attempt_id"]
    assert all(_bytes(root) == before for root, before in snapshots.items())


@pytest.mark.parametrize("stage", ["groups", "export", "qa"])
def test_real_process_exit_between_stage_publish_and_checkpoint_is_reconciled(
    publication, monkeypatch, stage
):
    session, payload = publication
    config = session.config
    script = """
import json, os, sys
from pathlib import Path
from image_dataset_train.config import Config, ExportConfig, ValidationConfig
from image_dataset_train.review_ui import ReviewSession
from image_dataset_train.review_publication import Publication
source, runs, reviews, exports, qa, revision, stage = sys.argv[1:]
config = Config(Path(source), Path(runs), ValidationConfig(), reviews=Path(reviews),
                exports=Path(exports), export=ExportConfig(validation_ratio=0.25))
original = Publication._checkpoint
def interrupted(self, attempt, current, path):
    if current == stage:
        os._exit(81)
    return original(self, attempt, current, path)
Publication._checkpoint = interrupted
session = ReviewSession(config, Path(qa))
session.publication.start({'mode': 'export', 'expected_revision': int(revision)})
session.publication.wait()
print(json.dumps(session.publication.read()))
"""
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            *map(
                str,
                (
                    config.source,
                    config.runs,
                    config.reviews,
                    config.exports,
                    session.run,
                    payload["expected_revision"],
                    stage,
                ),
            ),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert process.returncode == 81, process.stdout + process.stderr
    job = json.loads(session.publication.path.read_text())
    assert job["attempts"][-1]["status"] == "running"
    assert stage not in job["attempts"][-1]["outputs"]
    restarted = ReviewSession(config, session.run)
    recovered = restarted.publication.read()
    assert stage in recovered["outputs"]
    orphan_path = recovered["outputs"][stage]["path"]

    def duplicate(*args, **kwargs):
        raise AssertionError("Reconciled stage must not execute again")

    monkeypatch.setattr(
        publication_module,
        {"groups": "publish_groups", "export": "export_dataset", "qa": "create_qa"}[stage],
        duplicate,
    )
    result = _finish(restarted, payload)
    assert result["status"] == "completed", result
    assert result["outputs"][stage]["path"] == orphan_path
    assert len(result["attempts"]) == (1 if stage == "qa" else 2)


@pytest.mark.parametrize("change", ["settings", "reviews", "input"])
def test_changed_request_creates_fresh_attempt_without_reusing_outputs(
    publication, monkeypatch, change
):
    session, payload = publication
    old = _failed_qa(session, payload, monkeypatch)
    if change == "settings":
        payload["export"] = {"repeats": 2}
    elif change == "reviews":
        saved = review_image(
            session.config,
            session.similarity,
            "c.png",
            caption="corrected blue",
            reason="New review revision",
        )
        payload["expected_revision"] = saved["revision"]
    else:
        caption = Path(session.meta["caption_run"])
        (caption / "additional-evidence.txt").write_text("new diagnostic context", encoding="utf-8")
    restarted = ReviewSession(session.config, session.run)
    result = _finish(restarted, payload)
    assert result["status"] == "completed", result
    assert result["reused_stages"] == [] and len(result["attempts"]) == 2
    assert result["outputs"]["groups"]["path"] != old["outputs"]["groups"]["path"]


@pytest.mark.parametrize("damage", ["payload", "completed_with_errors", "source"])
def test_invalid_saved_output_is_preserved_but_not_adopted(publication, monkeypatch, damage):
    session, payload = publication
    failed = _failed_qa(session, payload, monkeypatch)
    groups = Path(failed["outputs"]["groups"]["path"])
    if damage == "payload":
        (groups / "summary.json").write_text("{}", encoding="utf-8")
    else:
        metadata = json.loads((groups / "run.json").read_text())
        metadata["status" if damage == "completed_with_errors" else "source"] = (
            "completed_with_errors" if damage == "completed_with_errors" else str(groups)
        )
        (groups / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    damaged = _bytes(groups)
    restarted = ReviewSession(session.config, session.run)
    assert restarted.publication.read()["outputs"] == {}
    result = _finish(restarted, payload)
    assert result["status"] == "completed" and result["reused_stages"] == []
    assert _bytes(groups) == damaged


def test_source_drift_and_stale_revision_reject_retry(publication, monkeypatch):
    session, payload = publication
    _failed_qa(session, payload, monkeypatch)
    before = len(session.publication.document["attempts"])
    with pytest.raises(ReviewConflict, match="changed"):
        session.publication.start(
            {**payload, "expected_revision": payload["expected_revision"] - 1}
        )
    source = session.config.source / "a.png"
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed since inventory"):
        session.publication.start(payload)
    assert len(session.publication.document["attempts"]) == before


def test_polling_and_second_session_cannot_lose_or_duplicate_live_checkpoints(
    publication, monkeypatch
):
    session, payload = publication
    entered, release = Event(), Event()
    original = publication_module.export_dataset

    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return original(*args, **kwargs)

    monkeypatch.setattr(publication_module, "export_dataset", paused)
    session.publication.start(payload)
    try:
        assert entered.wait(15)
        assert set(session.publication.read()["outputs"]) == {"groups"}
        second = ReviewSession(session.config, session.run)
        assert second.publication.read()["status"] == "running"
        with pytest.raises(ReviewConflict, match="already running"):
            second.publication.start(payload)
        for _ in range(4):
            assert session.publication.read()["status"] == "running"
    finally:
        release.set()
        session.publication.wait()
    assert session.publication.read()["status"] == "completed"
    assert set(second.publication.read()["outputs"]) == {"groups", "export", "qa"}


def test_publication_lock_is_shared_between_processes(publication):
    session, payload = publication
    session.publication.root.mkdir(parents=True, exist_ok=True)
    script = """
import sys
from filelock import FileLock
with FileLock(sys.argv[1], timeout=0):
    print('locked', flush=True)
    sys.stdin.readline()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(session.publication.lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(ReviewConflict, match="already running"):
            session.publication.start(payload)
        assert not session.publication.path.exists()
    finally:
        process.communicate("release\n", timeout=15)
    assert _finish(session, payload)["status"] == "completed"


@pytest.mark.parametrize("destination", ["runs", "exports", "reviews"])
def test_publication_output_must_not_overlap_input_artifacts(publication, destination):
    session, payload = publication
    before = _bytes(session.run)
    config = replace(session.config, **{destination: session.run / "nested"})
    with pytest.raises(ValueError, match="separate trees"):
        candidate = ReviewSession(config, session.run)
        candidate.publication.start(payload)
    assert _bytes(session.run) == before


def test_publication_protects_qa_input_snapshot(publication):
    session, payload = publication
    original = Path(session.meta["input_run"])
    before = _bytes(original)
    candidate = ReviewSession(replace(session.config, runs=original / "nested"), session.run)
    with pytest.raises(ValueError, match="separate trees"):
        candidate.publication.start(payload)
    assert _bytes(original) == before
