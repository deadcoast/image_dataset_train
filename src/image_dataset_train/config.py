"""Small, strict configuration for implemented dataset CLI stages."""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from image_dataset_train.annotations import annotation_name


def _probability(value: object, name: str) -> None:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")


@dataclass(frozen=True)
class SubsetRule:
    name: str
    all_tags: list[str] = field(default_factory=list)
    any_tags: list[str] = field(default_factory=list)
    none_tags: list[str] = field(default_factory=list)
    expect_tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", annotation_name(self.name))
        for name in ("all_tags", "any_tags", "none_tags", "expect_tags"):
            values = getattr(self, name)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"subset_rules.{name} must be an array of raw tag names")
        if not self.all_tags and not self.any_tags:
            raise ValueError("Subset rules require all_tags or any_tags")
        if set(self.all_tags) & set(self.none_tags):
            raise ValueError("A subset rule cannot require and forbid the same tag")


def _caption_phrase(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or any(char in value for char in (",", "\n", "\r", "\0")):
        raise ValueError(f"{name} must be one caption phrase without commas or line breaks")
    value = " ".join(value.split())
    if not empty and not value:
        raise ValueError(f"{name} cannot be empty")
    return value


@dataclass(frozen=True)
class CaptionConfig:
    general_threshold: float | None = None
    character_threshold: float = 0.85
    keep_characters: bool = False
    uncertainty_margin: float = 0.05
    drop_tags: list[str] = field(default_factory=list)
    tag_thresholds: dict[str, float] = field(default_factory=dict)
    trigger: str = ""
    force_tags: list[str] = field(default_factory=list)
    subset_rules: list[SubsetRule] = field(default_factory=list)

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
        object.__setattr__(self, "trigger", _caption_phrase(self.trigger, "trigger", empty=True))
        if not isinstance(self.force_tags, list):
            raise ValueError("force_tags must be an array of caption phrases")
        object.__setattr__(
            self, "force_tags", [_caption_phrase(value, "force_tags") for value in self.force_tags]
        )
        if not isinstance(self.subset_rules, list):
            raise ValueError("subset_rules must be an array of tables")
        rules = []
        for rule in self.subset_rules:
            if isinstance(rule, dict):
                _table(rule, "subset_rules", set(SubsetRule.__dataclass_fields__))
                if "name" not in rule:
                    raise ValueError("Each subset rule needs a name")
                rule = SubsetRule(**rule)
            if not isinstance(rule, SubsetRule):
                raise ValueError("subset_rules must contain rule tables")
            rules.append(rule)
        if len({rule.name for rule in rules}) != len(rules):
            raise ValueError("Subset rule names must be unique")
        object.__setattr__(self, "subset_rules", rules)


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
        if not isinstance(self.device, str) or self.device not in {"cpu", "cuda", "auto"}:
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
class ExportConfig:
    validation_ratio: float = 0.05
    seed: int = 20261011
    resolution: int = 1024
    repeats: int = 1
    split_strategy: str = "semantic"

    def __post_init__(self) -> None:
        _probability(self.validation_ratio, "export.validation_ratio")
        if self.validation_ratio == 1:
            raise ValueError("export.validation_ratio must be less than 1")
        if type(self.seed) is not int:
            raise ValueError("export.seed must be an integer")
        if type(self.resolution) is not int or self.resolution < 64 or self.resolution % 64:
            raise ValueError("export.resolution must be a positive multiple of 64")
        if type(self.repeats) is not int or self.repeats < 1:
            raise ValueError("export.repeats must be a positive integer")
        if self.split_strategy not in ("semantic", "size"):
            raise ValueError("export.split_strategy must be semantic or size")


@dataclass(frozen=True)
class Config:
    source: Path
    runs: Path
    validation: ValidationConfig
    models: Path = Path("data/models")
    scores: Path = Path("data/derived/scores")
    tagging: TaggingConfig = field(default_factory=TaggingConfig)
    captions: CaptionConfig = field(default_factory=CaptionConfig)
    reviews: Path = Path("data/reviews")
    exports: Path = Path("data/exports")
    export: ExportConfig = field(default_factory=ExportConfig)


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
    _table(raw, "root", {"schema_version", "paths", "validation", "tagging", "captions", "export"})
    version = raw.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("schema_version must be 1")
    paths = _table(
        raw.get("paths", {}), "paths", {"source", "runs", "models", "scores", "reviews", "exports"}
    )
    validation = _table(
        raw.get("validation", {}), "validation", set(ValidationConfig.__dataclass_fields__)
    )
    resolved = {}
    for name, default in (
        ("source", "data/00_inbox"),
        ("runs", "data/runs"),
        ("models", "data/models"),
        ("scores", "data/derived/scores"),
        ("reviews", "data/reviews"),
        ("exports", "data/exports"),
    ):
        value = paths.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"paths.{name} must be a nonempty path string")
        resolved[name] = (path.resolve().parent / value).resolve()
    tagging = _table(raw.get("tagging", {}), "tagging", set(TaggingConfig.__dataclass_fields__))
    captions = _table(raw.get("captions", {}), "captions", set(CaptionConfig.__dataclass_fields__))
    export = _table(raw.get("export", {}), "export", set(ExportConfig.__dataclass_fields__))
    return Config(
        **resolved,
        validation=ValidationConfig(**validation),
        tagging=TaggingConfig(**tagging),
        captions=CaptionConfig(**captions),
        export=ExportConfig(**export),
    )
