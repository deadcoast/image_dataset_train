"""Persisted label history is validated without changing or reattributing evidence."""

import json
from copy import deepcopy

import pytest
from test_label_evaluation import evaluation_pilot as evaluation_pilot

from image_dataset_train.label_workspace import LabelWorkspace, _judgment_json, _validate_selection

DIGEST = "a" * 64
SELECTION = "b" * 64


def bare_store():
    store = object.__new__(LabelWorkspace)
    store.members = {DIGEST: {"aliases": []}}
    store.labels = {"blue_hair"}
    store.selection_sha256 = SELECTION
    store.inherited_state = None
    return store


def record(**changes):
    return {
        "value": "present",
        "reviewer": "Synthetic assistant",
        "reviewer_kind": "assistant",
        "notes": "Generated fixture only",
        "at": "2026-11-12T00:00:00+00:00",
        **changes,
    }


def state(*, clear=False, legacy=False):
    saved = record(value="unreviewed" if clear else "present")
    event = {
        "revision": 1,
        "sha256": DIGEST,
        "label": "blue_hair",
        "record": None if clear else deepcopy(saved),
    }
    if not legacy:
        event["actor"] = deepcopy(saved)
    return {
        "schema_version": 1,
        "selection_sha256": SELECTION,
        "revision": 1,
        "history": [event],
        "judgments": {} if clear else {DIGEST: {"blue_hair": saved}},
    }


@pytest.mark.parametrize("clear", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_valid_current_and_actorless_legacy_histories_stay_byte_equivalent(clear, legacy):
    saved = state(clear=clear, legacy=legacy)
    before = deepcopy(saved)
    bare_store()._validate_state(saved, SELECTION)
    assert saved == before
    if not clear:
        assert saved["judgments"][DIGEST]["blue_hair"]["reviewer_kind"] == "assistant"


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
@pytest.mark.parametrize("field", ["schema_version", "revision", "event_revision"])
def test_versions_and_revisions_require_real_integers(field, value):
    saved = state()
    target = saved["history"][0] if field == "event_revision" else saved
    target["revision" if field == "event_revision" else field] = value
    with pytest.raises(ValueError):
        bare_store()._validate_state(saved, SELECTION)


@pytest.mark.parametrize("actor", [None, {}, [], "assistant", record(value="present")])
def test_clearing_actor_must_be_a_valid_unreviewed_record(actor):
    saved = state(clear=True)
    saved["history"][0]["actor"] = actor
    with pytest.raises(ValueError):
        bare_store()._validate_state(saved, SELECTION)


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewer_kind": "unknown"},
        {"reviewer_kind": []},
        {"reviewer": ""},
        {"notes": True},
        {"comparison_exposure": "bad"},
        {"comparison_exposure": [{"run": "/unused", "run_sha256": "not-a-digest"}]},
        {"extra": "unsupported"},
    ],
)
def test_clear_validates_attribution_and_exposure_independently(changes):
    saved = state(clear=True)
    saved["history"][0]["actor"].update(changes)
    with pytest.raises(ValueError):
        bare_store()._validate_state(saved, SELECTION)


def test_present_actor_cannot_disagree_with_valid_record():
    saved = state()
    saved["history"][0]["actor"]["reviewer_kind"] = "human"
    with pytest.raises(ValueError, match="actor differs"):
        bare_store()._validate_state(saved, SELECTION)


def test_summary_rejects_caller_supplied_invalid_state():
    saved = state()
    saved["judgments"][DIGEST]["blue_hair"]["reviewer_kind"] = "human"
    with pytest.raises(ValueError, match="differ from their history"):
        bare_store().summary(saved)


def test_summary_cannot_replace_inherited_history_with_another_valid_history():
    store = bare_store()
    store.inherited_state = state()
    replacement = state()
    replacement["history"][0]["record"]["reviewer_kind"] = "human"
    replacement["history"][0]["actor"]["reviewer_kind"] = "human"
    replacement["judgments"][DIGEST]["blue_hair"]["reviewer_kind"] = "human"
    with pytest.raises(ValueError, match="Carried-forward"):
        store.summary(replacement)


