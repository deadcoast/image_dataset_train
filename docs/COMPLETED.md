# Completed work and verification log

Extracted from the project TODO on **2026-11-09**. Original milestone dates,
versions, completed checklist items, verification results, evidence locations and
qualification limits are retained. Refer to [TODO.md](../TODO.md) for unfinished
work and [PLAN.md](PLAN.md) for the governing design and milestone order.

This is a historical completion log, not a claim that every milestone's collection
acceptance is complete. Earlier limitations describe the evidence available at that
milestone; later entries may supersede them. Generated fixtures, model execution,
trainer import and human acceptance remain distinct. Evidence paths in code spans
are relative to the repository root unless an absolute location is specified.

## Delivered status — 2026-11-09

- The installed `trainime` directory workflow and technical `dataset` pipeline are
  separate: the former may write/remove source captions; the latter writes
  inventory, score, and draft artifacts under configured run paths.
- M1 inventory, WD tagging execution, and Trainime recovery workflows are
  implemented. The current full regression run and isolated M2 wheel check are
  recorded below. Historical model and installed-Trainime evidence retains its
  original dates.
- M2 has an initial read-only pHash proposal command. It publishes a hashed list
  of image fingerprints and unreviewed candidate pairs, streaming pair records
  into a staged run instead of retaining the full pair list in memory. Generated
  fixture regression coverage passes; collection-specific threshold qualification
  remains outstanding.
- Durable pair/image decisions, manual caption overrides, and related-image group
  snapshots are implemented through `dataset review` and `dataset groups`.
  Exact-byte aliases retain their individual provenance and decisions.
- Group-aware splits, verified image/caption exports, independent export
  verification, and separate Kohya configurations are implemented.
- Pinned sd-scripts CPU dataset imports pass for generated exports, including
  mixed formats and training repeats. Each export can receive a separate receipt.
  The reviewer and `trainer-status` show export-bound receipt history, current-pin
  qualification, split counts, buckets, and loader logs.
- Reviewed labels/subsets persist through snapshots and exports; semantic
  group-aware balancing and per-category coverage reports are implemented.
- M4 configured caption phrases and subset rules are implemented with score-only
  regeneration, explicit review acceptance, and preserved rule provenance.
- Pilot QA reporting and browser/CLI navigation cover captions, annotations,
  related groups, and split coverage. Direct image corrections and recorded pilot
  judgments/conclusions are implemented. Graphical related/distinct pair review,
  manual comparisons, and group/export publication now complete the reviewer flow.
  Representative collection acceptance remains outstanding. Model training belongs
  to the downstream trainer; it is not an unfinished application milestone.

