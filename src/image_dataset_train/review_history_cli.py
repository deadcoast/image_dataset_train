"""Read saved review changes and restore one target through a guarded preview."""

from __future__ import annotations

import json
from pathlib import Path

from image_dataset_train.implementation import implementation_identity
from image_dataset_train.review_selection import (
    Selection,
    add_selection_arguments,
    refresh_command,
    select_report,
)
from image_dataset_train.review_selection import (
    command as _command,
)
from image_dataset_train.review_selection import (
    display as _display,
)
from image_dataset_train.review_selection import (
    fingerprint as _fingerprint,
)
from image_dataset_train.review_selection import (
    select_review as _select,
)
from image_dataset_train.review_selection import (
    selection_args as _selection_args,
)

COMMANDS = {"review-history"}


def register_commands(commands) -> None:
    parser = commands.add_parser(
        "review-history", help="inspect saved review changes and preview guarded restoration"
    )
    actions = parser.add_subparsers(dest="history_action", required=True)
    for name, help_text in (
        ("list", "list image and pair revisions without changing reviews"),
        ("show", "show one revision and its current restoration preview"),
        ("restore", "preview restoring one revision; --apply performs the guarded change"),
        ("changes", "inspect saved review changes since an exact QA report"),
    ):
        action = actions.add_parser(name, help=help_text)
        add_selection_arguments(action)
        if name == "changes":
            action.add_argument(
                "--report", type=Path, help="exact QA report; otherwise selected job QA"
            )
            action.add_argument(
                "--kind", choices=["images", "pairs"], help="filter changed records"
            )
            action.add_argument(
                "--limit", type=int, default=20, help="maximum changed records displayed"
            )
            action.add_argument("--offset", type=int, default=0, help="offset in filtered changes")
            action.add_argument(
                "--expected-inspection-sha256",
                help="guard a subsequent page against changed evidence",
            )
        elif name == "list":
            target = action.add_mutually_exclusive_group()
            target.add_argument("--image", help="exact relative source path")
            target.add_argument("--pair", help="complete saved pair ID")
            action.add_argument("--limit", type=int, default=20, help="maximum revisions displayed")
            action.add_argument("--offset", type=int, default=0, help="offset in filtered history")
        else:
            action.add_argument(
                "--revision", type=int, required=True, help="exact history revision"
            )
            action.add_argument(
                "--before", action="store_true", help="restore the state before the selected edit"
            )
        if name == "restore":
            action.add_argument("--apply", action="store_true", help="apply a matching preview")
            action.add_argument(
                "--expected-revision", type=int, help="current revision from preview"
            )
            action.add_argument("--expected-plan-sha256", help="exact preview identity")
            action.add_argument("--reason", help="reason for this restoration")
            action.add_argument("--reviewer", help="identity of the restoration actor")
            action.add_argument("--reviewer-kind", choices=["human", "assistant", "unknown"])


def _refresh_command(selected: Selection) -> dict:
    return refresh_command(selected, identity_provider=implementation_identity)


def _next_commands(args, selected: Selection, result: dict) -> list[dict]:
    selectors = _selection_args(selected)
    if args.history_action == "changes":
        commands = []
        if result.get("next_offset") is not None:
            argv = [
                "dataset",
                "review-history",
                "changes",
                *selectors,
                "--report",
                result["report"],
                "--limit",
                str(result["limit"]),
                "--offset",
                str(result["next_offset"]),
                "--expected-inspection-sha256",
                result["inspection_sha256"],
            ]
            if args.kind is not None:
                argv += ["--kind", args.kind]
            commands.append(_command("Next changes page", argv))
        if result["state"] == "changed":
            commands.append(_refresh_command(selected))
        return commands
    if args.history_action == "list":
        commands = []
        if result.get("next_offset") is not None:
            argv = [
                "dataset",
                "review-history",
                "list",
                *selectors,
                "--limit",
                str(args.limit),
                "--offset",
                str(result["next_offset"]),
            ]
            if args.image is not None:
                argv += ["--image", args.image]
            if args.pair is not None:
                argv += ["--pair", args.pair]
            commands.append(_command("Next history page", argv))
        if result.get("events"):
            revision = result["events"][0]["revision"]
            commands.append(
                _command(
                    "Inspect this revision",
                    ["dataset", "review-history", "show", *selectors, "--revision", str(revision)],
                )
            )
        return commands
    if args.history_action == "restore" and args.apply:
        return [_refresh_command(selected)] if result["status"] == "restored" else []
    argv = ["dataset", "review-history", "restore", *selectors, "--revision", str(args.revision)]
    if args.before:
        argv.append("--before")
    commands = []
    if result["applicable"] and not result["no_op"]:
        argv += [
            "--apply",
            "--expected-revision",
            str(result["current_revision"]),
            "--expected-plan-sha256",
            result["plan_sha256"],
            "--reason",
            getattr(args, "reason", None) or "<reason>",
            "--reviewer",
            getattr(args, "reviewer", None) or "<reviewer>",
            "--reviewer-kind",
            getattr(args, "reviewer_kind", None) or "<human|assistant|unknown>",
        ]
        commands.append(_command("Apply this exact preview after supplying actor and reason", argv))
    return commands


