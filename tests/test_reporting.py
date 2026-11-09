from image_dataset_train.reporting import content_report


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
