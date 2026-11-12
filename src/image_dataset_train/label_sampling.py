"""Replayable hash-only sampling and separate frozen evaluation group constraints."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path, PurePosixPath

ALGORITHM = "representative-source-content-v1"


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return not (
        path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(part.rstrip(". ") != part for part in path.parts)
        or any(ord(char) < 32 for char in value)
    )


def validate_frame(frame: object) -> None:
    if not isinstance(frame, list) or not frame:
        raise ValueError("Probability sampling requires a nonempty frozen population frame")
    hashes, paths, identifiers = set(), set(), set()
    for item in frame:
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "aliases"}
            or not _hash(item["sha256"])
            or item["sha256"] in hashes
            or not isinstance(item["aliases"], list)
            or not item["aliases"]
        ):
            raise ValueError("Invalid or repeated population content identity")
        hashes.add(item["sha256"])
        for alias in item["aliases"]:
            if (
                not isinstance(alias, dict)
                or set(alias) != {"id", "source_path"}
                or not _path(alias["source_path"])
                or not _hash(alias["id"])
                or alias["source_path"] in paths
                or alias["id"] in identifiers
            ):
                raise ValueError("Invalid or repeated population source alias")
            expected = hashlib.sha256(
                f"0\0{alias['source_path']}\0{item['sha256']}".encode()
            ).hexdigest()
            if alias["id"] != expected:
                raise ValueError("Population alias identifier differs from its path/content")
            paths.add(alias["source_path"])
            identifiers.add(alias["id"])
        if item["aliases"] != sorted(item["aliases"], key=lambda alias: alias["source_path"]):
            raise ValueError("Population aliases must use canonical source-path order")
    if frame != sorted(frame, key=lambda item: item["sha256"]):
        raise ValueError("Population frame must use canonical content-hash order")


def population_frame(entries: list[dict], groups: list[dict]) -> list[dict]:
    """Use every QA/group identity; never inspect captions, scores or eligibility."""
    identities = {
        (member["source_path"], member["sha256"]): group["group_id"]
        for group in groups
        for member in group["members"]
    }
    if (
        len(entries) != len(identities)
        or len({entry["source_path"] for entry in entries}) != len(entries)
        or any(
            identities.get((entry["source_path"], entry["sha256"])) != entry["group_id"]
            for entry in entries
        )
    ):
        raise ValueError("Probability population must cover the complete QA/group identity frame")
    members = {}
    for entry in entries:
        members.setdefault(entry["sha256"], []).append(
            {"id": entry["id"], "source_path": entry["source_path"]}
        )
    frame = [
        {"sha256": sha, "aliases": sorted(aliases, key=lambda alias: alias["source_path"])}
        for sha, aliases in sorted(members.items())
    ]
    validate_frame(frame)
    return frame


def draw_hashes(frame: list[dict], size: int, seed: int) -> list[str]:
    validate_frame(frame)
    if type(size) is not int or not 1 <= size <= len(frame):
        raise ValueError("Probability sample size must be between 1 and the full population size")
    if type(seed) is not int:
        raise ValueError("Choose an explicit integer selection seed")
    hashes = [item["sha256"] for item in frame]
    return sorted(
        hashes,
        key=lambda sha: (
            hashlib.sha256(f"{ALGORITHM}\0{seed}\0{sha}".encode()).hexdigest(),
            sha,
        ),
    )[:size]


def probability_design(frame: list[dict], size: int, seed: int) -> dict:
    selected = draw_hashes(frame, size, seed)
    return {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "selection_seed": seed,
        "sampling_unit": "unique_original_content_sha256",
        "population_unique_images": len(frame),
        "sample_unique_images": size,
        "population_frame": deepcopy(frame),
        "population_frame_sha256": digest(frame),
        "inclusion_probability": {"numerator": size, "denominator": len(frame)},
        "drawn_sha256": selected,
    }


def evaluation_grouping(frame: list[dict], groups: list[dict], origin: dict) -> dict:
    """Bind every source occurrence, ignoring the partition snapshot's training decisions."""
    validate_frame(frame)
    expected = {
        (alias["source_path"], item["sha256"]) for item in frame for alias in item["aliases"]
    }
    seen, assigned = set(), {}
    for group in groups:
        if not _hash(group["group_id"]):
            raise ValueError("Invalid evaluation group identity")
        for member in group["members"]:
            identity = member["source_path"], member["sha256"]
            if identity not in expected or identity in seen:
                raise ValueError("Partition groups must match every frozen source identity exactly")
            seen.add(identity)
            if assigned.setdefault(member["sha256"], group["group_id"]) != group["group_id"]:
                raise ValueError("Exact aliases cannot cross evaluation partition groups")
    if seen != expected:
        raise ValueError("Partition groups must match every frozen source identity exactly")
    memberships = [{"sha256": sha, "group_id": group} for sha, group in sorted(assigned.items())]
    return {
        "schema_version": 1,
        "origin": deepcopy(origin),
        "training_eligibility_used": False,
        "memberships": memberships,
        "memberships_sha256": digest(memberships),
    }