Development follows [PLAN.md's work order and completion boundaries](PLAN.md#work-order-and-completion-boundaries).
Unfinished requirements and acceptance evidence are tracked in
[TODO.md](../TODO.md#remaining-work-against-the-existing-plan). The feature entries
below are implementation history, not replacement milestones. Launching trainer
imports from the reviewer was an assistant-proposed follow-up, not an established
requirement or current priority.

## M2 reviewed-pair threshold evaluation — 2026-11-09

M2 is the earliest unfinished milestone in the plan. Implemented the missing
measurement support for its false/missed-match and threshold-calibration work:
`dataset similarity-evaluate` and **Evaluate saved judgments** in the pair reviewer.
The shared evaluator sweeps radii 0–64 using explicit judgments and recorded hashes,
including manual pairs outside proposals. It collapses aliases, reports evidence
gaps and undefined ratios, saves replayable pair evidence and links errors back to
graphical comparison. Source data and review state remain unchanged.

Verification: **274 passed, 2 skipped** (`.cache/m2-evaluation-final.xml`), with two
new focused tests and the existing reviewer HTTP case extended for evaluation.
Generated fixtures cover manual misses, false matches, radius boundaries, alias
weighting, missing hashes, stale/pending decisions and source-offline replay.
CLI and graphical summaries matched exactly; all 65 rows and error-to-pair navigation
were checked in the browser (`.cache/m2-evaluation-smoke`), with a retained screenshot.
Lint, JS syntax, and wheel/sdist resource comparisons passed
(`.cache/m2-evaluation-build/resource-check.json`).

This supplies M2 evaluation tooling; representative pair judgments, actual threshold
calibration and collection-scale performance acceptance remain open. Later milestone
qualification continues to depend on that selected pilot, in the existing order.

## M6 count reconciliation and processing measurements — 2026-11-09

Implemented PLAN's count/time/disk reporting requirements: occurrence-identity and
count comparisons across intake, reviews, snapshots, tagging coverage, splits and
export pairs; monotonic stage timing; logical payload sizes; captured source sizes;
and deduplicated processing receipts retained through recaption and export. The same
results appear in CLI JSON, standalone QA and the graphical Snapshot report.
Inventory timing now begins before scanning; paths publishing precomputed inventory
or scores explicitly measure publication only. Legacy gaps remain visible.

Verification: **272 passed, 2 skipped** (`.cache/m6-accounting-final.xml`), with two
new focused tests for scan-inclusive timing and portable count/resource accounting.
CLI JSON and live/standalone browser checks used an export with source and upstream
runs offline (`.cache/m6-accounting-smoke`). An older export correctly reported
partial reconciliation and unavailable measurements. Screenshot capture timed out;
browser controls/data were checked, but no new visual-layout qualification is claimed.
Lint, JS syntax, and wheel/sdist resource comparisons passed
(`.cache/m6-accounting-build/resource-check.json`).

Representative batch measurements, corrected pilot findings, and user acceptance
still require the selected collection. Stage totals exclude human review waits,
final presentation files, shared models/caches and peak temporary disk usage.

## M6 snapshot reporting source requirements — 2026-11-09

Implemented PLAN section 6's content/rating distributions, top tags, and model/provider
provenance in the shared QA summary, offline report, graphical reviewer, and CLI.
Included and whole-snapshot populations stay separate; original run rows outside the
snapshot cannot contribute. Export reports read frozen evidence with the source and
caption run offline. Missing legacy observations remain unavailable.

Verification: **270 passed, 2 skipped** (`.cache/m6-final.xml`); the final missing-versus-null
provenance refinement passed both focused reporting tests (`.cache/m6-provenance.xml`).
Only two new tests were added, covering membership, excluded rows, alias counts,
rating ties, omitted/forced tags, legacy gaps and portable export evidence. CLI JSON,
live/standalone browser reporting, and prior-export verification are recorded under
`.cache/m6-smoke`; a rendered screenshot is retained there. Lint, JS syntax, and
wheel/sdist resource checks pass (`.cache/m6-build/resource-check.json`). These are
generated observations, not new model inference or collection-quality evidence.

This delivers the requested reporting source work, not M6 collection acceptance.
The selected collection, measured run resources, corrected pilot errors, and recorded
user acceptance remain outstanding under the existing plan.

**M5 is implemented:** group-aware splits, verified immutable exports, Kohya adapters,
and actual pinned CPU import receipts are recorded in the export/trainer entries below
and [docs/EXPORT.md](EXPORT.md). Those generated-fixture imports establish the
implementation path. Representative pilot export/import acceptance remains open.

## M4 configured caption and subset rules — 2026-11-09

Implements PLAN section 4: empty-default trigger/forced phrases, explicit raw-tag
subset predicates and conditional expectations, neutral composition, and visible
conflicts. Rules generate proposals; reviewed annotations still control splits.
CLI and graphical acceptance record the caption run and rule identity. Recaptioning
reuses scores and preserves saved reviews; exports retain independently verifiable
rule evidence even when a manual/source caption takes precedence.

Verification: **268 passed, 2 skipped** (`.cache/m4-final.xml`). Three focused cases
exercise evidence/addition separation, rule conflicts and schema, score-only replay,
CLI/GUI acceptance, manual override preservation and source-independent export QA.
Generated workflow evidence is under `.cache/m4-smoke/eb5cc662`; actual CLI
recaptioning inferred zero images, and browser acceptance saved/reloaded the subset.
Its `evidence.json` records the verified export and unchanged sources. Ruff,
JavaScript syntax, wheel/sdist builds and source-resource checks pass; build
artifacts are under `.cache/m4-build`.
Browser screenshot capture timed out; visual layout acceptance remains unverified.
This closes the identified M4 source gap, not representative caption accuracy or
collection acceptance. The existing M2-M6 qualification dependencies remain in
[TODO.md](../TODO.md#remaining-work-against-the-existing-plan).

## Graphical trainer receipts and qualification — 2026-11-09

- [x] Discover exact-export receipts and identify the latest current-pin result;
  retain failed, historical, mismatched, and damaged receipt states.
- [x] Add a Training import tab with refresh, split/repeat/bucket details, receipt
  JSON and loader log links, and copyable import commands for both shell families.
- [x] Show export integrity, CPU import, and report-bound pilot assessment separately.
- [x] Share receipt interpretation with `dataset trainer-status`; retain portable
  hash matching and leave export artifacts unchanged.
- [x] Refuse to publish an import receipt if the export identity changed during loading.

Verification: **265 passed, 2 skipped** (`.cache/trainer-receipts-final.xml`), with
two focused cases covering history precedence, export identity, relocation,
changed evidence, CLI status, and graphical artifact routes. Actual pinned CPU
import passed at `.cache/trainer-ui-smoke/3d779627/runs/20261109T092828423603Z-trainer-9602f377`:
2 training images / 4 repeated instances, 1 validation image, 384x256 buckets.
Browser interaction verified the transition from Not checked to Passed, receipt
details, loader-log access, and persistence after reload. Screenshot capture was
unavailable in the browser tool; visual layout acceptance remains unverified.
`evidence.json` records unchanged export/source hashes. Ruff, JavaScript syntax,
and wheel/sdist resource checks pass under `.cache/trainer-receipts-build`.
This is generated-fixture CPU loading evidence, not model training or collection acceptance.

## Graphical pair review and publication — 2026-11-09

- [x] Compare proposed and manual pairs with verified previews, decision filters,
  pagination, saved reasons, and shared CLI revision/conflict handling.
- [x] Make saved manual links navigable and count reset links as unresolved.
- [x] Publish immutable groups and QA, or groups plus a verified training export
  and QA, with configurable splits, caption drafts, resolution, and repeats.
- [x] Keep publication responsive, show progress and output paths, retain earlier
  successful outputs on failure, and open new reports within the reviewer.
- [x] Retain caption draft provenance for subsequent export publication.

Browser evidence: `.cache/pair-ui-smoke/abb904f5/evidence.json` records generated
PNG/TIFF pair review (one related, two distinct), two groups, and publication from
the reviewer. The verified export contains two training images and one validation
image with training repeats set to two; related images stay together. Source
hashes and the original QA artifacts are unchanged. `publication.jpg` shows the
completed operation, and the new report opened with published split assignments.
These fixtures establish workflow behavior, not real collection acceptance.

Verification: **263 passed, 2 skipped** (`.cache/pair-publication-final.xml`). Two
focused cases cover pair navigation/reset, stale edits, conflict handling, partial
publication results, caption provenance, and verified exports. Ruff and both
JavaScript syntax checks pass. Wheel/sdist and resource checks are recorded under
`.cache/pair-publication-build`.

## Graphical corrections and recorded pilot assessment — 2026-11-09

- [x] `dataset review-ui` serves a loopback browser app for caption overrides,
  inclusion decisions, labels, subsets, and reasons using the shared CLI review store.
- [x] Preserve concurrent changes with review-revision checks and reload controls;
  retain source hashes, immutable QA data, and existing review history.
- [x] Record report-bound image judgments, caption checks, critical-label errors,
  reviewer notes, progress, and explicit pilot conclusions with durable history.
- [x] Expose saved pilot results through `dataset assessment`; keep export QA
  assessment available when source images are offline.
- [x] Separate browser logic into a packaged JavaScript resource, shared by saved
  reports and the local reviewer. Full images are served from verified snapshot identities.

Browser evidence: `.cache/review-ui-smoke/3625a1f9` contains generated fixtures,
unchanged-source hashes, a saved graphical correction, two pilot judgments, and a
persisted needs-changes conclusion. Actual browser saves and reload persistence
were checked, including a missing critical label. Screenshot: `pilot-assessment.jpg`.
These are automated fixture judgments, not human acceptance of a real collection.
At this milestone, pair decisions and publishing new groups/exports were CLI
operations; the later pair-review milestone above adds the graphical workflow.

Verification: **261 passed, 2 skipped** (`.cache/review-ui-final.xml`). Two focused
integration cases cover real HTTP corrections, shared CLI state, stale edits,
new verified exports, and assessment persistence/conclusion history. The browser
correction also reached a new verified export with source hashes unchanged;
`evidence.json` records that chain. Ruff, JavaScript syntax, and package-resource
checks pass. Wheel/sdist output is under `.cache/review-ui-build`.

## Pilot QA reports and navigation — 2026-11-08

- [x] Generate image previews, caption/annotation findings, and category coverage
  from unfinished group snapshots or verified, source-independent exports.
- [x] Select a repeatable coverage-focused pilot while retaining the full queue;
  distinguish preview splits from published assignments and reviewed empty annotations.
- [x] Add local browser search/filter/group/category navigation and matching
  `qa-list` pagination, with commands leading back to existing review records.
- [x] Keep reports separate from source files, review state, and input snapshots.

Verification: **259 passed, 2 skipped** (`.cache/qa-final.xml`), including two
focused integration cases for incomplete reviews, source drift, deterministic
sampling, annotation/coverage filters, and exports with their source offline.
An actual CLI report for the eight-image generated export is at
`data/runs/20261108T142431476729Z-qa-756cb373/report.html` (four selected pilot images).
Filtering that report by label, split, and pilot selection and following its
emitted command returned the correct original review record and annotations.
Ruff, JavaScript syntax, and wheel/sdist resource checks pass. The managed browser blocked local
`file://` navigation; rendered interaction remains unverified. Generated fixtures
do not establish collection accuracy or human acceptance.

## Reviewed annotations and semantic splits — 2026-11-08

- [x] Add/remove/clear human labels and set/clear a semantic subset through
  `dataset review`, preserving captions and inclusion decisions under the review lock.
- [x] Track explicit empty choices separately from unreviewed annotations; list
  included images still needing annotations with `--unannotated`.
- [x] Carry hash-bound annotations and their reasons into group/export snapshots;
  reverify export annotations against captured review provenance.
- [x] Balance whole groups using reviewed multi-label/subset counts, preserving
  the primary image-ratio objective and the prior allocator for unannotated data.
- [x] Report per-category split counts, single-group limitations, missing coverage,
  mixed-subset groups, and annotation completeness. Excluded images do not count.

Verification: **257 passed, 2 skipped** (`.cache/semantic-final.xml`). Focused
cases cover annotation edits/reruns, changed-byte invalidation, CLI navigation,
overlapping labels, mixed/rare groups, deterministic allocation, and export integration.
Generated end-to-end evidence is under `.cache/semantic-smoke/46d647e2`: eight
images in four related groups, with both categories represented equally in each
split after balancing. Source hashes were unchanged. Pinned CPU trainer import
passed at `data/runs/20261108T123908380429Z-trainer-86f5c9e8` (4 training images,
8 instances with repeats, 4 validation images). No real collection accuracy or
globally optimal split claim follows from these checks.

## Pinned trainer import and compatible derivatives — 2026-11-08

- [x] Add `dataset trainer-setup` and `dataset trainer-check`, with a separate
  pinned Python 3.12 CPU runtime and unmodified sd-scripts v0.12.3 at
  `cb70b96858477e716a2096292ab8aab433277f38`.
- [x] Run upstream configuration parsing, dataset discovery, caption reading,
  repeats, bucketing, decoding, crop/resize, and finite tensor checks offline.
- [x] Publish export-bound receipts and loader logs separately; retain failure
  evidence without rewriting an export's qualification flags.
- [x] Resolve observed loader gaps: TIFF conversion, EXIF orientation, white
  alpha compositing, and zero-sized buckets from tiny/extreme-aspect images.
  Original files remain untouched; derivatives have separate recorded hashes.

Actual CLI evidence: ordinary export import passed at
`data/runs/20261108T094454819525Z-trainer-de11f767`; mixed TIFF/alpha/EXIF import
passed at `data/runs/20261108T094608640027Z-trainer-ec477643` (2 train images,
6 instances with repeats, 1 validation image, three valid aspect-ratio buckets).
The mixed fixture/export and unchanged-source hashes are under
`.cache/trainer/qualification-be9946da`. The initial tiny-image failure is retained
at `data/runs/20261108T094308540235Z-trainer-d1a5dd0e`.
No mocks replaced trainer loading functions. No tokenizer, model training step,
GPU execution, anime-collection accuracy, or human acceptance is claimed.

Final verification: **254 passed, 2 skipped** (`.cache/trainer-final.xml`);
Ruff lint/format and whitespace checks pass. Wheel/sdist build under
`.cache/trainer-build` includes the worker and pinned dependency resources.
Final mixed-export CLI receipt after runtime checks were finalized:
`data/runs/20261108T094913631642Z-trainer-02a7d4b3`.
Setup succeeds on repeat without network when installed dependency pins match.

## Group-aware splits and verified export — 2026-11-08

- [x] Deterministic whole-group train/validation allocation with configurable seed
  and ratio, actual counts, and small-collection warnings.
- [x] Apply manual overrides, source sidecars, and optional tagging/recaption
  drafts in that order; publish only explicitly included occurrences.
- [x] Copy original image bytes and normalized captions to unique pairs; freeze
  split assignments, review provenance, and checksums in each new snapshot.
- [x] Verify copied pairs and group/byte split isolation before publication;
  independently reverify snapshots without their original source collection.
- [x] Generate separate Kohya train/validation TOML with configurable resolution
  and repeats, aspect-ratio bucketing, and no upscaling.

Five focused integration cases cover real caption publication, review-to-export
flow, deterministic reruns, alias preservation, exclusions, changed image/sidecar
bytes, missing captions, orphan files, source-offline verification, and CLI use.
Commands: [docs/EXPORT.md](EXPORT.md). Trainer import, collection quality,
and semantic label balancing are not established by these checks.

Verification: **250 passed, 2 skipped**; `.cache/export-final.xml` and
`.cache/pytest-export-final`. Ruff lint/format and whitespace checks pass.
The actual `dataset.exe` entry point also verified the generated CLI export.
The two skips remain Windows symlink privilege and case-only caption names.
The initial full run caught one changed scan-output assertion, corrected before
the passing run; its receipt remains `.cache/export-full.xml`.

## Durable review and group snapshots — 2026-11-07

- [x] List pending pairs/images; record related/distinct pair decisions and
  include/exclude image decisions, each with a reason and revision history.
- [x] Manually link related artwork outside the pHash proposal list.
- [x] Save/clear manual caption overrides independently of inclusion decisions;
  preserve source captions and generated drafts.
- [x] Persist review state atomically under a writer lock, bound to source paths
  and hashes. Reuse unchanged-source decisions and report stale records.
- [x] Publish deterministic group membership, retaining exact-byte aliases,
  individual decisions, captions, and history. Reject transitive contradictions
  before saving edits; recheck source images before publication.
- [x] Distinguish incomplete review snapshots from completed reviews and keep
  training readiness false until export/trainer validation exists.

Commands and storage contract: [docs/REVIEW.md](REVIEW.md). Generated-fixture
integration checks cover the persistent workflow, CLI navigation/manual links,
transitive conflicts, changed sources, caption preservation, and unchanged-source
reruns. Source/sidecar bytes remain unchanged. Source-sidecar revalidation and
applying overrides to final captions remain export-stage work.

Verification: **245 passed, 2 skipped** in the full source suite;
`.cache/review-suite.xml` and `.cache/pytest-review-suite`, with fresh bytecode
under `.cache/pyc-review`. Ruff lint/format and diff whitespace checks pass.
The two skips remain Windows symlink privilege and case-only caption names.
The three added integration tests exercise the new review implementation; the
earlier 38 similarity tests are separate historical work. These results establish
source execution and preservation, not a rendered reviewer, installed release,
collection acceptance, export compatibility, or training quality.

## M2 proposal execution qualification — 2026-11-07

- [x] 38 new regression cases cover real Pillow image variants, EXIF/alpha
  preparation, Hamming-index results against exhaustive comparison, stable pair
  IDs, deterministic artifacts, streamed writes, source preservation, changed
  sources, malformed inventories, decode limits, interruption, failed publication,
  CLI exit codes, optional-dependency isolation, and a real Windows junction.
- [x] Fix malformed inventory objects/rows that crashed or silently omitted
  eligible images. Validate schema, paths, kinds, decisions, reasons, and hashes
  before downstream output creation; tagging shares the inventory reader.
- [x] Reject a source root replaced by a file; check padded-square limits before
  decoding; remove deprecated Pillow pixel access without changing the hash policy.
- [x] Record current validation limits and reconcile total images, considered
  images, exact duplicate aliases skipped, and ineligible images skipped.

Verification: **242 passed, 2 skipped**, `.cache/m2-final.xml`, using
`.cache/pytest-m2-final-v2` and a fresh `.cache/pyc-m2-current` bytecode cache. Both
Windows junction tests pass. The skips remain Windows symlink privilege and
case-only caption names. Ruff lint/format and diff whitespace checks pass.
Wheel and sdist built offline under `.cache/m2-build`.

An isolated non-editable wheel, with no NumPy/ONNX runtime installed, ran
`dataset scan` and `dataset similarity` on generated PNG/BMP variants and an exact-byte
alias. Counts reconciled, one review pair was produced, and every source image and
manual caption hash remained unchanged. Evidence:
`.cache/m2-wheel-smoke/0e6d97a31665457b91db6f3c80f7874c/verification.json`
and adjacent command logs.

The checkout had a stale editable install and pytest bytecode referring to its
previous path. Locked environment sync repaired the install; a fresh local bytecode
cache resolved a traceback-source test failure. Initial failing regression
evidence remains in `.cache/similarity-initial.xml` and `.cache/m2-qualified.xml`.
These checks establish proposal execution and preservation, not anime similarity
accuracy, collection-scale throughput, approved groups, or training readiness.
See [the similarity contract](SIMILARITY.md).

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

See [docs/INSTALLATION.md](INSTALLATION.md) for the recovery contract.
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

Workflow design and research links: [docs/TRAINIME.md](TRAINIME.md).
Anime accuracy, physical CUDA, large-collection performance, reviewed export,
and trainer acceptance remain pending.

## Initial M1/M3 qualification boundary (historical)

The current implementation status and later export/import evidence are recorded
at the top of this document. The following preserves the earlier milestone boundary.

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

## Implementation reconciliation — 2026-11-09

Completed portions extracted from the former mixed-status matrix. These entries
record source implementation; the active acceptance work is in
[TODO.md](../TODO.md#remaining-work-against-the-existing-plan).

| Milestone / source | Implemented portion |
| --- | --- |
| **M1 — intake**, PLAN section 1 | Inventory, validation, exact duplicates, source preservation, CLI/configuration and reports. |
| **M2 — similarity**, PLAN section 2 | Indexed pHash proposals, durable pair/image review, exact aliases, related groups, graphical comparisons and saved-judgment threshold evaluation with false-match/known-miss navigation. |
| **M3 — tagging**, PLAN section 3 and docs/TAGGING.md | Pinned WD profiles, reference preprocessing, raw scores, cache/resume, CPU/provider handling and score-only recaptioning. |
| **M4 — captions and review**, PLAN section 4 | Threshold/exclusion rules, opt-in triggers/forced phrases, configured subset proposals, neutral composition/conflicts, durable overrides, explicit proposal acceptance, manual annotations and pilot assessments. |
| **M5 — export**, PLAN section 5 | Whole-group semantic splits, immutable pairs, independent verification, Kohya configurations and pinned CPU import receipts. |
| **M6 — full collection**, PLAN section 6 and M6 acceptance row | Snapshot QA, pilot navigation, split coverage, caption findings, recorded judgments, content/rating distributions, top tags, provenance, count reconciliation and stage time/payload measurements. |
| **Trainime and installation**, docs/TRAINIME.md and docs/INSTALLATION.md | Installed directory tagging/removal, exact four-choice menu, settings, recovery, diagnostics and repair registry have recorded milestone evidence. |

### Delivered source work

1. **M2 reviewed-pair evaluation — source support delivered:** measured threshold
   comparisons use explicit labels and recorded hashes. Representative pilot
   selection, judgments and collection calibration remain the earliest open acceptance work.
2. **M4 caption/subset rules — source implementation delivered:** semantics are
   recorded in PLAN section 4 and docs/TAGGING.md. Rule identity now follows
   recaptioning, accepted reviews and export evidence; pilot accuracy remains open.
3. **M6 reporting — source implementation delivered:** snapshot membership,
   separate included counts, rating ties, missing observations, tag rankings,
   frozen model/provider provenance, count reconciliation and processing time/payload
   receipts now follow PLAN section 6. Full-collection execution and acceptance remain open.

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

Research, commands, evidence scope, and pending comparisons are in
[docs/TAGGING.md](TAGGING.md). Camie is researched but not implemented.

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
