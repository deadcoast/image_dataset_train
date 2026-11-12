"""Inspect exact caption candidates without saving reviews or opening image payloads."""

from __future__ import annotations

import hashlib
import stat
from collections import Counter
from pathlib import Path

from image_dataset_train.exporting import _caption, _draft_records
from image_dataset_train.review_changes import (
    _directory,
    _Metadata,
    _metadata,
    _rows,
    _snapshot,
)
from image_dataset_train.review_history import (
    _absolute,
    _bytes,
    _digest,
    _json,
    _loaded,
    _relative,
    _unlinked,
)
from image_dataset_train.reviews import ReviewConflict, _identity, _image_key

CANDIDATE_BYTES = 1024 * 1024
METADATA_BYTES = 64 * 1024 * 1024
PHRASE_ITEMS = 40
PHRASE_CHARACTERS = 240


class _Unavailable(ValueError):
    pass


def _fingerprint(path):
    try:
        _unlinked(path)
        value = path.stat()
        return ("file", value.st_mode, value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    except (OSError, ValueError) as exc:
        return (type(exc).__name__, str(exc))


def _bounded(path, limit):
    _unlinked(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Caption evidence must be a regular file: {path}")
    if before.st_size > limit:
        raise _Unavailable(f"Caption evidence exceeds the {limit}-byte inspection limit: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _unlinked(path)
    after = path.stat()
    if len(raw) > limit:
        raise _Unavailable(f"Caption evidence exceeds the {limit}-byte inspection limit: {path}")
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ReviewConflict("Caption evidence changed while reading; inspect again")
    return raw


class _Reads(_Metadata):
    """Bound snapshot/draft evidence; the existing context/history loader is separate."""

    def __init__(self):
        super().__init__()
        self.bounds = {}
        self.observations = {}

    def read(self, path, expected=None, *, limit=METADATA_BYTES):
        path = Path(path).absolute()
        name = str(path)
        observation = _fingerprint(path)
        if self.observations.setdefault(name, observation) != observation:
            raise ReviewConflict("Caption evidence changed during inspection")
        raw = _bounded(path, limit)
        digest = hashlib.sha256(raw).hexdigest()
        if self.hashes.setdefault(name, digest) != digest:
            raise ReviewConflict("Caption evidence changed during inspection")
        self.bounds[name] = min(limit, self.bounds.get(name, limit))
        if expected is not None and digest != _digest(expected):
            raise ValueError(f"Caption evidence hash mismatch: {path}")
        return raw

    def verify(self):
        for name, observed in self.observations.items():
            path = Path(name)
            if _fingerprint(path) != observed:
                raise ReviewConflict("Caption evidence availability changed during inspection")
            if (
                name in self.hashes
                and hashlib.sha256(_bounded(path, self.bounds[name])).hexdigest()
                != self.hashes[name]
            ):
                raise ReviewConflict("Caption evidence changed during inspection")


def _candidate(status, provenance, *, text=None, normalized_text=None, error=None):
    return {
        "status": status,
        "text": text,
        "normalized_text": normalized_text,
        "provenance": provenance,
        "error": error,
    }


def _failed(provenance, exc):
    if isinstance(exc, ReviewConflict):
        raise exc
    status = "unavailable" if isinstance(exc, (OSError, _Unavailable)) else "invalid"
    return _candidate(status, provenance, error=str(exc))


def _text_candidate(kind, member, value, provenance, *, raw=None, drafts=None):
    text = value if isinstance(value, str) else None
    try:
        if text is not None and len(text.encode("utf-8")) > CANDIDATE_BYTES:
            return _candidate(
                "unavailable",
                provenance,
                error=f"Caption exceeds the {CANDIDATE_BYTES}-byte inspection limit",
            )
        if kind == "override":
            target = {**member, "caption_override": value}
            normalized, origin = _caption(target, None, {})
        elif kind == "sidecar":
            normalized, origin = _caption({**member, "caption_override": None}, raw, {})
        else:
            normalized, origin = _caption({**member, "caption_override": None}, None, drafts)
        return _candidate(
            "present", {**origin, **provenance}, text=text, normalized_text=normalized
        )
    except (UnicodeError, ValueError, KeyError) as exc:
        return _candidate("invalid", provenance, text=text, error=str(exc))


def _sidecar(reader, context, member, input_run, input_meta):
    exported = input_meta["stage"] == "export"
    provenance = {
        "kind": "sidecar",
        "evidence": "captured_export" if exported else "source_sidecar",
        "source_path": member.get("sidecar_path"),
        "sha256": member.get("sidecar_sha256"),
        "source_checked": False,
    }
    if member.get("sidecar_path") is None and member.get("sidecar_sha256") is None:
        return _candidate("absent", {**provenance, "basis": "recorded_inventory"}), None
    try:
        relative, digest = (
            _relative(member.get("sidecar_path")),
            _digest(member.get("sidecar_sha256")),
        )
        if exported:
            name = f"provenance/sidecars/{digest}.txt"
            provenance["artifact_path"] = str(input_run / name)
            files = input_meta["files"]
            if name not in files:
                if input_meta.get("caption_source_version") == 1:
                    raise ValueError("The export is missing its declared sidecar capture")
                raise _Unavailable("This export did not retain the original sidecar candidate")
            if _digest(files[name]) != digest:
                raise ValueError("Captured sidecar digest differs from the recorded source sidecar")
            path = input_run / name
        else:
            path = context.source / relative
            provenance["artifact_path"] = str(path)
        raw = reader.read(path, digest, limit=CANDIDATE_BYTES)
        provenance["source_checked"] = not exported
        text = raw.decode("utf-8-sig")
        return _text_candidate("sidecar", member, text, provenance, raw=raw), raw
    except (OSError, ValueError, KeyError) as exc:
        return _failed(provenance, exc), None


def _draft(reader, context, member, report_meta, input_run, input_meta):
    exported = input_meta["stage"] == "export"
    run = input_meta.get("caption_run") if exported else report_meta.get("caption_run")
    expected = report_meta.get("caption_manifest_sha256")
    provenance = {
        "kind": "draft",
        "evidence": "captured_export" if exported else "report_draft",
        "run": run,
        "manifest_sha256": expected,
        "manifest_binding": "qa_pinned",
        "metadata_binding": "captured_export" if exported else "checked_current",
    }
    try:
        files = input_meta["files"]
        if run is None and expected is None:
            if exported and any(
                name in files
                for name in ("provenance/captions-run.json", "provenance/captions-manifest.jsonl")
            ):
                raise ValueError("Export draft evidence has no recorded caption-run identity")
            return _candidate("absent", provenance), {}
        _absolute(run)
        expected = _digest(expected)
        if exported:
            if report_meta.get("publication_caption_run") != run:
                raise ValueError("QA and export disagree about the captured caption run")
            names = ("provenance/captions-run.json", "provenance/captions-manifest.jsonl")
            if any(name not in files for name in names):
                if input_meta.get("caption_analysis_version") == 1:
                    raise ValueError("The export is missing its declared draft capture")
                raise _Unavailable("This export did not retain the complete pinned draft evidence")
            meta = _metadata(
                reader.checked(input_run, input_meta, names[0]), {"tagging", "recaption"}
            )
            raw = reader.checked(input_run, input_meta, names[1])
            provenance["artifact_path"] = str(input_run / names[1])
        else:
            directory = Path(run)
            # Preserve the original path until the reader has rejected linked ancestors.
            meta = _metadata(reader.read(directory / "run.json"), {"tagging", "recaption"})
            if directory.name.startswith(".pending-"):
                raise ValueError("Pinned captions must be a published run")
            raw = reader.read(directory / "manifest.jsonl", expected)
            provenance["artifact_path"] = str(directory / "manifest.jsonl")
        if (
            Path(_absolute(meta.get("source"))) != context.source
            or meta.get("inventory_manifest_sha256") != context.inventory_hash
            or _digest(meta.get("manifest_sha256")) != expected
            or hashlib.sha256(raw).hexdigest() != expected
        ):
            raise ValueError(
                "Draft metadata or manifest differs from the report's source/inventory pin"
            )
        rows = _rows(raw)
        for row in rows:
            if row.get("decision") == "tagged":
                _relative(row.get("source_path"))
                _digest(row.get("sha256"))
                if (
                    row["source_path"] == member["source_path"]
                    and row["sha256"] != member["sha256"]
                ):
                    raise ValueError(
                        "Draft image content identity differs from the selected report image"
                    )
        drafts = _draft_records(raw)
        value = drafts.get((member["source_path"], member["sha256"]))
        if value is None:
            return _candidate("absent", provenance), drafts
        return _text_candidate(
            "draft", member, value.get("caption"), provenance, drafts=drafts
        ), drafts
    except (OSError, ValueError, KeyError) as exc:
        return _failed(provenance, exc), {}


def _effective(member, candidates, sidecar, drafts):
    winner = (
        "override"
        if member.get("caption_override") is not None
        else "sidecar"
        if candidates["sidecar"]["status"] != "absent"
        else "draft"
    )
    selected = candidates[winner]
    if selected["status"] != "present":
        return {
            "status": selected["status"],
            "text": None,
            "provenance": selected["provenance"],
            "error": selected["error"]
            or "No recorded caption candidate is available; save an override.",
        }
    try:
        text, origin = _caption(member, sidecar, drafts)
        return {
            "status": "present",
            "text": text,
            "provenance": {**origin, **selected["provenance"]},
            "error": None,
        }
    except (UnicodeError, ValueError, KeyError) as exc:
        return {
            "status": "invalid",
            "text": None,
            "provenance": selected["provenance"],
            "error": str(exc),
        }


def _literal_changes(before, after):
    result = {
        "literal_changes": [],
        "literal_changes_total": 0,
        "literal_changes_truncated": False,
        "literal_changes_available": before["status"] == after["status"] == "present",
        "literal_text_changed": None,
        "literal_changes_method": "comma_separated_phrase_counts",
        "literal_changes_basis": "effective.keep_to_effective.proposed",
    }
    if not result["literal_changes_available"]:
        return result
    result["literal_text_changed"] = before["text"] != after["text"]
    left = Counter(phrase.strip() for phrase in before["text"].split(",") if phrase.strip())
    right = Counter(phrase.strip() for phrase in after["text"].split(",") if phrase.strip())
    for operation, values in (("removed", left - right), ("added", right - left)):
        result["literal_changes_total"] += sum(values.values())
        for phrase, count in values.items():
            for _ in range(min(count, PHRASE_ITEMS - len(result["literal_changes"]))):
                clipped = len(phrase) > PHRASE_CHARACTERS
                result["literal_changes"].append(
                    {
                        "operation": operation,
                        "text": phrase[:PHRASE_CHARACTERS],
                        "text_truncated": clipped,
                    }
                )
                result["literal_changes_truncated"] |= clipped
    result["literal_changes_truncated"] |= result["literal_changes_total"] > len(
        result["literal_changes"]
    )
    return result


def inspect_caption_comparison(
    config, similarity_run, report, image_id, *, action="keep", caption=None
):
    """Resolve text candidates from exact evidence; this does not predict export readiness."""
    if action not in ("keep", "replace", "clear") or not isinstance(image_id, str):
        raise ValueError("Choose a report image and keep, replace, or clear caption action")
    if action == "replace":
        if not isinstance(caption, str) or len(caption.encode("utf-8")) > CANDIDATE_BYTES:
            raise ValueError(
                f"Replacement caption must be text within {CANDIDATE_BYTES} UTF-8 bytes"
            )
    elif caption is not None:
        raise ValueError("Only replace accepts a proposed caption")
    report = _directory(report)
    context, store, context_hashes, current, _, current_digest = _loaded(config, similarity_run)
    reader = _Reads()
    captured, _, input_run, input_stage = _snapshot(context, report, reader)
    if (
        current["revision"] < captured["revision"]
        or current["history"][: captured["revision"]] != captured["history"]
    ):
        raise ValueError("Current review history is truncated or diverges from the report snapshot")
    report_meta = _json(reader.read(report / "run.json"))
    entries = _rows(reader.checked(report, report_meta, "entries.jsonl"))
    entry = next((row for row in entries if row["id"] == image_id), None)
    if entry is None:
        raise ValueError("Unknown report image")
    input_meta = _json(reader.read(input_run / "run.json"))
    name = "provenance/groups.jsonl" if input_stage == "export" else "groups.jsonl"
    groups = _rows(reader.checked(input_run, input_meta, name))
    member = next(
        row
        for group in groups
        for row in group["members"]
        if row["source_path"] == entry["source_path"]
    )
    inventory = context.rows[member["source_path"]]
    if any(
        member.get(field) != inventory.get(field)
        for field in ("source_path", "sha256", "sidecar_path", "sidecar_sha256")
    ):
        raise ValueError("Caption source identity differs from the selected inventory")
    saved = current["images"].get(_image_key(member), {})
    current_member = {
        **member,
        "caption_override": saved.get("caption_override"),
        "caption_rule_version": saved.get("caption_rule_version"),
    }
    override_provenance = {
        "kind": "override",
        "evidence": "current_review",
        "revision": current["revision"],
        "review_file": str(store.path),
    }
    override = (
        _candidate("absent", override_provenance)
        if current_member["caption_override"] is None
        else _text_candidate(
            "override", current_member, current_member["caption_override"], override_provenance
        )
    )
    sidecar, sidecar_raw = _sidecar(reader, context, member, input_run, input_meta)
    draft, drafts = _draft(reader, context, member, report_meta, input_run, input_meta)
    candidates = {"override": override, "sidecar": sidecar, "draft": draft}
    clear_member = {**current_member, "caption_override": None, "caption_rule_version": None}
    keep = _effective(current_member, candidates, sidecar_raw, drafts)
    clear = _effective(clear_member, candidates, sidecar_raw, drafts)
    proposed = keep if action == "keep" else clear
    if action == "replace":
        proposed_member = {
            **current_member,
            "caption_override": caption.strip(),
            "caption_rule_version": "manual-v1",
        }
        replacement = _text_candidate(
            "override",
            proposed_member,
            caption.strip(),
            {"kind": "override", "evidence": "proposed_override"},
        )
        proposed = _effective(
            proposed_member, {**candidates, "override": replacement}, sidecar_raw, drafts
        )
    snapshot = {
        "caption": entry.get("caption"),
        "caption_origin": entry.get("caption_origin"),
        "status": "present",
        "error": None,
    }
    if (
        not isinstance(snapshot["caption"], str)
        or len(snapshot["caption"].encode("utf-8")) > CANDIDATE_BYTES
    ):
        snapshot.update(
            caption=None,
            status="unavailable",
            error="Snapshot caption exceeds the inspection text limit or is invalid",
        )
    elif not snapshot["caption"].strip():
        snapshot.update(status="unavailable", error="The report recorded no usable caption")
    elif "\0" in snapshot["caption"]:
        snapshot.update(status="invalid", error="The report caption contains a NUL character")
    reader.verify()
    final_context, final_store, final_hashes, final_current, _, final_digest = _loaded(
        config, similarity_run
    )
    if (
        final_context.source != context.source
        or final_store.path != store.path
        or final_hashes != context_hashes
        or final_current != current
        or final_digest != current_digest
    ):
        raise ReviewConflict("Review context or current state changed during caption inspection")
    reader.verify()
    if any(
        hashlib.sha256(_bytes(Path(path))).hexdigest() != digest
        for path, digest in context_hashes.items()
    ):
        raise ReviewConflict("Review context changed during caption inspection")
    final_raw = _bytes(store.path) if store.path.exists() else None
    if (hashlib.sha256(final_raw).hexdigest() if final_raw is not None else None) != current_digest:
        raise ReviewConflict("Review state changed during caption inspection")
    result = {
        "report": str(report),
        "report_sha256": reader.hashes[str(report / "run.json")],
        "image_id": image_id,
        "identity": {"source_path": member["source_path"], "sha256": member["sha256"]},
        "current_revision": current["revision"],
        "snapshot_revision": captured["revision"],
        "current_store_sha256": current_digest,
        "source_revalidated": False,
        "derivative_preview": False,
        "input_run": str(input_run),
        "input_stage": input_stage,
        "snapshot": snapshot,
        "candidates": candidates,
        "effective": {"keep": keep, "clear": clear, "proposed": proposed},
        "proposed_action": action,
        "evidence_warnings": [
            {"candidate": name, "status": item["status"], "message": item["error"]}
            for name, item in candidates.items()
            if item["status"] in {"invalid", "unavailable"}
        ],
        "read_sha256": {**context_hashes, **reader.hashes},
        "evidence_observations": reader.observations,
        "limits": {
            "candidate_bytes": CANDIDATE_BYTES,
            "snapshot_and_draft_metadata_bytes": METADATA_BYTES,
            "phrase_items": PHRASE_ITEMS,
            "phrase_characters": PHRASE_CHARACTERS,
        },
        **_literal_changes(keep, proposed),
    }
    result["comparison_sha256"] = _identity(result)
    return result