def partition_members(members: list[dict], seed: int, held_out_fraction: float) -> None:
    if type(seed) is not int:
        raise ValueError("Evaluation seed must be an integer")
    if (
        type(held_out_fraction) not in {int, float}
        or not math.isfinite(held_out_fraction)
        or not 0 < held_out_fraction < 1
    ):
        raise ValueError("Held-out fraction must be between zero and one")
    group_ids = sorted(
        {member["group_id"] for member in members},
        key=lambda group: hashlib.sha256(f"{seed}\0{group}".encode()).hexdigest(),
    )
    held_count = min(len(group_ids) - 1, max(1, round(len(group_ids) * held_out_fraction)))
    held_out = set(group_ids[: max(0, held_count)])
    for member in members:
        member["evaluation_set"] = "held_out" if member["group_id"] in held_out else "calibration"


def validate_probability_selection(selection: dict) -> None:
    """Replay exclusively from immutable selection bytes, with no parent/source reads."""
    sample, grouping = selection.get("sampling"), selection.get("evaluation_grouping")
    if not isinstance(sample, dict) or not isinstance(grouping, dict):
        raise ValueError("Probability selection is missing its frozen sampling/grouping evidence")
    probability = sample.get("inclusion_probability")
    if (
        type(sample.get("schema_version")) is not int
        or type(sample.get("population_unique_images")) is not int
        or not isinstance(probability, dict)
        or type(probability.get("numerator")) is not int
        or type(probability.get("denominator")) is not int
    ):
        raise ValueError("Invalid probability sampling counts or schema")
    expected = probability_design(
        sample.get("population_frame"),
        sample.get("sample_unique_images"),
        sample.get("selection_seed"),
    )
    if sample != expected:
        raise ValueError("Probability sampling metadata or draw differs from the frozen replay")
    frame = sample["population_frame"]
    memberships = grouping.get("memberships")
    origin = grouping.get("origin")
    if (
        set(grouping)
        != {
            "schema_version",
            "origin",
            "training_eligibility_used",
            "memberships",
            "memberships_sha256",
        }
        or type(grouping["schema_version"]) is not int
        or grouping["schema_version"] != 1
        or grouping["training_eligibility_used"] is not False
        or not isinstance(origin, dict)
        or set(origin) != {"run", "run_sha256", "source", "kind"}
        or not isinstance(origin["run"], str)
        or not Path(origin["run"]).is_absolute()
        or (
            origin["run"] != selection["input_run"]
            and origin["run"] not in selection.get("lineage_inputs", [])
        )
        or (
            origin["run"] == selection["input_run"]
            and origin["run_sha256"] != selection["input_run_sha256"]
        )
        or not _hash(origin["run_sha256"])
        or origin["source"] != selection["source"]
        or origin["kind"]
        not in {"group_snapshot", "reviewed_group_snapshot", "preparation_partition_constraints"}
        or not isinstance(memberships, list)
        or len(memberships) != len(frame)
        or any(
            not isinstance(item, dict)
            or set(item) != {"sha256", "group_id"}
            or not _hash(item["sha256"])
            or not _hash(item["group_id"])
            for item in memberships
        )
        or [item["sha256"] for item in memberships] != [item["sha256"] for item in frame]
        or grouping["memberships_sha256"] != digest(memberships)
    ):
        raise ValueError("Invalid frozen evaluation partition grouping")
    groups = {item["sha256"]: item["group_id"] for item in memberships}
    group_members = {}
    for item in frame:
        group_members.setdefault(groups[item["sha256"]], []).extend(
            [alias["source_path"], item["sha256"]] for alias in item["aliases"]
        )
    for group_id, identities in group_members.items():
        # Match the established groups artifact identity, including all source aliases.
        expected_group = hashlib.sha256(
            json.dumps(sorted(identities), ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        if group_id != expected_group:
            raise ValueError(
                "Frozen evaluation group identity differs from its complete membership"
            )
    chosen = set(sample["drawn_sha256"])
    members = [
        {**deepcopy(item), "group_id": groups[item["sha256"]]}
        for item in frame
        if item["sha256"] in chosen
    ]
    partition_members(members, selection["seed"], selection["held_out_fraction"])
    if members != selection["members"]:
        raise ValueError("Frozen labels do not match the probability draw, aliases or partitions")
