"""Explicit collection navigation and checked handoff to the existing reviewer."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

COMMANDS = frozenset({"collections", "runs"})


def _json_option(parser, *, inherited=False):
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS if inherited else False
    )


def register_commands(commands) -> None:
    collections = commands.add_parser("collections", help="find registered preparation workspaces")
    collections.add_argument("--source", type=Path, help="list collections for this exact source")
    _json_option(collections)
    actions = collections.add_subparsers(dest="collection_action")
    add = actions.add_parser("add", help="register or name an existing preparation workspace")
    add.add_argument("workspace", type=Path)
    add.add_argument("--name")
    _json_option(add, inherited=True)
    remove = actions.add_parser("remove", help="unregister a collection; keep all workspace files")
    remove.add_argument("collection")
    _json_option(remove, inherited=True)
    show = actions.add_parser("show", help="show a collection's recorded jobs and runs")
    show.add_argument("collection")
    _json_option(show, inherited=True)
    review = actions.add_parser("review", help="open one checked QA record in the local reviewer")
    review.add_argument("collection")
    review.add_argument("--run", required=True, help="exact record ID from dataset runs")
    review.add_argument("--expected-sha256", help="expected run.json checksum from the listing")
    review.add_argument(
        "--no-open", action="store_true", help="print the local URL without opening it"
    )
    review.add_argument("--port", type=int, default=0)

    runs = commands.add_parser("runs", help="list recorded artifacts for one registered collection")
    runs.add_argument("--collection", required=True, help="registered name or exact collection ID")
    runs.add_argument("--stage", help="exact recorded stage")
    runs.add_argument("--status", help="exact recorded status; not process liveness")
    runs.add_argument("--since", help="inclusive UTC date, YYYY-MM-DD")
    runs.add_argument("--until", help="inclusive UTC date, YYYY-MM-DD")
    runs.add_argument("--run", help="select one exact record ID")
    _json_option(runs)


def _display(value) -> str:
    text = str(value)
    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 32 or 127 <= ord(character) < 160
        else character
        for character in text
    )


def _date(value, flag):
    if value is None:
        return None
    try:
        result = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{flag} requires a calendar date in YYYY-MM-DD form") from exc
    if result.isoformat() != value:
        raise ValueError(f"{flag} requires a calendar date in YYYY-MM-DD form")
    return result


def _record_date(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(UTC)
    return stamp.date()


def _commands(entry, record):
    from image_dataset_train.qa import _commands as render_commands

    path, stage = record["path"], record["stage"]
    config = record.get("config_path")
    if not isinstance(config, str):
        config = None
    config_args = ["--config", config] if config else []
    if stage == "qa":
        arguments = [
            "dataset",
            "collections",
            "review",
            entry["id"],
            "--run",
            record["id"],
            "--expected-sha256",
            record["run_sha256"],
        ]
    elif stage == "export":
        arguments = ["dataset", "verify-export", "--run", path]
    elif stage == "groups" and config:
        arguments = ["dataset", "qa", "--run", path, *config_args]
    elif stage in {"tagging", "recaption"} and config:
        arguments = ["dataset", "recaption", "--run", path, *config_args]
    elif stage == "similarity" and config:
        arguments = ["dataset", "review", "--run", path, *config_args]
    else:
        return None
    return {"args": arguments, **render_commands(arguments)}


def _with_commands(entry, records):
    return [{**record, "commands": _commands(entry, record)} for record in records]


def _show_collection(entry):
    print(f"Collection: {_display(entry.get('name') or entry['id'])}")
    print(f"ID: {_display(entry['id'])}")
    print(f"Source: {_display(entry['source'])}")
    print(f"Workspace: {_display(entry['workspace'])}")


def _show_runs(records):
    if not records:
        print(
            "No runs match this selection. Use collections show to inspect jobs and catalog errors."
        )
        return
    for record in records:
        print(
            f"{_display(record['stage'])} | recorded {_display(record['status'])} | "
            f"{_display(record.get('created_at') or 'date unavailable')}"
        )
        print(f"  Record ID: {_display(record['id'])}")
        print(f"  Run: {_display(record['path'])}")
        print(f"  SHA256: {_display(record['run_sha256'])}")
        print(f"  Job: {_display(record.get('job_id') or 'standalone')}")
        commands = record.get("commands")
        if commands:
            print(f"  Next: {_display(commands['powershell'])}")


def _show_errors(errors):
    if errors:
        print(f"Catalog warnings: {len(errors)}; unavailable or invalid records were not adopted.")
        for error in errors:
            print("  " + _display(json.dumps(error, ensure_ascii=False, sort_keys=True)))


def _show_overview(result):
    from image_dataset_train.qa import _commands as render_commands

    entry = result["collection"]
    selector = entry.get("name") or entry["id"]
    _show_collection(entry)
    current = result.get("current_job_id")
    print(f"Current job: {_display(current or 'unavailable')}")
    revision = result.get("current_review_revision")
    print(
        f"Current review revision: {_display(revision if revision is not None else 'unavailable')}"
    )
    print(f"Recorded jobs: {len(result['jobs'])}; runs: {len(result['runs'])}")
    print("Metadata only; recorded status is not process liveness or dataset acceptance.")
    for job in result["jobs"]:
        marker = "current" if job.get("current") else "historical"
        print(
            f"  {marker}: {_display(job['id'])} | recorded {_display(job.get('status', 'unknown'))}"
        )
        if job.get("error"):
            print("    Error: " + _display(json.dumps(job["error"], ensure_ascii=False)))
    stages = Counter(row["stage"] for row in result["runs"] if row.get("job_id") == current)
    if stages:
        print(
            "Current-job retained artifacts: "
            + ", ".join(f"{_display(stage)} ({count})" for stage, count in sorted(stages.items()))
        )
    status = ["dataset", "status", "--collection", selector]
    if current:
        status += ["--job", current]
    print("Inspect: " + _display(render_commands(status)["powershell"]))
    if current:
        resume = ["dataset", "resume", "--collection", selector, "--job", current]
        print("Continue: " + _display(render_commands(resume)["powershell"]))
    runs = ["dataset", "runs", "--collection", selector, "--stage", "qa"]
    print("QA reports: " + _display(render_commands(runs)["powershell"]))
    history = ["dataset", "review-history", "list", "--collection", selector]
    if current:
        history += ["--job", current]
    print("Review history: " + _display(render_commands(history)["powershell"]))
    _show_errors(result["errors"])


def _review(entry, record, args):
    from image_dataset_train.config import load_config
    from image_dataset_train.exporting import _checked
    from image_dataset_train.inventory import file_sha256
    from image_dataset_train.qa import read_qa
    from image_dataset_train.review_ui import serve_reviews

    if record["stage"] != "qa":
        raise ValueError("Choose a QA record from dataset runs --stage qa")
    if args.json:
        raise ValueError("The interactive reviewer prints its local URL; omit --json")
    if not 0 <= args.port <= 65535:
        raise ValueError("--port must be between 0 and 65535")
    config_path = record.get("config_path")
    if not config_path:
        raise ValueError(
            "This QA record has no matching configuration; use its explicit review-ui command"
        )
    config_path = Path(config_path)
    if not config_path.is_absolute():
        raise ValueError("QA configuration locator must be an absolute path")
    config_checksum = record.get("config_sha256") or file_sha256(config_path)
    _checked(config_path.parent, config_path.name, config_checksum)
    config = load_config(config_path)
    source = Path(entry["source"]).resolve()
    if config.source.resolve() != source:
        raise ValueError("QA configuration source differs from the registered collection")
    roots = record.get("registered_roots", {})
    for field in ("runs", "reviews", "exports"):
        allowed = {Path(path).resolve() for path in roots.get(field, [])}
        if getattr(config, field).resolve() not in allowed:
            raise ValueError(f"QA configuration {field} root is outside this registered collection")
    run = Path(record["path"])
    metadata, _ = read_qa(run)
    if Path(metadata["source"]).resolve() != source:
        raise ValueError("QA source differs from the registered collection")
    _checked(run, "run.json", record["run_sha256"])
    _checked(config_path.parent, config_path.name, config_checksum)
    print(f"Opening checked QA: {_display(run)}")
    print(
        "Saved assessments keep their reviewer attribution; opening a report grants no acceptance."
    )
    serve_reviews(config, run, args.port, open_browser=not args.no_open, config_path=config_path)


def run_command(args) -> int:
    from image_dataset_train.collection_catalog import collection_snapshot, select_run
    from image_dataset_train.collection_registry import CollectionRegistry

    try:
        registry = CollectionRegistry()
        if args.command == "collections":
            action = args.collection_action
            if action and args.source is not None:
                raise ValueError(
                    "--source filters the collection list; omit it for collection actions"
                )
            if action is None:
                result = {"collections": registry.list(source=args.source)}
                if not args.json:
                    if not result["collections"]:
                        print("No registered collections match this selection.")
                        print(
                            "Start with dataset prepare <directory> "
                            "or dataset collections add <workspace>."
                        )
                    for entry in result["collections"]:
                        _show_collection(entry)
                    print("Use dataset collections show <name-or-id> for recorded jobs and runs.")
            elif action in {"add", "remove"}:
                entry = (
                    registry.register(args.workspace, name=args.name)
                    if action == "add"
                    else registry.remove(args.collection)
                )
                result = {
                    "action": "registered" if action == "add" else "unregistered",
                    "collection": entry,
                }
                if not args.json:
                    print(
                        f"{result['action'].capitalize()}: "
                        f"{_display(entry.get('name') or entry['id'])}"
                    )
                    _show_collection(entry)
                    if action == "remove":
                        print(
                            "Only the registration was removed. Workspace and source files remain."
                        )
            else:
                entry = registry.resolve(args.collection)
                if action == "review":
                    record = select_run(entry, args.run, expected_sha256=args.expected_sha256)
                    _review(entry, record, args)
                    return 0
                result = collection_snapshot(entry)
                result["runs"] = _with_commands(entry, result["runs"])
                if not args.json:
                    _show_overview(result)
        else:
            since, until = _date(args.since, "--since"), _date(args.until, "--until")
            if since and until and since > until:
                raise ValueError("--since must not be later than --until")
            entry = registry.resolve(args.collection)
            snapshot = collection_snapshot(entry)
            records = [select_run(entry, args.run)] if args.run else snapshot["runs"]
            selected, undated = [], 0
            for record in records:
                if args.stage and record["stage"] != args.stage:
                    continue
                if args.status and record["status"] != args.status:
                    continue
                stamp = _record_date(record.get("created_at"))
                if (since or until) and stamp is None:
                    undated += 1
                    continue
                if since and stamp < since or until and stamp > until:
                    continue
                selected.append(record)
            result = {
                "collection": entry,
                "runs": _with_commands(entry, selected),
                "errors": snapshot["errors"],
                "filters": {
                    key: getattr(args, key) for key in ("stage", "status", "since", "until", "run")
                },
                "undated_excluded": undated,
                "metadata_verification": "metadata_only",
                "status_is_liveness": False,
            }
            if not args.json:
                _show_collection(entry)
                print(f"Matching runs: {len(selected)}")
                print(
                    "Metadata only; recorded status is not process liveness or dataset acceptance."
                )
                _show_runs(result["runs"])
                if undated:
                    print(f"Date filter excluded {undated} records without a valid date.")
                _show_errors(result["errors"])
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    },
                    indent=2,
                )
            )
        else:
            print(f"Collection command failed: {_display(exc)}")
        return 2
