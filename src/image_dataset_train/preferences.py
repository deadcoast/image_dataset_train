"""Trainime's persistent preference and process-local session selection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from image_dataset_train.diagnostics import app_home as app_home
from image_dataset_train.diagnostics import atomic_json


def image_directory(value: str) -> Path:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if not text:
        raise ValueError("Enter an image directory.")
    path = Path(os.path.expandvars(text)).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")
    return path


@dataclass
class Preferences:
    home: Path
    default_path: Path | None = None
    session_path: Path | None = None

    @property
    def selected_path(self) -> Path | None:
        return self.session_path or self.default_path

    @property
    def settings_file(self) -> Path:
        return self.home / "settings.json"

    @classmethod
    def load(cls, home: Path) -> Preferences:
        result = cls(home)
        if not result.settings_file.exists():
            return result
        try:
            raw = json.loads(result.settings_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema_version") != 1:
                raise ValueError("unsupported settings format")
            value = raw.get("default_path")
            if value is not None and (not isinstance(value, str) or not Path(value).is_absolute()):
                raise ValueError("default_path must be an absolute path or null")
            result.default_path = Path(value) if value else None
        except (ValueError, OSError) as exc:
            raise ValueError(f"Cannot read settings at {result.settings_file}: {exc}") from exc
        return result

    def save_default(self, path: Path | None) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if self.settings_file.exists():
            try:
                self.load(self.home)
            except ValueError:
                from image_dataset_train.doctor import preserve

                preserve(self.settings_file, self.home, "settings")
        atomic_json(
            self.settings_file,
            {
                "schema_version": 1,
                "default_path": str(path) if path else None,
            },
        )
        self.default_path = path
