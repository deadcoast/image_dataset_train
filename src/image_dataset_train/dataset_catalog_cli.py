"""Config-independent command adapters for verified dataset catalog metadata."""

from __future__ import annotations

import json
from pathlib import Path

from image_dataset_train.dataset_catalog import build_catalog, query_catalog, read_catalog

COMMANDS = frozenset({"catalog-build", "catalog-info", "catalog-query"})


def register_commands(subparsers) -> None:
    build = subparsers.add_parser(
        "catalog-build", help="index a verified historical export without changing it"
    )
    build.add_argument("--run", type=Path, required=True, help="published training export")
    build.add_argument(
        "--output", type=Path, required=True, help="root for a new metadata-only index"
    )
    build.add_argument("--json", action="store_true")
    info = subparsers.add_parser(
        "catalog-info", help="verify and summarize dataset catalog metadata"
    )
    info.add_argument("--run", type=Path, required=True, help="export or standalone catalog")
    info.add_argument("--json", action="store_true")
    query = subparsers.add_parser("catalog-query", help="query verified export records as JSON")
    query.add_argument("--run", type=Path, required=True, help="export or standalone catalog")
    query.add_argument("--split", choices=("train", "validation"))
    query.add_argument("--group", dest="group_id")
    query.add_argument("--label", help="explicit saved annotation; never a predicted tag")
    query.add_argument("--text", help="literal caption substring (ASCII case-insensitive)")
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--offset", type=int, default=0)
    query.add_argument("--json", action="store_true", help="JSON is the query output format")


def run_command(args) -> int:
    if args.command == "catalog-build":
        _, result = build_catalog(args.run, output_root=args.output)
    elif args.command == "catalog-info":
        result = read_catalog(args.run)
    elif args.command == "catalog-query":
        result = query_catalog(
            args.run,
            split=args.split,
            group_id=args.group_id,
            label=args.label,
            text=args.text,
            limit=args.limit,
            offset=args.offset,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    else:
        raise ValueError("Unknown catalog command")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Catalog: {result['catalog']}")
        print(f"Images: {result['images']}; groups: {result['groups']}")
        print(
            "Media: "
            + (
                "packaged in this export"
                if result["media_packaged"]
                else "external; metadata-only index"
            )
        )
        print("Verified catalog and metadata; use verify-export to check media bytes.")
    return 0
