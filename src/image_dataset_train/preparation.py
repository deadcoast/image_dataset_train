"""Durable directory-to-dataset jobs composed from the existing stage APIs."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout

from image_dataset_train import __version__
from image_dataset_train.config import (
    CaptionConfig,
    Config,
    ExportConfig,
    TaggingConfig,
    ValidationConfig,
)
from image_dataset_train.diagnostics import atomic_json, diagnose
from image_dataset_train.exporting import _path
from image_dataset_train.implementation import implementation_identity as _implementation_identity
from image_dataset_train.implementation import validate_implementation_identity
from image_dataset_train.inventory import _walk, file_sha256, scan, summarize
from image_dataset_train.inventory_data import read_inventory
from image_dataset_train.model_bundle import MODELS
from image_dataset_train.preparation_policy import POLICY

STAGES = ("inventory", "similarity", "tagging", "groups", "policy", "export", "qa")
PATH_SETTINGS = ("source", "runs", "models", "scores", "reviews", "exports")


class PreparationRecoveryError(ValueError):
    """A retained job requires a specific operation before it can continue."""

    def __init__(self, message: str, action: str):
        super().__init__(message)
        self.action = action


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _settings(config: Config) -> dict:
    value = asdict(config)
    for key in PATH_SETTINGS:
        value[key] = str(getattr(config, key).resolve())
    return value


def _config(value: dict) -> Config:
    return Config(
        **{key: Path(value[key]) for key in PATH_SETTINGS},
        validation=ValidationConfig(**value["validation"]),
        tagging=TaggingConfig(**value["tagging"]),
        captions=CaptionConfig(**value["captions"]),
        export=ExportConfig(**value["export"]),
    )


def preparation_config(source: Path, workspace: Path, *, base: Config | None = None) -> Config:
    """Use local defaults without requiring a repository or a config file."""
    from image_dataset_train.diagnostics import app_home

    source = source.expanduser().resolve(strict=True)
    workspace = workspace.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("Preparation source must be a directory")
    if source.is_relative_to(workspace) or workspace.is_relative_to(source):
        raise ValueError("Source and preparation workspace must be separate directory trees")
    base = base or Config(
        source=source,
        runs=workspace / "runs",
        validation=ValidationConfig(),
        models=app_home() / "models",
        scores=app_home() / "scores",
        reviews=workspace / "reviews",
        exports=workspace / "exports",
    )
    config = replace(
        base,
        source=source,
        runs=workspace / "runs",
        exports=workspace / "exports",
        tagging=replace(
            base.tagging,
            revision=base.tagging.revision or MODELS[base.tagging.model].revision,
        ),
    )
    for name in PATH_SETTINGS[1:]:
        destination = getattr(config, name).resolve()
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError(f"Source and {name} directories must be separate trees")
    return config


def default_workspace(source: Path) -> Path:
    from image_dataset_train.diagnostics import app_home

    source = source.expanduser().resolve(strict=True)
    identity = sha256(os.path.normcase(str(source)).encode()).hexdigest()[:16]
    return app_home() / "collections" / identity


def _write_config(path: Path, config: Config) -> None:
    """Save a complete strict TOML config for existing review and stage commands."""
    value = _settings(config)
    lines = ["schema_version = 1", "", "[paths]"]
    lines += [f"{key} = {json.dumps(value[key], ensure_ascii=False)}" for key in PATH_SETTINGS]
    for section in ("validation", "tagging", "export", "captions"):
        lines.extend(("", f"[{section}]"))
        for key, item in value[section].items():
            if item is None or isinstance(item, dict) or key == "subset_rules":
                continue
            lines.append(f"{key} = {json.dumps(item, ensure_ascii=False)}")
    lines.extend(("", "[captions.tag_thresholds]"))
    for key, item in config.captions.tag_thresholds.items():
        lines.append(f"{json.dumps(key, ensure_ascii=False)} = {item}")
    for rule in config.captions.subset_rules:
        lines.extend(("", "[[captions.subset_rules]]"))
        lines += [
            f"{key} = {json.dumps(item, ensure_ascii=False)}" for key, item in asdict(rule).items()
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _tree(root: Path) -> dict[str, str]:
    hashes = {}
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked preparation artifact: {path}")
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = file_sha256(path)
    return hashes


def _assert_sources(config: Config, inventory: Path) -> None:
    """Check membership and bytes, including sidecars, without decoding a second time."""
    _, rows, _ = read_inventory(inventory)
    expected = {row["source_path"]: row for row in rows}
    current = {p.relative_to(config.source).as_posix(): p for p in _walk(config.source)}
    if current.keys() != expected.keys():
        raise PreparationRecoveryError(
            "Source membership changed; start a new preparation job with --new", "new_job"
        )
    for name, path in current.items():
        row = expected[name]
        linked = path.is_symlink() or path.is_junction()
        if linked != (row["kind"] == "link"):
            raise PreparationRecoveryError(
                f"Source link state changed: {name}; start a new job with --new", "new_job"
            )
        if linked:
            continue
        before = path.stat()
        digest = file_sha256(path)
        after = path.stat()
        if digest != row["sha256"] or (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise PreparationRecoveryError(
                f"Source changed: {name}; start a new preparation job with --new", "new_job"
            )


def _job_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value) is None
    ):
        raise PreparationRecoveryError("Choose one exact preparation job ID", "inspect_artifacts")
    return value


def _binding(workspace: Path) -> dict:
    binding = json.loads(_path(workspace, "collection.json").read_text(encoding="utf-8"))
    if (
        not isinstance(binding, dict)
        or binding.get("schema_version") != 1
        or not isinstance(binding.get("job"), str)
        or not isinstance(binding.get("source"), str)
        or not Path(binding["source"]).is_absolute()
    ):
        raise PreparationRecoveryError(
            "Invalid preparation collection record; preserve it before recovery",
            "inspect_artifacts",
        )
    parts = binding["job"].split("/")
    if len(parts) != 2 or parts[0] != "jobs":
        raise PreparationRecoveryError("Invalid preparation job binding", "inspect_artifacts")
    _job_id(parts[1])
    return binding


def read_preparation_job(workspace: Path, *, job_id: str | None = None) -> tuple[Path, dict]:
    """Read the current or one exact historical job without rebinding the collection."""
    workspace = workspace.expanduser().absolute()
    _path(workspace, "collection.json")  # Reject linked workspace roots before resolving them.
    workspace = workspace.resolve(strict=True)
    binding = _binding(workspace)
    selected = _job_id(job_id) if job_id is not None else binding["job"].split("/")[1]
    job = _path(workspace, f"jobs/{selected}")
    state = json.loads(_path(job, "job.json").read_text(encoding="utf-8"))
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or state.get("policy") != POLICY
        or state.get("settings_sha256") != _digest(state.get("settings"))
        or state.get("source") != binding.get("source")
        or state.get("workspace") != str(workspace)
        or state.get("job_id") != selected
        or state.get("options_sha256") != _digest(state.get("options"))
        or not isinstance(state.get("stages"), dict)
        or not isinstance(state.get("history"), list)
        or not isinstance(state.get("prior_attempts", []), list)
        or state.get("config_sha256") != file_sha256(_path(job, "config.toml"))
    ):
        raise PreparationRecoveryError(
            "Invalid or altered preparation job contract; preserve it before recovery",
            "inspect_artifacts",
        )
    try:
        implementation = state["implementation"]
        if isinstance(implementation, dict) and "schema_version" in implementation:
            validate_implementation_identity(implementation)
        elif (
            not isinstance(implementation, dict)
            or set(implementation) != {"version", "payload_sha256", "files"}
            or not isinstance(implementation["files"], dict)
            or implementation["payload_sha256"] != _digest(implementation["files"])
        ):
            # Initial product-phase jobs used this unversioned audit shape.
            raise ValueError("Invalid preparation implementation identity")
        if (
            state["status"]
            not in {"planned", "running", "failed", "cancelled", "needs_review", "completed"}
            or not isinstance(state["job_id"], str)
            or state["human_accepted"] is not False
            or state["options"]["captions"] not in {"model", "existing"}
            or type(state["options"]["offline"]) is not bool
            or type(state["options"]["max_distance"]) is not int
            or not 0 <= state["options"]["max_distance"] <= 64
            or type(state["options"]["sample_size"]) is not int
            or state["options"]["sample_size"] < 1
            or str(_config(state["settings"]).source) != state["source"]
        ):
            raise ValueError("Invalid preparation settings or job status")
        for stage, record in state["stages"].items():
            if (
                stage not in {*STAGES, "review_qa"}
                or record["status"] not in {"running", "completed"}
                or not isinstance(record["attempt"], str)
                or (
                    record["status"] == "completed"
                    and (
                        not isinstance(record["output"], str)
                        or not isinstance(record["files"], dict)
                        or not isinstance(record["summary"], dict)
                    )
                )
            ):
                raise ValueError("Invalid preparation stage checkpoint")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise PreparationRecoveryError(
            "Invalid or altered preparation job contract; preserve it before recovery",
            "inspect_artifacts",
        ) from exc
    return job, state


def _read_state(workspace: Path) -> tuple[Path, dict]:
    return read_preparation_job(workspace)


def _save(job: Path, state: dict, event: str, **values) -> None:
    state["updated_at"] = _now()
    state["history"].append({"at": state["updated_at"], "event": event, **values})
    atomic_json(job / "job.json", state)


def _output(job: Path, state: dict, stage: str) -> Path:
    return _path(job, state["stages"][stage]["output"])


def _verify_stage(stage: str, path: Path) -> dict:
    """Perform stage-specific integrity checks before checkpointing or reusing it."""
    from image_dataset_train.exporting import _load_groups, verify_export
    from image_dataset_train.qa import read_qa
    from image_dataset_train.reviews import load_context

    if stage == "inventory":
        read_inventory(path)
    elif stage == "similarity":
        load_context(path, require_source=False)
    elif stage == "tagging":
        from image_dataset_train.scored_runs import ScoredRun

        scored = ScoredRun(path)
        for digest in scored.index:
            scored.vector(digest)
    elif stage in {"groups", "policy"}:
        _load_groups(path, require_reviewed=False)
    elif stage == "export":
        verify_export(path)
    elif stage in {"qa", "review_qa"}:
        read_qa(path)
    else:
        raise ValueError(f"Unsupported preparation stage: {stage}")
    meta = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if meta["status"] != "completed":
        raise ValueError(f"{stage} completed with errors; inspect its retained report before retry")
    return json.loads((path / "summary.json").read_text(encoding="utf-8"))


def _execute(stage: str, config: Config, job: Path, state: dict, progress: Callable) -> Path:
    from image_dataset_train.exporting import export_dataset
    from image_dataset_train.preparation_policy import prepare_groups
    from image_dataset_train.qa import create_qa
    from image_dataset_train.reviews import publish_groups
    from image_dataset_train.runs import run_scan
    from image_dataset_train.similarity import propose_similar

    def output(name):
        return _output(job, state, name)

    options = state["options"]
    captions = (
        output("tagging")
        if state["stages"].get("tagging", {}).get("status") == "completed"
        else None
    )
    if stage == "inventory":
        return run_scan(
            config, lambda n: progress(f"Inspected {n} files") if n % 100 == 0 else None
        )[0]
    if stage == "similarity":
        return propose_similar(
            config, output("inventory"), max_distance=options["max_distance"], progress=progress
        )[0]
    if stage == "tagging":
        from image_dataset_train.model_bundle import bundle_path, fetch_bundle, load_bundle
        from image_dataset_train.tagging import tag_inventory

        bundle = bundle_path(config.models, config.tagging.model, config.tagging.revision)
        if not (bundle / "model.json").is_file():
            if options["offline"]:
                raise PreparationRecoveryError(
                    f"Pinned model is unavailable offline: {bundle}. "
                    "Fetch that model before resuming this job.",
                    "fetch_model",
                )
            progress("Obtaining the pinned local tagging model")
            fetch_bundle(config.models, config.tagging.model, config.tagging.revision)
        identity = load_bundle(
            bundle, model=config.tagging.model, revision=config.tagging.revision
        ).metadata
        if state.get("model_identity") is not None and state["model_identity"] != identity:
            raise PreparationRecoveryError(
                "Pinned model identity changed; start a new preparation job", "new_job"
            )
        state["model_identity"] = identity
        _save(job, state, "model_verified", artifact_id=identity["artifact_id"])
        return tag_inventory(config, output("inventory"), progress, repair_cache=True)[0]
    if stage == "groups":
        return publish_groups(config, output("similarity"))[0]
    if stage == "policy":
        return prepare_groups(config, output("groups"), captions_run=captions)[0]
    if stage == "export":
        return export_dataset(
            config, output("policy"), captions_run=captions, progress=progress, allow_prepared=True
        )[0]
    if stage in {"qa", "review_qa"}:
        is_export = stage == "qa"
        return create_qa(
            config,
            output("export" if is_export else "policy"),
            captions_run=None if is_export else captions,
            sample_size=options["sample_size"],
            config_path=job / "config.toml",
        )[0]
    raise ValueError(f"Unsupported preparation stage: {stage}")


def _verify_input_identity(job: Path, state: dict, stage: str, path: Path) -> None:
    try:
        _assert_input_identity(job, state, stage, path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PreparationRecoveryError(str(exc), "inspect_artifacts") from exc


def _assert_input_identity(job: Path, state: dict, stage: str, path: Path) -> None:
    """A valid artifact must also be the output of this exact frozen job/input."""
    meta = json.loads(_path(path, "run.json").read_text(encoding="utf-8"))
    expected_stage = {"policy": "groups", "review_qa": "qa"}.get(stage, stage)
    if meta.get("stage") != expected_stage or meta.get("source") != state["source"]:
        raise ValueError(f"Recovered {stage} source/stage identity differs from this job")
    settings = state["settings"]

    def output(name):
        return _output(job, state, name)

    if stage == "inventory":
        if meta.get("validation") != settings["validation"]:
            raise ValueError("Recovered inventory validation settings differ from this job")
        return
    inventory_meta = json.loads((output("inventory") / "run.json").read_text(encoding="utf-8"))
    if stage in {"similarity", "tagging", "groups", "policy"}:
        if meta.get("inventory_manifest_sha256") != inventory_meta["manifest_sha256"] or meta.get(
            "inventory_run"
        ) != str(output("inventory")):
            raise ValueError(f"Recovered {stage} inventory input differs from this job")
    if stage == "similarity" and (
        meta.get("max_hamming_distance") != state["options"]["max_distance"]
        or meta.get("validation") != settings["validation"]
    ):
        raise ValueError("Recovered similarity settings differ from this job")
    if stage == "tagging":
        from image_dataset_train.model_bundle import check_model_binding

        model_identity = state.get("model_identity")
        if model_identity is None:
            # Compatibility for initial product-phase jobs predating this checkpoint field.
            from image_dataset_train.model_bundle import bundle_path, load_bundle

            config = _config(settings)
            model_identity = load_bundle(
                bundle_path(config.models, config.tagging.model, config.tagging.revision),
                model=config.tagging.model,
                revision=config.tagging.revision,
            ).metadata
        check_model_binding(
            model_identity, settings["tagging"]["model"], settings["tagging"].get("revision")
        )
        if (
            meta.get("model") != model_identity
            or meta.get("caption_rules") != settings["captions"]
            or meta.get("requested_device") != settings["tagging"]["device"]
            or meta.get("validation") != settings["validation"]
        ):
            raise ValueError("Recovered tagging model/rule input differs from this job")
    if stage in {"groups", "policy"} and (
        meta.get("similarity_run") != str(output("similarity"))
        or meta.get("review_revision") != state["review_revision"]
    ):
        raise ValueError(f"Recovered {stage} review/input identity differs from this job")
    captions = (
        str(output("tagging"))
        if state["stages"].get("tagging", {}).get("status") == "completed"
        else None
    )
    if stage == "policy":
        policy = json.loads(_path(path, "preparation.json").read_text(encoding="utf-8"))
        if (
            policy.get("base_groups_run") != str(output("groups"))
            or policy.get("base_groups_sha256") != state["stages"]["groups"]["files"]["run.json"]
            or policy.get("caption_run") != captions
        ):
            raise ValueError("Recovered policy inputs differ from this job")
    if stage == "export" and (
        meta.get("groups_run") != str(output("policy"))
        or meta.get("caption_run") != captions
        or meta.get("preparation_policy") != POLICY
    ):
        raise ValueError("Recovered export inputs differ from this job")
    if stage in {"qa", "review_qa"}:
        dependency = "export" if stage == "qa" else "policy"
        if (
            meta.get("input_run") != str(output(dependency))
            or meta.get("input_run_sha256") != state["stages"][dependency]["files"]["run.json"]
            or meta.get("config_path") != str(job / "config.toml")
        ):
            raise ValueError("Recovered QA inputs differ from this job")


def _checkpoint(job: Path, state: dict, stage: str, path: Path, *, recovered: bool) -> None:
    _verify_input_identity(job, state, stage, path)
    summary = _verify_stage(stage, path)
    record = state["stages"][stage]
    record.update(
        status="completed",
        output=path.relative_to(job).as_posix(),
        files=_tree(path),
        summary=summary,
        completed_at=_now(),
    )
    _save(job, state, "stage_recovered" if recovered else "stage_completed", stage=stage)


def _attempt_contents(job: Path, stage: str, record: dict) -> tuple[Path, list[Path], list[Path]]:
    relative = record["attempt"]
    if (
        not isinstance(relative, str)
        or len(relative.split("/")) != 2
        or not relative.startswith(f"attempts/{stage}-")
    ):
        raise ValueError(f"Invalid retained {stage} attempt ownership")
    attempt = _path(job, relative)
    published, pending = [], []
    for name in ("runs", "exports"):
        root = _path(attempt, name)
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            path = _path(root, entry.name)
            if path.is_dir():
                (pending if path.name.startswith(".pending-") else published).append(path)
    return attempt, published, pending


def _candidate_metadata(stage: str, path: Path) -> dict:
    meta = json.loads(_path(path, "run.json").read_text(encoding="utf-8"))
    if (
        not isinstance(meta, dict)
        or meta.get("stage") != {"policy": "groups", "review_qa": "qa"}.get(stage, stage)
        or meta.get("status") not in {"completed", "completed_with_errors", "failed", "cancelled"}
    ):
        raise ValueError(f"Invalid retained {stage} publication metadata: {path}")
    return meta


def _stage(job: Path, state: dict, stage: str, config: Config, progress: Callable) -> None:
    existing = state["stages"].get(stage)
    if existing and existing.get("status") == "completed":
        try:
            path = _output(job, state, stage)
            if _tree(path) != existing["files"]:
                raise ValueError(f"Completed {stage} artifacts changed: {path}")
            _verify_input_identity(job, state, stage, path)
            _verify_stage(stage, path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PreparationRecoveryError(str(exc), "inspect_artifacts") from exc
        progress(f"Reusing verified {stage}")
        return
    if existing:
        # Each attempt owns its output root; no global 'latest run' discovery.
        try:
            attempt, outputs, _ = _attempt_contents(job, stage, existing)
            if len(outputs) > 1:
                raise ValueError(f"Ambiguous {stage} attempt outputs; inspect {attempt}")
            recoverable = (
                outputs and _candidate_metadata(stage, outputs[0])["status"] == "completed"
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PreparationRecoveryError(str(exc), "inspect_artifacts") from exc
        if recoverable:
            _checkpoint(job, state, stage, outputs[0], recovered=True)
            progress(f"Recovered published {stage} after interruption")
            return
    attempt_name = f"attempts/{stage}-{uuid4().hex[:12]}"
    attempt = _path(job, attempt_name)
    attempt.mkdir(parents=True)
    if existing:
        state.setdefault("prior_attempts", []).append({"stage": stage, **existing})
    state["stages"][stage] = {"status": "running", "attempt": attempt_name, "started_at": _now()}
    state["current_stage"] = stage
    _save(job, state, "stage_started", stage=stage, attempt=attempt_name)
    scoped = replace(config, runs=attempt / "runs", exports=attempt / "exports")
    progress(f"Preparing: {stage}")
    path = _execute(stage, scoped, job, state, progress)
    _checkpoint(job, state, stage, path, recovered=False)


def _review_revision(config: Config) -> int:
    from image_dataset_train.reviews import ReviewStore

    return ReviewStore(config.reviews, config.source).read()["revision"]


def _continue(job: Path, state: dict, *, refresh_reviews: bool, progress: Callable) -> dict:
    config = _config(state["settings"])
    if (state["status"] != "completed" or refresh_reviews) and state.get(
        "implementation"
    ) != _implementation_identity():
        raise PreparationRecoveryError(
            "Application implementation changed since this job began; start a new "
            "preparation with --new, or restore the recorded build before resuming",
            "new_job",
        )
    if refresh_reviews:
        for stage in ("groups", "policy", "export", "qa", "review_qa"):
            if stage in state["stages"]:
                state.setdefault("prior_attempts", []).append(
                    {
                        "stage": stage,
                        "superseded_by_review_refresh": True,
                        **state["stages"].pop(stage),
                    }
                )
        state.pop("review_revision", None)
        _save(job, state, "review_refresh_requested")
    state.update(status="running", error=None, next_action=None)
    _save(job, state, "continuation_started")
    try:
        for stage in STAGES:
            if stage == "tagging" and state["options"]["captions"] == "existing":
                continue
            state["current_stage"] = stage
            if stage == "similarity":
                _assert_sources(config, _output(job, state, "inventory"))
            if stage == "groups":
                current_revision = _review_revision(config)
                if state.get("review_revision", current_revision) != current_revision:
                    raise PreparationRecoveryError(
                        "Reviews changed; resume with --refresh-reviews to republish",
                        "refresh_reviews",
                    )
                state["review_revision"] = current_revision
            if stage == "export":
                _assert_sources(config, _output(job, state, "inventory"))
                if _review_revision(config) != state["review_revision"]:
                    raise PreparationRecoveryError(
                        "Reviews changed; resume with --refresh-reviews to republish",
                        "refresh_reviews",
                    )
                policy_summary = state["stages"]["policy"]["summary"]
                if not policy_summary["preparation_complete"]:
                    _stage(job, state, "review_qa", config, progress)
                    state.update(status="needs_review", next_action="review_then_resume")
                    _save(job, state, "review_required", blockers=policy_summary["blockers"])
                    return inspect_preparation(Path(state["workspace"]))
            _stage(job, state, stage, config, progress)
        _assert_sources(config, _output(job, state, "inventory"))
        state.update(status="completed", current_stage=None, completed_at=_now())
        _save(job, state, "preparation_completed")
    except BaseException as exc:
        state["status"] = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
        state["error"] = {"type": type(exc).__name__, "message": str(exc), **asdict(diagnose(exc))}
        state["next_action"] = getattr(exc, "action", "resume")
        _save(job, state, state["status"], stage=state.get("current_stage"))
        raise
    return inspect_preparation(Path(state["workspace"]))


def preview_preparation(config: Config, *, captions: str = "model") -> dict:
    """Read-only, offline source inspection; no model or report/cache writes."""
    records = scan(config.source, config.validation)
    return {
        "dry_run": True,
        "source": str(config.source),
        "intake": summarize(records),
        "policy": POLICY,
        "caption_mode": captions,
        "model": config.tagging.model if captions == "model" else None,
        "settings": _settings(config),
        "source_files_changed": False,
        "inference_performed": False,
        "caption_accuracy_established": False,
    }


def prepare_directory(
    config: Config,
    workspace: Path,
    *,
    captions: str = "model",
    offline: bool = False,
    max_distance: int = 8,
    sample_size: int = 50,
    new: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    workspace = workspace.expanduser().resolve()
    config = preparation_config(config.source, workspace, base=config)
    if captions not in {"model", "existing"} or type(offline) is not bool:
        raise ValueError("Choose model or existing captions and a boolean offline option")
    if type(max_distance) is not int or not 0 <= max_distance <= 64:
        raise ValueError("Similarity distance must be an integer between 0 and 64")
    if type(sample_size) is not int or sample_size < 1:
        raise ValueError("QA sample size must be a positive integer")
    options = dict(
        captions=captions, offline=offline, max_distance=max_distance, sample_size=sample_size
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(_path(workspace, "prepare.lock")), timeout=0):
            if (workspace / "collection.json").exists():
                job, state = _read_state(workspace)
                if state["source"] != str(config.source):
                    raise PreparationRecoveryError(
                        "This workspace belongs to another source directory; "
                        "choose a different workspace",
                        "correct_arguments",
                    )
                if not new:
                    if state["settings_sha256"] != _digest(_settings(config)) or state[
                        "options_sha256"
                    ] != _digest(options):
                        raise PreparationRecoveryError(
                            "Preparation settings changed; use --new for a new job", "new_job"
                        )
                    return _continue(job, state, refresh_reviews=False, progress=progress or print)
            job_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
            job = _path(workspace, f"jobs/{job_id}")
            job.mkdir(parents=True)
            settings = _settings(config)
            state = {
                "schema_version": 1,
                "job_id": job_id,
                "workspace": str(workspace),
                "source": str(config.source),
                "policy": POLICY,
                "pipeline_version": __version__,
                "created_at": _now(),
                "status": "planned",
                "settings": settings,
                "settings_sha256": _digest(settings),
                "options": options,
                "options_sha256": _digest(options),
                "stages": {},
                "history": [],
                "human_accepted": False,
            }
            _write_config(job / "config.toml", config)
            state["config_sha256"] = file_sha256(job / "config.toml")
            state["implementation"] = _implementation_identity()
            _save(job, state, "job_created")
            atomic_json(
                workspace / "collection.json",
                {
                    "schema_version": 1,
                    "source": str(config.source),
                    "job": f"jobs/{job_id}",
                },
            )
            return _continue(job, state, refresh_reviews=False, progress=progress or print)
    except Timeout as exc:
        raise ValueError(
            "Another preparation is using this workspace; inspect dataset status"
        ) from exc


def resume_preparation(
    workspace: Path,
    *,
    refresh_reviews: bool = False,
    expected_job_id: str | None = None,
    expected_source: Path | None = None,
    progress: Callable | None = None,
) -> dict:
    workspace = workspace.expanduser().resolve(strict=True)
    try:
        with FileLock(str(_path(workspace, "prepare.lock")), timeout=0):
            job, state = _read_state(workspace)
            if expected_source is not None and Path(state["source"]) != expected_source.resolve():
                raise PreparationRecoveryError(
                    "Registered collection source differs from the preparation job",
                    "correct_arguments",
                )
            if expected_job_id is not None and _job_id(expected_job_id) != state["job_id"]:
                raise PreparationRecoveryError(
                    f"Current preparation job is {state['job_id']}, not {expected_job_id}; "
                    "inspect the current job before choosing a continuation",
                    "select_current_job",
                )
            return _continue(
                job, state, refresh_reviews=refresh_reviews, progress=progress or print
            )
    except Timeout as exc:
        raise ValueError(
            "Another preparation is using this workspace; inspect dataset status"
        ) from exc


def job_status(workspace: Path, *, verify: bool = False) -> dict:
    job, state = _read_state(workspace)
    outputs = {}
    for stage, item in state["stages"].items():
        if item["status"] != "completed":
            continue
        path = _output(job, state, stage)
        if verify:
            if _tree(path) != item["files"]:
                raise ValueError(f"Completed {stage} artifacts changed")
            _verify_input_identity(job, state, stage, path)
            _verify_stage(stage, path)
        outputs[stage] = {"path": str(path), "summary": item["summary"]}
    return _status_result(job, state, outputs, verify=verify)


def _status_result(job: Path, state: dict, outputs: dict, *, verify: bool) -> dict:
    return {
        "workspace": state["workspace"],
        "job": str(job),
        "job_id": state["job_id"],
        "source": state["source"],
        "status": state["status"],
        "policy": state["policy"],
        "current_stage": state.get("current_stage"),
        "error": state.get("error"),
        "next_action": state.get("next_action"),
        "options": state["options"],
        "outputs": outputs,
        "config": str(job / "config.toml"),
        "artifact_verification": "full" if verify else "not_rechecked",
        "source_revalidated": False,
        "human_accepted": False,
        "prepared": state["status"] == "completed",
        "updated_at": state["updated_at"],
    }


def _inspect_attempt(job: Path, state: dict, stage: str, record: dict, *, verify: bool) -> dict:
    """Describe only an owned attempt; never checkpoint, repair, or infer from status."""
    view = {
        "stage": stage,
        "status": record.get("status"),
        "integrity": "not_rechecked",
        "attempt": None,
        "published_outputs": [],
        "pending_outputs": [],
        "continuation": "retry_inference" if stage == "tagging" else "retry_stage",
        "error": None,
    }
    if record.get("status") == "running":
        view["checkpoint_status"] = "running"
        view["status"] = (
            state["status"]
            if state.get("current_stage") == stage and state["status"] in {"failed", "cancelled"}
            else "uncheckpointed"
        )
    try:
        attempt, published, pending = _attempt_contents(job, stage, record)
        view["attempt"] = str(attempt)
        view["pending_outputs"] = [str(path) for path in pending]
        # Preserve every candidate location even if one record cannot be read.
        view["published_outputs"] = [{"path": str(path)} for path in published]
        if record["status"] == "completed":
            output = _path(job, record["output"])
            if not output.is_relative_to(attempt) or output.parent.name not in {"runs", "exports"}:
                raise ValueError(f"Completed {stage} output is outside its recorded attempt")
            view["output"] = str(output)
            view["continuation"] = "reuse_checkpoint"
            if verify:
                if _tree(output) != record["files"]:
                    raise ValueError(f"Completed {stage} artifacts changed: {output}")
                _verify_input_identity(job, state, stage, output)
                _verify_stage(stage, output)
                view["integrity"] = "verified"
            return view
        if len(published) > 1:
            raise ValueError(f"Ambiguous {stage} attempt outputs; inspect {attempt}")
        if published:
            path = published[0]
            metadata = _candidate_metadata(stage, path)
            candidate = view["published_outputs"][0]
            candidate["status"] = metadata["status"]
            candidate["integrity"] = "not_rechecked"
            if isinstance(metadata.get("counts"), dict):
                candidate["reported_counts"] = metadata["counts"]
            if metadata["status"] == "completed":
                view["continuation"] = "verify_then_recover_publication"
                if verify:
                    _verify_input_identity(job, state, stage, path)
                    _verify_stage(stage, path)
                    candidate["integrity"] = view["integrity"] = "verified"
                    view["continuation"] = "recover_publication"
            elif stage == "tagging" and metadata["status"] == "completed_with_errors" and verify:
                from image_dataset_train.scored_runs import ScoredRun

                _verify_input_identity(job, state, stage, path)
                scored = ScoredRun(path)
                for digest in scored.index:
                    scored.vector(digest)
                candidate["integrity"] = "verified_partial"
                candidate["verified_retained_score_vectors"] = len(scored.index)
                # A retained score vector is not proof that a future runtime can reuse its cache.
                candidate["inference_cache_reuse"] = "validated_during_resume"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        view.update(
            integrity="invalid",
            continuation="inspect_artifacts",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    return view


def _inspect_preparation_cache(job: Path, state: dict, *, current_id: str) -> dict:
    """Inspect a live cache separately from the saved dataset's artifact integrity."""
    result = {
        "status": "not_applicable",
        "counts": None,
        "inventory_verification": "not_rechecked",
        "source_verification": {"status": "not_rechecked"},
        "implementation_match": None,
        "is_current_job": state["job_id"] == current_id,
        "cache_relevant_for_resume": False,
        "tagging_continuation": "none",
        "continuation_constraints": [],
        "has_diagnostics": False,
        "inference_performed": False,
        "application_writes": False,
    }
    if state["options"]["captions"] == "existing":
        result["reason"] = "existing_captions"
        return result

    result["cache_relevant_for_resume"] = (
        state["stages"].get("tagging", {}).get("status") != "completed"
    )
    result["tagging_continuation"] = (
        "retry_inference" if result["cache_relevant_for_resume"] else "reuse_checkpoint"
    )
    constraints = result["continuation_constraints"]
    if not result["is_current_job"]:
        constraints.append("historical_job")
    try:
        result["implementation_match"] = state["implementation"] == _implementation_identity()
    except (OSError, ValueError) as exc:
        result["implementation_error"] = {"type": type(exc).__name__, "message": str(exc)}
    if result["implementation_match"] is not True and state["status"] != "completed":
        constraints.append("implementation_changed_or_unavailable")

    record = state["stages"].get("inventory", {})
    if record.get("status") != "completed":
        result.update(
            status="unavailable", reason="inventory_not_checkpointed", has_diagnostics=True
        )
        return result
    checked = _inspect_attempt(job, state, "inventory", record, verify=True)
    result["inventory_verification"] = checked["integrity"]
    if checked["integrity"] != "verified":
        result.update(
            status="unavailable",
            reason="inventory_invalid",
            error=checked["error"],
            has_diagnostics=True,
        )
        constraints.append("inventory_invalid")
        return result

    config = _config(state["settings"])
    inventory = Path(checked["output"])
    tagging_record = state["stages"].get("tagging")
    if tagging_record and result["cache_relevant_for_resume"]:
        try:
            tagging = _inspect_attempt(job, state, "tagging", tagging_record, verify=True)
        except ImportError as exc:
            tagging = {
                "integrity": "unavailable",
                "continuation": "verify_then_recover_publication",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            constraints.append("tagging_verification_unavailable")
        result["tagging_continuation"] = tagging["continuation"]
        result["tagging_verification"] = {
            key: tagging[key] for key in ("integrity", "continuation", "error")
        }
        if tagging["continuation"] == "recover_publication":
            result["cache_relevant_for_resume"] = False
        elif tagging["integrity"] == "invalid":
            constraints.append("tagging_artifacts_invalid")
    try:
        if any(p.is_symlink() or p.is_junction() for p in (config.source, *config.source.parents)):
            source = {"status": "changed", "message": "Source path is now linked"}
        elif not config.source.exists():
            source = {"status": "offline", "message": "Source directory is unavailable"}
        elif not config.source.is_dir():
            source = {"status": "changed", "message": "Source is no longer a directory"}
        else:
            _assert_sources(config, inventory)
            source = {"status": "verified"}
    except PreparationRecoveryError as exc:
        source = {"status": "changed", "message": str(exc)}
    except (OSError, ValueError) as exc:
        source = {"status": "unavailable", "message": str(exc)}
    result["source_verification"] = source
    if source["status"] != "verified":
        constraints.append("source_" + source["status"])

    try:
        # Keep optional inference dependencies and native session initialization
        # out of ordinary status and artifact-only verification.
        from image_dataset_train.cache_inspection import inspect_inference_cache

        cache = inspect_inference_cache(
            config, inventory, expected_model=state.get("model_identity")
        )
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        cache = {
            "status": "unavailable",
            "reason": "cache_inspection_unavailable",
            "counts": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    result.update(cache)
    result["has_diagnostics"] = (
        result["status"] in {"partial", "unavailable"}
        or source["status"] != "verified"
        or "implementation_changed_or_unavailable" in constraints
        or "tagging_artifacts_invalid" in constraints
        or "tagging_verification_unavailable" in constraints
    )
    return result


def inspect_preparation(
    workspace: Path,
    *,
    job_id: str | None = None,
    verify: bool = False,
    verify_cache: bool = False,
) -> dict:
    """Read stage/attempt recovery evidence while preserving independent healthy checks."""
    job, state = read_preparation_job(workspace, job_id=job_id)
    current_id = _binding(Path(state["workspace"]))["job"].split("/")[1]
    outputs, stages, errors = {}, [], []
    names = [*STAGES, *(name for name in ("review_qa",) if name in state["stages"])]
    for name in names:
        record = state["stages"].get(name)
        if record is None:
            skipped = name == "tagging" and state["options"]["captions"] == "existing"
            stages.append(
                {
                    "stage": name,
                    "status": "skipped" if skipped else "not_started",
                    "integrity": "not_applicable",
                    "continuation": "none" if skipped else "run_stage",
                }
            )
            continue
        view = _inspect_attempt(job, state, name, record, verify=verify)
        stages.append(view)
        if view.get("output"):
            outputs[name] = {"path": view["output"], "summary": record["summary"]}
        if view["error"]:
            errors.append({"stage": name, "attempt": view["attempt"], **view["error"]})
    retained = []
    for record in state.get("prior_attempts", []):
        if not isinstance(record, dict) or record.get("stage") not in {*STAGES, "review_qa"}:
            retained.append({"integrity": "invalid", "error": "Invalid retained attempt record"})
            continue
        view = _inspect_attempt(job, state, record["stage"], record, verify=False)
        view["superseded_by_review_refresh"] = record.get("superseded_by_review_refresh", False)
        view["continuation"] = "retained_only"
        retained.append(view)
    result = _status_result(job, state, outputs, verify=verify)
    action = "inspect_artifacts" if errors else state.get("next_action")
    if state["job_id"] != current_id:
        action = "select_current_job"
    if errors:
        result.update(prepared=False, artifact_verification="failed")
    result.update(
        stages=stages,
        retained_attempts=retained,
        verification_errors=errors,
        next_action=action,
        is_current_job=state["job_id"] == current_id,
        current_job_id=current_id,
        recovery={
            "action": action,
            "remaining_stages": [
                v["stage"] for v in stages if v["status"] not in {"completed", "skipped"}
            ],
            "retained_attempts": len(retained),
            "running_state": "recorded state; live process ownership is not inferred",
            "cache_progress": (
                "Retained score counts describe saved reports; "
                "live cache reuse is checked on resume."
            ),
        },
    )
    if verify_cache:
        cache = _inspect_preparation_cache(job, state, current_id=current_id)
        result["cache_verification"] = cache
        result["source_revalidated"] = cache["source_verification"]["status"] == "verified"
        constraints = cache["continuation_constraints"]
        # These are continuation constraints, not failures of the prepared export.
        if action not in {"inspect_artifacts", "select_current_job"}:
            if "inventory_invalid" in constraints or "tagging_artifacts_invalid" in constraints:
                action = "inspect_artifacts"
            elif (
                "source_changed" in constraints
                or "implementation_changed_or_unavailable" in constraints
                or (
                    cache.get("reason") == "model_identity_changed"
                    and cache["cache_relevant_for_resume"]
                )
            ):
                action = "new_job"
            elif "source_offline" in constraints or "source_unavailable" in constraints:
                action = "restore_source"
            elif cache["cache_relevant_for_resume"] and cache["status"] == "unavailable":
                reason = cache.get("reason")
                if reason == "model_unavailable" and cache.get("error", {}).get("type") == (
                    "FileNotFoundError"
                ):
                    action = "fetch_model"
                elif reason != "inventory_not_checkpointed":
                    action = "inspect_cache"
        result["next_action"] = result["recovery"]["action"] = action
        result["recovery"]["cache_progress"] = (
            "Cache counts are a read-only snapshot under the inspected local runtime. "
            "Resume validates its own sources, model, runtime and entries again."
        )
    return result
