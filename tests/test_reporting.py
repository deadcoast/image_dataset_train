from image_dataset_train.reporting import content_report


def test_inventory_measurement_starts_before_scan_and_labels_reused_inventory(
    tmp_path, monkeypatch
):
    import json

    from PIL import Image

    from image_dataset_train import execution, runs
    from image_dataset_train.config import Config, ValidationConfig

    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (128, 192)).save(source / "one.png")
    config = Config(source, tmp_path / "runs", ValidationConfig())
    clock = {"now": 10.0}
    monkeypatch.setattr(execution, "perf_counter", lambda: clock["now"])
    original_scan = runs.scan
    records = []

    def measured_scan(*args):
        records.extend(original_scan(*args))
        clock["now"] += 7.5
        return records

    monkeypatch.setattr(runs, "scan", measured_scan)
    output, _ = runs.run_scan(config)
    meta = json.loads((output / "run.json").read_text())
    assert meta["metrics"]["elapsed_seconds"] == 7.5
    assert meta["metrics"]["timing_scope"] == "stage_processing"
    assert meta["metrics"]["payload_bytes"] == (output / "manifest.jsonl").stat().st_size
    assert meta["intake"]["source_image_bytes"] == (source / "one.png").stat().st_size
    published, _ = runs.publish_scan(config, records)
    assert json.loads((published / "run.json").read_text())["metrics"]["timing_scope"] == (
        "inventory_publication_only"
    )


def test_legacy_and_missing_evidence_are_not_zero_observations():
    members = [
        {"source_path": name, "sha256": name, "review_decision": decision}
        for name, decision in [("old", "include"), ("missing", "unreviewed")]
    ]
    drafts = {
        ("old", "old"): {
            "selected_tags": [{"name": "blue_hair", "category": 0}],
            "ratings": {"general": float("nan")},
        }
    }
    result = content_report(
        members, drafts, {"run_id": "old"}, evidence_source="caption_run", manifest_available=True
    )
    scope = result["scopes"]["snapshot"]
    assert scope["tagged_images"] == scope["untagged_images"] == 1
    assert scope["selected_tags"]["available_images"] == 1
    assert scope["selected_tags"]["top_tags"][0]["images"] == 1
    assert scope["observed_tags"]["available_images"] == 0
    assert scope["observed_tags"]["unavailable_images"] == 2
    assert scope["composition"] == {"counts": {}, "unavailable_images": 2}
    assert scope["ratings"]["unavailable_images"] == 2
    assert "model" not in result["provenance"]
    assert "runtime" not in result["provenance"]
    result = content_report(
        members, {}, None, evidence_source="export_provenance", manifest_available=False
    )
    assert result["provenance"] is None
    assert result["scopes"]["included"]["untagged_images"] == 1
