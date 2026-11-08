# Implementation status

## Current status — 2026-11-07

- The installed `trainime` directory workflow and technical `dataset` pipeline are
  separate: the former may write/remove source captions; the latter writes
  inventory, score, and draft artifacts under configured run paths.
- M1 inventory, WD tagging execution, and Trainime recovery workflows are
  implemented. Historical package and installed-command evidence is recorded in
  the milestone sections below; it was not rerun for this status update.
- M2 has an initial read-only pHash proposal command. It publishes a hashed list
  of image fingerprints and unreviewed candidate pairs. Automated regression
  coverage and collection-specific threshold qualification remain outstanding.
- Durable review decisions, related-image groups, group-aware splits, reviewed
  exports, and pinned trainer import are not implemented. No user collection has
  been scanned or accepted as training-ready.

The next steps are similarity-stage coverage and pilot calibration, durable review
records, then group-aware split/export and a pinned trainer import check. Model
accuracy, physical CUDA, scale, and human acceptance stay separately qualified.

## Trainime 0.5.1: numeric repair registry and dispatch

- [x] Replace the 0.5.0 single-fix CLI/doctor branches with registered numeric
  error and fix definitions, explicit one-to-many mappings, and shared dispatch.
- [x] Bare `--fix` discovers applicable registered handlers; numeric IDs, padded
  IDs, error/fix codes, comma selections, and repeated flags select handlers.
  Selection validates before mutation, deduplicates, and sorts numerically.
- [x] Menu offers, command echoes, diagnostics, operation receipts, result
  metrics, dry-run projections, and pending-repair checks use the registry.
- [x] Failures stop subsequent mutations; interrupted unselected fixes identify
  their resume codes. Collision repair retains its existing recovery behavior.

Verification: **204 passed, 2 skipped**; `.cache/registry-full.xml` and
`.cache/pytest-registry-full`. Ruff lint and formatting pass. The Windows skips
are unchanged from 0.5.0 below. Additional test-only handlers prove multiple
dispatch, numeric ordering, IDs beyond three digits, differing error/fix IDs,
one-to-many mappings, conditional menu choices, and failure isolation. `tf001`
is the only production directory repair currently implemented.

Installed 0.5.1 through `install.cmd`; every installed source module matches the
checkout. Installed-command checks cover selector aliases/repetition, bare flags
before subcommands/paths, invalid codes, read-only previews, actual SwinV2 CPU
tagging after collision repair, byte/caption preservation, repeat runs, and doctor.
The installed dispatcher also ran two additional test-only registered handlers
without changing CLI code. No personal dataset or personal error logs were used.
Evidence: `.cache/registry-installed/027500e52b65451fa59ee2dd3e9553a3/verification.json`
and adjacent command transcripts. Installer receipt:
`install-20261012T011634959Z-111187f7.log` under the application log directory.

## Trainime 0.5.0: executable te001 / tf001 repair

- [x] Stable TERROR/TERROR_FIX definitions, structured error/fix codes, and a
  runnable command in collision output.
- [x] One general recursive repair: deterministic unique stems, case-folded
  reservations, occupied-name counters, long-name handling, unchanged image bytes,
  verified recovery for ambiguous captions, and preservation of unrelated pairs.
- [x] `tag/remove --fix [tf001]`, fix-only command, targeted doctor repair, and
  one conditional menu question when te001 occurs. No normal-path menu changes.
- [x] Read-only dry-run plans and apply commands that retain the fix flag.
- [x] Shared operation lock, saved intent, exclusive renames, partial-backup
  retention, cancellation/restart recovery, and repeat-run idempotence.

Verification: **167 passed, 2 skipped**, `.cache/pytest-tf001-qualified`; Ruff lint
and formatting pass. The skips are the existing Windows symlink privilege check
and case-only caption duplicates, which standard Windows directories cannot hold.
Real junction escape checks pass. Tests use arbitrary stems, Unicode, nested groups,
existing destinations, actual native ONNX test inference, incomplete backups,
interrupted rename/journal publication, concurrent destination creation, retries,
and menu/CLI/doctor paths. No personal image directory or personal error log was
examined to develop this rule.

Final verification exposed transient Windows access-denied errors while publishing
tag reports (retained in `.cache/tf001-final-recheck.xml`). Report publication now
retries Windows sharing/access locks at most five times with bounded backoff and
logs each retry; persistent failures retain the completed staging directory.
Transient and persistent failure tests pass. Final suite receipt:
`.cache/tf001-qualified.xml`.

Installed 0.5.0 through `install.cmd`. The installed wheel matches all source
modules. Its real SwinV2 CPU run repaired two colliding generated images, retained
their exact bytes, preserved the ambiguous caption, and generated independent
captions. Repeat repair changed no names or captions. Installed dry runs wrote
nothing, and targeted doctor/fix-only commands passed on another arbitrary stem.
Final installed evidence: `.cache/tf001-installed/f67e1b0947d64f18b6579a5f4bc92809/verification.json`
and adjacent command transcripts, with isolated application data and repair journals.

## Trainime 0.4.1: terminal output polish

