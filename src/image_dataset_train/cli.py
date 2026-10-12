"""Command line interface for the implemented pipeline stages."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from image_dataset_train import __version__
from image_dataset_train.config import load_config
from image_dataset_train.diagnostics import EventLog, app_home, failure_text
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
    from image_dataset_train.model_bundle import MODELS

    fetch = commands.add_parser("fetch-model", help="download a pinned WD model and its labels")
    fetch.add_argument("--config", type=Path, default=Path("config.toml"))
    fetch.add_argument("--model", choices=MODELS)
    tag = commands.add_parser(
        "tag", help="tag an inventory locally; preserve sources and raw scores"
    )
    tag.add_argument("--inventory", type=Path, required=True)
    tag.add_argument("--config", type=Path, default=Path("config.toml"))
    tag.add_argument("--model", choices=MODELS)
    tag.add_argument("--device", choices=["auto", "cpu", "cuda"])
    tag.add_argument("--batch-size", type=int)
    recaption = commands.add_parser(
        "recaption", help="change captions using saved scores; no inference"
    )
    recaption.add_argument("--run", type=Path, required=True)
    recaption.add_argument("--config", type=Path, default=Path("config.toml"))
    for command in (tag, recaption):
        command.add_argument("--threshold", type=float, help="override general tag threshold")
        command.add_argument("--keep-characters", action="store_true", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if getattr(args, "source", None) is not None:
            config = replace(config, source=args.source.resolve())
        if getattr(args, "runs", None) is not None:
            config = replace(config, runs=args.runs.resolve())
        if getattr(args, "model", None) is not None:
            config = replace(
                config, tagging=replace(config.tagging, model=args.model, revision=None)
            )
        if getattr(args, "device", None) is not None:
            config = replace(config, tagging=replace(config.tagging, device=args.device))
        if getattr(args, "batch_size", None) is not None:
            config = replace(config, tagging=replace(config.tagging, batch_size=args.batch_size))
        if getattr(args, "threshold", None) is not None:
            config = replace(
                config, captions=replace(config.captions, general_threshold=args.threshold)
            )
        if getattr(args, "keep_characters", None) is not None:
            config = replace(config, captions=replace(config.captions, keep_characters=True))

        if args.command == "fetch-model":
            from image_dataset_train.model_bundle import fetch_bundle

            source, models = config.source.resolve(), config.models.resolve()
            if source.is_relative_to(models) or models.is_relative_to(source):
                raise ValueError("source and model directories must be separate trees")
            print(f"Fetching pinned model: {config.tagging.model}", flush=True)
            print(fetch_bundle(models, config.tagging.model, config.tagging.revision))
            return 0

        if args.command in {"tag", "recaption"}:
            from image_dataset_train.tagging import recaption, tag_inventory

            if args.command == "tag":
                directory, summary = tag_inventory(
                    config,
                    args.inventory,
                    lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                directory, summary = recaption(config, args.run)
            print(f"Caption drafts: {directory}")
            print("; ".join(f"{name}: {count}" for name, count in summary["decisions"].items()))
            print(
                f"Inferred: {summary['inferred_images']}; "
                f"unique scores: {summary['unique_scored_images']}"
            )
            print(
                "Draft captions and scores saved separately. "
                "Review and training export remain pending."
            )
            return 1 if summary["decisions"].get("error") else 0

        def progress(count: int) -> None:
            if count % 100 == 0:
                print(f"Scanned {count} files", file=sys.stderr, flush=True)

        directory, summary = run_scan(config, progress)
    except ImportError as exc:
        print(
            "error: " + failure_text(exc, EventLog(app_home()), action=args.command),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            "error: " + failure_text(exc, EventLog(app_home()), action=args.command),
            file=sys.stderr,
        )
        return 2
    print(f"Inventory: {directory}")
    print(f"Files: {summary['files_seen']}; images: {summary['images_seen']}")
    print("; ".join(f"{name}: {count}" for name, count in summary["decisions"].items()))
    print("Inventory only. Tagging, review, and training export remain pending.")
    return 1 if summary["decisions"].get("error") else 0
