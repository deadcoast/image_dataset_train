"""Browsing persistence cannot become review evidence or cross report identities."""

import copy
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from filelock import FileLock

from image_dataset_train.config import Config, ValidationConfig
from image_dataset_train.inventory import file_sha256
from image_dataset_train.review_preferences import ReviewPreferences, empty_filters
from image_dataset_train.reviews import ReviewConflict


def tree(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def browsing(tmp_path):
    config = Config(
        tmp_path / "source",
        tmp_path / "runs",
        ValidationConfig(),
        models=tmp_path / "models",
        scores=tmp_path / "scores",
        reviews=tmp_path / "reviews",
        exports=tmp_path / "exports",
    )
    for directory in (config.source, config.reviews, config.exports, config.models, config.scores):
        directory.mkdir()
        (directory / "protected.txt").write_text("original evidence", encoding="utf-8")
    report = config.runs / "qa"
    report.mkdir(parents=True)
    (report / "run.json").write_text('{"stage":"qa","revision":7}\n', encoding="utf-8")
    data = {
        "entries": [
            {
                "id": "a" * 64,
                "group_id": "group-one",
                "findings": ["missing-caption"],
                "labels": ["portrait", "猫"],
                "subset": "solo",
                "split": "train",
                "decision": "include",
            },
            {
                "id": "b" * 64,
                "group_id": "group-two",
                "findings": [],
                "labels": ["scenery"],
                "subset": "landscape",
                "split": "validation",
                "decision": "exclude",
            },
            {
                "id": "c" * 64,
                "group_id": "group-two",
                "findings": ["unreviewed"],
                "labels": [],
                "subset": "",
                "split": "unpublished",
                "decision": "unreviewed",
            },
        ]
    }
    home = tmp_path / "application"
    store = ReviewPreferences(config, report, file_sha256(report / "run.json"), data, root=home)
    return store, config, data, home


def update(store, **changes):
    state = store.read()
    payload = {
        "expected_revision": state["revision"],
        "last": state["last"],
        "views": state["views"],
    }
    payload["last"]["image_id"] = "b" * 64
    payload["last"]["position"] = 1
    payload["last"]["filters"].update(label="猫", search="a phrase", pilot=True, group="group-one")
    payload.update(changes)
    return payload


def reopened(browsing, *, run=None, digest=None, root=None):
    store, config, data, home = browsing
    run = run or store.run
    return ReviewPreferences(
        config, run, digest or file_sha256(run / "run.json"), data, root=root or home
    )


def test_empty_read_is_pure_and_defaults_are_independent(browsing, tmp_path):
    store, _, _, home = browsing
    before = tree(tmp_path)
    empty = store.read()
    assert empty == {
        "schema_version": 1,
        "report_id": store.report_id,
        "revision": 0,
        "last": {
            "filters": empty_filters(),
            "image_id": None,
            "position": 0,
            "pair": {"decision": "unreviewed", "offset": 0, "pair_id": None},
        },
        "views": [],
    }
    empty["last"]["filters"]["search"] = "caller edit"
    assert store.read()["last"]["filters"]["search"] == ""
    assert not home.exists() and tree(tmp_path) == before


def test_saved_state_survives_new_instance_and_only_preferences_are_written(browsing, tmp_path):
    store, _, _, home = browsing
    before = tree(tmp_path)
    payload = update(store)
    payload["last"]["pair"] = {"decision": "all", "offset": 40, "pair_id": "f" * 64}
    payload["views"] = [
        {"name": "猫 portraits", "filters": copy.deepcopy(payload["last"]["filters"])}
    ]
    saved = store.save(payload)
    assert saved["revision"] == 1 and reopened(browsing).read() == saved
    assert store.path == home / "review-preferences" / (store.report_id + ".json")
    after = tree(tmp_path)
    assert all(after[path] == digest for path, digest in before.items())
    assert all(
        path.startswith("application\\review-preferences\\")
        or path.startswith("application/review-preferences/")
        for path in after.keys() - before.keys()
    )
    raw = store.path.read_text(encoding="utf-8")
    assert "猫" in raw and str(store.run) not in raw and "source_path" not in raw
    assert set(json.loads(raw)) == {"schema_version", "report_id", "revision", "last", "views"}


def test_noop_preserves_revision_and_reset_requires_current_cas(browsing):
    store = browsing[0]
    saved = store.save(update(store))
    before = store.path.read_bytes()
    same = {"expected_revision": 1, "last": saved["last"], "views": saved["views"]}
    assert store.save(same) == saved and store.path.read_bytes() == before
    blank = store.empty()
    with pytest.raises(ReviewConflict):
        store.save({"expected_revision": 0, "last": blank["last"], "views": []})
    reset = store.save({"expected_revision": 1, "last": blank["last"], "views": []})
    assert reset == {**blank, "revision": 2}


def test_two_sessions_cannot_erase_each_others_named_views(browsing):
    first, second = browsing[0], reopened(browsing)
    barrier = Barrier(2)

    def save(store, name):
        payload = update(store)
        payload["views"] = [{"name": name, "filters": empty_filters()}]
        barrier.wait(timeout=10)
        try:
            return store.save(payload)
        except ReviewConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(save, first, "first"), executor.submit(save, second, "second")]
        outcomes = [future.result(timeout=15) for future in futures]
    assert sum(result is not None for result in outcomes) == 1
    assert first.read() == next(result for result in outcomes if result is not None)
    assert first.read()["revision"] == 1


