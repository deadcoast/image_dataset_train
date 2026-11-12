import json
from pathlib import Path

import pytest
from test_exports import reviewed as reviewed

import image_dataset_train.review_publication as publication_module
from image_dataset_train.assessments import PilotAssessment
from image_dataset_train.cli import main
from image_dataset_train.inventory import file_sha256
from image_dataset_train.qa import create_qa, list_qa, read_qa, select_pilot
from image_dataset_train.review_ui import ReviewSession
from image_dataset_train.reviews import review_image, review_status

REASON = "Frozen fixture membership chosen before assessment"
SELECTED = ["c.png", "a.png"]


def _report(reviewed, **kwargs):
    config, groups, drafts = reviewed
    return create_qa(
        config,
        groups,
        captions_run=drafts,
        pilot_source_paths=SELECTED,
        selection_reason=REASON,
        **kwargs,
    )


def _rewrite(report, meta, data):
    (report / "summary.json").write_text(json.dumps(data["summary"]), encoding="utf-8")
    (report / "entries.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in data["entries"]), encoding="utf-8"
    )
    for name in ("summary.json", "entries.jsonl"):
        meta["files"][name] = file_sha256(report / name)
    (report / "run.json").write_text(json.dumps(meta), encoding="utf-8")


def test_explicit_selection_freezes_exact_order_and_assessment_population(reviewed):
    report, summary = _report(reviewed, sample_size=1)
    meta, data = read_qa(report)
    selection = {"method": "explicit_source_paths", "source_paths": SELECTED, "reason": REASON}
    assert meta["pilot_selection"] == summary["pilot_selection"] == selection
    by_id = {entry["id"]: entry for entry in data["entries"]}
    assert [by_id[identifier]["source_path"] for identifier in summary["pilot_ids"]] == SELECTED
    assert summary["requested_pilot_images"] == summary["pilot_images"] == 2
    assert {entry["source_path"] for entry in list_qa(report, pilot=True)["entries"]} == set(
        SELECTED
    )
    store = PilotAssessment(reviewed[0].reviews, report)
    assert store.summary()["pilot_images"] == 2
    assert store.data["summary"]["pilot_ids"] == summary["pilot_ids"]


@pytest.mark.parametrize(
    "paths,reason,message",
    [
        ([], REASON, "nonempty"),
        (["a.png", "a.png"], REASON, "duplicates"),
        (["missing.png"], REASON, "absent"),
        (["e.png"], REASON, "excluded"),
        (["a.png"], None, "reason"),
        (["a.png"], "   ", "reason"),
        (None, REASON, "explicit"),
    ],
)
def test_invalid_explicit_membership_does_not_publish_or_create_pending_output(
    reviewed, paths, reason, message
):
    config, groups, drafts = reviewed
    before = set(config.runs.iterdir())
    with pytest.raises(ValueError, match=message):
        create_qa(
            config,
            groups,
            captions_run=drafts,
            pilot_source_paths=paths,
            selection_reason=reason,
        )
    assert set(config.runs.iterdir()) == before


