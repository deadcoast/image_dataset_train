import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from test_label_evaluation import evaluation_pilot as evaluation_pilot

from image_dataset_train.cli import main
from image_dataset_train.diagnostics import atomic_json
from image_dataset_train.inventory import file_sha256
from image_dataset_train.label_sampling import (
    ALGORITHM,
    digest,
    evaluation_grouping,
    partition_members,
    population_frame,
)
from image_dataset_train.label_workspace import (
    LabelWorkspace,
    create_label_workspace,
    refresh_label_workspace,
)
from image_dataset_train.preparation_policy import prepare_groups
from image_dataset_train.qa import create_qa
from image_dataset_train.reviews import (
    load_context,
    publish_groups,
    review_image,
    review_link,
    review_pair,
)
from image_dataset_train.runs import run_scan
from image_dataset_train.similarity import propose_similar


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sample(pilot, **kwargs):
    config, qa, scored, _, _ = pilot
    return create_label_workspace(
        config,
        qa,
        scored,
        ["blue_hair", "red_eyes"],
        selection_reason="Predeclared synthetic probability sample",
        probability_sample_size=kwargs.pop("probability_sample_size", 4),
        selection_seed=kwargs.pop("selection_seed", 20261110),
        **kwargs,
    )


def rewrite_selection(directory, selection):
    atomic_json(directory / "selection.json", selection)
    metadata = read(directory / "run.json")
    metadata["files"]["selection.json"] = file_sha256(directory / "selection.json")
    atomic_json(directory / "run.json", metadata)


def test_full_frame_ignores_qa_pilot_models_and_training_decisions(evaluation_pilot):
    config, qa, scored, _, _ = evaluation_pilot
    groups = Path(read(qa / "run.json")["input_run"])
    tiny_qa, summary = create_qa(config, groups, captions_run=scored, sample_size=1)
    assert len(summary["pilot_ids"]) == 1
    policy, _ = prepare_groups(config, groups, captions_run=scored)
    # All fixture images are below the trainer minimum, but remain valid label-review inputs.
    policy_rows = [json.loads(line) for line in (policy / "groups.jsonl").read_text().splitlines()]
    assert all(m["review_decision"] == "exclude" for g in policy_rows for m in g["members"])
    workspace = create_label_workspace(
        config,
        tiny_qa,
        scored,
        ["blue_hair"],
        selection_reason="Full source frame",
        probability_sample_size=8,
        selection_seed=20261110,
        partition_groups=policy,
    )
    store = LabelWorkspace(workspace)
    assert len(store.members) == 8 and store.summary()["source_occurrences"] == 9
    sampling = store.selection["sampling"]
    assert sampling["population_unique_images"] == sampling["sample_unique_images"] == 8
    assert sampling["inclusion_probability"] == {"numerator": 8, "denominator": 8}
    assert store.selection["evaluation_grouping"]["training_eligibility_used"] is False
    assert (
        store.selection["evaluation_grouping"]["origin"]["kind"]
        == "preparation_partition_constraints"
    )
    expected = {m["sha256"]: g["group_id"] for g in policy_rows for m in g["members"]}
    assert {sha: m["group_id"] for sha, m in store.members.items()} == expected
    entries = [json.loads(line) for line in (tiny_qa / "entries.jsonl").read_text().splitlines()]
    original_groups = [
        json.loads(line) for line in (groups / "groups.jsonl").read_text().splitlines()
    ]
    before = population_frame(entries, original_groups)
    for entry in entries:
        entry.update(
            decision="exclude",
            pilot=False,
            caption="arbitrary changed prediction",
            findings=["new"],
        )
    assert population_frame(entries, original_groups) == before


def test_partition_review_status_comes_from_partition_snapshot(evaluation_pilot):
    config, qa, scored, _, _ = evaluation_pilot
    original = Path(read(qa / "run.json")["input_run"])
    original_summary = read(original / "summary.json")
    assert original_summary["review_complete"] is False
    similarity = Path(read(original / "run.json")["similarity_run"])
    context = load_context(similarity)
    for pair in context.pairs():
        review_pair(config, similarity, pair["pair_id"], "related", "Synthetic relation")
    for path, member in context.rows.items():
        if member["kind"] == "image":
            review_image(config, similarity, path, decision="include", reason="Synthetic inclusion")
    reviewed, summary = publish_groups(config, similarity)
    assert summary["review_complete"] is True
    reviewed_qa, _ = create_qa(config, reviewed, captions_run=scored)
    directory = create_label_workspace(
        config,
        reviewed_qa,
        scored,
        ["blue_hair"],
        selection_reason="Review status follows independent partition evidence",
        probability_sample_size=4,
        selection_seed=20261110,
        partition_groups=original,
    )
    selection = LabelWorkspace(directory).selection
    assert selection["evaluation_grouping"]["origin"]["kind"] == "group_snapshot"
    assert selection["group_review_complete"] is False
    assert selection["unresolved_pairs"] == original_summary["unresolved_pairs"]


