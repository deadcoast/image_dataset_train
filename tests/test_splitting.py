from dataclasses import replace

from image_dataset_train.config import ExportConfig
from image_dataset_train.splitting import assign_splits, plan_splits


def test_semantic_balancing_represents_labels_and_subsets_at_the_same_ratio():
    settings = ExportConfig(validation_ratio=0.5)
    sizes = {f"group-{i}": 2 for i in range(4)}
    baseline = assign_splits(sizes, settings)
    # Build two label/subset categories that the size-only allocation segregates.
    included = [
        (
            key,
            {
                "labels": ["portrait", "blue hair"] if split == "validation" else ["landscape"],
                "subset": "solo" if split == "validation" else "scenery",
            },
        )
        for key, split in baseline.items()
        for _ in range(2)
    ]
    result = plan_splits(included, settings)
    assert result["algorithm"] == "semantic-groups-v1"
    assert sum(sizes[k] for k, s in result["assignments"].items() if s == "validation") == 4
    assert all(row["validation_images"] == 2 for row in result["balance"]["strata"])
    assert result == plan_splits(list(reversed(included)), settings)
    assert (
        plan_splits(included, replace(settings, split_strategy="size"))["assignments"] == baseline
    )


def test_rare_and_mixed_groups_are_reported_without_splitting_members():
    included = [
        ("related", {"labels": ["rare"], "subset": "solo"}),
        ("related", {"labels": ["rare", "portrait"], "subset": "multiple"}),
        ("other", {"labels": ["portrait"], "subset": "solo"}),
        ("unknown", {}),
    ]
    result = plan_splits(included, ExportConfig(validation_ratio=0.5))
    rare = next(row for row in result["balance"]["strata"] if row["name"] == "rare")
    assert rare["single_group"] and rare["validation_images"] in (0, 2)
    assert result["balance"]["mixed_subset_groups"] == {"related": ["multiple", "solo"]}
    assert result["balance"]["annotations"]["labels_reviewed"] == 3
    assert set(result["assignments"]) == {"related", "other", "unknown"}
    zero = plan_splits(included, ExportConfig(validation_ratio=0))
    assert set(zero["assignments"].values()) == {"train"}
    plain = [(str(i), {}) for i in range(4)]
    assert plan_splits(plain, ExportConfig())["algorithm"] == "seeded-group-count-v1"
