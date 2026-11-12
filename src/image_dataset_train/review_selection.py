"""Shared exact selection and publication guidance for review operations."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from image_dataset_train.collection_registry import CollectionRegistry, path_key, unlinked_path
from image_dataset_train.config import Config, load_config
from image_dataset_train.implementation import implementation_identity


def add_selection_arguments(parser) -> None:
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--collection", help="registered collection name or exact ID")
    selector.add_argument("--workspace", type=Path, help="saved preparation workspace")
    selector.add_argument("--run", type=Path, help="explicit published similarity run")
    parser.add_argument("--config", type=Path, help="required with --run only")
    parser.add_argument("--job", help="expected current job for a collection or workspace")
    parser.add_argument("--json", action="store_true", help="structured records and commands")


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def read_metadata_bytes(path: Path, *, limit=64 * 1024 * 1024) -> bytes:
    path = unlinked_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError(f"Review selection requires bounded regular metadata: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    unlinked_path(path)
    after = path.stat()
    if len(raw) > limit or (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise ValueError(f"Review selection metadata changed while reading: {path}")
    return raw


def _checked_config(path: Path) -> tuple[Config, str]:
    path = unlinked_path(path)
    raw = read_metadata_bytes(path)
    parsed = tomllib.loads(raw.decode("utf-8"))
    paths = parsed.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Configuration paths must be a table")
    inactive = {}
    for key, default in (
        ("source", "data/00_inbox"),
        ("runs", "data/runs"),
        ("models", "data/models"),
        ("scores", "data/derived/scores"),
        ("reviews", "data/reviews"),
        ("exports", "data/exports"),
    ):
        value = paths.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"paths.{key} must be a nonempty path string")
        if key in {"source", "reviews"}:
            unlinked_path(path.parent / value)
        else:
            # These locations are not read by history. Keep their recorded paths
            # stable if an unrelated model/cache/export root becomes a junction.
            inactive[key] = Path(os.path.abspath(path.parent / value))
    config = load_config(path)
    if read_metadata_bytes(path) != raw:
        raise ValueError("Configuration changed while selecting reviews")
    return replace(config, **inactive), hashlib.sha256(raw).hexdigest()


@dataclass
class Selection:
    config: Config
    run: Path
    identity: dict
    state: dict | None = None


def select_review(args) -> Selection:
    """Use saved ownership contracts, never a directory's implicit latest run."""
    from image_dataset_train.preparation import _config, _inspect_attempt, read_preparation_job

    entry = None
    if args.run is not None:
        if args.config is None or args.job is not None:
            raise ValueError("Explicit --run requires --config and does not accept --job")
        config_path = unlinked_path(args.config)
        config, config_hash = _checked_config(config_path)
        selected_run = unlinked_path(args.run)
        identity = {"kind": "run", "config": str(config_path), "config_sha256": config_hash}
        state = None
    else:
        if args.config is not None:
            raise ValueError(
                "Collection/workspace review uses its saved configuration; omit --config"
            )
        if args.collection is not None:
            entry = CollectionRegistry().resolve(args.collection)
            workspace = unlinked_path(Path(entry["workspace"]))
        else:
            workspace = unlinked_path(args.workspace)
        binding_before = read_metadata_bytes(workspace / "collection.json")
        job, state = read_preparation_job(workspace)
        job_before = read_metadata_bytes(job / "job.json")
        if json.loads(job_before) != state:
            raise ValueError("Preparation job changed while selecting reviews")
        if args.job is not None and args.job != state["job_id"]:
            raise ValueError(
                f"Current preparation job is {state['job_id']}, not {args.job}; inspect it first"
            )
        if entry and path_key(entry["source"]) != path_key(state["source"]):
            raise ValueError("Registered collection source differs from its preparation job")
        config_path = unlinked_path(job / "config.toml")
        config, config_hash = _checked_config(config_path)
        if config_hash != state["config_sha256"] or config != _config(state["settings"]):
            raise ValueError("Saved configuration differs from the preparation job settings")
        selected_run = None
        for stage in ("inventory", "similarity"):
            record = state["stages"].get(stage, {})
            if record.get("status") != "completed":
                raise ValueError(f"The selected job has no completed {stage} checkpoint")
            checked = _inspect_attempt(job, state, stage, record, verify=True)
            if checked["integrity"] != "verified":
                message = (checked.get("error") or {}).get("message", "checkpoint is unavailable")
                raise ValueError(f"Cannot use the selected {stage} checkpoint: {message}")
            if stage == "similarity":
                selected_run = unlinked_path(Path(checked["output"]))
        if (
            read_metadata_bytes(workspace / "collection.json") != binding_before
            or read_metadata_bytes(job / "job.json") != job_before
        ):
            raise ValueError("Preparation selection changed while reading; inspect again")
        identity = {
            "kind": "collection" if entry else "workspace",
            "workspace": str(workspace),
            "job_id": state["job_id"],
            "job_sha256": hashlib.sha256(job_before).hexdigest(),
            "binding_sha256": hashlib.sha256(binding_before).hexdigest(),
            "config": str(config_path),
            "config_sha256": config_hash,
        }
        if entry:
            identity["collection"] = entry
    run_raw = read_metadata_bytes(selected_run / "run.json")
    run_meta = json.loads(run_raw)
    if (
        not isinstance(run_meta, dict)
        or run_meta.get("stage") != "similarity"
        or not isinstance(run_meta.get("inventory_run"), str)
        or not Path(run_meta["inventory_run"]).is_absolute()
    ):
        raise ValueError(
            "Review selection requires a similarity run with an absolute inventory reference"
        )
    inventory = unlinked_path(Path(run_meta["inventory_run"]))
    inventory_raw = read_metadata_bytes(inventory / "run.json")
    inventory_meta = json.loads(inventory_raw)
    if (
        not isinstance(inventory_meta, dict)
        or not isinstance(inventory_meta.get("source"), str)
        or not Path(inventory_meta["source"]).is_absolute()
        or path_key(inventory_meta["source"]) != path_key(config.source)
    ):
        raise ValueError("Configuration source differs from the inventory source")
    unlinked_path(Path(inventory_meta["source"]))
    for name in ("manifest.jsonl",):
        unlinked_path(inventory / name)
    identity.update(
        run=str(selected_run),
        run_sha256=hashlib.sha256(run_raw).hexdigest(),
        inventory=str(inventory),
        inventory_sha256=hashlib.sha256(inventory_raw).hexdigest(),
        source=str(config.source),
        reviews=str(config.reviews),
    )
    return Selection(config, selected_run, identity, state)


