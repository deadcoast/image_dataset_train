# Implementation status

## Trainime 0.3.0: implemented and installed

- [x] Exact four-choice Home menu; path and `--dryrun` are the only action prompts.
- [x] Session/default path precedence, atomic saved settings, quoted/Unicode paths,
  completion, concise Help, and cancellation back to Home.
- [x] One tagging action: inspection, automatic pinned model setup, inference for
  missing captions only, cache reuse, and exclusive source-side `.txt` publication.
- [x] Remove paired captions with SHA256-verified recovery copies and a durable
  per-file journal; preserve images, unrelated text, and ambiguous associations.
- [x] Read-only/offline previews, OS job locks, source rechecks, partial-operation
  reports, direct commands, bounded summaries, and copyable command/path output.
- [x] Installed CPU wheel into the existing uv tool environment. `trainime` resolves
  to `C:\Users\ryanf\.local\bin\trainime.exe` and runs outside the checkout.
- [x] Reused the already verified pinned SwinV2 artifacts in the application cache;
  the installed command is ready to tag without another model download.

Verification on 2026-10-11:

- **96 passed, 1 skipped** with `--basetemp .cache/pytest-trainime-release`.
  The existing skip is Windows symlink privilege; the real junction test passes.
- Ruff lint, formatting, wheel/sdist build, and diff whitespace checks pass.
- Live Windows terminal: exact Home menu, Settings, Ctrl+C, quoted path input,
  `--dryrun` prompt, and reuse of the session path without another path prompt.
- Installed wheel, real SwinV2 CPU: two unique generated images inferred; an
  existing manual caption preserved; all three paired captions backed up and
  removed; retagging reused two score vectors plus one exact duplicate with zero
  new inference. All image hashes and unrelated text were preserved.
- Evidence: `.cache/trainime-smoke/00eede1dc2a84d1b8ded683f8337e934/verification.json`
  and adjacent command transcripts. The imported module is the installed wheel's
  `site-packages`, not editable source. No user image collection was used.
- The initial installed smoke caught access-time changes being mistaken for
  caption edits. That run stopped removal without deleting captions; the check
  now compares size, modification time, inode, and mode, with a regression test
  that deliberately updates access times. Initial evidence is retained under
  `.cache/trainime-smoke/cc21080cd061446d853fe53e293fce10/`.

Workflow design and research links: [docs/TRAINIME.md](docs/TRAINIME.md).
Anime accuracy, physical CUDA, large-collection performance, reviewed export,
and trainer acceptance remain pending.

## Current boundary

M1, WD tagging, and the `trainime` interactive directory workflow are implemented.
The pinned SwinV2 model has
been downloaded and CPU inference exercised on generated fixtures. No user dataset
has been scanned or tagged, and no reviewed training export exists.
`PLAN.md` is the working design. `TAGGING-METHODS.md` contains the historical notes
originally named `OVERVIEW.md`.

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
- Original notes remain in `OVERVIEW.md`, with navigation to the active documents.
  Concurrent repository edits and formatting changes are retained; byte-for-byte
  identity with the initial note is not claimed.

These checks establish intake behavior and packaging. They do not establish
anime tagging accuracy, large-collection performance, or training readiness.

## Next implementation

1. Tagging quality: compare model profiles and tune thresholds on a reviewed anime pilot.
2. M2: pHash pair proposals and reviewable related-image groups; no automatic moves.
3. M4: durable per-image review overrides; initial deterministic caption rules already work.
4. M5: group-aware splitting, verified image/caption exports, Kohya adapter.
5. M6: pilot qualification, then full collection run and QA.

## Pending evidence

- Real images: readability, size distribution, caption collisions, duplicate rate.
- Similarity: calibrated false-match/missed-match behavior on anime artwork.
- Tagging: throughput and accuracy on this collection; alternate models and physical GPU inference.
- Export: pinned trainer import and repeat/bucket behavior.
- Dataset acceptance: image/caption review; automated tests cannot establish it.

## M3 and initial caption rules: implemented

- [x] Research WD SwinV2/ViT-Large/EVA02-Large and Camie v2 using primary sources.
- [x] Pinned WD downloads with model/label checksums and a separate offline inference stage.
- [x] Reference input preparation, EXIF correction, category indexing, tensor/output validation.
- [x] CPU/auto/explicit-CUDA selection; actual registered providers recorded.
- [x] Batch inference, fixed-batch-one handling, atomic raw-score cache, interrupted-run recovery.
- [x] Recheck source hashes, preserve originals/manual captions, retain every score/category.
- [x] Model/per-tag thresholds, opt-in characters, explicit exclusions, ambiguity/conflict flags.
- [x] Self-contained runs and score-only recaptioning into a new run.
- [x] Real pinned SwinV2 CPU smoke and four exact publisher-preprocessing tensor comparisons.
- [x] Final full-suite, lint, format, build, and installed-package checks for 0.2.0.
- [ ] Actual anime accuracy, alternate WD weights, physical GPU execution, collection-scale QA.

Research, commands, evidence scope, and pending comparisons are in
[docs/TAGGING.md](docs/TAGGING.md). Camie is researched but not implemented.

## Tagging verification: 2026-10-11

- Full suite: **66 passed, 1 skipped** using the CPU extra. The existing skip is
  Windows symlink creation privilege (`WinError 1314`); junction coverage passes.
- Ruff lint and formatting: passed. Source distribution and wheel: built.
- Isolated 0.2.0 CPU wheel: `scan`, `tag`, and `recaption` commands passed using
  actual pinned SwinV2 inference, with source-image/manual-caption preservation.
- Real-model smoke: two unique generated images inferred, a duplicate reused,
  rerun served from cache, and recaption performed zero inference.
- Reference input parity: **4/4 exact tensor matches** against the inspected
  publisher method at `fbd35b187d6e8cb8a00c529d52999f82d6b5193b`.
- This establishes execution and artifact handling, not accuracy on anime images
  or acceptance of a training dataset.