- [x] Dry runs explicitly report images that **can** be serviced for tags (or
  captions that can be removed), with green eligibility wording and counts.
- [x] Scanned/eligible/kept/skipped/error totals, explicit no-change preview
  wording, and a copyable command to apply the action.
- [x] Consistent cyan navigation, green success, amber attention, red failure;
  aligned Home descriptions, visible active path, clearer Settings and Help.
- [x] One progress line with elapsed time and actual caption completion counts;
  compact narrow-terminal layout, plain redirected output, and `NO_COLOR` support.
- [x] Readable image-decoder failures with a re-export instruction instead of a
  generic runtime-repair suggestion. Existing detailed operation data is retained.
- [x] Installed 0.4.1 through the supported installer. The normal user command
  resolves to `C:\Users\ryanf\.local\bin\trainime.exe`.

Verification on 2026-10-11: **66 existing workflow/diagnostics checks passed**;
Ruff lint/format and dependency-lock checks passed. Inspected 40/96-column color
renders and exercised the installed Home/Settings prompts in a Windows terminal.
Installed tag/remove previews on generated fixtures reported the correct eligible,
kept, and skipped counts, preserved every input byte, created no app-data files,
and emitted plain redirected text. Evidence: `.cache/cli-polish/`.
No personal image directory was processed for this presentation change.

## Trainime 0.4.0: installer, logs, and repair

- [x] `install.cmd` / `install.ps1` is the supported installation entry point.
  It locates its own checkout, obtains verified uv and Python when necessary,
  stages and probes a native inference runtime, installs the command, registers
  user PATH, and retains checksummed repair artifacts and an installation receipt.
- [x] Existing and missing/stale dependency locks, paths with spaces, inherited
  PowerShell 7 module paths in PowerShell 5.1, repeated installs, and offline repair.
  Stale locks are refreshed in an isolated copy; the source lock is preserved.
- [x] Structured operational logs, separate errors with full tracebacks, stable
  diagnosis codes, per-process rotation, fallback logging, common credential
  redaction, installer stdout/stderr/exit logs, and `trainime logs`.
- [x] Dependency-free startup/doctor, child-process native inference checks,
  `trainime doctor --fix`, settings recovery, damaged-model preservation/refetch,
  damaged-score preservation/recomputation, and data-specific recovery instructions.
- [x] A running Windows doctor repairs dependencies/application files in place
  without replacing its locked launcher. Its child process verifies the repair.
- [x] Normal menu choices are unchanged. Tag/remove dry runs still create no files.

Verification on 2026-10-11:

- **138 passed, 1 skipped** with `--basetemp .cache/pytest-installer-final`;
  existing Windows symlink privilege skip, real junction check passed. Ruff lint,
  formatting, and diff whitespace checks passed.
- Actual isolated installs and repeat installs with app/tool/bin paths containing
  spaces passed. The `.cmd` wrapper ran from outside the repository. Offline repair
  from the retained package passed.
- Official pinned uv bootstrap was downloaded, SHA256-verified, and executed.
  A separate empty Python-management directory automatically received CPython
  3.12.12, then supplied a successful full installation and native inference check.
- A stale-lock source copy installed successfully while preserving its original
  lock bytes. Evidence: `.cache/installer-smoke/13f2128011514c80af22e10f728a16d0/`
  (`stale-install.verification.json`, adjacent transcripts, and application logs).
- Deliberately removing NumPy from an isolated installed tool produced a readable
  doctor failure; `doctor --fix --runtime-only --json` restored it and returned
  `status=fixed`, with imports and native ONNX inference passing.
- The supported installer installed 0.4.0 into the user's command environment;
  `trainime doctor --json` passed runtime, storage, settings, command, model, and
  score-cache checks. PATH repair prioritizes the selected command over older
  user-PATH entries, preserves other entries, and checks command resolution again.
- Installed 0.4.0, real SwinV2 CPU: tagging, repeat tagging, both dry runs,
  removal with verified backups, cached retagging, and the four-choice menu passed.
  Image hashes, unrelated text, and manual captions until explicit removal were
  preserved. Evidence: `.cache/trainime-smoke/499497f2554e4395811f51c18ae7e708/verification.json`.
  Only generated test images were used.
- Initial failures are retained in that evidence directory: raw constraint paths
  containing spaces, PowerShell 5.1 receipt replacement, inherited module lookup,
  and attempting to replace a running Windows launcher. Regression checks and
  corrected install/repair runs cover each fix.

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for the recovery contract.
Windows x64 is qualified here; ARM64 native installation and other operating
systems' installer flows are not. Anime accuracy and reviewed dataset acceptance
remain separate, unfinished work.

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

1. Add and qualify tests for the read-only M2 pHash proposal stage on generated positive and negative pairs.
2. Review representative anime pairs and calibrate proposal thresholds; record false-match and missed-match behavior.
3. Add durable related-image groups and per-image review decisions without automatic source moves.
4. Add group-aware deterministic splits, verified immutable image/caption exports, and a Kohya adapter.
5. Verify export with a pinned trainer import, then qualify pilot and full-collection QA.

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
