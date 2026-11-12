import json

import pytest
from filelock import FileLock
from test_preparation import collection as collection
from test_preparation import run

from image_dataset_train.collection_registry import CollectionRegistry


def test_empty_registry_reads_create_nothing(tmp_path):
    root = tmp_path / "absent-home"
    registry = CollectionRegistry(root)
    assert registry.read() == {"schema_version": 1, "revision": 0, "collections": []}
    assert registry.list() == []
    with pytest.raises(ValueError, match="unknown"):
        registry.resolve("unknown")
    assert not root.exists()


def test_explicit_registration_is_idempotent_offline_and_unregister_only(collection, tmp_path):
    config, workspace = collection
    run(config, workspace)
    registry = CollectionRegistry(tmp_path / "application")
    entry = registry.register(workspace, name="Images café 雪")
    original = registry.path.read_bytes()
    original_workspace = {
        p.relative_to(workspace): p.read_bytes() for p in workspace.rglob("*") if p.is_file()
    }
    config.source.rename(config.source.with_name("offline-originals"))
    assert registry.register(workspace / ".." / workspace.name) == entry
    assert registry.path.read_bytes() == original
    assert registry.resolve("IMAGES CAFÉ 雪") == entry
    assert registry.resolve(entry["id"]) == entry
    assert registry.list(source=config.source) == [entry]
    assert registry.remove(entry["id"]) == entry
    assert registry.list() == []
    assert {
        p.relative_to(workspace): p.read_bytes() for p in workspace.rglob("*") if p.is_file()
    } == original_workspace


def test_names_are_unique_and_rename_is_explicit(collection, tmp_path):
    config, workspace = collection
    run(config, workspace)
    another = tmp_path / "another-workspace"
    run(config, another)
    registry = CollectionRegistry(tmp_path / "application")
    first = registry.register(workspace, "Set")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(another, "set")
    assert registry.resolve("Set") == first
    renamed = registry.register(workspace, "New name")
    assert renamed["id"] == first["id"] and renamed["registered_at"] == first["registered_at"]
    assert registry.register(workspace) == renamed
    with pytest.raises(ValueError, match="unknown"):
        registry.resolve("Set")


def test_corrupt_registry_is_preserved_and_writes_are_serialized(collection, tmp_path):
    config, workspace = collection
    run(config, workspace)
    registry = CollectionRegistry(tmp_path / "application")
    registry.register(workspace)
    with FileLock(str(registry.root / "collections.lock")):
        with pytest.raises(ValueError, match="Another collection"):
            registry.register(workspace, "rename")
    registry.path.write_text('{"schema_version":999}', encoding="utf-8")
    before = registry.path.read_bytes()
    with pytest.raises(ValueError, match="Invalid collection registry"):
        registry.register(workspace)
    assert registry.path.read_bytes() == before


def test_registry_refuses_source_or_workspace_storage(collection):
    config, workspace = collection
    run(config, workspace)
    for root in (config.source, workspace / "registry"):
        with pytest.raises(ValueError, match="outside source"):
            CollectionRegistry(root).register(workspace)
        assert not (root / "collections.json").exists()


def test_registry_rejects_linked_metadata_without_following_it(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"schema_version": 1, "revision": 0, "collections": []}))
    root = tmp_path / "application"
    root.mkdir()
    try:
        (root / "collections.json").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="Linked"):
        CollectionRegistry(root).read()
    assert json.loads(outside.read_text())["collections"] == []
