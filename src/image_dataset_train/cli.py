"""Command line interface for the implemented pipeline stages."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from image_dataset_train import __version__
from image_dataset_train.config import load_config
from image_dataset_train.runs import run_scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare local image datasets; preserve originals."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="inventory, validate, and identify exact duplicates")
    scan.add_argument("--config", type=Path, default=Path("config.toml"))
    scan.add_argument(
        "--source", type=Path, help="source override, relative to the current directory"
    )
    scan.add_argument(
        "--runs", type=Path, help="report root override, relative to the current directory"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.source is not None:
            config = replace(config, source=args.source.resolve())
        if args.runs is not None:
            config = replace(config, runs=args.runs.resolve())

        def progress(count: int) -> None:
            if count % 100 == 0:
                print(f"Scanned {count} files", file=sys.stderr, flush=True)

        directory, summary = run_scan(config, progress)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Inventory: {directory}")
    print(f"Files: {summary['files_seen']}; images: {summary['images_seen']}")
    print("; ".join(f"{name}: {count}" for name, count in summary["decisions"].items()))
    print("Inventory only. Tagging, review, and training export remain pending.")
    return 1 if summary["decisions"].get("error") else 0