def test_busy_lock_is_a_conflict_without_state_change(browsing):
    store = browsing[0]
    saved = store.save(update(store))
    before = store.path.read_bytes()
    payload = update(store)
    payload["last"]["filters"]["search"] = "second edit"
    with FileLock(str(store.lock_path), timeout=0):
        with pytest.raises(ReviewConflict, match="being saved"):
            reopened(browsing).save(payload)
    assert store.path.read_bytes() == before and store.read() == saved


def test_report_identity_uses_canonical_path_and_exact_metadata(browsing, tmp_path):
    store = browsing[0]
    saved = store.save(update(store))
    expected = hashlib.sha256(
        (os.path.normcase(str(store.run.resolve())) + "\0" + store.report_sha256).encode()
    ).hexdigest()
    assert store.report_id == expected
    assert reopened(browsing, run=store.run / ".." / store.run.name).read() == saved
    copied = tmp_path / "other-qa"
    copied.mkdir()
    (copied / "run.json").write_bytes((store.run / "run.json").read_bytes())
    different_path = reopened(browsing, run=copied)
    assert different_path.report_id != store.report_id and different_path.read()["revision"] == 0
    (store.run / "run.json").write_text('{"stage":"qa","revision":8}', encoding="utf-8")
    different_metadata = reopened(browsing)
    assert (
        different_metadata.report_id != store.report_id
        and different_metadata.read()["revision"] == 0
    )
    with pytest.raises(ValueError, match="identity changed"):
        store.read()
    assert json.loads(store.path.read_text(encoding="utf-8")) == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("finding", "other-finding"),
        ("label", "unknown"),
        ("subset", "unknown"),
        ("split", "unknown"),
        ("decision", "related"),
        ("group", "unknown"),
        ("pilot", 1),
        ("pilot", "true"),
        ("search", "x" * 513),
        ("search", "line\nsecond"),
        ("search", "\0"),
        ("search", "\ud800"),
        ("search", []),
        ("label", None),
    ],
)
def test_invalid_filters_reject_before_creating_storage(browsing, field, value):
    store = browsing[0]
    payload = update(store)
    payload["last"]["filters"][field] = value
    with pytest.raises(ValueError):
        store.save(payload)
    assert not browsing[3].exists()


