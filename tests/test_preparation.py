import json
from dataclasses import replace
from pathlib import Path

import pytest
from filelock import FileLock
from PIL import Image, ImageDraw
from test_tagging import make_bundle

from image_dataset_train import preparation
from image_dataset_train.cli import main
from image_dataset_train.config import load_config
from image_dataset_train.dataset_catalog import query_catalog
from image_dataset_train.exporting import _load_groups, export_dataset, verify_export
from image_dataset_train.model_bundle import Label, bundle_path
from image_dataset_train.preparation import (
    job_status,
    preparation_config,
    prepare_directory,
    preview_preparation,
    resume_preparation,
)
from image_dataset_train.reviews import ReviewStore, review_image, review_pair, review_status
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


@pytest.fixture
def collection(tmp_path):
    source = tmp_path / "images with spaces"
    source.mkdir()
    for i, name in enumerate(("a", "b", "c")):
        image = Image.new("RGB", (192, 256), (200, 100 + i * 25, 50))
        ImageDraw.Draw(image).rectangle((i * 35, 10, i * 35 + 40, 90), fill="black")
        image.save(source / f"{name}.png")
        (source / f"{name}.txt").write_text(f"caption {name}", encoding="utf-8")
    workspace = tmp_path / "prepared dataset"
    config = preparation_config(source, workspace)
    return config, workspace


def run(config, workspace, **kwargs):
    return prepare_directory(
        config, workspace, captions="existing", progress=lambda _: None, **kwargs
    )


def rows(result):
    return query_catalog(Path(result["outputs"]["export"]["path"]))


def test_directory_pipeline_catalog_and_unchanged_resume(collection):
    config, workspace = collection
    original = {p.name: p.read_bytes() for p in config.source.iterdir()}
    result = run(config, workspace)
    assert result["status"] == "completed" and result["human_accepted"] is False
    assert result["outputs"]["export"]["summary"]["images"] == 3
    exported = Path(result["outputs"]["export"]["path"])
    assert verify_export(exported)["images"] == 3
    assert len(rows(result)) == 3
    assert all(r["decision_origin"]["kind"] == "policy" for r in rows(result))
    assert not ReviewStore(config.reviews, config.source).path.exists()
    assert load_config(Path(result["config"])) == config
    again = run(config, workspace)
    assert again["outputs"] == result["outputs"]
    assert job_status(workspace, verify=True)["prepared"]
    assert {p.name: p.read_bytes() for p in config.source.iterdir()} == original


def test_exact_alias_policy_preserves_conflicting_captions(collection):
    config, workspace = collection
    for name, caption in (("alias", "caption a"), ("variant", "different caption")):
        (config.source / f"{name}.png").write_bytes((config.source / "a.png").read_bytes())
        (config.source / f"{name}.txt").write_text(caption, encoding="utf-8")
    result = run(config, workspace)
    by_name = {r["source_path"]: r for r in rows(result)}
    assert set(by_name) == {"a.png", "b.png", "c.png", "variant.png"}
    summary = result["outputs"]["policy"]["summary"]
    assert summary["policy_exclusions"] == {"exact_bytes_and_caption_already_represented": 1}
    assert (config.source / "alias.png").exists()


def test_crash_after_export_before_checkpoint_recovers_published_output(collection, monkeypatch):
    config, workspace = collection
    checkpoint = preparation._checkpoint
    failed = False

    def crash(job, state, stage, path, *, recovered):
        nonlocal failed
        if stage == "export" and not failed:
            failed = True
            raise OSError("simulated crash after export publication")
        return checkpoint(job, state, stage, path, recovered=recovered)

    monkeypatch.setattr(preparation, "_checkpoint", crash)
    with pytest.raises(OSError, match="simulated crash"):
        run(config, workspace)
    assert job_status(workspace)["status"] == "failed"
    outputs = list(workspace.glob("jobs/*/attempts/export-*/exports/*/run.json"))
    assert len(outputs) == 1
    result = resume_preparation(workspace, progress=lambda _: None)
    assert Path(result["outputs"]["export"]["path"]) == outputs[0].parent
    assert len(list(workspace.glob("jobs/*/attempts/export-*"))) == 1
    state = json.loads((Path(result["job"]) / "job.json").read_text(encoding="utf-8"))
    assert any(e["event"] == "stage_recovered" and e["stage"] == "export" for e in state["history"])


def test_failure_before_publication_retries_only_failed_stage(collection, monkeypatch):
    config, workspace = collection
    execute = preparation._execute

    def fail(stage, *args):
        if stage == "export":
            raise OSError("temporary output failure")
        return execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", fail)
    with pytest.raises(OSError, match="temporary"):
        run(config, workspace)
    before = job_status(workspace)["outputs"]
    monkeypatch.setattr(preparation, "_execute", execute)
    result = resume_preparation(workspace, progress=lambda _: None)
    for stage, record in before.items():
        assert result["outputs"][stage] == record
    assert len(list(workspace.glob("jobs/*/attempts/export-*"))) == 2


