"""The compact directory workflow, independent of repository configuration."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from image_dataset_train.config import load_config
from image_dataset_train.diagnostics import EventLog, app_home, diagnose
from image_dataset_train.model_bundle import MODELS
from image_dataset_train.preparation import (
    PreparationRecoveryError,
    default_workspace,
    inspect_preparation,
    preparation_config,
    prepare_directory,
    preview_preparation,
    read_preparation_job,
    resume_preparation,
)

COMMANDS = frozenset({"prepare", "resume", "status"})


def register_commands(commands) -> None:
    prepare = commands.add_parser(
        "prepare", help="prepare a directory as a portable training dataset"
    )
    prepare.add_argument("source", type=Path)
    prepare.add_argument("--workspace", type=Path, help="persistent job/review/output directory")
    prepare.add_argument("--config", type=Path, help="optional advanced settings and shared caches")
    prepare.add_argument("--captions", choices=["model", "existing"], default="model")
    prepare.add_argument("--model", choices=sorted(MODELS))
    prepare.add_argument("--device", choices=["auto", "cpu", "cuda"])
    prepare.add_argument("--batch-size", type=int)
    prepare.add_argument("--resolution", type=int)
    prepare.add_argument("--validation-ratio", type=float)
    prepare.add_argument("--max-distance", type=int, default=8, metavar="0..64")
    prepare.add_argument("--sample-size", type=int, default=50)
    prepare.add_argument("--offline", action="store_true", help="never fetch a missing model")
    prepare.add_argument(
        "--new", action="store_true", help="start a new frozen job in this workspace"
    )
    prepare.add_argument(
        "--dryrun", "--dry-run", action="store_true", help="inspect without writes or inference"
    )
    prepare.add_argument("--json", action="store_true")
    resume = commands.add_parser("resume", help="continue a saved directory preparation job")
    resume.add_argument("workspace", type=Path, nargs="?")
    resume.add_argument("--collection", help="registered collection name or exact ID")
    resume.add_argument("--job", help="resume only if this exact job is still current")
    resume.add_argument(
        "--refresh-reviews", action="store_true", help="republish after saved review changes"
    )
    resume.add_argument("--json", action="store_true")
    status = commands.add_parser(
        "status", help="show preparation stages, outputs and recovery actions"
    )
    status.add_argument("workspace", type=Path, nargs="?")
    status.add_argument("--collection", help="registered collection name or exact ID")
    status.add_argument("--job", help="inspect one exact current or historical job")
    status.add_argument("--verify", action="store_true", help="recheck every completed artifact")
    status.add_argument(
        "--verify-cache",
        action="store_true",
        help=(
            "verify cache and sources; loads the local model session without inference or downloads"
        ),
    )
    status.add_argument("--json", action="store_true")


def _command(*args) -> str:
    return "& " + " ".join("'" + str(arg).replace("'", "''") + "'" for arg in args)


def _path_text(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except (OSError, ValueError):
        return str(path)


def _prepare_argv(args, workspace: Path | None, *, new: bool = False) -> list[str]:
    argv = ["dataset", "prepare", _path_text(args.source)]
    if workspace is not None:
        argv.extend(("--workspace", _path_text(workspace)))
    for name in (
        "config",
        "captions",
        "model",
        "device",
        "batch_size",
        "resolution",
        "validation_ratio",
        "max_distance",
        "sample_size",
    ):
        value = getattr(args, name, None)
        if value is not None:
            argv.extend(
                (
                    "--" + name.replace("_", "-"),
                    _path_text(value) if name == "config" else str(value),
                )
            )
    for name in ("offline", "dryrun", "json"):
        if getattr(args, name, False) and not (new and name == "dryrun"):
            argv.append("--" + name)
    if new or args.new:
        argv.append("--new")
    return argv


def _next_commands(
    action: str | None, saved: dict | None, args, workspace: Path | None
) -> list[dict]:
    commands = []

    def add(label, *argv):
        values = [str(value) for value in argv]
        if saved and values[1] in {"status", "resume"} and "--job" not in values:
            values.extend(("--job", saved["job_id"]))
        if args.json and values[1] not in {"review-ui", "fetch-model"} and "--json" not in values:
            values.append("--json")
        commands.append({"label": label, "argv": values, "command": _command(*values)})

    location = saved["workspace"] if saved else _path_text(workspace) if workspace else None
    if action == "correct_arguments":
        return []
    if action == "select_current_job" and saved:
        add(
            "Inspect the current job",
            "dataset",
            "status",
            location,
            "--job",
            saved.get("current_job_id", saved["job_id"]),
        )
        return commands
    cache = saved.get("cache_verification", {}) if saved else {}
    if action == "restore_source":
        add("Recheck after restoring the source", "dataset", "status", location, "--verify-cache")
        return commands
    if action == "inspect_cache":
        add("Recheck after resolving diagnostic", "dataset", "status", location, "--verify-cache")
        return commands
    if action == "new_job" and args.command == "prepare":
        add(
            "Start a new job with the requested settings", *_prepare_argv(args, workspace, new=True)
        )
    elif action == "new_job" and saved:
        options = saved["options"]
        argv = [
            "dataset",
            "prepare",
            saved["source"],
            "--workspace",
            location,
            "--config",
            saved["config"],
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
        add("Start a new job with the saved settings", *argv)
    elif action == "fetch_model" and saved:
        # The saved configuration contains the exact model/revision pin; a CLI
        # model override would unnecessarily replace that binding.
        add("Fetch the pinned model", "dataset", "fetch-model", "--config", saved["config"])
        add("Resume", "dataset", "resume", location)
    elif action in {"review_then_resume", "refresh_reviews"} and saved:
        if action == "review_then_resume":
            report = saved["outputs"].get("review_qa")
            if report:
                add(
                    "Review",
                    "dataset",
                    "review-ui",
                    "--run",
                    report["path"],
                    "--config",
                    saved["config"],
                )
        add(
            "Refresh saved reviews and continue", "dataset", "resume", location, "--refresh-reviews"
        )
    elif action == "inspect_artifacts" and location:
        add("Inspect retained artifacts", "dataset", "status", location, "--verify")
    elif saved and saved["status"] == "completed" and action is None:
        report = saved["outputs"].get("qa")
        if report:
            add(
                "Open review",
                "dataset",
                "review-ui",
                "--run",
                report["path"],
                "--config",
                saved["config"],
            )
        add("Verify", "dataset", "status", location, "--verify")
    elif saved and location:
        add("Resume", "dataset", "resume", location)
    elif args.command == "prepare":
        add(
            "Retry after addressing the error",
            *_prepare_argv(args, workspace, new=action == "new_job"),
        )
    elif location:
        add("Inspect retained artifacts", "dataset", "status", location, "--verify")
    if cache.get("has_diagnostics"):
        add("Recheck inference cache", "dataset", "status", location, "--verify-cache")
    return commands


def _render(result: dict) -> None:
    if "saved_job" in result:
        error = result["error"]
        print(f"{result['command']}: {result['status']}")
        print(f"{error['code']}: {error['message']}")
        if result.get("workspace"):
            print(f"Workspace: {result['workspace']}")
        if result["saved_job"]:
            saved = result["saved_job"]
            print(f"Saved job: {saved['status']}; {saved['job']}")
            _render_stages(saved)
            for stage in ("export", "qa", "review_qa"):
                if stage in saved["outputs"]:
                    print(f"Retained {stage}: {saved['outputs'][stage]['path']}")
        if error.get("log"):
            print(f"Error report: {error['log']}")
        if result.get("log_unavailable"):
            print(f"Error log unavailable: {result['log_unavailable']['message']}")
        _render_registration(result)
        for next_command in result["next_commands"]:
            print(f"{next_command['label']}: {next_command['command']}")
        return
    if result.get("dry_run"):
        summary = result["intake"]
        print(f"Preview: {result['source']}")
        print(f"{summary['files_seen']} files; {summary['images_seen']} images")
        print("Intake: " + json.dumps(summary["decisions"]))
        print("No files changed, model downloaded or tags generated.")
        return
    print(f"Preparation: {result['status']}")
    if result.get("verification_errors"):
        print("Artifact verification failed; inspect the retained files before continuing.")
    print(f"Workspace: {result['workspace']}")
    print(
        f"Job: {result['job_id']}"
        + (" (historical)" if result.get("is_current_job") is False else "")
    )
    _render_stages(result)
    _render_cache(result.get("cache_verification"))
    if result.get("error"):
        print(f"{result['error']['code']}: {result['error']['message']}")
    for stage, record in result["outputs"].items():
        if stage in {"export", "qa", "review_qa"}:
            path = Path(record["path"]) / "report.html" if stage != "export" else record["path"]
            print(f"{stage}: {path}")
    exported = result["outputs"].get("export")
    if exported and not result.get("verification_errors"):
        print(f"Image/caption pairs: {exported['summary']['images']}")
        print(f"Catalog: {Path(exported['path']) / 'catalog.sqlite'}")
        print("Preparation decisions are attributed; human quality acceptance is separate.")
    _render_registration(result)
    for next_command in result["next_commands"]:
        print(f"{next_command['label']}: {next_command['command']}")


def _render_stages(result: dict) -> None:
    for stage in result.get("stages", []):
        print(
            f"  {stage['stage']}: {stage['status']}; {stage['integrity']}; {stage['continuation']}"
        )
        if stage.get("error"):
            print(f"    {stage['error']['message']}")
        if stage.get("attempt") and stage["status"] != "completed":
            print(f"    Retained attempt: {stage['attempt']}")
        for path in stage.get("pending_outputs", []):
            print(f"    Pending output: {path}")
        if stage["status"] != "completed":
            for output in stage.get("published_outputs", []):
                print(f"    Published output: {output['path']}")
                if "verified_retained_score_vectors" in output:
                    print(
                        "    Verified retained score vectors: "
                        f"{output['verified_retained_score_vectors']}; "
                        "inference cache reuse checked during resume"
                    )
    if result.get("retained_attempts"):
        print(f"Earlier retained attempts: {len(result['retained_attempts'])}")
        for attempt in result["retained_attempts"]:
            if attempt.get("attempt"):
                print(f"  {attempt['stage']}: {attempt['attempt']}")


def _render_cache(cache: dict | None) -> None:
    if cache is None:
        return
    if cache["status"] == "not_applicable":
        print("Inference cache: not applicable to existing captions")
        return
    print(f"Inference cache inspection: {cache['status']}")
    if cache.get("counts") is not None:
        counts = cache["counts"]
        print(
            f"  {cache['eligible_occurrences']} eligible image occurrences; "
            f"{cache['eligible_unique_contents']} unique contents"
        )
        print(
            f"  Unique cache entries: {counts['valid']} valid; {counts['missing']} missing; "
            f"{counts['invalid']} invalid"
        )
        if cache["cache_relevant_for_resume"]:
            print("  Missing entries need inference when tagging resumes.")
        invalid = [entry for entry in cache.get("entries", []) if entry["status"] == "invalid"]
        for entry in invalid[:3]:
            print(f"  Invalid cache: {entry['path']}")
            if entry.get("error"):
                print(f"    {entry['error']['message']}")
        if len(invalid) > 3:
            print(
                f"  {len(invalid) - 3} additional invalid cache entries; "
                "use --json for all paths and errors."
            )
    if cache.get("runtime"):
        print("  Runtime providers: " + ", ".join(cache["runtime"].get("providers", [])))
        if cache.get("provider_fallback"):
            print(f"  Provider fallback: {cache['provider_fallback']}")
    if cache.get("error"):
        print(f"  {cache['error']['message']}")
    elif cache["status"] == "unavailable":
        print(f"  {cache['reason'].replace('_', ' ')}; counts unavailable")
    source = cache["source_verification"]
    print(f"  Frozen source check: {source['status']}")
    if source.get("message"):
        print(f"  {source['message']}")
    if cache["implementation_match"] is False:
        print("  Application differs from the saved build; unfinished jobs need a new job.")
    tagging_error = cache.get("tagging_verification", {}).get("error")
    if tagging_error:
        print(f"  Tagging publication: {tagging_error['message']}")
    if not cache["cache_relevant_for_resume"]:
        if cache["tagging_continuation"] == "recover_publication":
            print("  Verified tagging publication can be recovered without the inference cache.")
        else:
            print("  Completed tagging uses its saved checkpoint; inference cache is not required.")
    print("  Cache counts are a snapshot; resume validates reuse again. No inference performed.")


def _job_view(result: dict) -> dict:
    """Present job-specific commands; retain generic diagnosis only in saved evidence."""
    if not result.get("error"):
        return result
    return {
        **result,
        "error": {
            key: value for key, value in result["error"].items() if key not in {"fix", "fix_code"}
        },
    }


def _remember_collection(result: dict, saved: dict) -> None:
    """Navigation persistence must not invalidate a successful or retained preparation."""
    try:
        from image_dataset_train.collection_registry import CollectionRegistry

        entry = CollectionRegistry().register(Path(saved["workspace"]))
        result["collection_registration"] = {"status": "registered", "collection": entry}
    except Exception as error:
        result["collection_registration"] = {
            "status": "failed",
            "error": {"type": type(error).__name__, "message": str(error)},
            "command": _command("dataset", "collections", "add", saved["workspace"]),
        }


def _render_registration(result: dict) -> None:
    registration = result.get("collection_registration")
    if not registration:
        return
    if registration["status"] == "registered":
        entry = registration["collection"]
        print(f"Saved collection: {entry.get('name') or entry['id']}")
    else:
        print(f"Collection registration unavailable: {registration['error']['message']}")
        print(f"Register after resolving that issue: {registration['command']}")


def _failure(args, workspace, error, *, readonly: bool, executing: bool) -> int:
    saved = None
    if workspace is not None:
        try:
            saved = _job_view(inspect_preparation(workspace, job_id=getattr(args, "job", None)))
        except Exception:
            # A damaged/missing job must not hide the original command failure.
            pass
    action = getattr(error, "action", None)
    if action is None:
        action = (
            "inspect_artifacts"
            if args.command == "status"
            else "correct_arguments"
            if isinstance(error, ValueError) and not executing
            else "resume"
        )
    diagnosis = diagnose(error)
    log = None
    log_unavailable = None
    if not readonly:
        try:
            log = EventLog(app_home()).exception(
                error,
                action=args.command,
                workspace=workspace,
                saved_job=saved["job"] if saved else None,
            )
        except Exception as log_error:
            log_unavailable = {"type": type(log_error).__name__, "message": str(log_error)}
    result = {
        "command": args.command,
        "status": "cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
        "workspace": _path_text(workspace) if workspace is not None else None,
        "error": {
            "type": type(error).__name__,
            "code": diagnosis.code,
            "message": str(error) or "Cancelled by the caller",
            "log": str(log) if log else None,
        },
        "saved_job": saved,
        "next_action": action,
        "next_commands": _next_commands(action, saved, args, workspace),
        "prepared": False,
        "human_accepted": False,
    }
    if log_unavailable is not None:
        result["log_unavailable"] = log_unavailable
    if (
        args.command == "prepare"
        and executing
        and not readonly
        and saved is not None
        and Path(saved["source"]) == Path(_path_text(args.source))
    ):
        _remember_collection(result, saved)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    return 130 if isinstance(error, KeyboardInterrupt) else 2


def run_command(args) -> int:
    def progress(message):
        print(message, file=sys.stderr, flush=True)

    workspace = args.workspace
    readonly = args.command == "status" or args.command == "prepare" and args.dryrun
    executing = False
    try:
        registered_source = None
        if args.command in {"status", "resume"}:
            if (workspace is None) == (args.collection is None):
                raise PreparationRecoveryError(
                    "Choose a workspace path or --collection, but not both", "correct_arguments"
                )
            if args.collection is not None:
                from image_dataset_train.collection_registry import CollectionRegistry

                entry = CollectionRegistry().resolve(args.collection)
                workspace = Path(entry["workspace"])
                registered_source = Path(entry["source"])
                _, selected = read_preparation_job(workspace, job_id=args.job)
                if Path(selected["source"]) != registered_source:
                    raise PreparationRecoveryError(
                        "Registered collection source differs from the preparation job",
                        "correct_arguments",
                    )
                if args.command == "resume" and args.job is None:
                    args.job = selected["job_id"]
        if args.command == "prepare":
            if not 0 <= args.max_distance <= 64:
                raise ValueError("Similarity distance must be an integer between 0 and 64")
            if args.sample_size < 1:
                raise ValueError("QA sample size must be a positive integer")
            workspace = args.workspace or default_workspace(args.source)
            config = preparation_config(
                args.source, workspace, base=load_config(args.config) if args.config else None
            )
            tag_changes = {
                key: getattr(args, key)
                for key in ("model", "device", "batch_size")
                if getattr(args, key) is not None
            }
            if args.model is not None:
                tag_changes["revision"] = MODELS[args.model].revision
            export_changes = {
                key: getattr(args, key)
                for key in ("resolution", "validation_ratio")
                if getattr(args, key) is not None
            }
            config = replace(
                config,
                tagging=replace(config.tagging, **tag_changes),
                export=replace(config.export, **export_changes),
            )
            if args.dryrun:
                result = preview_preparation(config, captions=args.captions)
            else:
                executing = True
                result = prepare_directory(
                    config,
                    workspace,
                    captions=args.captions,
                    offline=args.offline,
                    max_distance=args.max_distance,
                    sample_size=args.sample_size,
                    new=args.new,
                    progress=progress,
                )
        elif args.command == "resume":
            executing = True
            result = resume_preparation(
                workspace,
                refresh_reviews=args.refresh_reviews,
                expected_job_id=args.job,
                expected_source=registered_source,
                progress=progress,
            )
        else:
            result = inspect_preparation(
                workspace, job_id=args.job, verify=args.verify, verify_cache=args.verify_cache
            )
            if registered_source is not None and Path(result["source"]) != registered_source:
                raise PreparationRecoveryError(
                    "Registered collection source differs from the preparation job",
                    "correct_arguments",
                )
    except (Exception, KeyboardInterrupt) as error:
        return _failure(args, workspace, error, readonly=readonly, executing=executing)
    if not result.get("dry_run"):
        result = _job_view(result)
        result["next_commands"] = _next_commands(result.get("next_action"), result, args, workspace)
        if args.command == "prepare":
            _remember_collection(result, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    return (
        2
        if result.get("verification_errors")
        else 1
        if result.get("status") == "needs_review"
        or result.get("cache_verification", {}).get("has_diagnostics")
        else 0
    )
