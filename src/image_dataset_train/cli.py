"""Command line interface for the implemented pipeline stages."""

from __future__ import annotations

import argparse
import json
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
    similarity = commands.add_parser(
        "similarity",
        help="propose perceptually similar image pairs for review; never changes sources",
    )
    similarity.add_argument("--inventory", type=Path, required=True)
    similarity.add_argument("--config", type=Path, default=Path("config.toml"))
    similarity.add_argument(
        "--max-distance",
        type=int,
        choices=range(65),
        metavar="0..64",
        default=8,
        help="maximum 64-bit pHash Hamming distance for a review proposal (default: 8)",
    )
    review = commands.add_parser(
        "review", help="review pairs, image decisions, and caption overrides"
    )
    review.add_argument("--run", type=Path, required=True, help="published similarity run")
    review.add_argument("--config", type=Path, default=Path("config.toml"))
    target = review.add_mutually_exclusive_group()
    target.add_argument("--pair", help="pair ID or unambiguous prefix (at least 8 characters)")
    target.add_argument("--image", help="exact relative image path in the inventory")
    target.add_argument(
        "--images", action="store_true", help="list images awaiting include/exclude review"
    )
    target.add_argument(
        "--unannotated",
        action="store_true",
        help="list included images missing reviewed labels or a subset choice",
    )
    target.add_argument(
        "--link", nargs=2, metavar=("LEFT", "RIGHT"), help="review any two image paths"
    )
    review.add_argument(
        "--decision", choices=["related", "distinct", "include", "exclude", "unreviewed"]
    )
    review.add_argument("--reason", default="", help="reason for changing a decision or caption")
    caption = review.add_mutually_exclusive_group()
    caption.add_argument("--caption", help="durable manual caption override")
    caption.add_argument("--caption-file", type=Path, help="read a UTF-8 caption override")
    caption.add_argument(
        "--clear-caption", action="store_true", help="clear only the saved override"
    )
    review.add_argument("--label", action="append", help="add a reviewed label; repeat for more")
    review.add_argument("--remove-label", action="append", help="remove a reviewed label")
    review.add_argument("--clear-labels", action="store_true", help="record an empty label set")
    subset = review.add_mutually_exclusive_group()
    subset.add_argument("--subset", help="set the reviewed semantic subset")
    subset.add_argument(
        "--subset-from", type=Path, help="accept this image's subset proposal from a caption run"
    )
    subset.add_argument("--clear-subset", action="store_true", help="record no subset assignment")
    review.add_argument("--limit", type=int, default=20, help="maximum entries displayed")
    review.add_argument("--all", action="store_true", help="include previously reviewed entries")
    review.add_argument("--json", action="store_true", help="structured result")
    groups = commands.add_parser("groups", help="publish reviewed related-image groups")
    groups.add_argument("--run", type=Path, required=True, help="published similarity run")
    groups.add_argument("--config", type=Path, default=Path("config.toml"))
    export = commands.add_parser(
        "export", help="split reviewed groups and copy verified training pairs"
    )
    export.add_argument("--groups", type=Path, required=True, help="published group snapshot")
    export.add_argument("--captions", type=Path, help="tagging/recaption run for missing captions")
    export.add_argument("--config", type=Path, default=Path("config.toml"))
    export.add_argument(
        "--output", type=Path, help="export root; each invocation creates a snapshot"
    )
    export.add_argument(
        "--validation-ratio", type=float, help="held-out image ratio (default: 0.05)"
    )
    export.add_argument("--seed", type=int, help="deterministic split seed (default: 20261011)")
    export.add_argument("--resolution", type=int, help="trainer bucket resolution (default: 1024)")
    export.add_argument("--repeats", type=int, help="training repeats (default: 1)")
    export.add_argument(
        "--split-strategy",
        choices=["semantic", "size"],
        help="balance reviewed semantics or image counts only",
    )
    verify = commands.add_parser(
        "verify-export", help="verify an export without its source collection"
    )
    verify.add_argument("--run", type=Path, required=True, help="published export snapshot")
    setup = commands.add_parser(
        "trainer-setup", help="install the isolated pinned CPU import runtime"
    )
    setup.add_argument("--runtime", type=Path, default=Path(".cache/trainer"))
    trainer = commands.add_parser("trainer-check", help="import an export with the pinned trainer")
    trainer.add_argument("--run", type=Path, required=True, help="verified export snapshot")
    trainer.add_argument("--runtime", type=Path, default=Path(".cache/trainer"))
    trainer.add_argument("--config", type=Path, default=Path("config.toml"))
    trainer_status = commands.add_parser(
        "trainer-status", help="show export-bound trainer import receipts and qualification"
    )
    trainer_status.add_argument("--run", type=Path, required=True, help="published export snapshot")
    trainer_status.add_argument("--config", type=Path, default=Path("config.toml"))
    trainer_status.add_argument("--json", action="store_true")
    qa = commands.add_parser("qa", help="publish a pilot QA report with local image navigation")
    qa.add_argument("--run", type=Path, required=True, help="group snapshot or verified export")
    qa.add_argument("--captions", type=Path, help="optional tagging/recaption run for group QA")
    qa.add_argument("--json", action="store_true", help="print the saved snapshot summary as JSON")
    qa.add_argument(
        "--sample-size", type=int, default=50, help="maximum pilot images (default: 50)"
    )
    qa.add_argument(
        "--seed",
        type=int,
        default=20261011,
        help="pilot selection seed; preview split assignments use the export configuration",
    )
    qa.add_argument("--config", type=Path, default=Path("config.toml"))
    ui = commands.add_parser("review-ui", help="edit reviews and assess a pilot in a local browser")
    ui.add_argument("--run", type=Path, required=True, help="saved QA report")
    ui.add_argument("--config", type=Path, help="defaults to the QA report's saved configuration")
    ui.add_argument(
        "--port", type=int, default=0, help="loopback port; default chooses a free port"
    )
    ui.add_argument(
        "--no-open", action="store_true", help="print the URL without opening a browser"
    )
    assessment = commands.add_parser(
        "assessment", help="show recorded pilot judgments and conclusion"
    )
    assessment.add_argument("--run", type=Path, required=True, help="saved QA report")
    assessment.add_argument(
        "--config", type=Path, help="defaults to the QA report's saved configuration"
    )
    assessment.add_argument("--json", action="store_true")
    queue = commands.add_parser("qa-list", help="filter and page through a saved QA report")
    queue.add_argument("--run", type=Path, required=True)
    for name in ("finding", "label", "subset", "group"):
        queue.add_argument("--" + name)
    queue.add_argument("--split", choices=["train", "validation", "unassigned"])
    queue.add_argument("--pilot", action="store_true")
    queue.add_argument("--offset", type=int, default=0)
    queue.add_argument("--limit", type=int, default=20)
    queue.add_argument("--json", action="store_true")
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
        if args.command == "qa-list":
            from image_dataset_train.qa import list_qa

            result = list_qa(
                args.run,
                finding=args.finding,
                label=args.label,
                subset=args.subset,
                split=args.split,
                group=args.group,
                pilot=args.pilot,
                offset=args.offset,
                limit=args.limit,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Matches: {result['total']}; offset: {result['offset']}")
                for entry in result["entries"]:
                    print(
                        f"{entry['source_path']}  {entry['split']}  {', '.join(entry['findings'])}"
                    )
                    print(entry["review_commands"]["powershell"])
                    analysis = entry.get("caption_analysis") or {}
                    if analysis.get("subset_proposal"):
                        print(
                            "Subset proposal: "
                            + json.dumps(analysis["subset_proposal"], ensure_ascii=False)
                        )
                if result["next_offset"] is not None:
                    print(f"Continue with --offset {result['next_offset']}")
            return 0
        if args.command == "trainer-setup":
            from image_dataset_train.trainer import setup_trainer

            print("Preparing the pinned CPU trainer import runtime...", flush=True)
            print(json.dumps(setup_trainer(args.runtime), indent=2))
            return 0
        if args.command == "verify-export":
            from image_dataset_train.exporting import verify_export

            print(json.dumps(verify_export(args.run), indent=2))
            return 0
        if args.command in {"review-ui", "assessment"} and args.config is None:
            from image_dataset_train.qa import read_qa

            meta, data = read_qa(args.run)
            if meta.get("config_path"):
                args.config = Path(meta["config_path"])
            elif data["entries"]:
                command = data["entries"][0]["review_args"]
                args.config = Path(command[command.index("--config") + 1])
            else:
                args.config = Path("config.toml")
        config = load_config(args.config)
        if args.command == "review-ui":
            from image_dataset_train.review_ui import serve_reviews

            serve_reviews(
                config, args.run, args.port, open_browser=not args.no_open, config_path=args.config
            )
            return 0
        if args.command == "assessment":
            from image_dataset_train.assessments import PilotAssessment

            result = PilotAssessment(config.reviews, args.run).summary()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Pilot assessed: {result['assessed_images']}/{result['pilot_images']}")
                print("Verdicts: " + json.dumps(result["verdicts"]))
                print(
                    "Critical labels: " + json.dumps(result["critical_labels"], ensure_ascii=False)
                )
                print("Conclusion: " + json.dumps(result["conclusion"], ensure_ascii=False))
                print(f"Saved assessment: {result['assessment_file']}")
            return 0
        if args.command == "qa":
            from image_dataset_train.qa import create_qa

            directory, summary = create_qa(
                config,
                args.run,
                captions_run=args.captions,
                sample_size=args.sample_size,
                seed=args.seed,
                config_path=args.config,
            )
            if args.json:
                print(json.dumps({"run": str(directory), **summary}, ensure_ascii=False, indent=2))
                return 0
            print(f"Pilot QA report: {directory / 'report.html'}")
            print(
                f"Images: {summary['images']}; pilot: {summary['pilot_images']}; "
                f"split state: {summary['split_state']}"
            )
            print("Findings: " + json.dumps(summary["findings"], ensure_ascii=False))
            content = summary["content"]["scopes"]["included"]
            print(
                f"Included content: {content['images']} images; "
                f"{content['tagged_images']} with matching tagging evidence"
            )
            print("Model rating counts: " + json.dumps(content["ratings"], ensure_ascii=False))
            print(
                "Top observed tags: "
                + ", ".join(
                    f"{tag['name']} ({tag['images']})"
                    for tag in content["observed_tags"]["top_tags"][:10]
                )
            )
            provenance = summary["content"]["provenance"] or {}
            print(
                "Model/provider provenance: "
                + json.dumps(
                    {key: provenance.get(key) for key in ("model", "runtime", "provider_fallback")},
                    ensure_ascii=False,
                )
            )
            print(f"Complete snapshot summary: {directory / 'summary.json'}")
            print("Use dataset qa-list --run <this-report> to navigate findings in the terminal.")
            return 0
        if args.command == "trainer-status":
            from image_dataset_train.trainer_receipts import trainer_status

            result = trainer_status(args.run, config.runs)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"CPU dataset import: {result['status']}")
                print(f"Receipts: {result['receipt_root']}")
                for receipt in result["receipts"]:
                    print(f"{receipt['completed_at']}  {receipt['status']}  {receipt['path']}")
                if result.get("error"):
                    print(result["error"])
                for error in result["discovery_errors"]:
                    print(f"Could not read {error['path']}: {error['error']}")
                print(
                    "Scope: CPU dataset import; no tokenization, GPU training, or pilot acceptance."
                )
            return 0 if result["status"] == "passed" else 1
        if args.command == "trainer-check":
            from image_dataset_train.trainer import check_trainer

            print("Importing image/caption pairs with the pinned trainer...", flush=True)
            directory, result = check_trainer(config, args.run, args.runtime)
            print(f"Trainer import report: {directory}")
            if not result["qualified"]:
                print(f"Import failed: {result.get('error', 'See loader.log')}", file=sys.stderr)
                return 1
            print(json.dumps(result["splits"], indent=2))
            print("CPU dataset import passed. Model training and tokenization were not run.")
            return 0
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

        if args.command == "export":
            from image_dataset_train.exporting import export_dataset

            options = {
                key: getattr(args, key)
                for key in ("validation_ratio", "seed", "resolution", "repeats", "split_strategy")
                if getattr(args, key) is not None
            }
            config = replace(
                config,
                export=replace(config.export, **options),
                exports=args.output.resolve() if args.output else config.exports,
            )
            directory, summary = export_dataset(
                config,
                args.groups,
                captions_run=args.captions,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
            print(f"Verified training pairs: {directory}")
            print(
                f"Images: {summary['images']}; groups: {summary['groups']}; "
                f"splits: {summary['split_images']}"
            )
            print(
                f"Validation ratio: {summary['actual_validation_ratio']:.2%} "
                f"(requested {summary['requested_validation_ratio']:.2%})"
            )
            for warning in summary["warnings"]:
                print(f"Note: {warning}")
            annotations = summary["annotations"]
            print(
                f"Split method: {summary['split_algorithm']}; "
                f"labels reviewed: {annotations['labels_reviewed']}/{annotations['images']}; "
                f"subsets reviewed: {annotations['subset_reviewed']}/{annotations['images']}"
            )
            print("Next: dataset trainer-check --run <this-export> for pinned CPU import.")
            return 0

        if args.command in {"review", "groups"}:
            from image_dataset_train.reviews import (
                publish_groups,
                review_image,
                review_link,
                review_pair,
                review_status,
            )

            if args.command == "groups":
                directory, summary = publish_groups(config, args.run)
                print(f"Group snapshot: {directory}")
                print(f"Groups: {summary['groups']}; images retained: {summary['images']}")
                print(
                    f"Unresolved pairs: {summary['unresolved_pairs']}; "
                    f"image decisions: {summary['image_decisions']}"
                )
                print(
                    f"Review complete: {summary['review_complete']}; "
                    f"conflicts: {len(summary['conflicts'])}; "
                    f"similarity errors: {summary['similarity_errors']}"
                )
                print("Next: dataset export --groups <this-snapshot> [--captions <tagging-run>]")
                return 0 if summary["review_complete"] else 1
            has_caption = (
                args.caption is not None or args.caption_file is not None or args.clear_caption
            )
            has_annotations = args.subset_from is not None or (
                args.label is not None
                or args.remove_label is not None
                or args.clear_labels
                or args.subset is not None
                or args.clear_subset
            )
            if args.pair or args.link:
                if has_caption or has_annotations:
                    raise ValueError("Caption overrides and annotations require --image.")
                if args.decision is None:
                    raise ValueError("Provide --decision related, distinct, or unreviewed.")
                action = review_link if args.link else review_pair
                result = action(
                    config, args.run, args.link or args.pair, args.decision, args.reason
                )
            elif args.image:
                text = args.caption
                if args.caption_file is not None:
                    text = args.caption_file.read_text(encoding="utf-8")
                result = review_image(
                    config,
                    args.run,
                    args.image,
                    decision=args.decision,
                    reason=args.reason,
                    caption=text,
                    clear_caption=args.clear_caption,
                    add_labels=args.label,
                    remove_labels=args.remove_label,
                    clear_labels=args.clear_labels,
                    subset=args.subset,
                    subset_from=args.subset_from,
                    clear_subset=args.clear_subset,
                )
            else:
                if args.decision is not None or args.reason or has_caption or has_annotations:
                    raise ValueError("Select --pair, --link, or --image when changing a review.")
                result = review_status(
                    config,
                    args.run,
                    limit=args.limit,
                    show_all=args.all,
                    image_view=args.images,
                    unannotated=args.unannotated,
                )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif "pair_counts" in result:
                print(f"Source: {result['source']}")
                print(
                    f"Pair decisions: {result['pair_counts']}; "
                    f"image decisions: {result['image_counts']}"
                )
                for pair in result.get("pairs", []):
                    print(
                        f"{pair['pair_id'][:12]}  {pair['left_source_path']} <-> "
                        f"{pair['right_source_path']}  distance={pair['hamming_distance']}  "
                        f"{pair['decision']}"
                    )
                for image in result.get("images", []):
                    print(
                        f"{image['source_path']}  {image['decision']}  "
                        f"labels={', '.join(image['labels']) or '(none)'}  "
                        f"subset={image['subset'] or '(unassigned)'}"
                    )
                if not result.get("pairs") and not result.get("images"):
                    print("No entries match this view.")
                if result["stale_pair_decisions"] or result["stale_image_decisions"]:
                    print(
                        f"Stale reviews retained: {result['stale_pair_decisions']} pairs, "
                        f"{result['stale_image_decisions']} images."
                    )
                if result["similarity_errors"]:
                    print(f"Similarity errors still need attention: {result['similarity_errors']}")
                print(f"Review state: {result['review_file']} (revision {result['revision']})")
            else:
                print(f"{result.get('source_path', result.get('pair_id'))}: {result['decision']}")
                if result.get("caption_override") is not None:
                    print(f"Caption override: {result['caption_override']}")
                if "labels" in result:
                    print(f"Labels: {', '.join(result['labels']) or '(none)'}")
                    print(f"Subset: {result['subset'] or '(unassigned)'}")
                if "review_file" in result:
                    print(f"Saved review: {result['review_file']} (revision {result['revision']})")
            return 0

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
                "Use dataset review, dataset groups, then dataset export to publish training pairs."
            )
            return 1 if summary["decisions"].get("error") else 0

        if args.command == "similarity":
            from image_dataset_train.similarity import propose_similar

            directory, summary = propose_similar(
                config,
                args.inventory,
                max_distance=args.max_distance,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
            print(f"Similarity review proposals: {directory}")
            print(
                f"Images hashed: {summary['images_hashed']}/{summary['images_considered']}; "
                f"pairs to review: {summary['pairs_proposed']}; errors: {summary['errors']}"
            )
            print(
                f"Skipped: {summary['exact_duplicates_skipped']} exact duplicates; "
                f"{summary['ineligible_images_skipped']} ineligible images."
            )
            print(
                "This command does not write source files. Proposals are not duplicate decisions."
            )
            return 1 if summary["errors"] else 0

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
    print(
        "Inventory only. Next: dataset similarity and dataset tag, then review, groups, and export."
    )
    return 1 if summary["decisions"].get("error") else 0
