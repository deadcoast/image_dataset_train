import io
import json
import tomllib
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import numpy as np
import pytest
from PIL import Image, ImageDraw

from image_dataset_train.assessments import PilotAssessment
from image_dataset_train.cli import main
from image_dataset_train.config import CaptionConfig, Config, ExportConfig, ValidationConfig
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.exporting import (
    _prepare_export_image,
    assign_splits,
    export_dataset,
    verify_export,
)
from image_dataset_train.inventory import file_sha256
from image_dataset_train.model_bundle import Label
from image_dataset_train.qa import create_qa, list_qa
from image_dataset_train.review_ui import ReviewSession, make_server
from image_dataset_train.reviews import publish_groups, review_image, review_pair, review_status
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar
from image_dataset_train.tagging import _publish, recaption
from image_dataset_train.trainer_receipts import trainer_pin, trainer_status


@pytest.fixture
def reviewed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for i, name in enumerate(("a", "b", "c", "e")):
        image = Image.new("RGB", (128, 192), "white")
        ImageDraw.Draw(image).rectangle((i * 4, 2, i * 4 + 10, 20), fill="black")
        image.save(source / f"{name}.png")
    (source / "alias.png").write_bytes((source / "a.png").read_bytes())
    (source / "a.txt").write_text("original caption\nsecond line", encoding="utf-8")
    (source / "alias.txt").write_text("alias caption", encoding="utf-8")
    config = Config(
        source,
        tmp_path / "runs",
        ValidationConfig(),
        reviews=tmp_path / "reviews",
        exports=tmp_path / "exports",
        export=ExportConfig(validation_ratio=0.25),
    )
    inventory, _ = run_scan(config)
    similarity, _ = propose_similar(config, inventory, max_distance=64)
    for pair in review_status(config, similarity, limit=100)["pairs"]:
        related = {pair["left_source_path"], pair["right_source_path"]} == {"a.png", "b.png"}
        review_pair(
            config, similarity, pair["pair_id"], "related" if related else "distinct", "inspected"
        )
    for name in ("a", "alias", "b", "c", "e"):
        review_image(
            config,
            similarity,
            f"{name}.png",
            decision="exclude" if name == "e" else "include",
            reason="inspected",
            add_labels=[
                "excluded-only" if name == "e" else "scenery" if name == "c" else "portrait"
            ],
            subset="scenery" if name == "c" else "solo",
        )
    review_image(config, similarity, "b.png", caption="human override", reason="corrected")
    groups, _ = publish_groups(config, similarity)
    meta = json.loads((groups / "run.json").read_text())
    members = [
        m
        for line in (groups / "groups.jsonl").read_text().splitlines()
        for m in json.loads(line)["members"]
    ]
    c = next(m for m in members if m["source_path"] == "c.png")
    # Real caption publication supplies the same artifact that tagging/recaption exports.
    drafts = _publish(
        config.runs,
        [{"source_path": "c.png", "sha256": c["sha256"], "decision": "tagged"}],
        {c["sha256"]: np.array([0.9], dtype=np.float32)},
        [Label(0, "blue_hair", 0)],
        {
            "stage": "recaption",
            "source": str(source),
            "inventory_manifest_sha256": meta["inventory_manifest_sha256"],
        },
        {},
        CaptionConfig(),
        0.35,
    )
    return config, groups, drafts


def test_export_connects_reviews_captions_groups_and_portable_verification(reviewed):
    config, groups, drafts = reviewed
    original = {p.name: p.read_bytes() for p in config.source.iterdir()}
    output, summary = export_dataset(config, groups, captions_run=drafts)
    assert summary["split_images"] == {"train": 3, "validation": 1}
    assert summary["caption_origins"] == {"sidecar": 2, "override": 1, "draft": 1}
    assert summary["split_algorithm"] == "semantic-groups-v1"
    assert summary["annotations"]["labels"] == {"portrait": 3, "scenery": 1}
    rows = [json.loads(line) for line in (output / "manifest.jsonl").read_text().splitlines()]
    by_name = {r["source_path"]: r for r in rows}
    assert by_name["a.png"]["split"] == by_name["alias.png"]["split"] == by_name["b.png"]["split"]
    assert by_name["a.png"]["caption"] == "original caption second line"
    assert by_name["a.png"]["labels"] == ["portrait"] and by_name["a.png"]["subset"] == "solo"
    assert by_name["c.png"]["caption"] == "blue hair" and "e.png" not in by_name
    for row in rows:
        assert (output / row["image_path"]).read_bytes() == original[row["source_path"]]
        assert (row["width"], row["height"]) == (128, 192)
        assert (output / row["caption_path"]).read_text() == row["caption"] + "\n"
    adapter = tomllib.loads((output / "train.toml").read_text())
    assert adapter["datasets"][0]["subsets"] == [{"image_dir": "train", "num_repeats": 1}]
    again, _ = export_dataset(config, groups, captions_run=drafts)
    assert (again / "splits.json").read_bytes() == (output / "splits.json").read_bytes()
    assert (again / "manifest.jsonl").read_bytes() == (output / "manifest.jsonl").read_bytes()
    assert original == {p.name: p.read_bytes() for p in config.source.iterdir()}
    config.source.rename(config.source.with_name("offline"))
    assert verify_export(output)["verified"]
    (output / rows[0]["image_path"]).write_bytes(b"damaged")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_export(output)
    assert (config.source.with_name("offline") / rows[0]["source_path"]).read_bytes() == original[
        rows[0]["source_path"]
    ]


