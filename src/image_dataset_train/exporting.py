"""Publish reviewed, group-separated training pairs and verify them independently."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import tomllib
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, ImageOps

from image_dataset_train import __version__
from image_dataset_train.annotations import annotation_fields
from image_dataset_train.config import Config, ExportConfig
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.inventory import file_sha256
from image_dataset_train.splitting import assign_splits as assign_splits
from image_dataset_train.splitting import balance_report, plan_splits


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(value: object) -> str:
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _path(root: Path, relative: str) -> Path:
    """Resolve a manifest path without accepting aliases outside its artifact tree."""
    if not isinstance(relative, str) or not relative or "\0" in relative:
        raise ValueError("Invalid artifact path")
    parts = PurePosixPath(relative)
    if (
        parts.is_absolute()
        or ".." in parts.parts
        or "\\" in relative
        or ":" in relative
        or parts.as_posix() != relative
    ):
        raise ValueError(f"Unsafe artifact path: {relative}")
    path = root / relative
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Linked artifact/source is not supported: {path}")
        if part == root:
            break
    return path


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _rows(raw: bytes) -> list[dict]:
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Manifest records must be objects")
    return rows


def _checked(root: Path, name: str, digest: str) -> bytes:
    raw = _path(root, name).read_bytes()
    if _digest(raw) != digest:
        raise ValueError(f"Artifact hash mismatch: {name}")
    return raw


def _published(directory: Path, stages: set[str]) -> dict:
    metadata = _json(_path(directory, "run.json"))
    if (
        metadata.get("stage") not in stages
        or metadata.get("schema_version") != 1
        or metadata.get("status") not in {"completed", "completed_with_errors"}
        or directory.name.startswith(".pending-")
    ):
        raise ValueError(f"Expected a published {'/'.join(sorted(stages))} run")
    return metadata


def _load_groups(
    directory: Path, *, require_reviewed: bool = True
) -> tuple[dict, list[dict], dict[str, bytes]]:
    meta = _published(directory, {"groups"})
    files = meta.get("files", {})
    artifacts = {
        name: _checked(directory, name, files.get(name))
        for name in ("groups.jsonl", "reviews.json", "summary.json")
    }
    summary = json.loads(artifacts["summary.json"])
    if require_reviewed and (
        summary.get("review_complete") is not True
        or summary.get("unresolved_pairs") != 0
        or summary.get("conflicts")
        or summary.get("similarity_errors") != 0
    ):
        raise ValueError("Complete pair and image reviews, then publish a new group snapshot.")
    groups = _rows(artifacts["groups.jsonl"])
    seen, hashes, ids = set(), {}, set()
    for group in groups:
        members, key = group.get("members"), group.get("group_id")
        if not isinstance(members, list) or not members or key in ids:
            raise ValueError("Invalid or repeated group")
        identities = []
        for member in members:
            annotation_fields(member)
            path, digest = member.get("source_path"), member.get("sha256")
            if (
                not isinstance(path, str)
                or path in seen
                or not isinstance(digest, str)
                or len(digest) != 64
                or member.get("review_decision")
                not in (
                    {"include", "exclude"}
                    if require_reviewed
                    else {"include", "exclude", "unreviewed"}
                )
            ):
                raise ValueError("Invalid, repeated, or unreviewed group member")
            if digest in hashes and hashes[digest] != key:
                raise ValueError("Exact-byte aliases cross related-image groups")
            seen.add(path)
            hashes[digest] = key
            identities.append([path, digest])
        if key != _identity(sorted(identities)):
            raise ValueError("Group membership identity mismatch")
        ids.add(key)
    return meta, groups, artifacts


def _drafts(directory: Path | None, group_meta: dict) -> tuple[dict, dict | None]:
    if directory is None:
        return {}, None
    directory = directory.resolve(strict=True)
    meta = _published(directory, {"tagging", "recaption"})
    if (
        meta.get("source") != group_meta["source"]
        or meta.get("inventory_manifest_sha256") != group_meta["inventory_manifest_sha256"]
    ):
        raise ValueError("Caption run must refer to the same source inventory as the groups")
    raw = _checked(directory, "manifest.jsonl", meta.get("manifest_sha256"))
    return _draft_records(raw), meta


def _draft_records(raw: bytes) -> dict:
    drafts = {}
    for row in _rows(raw):
        if row.get("decision") == "tagged":
            key = (row.get("source_path"), row.get("sha256"))
            if key in drafts:
                raise ValueError("Repeated caption draft occurrence")
            # The hashed manifest is authoritative; loose editable draft files are not overrides.
            drafts[key] = row
    return drafts


def _export_drafts(directory: Path, metadata: dict) -> tuple[dict, dict | None]:
    """Read only frozen evidence; older exports may retain metadata without observations."""
    files = metadata["files"]
    name = "provenance/captions-run.json"
    if name not in files:
        return {}, None
    meta = json.loads(_checked(directory, name, files[name]))
    name = "provenance/captions-manifest.jsonl"
    if name not in files:
        return {}, meta
    raw = _checked(directory, name, files[name])
    if _digest(raw) != meta["manifest_sha256"]:
        raise ValueError("Caption evidence differs from its recorded run")
    return _draft_records(raw), meta


def _source_bytes(root: Path, relative: str, digest: str, limit: int) -> bytes:
    path = _path(root, relative)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Source exceeds byte limit: {relative}")
    if _digest(raw) != digest:
        raise ValueError(f"Source changed since inventory: {relative}. Scan and review again.")
    return raw


def _draft_analysis(member: dict, drafts: dict, metadata: dict | None) -> dict | None:
    """Keep model/rule findings separate from reviewed captions and annotations."""
    draft = drafts.get((member["source_path"], member["sha256"]))
    if draft is None:
        return None
    metadata = metadata or {}
    return {
        "run_id": metadata.get("run_id"),
        "manifest_sha256": metadata.get("manifest_sha256"),
        "caption_version": metadata.get("caption_version"),
        "rules_sha256": metadata.get("caption_rules_sha256"),
        "composition": draft.get("composition", "unknown"),
        "subset_proposal": draft.get("subset_proposal"),
        "caption_additions": draft.get("caption_additions"),
        "observed_tags": draft.get("observed_tags", draft.get("selected_tags", [])),
        "review_flags": draft.get("review_flags", []),
    }


def _caption(member: dict, sidecar: bytes | None, drafts: dict) -> tuple[str, dict]:
    if member.get("caption_override") is not None:
        text = member["caption_override"]
        provenance = {"kind": "override", "rule_version": member.get("caption_rule_version")}
    elif sidecar is not None:
        text = sidecar.decode("utf-8-sig")
        provenance = {
            "kind": "sidecar",
            "source_path": member["sidecar_path"],
            "sha256": member["sidecar_sha256"],
        }
    else:
        draft = drafts.get((member["source_path"], member["sha256"]), {})
        text = draft.get("caption")
        provenance = {"kind": "draft", "review_flags": draft.get("review_flags", [])}
        if draft.get("caption_version"):
            provenance.update(
                rule_version=draft["caption_version"],
                rules_sha256=draft.get("caption_rules_sha256"),
            )
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise ValueError(f"Missing or empty caption for {member['source_path']}; save an override.")
    # Trainers commonly read only the first line; retain all words as one caption.
    return " ".join(text.split()), provenance


def _adapter(split: str, settings: ExportConfig) -> str:
    return (
        "# Run the trainer with this export directory as its working directory.\n"
        '[general]\ncaption_extension = ".txt"\nshuffle_caption = false\n\n'
        "[[datasets]]\n"
        f"resolution = {settings.resolution}\nbatch_size = 1\n"
        "enable_bucket = true\nbucket_no_upscale = true\nbucket_reso_steps = 64\n\n"
        "[[datasets.subsets]]\n"
        f'image_dir = "{split}"\nnum_repeats = {settings.repeats if split == "train" else 1}\n'
    )


def _prepare_export_image(
    raw: bytes, filename: str, pixel_limit: int, resolution: int
) -> tuple[bytes, str, int, int, str, str]:
    """Normalize only formats/orientation/alpha that the pinned loader cannot honor."""
    suffix = Path(filename).suffix.lower()
    with Image.open(io.BytesIO(raw)) as original:
        if original.width * original.height > pixel_limit:
            raise ValueError(f"Export image exceeds pixel limit: {filename}")
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Training export requires single-frame images")
        original.load()
        has_alpha = "A" in original.getbands() or "transparency" in original.info
        transform = (
            suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
            or original.getexif().get(274, 1) != 1
            or has_alpha
        )
        if transform:
            image = ImageOps.exif_transpose(original).convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image).convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            raw, suffix, image_format, policy = (
                buffer.getvalue(),
                ".png",
                "PNG",
                "png-exif-white-v1",
            )
        else:
            image, image_format, policy = original, original.format, "copy-v1"
        width, height = image.size
        scale = min(1, resolution / (width * height) ** 0.5)
        if min(width, height) * scale < 64:
            raise ValueError(
                f"{filename} is too small or narrow for 64-pixel trainer buckets at "
                f"resolution {resolution}. Exclude it or prepare a suitable derivative; "
                "export does not upscale."
            )
        return raw, suffix, width, height, image_format, policy


def export_dataset(
    config: Config,
    groups_run: Path,
    *,
    captions_run: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict]:
    """Copy approved occurrences into a new self-contained export, then verify before publish."""
    groups_run = groups_run.resolve(strict=True)
    meta, groups, artifacts = _load_groups(groups_run)
    source = Path(meta["source"])
    if not source.is_absolute() or not source.is_dir():
        raise ValueError("Group snapshot source directory is unavailable")
    root = config.exports.resolve()
    if root.is_relative_to(source.resolve()) or source.resolve().is_relative_to(root):
        raise ValueError("Source and export directories must be separate trees")
    drafts, draft_meta = _drafts(captions_run, meta)
    included = [
        (group["group_id"], member)
        for group in groups
        for member in group["members"]
        if member["review_decision"] == "include"
    ]
    if not included:
        raise ValueError("No included images to export")
    sizes = Counter(key for key, _ in included)
    split_plan = plan_splits(included, config.export)
    assignments = split_plan["assignments"]
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-export-" + uuid4().hex[:8]
    staging = Path(tempfile.mkdtemp(prefix=".pending-export-", dir=root))
    for split in ("train", "validation"):
        (staging / split).mkdir()
    rows = []
    for group_id, member in sorted(included, key=lambda item: item[1]["source_path"]):
        raw = _source_bytes(
            source, member["source_path"], member["sha256"], config.validation.max_file_bytes
        )
        sidecar = None
        if member.get("sidecar_path"):
            sidecar = _source_bytes(
                source,
                member["sidecar_path"],
                member["sidecar_sha256"],
                config.validation.max_file_bytes,
            )
        caption, origin = _caption(member, sidecar, drafts)
        identifier = _identity([member["source_path"], member["sha256"]])
        split = assignments[group_id]
        raw, suffix, width, height, image_format, policy = _prepare_export_image(
            raw,
            member["source_path"],
            config.validation.max_decode_pixels,
            config.export.resolution,
        )
        image_name = f"{split}/{identifier}{suffix}"
        caption_name = f"{split}/{identifier}.txt"
        image_path = _path(staging, image_name)
        with image_path.open("xb") as stream:
            stream.write(raw)
        caption_bytes = (caption + "\n").encode("utf-8")
        with _path(staging, caption_name).open("xb") as stream:
            stream.write(caption_bytes)
        rows.append(
            {
                **member,
                "id": identifier,
                "group_id": group_id,
                "split": split,
                "image_path": image_name,
                "caption_path": caption_name,
                "image_sha256": _digest(raw),
                "image_transform": policy,
                "caption_sha256": _digest(caption_bytes),
                "caption": caption,
                "caption_origin": origin,
                "caption_analysis": _draft_analysis(member, drafts, draft_meta),
                "width": width,
                "height": height,
                "format": image_format,
            }
        )
        if progress and (len(rows) % 100 == 0 or len(rows) == len(included)):
            progress(f"Copied {len(rows)}/{len(included)} reviewed image/caption pairs")
    (staging / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    counts = Counter(row["split"] for row in rows)
    actual_ratio = counts["validation"] / len(rows)
    warnings = []
    if config.export.validation_ratio and not counts["validation"]:
        warnings.append("Only one included group; validation is empty to prevent group leakage.")
    if abs(actual_ratio - config.export.validation_ratio) > 1e-9:
        warnings.append("Whole-group allocation differs from the requested validation ratio.")
    rare = sum(row["single_group"] for row in split_plan["balance"]["strata"])
    if rare:
        warnings.append(f"{rare} label/subset strata occur in only one group; see splits.json.")
    summary = {
        "schema_version": 1,
        "stage": "export",
        "images": len(rows),
        "excluded_images": sum(len(group["members"]) for group in groups) - len(rows),
        "groups": len(sizes),
        "split_images": dict(counts),
        "split_groups": dict(Counter(assignments.values())),
        "requested_validation_ratio": config.export.validation_ratio,
        "actual_validation_ratio": actual_ratio,
        "caption_origins": dict(Counter(row["caption_origin"]["kind"] for row in rows)),
        "exact_byte_aliases": len(rows) - len({row["sha256"] for row in rows}),
        "image_transforms": dict(Counter(row["image_transform"] for row in rows)),
        "warnings": warnings,
        "trainer_qualified": False,
        "annotations": split_plan["balance"]["annotations"],
        "split_algorithm": split_plan["algorithm"],
    }
    atomic_json(staging / "summary.json", summary)
    atomic_json(staging / "splits.json", split_plan)
    evidence = staging / "provenance"
    evidence.mkdir()
    for name, raw in artifacts.items():
        (evidence / name).write_bytes(raw)
    atomic_json(evidence / "groups-run.json", meta)
    if draft_meta is not None:
        atomic_json(evidence / "captions-run.json", draft_meta)
        (evidence / "captions-manifest.jsonl").write_bytes(
            _checked(captions_run, "manifest.jsonl", draft_meta["manifest_sha256"])
        )
    for split in counts:
        (staging / f"{split}.toml").write_text(
            _adapter(split, config.export), encoding="utf-8", newline="\n"
        )
    files = {
        path.relative_to(staging).as_posix(): file_sha256(path)
        for path in staging.rglob("*")
        if path.is_file() and path.parent not in (staging / "train", staging / "validation")
    }
    metadata = {
        "schema_version": 1,
        "stage": "export",
        "status": "completed",
        "run_id": run_id,
        "source": str(source),
        "groups_run": str(groups_run),
        "caption_run": str(captions_run.resolve()) if captions_run else None,
        "caption_analysis_version": 1,
        "review_revision": meta["review_revision"],
        "pipeline_version": __version__,
        "completed_at": datetime.now(UTC).isoformat(),
        "files": files,
        "source_revalidated": True,
        "included_sidecars_revalidated": True,
        "trainer_qualified": False,
    }
    atomic_json(staging / "run.json", metadata)
    receipt = _verify_export(staging, metadata)
    atomic_json(staging / "verification.json", receipt)
    metadata["files"]["verification.json"] = file_sha256(staging / "verification.json")
    atomic_json(staging / "run.json", metadata)
    final = root / run_id
    publish_directory(staging, final)
    return final, summary


def _verify_export(directory: Path, meta: dict) -> dict:
    """Verify only the snapshot: it remains verifiable after the original source is offline."""
    files = meta.get("files", {})
    required = {
        "manifest.jsonl",
        "summary.json",
        "splits.json",
        "provenance/groups.jsonl",
        "provenance/reviews.json",
        "provenance/groups-run.json",
        "provenance/summary.json",
    }
    if meta.get("caption_analysis_version") == 1 and meta.get("caption_run"):
        required.update({"provenance/captions-run.json", "provenance/captions-manifest.jsonl"})
    if not required <= files.keys():
        raise ValueError("Export is missing required artifacts")
    raw = {name: _checked(directory, name, digest) for name, digest in files.items()}
    rows = _rows(raw["manifest.jsonl"])
    if not rows:
        raise ValueError("Export manifest is empty")
    summary, splits = json.loads(raw["summary.json"]), json.loads(raw["splits.json"])
    groups = _rows(raw["provenance/groups.jsonl"])
    drafts, draft_meta = {}, None
    if meta.get("caption_analysis_version") == 1 and meta.get("caption_run"):
        drafts, draft_meta = _export_drafts(directory, meta)
    expected_members = {
        (g["group_id"], m["source_path"], m["sha256"])
        for g in groups
        for m in g["members"]
        if m["review_decision"] == "include"
    }
    expected_annotations = {
        (g["group_id"], m["source_path"], m["sha256"]): annotation_fields(m)
        for g in groups
        for m in g["members"]
        if m["review_decision"] == "include"
    }
    expected_subset_origins = {
        (g["group_id"], m["source_path"], m["sha256"]): m.get("subset_origin")
        for g in groups
        for m in g["members"]
        if m["review_decision"] == "include"
    }
    expected_files, members, group_splits, hash_splits = set(files) | {"run.json"}, set(), {}, {}
    counts, ids, output_hash_splits = Counter(), set(), {}
    for row in rows:
        split, key, digest = row["split"], row["group_id"], row["sha256"]
        if split not in {"train", "validation"} or splits["assignments"].get(key) != split:
            raise ValueError("Split assignment mismatch")
        for mapping, identity in (
            (group_splits, key),
            (hash_splits, digest),
            (output_hash_splits, row["image_sha256"]),
        ):
            if identity in mapping and mapping[identity] != split:
                raise ValueError("Group or exact-byte leakage across splits")
            mapping[identity] = split
        identity = (key, row["source_path"], digest)
        if annotation_fields(row) != expected_annotations.get(identity):
            raise ValueError("Export annotations differ from the reviewed snapshot")
        if row.get("subset_origin") != expected_subset_origins.get(identity):
            raise ValueError("Export subset provenance differs from the reviewed snapshot")
        if meta.get("caption_analysis_version") == 1 and row.get("caption_analysis") != (
            _draft_analysis(row, drafts, draft_meta)
        ):
            raise ValueError("Export rule analysis differs from its caption evidence")
        if identity in members or row["id"] in ids:
            raise ValueError("Repeated exported occurrence")
        if row["id"] != _identity([row["source_path"], digest]):
            raise ValueError("Export occurrence identity mismatch")
        members.add(identity)
        ids.add(row["id"])
        image_path, caption_path = row["image_path"], row["caption_path"]
        if (
            PurePosixPath(image_path).parent.as_posix() != split
            or PurePosixPath(caption_path) != PurePosixPath(image_path).with_suffix(".txt")
            or PurePosixPath(image_path).stem != row["id"]
            or row.get("image_transform", "copy-v1") not in {"copy-v1", "png-exif-white-v1"}
            or row.get("image_transform", "copy-v1") == "copy-v1"
            and row["image_sha256"] != digest
            or row.get("image_transform") == "png-exif-white-v1"
            and PurePosixPath(image_path).suffix != ".png"
        ):
            raise ValueError("Invalid image/caption pairing")
        for name, checksum in (
            (image_path, row["image_sha256"]),
            (caption_path, row["caption_sha256"]),
        ):
            if name in expected_files:
                raise ValueError("Export filename collision")
            path = _path(directory, name)
            if file_sha256(path) != checksum:
                raise ValueError(f"Export file hash mismatch: {name}")
            expected_files.add(name)
        text = _path(directory, caption_path).read_text(encoding="utf-8")
        if not row["caption"].strip() or text != row["caption"] + "\n":
            raise ValueError("Empty or inconsistent export caption")
        counts[split] += 1
    if members != expected_members or summary["images"] != len(rows):
        raise ValueError("Export membership does not reconcile with reviewed groups")
    if dict(counts) != summary["split_images"] or group_splits != splits["assignments"]:
        raise ValueError("Export split counts do not reconcile")
    if "balance" in splits:
        balance = balance_report(
            [(row["group_id"], row) for row in rows], group_splits, splits["validation_ratio"]
        )
        if balance != splits["balance"] or balance["annotations"] != summary.get("annotations"):
            raise ValueError("Export annotation/balance counts do not reconcile")
    for split in counts:
        name = f"{split}.toml"
        if name not in files:
            raise ValueError(f"Missing trainer adapter: {name}")
        adapter = tomllib.loads(raw[name].decode("utf-8"))
        if (
            adapter["general"]["caption_extension"] != ".txt"
            or adapter["datasets"][0]["subsets"][0]["image_dir"] != split
        ):
            raise ValueError("Trainer adapter points outside its split")
    actual_files = set()
    for path in directory.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked file in export: {path}")
        if path.is_file():
            actual_files.add(path.relative_to(directory).as_posix())
    if actual_files != expected_files:
        raise ValueError(
            "Export has missing or untracked files, including orphan image/caption pairs"
        )
    return {
        "verified": True,
        "images": len(rows),
        "groups": len(group_splits),
        "split_images": dict(counts),
        "source_required": False,
        "trainer_qualified": False,
    }


def verify_export(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    meta = _published(directory, {"export"})
    try:
        return _verify_export(directory, meta)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed export manifest: {exc}") from exc