def test_cli_repeat_image_publishes_selected_membership(reviewed, capsys):
    config, groups, drafts = reviewed
    settings = config.source.parent / "qa-settings.toml"
    settings.write_text(
        'schema_version = 1\n[paths]\nsource = "source"\nruns = "cli-runs"\nreviews = "reviews"\n',
        encoding="utf-8",
    )
    assert (
        main(
            [
                "qa",
                "--run",
                str(groups),
                "--captions",
                str(drafts),
                "--config",
                str(settings),
                "--image",
                "c.png",
                "--image",
                "a.png",
                "--reason",
                REASON,
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    meta, data = read_qa(Path(result["run"]))
    assert result["pilot_images"] == 2
    assert meta["pilot_selection"]["source_paths"] == SELECTED
    assert data["summary"]["pilot_selection"]["reason"] == REASON


def test_default_coverage_and_historical_reports_keep_their_selection(reviewed):
    config, groups, drafts = reviewed
    report, summary = create_qa(config, groups, captions_run=drafts, sample_size=3, seed=19)
    meta, data = read_qa(report)
    assert summary["pilot_ids"] == select_pilot(data["entries"], 3, 19)
    assert summary["pilot_selection"]["method"] == "coverage-v1"
    meta.pop("pilot_selection")
    data["summary"].pop("pilot_selection")
    _rewrite(report, meta, data)
    before = (report / "run.json").read_bytes()
    assert read_qa(report)[1]["summary"]["pilot_ids"] == summary["pilot_ids"]
    assert (report / "run.json").read_bytes() == before


@pytest.mark.parametrize("change", ["flags", "identities", "selection", "metadata"])
def test_checksums_cannot_hide_inconsistent_frozen_membership(reviewed, change):
    report, _ = _report(reviewed)
    meta, data = read_qa(report)
    if change == "flags":
        next(entry for entry in data["entries"] if entry["pilot"])["pilot"] = False
    elif change == "identities":
        data["summary"]["pilot_ids"][0] = "not-an-image-identity"
    elif change == "selection":
        data["summary"]["pilot_selection"]["source_paths"].reverse()
    else:
        meta["pilot_selection"]["reason"] = "different selection rationale"
    _rewrite(report, meta, data)
    with pytest.raises(ValueError, match="pilot"):
        read_qa(report)
    with pytest.raises(ValueError, match="pilot"):
        list_qa(report, pilot=True)


@pytest.mark.parametrize("mode", ["groups", "export"])
def test_republication_preserves_explicit_membership_and_reason_after_caption_change(
    reviewed, mode
):
    config, _, _ = reviewed
    report, summary = _report(reviewed)
    session = ReviewSession(config, report)
    saved = review_image(
        config, session.similarity, "c.png", caption="corrected blue", reason="new review"
    )
    session.publication.start({"mode": mode, "expected_revision": saved["revision"]})
    session.publication.wait()
    result = session.publication.read()
    assert result["status"] == "completed", result
    _, new_data = read_qa(Path(result["outputs"]["qa"]["path"]))
    assert new_data["summary"]["pilot_ids"] == summary["pilot_ids"]
    assert new_data["summary"]["pilot_selection"] == summary["pilot_selection"]
    request = json.loads(session.publication.path.read_text(encoding="utf-8"))["attempts"][-1][
        "request"
    ]
    assert request["pilot"]["selection"] == summary["pilot_selection"]
    assert (
        next(entry for entry in new_data["entries"] if entry["source_path"] == "c.png")["caption"]
        == "corrected blue"
    )


def test_republication_fails_when_a_frozen_member_is_now_excluded(reviewed):
    config, _, _ = reviewed
    report, summary = _report(reviewed)
    session = ReviewSession(config, report)
    saved = review_image(
        config, session.similarity, "c.png", decision="exclude", reason="excluded after sample"
    )
    session.publication.start({"mode": "groups", "expected_revision": saved["revision"]})
    session.publication.wait()
    result = session.publication.read()
    assert result["status"] == "failed" and "excluded" in result["message"]
    assert "qa" not in result["outputs"]
    assert read_qa(report)[1]["summary"]["pilot_ids"] == summary["pilot_ids"]


def test_publication_rejects_valid_qa_with_a_different_explicit_sample(reviewed, monkeypatch):
    config, _, _ = reviewed
    report, _ = _report(reviewed)
    session = ReviewSession(config, report)
    revision = review_status(config, session.similarity)["revision"]
    outputs = []

    def substituted(*args, **kwargs):
        kwargs["pilot_source_paths"] = ["b.png", "a.png"]
        result = create_qa(*args, **kwargs)
        outputs.append(result[0])
        return result

    monkeypatch.setattr(publication_module, "create_qa", substituted)
    session.publication.start({"mode": "groups", "expected_revision": revision})
    session.publication.wait()
    result = session.publication.read()
    assert result["status"] == "failed" and "selection" in result["message"]
    assert "qa" not in result["outputs"]
    assert read_qa(outputs[0])[1]["summary"]["pilot_selection"]["source_paths"] == [
        "b.png",
        "a.png",
    ]
