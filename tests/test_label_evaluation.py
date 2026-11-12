"""Label evaluation uses frozen content, independent truth, and untouched held-out data."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from image_dataset_train.cli import main
from image_dataset_train.config import CaptionConfig, Config, ValidationConfig
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.label_workspace import LabelWorkspace, create_label_workspace
from image_dataset_train.model_bundle import Label
from image_dataset_train.qa import create_qa
from image_dataset_train.reviews import publish_groups, review_image, review_link
from image_dataset_train.runs import run_scan
from image_dataset_train.scored_runs import ScoredRun
from image_dataset_train.similarity import propose_similar
from image_dataset_train.tagging import _publish
from image_dataset_train.tagging_evaluation import evaluate_labels


@pytest.fixture
def evaluation_pilot(tmp_path):
    source = tmp_path / "originals"
    source.mkdir()
    for index in range(8):
        image = Image.new("RGB", (48, 64), (index * 23, 180, 240))
        ImageDraw.Draw(image).rectangle((index + 1, 3, index + 12, 20), fill="black")
        image.save(source / f"image-{index}.png")
    (source / "alias.png").write_bytes((source / "image-0.png").read_bytes())
    (source / "image-0.txt").write_text("manual source caption", encoding="utf-8")
    config = Config(
        source,
        tmp_path / "runs",
        ValidationConfig(min_short_side=8),
        models=tmp_path / "models",
        scores=tmp_path / "scores",
        reviews=tmp_path / "reviews",
        exports=tmp_path / "exports",
        captions=CaptionConfig(general_threshold=0.5),
    )
    inventory, _ = run_scan(config)
    similarity, _ = propose_similar(config, inventory, max_distance=0)
    review_link(
        config,
        similarity,
        ["image-0.png", "image-1.png"],
        "related",
        "Synthetic variants of one artwork",
    )
    groups, _ = publish_groups(config, similarity)
    group_meta = json.loads((groups / "run.json").read_text(encoding="utf-8"))
    members = [
        member
        for line in (groups / "groups.jsonl").read_text(encoding="utf-8").splitlines()
        for member in json.loads(line)["members"]
    ]
    rows = [
        {"source_path": row["source_path"], "sha256": row["sha256"], "decision": "tagged"}
        for row in members
    ]
    labels = [Label(0, "blue_hair", 0), Label(1, "red_eyes", 0), Label(2, "general", 9)]

    def scored_run(*, omit=None, scores=None, model="fixture-one", rules=None):
        selected = [row for row in rows if row["sha256"] != omit]
        vectors = {
            row["sha256"]: np.array(
                (scores or {}).get(row["sha256"], [0.5, 0.5, 0.5]), dtype=np.float32
            )
            for row in selected
        }
        return _publish(
            config.runs,
            selected,
            vectors,
            labels,
            {
                "stage": "tagging",
                "source": str(source),
                "inventory_manifest_sha256": group_meta["inventory_manifest_sha256"],
                "model": {"repo": model, "revision": "a" * 40, "artifact_id": model},
                "preprocessing": "fixture-wd-v1",
                "runtime": {"providers": ["CPUExecutionProvider"]},
            },
            {},
            rules or config.captions,
            0.5,
        )

    scored = scored_run()
    qa, _ = create_qa(config, groups, captions_run=scored, sample_size=100)
    workspace = create_label_workspace(
        config,
        qa,
        scored,
        ["blue_hair", "red_eyes"],
        selection_reason="All synthetic fixture images; not representative image-quality evidence",
        seed=7,
        held_out_fraction=0.33,
    )
    return config, qa, scored, workspace, scored_run


def save_truth(store, member, value, *, label="blue_hair", kind="human", image=None):
    return store.save(
        {
            "image": image or member["sha256"],
            "label": label,
            "value": value,
            "reviewer": "Synthetic fixture reviewer",
            "reviewer_kind": kind,
            "notes": "Known synthetic truth for behavior verification",
            "expected_revision": store.read()["revision"],
        }
    )


def test_explicit_membership_can_select_outside_qa_pilot(evaluation_pilot):
    config, original_qa, scored, _, _ = evaluation_pilot
    metadata = json.loads((original_qa / "run.json").read_text(encoding="utf-8"))
    small_qa, summary = create_qa(
        config, Path(metadata["input_run"]), captions_run=scored, sample_size=1
    )
    entries = [
        json.loads(line)
        for line in (small_qa / "entries.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outside = next(row["source_path"] for row in entries if row["id"] not in summary["pilot_ids"])
    path = create_label_workspace(
        config,
        small_qa,
        scored,
        ["blue_hair"],
        selection_reason="Explicit targeted case",
        source_paths=[outside],
    )
    store = LabelWorkspace(path)
    assert [a["source_path"] for m in store.members.values() for a in m["aliases"]] == [outside]
    assert store.selection["selection_method"].startswith("explicit source paths")
    assert store.summary()["unreviewed_labels"] == 1


@pytest.mark.parametrize(
    "paths", [[], ["missing.png"], ["image-0.png", "image-0.png"], "image-0.png"]
)
def test_explicit_membership_rejects_invalid_paths_without_output(evaluation_pilot, paths):
    config, qa, scored, _, _ = evaluation_pilot
    root = config.reviews / "label-evaluations"
    before = set(root.iterdir())
    with pytest.raises(ValueError):
        create_label_workspace(
            config,
            qa,
            scored,
            ["blue_hair"],
            selection_reason="Invalid fixture selection",
            source_paths=paths,
        )
    assert set(root.iterdir()) == before


def test_explicit_membership_retains_aliases_and_rejects_exclusions(evaluation_pilot):
    config, qa, scored, _, _ = evaluation_pilot
    selected = create_label_workspace(
        config,
        qa,
        scored,
        ["blue_hair"],
        selection_reason="Explicit exact aliases",
        source_paths=["image-0.png", "alias.png"],
    )
    summary = LabelWorkspace(selected).summary()
    assert summary["unique_images"] == 1 and summary["source_occurrences"] == 2
    metadata = json.loads((qa / "run.json").read_text(encoding="utf-8"))
    group_meta = json.loads((Path(metadata["input_run"]) / "run.json").read_text(encoding="utf-8"))
    similarity = Path(group_meta["similarity_run"])
    review_image(config, similarity, "image-0.png", decision="exclude", reason="Fixture exclusion")
    groups, _ = publish_groups(config, similarity)
    excluded_qa, _ = create_qa(config, groups, captions_run=scored)
    with pytest.raises(ValueError, match="excluded"):
        create_label_workspace(
            config,
            excluded_qa,
            scored,
            ["blue_hair"],
            selection_reason="Cannot retain exclusion",
            source_paths=["image-0.png"],
        )


def test_batch_label_save_is_atomic_and_keeps_individual_history(evaluation_pilot, monkeypatch):
    from image_dataset_train import label_workspace
    from image_dataset_train.reviews import ReviewConflict

    _, _, _, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    digest = next(iter(store.members))

    def payload(label, notes="Visible synthetic evidence"):
        return {
            "image": digest,
            "label": label,
            "value": "present",
            "reviewer": "Test",
            "reviewer_kind": "assistant",
            "notes": notes,
        }

    before = (path / "judgments.json").read_bytes()
    with pytest.raises(ValueError, match="notes"):
        store.save_many([payload("blue_hair"), payload("red_eyes", "")], expected_revision=0)
    assert (path / "judgments.json").read_bytes() == before
    with pytest.raises(ValueError, match="repeat"):
        store.save_many([payload("blue_hair"), payload("blue_hair")], expected_revision=0)
    result = store.save_many([payload("blue_hair"), payload("red_eyes")], expected_revision=0)
    assert result["state"]["revision"] == 2
    assert [e["label"] for e in result["state"]["history"]] == ["blue_hair", "red_eyes"]
    saved = (path / "judgments.json").read_bytes()
    with pytest.raises(ReviewConflict):
        store.save_many([payload("blue_hair")], expected_revision=0)

    def fail(*args):
        raise OSError("Injected publication failure")

    monkeypatch.setattr(label_workspace, "atomic_json", fail)
    with pytest.raises(OSError, match="publication failure"):
        store.save_many([payload("blue_hair", "Changed evidence")], expected_revision=2)
    assert (path / "judgments.json").read_bytes() == saved


def by_set(store):
    return {
        name: [m for m in store.selection["members"] if m["evaluation_set"] == name]
        for name in ("calibration", "held_out")
    }


def test_workspace_freezes_groups_aliases_and_same_population(evaluation_pilot):
    config, qa, scored, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    assert len(store.selection["members"]) == 8
    entries = {
        alias["source_path"]: member
        for member in store.selection["members"]
        for alias in member["aliases"]
    }
    assert entries["alias.png"] == entries["image-0.png"]
    assert entries["image-0.png"]["sha256"] != entries["image-1.png"]["sha256"]
    assert entries["image-0.png"]["group_id"] == entries["image-1.png"]["group_id"]
    split = by_set(store)
    assert split["calibration"] and split["held_out"]
    assert {m["group_id"] for m in split["calibration"]}.isdisjoint(
        m["group_id"] for m in split["held_out"]
    )
    repeated = create_label_workspace(
        config,
        qa,
        scored,
        ["blue_hair", "red_eyes"],
        selection_reason="Reproduce frozen fixture selection",
        seed=7,
        held_out_fraction=0.33,
    )
    assert LabelWorkspace(repeated).selection["members"] == store.selection["members"]
    assert not store.read()["judgments"]


def test_truth_revision_and_alias_updates_do_not_mutate_selection(evaluation_pilot):
    _, _, _, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    member = next(m for m in store.selection["members"] if len(m["aliases"]) == 2)
    frozen = store.selection_sha256
    result = save_truth(store, member, "present", image="alias.png")
    revision = result["state"]["revision"]
    assert result["state"]["judgments"][member["sha256"]]["blue_hair"]["value"] == "present"
    save_truth(store, member, "uncertain", image="image-0.png")
    assert len(store.read()["judgments"]) == 1
    before = store.read()
    with pytest.raises(ValueError, match="changed|revision|Reload"):
        store.save(
            {
                "image": "alias.png",
                "label": "blue_hair",
                "value": "absent",
                "reviewer": "Synthetic fixture reviewer",
                "reviewer_kind": "human",
                "notes": "Stale concurrent update",
                "expected_revision": revision,
            }
        )
    assert store.read() == before
    assert LabelWorkspace(path).selection_sha256 == frozen
    save_truth(store, member, "unreviewed")
    value = store.read()["judgments"].get(member["sha256"], {}).get("blue_hair")
    assert value is None or value["value"] == "unreviewed"


def test_label_metrics_exclude_uncertainty_assistant_and_unchecked_truth(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    partitions = by_set(store)
    calibration = partitions["calibration"]
    assert len(calibration) >= 4
    for members in partitions.values():
        for index, member in enumerate(members):
            save_truth(store, member, "present" if index == 0 else "absent")
    save_truth(store, calibration[2], "uncertain")
    save_truth(store, calibration[3], "present", kind="assistant")
    output, result = evaluate_labels(config, path, [scored])
    measured = result["models"][0]["labels"]["blue_hair"]
    assert measured["counts"]["calibration"]["uncertain"] == 1
    assert measured["counts"]["calibration"]["assistant_excluded"] == 1
    baseline = measured["calibration_baseline"]
    # Equal to the cutoff is absent, matching actual caption publication's strict > rule.
    assert (baseline["tp"], baseline["fp"], baseline["fn"]) == (0, 0, 1)
    assert baseline["tn"] == len(calibration) - 3
    assert baseline["precision"] is None and baseline["recall"] == 0
    unchecked = result["models"][0]["labels"]["red_eyes"]
    assert unchecked["fit_threshold"] is None
    assert unchecked["counts"]["calibration"]["unreviewed"] == len(calibration)
    assert unchecked["calibration_baseline"]["precision"] is None
    _, diagnostic = evaluate_labels(config, path, [scored], include_assistant=True)
    diagnostic_counts = diagnostic["models"][0]["labels"]["blue_hair"]["counts"]["calibration"]
    assert diagnostic_counts["present"] == 2
    assert diagnostic_counts["assistant_excluded"] == 0
    assert output != path and (output / "run.json").exists()


def test_held_out_changes_cannot_choose_threshold_and_results_keep_truth_snapshot(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    partitions = by_set(store)
    for members in partitions.values():
        for index, member in enumerate(members):
            save_truth(store, member, "present" if index == 0 else "absent")
    output, original = evaluate_labels(config, path, [scored])
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    for member in partitions["held_out"]:
        save_truth(store, member, "present")
    _, revised = evaluate_labels(config, path, [scored])
    first = original["models"][0]["labels"]["blue_hair"]
    second = revised["models"][0]["labels"]["blue_hair"]
    assert first["fit_threshold"] is not None
    assert first["fit_threshold"] == second["fit_threshold"]
    assert first["calibration_fitted"] == second["calibration_fitted"]
    assert first["held_out_fitted"] != second["held_out_fitted"]
    assert before == {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }


def test_fit_requires_positive_and_negative_calibration_evidence(evaluation_pilot):
    config, _, scored, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    for member in store.selection["members"]:
        save_truth(store, member, "present")
    _, result = evaluate_labels(config, path, [scored])
    label = result["models"][0]["labels"]["blue_hair"]
    assert label["fit_threshold"] is None
    assert label["calibration_fitted"] is None
    assert label["held_out_fitted"] is None
    assert label["calibration_baseline"]["fn"] == len(by_set(store)["calibration"])


def test_comparison_requires_all_frozen_content_for_every_model(evaluation_pilot):
    config, _, scored, path, publish = evaluation_pilot
    missing = LabelWorkspace(path).selection["members"][0]["sha256"]
    incomplete = publish(omit=missing, model="incomplete-fixture")
    existing = set(config.runs.iterdir())
    with pytest.raises(ValueError, match="missing .* selected path/hash"):
        evaluate_labels(config, path, [scored, incomplete])
    assert {p for p in config.runs.iterdir() if not p.name.startswith(".pending-")} == existing


def test_offline_evaluation_preserves_sources_reviews_and_caption_rules(evaluation_pilot):
    config, qa, scored, path, publish = evaluation_pilot
    store = LabelWorkspace(path)
    for members in by_set(store).values():
        for index, member in enumerate(members):
            save_truth(store, member, "present" if index == 0 else "absent")
    second_model = publish(model="fixture-two", rules=CaptionConfig(general_threshold=0.75))
    protected = {
        p: p.read_bytes()
        for root in (config.reviews, qa, scored, second_model)
        for p in root.rglob("*")
        if p.is_file()
    }
    sources = {p.name: p.read_bytes() for p in config.source.iterdir()}
    offline = config.source.with_name("offline-originals")
    config.source.rename(offline)
    _, result = evaluate_labels(config, path, [scored, second_model])
    assert len(result["models"]) == 2
    assert result["models"][0]["labels"]["blue_hair"]["baseline_threshold"] == 0.5
    assert result["models"][1]["labels"]["blue_hair"]["baseline_threshold"] == 0.75
    assert all(p.read_bytes() == raw for p, raw in protected.items())
    assert sources == {p.name: p.read_bytes() for p in offline.iterdir()}


@pytest.mark.parametrize("artifact", ["labels.json", "score_index.json", "vector"])
def test_changed_score_artifacts_fail_before_result_publication(evaluation_pilot, artifact):
    config, _, scored, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    if artifact == "vector":
        digest = store.selection["members"][0]["sha256"]
        target = scored / "scores" / f"{digest}.npy"
    else:
        target = scored / artifact
    target.write_bytes(target.read_bytes() + b"tampered")
    existing = set(config.runs.iterdir())
    with pytest.raises(ValueError, match="hash|integrity|checksum"):
        evaluate_labels(config, path, [scored])
    assert {p for p in config.runs.iterdir() if not p.name.startswith(".pending-")} == existing


def test_checked_score_index_rejects_escaping_paths(evaluation_pilot):
    _, _, scored, _, _ = evaluation_pilot
    index = json.loads((scored / "score_index.json").read_text(encoding="utf-8"))
    first = next(iter(index.values()))
    first["path"] = "../outside.npy"
    atomic_json(scored / "score_index.json", index)
    metadata = json.loads((scored / "run.json").read_text(encoding="utf-8"))
    metadata["score_index_sha256"] = file_sha256(scored / "score_index.json")
    atomic_json(scored / "run.json", metadata)
    with pytest.raises(ValueError, match="path|artifact"):
        run = ScoredRun(scored)
        run.vector(next(iter(index)))


def test_group_partition_validation_rejects_a_related_variant_in_other_set(evaluation_pilot):
    _, _, _, path, _ = evaluation_pilot
    store = LabelWorkspace(path)
    selection = store.selection
    first = next(
        m
        for m in selection["members"]
        if any(a["source_path"] == "image-0.png" for a in m["aliases"])
    )
    variant = next(
        m
        for m in selection["members"]
        if any(a["source_path"] == "image-1.png" for a in m["aliases"])
    )
    variant["evaluation_set"] = (
        "held_out" if first["evaluation_set"] == "calibration" else "calibration"
    )
    atomic_json(path / "selection.json", selection)
    metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
    metadata["files"]["selection.json"] = file_sha256(path / "selection.json")
    atomic_json(path / "run.json", metadata)
    with pytest.raises(ValueError, match="group|Group|evaluation sets"):
        LabelWorkspace(path)


def test_score_label_indexes_cannot_silently_change_truth_mapping(evaluation_pilot):
    _, _, scored, _, _ = evaluation_pilot
    labels = json.loads((scored / "labels.json").read_text(encoding="utf-8"))
    labels[0]["index"], labels[1]["index"] = labels[1]["index"], labels[0]["index"]
    atomic_json(scored / "labels.json", labels)
    metadata = json.loads((scored / "run.json").read_text(encoding="utf-8"))
    metadata["labels_sha256"] = file_sha256(scored / "labels.json")
    atomic_json(scored / "run.json", metadata)
    with pytest.raises(ValueError, match="label index"):
        ScoredRun(scored)


@pytest.mark.parametrize("label", ["blue hair", "unknown_raw_tag", "general"])
def test_workspace_rejects_display_names_unknown_tags_and_ratings(evaluation_pilot, label):
    config, qa, scored, _, _ = evaluation_pilot
    with pytest.raises(ValueError):
        create_label_workspace(
            config, qa, scored, [label], selection_reason="Invalid label fixture"
        )


def test_workspace_storage_cannot_overlap_originals(evaluation_pilot):
    config, qa, scored, _, _ = evaluation_pilot
    original = {p.name: p.read_bytes() for p in config.source.iterdir()}
    with pytest.raises(ValueError, match="separate|source|Source|overlap"):
        create_label_workspace(
            replace(config, reviews=config.source / "reviews"),
            qa,
            scored,
            ["blue_hair"],
            selection_reason="Unsafe storage fixture",
        )
    assert original == {p.name: p.read_bytes() for p in config.source.iterdir()}


@pytest.mark.parametrize("artifact", ["qa", "input", "reference", "workspace"])
@pytest.mark.parametrize("descendant", [False, True], ids=["equal", "descendant"])
def test_evaluation_outputs_cannot_mutate_any_frozen_input(evaluation_pilot, artifact, descendant):
    config, qa, reference, workspace, publish = evaluation_pilot
    store = LabelWorkspace(workspace)
    alternate = publish(model="alternate-scored-fixture")
    targets = {
        "qa": qa,
        "input": Path(store.selection["input_run"]),
        "reference": reference,
        "workspace": workspace,
    }
    target = targets[artifact]
    output = target / "nested-results" if descendant else target
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        # The reference is intentionally not among the model runs passed to this evaluation.
        evaluate_labels(replace(config, runs=output), workspace, [alternate])
    assert before == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    if descendant:
        assert not output.exists()


def test_cli_freezes_reviews_and_evaluates_the_same_saved_population(
    evaluation_pilot, capsys, monkeypatch
):
    config, qa, scored, _, _ = evaluation_pilot
    settings = config.source.parent / "evaluation-settings.toml"
    settings.write_text(
        'schema_version = 1\n[paths]\nsource = "originals"\nruns = "runs"\n'
        'reviews = "reviews"\n[captions]\ngeneral_threshold = 0.99\n',
        encoding="utf-8",
    )
    settings_bytes = settings.read_bytes()
    original = {p.name: p.read_bytes() for p in config.source.iterdir()}
    monkeypatch.chdir(config.source.parent)
    assert (
        main(
            [
                "label-pilot",
                "--run",
                str(qa),
                "--reference",
                str(scored),
                "--label",
                "blue_hair",
                "--reason",
                "Synthetic CLI workflow; no image-quality acceptance",
                "--seed",
                "7",
                "--config",
                str(settings),
                "--json",
            ]
        )
        == 0
    )
    frozen = json.loads(capsys.readouterr().out)
    workspace = Path(frozen["workspace"])
    assert frozen["unique_images"] == 8 and frozen["unreviewed_labels"] == 8
    assert main(["label-review", "--workspace", str(workspace), "--json"]) == 0
    before_review = json.loads(capsys.readouterr().out)
    assert before_review["state"]["revision"] == 0
    partitions = by_set(LabelWorkspace(workspace))
    selected = [
        (partitions["calibration"][0], "present"),
        (partitions["calibration"][1], "absent"),
        (partitions["held_out"][0], "present"),
    ]
    for revision, (member, value) in enumerate(selected):
        command = [
            "label-review",
            "--workspace",
            str(workspace),
            "--image",
            member["aliases"][0]["source_path"],
            "--label",
            "blue_hair",
            "--value",
            value,
            "--reviewer",
            "Synthetic CLI reviewer",
            "--reviewer-kind",
            "human",
            "--notes",
            "Known fixture truth",
            "--expected-revision",
            str(revision),
            "--json",
        ]
        assert main(command) == 0
        saved = json.loads(capsys.readouterr().out)
        assert saved["state"]["revision"] == revision + 1
    assert main(command) == 2  # A retry cannot silently overwrite a newer revision.
    capsys.readouterr()
    assert (
        main(
            [
                "tag-evaluate",
                "--workspace",
                str(workspace),
                "--run",
                str(scored),
                "--config",
                str(settings),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["judgment_revision"] == 3
    measured = result["models"][0]["labels"]["blue_hair"]
    assert measured["baseline_threshold"] == 0.5  # Frozen run, not today's config threshold.
    assert measured["fit_threshold"] is not None
    assert measured["held_out_baseline"]["fn"] == 1
    assert measured["held_out_fitted"]["tp"] == 1
    assert not result["human_accepted"] and not result["representative_acceptance"]
    assert (Path(result["run"]) / "result.json").is_file()
    assert settings.read_bytes() == settings_bytes
    assert original == {p.name: p.read_bytes() for p in config.source.iterdir()}


def _refresh(config, parent, groups, *, revision=None):
    from image_dataset_train.label_workspace import refresh_label_workspace

    if revision is None:
        revision = LabelWorkspace(parent).read()["revision"]
    return refresh_label_workspace(
        config,
        parent,
        groups,
        reason="Newly reviewed relationship in generated fixture; retain original label truth",
        expected_parent_revision=revision,
    )


def _tree_bytes(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def _selected_occurrences(store):
    return {
        (member["sha256"], alias["id"], alias["source_path"])
        for member in store.selection["members"]
        for alias in member["aliases"]
    }


def test_refresh_regroups_transitive_links_outside_pilot_without_rejudging(evaluation_pilot):
    config, _, scored, original_path, _ = evaluation_pilot
    original = LabelWorkspace(original_path)
    original_groups = Path(original.selection["input_run"])
    group_meta = json.loads((original_groups / "run.json").read_text(encoding="utf-8"))
    similarity = Path(group_meta["similarity_run"])
    qa, _ = create_qa(config, original_groups, captions_run=scored, sample_size=3)
    parent = create_label_workspace(
        config,
        qa,
        scored,
        ["blue_hair", "red_eyes"],
        selection_reason="Small synthetic pilot with other collection images outside it",
        seed=7,
    )
    store = LabelWorkspace(parent)
    subsets = by_set(store)
    left, right = subsets["calibration"][0], subsets["held_out"][0]
    selected_hashes = {m["sha256"] for m in store.selection["members"]}
    selected_groups = {m["group_id"] for m in store.selection["members"]}
    bridge = next(
        m
        for m in original.selection["members"]
        if m["sha256"] not in selected_hashes and m["group_id"] not in selected_groups
    )
    for index, member in enumerate(store.selection["members"]):
        save_truth(store, member, "present" if index == 0 else "absent", kind="assistant")
        save_truth(store, member, "uncertain", label="red_eyes", kind="assistant")
    # Include a cleared/overridden label in history, not only a flat current-state copy.
    save_truth(store, left, "unreviewed", label="red_eyes", kind="assistant")
    save_truth(store, left, "absent", label="red_eyes", kind="assistant")
    for member in (left, right):
        review_link(
            config,
            similarity,
            [member["aliases"][0]["source_path"], bridge["aliases"][0]["source_path"]],
            "related",
            "Fixture connection through a non-pilot collection image",
        )
    new_groups, _ = publish_groups(config, similarity)
    old_state = store.read()
    protected = {
        path: _tree_bytes(path) for path in (parent, qa, scored, original_groups, new_groups)
    }
    sources = _tree_bytes(config.source)
    refreshed_path = _refresh(config, parent, new_groups)
    refreshed = LabelWorkspace(refreshed_path)
    actual = refreshed.read()
    assert refreshed_path != parent
    assert _selected_occurrences(refreshed) == _selected_occurrences(store)
    assert refreshed.selection["labels"] == store.selection["labels"]
    members = {m["sha256"]: m for m in refreshed.selection["members"]}
    assert members[left["sha256"]]["group_id"] == members[right["sha256"]]["group_id"]
    assert members[left["sha256"]]["evaluation_set"] == members[right["sha256"]]["evaluation_set"]
    assert bridge["sha256"] not in members
    assert actual["judgments"] == old_state["judgments"]
    assert actual["history"] == old_state["history"]
    assert actual["revision"] == old_state["revision"]
    assert actual["selection_sha256"] == refreshed.selection_sha256 != store.selection_sha256
    assert Path(refreshed.selection["input_run"]) == new_groups
    provenance = refreshed.selection["refresh"]
    assert provenance["parent_judgment_revision"] == old_state["revision"]
    assert provenance["reused_evaluation_population"] is True
    for name, digest in refreshed.metadata["files"].items():
        assert file_sha256(refreshed_path / name) == digest
    assert (refreshed_path / "parent-run.json").read_bytes() == (parent / "run.json").read_bytes()
    assert (refreshed_path / "parent-selection.json").read_bytes() == (
        parent / "selection.json"
    ).read_bytes()
    assert json.loads((refreshed_path / "parent-judgments.json").read_text()) == old_state
    assert protected == {path: _tree_bytes(path) for path in protected}
    assert _tree_bytes(config.source) == sources
    save_truth(refreshed, members[left["sha256"]], "uncertain", kind="assistant")
    assert refreshed.read()["revision"] == old_state["revision"] + 1
    assert LabelWorkspace(parent).read() == old_state
    assert json.loads((refreshed_path / "parent-judgments.json").read_text()) == old_state


@pytest.mark.parametrize("change", ["source", "content", "missing", "excluded"])
def test_refresh_rejects_changed_or_ineligible_selected_occurrences(evaluation_pilot, change):
    config, _, _, parent, _ = evaluation_pilot
    store = LabelWorkspace(parent)
    member = next(m for m in store.selection["members"] if len(m["aliases"]) == 1)
    source_path = member["aliases"][0]["source_path"]
    group_meta = json.loads((Path(store.selection["input_run"]) / "run.json").read_text())
    if change == "excluded":
        similarity = Path(group_meta["similarity_run"])
        review_image(
            config, similarity, source_path, decision="exclude", reason="Fixture exclusion"
        )
        groups, _ = publish_groups(config, similarity)
    else:
        changed_config = config
        if change == "source":
            relocated = config.source.with_name("different-originals")
            shutil.copytree(config.source, relocated)
            changed_config = replace(config, source=relocated)
        elif change == "content":
            Image.new("RGB", (48, 64), "orange").save(config.source / source_path)
        else:
            (config.source / source_path).unlink()
        inventory, _ = run_scan(changed_config)
        similarity, _ = propose_similar(changed_config, inventory, max_distance=0)
        groups, _ = publish_groups(changed_config, similarity)
    before = _tree_bytes(parent)
    outputs = set(parent.parent.iterdir())
    with pytest.raises(ValueError):
        _refresh(config, parent, groups)
    assert _tree_bytes(parent) == before
    assert set(parent.parent.iterdir()) == outputs


def test_refresh_rejects_stale_revision_and_corrupt_parent_evidence(evaluation_pilot):
    config, _, _, parent, _ = evaluation_pilot
    store = LabelWorkspace(parent)
    groups = Path(store.selection["input_run"])
    save_truth(store, store.selection["members"][0], "present", kind="assistant")
    outputs = set(parent.parent.iterdir())
    before = _tree_bytes(parent)
    with pytest.raises(ValueError, match="revision|changed|Reload"):
        _refresh(config, parent, groups, revision=0)
    assert _tree_bytes(parent) == before
    (parent / "selection.json").write_bytes((parent / "selection.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash|integrity"):
        _refresh(config, parent, groups, revision=1)
    assert set(parent.parent.iterdir()) == outputs


def test_refresh_rejects_modified_inherited_provenance(evaluation_pilot):
    config, _, _, parent, _ = evaluation_pilot
    groups = Path(LabelWorkspace(parent).selection["input_run"])
    successor = _refresh(config, parent, groups)
    artifact = successor / "parent-judgments.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")
    outputs = set(parent.parent.iterdir())
    with pytest.raises(ValueError, match="hash|integrity"):
        _refresh(config, successor, groups, revision=0)
    assert set(parent.parent.iterdir()) == outputs


def test_open_refreshed_workspace_detects_later_inherited_evidence_corruption(evaluation_pilot):
    config, _, _, parent, _ = evaluation_pilot
    groups = Path(LabelWorkspace(parent).selection["input_run"])
    successor = _refresh(config, parent, groups)
    opened = LabelWorkspace(successor)
    opened.read()
    snapshot = successor / "parent-judgments.json"
    snapshot.write_bytes(snapshot.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash|integrity"):
        opened.read()


def test_refreshed_evaluation_retains_parent_evidence_when_workspaces_are_unavailable(
    evaluation_pilot,
):
    config, _, scored, parent, _ = evaluation_pilot
    store = LabelWorkspace(parent)
    for index, member in enumerate(store.selection["members"]):
        save_truth(store, member, "present" if index % 2 else "absent", kind="assistant")
    parent_state = store.read()
    groups = Path(store.selection["input_run"])
    successor = _refresh(config, parent, groups)
    output, result = evaluate_labels(config, successor, [scored], include_assistant=True)
    snapshots = result["workspace_provenance"]
    assert set(snapshots) == {"parent-run.json", "parent-selection.json", "parent-judgments.json"}
    frozen_output = _tree_bytes(output)
    parent.rename(parent.with_name(parent.name + "-offline"))
    successor.rename(successor.with_name(successor.name + "-offline"))
    assert not parent.exists() and not successor.exists()
    # The evaluation alone carries both the source metadata and each inherited artifact.
    archived_workspace = json.loads((output / "workspace-run.json").read_text())
    archived_result = json.loads((output / "result.json").read_text())
    metadata = json.loads((output / "run.json").read_text())
    assert archived_result["workspace_provenance"] == snapshots
    for source_name, archived_name in snapshots.items():
        digest = file_sha256(output / archived_name)
        assert digest == archived_workspace["files"][source_name]
        assert digest == metadata["files"][archived_name]
    inherited = json.loads((output / snapshots["parent-judgments.json"]).read_text())
    assert inherited == parent_state
    assert {
        r["reviewer_kind"] for labels in inherited["judgments"].values() for r in labels.values()
    } == {"assistant"}
    assert archived_result["judgment_revision"] == parent_state["revision"]
    assert not archived_result["human_accepted"]
    assert _tree_bytes(output) == frozen_output


@pytest.mark.parametrize("artifact", ["source", "workspace", "groups", "qa", "reference"])
def test_refresh_outputs_cannot_be_nested_inside_protected_inputs(evaluation_pilot, artifact):
    config, qa, reference, parent, _ = evaluation_pilot
    store = LabelWorkspace(parent)
    groups = Path(store.selection["input_run"])
    target = {
        "source": config.source,
        "workspace": parent,
        "groups": groups,
        "qa": qa,
        "reference": reference,
    }[artifact]
    before = _tree_bytes(target)
    with pytest.raises(ValueError):
        _refresh(replace(config, reviews=target / "new-reviews"), parent, groups)
    assert _tree_bytes(target) == before
    assert not (target / "new-reviews").exists()


def test_refresh_cli_preserves_assistant_attribution_and_default_exclusion(
    evaluation_pilot, capsys, monkeypatch
):
    config, _, scored, parent, _ = evaluation_pilot
    store = LabelWorkspace(parent)
    for index, member in enumerate(store.selection["members"]):
        save_truth(store, member, "present" if index % 2 else "absent", kind="assistant")
    groups = Path(store.selection["input_run"])
    settings = config.source.parent / "refresh-settings.toml"
    settings.write_text(
        'schema_version = 1\n[paths]\nsource = "originals"\nruns = "runs"\nreviews = "reviews"\n'
    )
    monkeypatch.chdir(config.source.parent)
    command = [
        "label-refresh",
        "--workspace",
        str(parent),
        "--groups",
        str(groups),
        "--reason",
        "Retain assistant-only synthetic evidence",
        "--expected-revision",
        str(store.read()["revision"]),
        "--config",
        str(settings),
        "--json",
    ]
    assert main(command) == 0
    summary = json.loads(capsys.readouterr().out)
    refreshed = Path(summary["workspace"])
    assert summary["reviewer_kinds"] == {"assistant": len(store.selection["members"])}
    assert (
        main(
            [
                "tag-evaluate",
                "--workspace",
                str(refreshed),
                "--run",
                str(scored),
                "--config",
                str(settings),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    metrics = result["models"][0]["labels"]["blue_hair"]
    assert metrics["fit_threshold"] is None
    assert sum(c["assistant_excluded"] for c in metrics["counts"].values()) == len(store.members)
    assert not result["human_accepted"] and not result["representative_acceptance"]
    assert (
        LabelWorkspace(parent).read()["judgments"] == LabelWorkspace(refreshed).read()["judgments"]
    )
