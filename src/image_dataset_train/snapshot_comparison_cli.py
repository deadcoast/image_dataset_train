"""Read-only snapshot comparison, with optional immutable report publication."""

from __future__ import annotations

import json
from pathlib import Path

from image_dataset_train.config import load_config
from image_dataset_train.snapshot_comparison import compare_snapshots, publish_comparison

COMMANDS = frozenset({"snapshot-compare"})


def register_commands(commands) -> None:
    parser = commands.add_parser(
        "snapshot-compare", help="verify and compare two group or export snapshots"
    )
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path, help="publish a comparison receipt under this root")
    output.add_argument(
        "--publish", action="store_true", help="publish a receipt under configured runs"
    )
    parser.add_argument(
        "--config", type=Path, help="configuration for --publish; otherwise not required"
    )
    parser.add_argument("--json", action="store_true")


def run_command(args) -> int:
    try:
        if args.config is not None and not args.publish:
            raise ValueError(
                "--config requires --publish; read-only comparison needs no configuration"
            )
        output = (
            load_config(args.config or Path("config.toml")).runs if args.publish else args.output
        )
        if output is None:
            result = compare_snapshots(args.before, args.after)
        else:
            directory, comparison = publish_comparison(args.before, args.after, output_root=output)
            result = {**comparison, "report": str(directory)}
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
            print(f"Snapshot comparison failed: {exc}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = result["summary"]
        print(
            f"Snapshot comparison: {result['kind']}; "
            f"{'changes found' if result['changed'] else 'no changes'}"
        )
        print(
            f"Occurrences: {counts['before_occurrences']} -> {counts['after_occurrences']}; "
            f"unique contents: {counts['before_unique_contents']} "
            f"-> {counts['after_unique_contents']}"
        )
        print(
            f"Added: {counts['added']}; removed: {counts['removed']}; "
            f"changed source content: {counts['changed_content']}"
        )
        print(
            f"Caption text changes: {counts['caption_changes']}; "
            f"caption provenance changes: {counts['caption_provenance_changes']}"
        )
        print(
            f"annotations: {counts['annotation_changes']}; decisions: {counts['decision_changes']}"
        )
        print(
            f"Group merges: {counts['group_merges']}; group splits: {counts['group_splits']}; "
            f"split moves: {counts['split_moves']}"
        )
        if not result["availability"]["effective_captions"]:
            print(
                "Group captions compare saved overrides; "
                "effective captions and training splits are unavailable."
            )
        if result.get("report"):
            print(f"Comparison report: {Path(result['report']) / 'comparison.json'}")
    return 0
