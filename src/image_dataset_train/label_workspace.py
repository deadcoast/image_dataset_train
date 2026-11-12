"""Frozen critical-label populations and explicit, prediction-independent judgments."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.exporting import _checked, _load_groups, _path, _published
from image_dataset_train.implementation import implementation_identity
from image_dataset_train.inventory import file_sha256
from image_dataset_train.label_sampling import (
    evaluation_grouping,
    population_frame,
    probability_design,
    validate_probability_selection,
)
from image_dataset_train.label_sampling import (
    partition_members as _partition_members,
)
from image_dataset_train.qa import read_qa
from image_dataset_train.reviews import ReviewConflict, _separate


def _digest(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value.strip()


def _validate_selection(selection: dict) -> None:
    if (
        not isinstance(selection, dict)
        or type(selection.get("schema_version")) is not int
        or selection["schema_version"] != 1
    ):
        raise ValueError("Invalid label selection")
    labels = selection.get("labels")
    lineage = selection.get("lineage_inputs", [])
    if not isinstance(lineage, list) or any(
        not isinstance(path, str) or not Path(path).is_absolute() for path in lineage
    ):
        raise ValueError("Invalid label-workspace input lineage")
    if not isinstance(labels, list) or not labels:
        raise ValueError("Choose a nonempty raw WD label vocabulary")
    names = set()
    for label in labels:
        if not isinstance(label, dict):
            raise ValueError("Invalid raw WD label")
        name = _text(label.get("name"), "Raw WD label")
        if name != label["name"] or name in names or label.get("category") not in {0, 4}:
            raise ValueError("Use unique raw WD general/character labels, not ratings")
        names.add(name)
    groups, hashes, paths, ids = {}, set(), set(), set()
    members = selection.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("The frozen pilot must contain images")
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("Invalid frozen image record")
        digest, group, split = (member.get(key) for key in ("sha256", "group_id", "evaluation_set"))
        if not _digest(digest) or digest in hashes or not _digest(group):
            raise ValueError("Invalid or duplicate frozen image/group identity")
        if split not in {"calibration", "held_out"} or groups.setdefault(group, split) != split:
            raise ValueError("Related groups cannot cross evaluation sets")
        hashes.add(digest)
        aliases = member.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError("Frozen images need their source aliases")
        for alias in aliases:
            if not isinstance(alias, dict):
                raise ValueError("Invalid frozen source alias")
            path, identifier = alias.get("source_path"), alias.get("id")
            _path(Path(selection["source"]), path)
            if path in paths or not _digest(identifier) or identifier in ids:
                raise ValueError("Repeated or invalid source alias")
            paths.add(path)
            ids.add(identifier)
    if (
        "sampling" in selection
        or "evaluation_grouping" in selection
        or selection.get("selection_method")
        == "probability sample of the complete unique original-content frame"
    ):
        validate_probability_selection(selection)


def _judgment_json(raw: str | bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate keys in label judgment evidence")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite value in label judgment evidence: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def _grouping_origin(directory: Path, metadata: dict, checksum: str) -> dict:
    return {
        "run": str(directory.resolve()),
        "run_sha256": checksum,
        "source": str(Path(metadata["source"]).resolve()),
        "kind": (
            "preparation_partition_constraints"
            if metadata.get("preparation_policy")
            else "group_snapshot"
        ),
    }


def _publish_workspace(
    root: Path,
    selection: dict,
    *,
    state: dict | None = None,
    provenance: dict[str, bytes] | None = None,
) -> Path:
    _validate_selection(selection)
    implementation = implementation_identity()
    root.mkdir(parents=True, exist_ok=True)
    pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    for name, raw in (provenance or {}).items():
        _path(pending, name).write_bytes(raw)
    atomic_json(pending / "selection.json", selection)
    selection_digest = file_sha256(pending / "selection.json")
    state = (
        deepcopy(state)
        if state is not None
        else {"schema_version": 1, "revision": 0, "judgments": {}, "history": []}
    )
    state["selection_sha256"] = selection_digest
    atomic_json(pending / "judgments.json", state)
    identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-labels-" + uuid4().hex[:8]
    atomic_json(
        pending / "run.json",
        {
            "schema_version": 1,
            "stage": "label_workspace",
            "status": "completed",
            "run_id": identifier,
            "created_at": datetime.now(UTC).isoformat(),
            "implementation": implementation,
            "source": selection["source"],
            "files": {
                name: file_sha256(pending / name)
                for name in ("selection.json", *(provenance or {}))
            },
        },
    )
    destination = root / identifier
    publish_directory(pending, destination)
    return destination


def create_label_workspace(
    config: Config,
    qa_run: Path,
    reference_run: Path,
    labels: list[str],
    *,
    selection_reason: str,
    seed: int = 20261011,
    held_out_fraction: float = 0.33,
    source_paths: list[str] | None = None,
    probability_sample_size: int | None = None,
    selection_seed: int | None = None,
    partition_groups: Path | None = None,
) -> Path:
    """Freeze one existing group-QA pilot; this does not certify its representativeness."""
    from image_dataset_train.scored_runs import ScoredRun

    selection_reason = _text(selection_reason, "Selection reason")
    probability = probability_sample_size is not None
    if probability and source_paths is not None:
        raise ValueError("Choose probability sampling or explicit source paths, not both")
    if not probability and (selection_seed is not None or partition_groups is not None):
        raise ValueError("Selection seed and partition groups require probability sampling")
    if probability and type(selection_seed) is not int:
        raise ValueError("Probability sampling requires an explicit integer selection seed")
    if type(seed) is not int:
        raise ValueError("Evaluation seed must be an integer")
    if (
        type(held_out_fraction) not in {int, float}
        or not math.isfinite(held_out_fraction)
        or not 0 < held_out_fraction < 1
    ):
        raise ValueError("Held-out fraction must be between zero and one")
    qa_run = qa_run.absolute()
    qa_digest = file_sha256(_path(qa_run, "run.json"))
    meta, data = read_qa(qa_run)
    snapshot = Path(meta["input_run"])
    if file_sha256(_path(snapshot, "run.json")) != meta["input_run_sha256"]:
        raise ValueError("QA input snapshot hash mismatch")
    group_meta, groups, group_artifacts = _load_groups(snapshot, require_reviewed=False)
    group_summary = json.loads(group_artifacts["summary.json"])
    source = Path(meta["source"]).resolve()
    if Path(group_meta["source"]).resolve() != source:
        raise ValueError("QA and group snapshot source mismatch")
    identities = {
        (member["source_path"], member["sha256"]): group["group_id"]
        for group in groups
        for member in group["members"]
    }
    sampling, grouping, partition_digest = None, None, None
    partition_summary = group_summary
    if probability:
        frame = population_frame(data["entries"], groups)
        sampling = probability_design(frame, probability_sample_size, selection_seed)
        partition_path = snapshot
        partition_meta, partition_members = group_meta, groups
        partition_digest = meta["input_run_sha256"]
        if partition_groups is not None:
            partition_path = partition_groups.absolute()
            partition_digest = file_sha256(_path(partition_path, "run.json"))
            partition_meta, partition_members, partition_artifacts = _load_groups(
                partition_path, require_reviewed=False
            )
            partition_summary = json.loads(partition_artifacts["summary.json"])
            if Path(partition_meta["source"]).resolve() != source:
                raise ValueError("Partition groups source differs from the probability population")
        grouping = evaluation_grouping(
            frame,
            partition_members,
            _grouping_origin(partition_path, partition_meta, partition_digest),
        )
        source_paths = [
            alias["source_path"]
            for member in frame
            if member["sha256"] in sampling["drawn_sha256"]
            for alias in member["aliases"]
        ]
    scored = ScoredRun(reference_run)
    if Path(scored.metadata["source"]).resolve() != source:
        raise ValueError("Reference score source differs from QA source")
    if not isinstance(labels, list) or not labels or len(set(labels)) != len(labels):
        raise ValueError("Choose unique raw WD labels")
    vocabulary = {label.name: label for label in scored.labels}
    if any(name not in vocabulary or vocabulary[name].category not in {0, 4} for name in labels):
        raise ValueError("Choose raw WD general/character labels in the reference run, not ratings")
    pilot = data["summary"]["pilot_ids"]
    if len(set(pilot)) != len(pilot):
        raise ValueError("Duplicate QA pilot identifiers")
    entries = {entry["id"]: entry for entry in data["entries"]}
    if len(entries) != len(data["entries"]) or set(pilot) - entries.keys():
        raise ValueError("QA pilot membership differs from its entries")
    if source_paths is not None:
        if (
            not isinstance(source_paths, list)
            or not source_paths
            or any(not isinstance(path, str) or not path for path in source_paths)
            or len(set(source_paths)) != len(source_paths)
        ):
            raise ValueError("Choose a nonempty list of unique exact source paths")
        paths = {entry["source_path"]: entry["id"] for entry in entries.values()}
        if len(paths) != len(entries) or set(source_paths) - paths.keys():
            raise ValueError("Selected source paths must match the verified QA entries")
        pilot = [paths[path] for path in sorted(source_paths)]
    scored_identities = {
        (row["source_path"], row.get("sha256"))
        for row in scored.rows
        if row.get("decision") == "tagged"
    }
    members = {}
    for identifier in pilot:
        entry = entries[identifier]
        identity = (entry["source_path"], entry["sha256"])
        if not probability and (
            (source_paths is None and not entry["pilot"]) or entry["decision"] == "exclude"
        ):
            raise ValueError("Pilot includes an excluded or unselected entry")
        if identities.get(identity) != entry["group_id"]:
            raise ValueError("QA image/group identity differs from its snapshot")
        if identity not in scored_identities:
            raise ValueError("Reference scores must cover every frozen path/hash identity")
        member = members.setdefault(
            entry["sha256"],
            {"sha256": entry["sha256"], "group_id": entry["group_id"], "aliases": []},
        )
        if member["group_id"] != entry["group_id"]:
            raise ValueError("Exact-byte aliases cannot belong to different groups")
        member["aliases"].append({"id": identifier, "source_path": entry["source_path"]})
    for digest, member in members.items():
        scored.vector(digest)  # Verify the selected vectors before creating review state.
        member["aliases"].sort(key=lambda alias: alias["source_path"])
    if probability:
        assignments = {item["sha256"]: item["group_id"] for item in grouping["memberships"]}
        for digest, member in members.items():
            member["group_id"] = assignments[digest]
    _partition_members(list(members.values()), seed, held_out_fraction)
    selection = {
        "schema_version": 1,
        "source": str(source),
        "qa_run": str(qa_run.resolve()),
        "qa_sha256": qa_digest,
        "input_run": str(snapshot.resolve()),
        "input_run_sha256": meta["input_run_sha256"],
        "reference_run": str(scored.run),
        "reference_run_sha256": scored.digest,
        "labels": [{"name": name, "category": vocabulary[name].category} for name in labels],
        "members": [members[digest] for digest in sorted(members)],
        "selection_reason": selection_reason,
        "selection_method": (
            "explicit source paths from verified QA; representativeness requires independent review"
            if source_paths is not None
            else "frozen QA pilot; representativeness requires independent review"
        ),
        "seed": seed,
        "held_out_fraction": held_out_fraction,
        "partition_method": "seeded SHA256 group order; rounded group fraction, not image fraction",
        "group_review_complete": partition_summary.get("review_complete", False),
        "unresolved_pairs": partition_summary.get("unresolved_pairs"),
        "limitations": [
            "Known frozen groups are disjoint; unresolved relationships can still conceal leakage.",
            "Existing QA coverage selection can depend on the model's caption findings.",
            "Singleton group populations have no held-out group.",
        ],
    }
    if probability:
        selection.update(
            sampling=sampling,
            evaluation_grouping=grouping,
            selection_method="probability sample of the complete unique original-content frame",
            lineage_inputs=[str(partition_path.resolve())],
            limitations=[
                "Sampling uses original hashes, independently of models and training eligibility.",
                "Frozen groups are disjoint; unresolved relationships can still conceal leakage.",
                "Preparation group constraints do not establish verified semantic relationships.",
                "Prior exposure is not exhaustive; retain an attributed external audit overlay.",
                "Comparison and threshold fitting remain diagnostic; no threshold is adopted.",
                "Singleton group populations have no held-out group.",
            ],
        )
    _validate_selection(selection)
    root = config.reviews.resolve() / "label-evaluations"
    _separate(source, root)
    for artifact in (qa_run.resolve(), snapshot.resolve(), scored.run):
        _separate(artifact, root)
    if probability:
        _separate(partition_path.resolve(), root)
        if file_sha256(_path(partition_path, "run.json")) != partition_digest:
            raise ValueError("Partition groups changed while freezing the probability sample")
    if file_sha256(qa_run / "run.json") != qa_digest:
        raise ValueError("QA report changed while freezing the pilot")
    if file_sha256(snapshot / "run.json") != meta["input_run_sha256"]:
        raise ValueError("QA input snapshot changed while freezing the pilot")
    return _publish_workspace(root, selection)


def refresh_label_workspace(
    config: Config,
    parent_workspace: Path,
    groups_run: Path,
    *,
    reason: str,
    expected_parent_revision: int,
) -> Path:
    """Carry unchanged-content judgments into a new grouping of the same frozen pilot."""
    reason = _text(reason, "Refresh reason")
    parent = LabelWorkspace(parent_workspace)
    state = parent.read()
    if type(expected_parent_revision) is not int or state["revision"] != expected_parent_revision:
        raise ReviewConflict(
            "Parent judgments changed. Reload the workspace revision before refresh."
        )
    groups_run = groups_run.absolute()
    groups_digest = file_sha256(_path(groups_run, "run.json"))
    group_meta, groups, group_artifacts = _load_groups(groups_run, require_reviewed=False)
    groups_run = groups_run.resolve(strict=True)
    source = Path(parent.selection["source"]).resolve()
    if Path(group_meta["source"]).resolve() != source:
        raise ValueError("New groups source differs from the frozen pilot")
    identities = {
        (member["source_path"], member["sha256"]): (group["group_id"], member["review_decision"])
        for group in groups
        for member in group["members"]
    }
    selection = deepcopy(parent.selection)
    probability = "sampling" in selection
    if probability:
        selection["evaluation_grouping"] = evaluation_grouping(
            selection["sampling"]["population_frame"],
            groups,
            _grouping_origin(groups_run, group_meta, groups_digest),
        )
    for member in selection["members"]:
        assigned = set()
        for alias in member["aliases"]:
            match = identities.get((alias["source_path"], member["sha256"]))
            if match is None:
                raise ValueError(
                    "New groups are missing a selected path/hash identity or its content changed"
                )
            group_id, decision = match
            if decision == "exclude" and not probability:
                raise ValueError(
                    "New groups exclude a selected image; choose a new pilot explicitly"
                )
            assigned.add(group_id)
        if len(assigned) != 1:
            raise ValueError("Selected exact-byte aliases cross new related groups")
        member["group_id"] = assigned.pop()
    _partition_members(selection["members"], selection["seed"], selection["held_out_fraction"])
    lineage = {
        str(parent.directory),
        *(
            str(Path(parent.selection[key]).resolve())
            for key in ("qa_run", "input_run", "reference_run")
        ),
        *parent.selection.get("lineage_inputs", []),
    }
    root = config.reviews.resolve() / "label-evaluations"
    _separate(source, root)
    if any(root.is_relative_to(Path(path).resolve()) for path in (*lineage, str(groups_run))):
        raise ValueError("Refreshed workspaces cannot be published inside their input lineage")
    parent_state_raw = (
        json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    provenance = {
        "parent-run.json": _checked(parent.directory, "run.json", parent.digest),
        "parent-selection.json": _checked(
            parent.directory, "selection.json", parent.selection_sha256
        ),
        "parent-judgments.json": parent_state_raw,
    }
    summary = json.loads(group_artifacts["summary.json"])
    selection.update(
        input_run=str(groups_run),
        input_run_sha256=groups_digest,
        group_review_complete=summary.get("review_complete", False),
        unresolved_pairs=summary.get("unresolved_pairs"),
        lineage_inputs=sorted(lineage),
        refresh={
            "parent_workspace": str(parent.directory),
            "parent_workspace_sha256": parent.digest,
            "parent_selection_sha256": parent.selection_sha256,
            "parent_judgment_revision": state["revision"],
            "parent_judgments_sha256": hashlib.sha256(parent_state_raw).hexdigest(),
            "previous_input_run": parent.selection["input_run"],
            "previous_input_run_sha256": parent.selection["input_run_sha256"],
            "reason": reason,
            "at": datetime.now(UTC).isoformat(),
            "judgment_policy": "carry_forward_unchanged_content",
            "reused_evaluation_population": True,
            "qa_context": "original QA selection and image views; current groups are input_run",
        },
    )
    limitation = (
        "Refreshed partitions reuse reviewed data; "
        "this is not a new independent validation population."
    )
    if limitation not in selection["limitations"]:
        selection["limitations"].append(limitation)
    if file_sha256(_path(groups_run, "run.json")) != groups_digest:
        raise ValueError("Group snapshot changed during label refresh")
    if parent.read()["revision"] != expected_parent_revision:
        raise ReviewConflict(
            "Parent judgments changed during refresh; retry with the current revision."
        )
    return _publish_workspace(root, selection, state=state, provenance=provenance)


class LabelWorkspace:
    def __init__(self, directory: Path):
        directory = directory.absolute()
        self.digest = file_sha256(_path(directory, "run.json"))
        self.directory = directory.resolve(strict=True)
        self.metadata = _published(self.directory, {"label_workspace"})
        self.selection_sha256 = self.metadata["files"]["selection.json"]
        self.selection = json.loads(
            _checked(self.directory, "selection.json", self.selection_sha256)
        )
        _validate_selection(self.selection)
        _separate(Path(self.selection["source"]).resolve(), self.directory)
        self.members = {member["sha256"]: member for member in self.selection["members"]}
        self.labels = {label["name"] for label in self.selection["labels"]}
        self.inherited_state = None
        if "refresh" in self.selection:
            self._load_inheritance()

    def _load_inheritance(self) -> None:
        refresh = self.selection["refresh"]
        if (
            not isinstance(refresh, dict)
            or refresh.get("judgment_policy") != "carry_forward_unchanged_content"
        ):
            raise ValueError("Invalid label refresh provenance")
        raw = {
            name: _checked(self.directory, name, self.metadata["files"].get(name))
            for name in ("parent-run.json", "parent-selection.json", "parent-judgments.json")
        }
        for name, key in (
            ("parent-run.json", "parent_workspace_sha256"),
            ("parent-selection.json", "parent_selection_sha256"),
            ("parent-judgments.json", "parent_judgments_sha256"),
        ):
            if hashlib.sha256(raw[name]).hexdigest() != refresh.get(key):
                raise ValueError("Label refresh snapshot hash mismatch")
        parent_meta = json.loads(raw["parent-run.json"])
        parent_selection = json.loads(raw["parent-selection.json"])
        parent_state = _judgment_json(raw["parent-judgments.json"])
        _validate_selection(parent_selection)
        if (
            parent_meta.get("files", {}).get("selection.json") != refresh["parent_selection_sha256"]
            or parent_selection["labels"] != self.selection["labels"]
            or parent_selection.get("sampling") != self.selection.get("sampling")
            or any(
                parent_selection.get(key) != self.selection.get(key)
                for key in (
                    "seed",
                    "held_out_fraction",
                    "selection_reason",
                    "selection_method",
                    "partition_method",
                    "qa_run",
                    "qa_sha256",
                    "reference_run",
                    "reference_run_sha256",
                )
            )
            or Path(parent_selection["source"]).resolve()
            != Path(self.selection["source"]).resolve()
            or [
                {"sha256": m["sha256"], "aliases": m["aliases"]}
                for m in parent_selection["members"]
            ]
            != [{"sha256": m["sha256"], "aliases": m["aliases"]} for m in self.selection["members"]]
            or refresh.get("parent_workspace") not in self.selection.get("lineage_inputs", [])
        ):
            raise ValueError("Label refresh changed its frozen content or vocabulary")
        self._validate_state(parent_state, refresh["parent_selection_sha256"])
        if (
            type(refresh.get("parent_judgment_revision")) is not int
            or parent_state["revision"] != refresh["parent_judgment_revision"]
        ):
            raise ValueError("Label refresh parent revision mismatch")
        self.inherited_state = parent_state

    def _record(self, digest: str, label: str, record: dict | None) -> None:
        if (
            not isinstance(digest, str)
            or not isinstance(label, str)
            or digest not in self.members
            or label not in self.labels
        ):
            raise ValueError("Judgment is outside the frozen images/raw label vocabulary")
        if record is None:
            return
        if (
            not isinstance(record, dict)
            or set(record)
            - {"value", "reviewer", "reviewer_kind", "notes", "at", "comparison_exposure"}
            or not isinstance(record.get("value"), str)
            or record["value"]
            not in {
                "present",
                "absent",
                "uncertain",
            }
        ):
            raise ValueError("Invalid actual-presence judgment")
        if not isinstance(record.get("reviewer_kind"), str) or record["reviewer_kind"] not in {
            "human",
            "assistant",
        }:
            raise ValueError("Specify whether the reviewer is human or assistant")
        for key in ("reviewer", "notes", "at"):
            _text(record.get(key), key)
        exposure = record.get("comparison_exposure", [])
        if not isinstance(exposure, list):
            raise ValueError("Invalid model comparison exposure")
        for item in exposure:
            if (
                not isinstance(item, dict)
                or set(item) != {"run", "run_sha256", "at", "reviewer", "reviewer_kind"}
                or not isinstance(item.get("run"), str)
                or not Path(item["run"]).is_absolute()
                or not _digest(item.get("run_sha256"))
            ):
                raise ValueError("Invalid model comparison exposure")
            _text(item.get("at"), "Comparison exposure timestamp")
            _text(item.get("reviewer"), "Comparison viewer")
            if not isinstance(item.get("reviewer_kind"), str) or item["reviewer_kind"] not in {
                "human",
                "assistant",
            }:
                raise ValueError("Invalid comparison viewer kind")

    def read(self) -> dict:
        if file_sha256(_path(self.directory, "run.json")) != self.digest:
            raise ValueError("Label workspace metadata changed")
        _checked(self.directory, "selection.json", self.selection_sha256)
        if self.inherited_state is not None:
            for name in ("parent-run.json", "parent-selection.json", "parent-judgments.json"):
                _checked(self.directory, name, self.metadata["files"].get(name))
        state = _judgment_json(_path(self.directory, "judgments.json").read_text(encoding="utf-8"))
        self._validate_state(state, self.selection_sha256)
        if self.inherited_state is not None and (
            state["history"][: self.inherited_state["revision"]] != self.inherited_state["history"]
        ):
            raise ValueError("Carried-forward label history changed")
        return state

    def _validate_state(self, state: dict, selection_sha256: str) -> None:
        if (
            not isinstance(state, dict)
            or set(state)
            != {"schema_version", "selection_sha256", "revision", "history", "judgments"}
            or type(state.get("schema_version")) is not int
            or state.get("schema_version") != 1
            or state.get("selection_sha256") != selection_sha256
            or type(state.get("revision")) is not int
            or not isinstance(state.get("history"), list)
            or not isinstance(state.get("judgments"), dict)
            or state["revision"] != len(state["history"])
        ):
            raise ValueError("Invalid label judgment history/identity")
        replay = {}
        for revision, event in enumerate(state["history"], 1):
            if (
                not isinstance(event, dict)
                or not {"revision", "sha256", "label", "record"} <= set(event)
                or set(event) - {"revision", "sha256", "label", "record", "actor"}
            ):
                raise ValueError("Invalid label judgment history event")
            digest, label, record = event.get("sha256"), event.get("label"), event.get("record")
            if type(event.get("revision")) is not int or event["revision"] != revision:
                raise ValueError("Invalid label judgment revision")
            self._record(digest, label, record)
            if "actor" in event:
                actor = event["actor"]
                if not isinstance(actor, dict):
                    raise ValueError("Invalid label judgment actor")
                if record is None:
                    if actor.get("value") != "unreviewed":
                        raise ValueError("Cleared label judgment requires an unreviewed actor")
                    self._record(digest, label, {**actor, "value": "uncertain"})
                elif actor != record:
                    raise ValueError("Label judgment actor differs from its record")
                else:
                    self._record(digest, label, actor)
            if record is None:
                replay.get(digest, {}).pop(label, None)
                if not replay.get(digest):
                    replay.pop(digest, None)
            else:
                replay.setdefault(digest, {})[label] = record
        if replay != state.get("judgments"):
            raise ValueError("Label judgments differ from their history")

    def summary(self, state: dict | None = None) -> dict:
        state = self.read() if state is None else state
        self._validate_state(state, self.selection_sha256)
        if self.inherited_state is not None and (
            state["history"][: self.inherited_state["revision"]] != self.inherited_state["history"]
        ):
            raise ValueError("Carried-forward label history changed")
        values, kinds = Counter(), Counter()
        for labels in state["judgments"].values():
            for record in labels.values():
                values[record["value"]] += 1
                kinds[record["reviewer_kind"]] += 1
        return {
            "workspace": str(self.directory),
            "revision": state["revision"],
            "unique_images": len(self.members),
            "labels": sorted(self.labels),
            "source_occurrences": sum(len(member["aliases"]) for member in self.members.values()),
            "evaluation_sets": dict(Counter(m["evaluation_set"] for m in self.members.values())),
            "judgments": dict(values),
            "reviewer_kinds": dict(kinds),
            "unreviewed_labels": len(self.members) * len(self.labels) - values.total(),
            "selection_reason": self.selection["selection_reason"],
            "sampling": (
                {
                    key: self.selection["sampling"][key]
                    for key in (
                        "algorithm",
                        "selection_seed",
                        "population_unique_images",
                        "sample_unique_images",
                        "population_frame_sha256",
                        "inclusion_probability",
                    )
                }
                if "sampling" in self.selection
                else None
            ),
            "acceptance": "not established by this workspace",
        }

    def _prepare_judgment(self, payload: dict) -> tuple[str, str, dict]:
        if not isinstance(payload, dict):
            raise ValueError("Each label judgment must be an object")
        image = _text(payload.get("image"), "Image path or SHA256")
        matches = [
            digest
            for digest, member in self.members.items()
            if image == digest or any(a["source_path"] == image for a in member["aliases"])
        ]
        if len(matches) != 1:
            raise ValueError("Choose one frozen image by exact source path or SHA256")
        digest, label = matches[0], payload.get("label")
        reviewer = _text(payload.get("reviewer"), "Reviewer")
        notes = _text(payload.get("notes"), "Judgment notes")
        if payload.get("reviewer_kind") not in {"human", "assistant"}:
            raise ValueError("Specify whether the reviewer is human or assistant")
        record = {
            "value": payload.get("value"),
            "reviewer": reviewer,
            "reviewer_kind": payload["reviewer_kind"],
            "notes": notes,
            "at": datetime.now(UTC).isoformat(),
        }
        if "comparison_exposure" in payload:
            record["comparison_exposure"] = deepcopy(payload["comparison_exposure"])
        self._record(
            digest,
            label,
            {**record, "value": "uncertain"} if record["value"] == "unreviewed" else record,
        )
        return digest, label, record

    def save(self, payload: dict) -> dict:
        return self.save_many([payload], expected_revision=payload.get("expected_revision"))

    def save_many(self, payloads: list[dict], *, expected_revision: int) -> dict:
        """Commit a validated batch atomically, preserving one history event per judgment."""
        if not isinstance(payloads, list) or not payloads or len(payloads) > 1000:
            raise ValueError("Save between one and 1000 label judgments at a time")
        prepared = [self._prepare_judgment(payload) for payload in payloads]
        if len({(digest, label) for digest, label, _ in prepared}) != len(prepared):
            raise ValueError("A batch cannot repeat an image/label judgment")
        if type(expected_revision) is not int:
            raise ValueError("Reload the label workspace before saving")
        try:
            with FileLock(str(_path(self.directory, "judgments.lock")), timeout=0):
                state = self.read()
                if state["revision"] != expected_revision:
                    raise ReviewConflict("Label judgments changed. Reload before saving again.")
                exposed = {}
                for event in state["history"]:
                    # Only an absent legacy actor falls back to the record.
                    # Present malformed actors are rejected by read() above.
                    prior = event["actor"] if "actor" in event else event["record"] or {}
                    if prior.get("comparison_exposure"):
                        exposed[(event["sha256"], event["label"])] = prior["comparison_exposure"]
                for digest, label, record in prepared:
                    exposure = deepcopy(exposed.get((digest, label), []))
                    for item in record.get("comparison_exposure", []):
                        if item not in exposure:
                            exposure.append(item)
                    if exposure:
                        record["comparison_exposure"] = exposure
                    clear = record["value"] == "unreviewed"
                    if clear:
                        state["judgments"].get(digest, {}).pop(label, None)
                        if not state["judgments"].get(digest):
                            state["judgments"].pop(digest, None)
                    else:
                        state["judgments"].setdefault(digest, {})[label] = record
                    state["revision"] += 1
                    state["history"].append(
                        {
                            "revision": state["revision"],
                            "sha256": digest,
                            "label": label,
                            "record": None if clear else record,
                            "actor": record,
                        }
                    )
                self._validate_state(state, self.selection_sha256)
                atomic_json(_path(self.directory, "judgments.json"), state)
        except Timeout as exc:
            raise ReviewConflict("Another label judgment save is running; retry.") from exc
        return {"state": state, "summary": self.summary(state)}
