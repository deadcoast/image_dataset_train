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
    from image_dataset_train.caption_explanations_cli import register_commands as explain_commands
    from image_dataset_train.caption_restore_cli import register_commands as restore_commands
    from image_dataset_train.collection_catalog_cli import register_commands as collection_commands
    from image_dataset_train.dataset_catalog_cli import register_commands as catalog_commands
    from image_dataset_train.preparation_cli import register_commands as preparation_commands
    from image_dataset_train.recovery_catalog_cli import register_commands as recovery_commands
    from image_dataset_train.review_batch_cli import register_commands as batch_commands
    from image_dataset_train.review_history_cli import register_commands as history_commands
    from image_dataset_train.snapshot_comparison_cli import register_commands as comparison_commands

    preparation_commands(commands)
    recovery_commands(commands)
    batch_commands(commands)
    history_commands(commands)
    collection_commands(commands)
    catalog_commands(commands)
    restore_commands(commands)
    comparison_commands(commands)
    explain_commands(commands)
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
    evaluation = commands.add_parser(
        "similarity-evaluate", help="measure pHash thresholds against saved pair judgments"
    )
    evaluation.add_argument("--run", type=Path, required=True, help="published similarity run")
    evaluation.add_argument("--config", type=Path, default=Path("config.toml"))
    evaluation.add_argument("--json", action="store_true")
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
    review.add_argument(
        "--evaluation-set",
        choices=["calibration", "held_out"],
        help="save this pair in the M2 calibration or held-out evaluation set",
    )
    review.add_argument(
        "--clear-evaluation-set",
        action="store_true",
        help="remove this pair's calibration/held-out assignment",
    )
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
        "--image",
        action="append",
        help="exact source path to include in the frozen pilot; repeatable",
    )
    qa.add_argument("--reason", help="reason for the explicit pilot membership (requires --image)")
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
    label_pilot = commands.add_parser(
        "label-pilot", help="freeze a QA pilot and raw label vocabulary for model evaluation"
    )
    label_pilot.add_argument("--run", type=Path, required=True, help="saved group QA report")
    label_pilot.add_argument("--reference", type=Path, required=True, help="saved scored run")
    label_pilot.add_argument("--label", action="append", required=True, help="raw WD tag name")
    label_pilot.add_argument(
        "--image",
        action="append",
        help="explicit source path from QA; repeat to freeze a chosen set",
    )
    label_pilot.add_argument("--reason", required=True, help="selection rationale and known bias")
    label_pilot.add_argument("--seed", type=int, default=20261011)
    label_pilot.add_argument(
        "--probability-sample-size", type=int, help="draw unique original contents from the full QA"
    )
    label_pilot.add_argument(
        "--selection-seed", type=int, help="explicit probability draw seed, separate from --seed"
    )
    label_pilot.add_argument(
        "--partition-groups",
        type=Path,
        help="verified full-population groups used only for partitioning",
    )
    label_pilot.add_argument("--held-out-fraction", type=float, default=0.33)
    label_pilot.add_argument("--config", type=Path, default=Path("config.toml"))
    label_pilot.add_argument("--json", action="store_true")
    label_refresh = commands.add_parser(
        "label-refresh", help="carry a frozen pilot and judgments into a corrected group snapshot"
    )
    label_refresh.add_argument("--workspace", type=Path, required=True)
    label_refresh.add_argument(
        "--groups", type=Path, required=True, help="new published group snapshot"
    )
    label_refresh.add_argument("--reason", required=True, help="reason for correcting grouping")
    label_refresh.add_argument("--expected-revision", type=int, required=True)
    label_refresh.add_argument("--config", type=Path, default=Path("config.toml"))
    label_refresh.add_argument("--json", action="store_true")
    label_review = commands.add_parser(
        "label-review", help="show or save actual label presence independently of predictions"
    )
    label_review.add_argument("--workspace", type=Path, required=True)
    label_review.add_argument("--image", help="exact frozen source path or image SHA256")
    label_review.add_argument("--label", help="raw tag in the frozen vocabulary")
    label_review.add_argument("--value", choices=["present", "absent", "uncertain", "unreviewed"])
    label_review.add_argument("--reviewer")
    label_review.add_argument("--reviewer-kind", choices=["human", "assistant"])
    label_review.add_argument("--notes")
    label_review.add_argument("--expected-revision", type=int)
    label_review.add_argument("--json", action="store_true")
    label_ui = commands.add_parser(
        "label-ui", help="review frozen critical labels in a local browser"
    )
    label_ui.add_argument("--workspace", type=Path, required=True)
    label_ui.add_argument(
        "--run", type=Path, action="append", default=[], help="optional scored comparison"
    )
    label_ui.add_argument("--config", type=Path)
    label_ui.add_argument("--port", type=int, default=0)
    label_ui.add_argument("--no-open", action="store_true")
    label_eval = commands.add_parser(
        "tag-evaluate", help="compare saved scores and fit thresholds using frozen label judgments"
    )
    label_eval.add_argument("--workspace", type=Path, required=True)
    label_eval.add_argument(
        "--run", type=Path, action="append", required=True, help="repeat per model"
    )
    label_eval.add_argument(
        "--include-assistant", action="store_true", help="include diagnostic judgments"
    )
    label_eval.add_argument("--config", type=Path, default=Path("config.toml"))
    label_eval.add_argument("--json", action="store_true")
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
        from image_dataset_train import (
            caption_explanations_cli,
            caption_restore_cli,
            collection_catalog_cli,
            dataset_catalog_cli,
            preparation_cli,
            recovery_catalog_cli,
            review_batch_cli,
            review_history_cli,
            snapshot_comparison_cli,
        )

        if args.command in preparation_cli.COMMANDS:
            return preparation_cli.run_command(args)
        if args.command in recovery_catalog_cli.COMMANDS:
            return recovery_catalog_cli.run_command(args)
        if args.command in review_batch_cli.COMMANDS:
            return review_batch_cli.run_command(args)
        if args.command in review_history_cli.COMMANDS:
            return review_history_cli.run_command(args)
        if args.command in collection_catalog_cli.COMMANDS:
            return collection_catalog_cli.run_command(args)
        if args.command in dataset_catalog_cli.COMMANDS:
            return dataset_catalog_cli.run_command(args)
        if args.command in caption_restore_cli.COMMANDS:
            return caption_restore_cli.run_command(args)
        if args.command in snapshot_comparison_cli.COMMANDS:
            return snapshot_comparison_cli.run_command(args)
        if args.command in caption_explanations_cli.COMMANDS:
            return caption_explanations_cli.run_command(args)
        if args.command == "label-ui":
            from image_dataset_train.label_review_ui import serve_label_reviews
            from image_dataset_train.label_workspace import LabelWorkspace

            workspace = LabelWorkspace(args.workspace)
            qa_meta = json.loads(
                (Path(workspace.selection["qa_run"]) / "run.json").read_text(encoding="utf-8")
            )
            config_path = args.config or Path(qa_meta["config_path"])
            serve_label_reviews(
                load_config(config_path),
                args.workspace,
                scored_runs=tuple(args.run),
                port=args.port,
                open_browser=not args.no_open,
            )
            return 0
        if args.command == "label-review":
            from image_dataset_train.label_workspace import LabelWorkspace

            workspace = LabelWorkspace(args.workspace)
            if args.value is not None:
                result = workspace.save(
                    {
                        "image": args.image,
                        "label": args.label,
                        "value": args.value,
                        "reviewer": args.reviewer,
                        "reviewer_kind": args.reviewer_kind,
                        "notes": args.notes,
                        "expected_revision": args.expected_revision,
                    }
                )
            else:
                if any(
                    value is not None
                    for value in (
                        args.image,
                        args.label,
                        args.reviewer,
                        args.reviewer_kind,
                        args.notes,
                        args.expected_revision,
                    )
                ):
                    raise ValueError(
                        "Use --value with a complete label judgment, or omit edit options"
                    )
                state = workspace.read()
                result = {
                    "state": state,
                    "summary": workspace.summary(state),
                    "selection": workspace.selection,
                }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                summary = result["summary"]
                print(f"Label workspace: {workspace.directory}; revision {summary['revision']}")
                print(
                    f"Unique images: {summary['unique_images']}; "
                    f"unreviewed labels: {summary['unreviewed_labels']}"
                )
                print("Judgments: " + json.dumps(summary["judgments"]))
                print("Reviewers: " + json.dumps(summary["reviewer_kinds"]))
                print("Use --json to inspect frozen paths, evaluation sets and saved judgments.")
            return 0
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
        if args.command == "label-pilot":
            from image_dataset_train.label_workspace import LabelWorkspace, create_label_workspace

            directory = create_label_workspace(
                config,
                args.run,
                args.reference,
                args.label,
                selection_reason=args.reason,
                seed=args.seed,
                held_out_fraction=args.held_out_fraction,
                source_paths=args.image,
                probability_sample_size=args.probability_sample_size,
                selection_seed=args.selection_seed,
                partition_groups=args.partition_groups,
            )
            summary = LabelWorkspace(directory).summary()
            print(
                json.dumps(summary, ensure_ascii=False, indent=2)
                if args.json
                else f"Frozen label workspace: {directory}\n"
                f"Images: {summary['unique_images']}; "
                f"unreviewed labels: {summary['unreviewed_labels']}"
            )
            return 0
        if args.command == "label-refresh":
            from image_dataset_train.label_workspace import LabelWorkspace, refresh_label_workspace

            directory = refresh_label_workspace(
                config,
                args.workspace,
                args.groups,
                reason=args.reason,
                expected_parent_revision=args.expected_revision,
            )
            summary = LabelWorkspace(directory).summary()
            print(
                json.dumps(summary, ensure_ascii=False, indent=2)
                if args.json
                else f"Refreshed label workspace: {directory}\n"
                f"Carried-forward revision: {summary['revision']}; "
                f"unreviewed labels: {summary['unreviewed_labels']}"
            )
            return 0
        if args.command == "tag-evaluate":
            from image_dataset_train.tagging_evaluation import evaluate_labels

            directory, result = evaluate_labels(
                config, args.workspace, args.run, include_assistant=args.include_assistant
            )
            if args.json:
                print(json.dumps({"run": str(directory), **result}, ensure_ascii=False, indent=2))
            else:
                print(f"Saved label evaluation: {directory}")
                print("See result.json for coverage, baseline and calibration/held-out metrics.")
                print("Proposed thresholds were not applied. Dataset acceptance remains separate.")
            return 0
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
                pilot_source_paths=args.image,
                selection_reason=args.reason,
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
            reconciliation, processing = summary["reconciliation"], summary["processing"]
            print(f"Count reconciliation: {reconciliation['status']}")
            for check in reconciliation["checks"]:
                if not check["matches"]:
                    print(f"  Mismatch: {check['name']}: {check['expected']} → {check['actual']}")
            print(
                f"Recorded processing: {processing['recorded_processing_seconds']:.3f}s; "
                f"payload: {processing['recorded_payload_bytes']} bytes "
                f"in {processing['recorded_payload_files']} files across referenced runs"
            )
            print(
                f"Measurement coverage: {len(processing['missing_stages'])} missing stages; "
                f"{len(processing['unmeasured_runs'])} unmeasured runs; "
                f"{len(processing['partial_scope_runs'])} publication-only runs. "
                "Payload excludes final report metadata and shared models/caches."
            )
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

        if args.command == "similarity-evaluate":
            from image_dataset_train.similarity_evaluation import evaluate_similarity

            directory, summary = evaluate_similarity(config, args.run)
            if args.json:
                print(json.dumps({"run": str(directory), **summary}, ensure_ascii=False, indent=2))
            else:
                current = summary["current"]
                print(f"Similarity evaluation: {directory}")
                print(
                    f"Review revision: {summary['review_revision']}; "
                    f"related pairs: {summary['related_pairs']}; "
                    f"distinct: {summary['distinct_pairs']}"
                )
                print(
                    f"Radius {current['max_distance']}: {current['false_positive']} false matches; "
                    f"{current['false_negative']} known misses"
                )
                print(
                    "Precision/recall: "
                    + json.dumps({key: current[key] for key in ("precision", "recall")})
                )
                print(summary["scope"])
                print("All 65 radii and evidence coverage are saved in summary.json.")
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
            if (args.evaluation_set is not None or args.clear_evaluation_set) and not (
                args.pair or args.link
            ):
                raise ValueError("Evaluation sets apply to pair decisions, not images.")
            if args.pair or args.link:
                if args.evaluation_set is not None and args.clear_evaluation_set:
                    raise ValueError("Choose --evaluation-set or --clear-evaluation-set.")
                if has_caption or has_annotations:
                    raise ValueError("Caption overrides and annotations require --image.")
                if args.decision is None:
                    raise ValueError("Provide --decision related, distinct, or unreviewed.")
                action = review_link if args.link else review_pair
                result = action(
                    config,
                    args.run,
                    args.link or args.pair,
                    args.decision,
                    args.reason,
                    evaluation_set="" if args.clear_evaluation_set else args.evaluation_set,
                )
            elif args.image:
                if args.evaluation_set is not None or args.clear_evaluation_set:
                    raise ValueError("Evaluation sets apply to pair decisions, not images.")
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
    except KeyboardInterrupt:
        print(
            "Cancelled. Completed artifacts and any saved job checkpoints are retained.",
            file=sys.stderr,
        )
        return 130
    except ImportError as exc:
        print(
            "error: "
            + failure_text(
                exc,
                EventLog(app_home(), enabled=not getattr(args, "dryrun", False)),
                action=args.command,
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            "error: "
            + failure_text(
                exc,
                EventLog(app_home(), enabled=not getattr(args, "dryrun", False)),
                action=args.command,
            ),
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
