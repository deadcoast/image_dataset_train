# Implementation status

## Current boundary

M1 is implemented and verified against generated fixtures. No real dataset has been scanned.
No model has been downloaded, no inference has run, and no training export exists.
`PLAN.md` is the working design. `OVERVIEW.md` remains historical source material.

## M1: inventory and validation

- [x] Package layout, Python 3.12, `uv`, CLI, strict TOML configuration.
- [x] Read-only inventory with complete SHA256 hashes and existing sidecar records.
- [x] Decode checks, frame checks, EXIF dimensions, alpha/mode/ICC and size flags.
- [x] Exact duplicate references and caption-conflict detection.
- [x] New report directory per run, deterministic manifest, atomic publication.
- [x] Preservation/failure/rerun tests, lint, format, package build, installed CLI smoke test.

## Verification: 2026-10-11

Windows, Python 3.12.10, Pillow 12.3.0, pytest 9.1.1, Ruff 0.17.0.

- `ruff check .`: passed. Initial line-length findings were corrected with formatting.
- `ruff format --check .`: passed. Historical `OVERVIEW.md` is excluded from formatting.
- `pytest -q -rs --basetemp .cache/pytest-final`: **31 passed, 1 skipped**.
  The symlink test is skipped because Windows denies symlink creation with
  `WinError 1314`. The separate real Windows junction test passes.
- `uv build`: wheel and source distribution built successfully.
- Isolated wheel installation: console entry point and module CLI both executed.
  A five-file generated fixture produced the expected report, and every input
  file's SHA256 was unchanged. Import location was the wheel environment's
  `site-packages`, not the editable source tree.
- Original `OVERVIEW.md` bytes are preserved after removing the added navigation banner.

These checks establish intake behavior and packaging. They do not establish
anime tagging accuracy, large-collection performance, or training readiness.

## Next implementation

1. M2: pHash pair proposals and reviewable related-image groups; no automatic moves.
2. M3: pinned WD model fetch, correct preprocessing/category handling, raw score cache.
3. M4: deterministic normalization and durable per-image review overrides.
4. M5: group-aware splitting, verified image/caption exports, Kohya adapter.
5. M6: pilot qualification, then full collection run and QA.

## Pending evidence

- Real images: readability, size distribution, caption collisions, duplicate rate.
- Similarity: calibrated false-match/missed-match behavior on anime artwork.
- Tagging: reference parity, throughput, and accuracy on this collection.
- Export: pinned trainer import and repeat/bucket behavior.
- Dataset acceptance: image/caption review; automated tests cannot establish it.
