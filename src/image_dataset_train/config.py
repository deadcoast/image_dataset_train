"""Small, strict configuration for the implemented intake stage."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


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
    _table(raw, "root", {"schema_version", "paths", "validation"})
    version = raw.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("schema_version must be 1")
    paths = _table(raw.get("paths", {}), "paths", {"source", "runs"})
    validation = _table(
        raw.get("validation", {}), "validation", set(ValidationConfig.__dataclass_fields__)
    )
    resolved = {}
    for name, default in (("source", "data/00_inbox"), ("runs", "data/runs")):
        value = paths.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"paths.{name} must be a nonempty path string")
        resolved[name] = (path.resolve().parent / value).resolve()
    return Config(**resolved, validation=ValidationConfig(**validation))