def test_draw_replays_exact_rank_keeps_all_aliases_and_has_separate_partition_seed(
    evaluation_pilot,
):
    first = LabelWorkspace(sample(evaluation_pilot, probability_sample_size=8, seed=101))
    second = LabelWorkspace(sample(evaluation_pilot, probability_sample_size=8, seed=202))
    assert first.selection["sampling"] == second.selection["sampling"]
    assert {sha: m["aliases"] for sha, m in first.members.items()} == {
        sha: m["aliases"] for sha, m in second.members.items()
    }
    frame = first.selection["sampling"]["population_frame"]
    expected = sorted(
        [m["sha256"] for m in frame],
        key=lambda sha: (
            hashlib.sha256(f"{ALGORITHM}\0{20261110}\0{sha}".encode()).hexdigest(),
            sha,
        ),
    )
    assert first.selection["sampling"]["drawn_sha256"] == expected
    reduced = LabelWorkspace(sample(evaluation_pilot, probability_sample_size=4))
    assert set(reduced.members) == set(expected[:4])
    assert reduced.selection["sampling"]["inclusion_probability"] == {
        "numerator": 4,
        "denominator": 8,
    }
    grouped = {}
    for member in reduced.members.values():
        assert (
            grouped.setdefault(member["group_id"], member["evaluation_set"])
            == member["evaluation_set"]
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"probability_sample_size": 0},
        {"probability_sample_size": 9},
        {"probability_sample_size": True},
        {"selection_seed": None},
        {"selection_seed": True},
        {"source_paths": ["image-0.png"]},
    ],
)
def test_invalid_sampling_options_do_not_publish(evaluation_pilot, kwargs):
    root = evaluation_pilot[0].reviews / "label-evaluations"
    before = set(root.iterdir())
    with pytest.raises(ValueError):
        sample(evaluation_pilot, **kwargs)
    assert set(root.iterdir()) == before


def test_sampling_only_options_cannot_modify_legacy_selection(evaluation_pilot):
    config, qa, scored, _, _ = evaluation_pilot
    with pytest.raises(ValueError, match="require probability"):
        create_label_workspace(
            config, qa, scored, ["blue_hair"], selection_reason="Invalid", selection_seed=12
        )


def test_partition_mapping_requires_exact_full_population_and_source(evaluation_pilot, tmp_path):
    config, qa, _, _, _ = evaluation_pilot
    workspace = LabelWorkspace(sample(evaluation_pilot))
    frame = workspace.selection["sampling"]["population_frame"]
    groups_path = Path(read(qa / "run.json")["input_run"])
    groups = [json.loads(line) for line in (groups_path / "groups.jsonl").read_text().splitlines()]
    incomplete = deepcopy(groups)
    incomplete.pop()
    with pytest.raises(ValueError, match="every frozen source identity"):
        evaluation_grouping(frame, incomplete, {})
    foreign = tmp_path / "foreign-groups"
    shutil.copytree(groups_path, foreign)
    metadata = read(foreign / "run.json")
    metadata["source"] = str(tmp_path / "another-source")
    atomic_json(foreign / "run.json", metadata)
    before = set((config.reviews / "label-evaluations").iterdir())
    with pytest.raises(ValueError, match="source differs"):
        sample(evaluation_pilot, partition_groups=foreign)
    assert set((config.reviews / "label-evaluations").iterdir()) == before


def test_probability_workspace_reads_without_source_or_parent_artifacts(evaluation_pilot, tmp_path):
    config, _, _, _, _ = evaluation_pilot
    directory = sample(evaluation_pilot)
    frozen = LabelWorkspace(directory).selection
    config.source.rename(tmp_path / "offline source")
    config.runs.rename(tmp_path / "offline parent runs")
    assert LabelWorkspace(directory).selection == frozen
    assert LabelWorkspace(directory).read()["revision"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "frame_hash",
        "frame",
        "draw",
        "probability",
        "boolean",
        "aliases",
        "partition",
        "origin_relative",
        "origin_foreign",
        "origin_checksum",
        "missing_design",
    ],
)
def test_read_replays_frozen_design_even_when_outer_metadata_is_rehashed(
    evaluation_pilot, mutation
):
    directory = sample(evaluation_pilot, probability_sample_size=8)
    selection = read(directory / "selection.json")
    design = selection["sampling"]
    if mutation == "frame_hash":
        design["population_frame_sha256"] = "0" * 64
    elif mutation == "frame":
        design["population_frame"].pop()
        design["population_frame_sha256"] = digest(design["population_frame"])
    elif mutation == "draw":
        design["drawn_sha256"].reverse()
    elif mutation == "probability":
        design["inclusion_probability"]["denominator"] += 1
    elif mutation == "boolean":
        design["schema_version"] = True
    elif mutation == "aliases":
        next(m for m in selection["members"] if len(m["aliases"]) == 2)["aliases"].pop()
    elif mutation == "origin_relative":
        selection["evaluation_grouping"]["origin"]["run"] = "relative-placeholder"
    elif mutation == "origin_foreign":
        selection["evaluation_grouping"]["origin"]["run"] = str(directory / "unbound-origin")
    elif mutation == "origin_checksum":
        selection["evaluation_grouping"]["origin"]["run_sha256"] = "0" * 64
    elif mutation == "missing_design":
        del selection["sampling"], selection["evaluation_grouping"]
    else:
        selection["members"][0]["group_id"] = "f" * 64
    rewrite_selection(directory, selection)
    with pytest.raises(ValueError):
        LabelWorkspace(directory)


