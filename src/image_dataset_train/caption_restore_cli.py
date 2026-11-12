"""Configuration-independent caption restoration command adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from image_dataset_train.caption_restore import restore_captions

COMMANDS = frozenset({"restore-captions"})


def register_commands(subparsers) -> None:
    command = subparsers.add_parser(
        "restore-captions", help="restore verified removed captions without overwriting newer files"
    )
    command.add_argument(
        "--receipt",
        type=Path,
        required=True,
        help="saved remove operation directory or operation.json",
    )
    command.add_argument(
        "--dryrun", "--dry-run", action="store_true", help="read-only recovery preview"
    )
    command.add_argument("--json", action="store_true")
    command.add_argument(
        "--expected-sha256", help="reject a removal receipt that changed since selection"
    )
    command.add_argument(
        "--expected-plan-sha256", help="reject a removal plan that changed since selection"
    )


def run_command(args) -> int:
    try:
        result = restore_captions(
            args.receipt,
            dryrun=args.dryrun,
            expected_sha256=args.expected_sha256,
            expected_plan_sha256=args.expected_plan_sha256,
        )
    except KeyboardInterrupt:
        print(
            "Caption restoration cancelled; saved recovery evidence is retained.", file=sys.stderr
        )
        return 130
    except Exception as exc:
        # A rejected preview/selection must not create application error logs.
        error = {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}
        if args.json:
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(f"Caption restoration failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Caption restoration: {result['status']}")
        print("Counts: " + json.dumps(result["counts"], sort_keys=True))
        if result["report"]:
            print(f"Recovery receipt: {result['report']}")
        for item in result["items"]:
            if item["status"] in {"conflict", "unverifiable"}:
                print(f"Kept {item['caption']}: {item['reason']}")
    return int(any(result["counts"].get(kind, 0) for kind in ("conflict", "unverifiable")))
