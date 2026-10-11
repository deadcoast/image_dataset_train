"""Small, strict configuration for the implemented intake stage."""

from __future__ import annotations

import tomllib
import math
from dataclasses import dataclass, field
from pathlib import Path


def _probability(value: object, name: str) -> None:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")


@dataclass(frozen=True)
class CaptionConfig:
    general_threshold: float | None = None
    character_threshold: float = 0.85
    keep_characters: bool = False
    uncertainty_margin: float = 0.05
    drop_tags: list[str] = field(default_factory=list)
    tag_thresholds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.general_threshold is not None:
            _probability(self.general_threshold, "general_threshold")
        _probability(self.character_threshold, "character_threshold")
        _probability(self.uncertainty_margin, "uncertainty_margin")
        if type(self.keep_characters) is not bool:
            raise ValueError("keep_characters must be boolean")
        if not isinstance(self.drop_tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in self.drop_tags
        ):
            raise ValueError("drop_tags must be an array of nonempty raw tag names")
        if not isinstance(self.tag_thresholds, dict):
            raise ValueError("tag_thresholds must be a table")
        for tag, value in self.tag_thresholds.items():
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tag_thresholds keys must be raw tag names")
            _probability(value, f"tag_thresholds.{tag}")


@dataclass(frozen=True)
class TaggingConfig:
    model: str = "swinv2-v3"
    revision: str | None = None
    device: str = "auto"
    batch_size: int = 4

    def __post_init__(self) -> None:
        # Imported here to avoid a config/inventory import cycle at module load.
        from image_dataset_train.model_bundle import bundle_path

        bundle_path(Path(), self.model, self.revision)
        if self.device not in {"cpu", "cuda", "auto"}:
            raise ValueError("tagging.device must be cpu, cuda, or auto")
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 64:
            raise ValueError("tagging.batch_size must be an integer between 1 and 64")


@dataclass(frozen=True)
class ValidationConfig:
    min_short_side: int = 768
    max_long_side: int = 4096
    max_decode_pixels: int = 50_000_000
    max_file_bytes: int = 268_435_456

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"validation.{name} must be a positive integer")
        if self.min_short_side > self.max_long_side:
            raise ValueError("min_short_side must not exceed max_long_side")


@dataclass(frozen=True)
class Config:
    source: Path
    runs: Path
    validation: ValidationConfig
    models: Path = Path("data/models")
    scores: Path = Path("data/derived/scores")
    tagging: TaggingConfig = field(default_factory=TaggingConfig)
    captions: CaptionConfig = field(default_factory=CaptionConfig)


def _table(value: object, name: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a TOML table")
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f"unknown {name} setting(s): {', '.join(sorted(unknown))}")
    return value


def load_config(path: Path) -> Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    _table(raw, "root", {"schema_version", "paths", "validation", "tagging", "captions"})
    version = raw.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("schema_version must be 1")
    paths = _table(raw.get("paths", {}), "paths", {"source", "runs", "models", "scores"})
    validation = _table(
        raw.get("validation", {}), "validation", set(ValidationConfig.__dataclass_fields__)
    )
    resolved = {}
    for name, default in (
        ("source", "data/00_inbox"), ("runs", "data/runs"),
        ("models", "data/models"), ("scores", "data/derived/scores"),
    ):
        value = paths.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"paths.{name} must be a nonempty path string")
        resolved[name] = (path.resolve().parent / value).resolve()
    tagging = _table(raw.get("tagging", {}), "tagging", set(TaggingConfig.__dataclass_fields__))
    captions = _table(raw.get("captions", {}), "captions", set(CaptionConfig.__dataclass_fields__))
    return Config(
        **resolved, validation=ValidationConfig(**validation),
        tagging=TaggingConfig(**tagging), captions=CaptionConfig(**captions),
    )