def test_interrupted_job_rejects_changed_implementation_without_losing_history(
    collection, monkeypatch
):
    config, workspace = collection
    execute = preparation._execute

    def fail(stage, *args):
        if stage == "export":
            raise OSError("temporary output failure")
        return execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", fail)
    with pytest.raises(OSError, match="temporary"):
        run(config, workspace)
    state_path = Path(job_status(workspace)["job"]) / "job.json"
    saved = state_path.read_bytes()
    identity = preparation._implementation_identity()
    monkeypatch.setattr(preparation, "_execute", execute)
    monkeypatch.setattr(
        preparation, "_implementation_identity", lambda: {**identity, "version": "future-build"}
    )
    with pytest.raises(ValueError, match="implementation changed"):
        resume_preparation(workspace, progress=lambda _: None)
    assert state_path.read_bytes() == saved
    result = run(config, workspace, new=True)
    assert result["prepared"] and Path(result["job"]) != state_path.parent
    assert state_path.read_bytes() == saved


def test_completed_job_can_verify_after_upgrade_but_review_refresh_needs_new_job(
    collection, monkeypatch
):
    config, workspace = collection
    original = run(config, workspace)
    identity = preparation._implementation_identity()
    monkeypatch.setattr(
        preparation, "_implementation_identity", lambda: {**identity, "version": "future-build"}
    )
    assert job_status(workspace, verify=True)["prepared"]
    assert resume_preparation(workspace, progress=lambda _: None)["outputs"] == original["outputs"]
    with pytest.raises(ValueError, match="implementation changed"):
        resume_preparation(workspace, refresh_reviews=True, progress=lambda _: None)


@pytest.mark.parametrize("corruption", ["collection", "job", "stage", "implementation"])
def test_malformed_job_records_are_actionable_and_preserved(collection, corruption):
    config, workspace = collection
    result = run(config, workspace)
    path = (
        workspace / "collection.json"
        if corruption == "collection"
        else Path(result["job"]) / "job.json"
    )
    value = (
        [] if corruption in {"collection", "job"} else json.loads(path.read_text(encoding="utf-8"))
    )
    if corruption == "stage":
        value["stages"]["export"] = []
    if corruption == "implementation":
        value["implementation"]["payload_sha256"] = "0" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid.*preparation"):
        job_status(workspace, verify=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["bytes", "new_file", "sidecar"])
def test_resume_rejects_source_drift_before_new_outputs(collection, change):
    config, workspace = collection
    result = run(config, workspace)
    output_before = result["outputs"]
    if change == "bytes":
        Image.new("RGB", (192, 256), "red").save(config.source / "a.png")
    elif change == "new_file":
        (config.source / "new.txt").write_text("new", encoding="utf-8")
    else:
        (config.source / "a.txt").write_text("new caption", encoding="utf-8")
    with pytest.raises(ValueError, match="Source.*changed"):
        resume_preparation(workspace, progress=lambda _: None)
    assert job_status(workspace)["outputs"] == output_before
    assert job_status(workspace)["status"] == "failed"


def test_changed_completed_artifact_is_not_silently_rebuilt(collection):
    config, workspace = collection
    result = run(config, workspace)
    path = Path(result["outputs"]["export"]["path"]) / "train" / "metadata.jsonl"
    path.write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError, match="artifacts changed"):
        resume_preparation(workspace, progress=lambda _: None)
    assert len(list(workspace.glob("jobs/*/attempts/export-*"))) == 1


def test_dry_run_does_not_create_workspace_or_infer(collection, monkeypatch):
    config, workspace = collection
    import image_dataset_train.model_bundle as models

    monkeypatch.setattr(models, "fetch_bundle", lambda *args: pytest.fail("network on preview"))
    result = preview_preparation(config)
    assert result["dry_run"] and not workspace.exists()
    assert result["intake"]["images_seen"] == 3
    assert (
        main(["prepare", str(config.source), "--workspace", str(workspace), "--dryrun", "--json"])
        == 0
    )
    assert not workspace.exists()


