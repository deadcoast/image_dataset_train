"""Preview and atomically apply reviewed annotations to an explicit image selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from image_dataset_train.collection_registry import unlinked_path
from image_dataset_train.implementation import implementation_identity
from image_dataset_train.review_selection import (
    Selection,
    add_selection_arguments,
    command,
    display,
    fingerprint,
    read_metadata_bytes,
    refresh_command,
    select_review,
    selection_args,
)

COMMANDS = {"review-batch"}
SELECTION_FILE_LIMIT = 4 * 1024 * 1024


def register_commands(commands) -> None:
    parser = commands.add_parser(
        "review-batch", help="preview explicit image annotations; --apply saves one atomic batch"
    )
    add_selection_arguments(parser)
    members = parser.add_mutually_exclusive_group(required=True)
    members.add_argument(
        "--image", action="append", help="exact relative image path; repeat for up to 1000 images"
    )
    members.add_argument(
        "--images-file", type=Path, help="UTF-8 JSON list of exact image paths (up to 4 MiB)"
    )
    parser.add_argument("--decision", choices=["include", "exclude", "unreviewed"])
    parser.add_argument("--add-label", action="append", help="reviewed label to add")
    parser.add_argument("--remove-label", action="append", help="reviewed label to remove")
    parser.add_argument(
        "--clear-labels", action="store_true", help="explicitly review labels as empty"
    )
    subset = parser.add_mutually_exclusive_group()
    subset.add_argument("--subset", help="explicit reviewed subset")
    subset.add_argument(
        "--clear-subset", action="store_true", help="explicitly review as unassigned"
    )
    parser.add_argument("--reason", required=True, help="reason for the proposed reviewed changes")
    parser.add_argument("--apply", action="store_true", help="apply this exact inspected preview")
    parser.add_argument("--expected-revision", type=int, help="current revision from the preview")
    parser.add_argument("--expected-plan-sha256", help="exact preview identity")
    parser.add_argument("--reviewer", help="identity of the batch actor")
    parser.add_argument("--reviewer-kind", choices=["human", "assistant", "unknown"])


def _members(args) -> tuple[list[str], dict]:
    if args.images_file is None:
        paths = args.image
        return paths, {"kind": "paths", "paths": sorted(paths)}
    path = unlinked_path(args.images_file)
    raw = read_metadata_bytes(path, limit=SELECTION_FILE_LIMIT)
    paths = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(paths, list) or any(not isinstance(value, str) for value in paths):
        raise ValueError("--images-file must contain a JSON list of exact relative image paths")
    return paths, {
        "kind": "file",
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _operations(args) -> dict:
    return {
        "decision": args.decision,
        "add_labels": args.add_label,
        "remove_labels": args.remove_label,
        "clear_labels": args.clear_labels,
        "subset": args.subset,
        "clear_subset": args.clear_subset,
        "reason": args.reason,
    }


def _refresh_command(selected: Selection) -> dict:
    return refresh_command(selected, identity_provider=implementation_identity)


def _next_commands(args, selected: Selection, membership: dict, result: dict) -> list[dict]:
    if args.apply:
        return [_refresh_command(selected)] if result["status"] == "applied" else []
    if not result["changed_count"]:
        return []
    argv = ["dataset", "review-batch", *selection_args(selected)]
    if membership["kind"] == "file":
        argv += ["--images-file", membership["path"]]
    else:
        for path in membership["paths"]:
            argv += ["--image", path]
    if args.decision is not None:
        argv += ["--decision", args.decision]
    for option, values in [("--add-label", args.add_label), ("--remove-label", args.remove_label)]:
        for value in values or []:
            argv += [option, value]
    if args.clear_labels:
        argv.append("--clear-labels")
    if args.subset is not None:
        argv += ["--subset", args.subset]
    if args.clear_subset:
        argv.append("--clear-subset")
    argv += [
        "--reason",
        args.reason,
        "--apply",
        "--expected-revision",
        str(result["current_revision"]),
        "--expected-plan-sha256",
        result["plan_sha256"],
        "--reviewer",
        args.reviewer or "<reviewer>",
        "--reviewer-kind",
        args.reviewer_kind or "<human|assistant|unknown>",
    ]
    return [command("Apply this exact selection after supplying its actor", argv)]


def _record(record) -> str:
    return (
        "absent"
        if record is None
        else display(json.dumps(record, ensure_ascii=False, sort_keys=True))
    )


def _render(result) -> None:
    if result.get("status") == "failed":
        print("Bulk review: " + display(result["error"]["message"]))
        return
    applied = result.get("status") == "applied"
    revision = result["revision"] if applied else result["current_revision"]
    print("Bulk review: " + result.get("status", "preview"))
    print("Source: " + display(result["source"]))
    print(f"Current review revision: {revision}")
    if result["selection"].get("job_id"):
        print("Selected job: " + display(result["selection"]["job_id"]))
    print(f"Selected images: {result['selected_count']}; changed images: {result['changed_count']}")
    print("Reason: " + display(result["reason"]))
    for index, member in enumerate(result["members"], 1):
        print(f"  {index}. " + display(member["source_path"]))
        print("    SHA256: " + member["sha256"])
        print(
            ("    Previous: " if applied else "    Current: ") + _record(member["current_record"])
        )
        print(("    Saved: " if applied else "    Proposed: ") + _record(member["proposed_record"]))
        if not member["changes"]:
            print("    Unchanged.")
        for change in member["changes"]:
            before = (
                display(json.dumps(change["before"], ensure_ascii=False, sort_keys=True))
                if change["before_present"]
                else "<absent>"
            )
            after = (
                display(json.dumps(change["after"], ensure_ascii=False, sort_keys=True))
                if change["after_present"]
                else "<absent>"
            )
            print("    " + display(change["field"]) + ": " + before + " -> " + after)
    if applied:
        print("Saved batch: " + result["batch_id"])
    elif result.get("status") == "unchanged":
        print("All selected source identities checked; no changes or history revisions saved.")
    else:
        print("Preview SHA256: " + result["plan_sha256"])
        if not result["changed_count"]:
            print("All selected records already match; no history revisions are needed.")
    print("Published artifacts and human acceptance are unchanged.")
    if result.get("guidance_error"):
        print("Continuation guidance unavailable: " + display(result["guidance_error"]["message"]))
    for item in result["next_commands"]:
        print(display(item["label"]) + ": " + display(item["powershell"]))


def run_command(args) -> int:
    try:
        from image_dataset_train.review_batch import apply_batch, preview_batch

        if args.apply:
            if args.expected_revision is None or args.expected_revision < 0:
                raise ValueError("--apply requires --expected-revision from the current preview")
            token = args.expected_plan_sha256
            if (
                not isinstance(token, str)
                or len(token) != 64
                or any(c not in "0123456789abcdef" for c in token)
            ):
                raise ValueError("--apply requires --expected-plan-sha256 from the current preview")
            if not args.reviewer or not args.reviewer.strip() or args.reviewer_kind is None:
                raise ValueError("--apply requires --reviewer and --reviewer-kind")
        selected = select_review(args)
        paths, membership = _members(args)
        operations = _operations(args)
        preview = preview_batch(selected.config, selected.run, paths, **operations)
        core_sha256 = preview["plan_sha256"]
        preview["plan_sha256"] = fingerprint(
            {
                "core_plan_sha256": core_sha256,
                "selection": selected.identity,
                "membership": membership,
            }
        )
        if args.apply:
            if args.expected_plan_sha256 != preview["plan_sha256"]:
                raise ValueError("Bulk review preview or selection changed; preview again")

            def guard():
                if select_review(args).identity != selected.identity:
                    raise ValueError("Review selection changed before bulk apply; preview again")
                if _members(args)[1] != membership:
                    raise ValueError("Image selection changed before bulk apply; preview again")

            result = apply_batch(
                selected.config,
                selected.run,
                paths,
                **operations,
                expected_revision=args.expected_revision,
                expected_plan_sha256=core_sha256,
                reviewer=args.reviewer,
                reviewer_kind=args.reviewer_kind,
                guard=guard,
            )
            result["plan_sha256"] = preview["plan_sha256"]
        else:
            result = preview
        result = {**result, "selection": selected.identity, "membership": membership}
        result["next_commands"] = []
        try:
            result["next_commands"] = _next_commands(args, selected, membership, result)
        except Exception as exc:
            result["guidance_error"] = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        result = {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}
        code = 2
    else:
        code = 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    return code
