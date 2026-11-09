"""Deterministic group allocation with reviewed multi-label and subset balancing."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict

from image_dataset_train.annotations import annotation_fields, annotation_summary
from image_dataset_train.config import ExportConfig


def _rank(seed: int, key: str) -> str:
    return hashlib.sha256(json.dumps([seed, key], ensure_ascii=False).encode()).hexdigest()


def assign_splits(groups: dict[str, int], settings: ExportConfig) -> dict[str, str]:
    """The original image-count allocator, also used as the semantic starting point."""
    order = sorted(groups, key=lambda key: (_rank(settings.seed, key), key))
    total = sum(groups.values())
    target = total * settings.validation_ratio
    validation, selected = 0, set()
    if target and len(order) > 1:
        for key in order:
            candidate = validation + groups[key]
            if candidate < total and abs(candidate - target) < abs(validation - target):
                selected.add(key)
                validation = candidate
        if not selected:
            selected.add(min(order, key=lambda key: abs(groups[key] - target)))
    return {key: "validation" if key in selected else "train" for key in sorted(groups)}


def _features(member: dict) -> list[tuple[str, str]]:
    fields = annotation_fields(member)
    result = [("label", label) for label in fields["labels"]] if fields["labels_reviewed"] else []
    if fields["subset_reviewed"] and fields["subset"] is not None:
        result.append(("subset", fields["subset"]))
    return result


def balance_report(
    included: list[tuple[str, dict]], assignments: dict[str, str], ratio: float
) -> dict:
    totals, validation = Counter(), Counter()
    memberships, subsets = defaultdict(set), defaultdict(set)
    for group_id, member in included:
        for feature in _features(member):
            totals[feature] += 1
            validation[feature] += assignments[group_id] == "validation"
            memberships[feature].add(group_id)
            if feature[0] == "subset":
                subsets[group_id].add(feature[1])
    return {
        "annotations": annotation_summary(member for _, member in included),
        "strata": [
            {
                "kind": kind,
                "name": name,
                "images": count,
                "groups": len(memberships[(kind, name)]),
                "target_validation_images": count * ratio,
                "validation_images": validation[(kind, name)],
                "train_images": count - validation[(kind, name)],
                "single_group": len(memberships[(kind, name)]) == 1,
                "missing_validation": validation[(kind, name)] == 0,
                "missing_train": validation[(kind, name)] == count,
            }
            for (kind, name), count in sorted(totals.items())
        ],
        "mixed_subset_groups": {
            key: sorted(values) for key, values in sorted(subsets.items()) if len(values) > 1
        },
    }


def plan_splits(included: list[tuple[str, dict]], settings: ExportConfig) -> dict:
    sizes = Counter(key for key, _ in included)
    assignments = assign_splits(dict(sizes), settings)
    vectors = {key: Counter() for key in sizes}
    for key, member in included:
        vectors[key].update(_features(member))
    totals = Counter()
    for vector in vectors.values():
        totals.update(vector)
    semantic = settings.split_strategy == "semantic" and bool(totals)
    passes = 0
    capped = False
    if semantic and settings.validation_ratio and len(sizes) > 1:
        ranks = {key: _rank(settings.seed, key) for key in sizes}
        order = sorted(sizes, key=lambda key: (ranks[key], key))
        signatures = {key: (sizes[key], tuple(sorted(vectors[key].items()))) for key in sizes}
        selected = {key for key, split in assignments.items() if split == "validation"}
        counts = Counter()
        for key in order:
            if key in selected:
                counts.update(vectors[key])
        count = sum(sizes[key] for key in selected)
        target = sum(sizes.values()) * settings.validation_ratio
        # Normalize each stratum by its population and average within each family.
        families = Counter(kind for kind, _ in totals)
        weights = {key: 1 / (value * value * families[key[0]]) for key, value in totals.items()}

        def delta(changes):
            return sum(
                (
                    (counts[key] + value - totals[key] * settings.validation_ratio) ** 2
                    - (counts[key] - totals[key] * settings.validation_ratio) ** 2
                )
                * weights[key]
                for key, value in changes.items()
            )

        def improvement(size_delta, changes):
            return round(abs(count + size_delta - target) - abs(count - target), 12), round(
                delta(changes), 12
            )

        # Sparse move deltas and bounded swaps avoid an all-pairs collection scan.
        for _ in range(32):
            best_score, best_move = (0.0, 0.0), None
            candidates = {True: [], False: []}
            for key in order:
                removing = key in selected
                sign = -1 if removing else 1
                changes = {name: sign * value for name, value in vectors[key].items()}
                score = improvement(sign * sizes[key], changes)
                candidates[removing].append((score, key))
                if 0 < len(selected) + sign < len(sizes) and score < best_score:
                    best_score, best_move = score, (key, None)

            def shortlist(items):
                seen, result = set(), []
                for _, key in sorted(items, key=lambda item: (item[0], ranks[item[1]])):
                    signature = signatures[key]
                    if signature not in seen:
                        seen.add(signature)
                        result.append(key)
                    if len(result) == 64:
                        break
                return result

            removals, additions = shortlist(candidates[True]), shortlist(candidates[False])
            for left in removals:
                for right in additions:
                    changes = dict(vectors[right])
                    for name, value in vectors[left].items():
                        changes[name] = changes.get(name, 0) - value
                    score = improvement(sizes[right] - sizes[left], changes)
                    if score < best_score:
                        best_score, best_move = score, (left, right)
            if best_move is None:
                break
            for key in best_move:
                if key is None:
                    continue
                sign = -1 if key in selected else 1
                count += sign * sizes[key]
                for name, value in vectors[key].items():
                    counts[name] += sign * value
                selected.symmetric_difference_update({key})
            passes += 1
        else:
            capped = True
        assignments = {key: "validation" if key in selected else "train" for key in sorted(sizes)}
    return {
        "algorithm": "semantic-groups-v1" if semantic else "seeded-group-count-v1",
        "strategy": settings.split_strategy,
        "seed": settings.seed,
        "validation_ratio": settings.validation_ratio,
        "assignments": assignments,
        "optimization_passes": passes,
        "search_limit_reached": capped,
        "balance": balance_report(included, assignments, settings.validation_ratio),
    }