def test_saved_decisions_override_policy_and_refresh_is_explicit(collection):
    config, workspace = collection
    staging = replace(config, runs=workspace.parent / "review runs")
    inventory, _ = run_scan(staging)
    similarity, _ = propose_similar(staging, inventory)
    review_image(config, similarity, "a.png", decision="exclude", reason="user choice")
    review_image(
        config, similarity, "b.png", caption="saved correction", reason="assistant correction"
    )
    result = run(config, workspace)
    by_name = {r["source_path"]: r for r in rows(result)}
    assert "a.png" not in by_name and by_name["b.png"]["caption"] == "saved correction"
    review_image(config, similarity, "c.png", decision="exclude", reason="new choice")
    with pytest.raises(ValueError, match="refresh-reviews"):
        resume_preparation(workspace, progress=lambda _: None)
    refreshed = resume_preparation(workspace, refresh_reviews=True, progress=lambda _: None)
    assert {r["source_path"] for r in rows(refreshed)} == {"b.png"}
    assert refreshed["outputs"]["inventory"] == result["outputs"]["inventory"]
    assert refreshed["outputs"]["export"]["path"] != result["outputs"]["export"]["path"]
    assert verify_export(Path(result["outputs"]["export"]["path"]))["images"] == 2


def test_narrow_images_are_accounted_for_without_upscaling(collection):
    config, workspace = collection
    Image.new("RGB", (6, 66), "gray").save(config.source / "strip.png")
    (config.source / "strip.txt").write_text("gray strip", encoding="utf-8")
    result = run(config, workspace)
    assert result["outputs"]["policy"]["summary"]["policy_exclusions"] == {
        "below_trainer_bucket_minimum": 1
    }
    assert len(rows(result)) == 3 and (config.source / "strip.png").exists()


def test_explicit_unusable_inclusion_requires_actionable_review(collection):
    config, workspace = collection
    Image.new("RGB", (6, 66), "gray").save(config.source / "strip.png")
    (config.source / "strip.txt").write_text("gray strip", encoding="utf-8")
    staging = replace(config, runs=workspace.parent / "review runs")
    inventory, _ = run_scan(staging)
    similarity, _ = propose_similar(staging, inventory)
    review_image(config, similarity, "strip.png", decision="include", reason="explicit include")
    result = run(config, workspace)
    assert result["status"] == "needs_review" and "review_qa" in result["outputs"]
    assert "export" not in result["outputs"]
    review_image(
        config, similarity, "strip.png", decision="exclude", reason="corrected eligibility"
    )
    done = resume_preparation(workspace, refresh_reviews=True, progress=lambda _: None)
    assert done["status"] == "completed"


def test_policy_does_not_weaken_strict_reviewed_export(collection):
    config, workspace = collection
    result = run(config, workspace)
    prepared = Path(result["outputs"]["policy"]["path"])
    assert _load_groups(prepared, require_reviewed=False)[0]["preparation_policy"]
    with pytest.raises(ValueError, match="automated preparation"):
        export_dataset(config, prepared)


def test_concurrent_work_and_setting_drift_are_actionable(collection):
    config, workspace = collection
    run(config, workspace)
    with FileLock(str(workspace / "prepare.lock")):
        with pytest.raises(ValueError, match="Another preparation"):
            resume_preparation(workspace)
    with pytest.raises(ValueError, match="settings changed"):
        run(replace(config, export=replace(config.export, resolution=512)), workspace)
    with pytest.raises(ValueError, match="separate directory"):
        preparation_config(config.source, config.source / "nested")


def test_conflicting_distinct_constraint_stays_reviewable(collection):
    config, workspace = collection
    staging = replace(config, runs=workspace.parent / "review runs")
    inventory, _ = run_scan(staging)
    similarity, _ = propose_similar(staging, inventory, max_distance=64)
    pairs = review_status(config, similarity, limit=100)["pairs"]
    selected = next(
        p for p in pairs if {p["left_source_path"], p["right_source_path"]} == {"a.png", "c.png"}
    )
    review_pair(config, similarity, selected["pair_id"], "distinct", "confirmed distinct")
    result = run(config, workspace, max_distance=64)
    assert result["status"] == "needs_review"
    assert any(
        b["code"] == "review_constraint_conflict"
        for b in result["outputs"]["policy"]["summary"]["blockers"]
    )