@pytest.mark.parametrize("missing", ["record", "sha256", "label", "revision"])
def test_event_required_fields_cannot_be_silently_defaulted(missing):
    saved = state(clear=True)
    del saved["history"][0][missing]
    with pytest.raises(ValueError, match="event"):
        bare_store()._validate_state(saved, SELECTION)


@pytest.mark.parametrize("raw", ['{"revision": 0, "revision": 1}', '{"value": NaN}'])
def test_ambiguous_or_nonfinite_json_is_invalid(raw):
    with pytest.raises(ValueError):
        _judgment_json(raw)


@pytest.mark.parametrize("version", [True, 1.0])
def test_frozen_selection_schema_requires_integer(version):
    with pytest.raises(ValueError, match="Invalid label selection"):
        _validate_selection({"schema_version": version})


def payload(store, value="present"):
    return {
        "image": next(iter(store.members)),
        "label": "blue_hair",
        "value": value,
        "reviewer": "Synthetic assistant",
        "reviewer_kind": "assistant",
        "notes": "Synthetic persistence check",
        "expected_revision": store.read()["revision"],
    }


def test_invalid_saved_actor_rejected_by_read_summary_and_locked_save(evaluation_pilot):
    store = LabelWorkspace(evaluation_pilot[3])
    store.save(payload(store, "unreviewed"))
    saved = store.read()
    saved["history"][0]["actor"]["reviewer_kind"] = "invalid"
    path = store.directory / "judgments.json"
    path.write_text(json.dumps(saved), encoding="utf-8")
    before = path.read_bytes()
    request = {**record(), "image": next(iter(store.members)), "label": "blue_hair"}
    for action in (
        store.read,
        store.summary,
        lambda: store.save_many([request], expected_revision=1),
    ):
        with pytest.raises(ValueError, match="human or assistant"):
            action()
        assert path.read_bytes() == before


def test_legacy_record_attribution_and_exposure_survive_clear_and_resave(evaluation_pilot):
    store = LabelWorkspace(evaluation_pilot[3])
    exposure = {
        "run": str(evaluation_pilot[2]),
        "run_sha256": "c" * 64,
        "at": "2026-11-12T00:00:00+00:00",
        "reviewer": "Synthetic assistant",
        "reviewer_kind": "assistant",
    }
    store.save({**payload(store), "comparison_exposure": [exposure]})
    saved = store.read()
    del saved["history"][0]["actor"]
    path = store.directory / "judgments.json"
    path.write_text(json.dumps(saved), encoding="utf-8")
    historical = deepcopy(saved["history"])
    store.save(payload(store, "unreviewed"))
    result = store.save(payload(store, "absent"))
    assert result["state"]["history"][:1] == historical
    current = result["state"]["judgments"][next(iter(store.members))]["blue_hair"]
    assert current["reviewer_kind"] == "assistant"
    assert current["comparison_exposure"] == [exposure]
    assert result["summary"]["reviewer_kinds"] == {"assistant": 1}


def test_label_save_revalidates_after_acquiring_lock(evaluation_pilot, monkeypatch):
    import image_dataset_train.label_workspace as module

    store = LabelWorkspace(evaluation_pilot[3])
    request = payload(store)
    lock_class = module.FileLock
    path = store.directory / "judgments.json"
    damaged = []

    class CorruptOnEntry:
        def __init__(self, *args, **kwargs):
            self.lock = lock_class(*args, **kwargs)

        def __enter__(self):
            self.lock.acquire()
            saved = store.read()
            saved["schema_version"] = True
            path.write_text(json.dumps(saved), encoding="utf-8")
            damaged.append(path.read_bytes())
            return self

        def __exit__(self, *args):
            self.lock.release()

    monkeypatch.setattr(module, "FileLock", CorruptOnEntry)
    with pytest.raises(ValueError, match="history/identity"):
        store.save(request)
    assert path.read_bytes() == damaged[0]
