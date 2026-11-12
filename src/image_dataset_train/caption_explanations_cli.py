"""Read-only navigation and terminal presentation for saved caption evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from image_dataset_train.collection_registry import CollectionRegistry, path_key, unlinked_path
from image_dataset_train.review_selection import display, read_metadata_bytes

COMMANDS = {"caption-explain"}


def register_commands(commands) -> None:
    parser = commands.add_parser(
        "caption-explain", help="explain one saved draft from its retained scores and rules"
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run", type=Path, help="exact saved tagging or recaption run")
    selector.add_argument("--workspace", type=Path, help="saved preparation workspace")
    selector.add_argument("--collection", help="registered collection name or exact ID")
    parser.add_argument("--job", help="exact historical job ID; otherwise use the current job")
    parser.add_argument("--image", required=True, help="exact relative source path in the run")
    parser.add_argument("--tag", action="append", help="exact raw tag name; repeat to inspect more")
    parser.add_argument("--limit", type=int, default=50, help="tag page size, 1–200 (default: 50)")
    parser.add_argument("--offset", type=int, default=0, help="tag page offset (default: 0)")
    parser.add_argument("--json", action="store_true", help="structured explanation and provenance")


def _digest(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"Missing or invalid saved {name} checksum")
    return value


@dataclass
class _Selection:
    run: Path
    pins: dict
    identity: dict
    reads: dict[Path, bytes]

    def verify(self):
        for path, expected in self.reads.items():
            if read_metadata_bytes(path) != expected:
                raise ValueError("Caption selection changed during inspection; inspect again")


def _select(args) -> _Selection:
    if args.run is not None:
        if args.job is not None:
            raise ValueError("--job requires --workspace or --collection")
        run = unlinked_path(args.run)
        return _Selection(run, {}, {"kind": "run", "run": str(run)}, {})

    from image_dataset_train.preparation import _inspect_attempt, read_preparation_job

    reads = {}

    def read(path, expected=None):
        path = unlinked_path(path)
        raw = read_metadata_bytes(path)
        if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"Saved caption checkpoint metadata changed: {path}")
        reads[path] = raw
        return raw

    entry = None
    if args.collection is not None:
        registry = CollectionRegistry()
        raw_registry = read(registry.path)
        registered = registry.read()
        if (
            json.loads(raw_registry) != registered
            or read_metadata_bytes(registry.path) != raw_registry
        ):
            raise ValueError("Collection registration changed during caption selection")
        entry = registry._resolve(registered["collections"], args.collection)
        workspace = unlinked_path(Path(entry["workspace"]))
    else:
        workspace = unlinked_path(args.workspace)
    binding = read(workspace / "collection.json")
    job, state = read_preparation_job(workspace, job_id=args.job)
    captured_binding = json.loads(binding)
    if (
        not isinstance(captured_binding, dict)
        or captured_binding.get("schema_version") != 1
        or captured_binding.get("source") != state["source"]
        or not isinstance(captured_binding.get("job"), str)
        or re.fullmatch(r"jobs/[A-Za-z0-9][A-Za-z0-9_-]{0,127}", captured_binding["job"]) is None
        or state["workspace"] != str(workspace)
        or job != workspace / "jobs" / state["job_id"]
        or (args.job is None and captured_binding["job"] != "jobs/" + state["job_id"])
        or (args.job is not None and args.job != state["job_id"])
    ):
        raise ValueError("Selected job differs from the captured collection binding")
    raw_job = read(job / "job.json")
    if json.loads(raw_job) != state:
        raise ValueError("Preparation job changed during caption selection")
    read(job / "config.toml", _digest(state["config_sha256"], "configuration"))
    if entry is not None and path_key(entry["source"]) != path_key(state["source"]):
        raise ValueError("Registered collection source differs from its saved preparation job")

    def checkpoint(stage):
        record = state["stages"].get(stage)
        if not isinstance(record, dict) or record.get("status") != "completed":
            raise ValueError(f"Selected preparation job has no completed {stage} checkpoint")
        checked = _inspect_attempt(job, state, stage, record, verify=False)
        if checked["integrity"] == "invalid" or not checked.get("output"):
            raise ValueError(f"Selected {stage} checkpoint ownership is invalid")
        run = unlinked_path(Path(checked["output"]))
        files = record["files"]
        run_sha = _digest(files.get("run.json"), f"{stage} run")
        manifest_sha = _digest(files.get("manifest.jsonl"), f"{stage} manifest")
        meta = json.loads(read(run / "run.json", run_sha))
        if not isinstance(meta, dict) or meta.get("manifest_sha256") != manifest_sha:
            raise ValueError(f"Saved {stage} checkpoint manifest identity is inconsistent")
        read(run / "manifest.jsonl", manifest_sha)
        return run, meta, run_sha, manifest_sha

    run, meta, run_sha, manifest_sha = checkpoint("tagging")
    inventory, inventory_meta, _, inventory_sha = checkpoint("inventory")
    if (
        inventory_meta.get("source") != state["source"]
        or meta.get("inventory_run") != str(inventory)
        or meta.get("inventory_manifest_sha256") != inventory_sha
        or meta.get("stage") != "tagging"
        or meta.get("caption_rules") != state["settings"]["captions"]
        or meta.get("requested_device") != state["settings"]["tagging"]["device"]
        or meta.get("validation") != state["settings"]["validation"]
        or (
            state.get("model_identity") is not None and meta.get("model") != state["model_identity"]
        )
    ):
        raise ValueError("Saved tagging input differs from its exact preparation job")
    identity = {
        "kind": "collection" if entry is not None else "workspace",
        "workspace": str(workspace),
        "job_id": state["job_id"],
        "binding_sha256": hashlib.sha256(binding).hexdigest(),
        "job_sha256": hashlib.sha256(raw_job).hexdigest(),
    }
    if entry is not None:
        identity["collection_id"] = entry["id"]
    selection = _Selection(
        run,
        {
            "expected_run_sha256": run_sha,
            "expected_manifest_sha256": manifest_sha,
            "expected_source": state["source"],
        },
        identity,
        reads,
    )
    selection.verify()
    return selection


def _names(values):
    return ", ".join(display(value) for value in values) or "none"


def _render(result):
    print(f"Saved draft: {display(result['identity']['source_path'])}")
    print(f"Run: {display(result['run'])}")
    print(f"Run SHA-256: {result['run_sha256']}")
    print(f"Image SHA-256: {result['identity']['sha256']}")
    if result["status"] == "unavailable":
        print(f"Explanation unavailable: {display(result['reason'])}")
        return
    print(f"Rules: {result['rules_sha256']} ({display(result['caption_version'])})")
    print(f"Caption: {display(result['caption'])}")
    summary = result["summary"]
    print(
        f"Tags: {summary['selected']} selected; {summary['omitted']} omitted; "
        f"{summary['near_threshold']} near threshold. Scores are not calibrated certainty."
    )
    print(
        f"Showing {len(result['tags'])} of {result['total']} {result['tag_scope']} tag records "
        f"from offset {result['offset']}. Use --tag for any exact raw label."
    )
    for tag in result["tags"]:
        threshold = (
            "rating only"
            if tag["threshold"] is None
            else f"strictly > {tag['threshold']} ({tag['threshold_source']})"
        )
        print(
            f"  {display(tag['name'])}: score {tag['score']}; {threshold}; "
            f"{_names(tag['reasons'])}; phrase {tag['phrase_status']}"
            + ("; near threshold" if tag["near_threshold"] else "")
        )
    if result["has_more"]:
        print(f"Next page: use --offset {result['offset'] + result['limit']}.")
    print(f"Subset proposal: {display(result['subset_proposal']['value'] or 'unassigned')}")
    for rule in result["subset_rules"]:
        print(f"  {display(rule['name'])}: {'matched' if rule['matched'] else 'not matched'}")
        for key in ("all_tags", "any_tags"):
            evidence = rule[key]
            if evidence["required"]:
                print(
                    f"    {key}: required {_names(evidence['required'])}; "
                    f"present {_names(evidence['present'])}; missing {_names(evidence['missing'])}"
                )
        forbidden = rule["none_tags"]
        if forbidden["forbidden"]:
            print(
                f"    none_tags: forbidden {_names(forbidden['forbidden'])}; "
                f"present {_names(forbidden['present'])}"
            )
        expected = rule["expect_tags"]
        if expected["expected"]:
            print(
                f"    expected: {_names(expected['expected'])}; "
                f"missing {_names(expected['missing'])}"
                + (" (matched rule)" if expected["applies"] else " (rule did not match)")
            )
    additions = result["additions"]
    print(f"Trigger: {display(additions['trigger']) or 'none'}")
    print(f"Forced phrases: {_names(additions['force_tags'])}")
    for phrase in result["phrases"]:
        if phrase["status"] == "duplicate_phrase":
            print(
                f"  Duplicate phrase omitted: {display(phrase['text'])} "
                f"({phrase['kind']}; first position {phrase['duplicate_of']})"
            )
    print("Evidence describes the saved draft. No inference or source-image reads were performed.")


def run_command(args) -> int:
    try:
        selection = _select(args)
        # Score parsing requires optional NumPy; help and unrelated commands do not.
        from image_dataset_train.caption_explanations import explain_caption

        result = explain_caption(
            selection.run,
            args.image,
            tags=args.tag,
            limit=args.limit,
            offset=args.offset,
            **selection.pins,
        )
        selection.verify()
        result = {**result, "selection": selection.identity}
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        message = str(exc)
        if isinstance(exc, ImportError):
            message = (
                f"Saved-score inspection needs the optional tagging dependencies: {exc}. "
                "Install image-dataset-train[tag-cpu] in this environment, "
                "or repair the existing tagging installation. No model download is required."
            )
        if args.json:
            print(
                json.dumps(
                    {"status": "failed", "error": {"type": type(exc).__name__, "message": message}},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"Caption explanation failed: {display(message)}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _render(result)
    return 0