@pytest.mark.parametrize(
    "path,value",
    [
        (("expected_revision",), True),
        (("expected_revision",), -1),
        (("expected_revision",), 1.0),
        (("expected_revision",), 1_000_000_000),
        (("last", "position"), True),
        (("last", "position"), -1),
        (("last", "position"), 3),
        (("last", "image_id"), "e" * 64),
        (("last", "image_id"), []),
        (("last", "pair", "decision"), "include"),
        (("last", "pair", "decision"), []),
        (("last", "pair", "offset"), 1),
        (("last", "pair", "offset"), -20),
        (("last", "pair", "offset"), True),
        (("last", "pair", "pair_id"), "A" * 64),
        (("last", "pair", "pair_id"), "not-an-identity"),
    ],
)
def test_invalid_resume_values_cannot_write(browsing, path, value):
    store = browsing[0]
    payload = update(store)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        store.save(payload)
    assert not browsing[3].exists()


@pytest.mark.parametrize(
    "path,key",
    [
        ((), "caption"),
        (("last",), "reason"),
        (("last", "filters"), "assessment"),
        (("last", "pair"), "reviewer"),
    ],
)
def test_non_browsing_and_private_fields_are_rejected(browsing, path, key):
    store = browsing[0]
    payload = update(store)
    target = payload
    for field in path:
        target = target[field]
    target[key] = "never persist this"
    with pytest.raises(ValueError, match="fields"):
        store.save(payload)
    assert not browsing[3].exists()


@pytest.mark.parametrize(
    "names",
    [
        [""],
        [" leading"],
        ["trailing "],
        ["e\u0301"],
        ["x" * 81],
        ["line\nfeed"],
        ["duplicate", "duplicate"],
        [str(index) for index in range(21)],
    ],
)
def test_invalid_or_ambiguous_named_views_reject(browsing, names):
    store = browsing[0]
    payload = update(store, views=[{"name": name, "filters": empty_filters()} for name in names])
    with pytest.raises(ValueError):
        store.save(payload)
    assert not browsing[3].exists()


def test_name_and_search_limits_allow_valid_unicode_and_twenty_distinct_views(browsing):
    store = browsing[0]
    payload = update(store)
    payload["last"]["filters"]["search"] = "猫" * 512
    payload["views"] = [{"name": str(i) + "é" * 78, "filters": empty_filters()} for i in range(20)]
    saved = store.save(payload)
    assert len(saved["views"]) == 20 and store.read() == saved


@pytest.mark.parametrize(
    "corruption", ["json", "oversize", "version", "report", "revision", "extra", "view-filter"]
)
def test_corrupt_saved_state_is_preserved_and_never_reset_implicitly(browsing, corruption):
    store = browsing[0]
    payload = update(store)
    saved = store.save(payload)
    if corruption == "json":
        raw = b"{unfinished"
    elif corruption == "oversize":
        raw = b" " * (64 * 1024 + 1)
    else:
        if corruption == "version":
            saved["schema_version"] = True
        if corruption == "report":
            saved["report_id"] = "0" * 64
        if corruption == "revision":
            saved["revision"] = True
        if corruption == "extra":
            saved["reason"] = "not browsing state"
        if corruption == "view-filter":
            saved["views"] = [{"name": "stale", "filters": {**empty_filters(), "label": "missing"}}]
        raw = json.dumps(saved).encode()
    store.path.write_bytes(raw)
    with pytest.raises(ValueError):
        store.read()
    with pytest.raises(ValueError):
        store.save(payload)
    assert store.path.read_bytes() == raw


def test_aggregate_utf8_size_bound_rejects_before_writes(browsing):
    store, _, data, _ = browsing
    large = "猫" * 4096
    data["entries"][0]["labels"] = [large]
    store = reopened(browsing)
    payload = update(store)
    payload["last"]["filters"]["label"] = large
    payload["views"] = [
        {"name": str(i), "filters": {**empty_filters(), "label": large}} for i in range(20)
    ]
    with pytest.raises(ValueError, match="64 KiB"):
        store.save(payload)
    assert not browsing[3].exists()


