"""Recovery navigation reads bounded saved metadata and never inspects source bytes."""

import hashlib
import json
from pathlib import Path

import pytest

from image_dataset_train import recovery_catalog as catalog


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def records(tmp_path):
    home, source = tmp_path / "application 猫", tmp_path / "offline source"
    removal = home / "operations" / "removed" / "operation.json"
    plan_hash = _save(
        removal.with_name("plan.json"),
        [
            {
                "image": "nested/a.png",
                "caption": "nested/a.txt",
                "status": "ready",
                "image_sha256": "a" * 64,
                "caption_sha256": "b" * 64,
            }
        ],
    )
    _save(
        removal,
        {
            "schema_version": 1,
            "action": "remove",
            "source": str(source),
            "status": "cancelled",
            "backup": str(removal.parent / "captions"),
            "plan_sha256": plan_hash,
            "journal_sha256": None,
            "updated_at": "2026-11-10T00:00:00+00:00",
        },
    )
    removal.with_name("journal.jsonl").write_bytes(b'{"event":"backup_verified"}\n{"event":')
    collision = home / "operations" / "collision" / "fix.json"
    _save(
        collision,
        {
            "schema_version": 1,
            "fix_code": "tf001",
            "source": str(source),
            "status": "failed",
            "groups": [
                {
                    "directory": ".",
                    "stem": "pair",
                    "actions": [
                        {
                            "kind": "caption",
                            "source": "pair.txt",
                            "target": "pair.txt",
                            "sha256": "b" * 64,
                            "done": True,
                        },
                        {
                            "kind": "image",
                            "source": "pair.png",
                            "target": "pair_2.png",
                            "sha256": "c" * 64,
                            "done": False,
                        },
                    ],
                    "retained": [],
                }
            ],
        },
    )
    restoration = home / "operations" / "restored" / "restore.json"
    _save(
        restoration,
        {
            "schema_version": 1,
            "action": "restore_captions",
            "source": str(source),
            "home": str(home),
            "status": "completed",
            "removal_receipt": str(removal),
            "items": [
                {
                    "image": "nested/a.png",
                    "caption": "nested/a.txt",
                    "image_sha256": "a" * 64,
                    "caption_sha256": "b" * 64,
                    "backup": str(removal.parent / "captions/nested/a.txt"),
                    "status": "restored",
                }
            ],
        },
    )
    package = home / "recovery" / "application" / "repair" / "repair.json"
    _save(
        package,
        {
            "schema_version": 1,
            "action": "repair_package",
            "status": "completed",
            "wheel": str(tmp_path / "missing.whl"),
            "wheel_sha256": "e" * 64,
            "site_packages": str(tmp_path / "missing environment"),
            "started_at": "2026-11-10T01:00:00+00:00",
            "files": [
                {
                    "path": "image_dataset_train/review_ui.py",
                    "before_sha256": "c" * 64,
                    "expected_sha256": "d" * 64,
                    "backup": "image_dataset_train/review_ui.py",
                    "status": "restored",
                }
            ],
        },
    )
    return (
        home,
        source,
        {"removal": removal, "collision": collision, "restore": restoration, "package": package},
    )


def test_metadata_navigation_offline_without_workers_or_backup_reads(records, monkeypatch):
    home, source, receipts = records
    assert not source.exists()
    before = _tree(home)
    original_open = Path.open
    allowed = {str(p) for p in receipts.values()} | {
        str(receipts["removal"].with_name("plan.json"))
    }

    def metadata_only(path, *args, **kwargs):
        assert str(path) in allowed, f"Read unexpected source/backup/journal: {path}"
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", metadata_only)
        result = catalog.list_recovery(home)
        assert not result["errors"]
        assert {r["kind"] for r in result["records"]} == catalog.KINDS
        for record in result["records"]:
            assert (
                catalog.select_recovery(
                    home, record["id"], expected_sha256=record["receipt_sha256"]
                )
                == record
            )
            assert record["metadata_verification"] == "metadata_only"
            assert not record["source_revalidated"]
    assert _tree(home) == before and not source.exists()
    removal = next(r for r in result["records"] if r["kind"] == "removal")
    assert removal["affected_count"] == 1 and removal["items"][0]["path"] == "nested/a.txt"
    assert any("journal" in warning for warning in removal["warnings"])
    assert len(removal["metadata_inputs"]) == 2


def test_missing_home_and_filters_do_not_create_state(records, tmp_path, monkeypatch):
    missing = tmp_path / "never created"
    monkeypatch.setenv("TRAINIME_HOME", str(missing))
    assert catalog.list_recovery()["records"] == [] and not missing.exists()
    home, source, _ = records
    result = catalog.list_recovery(home, source=source, kind="collision", status="failed")
    assert len(result["records"]) == 1 and result["records"][0]["kind"] == "collision"
    assert catalog.list_recovery(home, source=tmp_path / "other")["records"] == []
    assert len(catalog.list_recovery(home, source=source)["records"]) == 3
    with pytest.raises(ValueError, match="Unknown recovery"):
        catalog.list_recovery(home, kind="unknown")