def test_cli_works_without_repository_config(collection, monkeypatch, capsys):
    config, workspace = collection
    monkeypatch.chdir(config.source.parent)
    assert (
        main(
            [
                "prepare",
                str(config.source),
                "--workspace",
                str(workspace),
                "--captions",
                "existing",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert main(["status", str(workspace), "--verify", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_verification"] == "full"


def test_default_model_pipeline_and_offline_resume_use_saved_pinned_artifacts(
    collection, monkeypatch
):
    config, workspace = collection
    for path in config.source.glob("*.txt"):
        path.unlink()
    import image_dataset_train.model_bundle as models

    monkeypatch.setattr(models, "fetch_bundle", lambda *args: pytest.fail("offline model fetch"))
    with pytest.raises(ValueError, match="unavailable offline"):
        prepare_directory(config, workspace, offline=True, progress=lambda _: None)
    failed = job_status(workspace)
    assert failed["status"] == "failed" and failed["current_stage"] == "tagging"
    make_bundle(
        bundle_path(config.models, config.tagging.model, config.tagging.revision),
        [Label(0, "dark", 0), Label(1, "image", 0)],
    )
    done = resume_preparation(workspace, progress=lambda _: None)
    assert done["status"] == "completed"
    assert done["outputs"]["tagging"]["summary"]["inferred_images"] == 3
    assert all(row["caption_origin"]["kind"] == "draft" for row in rows(done))
    new = prepare_directory(config, workspace, offline=True, new=True, progress=lambda _: None)
    assert new["outputs"]["tagging"]["summary"]["cached_images"] == 3
    assert new["outputs"]["tagging"]["summary"]["inferred_images"] == 0
    assert not list(config.source.glob("*.txt"))


def test_cancelled_job_retains_completed_stages_for_resume(collection, monkeypatch):
    config, workspace = collection
    execute = preparation._execute

    def cancel(stage, *args):
        if stage == "policy":
            raise KeyboardInterrupt
        return execute(stage, *args)

    monkeypatch.setattr(preparation, "_execute", cancel)
    with pytest.raises(KeyboardInterrupt):
        run(config, workspace)
    before = job_status(workspace)
    assert before["status"] == "cancelled" and "groups" in before["outputs"]
    monkeypatch.setattr(preparation, "_execute", execute)
    done = resume_preparation(workspace, progress=lambda _: None)
    assert done["status"] == "completed"
    assert done["outputs"]["groups"] == before["outputs"]["groups"]


def test_empty_usable_population_is_a_review_result_not_a_ready_export(collection):
    config, workspace = collection
    for path in config.source.glob("*.txt"):
        path.unlink()
    result = run(config, workspace)
    assert result["status"] == "needs_review" and result["prepared"] is False
    assert "export" not in result["outputs"]
    assert any(
        b["code"] == "no_usable_images" for b in result["outputs"]["policy"]["summary"]["blockers"]
    )


def test_modified_saved_configuration_is_rejected(collection):
    config, workspace = collection
    result = run(config, workspace)
    path = Path(result["config"])
    path.write_text(path.read_text(encoding="utf-8") + "\n# altered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="altered preparation job"):
        resume_preparation(workspace)


def test_derivative_caption_adjustment_preserves_saved_override_and_source(collection):
    config, workspace = collection
    image = Image.new("RGBA", (128, 192), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((30, 30, 80, 150), fill=(200, 0, 0, 255))
    image.save(config.source / "alpha.png")
    (config.source / "alpha.txt").write_text("original sidecar", encoding="utf-8")
    staging = replace(config, runs=workspace.parent / "review runs")
    inventory, _ = run_scan(staging)
    similarity, _ = propose_similar(staging, inventory)
    review_image(
        config,
        similarity,
        "alpha.png",
        caption="red rectangle, transparent background",
        reason="assistant fixture correction",
    )
    store = ReviewStore(config.reviews, config.source)
    original_review = store.path.read_bytes()
    original_source = {p.name: p.read_bytes() for p in config.source.iterdir()}
    result = run(config, workspace)
    row = next(r for r in rows(result) if r["source_path"] == "alpha.png")
    assert row["source_caption"] == "red rectangle, transparent background"
    assert row["caption"] == "red rectangle"
    assert row["caption_origin"]["kind"] == "override"
    assert row["caption_transforms"][0]["policy"] == "opaque-alpha-caption-v1"
    output = Path(result["outputs"]["export"]["path"])
    with Image.open(output / row["image_path"]) as published:
        assert published.mode == "RGB" and published.getpixel((0, 0)) == (255, 255, 255)
    assert verify_export(output)["images"] == 4
    assert store.path.read_bytes() == original_review
    assert {p.name: p.read_bytes() for p in config.source.iterdir()} == original_source


def test_caption_transform_is_literal_and_cannot_publish_empty_captions(collection):
    from image_dataset_train.exporting import _caption_for_derivative

    sentence = "A shape on a transparent background"
    assert _caption_for_derivative(sentence, "png-exif-white-v1") == (sentence, [])
    assert _caption_for_derivative("transparent background", "copy-v1") == (
        "transparent background",
        [],
    )
    config, workspace = collection
    Image.new("RGBA", (128, 192), (255, 0, 0, 0)).save(config.source / "alpha.png")
    (config.source / "alpha.txt").write_text("transparent background", encoding="utf-8")
    result = run(config, workspace)
    assert "alpha.png" not in {r["source_path"] for r in rows(result)}
    evidence = json.loads(
        (Path(result["outputs"]["policy"]["path"]) / "preparation.json").read_text(encoding="utf-8")
    )
    assert "empty after preparing" in evidence["captions"]["alpha.png"]["error"]