@pytest.mark.parametrize(
    "protected", ["source", "runs", "reviews", "exports", "scores", "models", "report"]
)
def test_application_home_inside_any_dataset_tree_fails_without_writes(
    browsing, tmp_path, protected
):
    base, config, _, _ = browsing
    root = base.run if protected == "report" else getattr(config, protected)
    store = reopened(browsing, root=root / "bad-app-home")
    before = tree(tmp_path)
    with pytest.raises(ValueError, match="outside source"):
        store.read()
    blank = store.empty()
    with pytest.raises(ValueError, match="outside source"):
        store.save({"expected_revision": 0, "last": blank["last"], "views": []})
    assert tree(tmp_path) == before and not store.directory.exists()


def directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("Directory links unavailable")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert link.is_junction()


@pytest.mark.parametrize("location", ["home", "preferences", "report"])
def test_linked_ancestors_reject_read_and_save(browsing, tmp_path, location):
    base, _, _, home = browsing
    destination = tmp_path / "linked-destination"
    destination.mkdir()
    if location == "home":
        directory_link(home, destination)
        store = base
    elif location == "preferences":
        home.mkdir()
        directory_link(base.directory, destination)
        store = base
    else:
        link = tmp_path / "linked-report"
        directory_link(link, base.run)
        store = reopened(browsing, run=link)
    blank = store.empty()
    with pytest.raises(ValueError, match="Linked"):
        store.read()
    with pytest.raises(ValueError, match="Linked"):
        store.save({"expected_revision": 0, "last": blank["last"], "views": []})
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("file", ["state", "lock", "report"])
def test_hardlinked_files_are_rejected_without_altering_either_name(browsing, tmp_path, file):
    store = browsing[0]
    store.directory.mkdir(parents=True)
    target = tmp_path / "linked-file"
    target.write_bytes(b"preserved")
    path = {"state": store.path, "lock": store.lock_path, "report": store.run / "run.json"}[file]
    if path.exists():
        target.write_bytes(path.read_bytes())
        path.unlink()
    os.link(target, path)
    before = target.read_bytes()
    with pytest.raises(ValueError, match="Linked"):
        store.read()
    blank = store.empty()
    with pytest.raises(ValueError, match="Linked"):
        store.save({"expected_revision": 0, "last": blank["last"], "views": []})
    assert path.read_bytes() == target.read_bytes() == before


def test_permission_denied_is_not_an_absent_state(browsing, monkeypatch):
    store = browsing[0]
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == store.path:
            raise PermissionError("denied fixture preference file")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError):
        store.read()
    blank = store.empty()
    with pytest.raises(PermissionError):
        store.save({"expected_revision": 0, "last": blank["last"], "views": []})
    assert not browsing[3].exists()


@pytest.mark.parametrize("existing", [False, True])
def test_report_mutation_during_preference_read_is_rejected(browsing, monkeypatch, existing):
    store = browsing[0]
    if existing:
        store.save(update(store))
    original = Path.open

    def changing(path, *args, **kwargs):
        if path == store.path:
            with original(store.run / "run.json", "wb") as output:
                output.write(b'{"stage":"qa","changed":true}')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", changing)
    with pytest.raises(ValueError, match="identity changed"):
        store.read()


def test_no_source_or_review_artifact_is_opened_for_resume(browsing, monkeypatch):
    store, config, _, _ = browsing
    payload = update(store)
    original = Path.open

    def bounded(path, *args, **kwargs):
        if any(
            path.is_relative_to(root)
            for root in (
                config.source,
                config.reviews,
                config.exports,
                config.models,
                config.scores,
            )
        ):
            raise AssertionError(f"Browsing opened dataset evidence: {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", bounded)
    saved = store.save(payload)
    assert store.read() == saved
