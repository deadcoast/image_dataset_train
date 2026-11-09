"""Pilot selection, caption/annotation findings, and offline review navigation."""

from __future__ import annotations

import hashlib
import io
import json
import shlex
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from image_dataset_train.annotations import annotation_fields, annotation_name, annotation_summary
from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.exporting import (
    _caption,
    _checked,
    _draft_analysis,
    _drafts,
    _export_drafts,
    _load_groups,
    _path,
    _published,
    _rows,
    _source_bytes,
    verify_export,
)
from image_dataset_train.inventory import file_sha256
from image_dataset_train.reporting import content_report
from image_dataset_train.splitting import balance_report, plan_splits


def _rank(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode()).hexdigest()


def read_qa(run: Path) -> tuple[dict, dict]:
    """Read the saved report's data independently of its source collection."""
    meta = _published(run.resolve(strict=True), {"qa"})
    raw = {
        name: _checked(run, name, meta["files"].get(name))
        for name in ("entries.jsonl", "summary.json", "coverage.json")
    }
    return meta, {
        "entries": _rows(raw["entries.jsonl"]),
        "summary": json.loads(raw["summary.json"]),
        "coverage": json.loads(raw["coverage.json"]),
    }


def render_qa(data: dict) -> str:
    template = Path(__file__).with_name("qa_report.html").read_text(encoding="utf-8")
    script = "\n".join(
        Path(__file__).with_name(name).read_text(encoding="utf-8")
        for name in ("qa_report.js", "qa_content.js", "qa_workflow.js", "qa_training.js")
    )
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace("__QA_SCRIPT__", script).replace("__QA_DATA__", payload)


def select_pilot(entries: list[dict], size: int, seed: int) -> list[str]:
    """Cover review findings/categories and geometry first, then fill with seeded variety."""
    if size < 1:
        raise ValueError("Pilot size must be positive")
    candidates = [entry for entry in entries if entry["decision"] != "exclude"]
    ordered = sorted(candidates, key=lambda entry: (_rank(seed, entry["id"]), entry["id"]))
    features = {
        entry["id"]: {
            *(f"finding:{code}" for code in entry["findings"]),
            *(f"label:{label}" for label in entry["labels"]),
            f"subset:{entry['subset']}",
            f"split:{entry['split']}",
            f"orientation:{entry['orientation']}",
            f"caption:{entry['caption_origin']}",
        }
        for entry in ordered
    }
    selected, covered, groups = [], set(), set()
    remaining = list(ordered)
    while remaining and len(selected) < size:
        best = max(
            remaining,
            key=lambda entry: (
                len(features[entry["id"]] - covered),
                entry["group_id"] not in groups,
            ),
        )
        selected.append(best["id"])
        covered.update(features[best["id"]])
        groups.add(best["group_id"])
        remaining.remove(best)
    return selected


def _commands(args: list[str]) -> dict:
    return {
        "powershell": "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in args),
        "posix": shlex.join(args),
    }


def _preview(raw: bytes, destination: Path | io.BytesIO, pixel_limit: int) -> tuple[int, int]:
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > pixel_limit:
            raise ValueError("Preview exceeds configured pixel limit")
        image = ImageOps.exif_transpose(image)
        size = image.size
        image.thumbnail((640, 640))
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        Image.alpha_composite(white, rgba).convert("RGB").save(destination, "JPEG", quality=85)
        return size


def _findings(member: dict, caption: str, flags: list[str]) -> list[str]:
    result = []
    if member["review_decision"] == "unreviewed":
        result.append("decision_pending")
    if member["review_decision"] != "exclude":
        if not caption:
            result.append("caption_missing")
        if not annotation_fields(member)["labels_reviewed"]:
            result.append("labels_pending")
        if not annotation_fields(member)["subset_reviewed"]:
            result.append("subset_pending")
    phrases = [part.strip().casefold() for part in caption.split(",") if part.strip()]
    if len(set(phrases)) < len(phrases):
        result.append("caption_repeated_phrase")
    if len(caption) > 1000:
        result.append("caption_long")
    result.extend("draft:" + flag for flag in flags)
    result.extend("intake:" + reason for reason in member.get("intake_reasons", []))
    return result


