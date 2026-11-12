"""Recovery navigation remains usable when the normal application cannot import."""

from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("entry", ["launcher", "module"])
def test_navigation_without_ui_native_or_lock_dependencies(tmp_path, entry):
    source = Path(__file__).resolve().parents[1] / "src"
    home = tmp_path / "missing application data"
    script = r"""
import importlib.abc, json, runpy, sys
class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = {'PIL','numpy','onnxruntime','rich','prompt_toolkit','filelock','huggingface_hub'}
        if fullname.split('.')[0] in blocked:
            raise ImportError('deliberately unavailable: ' + fullname)
sys.meta_path.insert(0, DenyRuntime())
args = ['recovery', '--home', sys.argv[1], '--json']
if sys.argv[2] == 'launcher':
    from image_dataset_train.bootstrap import dataset_main
    raise SystemExit(dataset_main(args))
sys.argv = ['dataset', *args]
runpy.run_module('image_dataset_train', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(home), entry],
        env={**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["records"] == [] and data["errors"] == []
    assert not home.exists()


def test_doctor_history_does_not_reclassify_past_failures_as_current_damage(tmp_path, monkeypatch):
    from image_dataset_train import doctor, recovery_catalog

    monkeypatch.setattr(
        recovery_catalog,
        "list_recovery",
        lambda home: {"records": [{"status": "failed"}, {"status": "completed"}], "errors": []},
    )
    result = doctor._recovery_check(tmp_path)
    assert result.status == "ok" and "2 saved receipts" in result.detail
    assert all(value in result.fix for value in ("dataset", "recovery", "--home", str(tmp_path)))
    assert not list(tmp_path.iterdir())


def test_doctor_unreadable_history_is_separate_warning(tmp_path, monkeypatch):
    from image_dataset_train import doctor, recovery_catalog

    monkeypatch.setattr(
        recovery_catalog,
        "list_recovery",
        lambda home: {"records": [], "errors": [{"error": "invalid receipt"}]},
    )
    result = doctor._recovery_check(tmp_path)
    assert result.status == "warning" and "1 unreadable" in result.detail
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("module", ["recovery_catalog", "recovery_catalog_cli"])
def test_broken_navigation_modules_do_not_block_doctor(tmp_path, monkeypatch, module):
    from image_dataset_train import doctor

    original = builtins.__import__

    def reject(name, *args, **kwargs):
        if name == "image_dataset_train." + module:
            raise ImportError("damaged recovery module")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject)
    result = doctor._recovery_check(tmp_path)
    assert result.status == "warning" and "damaged recovery module" in result.detail
    assert "--home" in result.fix and str(tmp_path) in result.fix
    assert not list(tmp_path.iterdir())


def test_broken_navigation_entrypoint_failure_remains_read_only(tmp_path, monkeypatch, capsys):
    from image_dataset_train.bootstrap import dataset_main

    original = builtins.__import__

    def reject(name, *args, **kwargs):
        if name == "image_dataset_train.recovery_catalog_cli":
            raise ImportError("damaged browser module")
        return original(name, *args, **kwargs)

    home = tmp_path / "missing-home"
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    monkeypatch.setattr(builtins, "__import__", reject)
    assert dataset_main(["recovery", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["type"] == "ImportError"
    assert not home.exists()
