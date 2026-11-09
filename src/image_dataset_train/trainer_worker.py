"""Run inside the isolated trainer interpreter; no application or model imports needed."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import sys
import tomllib
import traceback
from pathlib import Path


def verify_runtime(requirements: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("The qualified CPU import runtime requires Python 3.12")
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(("#", " ")):
            name, version = line.split("==", 1)
            if importlib.metadata.version(name) != version:
                raise ValueError(f"Runtime package drift: {name}; rerun trainer-setup")


def inspect_dataset(trainer: Path, export: Path, requirements: Path) -> dict:
    verify_runtime(requirements)
    sys.path.insert(0, str(trainer))
    import torch
    from library import config_util
    from library.utils import IMAGE_TRANSFORMS, load_image, trim_and_resize_if_required

    os.chdir(export)
    rows = [
        json.loads(line)
        for line in (export / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    splits = {}
    for split in sorted({row["split"] for row in rows}):
        expected = {
            str((export / row["image_path"]).resolve()): row
            for row in rows
            if row["split"] == split
        }
        user_config = config_util.load_user_config(str(export / f"{split}.toml"))
        blueprint = config_util.BlueprintGenerator(
            config_util.ConfigSanitizer(True, False, False, True)
        ).generate(user_config, argparse.Namespace())
        dataset, internal_validation = config_util.generate_dataset_group_by_blueprint(
            blueprint.dataset_group
        )
        if internal_validation is not None:
            raise ValueError("Trainer attempted a second, image-level validation split")
        actual = {
            str(Path(info.absolute_path).resolve()): info for info in dataset.image_data.values()
        }
        if actual.keys() != expected.keys():
            raise ValueError(
                f"{split}: trainer discovered {len(actual)} of {len(expected)} exported images; "
                f"missing={sorted(expected.keys() - actual.keys())}"
            )
        settings = tomllib.loads((export / f"{split}.toml").read_text(encoding="utf-8"))
        repeats = settings["datasets"][0]["subsets"][0]["num_repeats"]
        buckets = {}
        for path, info in actual.items():
            if info.caption != expected[path]["caption"] or info.num_repeats != repeats:
                raise ValueError(f"Trainer caption/repeat mismatch: {path}")
            if min(info.bucket_reso) < 1:
                raise ValueError(f"Image is too small for trainer bucket steps: {path}")
            # Exercise upstream decoding, bucket resize/crop, and tensor conversion.
            pixels = load_image(path)
            pixels, _, _ = trim_and_resize_if_required(
                False, pixels, info.bucket_reso, info.resized_size
            )
            tensor = IMAGE_TRANSFORMS(pixels)
            if tensor.shape != (3, info.bucket_reso[1], info.bucket_reso[0]):
                raise ValueError(f"Trainer tensor geometry mismatch: {path}")
            if not torch.isfinite(tensor).all():
                raise ValueError(f"Non-finite trainer pixels: {path}")
            key = "x".join(str(size) for size in info.bucket_reso)
            buckets[key] = buckets.get(key, 0) + info.num_repeats
        if dataset.num_train_images != len(expected) * repeats:
            raise ValueError(f"Trainer repeat count mismatch in {split}")
        splits[split] = {
            "images": len(actual),
            "images_with_repeats": dataset.num_train_images,
            "batches": len(dataset),
            "buckets": buckets,
        }
    return {
        "qualified": True,
        "splits": splits,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tokenization_executed": False,
        "packages": {
            dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()
        },
    }


if __name__ == "__main__":
    if sys.argv[1] == "--runtime":
        verify_runtime(Path(sys.argv[2]))
        sys.exit(0)
    trainer_path, export_path, result_path, requirements_path = map(Path, sys.argv[1:])
    try:
        result = inspect_dataset(trainer_path, export_path, requirements_path)
    except Exception as exc:
        result_path.write_text(
            json.dumps({"qualified": False, "error": str(exc)}, indent=2), encoding="utf-8"
        )
        traceback.print_exc()
        sys.exit(1)
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