def create_qa(
    config: Config,
    run: Path,
    *,
    captions_run: Path | None = None,
    sample_size: int = 50,
    seed: int = 20261011,
    config_path: Path = Path("config.toml"),
) -> tuple[Path, dict]:
    run = run.resolve(strict=True)
    metadata = _published(run, {"groups", "export"})
    exported = metadata["stage"] == "export"
    drafts, draft_meta = {}, None
    if exported:
        if captions_run is not None:
            raise ValueError("An export already freezes captions; omit --captions.")
        verify_export(run)
        members = _rows((run / "manifest.jsonl").read_bytes())
        group_meta = json.loads((run / "provenance/groups-run.json").read_text(encoding="utf-8"))
        split_plan = json.loads((run / "splits.json").read_text(encoding="utf-8"))
        snapshot_summary = json.loads((run / "provenance/summary.json").read_text(encoding="utf-8"))
        drafts, draft_meta = _export_drafts(run, metadata)
    else:
        group_meta, groups, artifacts = _load_groups(run, require_reviewed=False)
        members = [
            {**member, "group_id": group["group_id"]}
            for group in groups
            for member in group["members"]
        ]
        split_plan = plan_splits(
            [(m["group_id"], m) for m in members if m["review_decision"] == "include"],
            config.export,
        )
        snapshot_summary = json.loads(artifacts["summary.json"])
        drafts, draft_meta = _drafts(captions_run, group_meta)
    if sample_size < 1:
        raise ValueError("Pilot size must be positive")
    source = Path(group_meta["source"])
    root = config.runs.resolve()
    if root.is_relative_to(source.resolve()) or source.resolve().is_relative_to(root):
        raise ValueError("Source and QA report directories must be separate trees")
    if root.is_relative_to(run):
        raise ValueError("QA reports must not be written inside their input snapshot")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-qa-", dir=root))
    (staging / "previews").mkdir()
    entries = []
    for member in sorted(members, key=lambda item: item["source_path"]):
        identifier = _rank(0, member["source_path"] + "\0" + member["sha256"])
        errors, flags = [], []
        analysis = (
            member.get("caption_analysis")
            if exported
            else _draft_analysis(member, drafts, draft_meta)
        )
        caption, origin, preview, width, height = "", "missing", None, None, None
        image_path = (
            _path(run, member["image_path"]) if exported else source / member["source_path"]
        )
        try:
            raw = (
                _source_bytes(
                    run,
                    member["image_path"],
                    member["image_sha256"],
                    config.validation.max_file_bytes,
                )
                if exported
                else _source_bytes(
                    source,
                    member["source_path"],
                    member["sha256"],
                    config.validation.max_file_bytes,
                )
            )
            width, height = _preview(
                raw, staging / "previews" / f"{identifier}.jpg", config.validation.max_decode_pixels
            )
            preview = f"previews/{identifier}.jpg"
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            errors.append(f"Image unavailable: {exc}")
        try:
            if exported:
                caption = member["caption"]
                origin = member["caption_origin"]["kind"]
                flags = member["caption_origin"].get("review_flags", [])
            else:
                sidecar = None
                if member.get("sidecar_path"):
                    sidecar = _source_bytes(
                        source,
                        member["sidecar_path"],
                        member["sidecar_sha256"],
                        config.validation.max_file_bytes,
                    )
                caption, provenance = _caption(member, sidecar, drafts)
                origin = provenance["kind"]
                flags = provenance.get("review_flags", [])
        except (OSError, ValueError) as exc:
            errors.append(f"Caption unavailable: {exc}")
        findings = _findings(member, caption, flags)
        if analysis:
            findings.extend("draft:" + flag for flag in analysis["review_flags"])
            proposed = (analysis.get("subset_proposal") or {}).get("value")
            if proposed and not annotation_fields(member)["subset_reviewed"]:
                findings.append("subset_proposal_pending")
            elif proposed and proposed != member.get("subset"):
                findings.append("subset_proposal_differs_from_review")
        if preview is None:
            findings.append("image_unavailable")
        if errors and caption == "":
            findings.append("caption_unavailable")
        args = [
            "dataset",
            "review",
            "--run",
            group_meta["similarity_run"],
            "--config",
            str(config_path.resolve()),
            "--image",
            member["source_path"],
        ]
        entries.append(
            {
                "id": identifier,
                "source_path": member["source_path"],
                "sha256": member["sha256"],
                "group_id": member["group_id"],
                "decision": member["review_decision"],
                "reason": member.get("reason", ""),
                **annotation_fields(member),
                "subset_origin": member.get("subset_origin"),
                "split": split_plan["assignments"].get(member["group_id"], "unassigned")
                if member["review_decision"] == "include"
                else "unassigned",
                "caption": caption,
                "caption_origin": origin,
                "caption_analysis": analysis,
                "caption_characters": len(caption),
                "caption_words": len(caption.split()),
                "findings": sorted(set(findings)),
                "errors": errors,
                "preview": preview,
                "image_uri": image_path.absolute().as_uri(),
                "width": width,
                "height": height,
                "orientation": (
                    "unknown"
                    if width is None
                    else "square"
                    if width == height
                    else "landscape"
                    if width > height
                    else "portrait"
                ),
                "review_args": args,
                "review_commands": _commands(args),
            }
        )
    included = [(m["group_id"], m) for m in members if m["review_decision"] == "include"]
    balance = balance_report(included, split_plan["assignments"], split_plan["validation_ratio"])
    uncovered = {
        (row["kind"], row["name"]): row
        for row in balance["strata"]
        if row["single_group"]
        or row["missing_train"]
        or (split_plan["validation_ratio"] > 0 and row["missing_validation"])
    }
    for entry in entries:
        if entry["decision"] != "include":
            continue
        features = [("label", name) for name in entry["labels"]]
        if entry["subset"] is not None:
            features.append(("subset", entry["subset"]))
        for feature in features:
            if feature in uncovered:
                row = uncovered[feature]
                if row["single_group"]:
                    entry["findings"].append("coverage_single_group")
                if row["missing_train"] or (
                    split_plan["validation_ratio"] > 0 and row["missing_validation"]
                ):
                    entry["findings"].append("coverage_missing_split")
        if entry["group_id"] in balance["mixed_subset_groups"]:
            entry["findings"].append("coverage_mixed_subset")
        entry["findings"] = sorted(set(entry["findings"]))
    pilot = select_pilot(entries, sample_size, seed)
    for entry in entries:
        entry["pilot"] = entry["id"] in pilot
    findings = Counter(code for entry in entries for code in entry["findings"])
    summary = {
        "images": len(entries),
        "pilot_images": len(pilot),
        "requested_pilot_images": sample_size,
        "groups": len({entry["group_id"] for entry in entries}),
        "decisions": dict(Counter(entry["decision"] for entry in entries)),
        "findings": dict(sorted(findings.items())),
        "annotations": annotation_summary(entries),
        "caption_origins": dict(Counter(entry["caption_origin"] for entry in entries)),
        "split_images": dict(Counter(entry["split"] for entry in entries)),
        "split_state": "published" if exported else "preview",
        "validation_ratio": split_plan["validation_ratio"],
        "unresolved_pairs": snapshot_summary["unresolved_pairs"],
        "conflicts": snapshot_summary.get("conflicts", []),
        "similarity_errors": snapshot_summary["similarity_errors"],
        "review_revision": group_meta["review_revision"],
        "seed": seed,
        "pilot_ids": pilot,
        "human_accepted": False,
        "content": content_report(
            members,
            drafts,
            draft_meta,
            evidence_source="export_provenance" if exported else "caption_run",
            manifest_available=(
                "provenance/captions-manifest.jsonl" in metadata["files"]
                if exported
                else captions_run is not None
            ),
        ),
    }
    atomic_json(staging / "summary.json", summary)
    atomic_json(staging / "coverage.json", balance)
    (staging / "entries.jsonl").write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
        newline="\n",
    )
    (staging / "report.html").write_text(
        render_qa({"summary": summary, "entries": entries, "coverage": balance}), encoding="utf-8"
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-qa-" + uuid4().hex[:8]
    atomic_json(
        staging / "run.json",
        {
            "schema_version": 1,
            "stage": "qa",
            "status": "completed",
            "run_id": run_id,
            "input_run": str(run),
            "input_run_sha256": file_sha256(run / "run.json"),
            "config_path": str(config_path.resolve()),
            "source": str(source),
            "similarity_run": group_meta["similarity_run"],
            "caption_run": str(captions_run.resolve()) if captions_run else None,
            "publication_caption_run": metadata.get("caption_run") if exported else None,
            "caption_manifest_sha256": draft_meta["manifest_sha256"] if draft_meta else None,
            "created_at": datetime.now(UTC).isoformat(),
            "files": {
                p.relative_to(staging).as_posix(): file_sha256(p)
                for p in staging.rglob("*")
                if p.is_file()
            },
        },
    )
    final = root / run_id
    publish_directory(staging, final)
    return final, summary


def list_qa(
    run: Path,
    *,
    finding: str | None = None,
    label: str | None = None,
    subset: str | None = None,
    split: str | None = None,
    group: str | None = None,
    pilot: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    if offset < 0 or limit < 1:
        raise ValueError("QA offset must be nonnegative and limit must be positive")
    run = run.resolve(strict=True)
    meta = _published(run, {"qa"})
    entries = _rows(_checked(run, "entries.jsonl", meta["files"].get("entries.jsonl")))
    if label is not None:
        label = annotation_name(label)
    if subset is not None:
        subset = annotation_name(subset)
    matches = [
        entry
        for entry in entries
        if (not finding or finding in entry["findings"])
        and (label is None or label in entry["labels"])
        and (subset is None or subset == entry["subset"])
        and (not split or split == entry["split"])
        and (not group or group == entry["group_id"])
        and (not pilot or entry["pilot"])
    ]
    return {
        "total": len(matches),
        "offset": offset,
        "entries": matches[offset : offset + limit],
        "next_offset": offset + limit if offset + limit < len(matches) else None,
    }