def test_stale_receipt_and_dependent_plan_ids_reject(records):
    home, _, receipts = records
    old = next(r for r in catalog.list_recovery(home)["records"] if r["kind"] == "removal")
    document = json.loads(receipts["removal"].read_text())
    document.pop("plan_sha256")
    _save(receipts["removal"], document)
    with pytest.raises(ValueError, match="missing, changed"):
        catalog.select_recovery(home, old["id"])
    legacy = next(r for r in catalog.list_recovery(home)["records"] if r["kind"] == "removal")
    assert any("Legacy" in warning for warning in legacy["warnings"])
    plan = receipts["removal"].with_name("plan.json")
    rows = json.loads(plan.read_text())
    rows[0]["status"] = "missing"
    _save(plan, rows)
    current = next(r for r in catalog.list_recovery(home)["records"] if r["kind"] == "removal")
    assert current["receipt_sha256"] == legacy["receipt_sha256"] and current["id"] != legacy["id"]
    with pytest.raises(ValueError, match="missing, changed"):
        catalog.select_recovery(home, legacy["id"], expected_sha256=legacy["receipt_sha256"])
    with pytest.raises(ValueError, match="changed"):
        catalog.select_recovery(home, current["id"], expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="exact recovery"):
        catalog.select_recovery(home, current["id"][:12])


def test_receipt_identity_distinguishes_identical_bytes_in_different_locations(records):
    home, _, receipts = records
    path = home / "operations" / "another collision" / "fix.json"
    path.parent.mkdir()
    path.write_bytes(receipts["collision"].read_bytes())
    records = catalog.list_recovery(home, kind="collision")["records"]
    assert len(records) == 2 and len({r["id"] for r in records}) == 2
    assert len({r["receipt_sha256"] for r in records}) == 1


@pytest.mark.parametrize(
    "damage", ["missing_plan", "plan_hash", "traversal", "bad_type", "oversized", "deep_json"]
)
def test_bad_metadata_isolated_from_other_receipts(records, monkeypatch, damage):
    home, _, receipts = records
    receipt = receipts["removal"]
    if damage == "missing_plan":
        receipt.with_name("plan.json").unlink()
    elif damage == "plan_hash":
        receipt.with_name("plan.json").write_text("[]")
    elif damage == "traversal":
        plan = [{"image": "../a.png", "caption": "../a.txt", "status": "ready"}]
        digest = _save(receipt.with_name("plan.json"), plan)
        metadata = json.loads(receipt.read_text())
        metadata["plan_sha256"] = digest
        _save(receipt, metadata)
    elif damage == "bad_type":
        _save(receipt, ["wrong"])
    elif damage == "oversized":
        # Only this receipt exceeds the reduced bound; valid peers remain readable.
        receipt.write_text(" " * 10000)
        monkeypatch.setattr(catalog, "MAX_METADATA_BYTES", 3000)
    else:
        receipt.write_text("[" * 5000 + "]" * 5000)
    result = catalog.list_recovery(home)
    assert {r["kind"] for r in result["records"]} == {"collision", "restore", "package"}
    assert len(result["errors"]) == 1 and result["errors"][0]["path"] == str(receipt)


@pytest.mark.parametrize("kind", ["collision", "restore", "package"])
def test_unsafe_saved_targets_are_not_exposed(records, kind):
    home, _, receipts = records
    path = receipts[kind]
    value = json.loads(path.read_text())
    if kind == "collision":
        value["groups"][0]["actions"][1]["target"] = "../escaped.png"
    elif kind == "restore":
        value["items"][0]["backup"] = str(home.parent / "unrelated.txt")
    else:
        value["files"][0]["path"] = "other_package/module.py"
    _save(path, value)
    result = catalog.list_recovery(home)
    assert kind not in {r["kind"] for r in result["records"]}
    assert len(result["errors"]) == 1


def test_linked_metadata_roots_do_not_follow_targets(records, tmp_path):
    home, _, _ = records
    linked = tmp_path / "linked home"
    try:
        linked.symlink_to(home, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    result = catalog.list_recovery(linked)
    assert not result["records"] and len(result["errors"]) == 2


def test_unrelated_layouts_are_not_discovered(records):
    home, _, receipts = records
    unrelated = home / "another" / "deep" / "fix.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(receipts["collision"].read_bytes())
    tag = home / "operations" / "tagged" / "operation.json"
    _save(tag, {"schema_version": 1, "action": "tag"})
    assert len(catalog.list_recovery(home)["records"]) == 4


def test_historical_collision_can_retain_case_distinct_captions(records):
    home, _, receipts = records
    receipt = receipts["collision"]
    document = json.loads(receipt.read_text())
    document["groups"][0]["actions"].insert(
        1,
        {
            "kind": "caption",
            "source": "PAIR.txt",
            "target": "PAIR.txt",
            "sha256": "a" * 64,
            "done": True,
        },
    )
    _save(receipt, document)
    result = catalog.list_recovery(home, kind="collision")
    assert not result["errors"]
    assert [item["path"] for item in result["records"][0]["items"]] == [
        "pair.txt",
        "PAIR.txt",
        "pair.png",
    ]


def test_source_overlap_and_nonregular_receipt_are_isolated(records):
    home, _, receipts = records
    collision = receipts["collision"]
    document = json.loads(collision.read_text())
    document["source"] = str(home / "operations")
    _save(collision, document)
    receipts["package"].unlink()
    receipts["package"].mkdir()
    result = catalog.list_recovery(home)
    assert {r["kind"] for r in result["records"]} == {"removal", "restore"}
    assert len(result["errors"]) == 2


def test_selection_rechecks_metadata_after_discovery(records, monkeypatch):
    home, _, receipts = records
    selected = catalog.list_recovery(home, kind="collision")["records"][0]
    actual = catalog.list_recovery

    def changed_after_list(*args, **kwargs):
        result = actual(*args, **kwargs)
        document = json.loads(receipts["collision"].read_text())
        document["status"] = "completed"
        _save(receipts["collision"], document)
        return result

    monkeypatch.setattr(catalog, "list_recovery", changed_after_list)
    with pytest.raises(ValueError, match="metadata changed"):
        catalog.select_recovery(home, selected["id"])