def _value(value, *, present=True) -> str:
    if not present:
        return "<absent>"
    text = _display(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return text if len(text) <= 240 else text[:237] + "..."


def _changes(changes, *, indent="    ") -> None:
    if not changes:
        print(indent + "No field changes.")
    for change in changes:
        before = _value(change["before"], present=change["before_present"])
        after = _value(change["after"], present=change["after_present"])
        print(indent + _display(change["field"]) + ": " + before + " -> " + after)


def _event(event, *, records=False) -> None:
    record = event["after"] or event["before"]
    target = (
        record["source_path"]
        if event["kind"] == "images"
        else record["left_source_path"] + " <-> " + record["right_source_path"]
    )
    print(f"  Revision {event['revision']} | {event['kind']} | {event['action']}")
    print("    Target: " + _display(target))
    print("    At: " + _display(event["at"]))
    print(
        "    Actor: "
        + _display(event.get("reviewer") or "not recorded")
        + " ("
        + _display(event.get("reviewer_kind", "unknown"))
        + ")"
    )
    print("    Reason: " + _value(event.get("reason")))
    print("    Event: " + _display(event["event_id"]))
    batch = event.get("batch")
    if batch:
        print(
            "    Batch: "
            + _display(batch["id"])
            + f" | change {batch['index'] + 1} of {batch['count']}"
        )
    if records:
        print("    Before: " + ("absent" if event["before"] is None else _value(event["before"])))
        print("    After: " + ("absent" if event["after"] is None else _value(event["after"])))
    _changes(event["changes"])
    if not event["compatible"]:
        print("    Historical content does not match the selected inventory.")


def _render(result: dict) -> None:
    if result.get("status") == "failed":
        print("Review history: " + _display(result["error"]["message"]))
        return
    print("Source: " + _display(result["source"]))
    applied = result.get("status") == "restored"
    current_revision = result["revision"] if applied else result["current_revision"]
    print(f"Current review revision: {current_revision}")
    if result["selection"].get("job_id"):
        print("Selected job: " + _display(result["selection"]["job_id"]))
    if "differences" in result:
        print("Report: " + _display(result["report"]))
        print(f"Snapshot revision: {result['snapshot_revision']} | {result['state']}")
        print(
            f"Saved changes: {result['net_change_count']} net records; "
            f"{result['history_delta_count']} later history events"
        )
        counts = result["counts"]
        print(f"Records: {counts['images']} images; {counts['pairs']} pairs")
        print(
            f"Scope: {counts['in_report']} in report; {counts['outside_report']} outside; "
            f"{counts['partial_report']} partly in report; "
            f"{counts['incompatible']} incompatible with selected inventory"
        )
        print(
            f"Page: {len(result['differences'])} of {result['filtered_count']} matching records "
            f"(offset {result['offset']})"
        )
        if not result["differences"]:
            message = (
                "History advanced, but saved records match this snapshot."
                if result["state"] == "history_only"
                else "No saved changes match this page/filter."
                if result["net_change_count"]
                else "Saved records match this snapshot."
            )
            print(message)
        for difference in result["differences"]:
            identity = difference["identity"]
            target = (
                identity["source_path"]
                if difference["kind"] == "images"
                else identity["left_source_path"] + " <-> " + identity["right_source_path"]
            )
            print("  " + difference["kind"] + ": " + _display(target))
            print(
                "    Identity: "
                + _display(json.dumps(identity, ensure_ascii=False, sort_keys=True))
            )
            print(
                "    Report membership: "
                + difference["report_membership"]
                + " | Selected inventory: "
                + ("compatible" if difference["inventory_compatible"] else "incompatible")
            )
            _changes(difference["changes"])
        print(
            "Saved-record differences only; export/caption effects "
            "and live source bytes are not validated."
        )
        print("Long values are abbreviated; --json retains complete records and changes.")
    elif "events" in result:
        print(
            f"History: {result['matching_events']} matching / "
            f"{result['total_events']} total revisions"
        )
        if not result["events"]:
            print("No saved changes match this selection.")
        for event in result["events"]:
            _event(event)
        print("Long values are abbreviated; --json retains complete records and changes.")
    else:
        print("Selected historical change:")
        _event(result["selected_event"], records=True)
        status = result.get("status", "preview")
        print(
            f"Restoration: {status}; revision {result['target_revision']} "
            + ("before" if result["before"] else "after")
        )
        if status == "restored":
            print(f"Saved new revision: {result['revision']}")
        else:
            print("Preview SHA256: " + result["plan_sha256"])
        print(
            ("Previous record: " if applied else "Current record: ")
            + (
                "absent"
                if result["current_record"] is None
                else _display(
                    json.dumps(result["current_record"], ensure_ascii=False, sort_keys=True)
                )
            )
        )
        print(
            ("Restored record: " if applied else "Proposed record: ")
            + (
                "absent"
                if result["proposed_record"] is None
                else _display(
                    json.dumps(result["proposed_record"], ensure_ascii=False, sort_keys=True)
                )
            )
        )
        print("Applied changes:" if applied else "Current-to-proposed changes:")
        _changes(result["changes"], indent="  ")
        if not result["applicable"]:
            print("This historical content cannot be restored into the selected inventory.")
        elif result["no_op"]:
            print("The selected state already matches; no revision is needed.")
    print("Published artifacts and human acceptance are unchanged.")
    if result.get("guidance_error"):
        print("Continuation guidance unavailable: " + _display(result["guidance_error"]["message"]))
    for command in result["next_commands"]:
        print(_display(command["label"]) + ": " + _display(command["powershell"]))


def run_command(args) -> int:
    try:
        from image_dataset_train.review_history import (
            inspect_history,
            preview_restore,
            restore_review,
        )

        apply = args.history_action == "restore" and args.apply
        if apply:
            if args.expected_revision is None or args.expected_revision < 0:
                raise ValueError("--apply requires --expected-revision from the current preview")
            if (
                not isinstance(args.expected_plan_sha256, str)
                or len(args.expected_plan_sha256) != 64
                or any(c not in "0123456789abcdef" for c in args.expected_plan_sha256)
            ):
                raise ValueError("--apply requires --expected-plan-sha256 from the current preview")
            if (
                not args.reason
                or not args.reason.strip()
                or not args.reviewer
                or not args.reviewer.strip()
                or args.reviewer_kind is None
            ):
                raise ValueError("--apply requires --reason, --reviewer and --reviewer-kind")
        selected = _select(args)
        if args.history_action == "changes":
            from image_dataset_train.review_changes import inspect_review_changes

            report = select_report(selected, args.report)
            result = inspect_review_changes(
                selected.config,
                selected.run,
                report,
                limit=args.limit,
                offset=args.offset,
                kind=args.kind,
            )
            if (
                _select(args).identity != selected.identity
                or select_report(selected, args.report) != report
            ):
                raise ValueError("Review selection changed during inspection; inspect again")
            result["inspection_sha256"] = _fingerprint(
                {
                    "selection": selected.identity,
                    "report": result["report"],
                    "report_sha256": result["report_sha256"],
                    "current_store_sha256": result["current_store_sha256"],
                    "metadata_sha256": result["metadata_sha256"],
                }
            )
            if (
                args.expected_inspection_sha256 is not None
                and args.expected_inspection_sha256 != result["inspection_sha256"]
            ):
                raise ValueError(
                    "Inspection evidence changed between pages; restart from the first page"
                )
        elif args.history_action == "list":
            result = inspect_history(
                selected.config,
                selected.run,
                image=args.image,
                pair=args.pair,
                limit=args.limit,
                offset=args.offset,
            )
        else:
            preview = preview_restore(
                selected.config, selected.run, args.revision, before=args.before
            )
            core_sha256 = preview["plan_sha256"]
            preview["plan_sha256"] = _fingerprint(
                {
                    "core_plan_sha256": core_sha256,
                    "selection": selected.identity,
                }
            )
            if apply:
                if args.expected_plan_sha256 != preview["plan_sha256"]:
                    raise ValueError(
                        "Restoration preview or collection selection changed; preview again"
                    )

                def guard():
                    if _select(args).identity != selected.identity:
                        raise ValueError(
                            "Review history selection changed before restoration; preview again"
                        )

                result = restore_review(
                    selected.config,
                    selected.run,
                    args.revision,
                    before=args.before,
                    expected_revision=args.expected_revision,
                    expected_plan_sha256=core_sha256,
                    reason=args.reason,
                    reviewer=args.reviewer,
                    reviewer_kind=args.reviewer_kind,
                    guard=guard,
                )
                result["plan_sha256"] = preview["plan_sha256"]
            else:
                result = preview
        result = {**result, "selection": selected.identity}
        # A committed restore must remain successful even when optional command
        # guidance cannot be generated (for example, damaged package metadata).
        result["next_commands"] = []
        try:
            result["next_commands"] = _next_commands(args, selected, result)
        except Exception as exc:
            result["guidance_error"] = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        # Inspection failures and rejected restores must not create application logs.
        result = {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}
        code = 2
    else:
        code = 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    return code
