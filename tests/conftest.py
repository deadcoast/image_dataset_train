"""Tests never write operational logs into the real user's application directory."""

import pytest


@pytest.fixture(autouse=True)
def isolated_application_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAINIME_HOME", str(tmp_path / "test-app-home"))