@pytest.mark.parametrize("changed", ["a.png", "a.txt"])
def test_changed_source_or_sidecar_cannot_be_published(reviewed, changed):
    config, groups, drafts = reviewed
    (config.source / changed).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed since inventory"):
        export_dataset(config, groups, captions_run=drafts)
    assert not [p for p in config.exports.iterdir() if not p.name.startswith(".pending-")]


def test_qa_connects_incomplete_reviews_captions_and_coverage(reviewed, capsys, monkeypatch):
    config, groups, _ = reviewed
    from pathlib import Path

    similarity = Path(json.loads((groups / "run.json").read_text())["similarity_run"])
    review_image(config, similarity, "e.png", decision="unreviewed", reason="revisit")
    review_image(
        config,
        similarity,
        "b.png",
        caption="portrait, PORTRAIT, </script>",
        clear_labels=True,
        clear_subset=True,
        reason="inspect caption",
    )
    groups, _ = publish_groups(config, similarity)
    (config.source / "a.png").write_bytes(b"changed after snapshot")
    before = {
        p: p.read_bytes()
        for root in (config.source, config.reviews)
        for p in root.rglob("*")
        if p.is_file()
    }
    output, summary = create_qa(config, groups, sample_size=3, seed=7)
    assert summary["split_state"] == "preview" and not summary["human_accepted"]
    assert summary["findings"]["decision_pending"] == 1
    assert summary["findings"]["caption_missing"] == 2
    entries = {e["source_path"]: e for e in list_qa(output)["entries"]}
    assert "image_unavailable" in entries["a.png"]["findings"]
    assert entries["b.png"]["labels_reviewed"] and entries["b.png"]["subset_reviewed"]
    assert "labels_pending" not in entries["b.png"]["findings"]
    assert "caption_repeated_phrase" in entries["b.png"]["findings"]
    assert "coverage_single_group" in entries["c.png"]["findings"]
    assert list_qa(output, finding="caption_missing")["total"] == 2
    assert list_qa(output, label="PORTRAIT", split="train")["total"] == 2
    assert list_qa(output, group=entries["a.png"]["group_id"])["total"] == 3
    assert list_qa(output, pilot=True, limit=2)["next_offset"] == 2
    assert list_qa(output, pilot=True, offset=2)["next_offset"] is None
    _, repeated = create_qa(config, groups, sample_size=3, seed=7)
    assert repeated["pilot_ids"] == summary["pilot_ids"]
    assert all(p.read_bytes() == raw for p, raw in before.items())
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "portrait, PORTRAIT, </script>" not in html
    assert "portrait, PORTRAIT, \\u003c/script>" in html
    monkeypatch.chdir(config.source)  # Saved QA navigation needs no local config.toml.
    assert main(["qa-list", "--run", str(output), "--subset", "solo", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 3


def test_qa_export_uses_frozen_images_captions_and_annotations(reviewed):
    config, groups, drafts = reviewed
    output, _ = export_dataset(config, groups, captions_run=drafts)
    config.source.rename(config.source.with_name("offline"))
    report, summary = create_qa(config, output, sample_size=50)
    assert summary["images"] == summary["pilot_images"] == 4
    assert summary["split_state"] == "published"
    assert summary["caption_origins"] == {"sidecar": 2, "override": 1, "draft": 1}
    assert summary["split_images"] == {"train": 3, "validation": 1}
    entries = list_qa(report)["entries"]
    assert {e["source_path"] for e in entries} == {"a.png", "alias.png", "b.png", "c.png"}
    assert all(not e["errors"] and (report / e["preview"]).is_file() for e in entries)
    assert all(e["review_args"][-2:] == ["--image", e["source_path"]] for e in entries)
    assert verify_export(output)["verified"]
    with pytest.raises(ValueError, match="freezes captions"):
        create_qa(config, output, captions_run=drafts)


def test_content_report_uses_snapshot_members_and_frozen_provenance(reviewed):
    config, groups, _ = reviewed
    meta = json.loads((groups / "run.json").read_text())
    members = [
        m
        for line in (groups / "groups.jsonl").read_text().splitlines()
        for m in json.loads(line)["members"]
    ]
    rows = [
        {"source_path": m["source_path"], "sha256": m["sha256"], "decision": "tagged"}
        for m in members
    ]
    vectors = {
        m["sha256"]: np.array(
            [0, 0, 0, 0.9, 0.2, 0.8]
            if m["source_path"] == "e.png"
            else [0.9, 0.9, 0.9, 0, 0.5, 0.5]
            if m["source_path"] == "c.png"
            else [0.9, 0.9, 0.9, 0, 0.8, 0.2],
            dtype=np.float32,
        )
        for m in members
    }
    rows.append({**rows[0], "source_path": "outside-snapshot.png"})
    from image_dataset_train.config import SubsetRule

    drafts = _publish(
        config.runs,
        rows,
        vectors,
        [
            Label(i, name, category)
            for i, (name, category) in enumerate(
                [
                    ("blue_theme", 0),
                    ("1girl", 0),
                    ("solo", 0),
                    ("excluded_tag", 0),
                    ("general", 9),
                    ("sensitive", 9),
                ]
            )
        ],
        {
            "stage": "recaption",
            "source": str(config.source),
            "inventory_manifest_sha256": meta["inventory_manifest_sha256"],
            "model": {"model": "fixture", "revision": "a" * 40, "artifact_id": "b" * 64},
            "runtime": {"providers": ["CPUExecutionProvider"], "onnxruntime": "fixture"},
            "requested_device": "cpu",
            "preprocessing": "fixture",
            "provider_fallback": None,
        },
        {},
        CaptionConfig(
            drop_tags=["blue_theme"],
            force_tags=["configured phrase"],
            subset_rules=[SubsetRule("blue", all_tags=["blue_theme"])],
        ),
        0.35,
    )
    _, summary = create_qa(config, groups, captions_run=drafts)
    content = summary["content"]
    included, whole = content["scopes"]["included"], content["scopes"]["snapshot"]
    assert (included["images"], whole["images"], included["unique_images"]) == (4, 5, 3)
    assert included["tagged_images"] == 4 and included["untagged_images"] == 0
    assert included["ratings"] == {
        "available_images": 4,
        "unavailable_images": 0,
        "tied_images": 1,
        "counts": {"general": 3},
    }
    assert whole["ratings"]["counts"] == {"general": 3, "sensitive": 1}
    observed = {t["name"]: t["images"] for t in included["observed_tags"]["top_tags"]}
    assert observed == {"blue_theme": 4, "1girl": 4, "solo": 4}
    assert {t["name"] for t in included["selected_tags"]["top_tags"]} == {"1girl", "solo"}
    assert included["composition"]["counts"] == {"single_subject": 4}
    assert included["subset_proposals"]["counts"] == {"blue": 4}
    assert included["reviewed_annotations"]["subsets"] == {"scenery": 1, "solo": 3}
    assert content["provenance"]["runtime"]["providers"] == ["CPUExecutionProvider"]
    assert content["provenance"]["model"]["revision"] == "a" * 40
    output, _ = export_dataset(config, groups, captions_run=drafts)
    config.source.rename(config.source.with_name("offline"))
    drafts.rename(drafts.with_name("offline-drafts"))
    report, exported = create_qa(config, output)
    assert exported["content"]["scopes"]["snapshot"] == included
    assert exported["content"]["provenance"] == content["provenance"]
    assert exported["content"]["evidence_source"] == "export_provenance"
    from image_dataset_train.qa import read_qa

    assert read_qa(report)[1]["summary"]["content"] == exported["content"]
    assert verify_export(output)["verified"]


def test_qa_reconciles_counts_and_keeps_measured_processing_offline(reviewed):
    from image_dataset_train.qa import read_qa
    from image_dataset_train.reporting import reconcile_counts

    config, groups_run, drafts = reviewed
    report, summary = create_qa(config, groups_run, captions_run=drafts)
    counts = summary["reconciliation"]
    assert counts["status"] == "reconciled"
    assert (counts["intake"]["files"], counts["intake"]["images"]) == (7, 5)
    assert counts["review"]["decisions"] == {"include": 4, "exclude": 1}
    assert counts["snapshot"]["without_tagged_evidence"] == 4
    entries = read_qa(report)[1]["entries"]
    groups = [json.loads(line) for line in (groups_run / "groups.jsonl").read_text().splitlines()]
    members = [m for g in groups for m in g["members"]]
    group_meta = json.loads((groups_run / "run.json").read_text())
    group_summary = json.loads((groups_run / "summary.json").read_text())
    changed = [{**entries[0], "sha256": "0" * 64}, *entries[1:]]
    result = reconcile_counts(
        groups, members, changed, {}, group_meta, group_summary, None, exported=False
    )
    assert result["status"] == "mismatch"
    assert next(c for c in result["checks"] if c["name"] == "Snapshot → QA images")["matches"]
    assert not next(c for c in result["checks"] if c["name"] == "Snapshot → QA identities")[
        "matches"
    ]
    legacy = {key: value for key, value in group_meta.items() if key != "intake"}
    assert (
        reconcile_counts(groups, members, entries, {}, legacy, group_summary, None, exported=False)[
            "status"
        ]
        == "partial"
    )
    output, _ = export_dataset(config, groups_run, captions_run=drafts)
    export_meta = json.loads((output / "run.json").read_text())
    expected_bytes = sum(
        p.stat().st_size
        for p in output.rglob("*")
        if p.is_file()
        and p.relative_to(output).as_posix() not in {"run.json", "summary.json", "report.html"}
    )
    assert export_meta["metrics"]["payload_bytes"] == expected_bytes
    config.source.rename(config.source.with_name("offline-source"))
    config.runs.rename(config.runs.with_name("offline-runs"))
    _, frozen = create_qa(config, output)
    assert frozen["reconciliation"]["status"] == "reconciled"
    assert frozen["reconciliation"]["snapshot"]["exported_pairs"] == 4
    assert frozen["reconciliation"]["intake"] == counts["intake"]
    processing = frozen["processing"]
    assert not processing["missing_stages"] and not processing["unmeasured_runs"]
    assert len(processing["partial_scope_runs"]) == 1  # Fixture publishes existing scores.
    stages = processing["stages"]
    assert sorted(r["stage"] for r in stages) == [
        "export",
        "groups",
        "inventory",
        "qa",
        "recaption",
        "similarity",
    ]
    assert len({r["run_id"] for r in stages}) == len(stages)
    assert processing["recorded_processing_seconds"] >= 0
    assert processing["recorded_payload_bytes"] > expected_bytes
    before = {r["run_id"]: r for r in summary["processing"]["stages"] if r["stage"] != "qa"}
    assert all(r == before[r["run_id"]] for r in stages if r["run_id"] in before)


def test_graphical_corrections_share_cli_state_and_export_path(reviewed):
    config, groups, drafts = reviewed
    qa, _ = create_qa(config, groups, captions_run=drafts, sample_size=1)
    entry = next(e for e in list_qa(qa)["entries"] if e["source_path"] == "b.png")
    before = {
        p: p.read_bytes() for root in (config.source, qa) for p in root.rglob("*") if p.is_file()
    }
    with make_server(config, qa) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def request(path, payload=None, origin=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            connection.request(
                "GET" if payload is None else "POST",
                urlsplit(server.url).path + path,
                body=json.dumps(payload) if payload is not None else None,
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin or "http://" + server.authority,
                },
            )
            response = connection.getresponse()
            status, raw = response.status, response.read()
            connection.close()
            return status, raw

        try:
            assert b"Save corrections" in request("")[1]
            code, raw = request("api/similarity-evaluation", {})
            assert code == 200 and json.loads(raw)["both_classes_reviewed"]
            assert request(entry["preview"])[0] == 200
            assert request("image/" + entry["id"])[1] == (config.source / "b.png").read_bytes()
            route = "api/review/" + entry["id"]
            current = json.loads(request(route)[1])
            change = {
                "expected_revision": current["revision"],
                "caption": "graphical correction",
                "clear_labels": True,
                "add_labels": ["new label"],
                "subset": "new subset",
                "decision": "include",
                "reason": "inspected in UI",
            }
            assert request(route, change, "https://unrelated.example")[0] == 403
            code, raw = request(route, change)
            assert code == 200
            saved = json.loads(raw)
            assert saved["labels"] == ["new label"] and saved["subset"] == "new subset"
            similarity = Path(entry["review_args"][entry["review_args"].index("--run") + 1])
            cli = review_image(config, similarity, "b.png")
            assert cli["caption_override"] == "graphical correction"
            review_image(config, similarity, "b.png", add_labels=["cli edit"], reason="terminal")
            assert request(route, {**change, "expected_revision": saved["revision"]})[0] == 409
            refreshed = json.loads(request(route)[1])
            assert "cli edit" in refreshed["labels"]
            new_groups, _ = publish_groups(config, similarity)
            exported, _ = export_dataset(config, new_groups, captions_run=drafts)
            row = next(
                json.loads(line)
                for line in (exported / "manifest.jsonl").read_text().splitlines()
                if json.loads(line)["source_path"] == "b.png"
            )
            assert row["caption"] == "graphical correction" and row["subset"] == "new subset"
            assert all(p.read_bytes() == raw for p, raw in before.items())
            (config.source / "b.png").write_bytes(b"changed")
            assert request(route, {**change, "expected_revision": refreshed["revision"]})[0] == 400
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_pilot_assessment_persists_errors_conclusion_and_cli_summary(reviewed, capsys):
    config, groups, drafts = reviewed
    settings = config.source.parent / "qa-config.toml"
    settings.write_text('schema_version = 1\n[paths]\nreviews = "reviews"\n')
    qa, _ = create_qa(config, groups, captions_run=drafts, sample_size=1, config_path=settings)
    store = PilotAssessment(config.reviews, qa)
    entry = list_qa(qa, pilot=True)["entries"][0]
    judgment = {
        "image_id": entry["id"],
        "expected_revision": 0,
        "reviewer": "Fixture reviewer",
        "reviewer_kind": "human",
        "notes": "Verified fixture caption",
        "verdict": "accepted",
        "caption_check": "correct",
        "label_checks": {name: "correct" for name in entry["labels"]},
    }
    conclude = {
        "expected_revision": 0,
        "reviewer": "Fixture reviewer",
        "reviewer_kind": "human",
        "notes": "Synthetic pilot complete",
        "verdict": "accepted",
    }
    with pytest.raises(ValueError, match="every pilot image"):
        store.save(conclude)
    assert not store.save(judgment)["summary"]["human_accepted"]
    assert store.save({**conclude, "expected_revision": 1})["summary"]["human_accepted"]
    correction = {
        **judgment,
        "expected_revision": 2,
        "verdict": "needs_changes",
        "caption_check": "incorrect",
        "label_checks": {"missed detail": "missing"},
    }
    result = store.save(correction)
    assert result["summary"]["conclusion"] is None
    assert result["summary"]["critical_labels"]["missed detail"]["errors"] == 1
    with pytest.raises(ValueError, match="changed"):
        store.save(correction)
    config.source.rename(config.source.with_name("offline"))
    reopened = PilotAssessment(config.reviews, qa)
    assert reopened.read()["history"] == result["state"]["history"]
    assert main(["assessment", "--run", str(qa), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["assessed_images"] == 1


def test_pilot_label_metrics_count_explicit_absence_and_exclude_unchecked(reviewed):
    config, groups, drafts = reviewed
    qa, _ = create_qa(config, groups, captions_run=drafts, sample_size=100)
    store = PilotAssessment(config.reviews, qa)
    entries = list_qa(qa, pilot=True)["entries"]
    assert len(entries) == 4
    for entry, check in zip(entries, ("correct", "spurious", "missing", "absent"), strict=True):
        store.save(
            {
                "image_id": entry["id"],
                "expected_revision": store.read()["revision"],
                "reviewer": "Synthetic fixture reviewer",
                "reviewer_kind": "assistant",
                "notes": "Explicit label evidence for metric regression",
                "verdict": "needs_changes",
                "caption_check": "not_checked",
                "label_checks": {"critical label": check, "unchecked label": "not_checked"},
            }
        )
    metrics = store.summary()["critical_labels"]
    checked = metrics["critical label"]
    assert (checked["tp"], checked["fp"], checked["fn"], checked["tn"]) == (1, 1, 1, 1)
    assert (checked["checked"], checked["errors"]) == (4, 2)
    assert checked["precision"] == checked["recall"] == checked["specificity"] == 0.5
    unchecked = metrics["unchecked label"]
    assert unchecked["checked"] == unchecked["errors"] == 0
    assert unchecked["precision"] is unchecked["recall"] is unchecked["specificity"] is None
    assert not store.summary()["human_accepted"]


def test_pair_review_and_snapshot_export_publication(reviewed):
    config, groups, drafts = reviewed
    qa, _ = create_qa(config, groups, captions_run=drafts)
    session = ReviewSession(config, qa)
    original = {
        p: p.read_bytes() for root in (config.source, qa) for p in root.rglob("*") if p.is_file()
    }
    compared = session.compare("a.png", "b.png")
    pair = compared["pair"]
    assert session.pair_image(pair["left_image"].split("/")[-1])[1] == "image/jpeg"
    change = {
        "left": "a.png",
        "right": "b.png",
        "decision": "unreviewed",
        "reason": "Recheck relationship",
        "expected_revision": compared["revision"],
    }
    reset = session.save_pair(change)
    with pytest.raises(ValueError, match="changed"):
        session.save_pair(change)
    assert session.pairs()["pair_total"] == 1
    session.publication.start({"mode": "groups", "expected_revision": reset["revision"]})
    session.publication.wait()
    snapshot = session.publication.read()
    assert snapshot["status"] == "completed"
    assert not snapshot["outputs"]["groups"]["summary"]["review_complete"]
    session.publication.start({"mode": "export", "expected_revision": reset["revision"]})
    session.publication.wait()
    failed = session.publication.read()
    assert failed["status"] == "failed" and set(failed["outputs"]) == {"groups"}
    saved = session.save_pair(
        {**change, "decision": "related", "expected_revision": reset["revision"]}
    )
    alias = session.compare("a.png", "alias.png")
    with pytest.raises(ValueError, match="conflicts"):
        session.save_pair(
            {
                "left": "a.png",
                "right": "alias.png",
                "decision": "distinct",
                "reason": "Invalid alias split",
                "expected_revision": alias["revision"],
            }
        )
    session.publication.start(
        {
            "mode": "export",
            "expected_revision": saved["revision"],
            "export": {"validation_ratio": 0.5, "repeats": 2},
        }
    )
    session.publication.wait()
    result = session.publication.read()
    assert result["status"] == "completed", result
    output = Path(result["outputs"]["export"]["path"])
    assert verify_export(output)["verified"]
    report_id = result["outputs"]["qa"]["report_id"]
    child_config, child_qa = session.reports[report_id]
    child = ReviewSession(child_config, child_qa)
    assert child.page()["publication"]["captions_run"] == str(drafts)
    assert child.data["summary"]["split_state"] == "published"
    rows = [json.loads(line) for line in (output / "manifest.jsonl").read_text().splitlines()]
    assert (
        len({r["split"] for r in rows if r["source_path"] in {"a.png", "b.png", "alias.png"}}) == 1
    )
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_missing_caption_and_orphan_files_are_reported(reviewed):
    config, groups, drafts = reviewed
    with pytest.raises(ValueError, match="Missing or empty caption"):
        export_dataset(config, groups)
    output, _ = export_dataset(config, groups, captions_run=drafts)
    (output / "train" / "orphan.txt").write_text("orphan")
    with pytest.raises(ValueError, match="untracked files"):
        verify_export(output)


def test_split_extremes_and_cli_export(reviewed, tmp_path, capsys):
    assert assign_splits({"only": 10}, ExportConfig()) == {"only": "train"}
    assert set(assign_splits({"a": 10, "b": 1}, ExportConfig(validation_ratio=0)).values()) == {
        "train"
    }
    assert assign_splits({"a": 10, "b": 1}, ExportConfig()) == assign_splits(
        {"b": 1, "a": 10}, ExportConfig()
    )
    config, groups, drafts = reviewed
    settings = tmp_path / "config.toml"
    settings.write_text(f'schema_version=1\n[paths]\nexports="{config.exports.as_posix()}"\n')
    assert (
        main(
            [
                "export",
                "--groups",
                str(groups),
                "--captions",
                str(drafts),
                "--config",
                str(settings),
                "--validation-ratio",
                "0.25",
            ]
        )
        == 0
    )
    output = next(config.exports.iterdir())
    assert "Verified training pairs:" in capsys.readouterr().out
    assert main(["verify-export", "--run", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"]
    # The export remains based on its captured review revision, not mutable current state.
    with pytest.raises(ValueError, match="separate trees"):
        export_dataset(
            replace(config, exports=config.source / "exports"), groups, captions_run=drafts
        )


@pytest.mark.parametrize(
    "image_format,mode,orientation",
    [
        ("TIFF", "RGB", 1),
        ("PNG", "RGBA", 1),
        ("JPEG", "RGB", 6),
    ],
)
def test_training_derivatives_preserve_geometry_and_resolve_loader_mismatches(
    image_format, mode, orientation
):
    image = Image.new(mode, (128, 192), (255, 0, 0, 0) if mode == "RGBA" else "red")
    exif = Image.Exif()
    exif[274] = orientation
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, exif=exif)
    source = buffer.getvalue()
    output, suffix, width, height, _, policy = _prepare_export_image(
        source, f"source.{image_format.lower()}", 100000, 1024
    )
    assert policy == "png-exif-white-v1" and suffix == ".png"
    assert (width, height) == ((192, 128) if orientation == 6 else (128, 192))
    with Image.open(io.BytesIO(output)) as decoded:
        assert decoded.format == "PNG" and decoded.mode == "RGB"
        assert decoded.getexif().get(274, 1) == 1
        if mode == "RGBA":
            assert decoded.getpixel((0, 0)) == (255, 255, 255)
    assert buffer.getvalue() == source


def test_m4_rules_recaption_review_acceptance_and_export_provenance(reviewed, capsys):
    config, groups, drafts = reviewed
    before = {p: p.read_bytes() for p in config.source.iterdir()}
    similarity = Path(json.loads((groups / "run.json").read_text())["similarity_run"])
    settings = config.source.parent / "rule-config.toml"
    settings.write_text('schema_version=1\n[paths]\nreviews="reviews"\nruns="runs"\n')
    configured = replace(
        config,
        captions=CaptionConfig(
            trigger="custom style",
            force_tags=["ink"],
            subset_rules=[{"name": "blue", "all_tags": ["blue_hair"]}],
        ),
    )
    regenerated, summary = recaption(configured, drafts)
    assert summary["inferred_images"] == 0 and summary["subset_proposals"] == {"blue": 1}
    qa, _ = create_qa(configured, groups, captions_run=regenerated, config_path=settings)
    entry = next(row for row in list_qa(qa)["entries"] if row["source_path"] == "c.png")
    assert entry["caption"] == "custom style, blue hair, ink" and entry["subset"] == "scenery"
    assert "subset_proposal_differs_from_review" in entry["findings"]
    session = ReviewSession(configured, qa)
    current = session.review(entry["id"])
    accepted = session.review(
        entry["id"],
        {
            "accept_subset_proposal": True,
            "expected_revision": current["revision"],
            "reason": "Reviewed proposal against image",
        },
    )
    assert accepted["subset"] == "blue" and accepted["subset_reviewed"]
    assert accepted["subset_origin"]["rules_sha256"] == entry["caption_analysis"]["rules_sha256"]
    assert (
        main(
            [
                "review",
                "--run",
                str(similarity),
                "--config",
                str(settings),
                "--image",
                "c.png",
                "--subset-from",
                str(regenerated),
                "--reason",
                "CLI acceptance",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["subset_origin"] == accepted["subset_origin"]
    review_image(config, similarity, "c.png", caption="manual correction", reason="Corrected")
    later, _ = recaption(
        replace(
            configured,
            captions=CaptionConfig(
                trigger="changed", subset_rules=[{"name": "another", "all_tags": ["blue_hair"]}]
            ),
        ),
        regenerated,
    )
    frozen, _ = publish_groups(config, similarity)
    export, _ = export_dataset(config, frozen, captions_run=later)
    rows = [json.loads(line) for line in (export / "manifest.jsonl").read_text().splitlines()]
    row = next(row for row in rows if row["source_path"] == "c.png")
    assert row["caption"] == "manual correction" and row["subset"] == "blue"
    assert row["subset_origin"] == accepted["subset_origin"]
    assert row["caption_analysis"]["subset_proposal"]["value"] == "another"
    assert all(p.read_bytes() == raw for p, raw in before.items())
    config.source.rename(config.source.with_name("offline"))
    assert verify_export(export)["verified"]
    exported_qa, _ = create_qa(config, export)
    saved = next(item for item in list_qa(exported_qa)["entries"] if item["source_path"] == "c.png")
    assert saved["subset_origin"] == row["subset_origin"]
    assert saved["caption_analysis"] == row["caption_analysis"]


def test_zero_sized_trainer_buckets_are_rejected():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 48)).save(buffer, format="PNG")
    with pytest.raises(ValueError, match="too small or narrow"):
        _prepare_export_image(buffer.getvalue(), "tiny.png", 100000, 1024)


def _receipt(config, export, number, **changes):
    directory = config.runs / f"20261109-trainer-{number}"
    directory.mkdir()
    result = {
        **trainer_pin(),
        "qualified": True,
        "training_step_executed": False,
        "export": str(export),
        "export_run_sha256": file_sha256(export / "run.json"),
        "export_manifest_sha256": file_sha256(export / "manifest.jsonl"),
        **changes,
    }
    atomic_json(directory / "result.json", result)
    (directory / "loader.log").write_text("Synthetic loader evidence\n", newline="\n")
    atomic_json(
        directory / "run.json",
        {
            "schema_version": 1,
            "stage": "trainer-check",
            "run_id": directory.name,
            "status": "completed" if result["qualified"] else "failed",
            "completed_at": f"2026-11-09T10:00:{number:02d}+00:00",
            "files": {
                name: file_sha256(directory / name) for name in ("result.json", "loader.log")
            },
        },
    )
    return directory


def test_trainer_receipts_follow_export_identity_and_latest_result(reviewed, capsys):
    config, groups, drafts = reviewed
    export, _ = export_dataset(config, groups, captions_run=drafts)
    assert trainer_status(export, config.runs)["status"] == "not_checked"
    passed = _receipt(config, export, 1)
    failed = _receipt(config, export, 2, qualified=False, error="Decode failure")
    _receipt(config, export, 3, revision="other-trainer")
    _receipt(config, export, 4, export_run_sha256="0" * 64)
    result = trainer_status(export, config.runs)
    assert result["status"] == "failed" and result["latest_receipt"] == failed.name
    assert [item["status"] for item in result["receipts"]] == [
        "stale",
        "other_pin",
        "failed",
        "passed",
    ]
    # A new export from the same groups does not inherit receipts from its predecessor.
    newer, _ = export_dataset(config, groups, captions_run=drafts)
    assert trainer_status(newer, config.runs)["status"] == "not_checked"
    export.rename(relocated := export.with_name("relocated"))
    config.source.rename(config.source.with_name("offline"))
    assert trainer_status(relocated, config.runs)["status"] == "failed"
    settings = config.source.parent / "receipts.toml"
    settings.write_text('schema_version=1\n[paths]\nruns="runs"\n')
    assert (
        main(["trainer-status", "--run", str(relocated), "--config", str(settings), "--json"]) == 1
    )
    assert json.loads(capsys.readouterr().out)["latest_receipt"] == failed.name
    (failed / "loader.log").write_text("changed evidence")
    assert trainer_status(relocated, config.runs)["status"] == "invalid"
    (passed / "result.json").write_text("not json")
    assert trainer_status(relocated, config.runs)["status"] == "history_incomplete"
    (relocated / "train.toml").write_text("changed export")
    assert trainer_status(relocated, config.runs)["status"] == "export_invalid"


def test_graphical_trainer_status_and_hash_checked_artifact_routes(reviewed):
    config, groups, drafts = reviewed
    export, _ = export_dataset(config, groups, captions_run=drafts)
    qa, _ = create_qa(config, export)
    group_qa, _ = create_qa(config, groups, captions_run=drafts)
    assert ReviewSession(config, group_qa).training()["status"] == "not_export"
    before = {p: p.read_bytes() for root in (export, qa) for p in root.rglob("*") if p.is_file()}
    with make_server(config, qa) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        prefix = urlsplit(server.url).path

        def get(path):
            connection = HTTPConnection(server.authority)
            connection.request("GET", prefix + path)
            response = connection.getresponse()
            result = response.status, response.read()
            connection.close()
            return result

        try:
            assert json.loads(get("api/training")[1])["status"] == "not_checked"
            receipt = _receipt(config, export, 1)
            state = json.loads(get("api/training")[1])
            assert state["status"] == "passed" and not state["pilot_assessment"]["human_accepted"]
            assert "trainer-check" in state["commands"]["powershell"]
            route = state["receipts"][0]["artifacts"]["loader.log"]
            assert get(route) == (200, b"Synthetic loader evidence\n")
            (receipt / "loader.log").write_text("changed")
            assert get(route)[0] == 400
            assert get("trainer-receipt/unknown/result.json")[0] == 400
            assert all(p.read_bytes() == raw for p, raw in before.items())
        finally:
            server.shutdown()
            worker.join(timeout=5)
