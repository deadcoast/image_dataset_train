"""Discover and dispatch registered repairs under the caller's source lock."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

from image_dataset_train import terror
from image_dataset_train.diagnostics import EventLog


@dataclass
class RepairResult:
    actions: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reports: list[Path] = field(default_factory=list)
    log: Path | None = None
    metrics: dict[str, int] = field(default_factory=dict)
    projections: dict[str, dict] = field(default_factory=dict)
    fix_code: str = ""
    error_codes: tuple[str, ...] = ()
    description: str = ""


@dataclass
class RepairBatch:
    runs: list[RepairResult] = field(default_factory=list)

    @property
    def actions(self) -> list[dict]:
        return [dict(a, fix_code=r.fix_code) for r in self.runs for a in r.actions]

    @property
    def errors(self) -> list[str]:
        return [error for run in self.runs for error in run.errors]

    @property
    def reports(self) -> list[Path]:
        return [p for run in self.runs for p in run.reports]

    @property
    def log(self) -> Path | None:
        return next((r.log for r in reversed(self.runs) if r.log), None)

    @property
    def projections(self) -> dict[str, dict]:
        return {
            path: dict(change, fix_code=run.fix_code, error_codes=run.error_codes)
            for run in self.runs
            for path, change in run.projections.items()
        }

    def records(self) -> list[dict]:
        return [
            {
                "fix_code": r.fix_code,
                "error_codes": r.error_codes,
                "metrics": r.metrics,
                "reports": list(map(str, r.reports)),
                "errors": r.errors,
            }
            for r in self.runs
        ]


def _callable(reference):
    if callable(reference):
        return reference
    module, name = reference.split(":", 1)
    return getattr(import_module(module), name)


def pending_fixes(source: Path, home: Path) -> tuple[str, ...]:
    return tuple(
        rule.code
        for rule in terror.REGISTRY.select(True)
        if rule.pending and _callable(rule.pending)(source, home)
    )


def dispatch(source: Path, home: Path, selection, *, dryrun: bool, progress) -> RepairBatch:
    selected = terror.REGISTRY.select(selection)
    batch = RepairBatch()
    log = EventLog(home, enabled=not dryrun)
    for rule in selected:
        codes = terror.REGISTRY.error_codes(rule.number)
        try:
            if not _callable(rule.detect)(source, home):
                continue
            progress(f"[{rule.code}] {rule.description}")
            run = _callable(rule.apply)(source, home, dryrun=dryrun, progress=progress)
            if not isinstance(run, RepairResult):
                raise TypeError(f"{rule.code} handler must return RepairResult.")
        except Exception as exc:
            run = RepairResult(errors=[f"[{rule.code}] {exc}"])
            run.log = log.exception(exc, fix_code=rule.code, error_codes=codes, source=source)
        run.fix_code, run.error_codes, run.description = rule.code, codes, rule.description
        batch.runs.append(run)
        log.event(
            "repair_dispatch",
            fix_code=rule.code,
            error_codes=codes,
            source=source,
            dryrun=dryrun,
            metrics=run.metrics,
            errors=run.errors,
        )
        if run.errors:
            break
    return batch
