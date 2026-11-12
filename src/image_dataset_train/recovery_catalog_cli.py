"""Dependency-light, read-only navigation of saved recovery operations."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path

COMMANDS = frozenset({"recovery"})


def _common_arguments(parser, *, inherited=False):
    default = argparse.SUPPRESS if inherited else None
    parser.add_argument("--home", type=Path, default=default, help="application data directory")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS if inherited else False
    )


def _configure(parser):
    _common_arguments(parser)
    parser.add_argument("--source", type=Path, help="list receipts for this exact source directory")
    parser.add_argument("--kind", choices=("removal", "collision", "restore", "package"))
    parser.add_argument("--status", help="filter the exact saved status; not process liveness")
    actions = parser.add_subparsers(dest="recovery_action")
    show = actions.add_parser("show", help="inspect one exact receipt and its recovery commands")
    show.add_argument("record", help="full record ID from dataset recovery")
    show.add_argument("--expected-sha256", help="expected receipt checksum from the listing")
    _common_arguments(show, inherited=True)


def register_commands(commands) -> None:
    parser = commands.add_parser("recovery", help="find saved caption and repair recovery records")
    _configure(parser)


def _display(value) -> str:
    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 32 or 127 <= ord(character) < 160
        else character
        for character in str(value)
    )


def _powershell_argument(value):
    return "'" + str(value).replace("'", "''") + "'"


def _command(argv, *, environment=None, label=None, scope=None):
    argv = [str(argument) for argument in argv]
    environment = dict(environment or {})
    ps_prefix = [
        f"$env:{key} = {_powershell_argument(value)}" for key, value in environment.items()
    ]
    posix_prefix = [f"{key}={shlex.quote(str(value))}" for key, value in environment.items()]
    result = {
        "argv": argv,
        "environment": environment,
        "powershell": "\n".join([*ps_prefix, "& " + " ".join(map(_powershell_argument, argv))]),
        "posix": " ".join([*posix_prefix, shlex.join(argv)]),
    }
    if label is not None:
        result["label"] = label
    if scope is not None:
        result["scope"] = scope
    return result


def browse_command(home: Path, source: Path | None = None) -> dict:
    """Return a copyable navigation command with an explicit application-data root."""
    argv = ["dataset", "recovery", "--home", str(home)]
    if source is not None:
        argv.extend(["--source", str(source)])
    return _command(argv)


def _commands(record):
    environment = {"TRAINIME_HOME": str(record["home"])}
    kind = record["kind"]
    if kind == "removal":
        plan_path = str(Path(record["receipt"]).with_name("plan.json"))
        plan_sha256 = record.get("metadata_inputs", {}).get(plan_path)
        if not isinstance(plan_sha256, str) or len(plan_sha256) != 64:
            raise ValueError(
                "Selected removal record is missing its plan identity; refresh the list"
            )
        argv = [
            "dataset",
            "restore-captions",
            "--receipt",
            record["receipt"],
            "--expected-sha256",
            record["receipt_sha256"],
            "--expected-plan-sha256",
            plan_sha256,
        ]
        return [
            _command(
                [*argv, "--dryrun"],
                environment=environment,
                label="Preview caption restoration",
                scope="Read-only verification of this removal receipt and current destinations.",
            ),
            _command(
                argv,
                environment=environment,
                label="Restore missing captions",
                scope="Explicit apply; preserves newer captions and records conflicts.",
            ),
        ]
    if kind == "collision":
        return [
            _command(
                ["trainime", "fix", record["source"], "--fix", "1", "--dryrun"],
                environment=environment,
                label="Preview source-directory collision recovery",
                scope=(
                    "Checks all pending tf001 repairs for this source, not only this receipt. "
                    "It does not undo renames or reassign ambiguous captions."
                ),
            )
        ]
    if kind == "package":
        return [
            _command(
                ["trainime", "doctor", "--dryrun"],
                environment=environment,
                label="Inspect the current installation",
                scope=(
                    "Read-only diagnosis of the command's current installation. "
                    "It does not replay this historical wheel or installation target."
                ),
            )
        ]
    return []


def _show_command(record):
    return _command(
        [
            "dataset",
            "recovery",
            "show",
            record["id"],
            "--home",
            record["home"],
            "--expected-sha256",
            record["receipt_sha256"],
        ]
    )


def _print_errors(errors):
    for error in errors:
        print(f"Unavailable receipt: {_display(error.get('path', 'unknown'))}")
        print("  " + _display(error.get("error", error.get("message", "Invalid metadata"))))


def _shell():
    return "powershell" if os.name == "nt" else "posix"


def _print_list(result):
    print(f"Recovery records: {len(result['records'])}")
    print(f"Application data: {_display(result['home'])}")
    print("Saved metadata only; status does not establish integrity or process liveness.")
    for record in result["records"]:
        print()
        print(
            f"{_display(record['kind'])}: {_display(record['status'])}; "
            f"{record['affected_count']} affected paths"
        )
        if record.get("source"):
            print(f"Source: {_display(record['source'])}")
        print(f"Receipt: {_display(record['receipt'])}")
        print("Inspect: " + _display(record["show_command"][_shell()]))
    if not result["records"]:
        print("No saved recovery receipts match this selection.")
    _print_errors(result.get("errors", []))


def _print_show(record):
    print(f"Recovery operation: {_display(record['kind'])} / {_display(record['status'])}")
    print("Saved metadata only; use an explicit preview to check current files.")
    print(f"Record ID: {_display(record['id'])}")
    print(f"Receipt: {_display(record['receipt'])}")
    print(f"Receipt SHA256: {_display(record['receipt_sha256'])}")
    if record.get("source"):
        print(f"Source: {_display(record['source'])}")
    if record.get("original_receipt"):
        print(f"Original removal receipt: {_display(record['original_receipt'])}")
        print("This records an earlier restoration; it is not an undo operation.")
    for location in record.get("recovery_locations", []):
        print(f"Recovery location: {_display(location)}")
    print(f"Affected paths: {record['affected_count']}")
    for item in record.get("items", [])[:20]:
        print("  " + _display(item.get("path", "Unknown path")))
        for field in ("target", "backup", "recorded_status"):
            if item.get(field) is not None:
                print(f"    {field}: {_display(item[field])}")
    if len(record.get("items", [])) > 20:
        print("  Further paths are available with --json.")
    for warning in record.get("warnings", []):
        print("Note: " + _display(warning))
    for command in record["commands"]:
        print()
        print(command["label"] + ": " + command["scope"])
        if _shell() == "powershell":
            for key, value in command["environment"].items():
                print(f"$env:{key} = " + _display(_powershell_argument(value)))
            print(_display(_command(command["argv"])["powershell"]))
        else:
            print(_display(command["posix"]))


def run_command(args) -> int:
    try:
        from image_dataset_train.recovery_catalog import list_recovery, select_recovery

        if args.recovery_action == "show":
            if args.source is not None or args.kind is not None or args.status is not None:
                raise ValueError(
                    "--source, --kind and --status filter the list; omit them for show"
                )
            result = select_recovery(args.home, args.record, expected_sha256=args.expected_sha256)
            result = {**result, "commands": _commands(result)}
            if not args.json:
                _print_show(result)
        else:
            result = list_recovery(
                args.home, source=args.source, kind=args.kind, status=args.status
            )
            result = {
                **result,
                "records": [
                    {**record, "show_command": _show_command(record)}
                    for record in result["records"]
                ],
            }
            if not args.json:
                _print_list(result)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        if args.json:
            print(json.dumps({"status": "cancelled", "read_only": True}))
        else:
            print("Recovery inspection cancelled. Saved evidence is unchanged.")
        return 130
    except (ValueError, OSError, ImportError) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("Recovery inspection failed: " + _display(exc))
        return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dataset recovery", description=__doc__)
    _configure(parser)
    return run_command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
