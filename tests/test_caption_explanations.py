"""Independent saved-caption replay, provenance, and read-only adversarial checks."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from image_dataset_train.caption_explanations import explain_caption
from image_dataset_train.captions import CAPTION_FIELDS, rules_identity
from image_dataset_train.config import CaptionConfig
from image_dataset_train.model_bundle import Label
from image_dataset_train.tagging import _publish


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path: Path):
    return {
        item.relative_to(path).as_posix(): (item.read_bytes(), item.stat().st_mtime_ns)
        for item in path.rglob("*")
        if item.is_file()
    }


def records(run: Path):
    return [json.loads(line) for line in (run / "manifest.jsonl").read_bytes().splitlines()]


def rewrite_records(run: Path, rows):
    (run / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    metadata = read(run / "run.json")
    metadata["manifest_sha256"] = digest(run / "manifest.jsonl")
    save(run / "run.json", metadata)


def make_run(tmp_path, *, rules=None, scores=None, labels=None, aliases=False):
    labels = labels or [
        Label(0, "blue_hair", 0),
        Label(1, "general", 9),
        Label(2, "hatsune_miku", 4),
        Label(3, "^_^", 0),
        Label(4, "1girl", 0),
        Label(5, "solo", 0),
        Label(6, "2girls", 0),
        Label(7, "pose_(test)", 0),
    ]
    scores = np.asarray(scores if scores is not None else [0.75] * len(labels), dtype=np.float32)
    source = tmp_path / "source-was-never-created"
    content = hashlib.sha256(b"retained image identity").hexdigest()
    rows = [{"source_path": "portraits/猫.png", "sha256": content, "decision": "tagged"}]
    if aliases:
        rows.append({"source_path": "alias.png", "sha256": content, "decision": "tagged"})
    rows.append(
        {
            "source_path": "skipped.png",
            "sha256": hashlib.sha256(b"skipped").hexdigest(),
            "decision": "skipped",
            "reason": "not_selected_for_caption_publication",
        }
    )
    run = _publish(
        tmp_path / "runs",
        rows,
        {content: scores},
        labels,
        {
            "stage": "tagging",
            "source": str(source),
            "inventory_manifest_sha256": "a" * 64,
        },
        {},
        rules or CaptionConfig(),
        0.5,
    )
    return run


def explain(run, **kwargs):
    return explain_caption(run, "portraits/猫.png", **kwargs)


@pytest.mark.parametrize(
    "field",
    [
        "caption",
        "selected_tags",
        "observed_tags",
        "ratings",
        "uncertain_tags",
        "review_flags",
        "composition",
        "subset_proposal",
        "caption_additions",
        "effective_general_threshold",
        "caption_rules_sha256",
    ],
)
def test_rehashed_manifest_cannot_lie_about_replayed_caption(tmp_path, field):
    run = make_run(tmp_path)
    rows = records(run)
    value = rows[0][field]
    if isinstance(value, str):
        rows[0][field] = "fabricated"
    elif isinstance(value, list):
        rows[0][field] = value + ["fabricated"]
    elif isinstance(value, dict):
        rows[0][field] = {**value, "fabricated": True}
    else:
        rows[0][field] = 0.123
    rewrite_records(run, rows)
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        explain(run)
    assert tree(tmp_path) == before


@pytest.mark.parametrize("value", [False, 0.0])
def test_replayed_label_index_preserves_integer_type(tmp_path, value):
    run = make_run(tmp_path)
    rows = records(run)
    assert rows[0]["selected_tags"][0]["index"] == 0
    rows[0]["selected_tags"][0]["index"] = value
    rewrite_records(run, rows)
    with pytest.raises(ValueError):
        explain(run)


@pytest.mark.parametrize("artifact", ["manifest.jsonl", "labels.json", "score_index.json"])
def test_artifact_hash_corruption_rejects_without_repair(tmp_path, artifact):
    run = make_run(tmp_path)
    with (run / artifact).open("ab") as stream:
        stream.write(b" ")
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        explain(run)
    assert tree(tmp_path) == before


@pytest.mark.parametrize(
    "damage",
    ["hash", "checksum", "shape", "integer", "nan", "range", "trailing", "huge_header", "object"],
)
def test_saved_score_corruption_rejects_without_allocating_untrusted_shape(
    tmp_path, monkeypatch, damage
):
    run = make_run(tmp_path)
    index = read(run / "score_index.json")
    artifact = next(iter(index.values()))
    path = run / artifact["path"]
    if damage == "hash":
        path.write_bytes(path.read_bytes() + b"changed")
    elif damage == "checksum":
        artifact["score_checksum"] = "0" * 64
    else:
        vector = np.full(8, 0.75, dtype=np.float32)
        if damage == "shape":
            vector = vector.reshape((2, 4))
        elif damage == "integer":
            vector = vector.astype(np.int32)
        elif damage == "nan":
            vector[0] = np.nan
        elif damage == "range":
            vector[0] = 1.5
        elif damage == "object":
            vector = np.array(["object"] * 8, dtype=object)
        stream = io.BytesIO()
        if damage == "huge_header":
            np.lib.format.write_array_header_1_0(
                stream, {"descr": "<f4", "fortran_order": False, "shape": (10**12,)}
            )
        else:
            np.save(stream, vector, allow_pickle=damage == "object")
        path.write_bytes(stream.getvalue() + (b"extra" if damage == "trailing" else b""))
        artifact["sha256"] = digest(path)
    save(run / "score_index.json", index)
    metadata = read(run / "run.json")
    metadata["score_index_sha256"] = digest(run / "score_index.json")
    save(run / "run.json", metadata)
    if damage in {"huge_header", "object", "shape", "integer", "trailing"}:

        def unexpected_load(*args, **kwargs):
            pytest.fail("A malformed NPY header must reject before np.load")

        monkeypatch.setattr(np, "load", unexpected_load)
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        explain(run)
    assert tree(tmp_path) == before


@pytest.mark.parametrize("field", ["schema_version", "stage", "status", "source"])
def test_invalid_run_metadata_rejects(tmp_path, field):
    run = make_run(tmp_path)
    metadata = read(run / "run.json")
    metadata[field] = {
        "schema_version": True,
        "stage": "scan",
        "status": "pending",
        "source": "relative/path",
    }[field]
    save(run / "run.json", metadata)
    with pytest.raises(ValueError):
        explain(run)


@pytest.mark.parametrize(
    "options",
    [
        {"expected_run_sha256": "0" * 64},
        {"expected_manifest_sha256": "0" * 64},
        {"expected_source": "C:/another/source"},
        {"expected_sha256": "0" * 64},
    ],
)
def test_exact_binding_mismatch_rejects(tmp_path, options):
    run = make_run(tmp_path)
    with pytest.raises(ValueError):
        explain(run, **options)


@pytest.mark.parametrize("source_path", ["missing.png", "../escape.png", "portraits\\猫.png", ""])
def test_unknown_or_invalid_exact_image_is_not_substituted(tmp_path, source_path):
    run = make_run(tmp_path, aliases=True)
    with pytest.raises(ValueError):
        explain_caption(run, source_path)


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 1001},
        {"offset": -1},
        {"offset": True},
        {"offset": 1.5},
        {"tags": ["unknown_tag"]},
        {"tags": ["blue hair"]},
    ],
)
def test_invalid_pagination_or_raw_tag_filter_rejects(tmp_path, options):
    run = make_run(tmp_path)
    with pytest.raises(ValueError):
        explain(run, **options)


def test_strict_threshold_and_inclusive_near_boundary(tmp_path):
    labels = [Label(0, "equal", 0), Label(1, "above", 0), Label(2, "below", 0)]
    run = make_run(
        tmp_path,
        labels=labels,
        scores=[0.5, 0.625, 0.375],
        rules=CaptionConfig(general_threshold=0.5, uncertainty_margin=0.125),
    )
    result = explain(run)
    assert result["status"] == "available"
    assert result["caption"] == "above"
    tags = {tag["name"]: tag for tag in result["tags"]}
    assert tags["equal"]["observed"] is False
    assert tags["equal"]["reasons"] == ["below_or_equal_threshold"]
    assert tags["above"]["selected"] is True
    assert tags["below"]["selected"] is False
    assert all(tag["near_threshold"] for tag in tags.values())
    assert all(tag["threshold_source"] == "general_threshold" for tag in tags.values())
    assert result["summary"]["near_threshold"] == 3


def test_zero_margin_disables_uncertainty_and_raw_filter_reveals_omitted_labels(tmp_path):
    labels = [Label(0, "equal", 0), Label(1, "above", 0), Label(2, "below", 0)]
    run = make_run(
        tmp_path, labels=labels, scores=[0.5, 0.75, 0.25], rules=CaptionConfig(uncertainty_margin=0)
    )
    default = explain(run)
    assert [tag["name"] for tag in default["tags"]] == ["above"]
    assert default["summary"] == {
        "labels": 3,
        "observed": 1,
        "selected": 1,
        "near_threshold": 0,
        "ratings": 0,
        "omitted": 2,
    }
    explicit = explain(run, tags=["below", "equal"])
    assert explicit["tag_scope"] == "requested"
    assert [tag["name"] for tag in explicit["tags"]] == ["equal", "below"]
    assert all(tag["threshold_source"] == "default_general_threshold" for tag in explicit["tags"])
    assert all(not tag["near_threshold"] for tag in explicit["tags"])


def test_all_drop_reasons_and_character_override_priority(tmp_path):
    rules = CaptionConfig(
        general_threshold=0.25,
        character_threshold=0.875,
        keep_characters=False,
        tag_thresholds={"hatsune_miku": 0.5},
        drop_tags=["hatsune_miku"],
    )
    run = make_run(tmp_path, rules=rules, scores=[0.75, 0.75, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1])
    tag = explain(run, tags=["hatsune_miku"])["tags"][0]
    assert tag["threshold"] == 0.5
    assert tag["threshold_source"] == "tag_override"
    assert tag["reasons"] == ["below_or_equal_threshold", "explicit_drop", "characters_disabled"]
    assert not tag["selected"] and not tag["observed"] and tag["near_threshold"]
    kept = make_run(
        tmp_path / "kept",
        rules=CaptionConfig(
            keep_characters=True, character_threshold=0.875, tag_thresholds={"hatsune_miku": 0.5}
        ),
    )
    character = explain(kept, tags=["hatsune_miku"])["tags"][0]
    assert character["selected"] and character["reasons"] == ["selected"]


def test_observed_dropped_tags_drive_every_subset_predicate_and_conflicts(tmp_path):
    rules = CaptionConfig(
        drop_tags=["blue_hair", "1girl"],
        trigger="2girls",
        force_tags=["solo"],
        subset_rules=[
            {
                "name": "blue",
                "all_tags": ["blue_hair"],
                "any_tags": ["1girl", "2girls"],
                "none_tags": ["solo"],
                "expect_tags": ["pose_(test)"],
            },
            {"name": "counted", "all_tags": ["1girl"]},
            {
                "name": "not-matched",
                "all_tags": ["solo"],
                "none_tags": ["blue_hair"],
                "expect_tags": ["hatsune_miku"],
            },
        ],
    )
    run = make_run(tmp_path, rules=rules, scores=[0.75, 0.99, 0.1, 0.1, 0.75, 0.1, 0.1, 0.1])
    result = explain(run)
    assert result["caption"] == "2girls, solo"
    assert result["composition"] == "single_subject"
    assert result["subset_proposal"] == {
        "value": None,
        "matches": ["blue", "counted"],
        "missing_tags": {"blue": ["pose_(test)"]},
    }
    by_name = {item["name"]: item for item in result["subset_rules"]}
    blue = by_name["blue"]
    assert blue["matched"]
    assert blue["all_tags"] == {
        "required": ["blue_hair"],
        "present": ["blue_hair"],
        "missing": [],
        "passed": True,
    }
    assert blue["any_tags"] == {
        "required": ["1girl", "2girls"],
        "present": ["1girl"],
        "missing": ["2girls"],
        "passed": True,
    }
    assert blue["none_tags"] == {"forbidden": ["solo"], "present": [], "passed": True}
    assert blue["expect_tags"] == {
        "expected": ["pose_(test)"],
        "present": [],
        "missing": ["pose_(test)"],
        "applies": True,
    }
    unmatched = by_name["not-matched"]
    assert not unmatched["matched"]
    assert not unmatched["all_tags"]["passed"] and not unmatched["none_tags"]["passed"]
    assert unmatched["expect_tags"]["applies"] is False
    assert unmatched["expect_tags"]["missing"] == ["hatsune_miku"]
    assert {"subset_rule_conflict", "subset_missing_expected_tags"} <= set(result["review_flags"])
    assert all(
        not item["selected"] for item in result["tags"] if item["name"] in {"1girl", "blue_hair"}
    )


def test_ratings_are_evidence_only_and_rejected_as_subset_predicates(tmp_path):
    run = make_run(tmp_path)
    tag = explain(run, tags=["general"])["tags"][0]
    assert tag["reasons"] == ["rating_only"]
    assert tag["threshold"] is None and tag["threshold_source"] is None
    assert not tag["selected"] and not tag["observed"] and not tag["near_threshold"]
    metadata = read(run / "run.json")
    rules = CaptionConfig(subset_rules=[{"name": "rating", "all_tags": ["general"]}])
    from dataclasses import asdict

    metadata["caption_rules"] = asdict(rules)
    metadata["caption_rules_sha256"] = rules_identity(rules, 0.5)
    save(run / "run.json", metadata)
    with pytest.raises(ValueError, match="rating"):
        explain(run)


def test_phrase_order_casefold_duplicates_and_kaomoji_are_literal(tmp_path):
    run = make_run(
        tmp_path,
        rules=CaptionConfig(trigger="BLUE HAIR", force_tags=["blue hair", "^_^", "new phrase"]),
        scores=[0.75, 0.75, 0.1, 0.875, 0.1, 0.1, 0.1, 0.1],
    )
    result = explain(run)
    assert result["caption"] == "BLUE HAIR, ^_^, new phrase"
    phrases = result["phrases"]
    assert [
        (item["kind"], item["text"], item["status"], item["duplicate_of"]) for item in phrases
    ] == [
        ("trigger", "BLUE HAIR", "emitted", None),
        ("tag", "^_^", "emitted", None),
        ("tag", "blue hair", "duplicate_phrase", 0),
        ("forced", "blue hair", "duplicate_phrase", 0),
        ("forced", "^_^", "duplicate_phrase", 1),
        ("forced", "new phrase", "emitted", None),
    ]
    blue = next(item for item in result["tags"] if item["name"] == "blue_hair")
    assert blue["selected"] and blue["phrase_status"] == "duplicate_phrase"


def test_alias_identity_paging_and_read_only_source_independence(tmp_path, monkeypatch):
    run = make_run(tmp_path, aliases=True)
    source = Path(read(run / "run.json")["source"])
    assert not source.exists()
    before = tree(tmp_path)
    original_open = Path.open
    opened = []

    def guarded_open(path, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+"), (
            "Explanation must not open files for writing"
        )
        assert path.is_relative_to(run), "Explanation must read only the selected retained run"
        opened.append(path)
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded_open)
        first = explain(
            run,
            limit=2,
            expected_run_sha256=digest(run / "run.json"),
            expected_manifest_sha256=digest(run / "manifest.jsonl"),
            expected_source=source,
            expected_sha256=records(run)[0]["sha256"],
        )
        second = explain(run, limit=2, offset=2)
        alias = explain_caption(run, "alias.png")
        all_rows = explain(run)["tags"]
        exhausted = explain(run, offset=10_000)
    assert first["tags"] + second["tags"] == all_rows[:4]
    assert first["has_more"] and first["offset"] == 0 and first["limit"] == 2
    assert first["run_sha256"] == second["run_sha256"] == alias["run_sha256"]
    assert first["identity"]["sha256"] == alias["identity"]["sha256"]
    assert first["identity"]["source_path"] != alias["identity"]["source_path"]
    assert exhausted["tags"] == [] and exhausted["has_more"] is False
    assert first["scope"] == "saved_draft"
    assert (
        first["source_files_read"]
        is first["inference_performed"]
        is first["human_accepted"]
        is False
    )
    assert opened and tree(tmp_path) == before


@pytest.mark.parametrize(
    "missing",
    [name for name in CAPTION_FIELDS if name != "caption_path"],
)
def test_missing_analysis_is_unavailable_instead_of_invented(tmp_path, missing):
    run = make_run(tmp_path)
    rows = records(run)
    rows[0].pop(missing)
    rewrite_records(run, rows)
    result = explain(run)
    assert result["status"] == "unavailable" and result["reason_code"] == "missing_analysis"
    assert "tags" not in result and "caption" not in result


@pytest.mark.parametrize("missing", list(CaptionConfig.__dataclass_fields__))
def test_incomplete_saved_rules_never_inherit_current_defaults(tmp_path, missing):
    run = make_run(tmp_path)
    metadata = read(run / "run.json")
    metadata["caption_rules"].pop(missing)
    save(run / "run.json", metadata)
    result = explain(run)
    assert result["status"] == "unavailable" and result["reason_code"] == "missing_rules"
    assert "tags" not in result


@pytest.mark.parametrize("version", ["wd-caption-v1", "future-caption-v999"])
def test_old_or_unknown_rule_version_stays_unavailable(tmp_path, version):
    run = make_run(tmp_path)
    metadata = read(run / "run.json")
    metadata["caption_version"] = version
    save(run / "run.json", metadata)
    before = tree(tmp_path)
    result = explain(run)
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "unsupported_caption_version"
    assert "tags" not in result and tree(tmp_path) == before


def test_unscored_occurrence_remains_explicitly_unavailable(tmp_path):
    run = make_run(tmp_path)
    result = explain_caption(run, "skipped.png")
    assert result["status"] == "unavailable" and result["reason_code"] == "not_scored"
    assert result["identity"]["source_path"] == "skipped.png" and "tags" not in result


@pytest.mark.parametrize("artifact", ["run.json", "manifest.jsonl", "vector"])
def test_mutation_after_vector_read_cannot_return_stale_explanation(
    tmp_path, monkeypatch, artifact
):
    from image_dataset_train.scored_runs import ScoredRun

    run = make_run(tmp_path)
    original = ScoredRun.vector

    def changing_vector(self, content):
        vector = original(self, content)
        path = run / (self.index[content]["path"] if artifact == "vector" else artifact)
        path.write_bytes(path.read_bytes() + b" ")
        return vector

    monkeypatch.setattr(ScoredRun, "vector", changing_vector)
    with pytest.raises(ValueError, match="changed|hash|mismatch"):
        explain(run)


@pytest.mark.parametrize("location", ["run", "ancestor", "score"])
def test_linked_evidence_rejected_before_resolution(tmp_path, location):
    run = make_run(tmp_path / "original")
    selected = run
    link = tmp_path / "linked"
    if location == "run":
        target = run
        selected = link
    elif location == "ancestor":
        target = run.parent
        selected = link / run.name
    else:
        target = tmp_path / "retained-scores"
        link = run / "scores"
        link.rename(target)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("directory symlink creation unavailable on this host")
        # Directory junctions need no Windows developer-mode/elevation permission.
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if created.returncode:
            pytest.skip("Neither directory symlink nor junction creation is available")
        assert link.is_junction()
    with pytest.raises(ValueError, match="[Ll]ink"):
        explain(selected)


@pytest.mark.parametrize("damage", ["edited", "missing"])
def test_loose_caption_file_is_not_authoritative_draft_evidence(tmp_path, damage):
    run = make_run(tmp_path)
    path = run / records(run)[0]["caption_path"]
    if damage == "edited":
        path.write_text("a local manual edit that is not a saved override", encoding="utf-8")
    else:
        path.unlink()
    before = tree(tmp_path)
    result = explain(run)
    assert result["status"] == "available"
    assert result["caption"] == records(run)[0]["caption"]
    assert str(path) not in result["evidence_sha256"]
    assert tree(tmp_path) == before


def test_complete_response_limit_covers_unpaged_literal_phrases(tmp_path):
    from image_dataset_train.caption_explanations import MAX_EXPLANATION_BYTES

    run = make_run(tmp_path, rules=CaptionConfig(force_tags=["x" * 750_000]))
    before = tree(tmp_path)
    result = explain(run, limit=1)
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "explanation_too_large"
    assert "tags" not in result and "phrases" not in result and "caption" not in result
    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= MAX_EXPLANATION_BYTES
    assert tree(tmp_path) == before


def test_saved_replay_imports_without_model_runtime_or_network_client(tmp_path):
    run = make_run(tmp_path)
    before = tree(tmp_path)
    script = """
import importlib.abc
import json
import sys
from pathlib import Path

class BlockModelPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'onnxruntime', 'onnx', 'huggingface_hub'}:
            raise AssertionError('saved evidence must not import model runtime: ' + fullname)

sys.meta_path.insert(0, BlockModelPackages())
from image_dataset_train.caption_explanations import explain_caption
result = explain_caption(Path(sys.argv[1]), 'portraits/猫.png')
assert result['status'] == 'available'
assert result['inference_performed'] is False
assert not any(name.startswith(('onnxruntime', 'huggingface_hub')) for name in sys.modules)
print(json.dumps({'status': result['status'], 'caption': result['caption']}))
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(run)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["caption"] == records(run)[0]["caption"]
    assert tree(tmp_path) == before