def test_refresh_retains_sampling_and_judgments_even_for_excluded_originals(evaluation_pilot):
    config, qa, _, _, _ = evaluation_pilot
    parent = LabelWorkspace(sample(evaluation_pilot, probability_sample_size=8))
    member = next(iter(parent.members.values()))
    parent.save(
        {
            "image": member["sha256"],
            "label": "blue_hair",
            "value": "uncertain",
            "reviewer": "Synthetic assistant",
            "reviewer_kind": "assistant",
            "notes": "Fixture evidence",
            "expected_revision": 0,
        }
    )
    source_groups = Path(read(qa / "run.json")["input_run"])
    similarity = Path(read(source_groups / "run.json")["similarity_run"])
    review_link(config, similarity, ["image-2.png", "image-3.png"], "related", "Synthetic family")
    review_image(
        config, similarity, "image-0.png", decision="exclude", reason="Fixture training exclusion"
    )
    groups, _ = publish_groups(config, similarity)
    directory = refresh_label_workspace(
        config, parent.directory, groups, reason="Corrected groups", expected_parent_revision=1
    )
    child = LabelWorkspace(directory)
    assert child.selection["sampling"] == parent.selection["sampling"]
    assert child.read()["history"] == parent.read()["history"]
    assert child.read()["judgments"] == parent.read()["judgments"]
    assert child.selection["evaluation_grouping"] != parent.selection["evaluation_grouping"]


@pytest.mark.parametrize("field", ["seed", "held_out_fraction", "qa_sha256"])
def test_refresh_rejects_rehashed_protocol_change(evaluation_pilot, field):
    config, qa, _, _, _ = evaluation_pilot
    parent = sample(evaluation_pilot, probability_sample_size=8)
    groups = Path(read(qa / "run.json")["input_run"])
    child = refresh_label_workspace(
        config, parent, groups, reason="Same frame, retained protocol", expected_parent_revision=0
    )
    selection = read(child / "selection.json")
    selection[field] = {"seed": 23, "held_out_fraction": 0.5, "qa_sha256": "0" * 64}[field]
    partition_members(selection["members"], selection["seed"], selection["held_out_fraction"])
    rewrite_selection(child, selection)
    with pytest.raises(ValueError, match="frozen content or vocabulary"):
        LabelWorkspace(child)


def test_refresh_rejects_changed_unselected_population_member(evaluation_pilot):
    config, _, _, _, _ = evaluation_pilot
    parent = LabelWorkspace(sample(evaluation_pilot, probability_sample_size=1))
    chosen = set(parent.members)
    outside = next(
        m for m in parent.selection["sampling"]["population_frame"] if m["sha256"] not in chosen
    )
    path = config.source / outside["aliases"][0]["source_path"]
    path.rename(path.with_name("renamed-" + path.name))
    inventory, _ = run_scan(config)
    similarity, _ = propose_similar(config, inventory)
    groups, _ = publish_groups(config, similarity)
    with pytest.raises(ValueError, match="every frozen source identity"):
        refresh_label_workspace(
            config,
            parent.directory,
            groups,
            reason="Changed population",
            expected_parent_revision=0,
        )


def test_probability_cli_passes_selection_and_partition_parameters(
    evaluation_pilot, tmp_path, capsys
):
    config, qa, scored, _, _ = evaluation_pilot
    settings = tmp_path / "settings.toml"
    settings.write_text(
        "schema_version=1\n[paths]\n"
        + "\n".join(
            f"{name}={json.dumps(str(getattr(config, name)))}"
            for name in ("source", "runs", "reviews", "exports")
        ),
        encoding="utf-8",
    )
    groups = read(qa / "run.json")["input_run"]
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
                "Predeclared fixture sample",
                "--probability-sample-size",
                "4",
                "--selection-seed",
                "20261110",
                "--seed",
                "20261011",
                "--partition-groups",
                groups,
                "--config",
                str(settings),
                "--json",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["sampling"]["selection_seed"] == 20261110
    assert summary["sampling"]["inclusion_probability"] == {"numerator": 4, "denominator": 8}
    assert LabelWorkspace(Path(summary["workspace"])).selection["seed"] == 20261011
