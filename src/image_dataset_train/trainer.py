"""Pinned, isolated sd-scripts dataset import and portable qualification receipts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from image_dataset_train.config import Config
from image_dataset_train.diagnostics import atomic_json, publish_directory
from image_dataset_train.exporting import verify_export
from image_dataset_train.inventory import file_sha256

TRAINER_REPOSITORY = "https://github.com/kohya-ss/sd-scripts.git"
TRAINER_REVISION = "cb70b96858477e716a2096292ab8aab433277f38"
TRAINER_RELEASE = "v0.12.3"


def _run(command: list[str], **kwargs) -> str:
    result = subprocess.run(command, check=False, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed:\n{result.stderr or result.stdout}")
    return result.stdout.strip()


def _python(runtime: Path) -> Path:
    return runtime / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _check_revision(source: Path) -> None:
    revision = _run(["git", "-C", str(source), "rev-parse", "HEAD"])
    changes = _run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=normal"])
    if revision != TRAINER_REVISION or changes:
        raise ValueError(f"Trainer must be an unchanged checkout of {TRAINER_REVISION}")


def setup_trainer(runtime: Path) -> dict:
    """Install only the CPU import runtime, separate from tagging and trainer model weights."""
    runtime = runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Install uv, then run dataset trainer-setup again.")
    source = runtime / "sd-scripts"
    if not source.exists():
        _run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                TRAINER_RELEASE,
                "--single-branch",
                TRAINER_REPOSITORY,
                str(source),
            ]
        )
    _check_revision(source)
    if not _python(runtime).exists():
        _run(
            [
                uv,
                "venv",
                str(runtime / "venv"),
                "--python",
                "3.12",
                "--cache-dir",
                str(runtime / "uv-cache"),
            ]
        )
    lock = Path(__file__).with_name("trainer-requirements.txt")
    runtime_check = subprocess.run(
        [
            str(_python(runtime)),
            "-I",
            str(Path(__file__).with_name("trainer_worker.py")),
            "--runtime",
            str(lock),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if runtime_check.returncode:
        _run(
            [
                uv,
                "pip",
                "sync",
                str(lock),
                "--python",
                str(_python(runtime)),
                "--index",
                "https://download.pytorch.org/whl/cpu",
                "--index-strategy",
                "unsafe-best-match",
                "--cache-dir",
                str(runtime / "uv-cache"),
                "--quiet",
            ]
        )
    result = {
        "repository": TRAINER_REPOSITORY,
        "revision": TRAINER_REVISION,
        "release": TRAINER_RELEASE,
        "requirements_sha256": file_sha256(lock),
        "python": str(_python(runtime)),
    }
    atomic_json(runtime / "runtime.json", result)
    return result


def check_trainer(config: Config, export: Path, runtime: Path) -> tuple[Path, dict]:
    export, runtime = export.resolve(strict=True), runtime.resolve(strict=True)
    verify_export(export)
    export_hash = file_sha256(export / "run.json")
    manifest_hash = file_sha256(export / "manifest.jsonl")
    _check_revision(runtime / "sd-scripts")
    python = _python(runtime)
    if not python.is_file():
        raise ValueError("Trainer runtime is missing. Run dataset trainer-setup first.")
    root = config.runs.resolve()
    if root.is_relative_to(export) or export.is_relative_to(root):
        raise ValueError("Trainer reports and export must be separate trees")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-trainer-", dir=root))
    report_path = staging / "result.json"
    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HOME": str(runtime / "huggingface"),
    }
    command = [
        str(python),
        "-I",
        "-B",
        "-X",
        "utf8",
        str(Path(__file__).with_name("trainer_worker.py")),
        str(runtime / "sd-scripts"),
        str(export),
        str(report_path),
        str(Path(__file__).with_name("trainer-requirements.txt")),
    ]
    with (staging / "loader.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command, cwd=export, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    result = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {
            "qualified": False,
            "error": f"Trainer worker exited {completed.returncode}; see loader.log.",
        }
    )
    if completed.returncode:
        result["qualified"] = False
    # Never modify an export to append evidence; bind a separate receipt to its exact bytes.
    verify_export(export)
    if (file_sha256(export / "run.json"), file_sha256(export / "manifest.jsonl")) != (
        export_hash,
        manifest_hash,
    ):
        raise ValueError("Export changed during trainer import; no receipt was published")
    result.update(
        {
            "repository": TRAINER_REPOSITORY,
            "revision": TRAINER_REVISION,
            "release": TRAINER_RELEASE,
            "export": str(export),
            "export_run_sha256": export_hash,
            "export_manifest_sha256": manifest_hash,
            "requirements_sha256": file_sha256(
                Path(__file__).with_name("trainer-requirements.txt")
            ),
            "scope": "cpu-dataset-import",
            "training_step_executed": False,
        }
    )
    atomic_json(report_path, result)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-trainer-" + uuid4().hex[:8]
    atomic_json(
        staging / "run.json",
        {
            "schema_version": 1,
            "stage": "trainer-check",
            "run_id": run_id,
            "status": "completed" if result["qualified"] else "failed",
            "completed_at": datetime.now(UTC).isoformat(),
            "files": {name: file_sha256(staging / name) for name in ("result.json", "loader.log")},
        },
    )
    final = root / run_id
    publish_directory(staging, final)
    return final, result