def select_report(selected: Selection, report: Path | None = None) -> Path:
    """Select an explicit report or the exact checked QA checkpoint of this job."""
    if report is not None:
        return unlinked_path(report)
    if selected.state is None:
        raise ValueError("Explicit --run changes require --report with the exact QA report")
    from image_dataset_train.preparation import _inspect_attempt, _verify_input_identity

    workspace = Path(selected.identity["workspace"])
    job = unlinked_path(workspace / "jobs" / selected.state["job_id"])
    record = selected.state["stages"].get("qa", {})
    if record.get("status") != "completed":
        raise ValueError("The selected job has no completed QA checkpoint; supply --report")
    paths = {
        job / "job.json": selected.identity["job_sha256"],
        workspace / "collection.json": selected.identity["binding_sha256"],
    }

    def unchanged():
        if any(
            hashlib.sha256(read_metadata_bytes(path)).hexdigest() != digest
            for path, digest in paths.items()
        ):
            raise ValueError("Preparation selection changed while selecting its QA report")

    unchanged()
    # Check exact attempt ownership without hashing its preview media/report assets.
    # Only the metadata used by review comparison must match the saved checkpoint.
    checked = _inspect_attempt(job, selected.state, "qa", record, verify=False)
    if checked["integrity"] == "invalid" or not checked.get("output"):
        message = (checked.get("error") or {}).get("message", "QA checkpoint is unavailable")
        raise ValueError(f"Cannot use the selected QA checkpoint: {message}")
    result = unlinked_path(Path(checked["output"]))
    files = record.get("files")
    if not isinstance(files, dict):
        raise ValueError("The selected QA checkpoint has no metadata hashes")
    for name in ("run.json", "entries.jsonl", "summary.json", "coverage.json"):
        digest = hashlib.sha256(read_metadata_bytes(result / name)).hexdigest()
        if files.get(name) != digest:
            raise ValueError(f"Selected QA checkpoint metadata changed: {name}")
    _verify_input_identity(job, selected.state, "qa", result)
    unchanged()
    return result


def display(value) -> str:
    text = str(value)
    return "".join(
        f"\\x{ord(char):02x}" if ord(char) < 32 or 127 <= ord(char) < 160 else char for char in text
    )


def command(label, argv):
    from image_dataset_train.qa import _commands

    values = [str(value) for value in argv]
    return {"label": label, "argv": values, **_commands(values)}


def selection_args(selected: Selection) -> list[str]:
    identity = selected.identity
    if identity["kind"] == "run":
        return ["--run", identity["run"], "--config", identity["config"]]
    if identity["kind"] == "collection":
        arguments = ["--collection", identity["collection"]["id"]]
    else:
        arguments = ["--workspace", identity["workspace"]]
    return [*arguments, "--job", identity["job_id"]]


def refresh_command(selected: Selection, *, identity_provider=None) -> dict:
    identity, state = selected.identity, selected.state
    if state is None:
        return command(
            "Publish fresh reviewed groups; existing exports remain unchanged",
            ["dataset", "groups", "--run", identity["run"], "--config", identity["config"]],
        )
    if state["implementation"] == (identity_provider or implementation_identity)():
        return command(
            "Refresh saved reviews and prepare a new publication",
            [
                "dataset",
                "resume",
                identity["workspace"],
                "--job",
                identity["job_id"],
                "--refresh-reviews",
            ],
        )
    options = state["options"]
    argv = [
        "dataset",
        "prepare",
        state["source"],
        "--workspace",
        identity["workspace"],
        "--config",
        identity["config"],
        "--captions",
        options["captions"],
        "--max-distance",
        str(options["max_distance"]),
        "--sample-size",
        str(options["sample_size"]),
        "--new",
    ]
    if options["offline"]:
        argv.append("--offline")
    return command("Saved job uses a different build; prepare a new job with its settings", argv)
