# Completed work and verification log

<!--
WORKFLOW_UTILIZED: "MIVIM.spec":"COMPLETE"
WORKFLOW_CYCLE: dataset-preparation-2026-10-11
WORKFLOW_UPSTREAM: ../TODO.md
WORKFLOW_NEXT: SHELVED.md
-->

Extracted from the project TODO on **2026-11-09**. Original milestone dates,
versions, completed checklist items, verification results, evidence locations and
qualification limits are retained. Refer to [TODO.md](../TODO.md) for unfinished
work and [PLAN.md](PLAN.md) for the governing design and milestone order.

This is a historical completion log, not a claim that every milestone's collection
acceptance is complete. Earlier limitations describe the evidence available at that
milestone; later entries may supersede them. Generated fixtures, model execution,
trainer import and human acceptance remain distinct. Evidence paths in code spans
are relative to the repository root unless an absolute location is specified.

<a id="artifact-coherence-0200"></a>

## Artifact snapshot coherence — 0.20.0 — 2026-11-12

Completed **CF22** in the existing cycle. Catalog summaries derive parsed values
and identity from the same captured metadata. Catalog verification and queries use
the captured SQLite payload, with all referenced metadata and standalone membership
checked again before return. Collection discovery retains checked job/binding/config
context and excludes changed dependent entries with explicit retry diagnostics.
Unaffected rows and historical/current distinctions remain available.

Trainer status checks captured export metadata, manifest, referenced metadata,
media and membership before reporting current qualification. Receipt metadata,
result and log are interpreted from one checked read set; detected changes or
incomplete discovery cannot retain an earlier current pass. Changed exports clear
the verification result. The reviewer pins artifact links to the inspected receipt
metadata digest, including after another refresh or a same-ID replacement. Legacy
valid receipts, historical failures, other pins, relocation and source-offline reads
remain supported. Inspection does not repair or rewrite evidence.

See [artifact snapshots and recovery](ARTIFACT-SNAPSHOTS.md). These checks detect
observed drift; they do not lock outside writers or guarantee future immutability.
General reader extraction (SC02), schema-reader work (SC06) and measured query
optimization (TM21) remain queued. No trainer/model adoption or acceptance change
was made.

### Original scheduled tasks, completed

- [x] **CF22 — return coherent catalog snapshots.** Derive parsed metadata and
  reported identity from the same captured bytes. Verify referenced artifacts
  against that snapshot and reject detected drift before returning catalog/query
  results. Preserve valid relocated exports and source-offline inspection. Do not
  rely on timestamps alone or require the whole SC02 reader-layer refactor.
- [x] **CF22 — bind trainer status to verified receipt/export snapshots.** Prevent
  an earlier passed receipt from appearing current after its receipt, manifest or
  export metadata changes during inspection. Preserve historical receipt identity,
  current versus historical distinctions and explicit stale/invalid diagnostics.
  Keep inspection read-only and avoid rewriting receipts or inferring acceptance.
- [x] **Qualify and archive the bounded batch.** Reproduce the retained deterministic
  read races, then verify metadata/manifest/receipt changes, same-ID rewrites,
  valid relocation, offline reads and unchanged artifact bytes. Run focused/full
  regression, installed catalog/trainer-status commands and affected status views.
  Record exact implementation identity, failures and qualification limits in
  COMPLETED, then reconcile CF22 and promote the next bounded candidate.


### Scoped push-qualification enabler — SC19

The requested baseline push exposed an existing workflow admission error before
any hosted jobs started: `.github/workflows/ci.yml` line 23, column 22 reported
`Unrecognized named-value: 'runner'` for the job-level `runner.temp` expression.
The correction sets `TRAINIME_HOME` in a Bash setup step from `$RUNNER_TEMP`,
writing the value to `$GITHUB_ENV` for later steps. This preserves isolated
application data on both configured runners without changing the frozen Python
payload. The original three CF22 task bodies above remain unchanged.

`ci-qualification.json` retains the rejected hosted run and official actionlint
validation of the corrected workflow. This is local workflow validation, not a
hosted Windows/Linux test pass. The hosted run for the final push remains pending.
SC19 retains its completed source-support state with this scoped correction;
no platform or human acceptance is inferred.

### Verification and retained evidence

Evidence root: `.cache/artifact-coherence-20261112/`.

- The completed 0.19.0 baseline was committed and pushed to `origin/main` as
  `a8d525f3ea82d9194c22f6e496a130637f9f3cbe` before CF22 development; the remote
  SHA matched. `baseline-git.json` records that handoff. The new source and workflow
  changes are a separate delivery.
- `independent-baseline-probe.json` reproduces four races against preserved 0.19.0:
  mixed catalog metadata/identity, late query drift, a trainer pass after export
  drift despite an expected QA hash, and a same-ID receipt replacement inheriting
  an earlier pass. Original bytes were restored. Eight initial failing catalog
  regressions are retained in `catalog-before-fix.*`; focused/final review evidence
  retains later corrections rather than erasing initial results.
- `independent-current-probe-02.json` retained a later failure: a receipt rewritten
  during the expensive final export verification could still appear passed. The
  final receipt fence now follows that export check, with controlling metadata
  checked after its payloads. `independent-current-probe-03.json` passes that race
  and all eight other independent cases; these probes preserve generated bytes.
- `catalog-final-focused.*` records **70 passed, 1 skipped**. That process had
  already loaded the collection module before the last narrow fence-order change.
  `catalog-final-order.*` separately passes all three final ordering/receipt cases,
  including the added regression. `catalog-contract.json` preserves this exact
  boundary; the full suite below runs against the final frozen source and tests.
- Final full regression: **1541 passed, 16 skipped**, with no
  failures or errors (`full-suite.xml`, `full-suite-timing.json`). Focused catalog,
  trainer, HTTP and deterministic race checks passed. Ruff and formatting checks
  passed for source, tests and scripts. `qualification-start.json` pins the exact
  source/test/smoke inputs used by final qualification.
- Isolated installed **0.20.0** qualification passed **154 command checks**
  (`installed-01/result.json`). `artifact-snapshot-coherence.json` checks catalog
  inspection/query on a relocated Unicode export and standalone index, with the
  original source offline; generated trainer receipt pass/failure/stale/invalid
  states; pinned artifact-link rejection; and recovery after exact restoration.
  Export/catalog/report/receipt bytes were preserved. Generated receipts are
  explicitly fixtures: no new trainer execution or import qualification is claimed.
- `browser-qualification.json` records live installed Training import controls,
  same-ID receipt replacement, export-drift rejection and restored status. Human
  acceptance remains false. Screenshot inspection also checked the affected Training import view.
  Owned tabs and servers were closed and generated artifacts were restored.
- `actual-source.json` and `actual-installed.json` record read-only inspection of
  the already selected collection: **399 source files / 564,441,065 bytes**, **14
  protected records**, model and saved-score files remain unchanged. Assessment
  revision **63** and review revision **109** remain intact. Existing export,
  catalog and trainer receipts were inspected without running inference/import or
  changing dataset acceptance. The checked export's **729
  files** remain unchanged and **3 catalog rows**
  were queried. Existing trainer evidence reports `passed`
  across **1 receipt(s)**. This checks existing
  evidence and does not establish a new trainer execution.
- Runtime payload `6fb884c880f747e3b7ad83462faa1fa228da75b254a9996e5fe27d72a3c6de2e`
  (**81 runtime files**). `package-parity.json` binds final
  source/wheel/sdist/installed bytes, tests, documentation and command ledgers.
  `document-validation.json` checks all 109 queue IDs, task bodies, history and
  local links. The phase `result.json` binds final evidence and qualification limits.

This delivery establishes source, generated-fixture, installed-command and browser
behavior within the recorded scope. It does not establish new model accuracy,
training/GPU results or human dataset acceptance. Required M4 acceptance and its
M5/M6 dependencies stay open; no new IDENTIFIED cycle has begun.

CF22 is completed in SHELVED. TODO now schedules **QOL21 + localized SC15**
publication reconnect/response ordering in PLAN order; that next batch remains
unimplemented. Only the localized SC15 publication portion is active; broader
frontend request abstraction remains queued within that row.

<a id="model-rule-contract-0190"></a>

## Configured model identity and saved-rule contract — 0.19.0 — 2026-11-12

Completed **CF24** and the scheduled **bounded SC06 saved-caption rule contract**
in the existing cycle. Configured fetch reuse, tagging, preparation/resume, cache
inspection and managed recovery verify requested model, repository and resolved
full revision before inference or default selection. Existing artifact hash checks
remain. Generic inspection and explicit custom revisions remain available; frozen
completed checkpoints can be verified without a local model when their retained
evidence is sufficient. Recovery retains rejected bundle bytes before replacement.

One checked resolver now supplies recorded caption rules to label evaluation,
model comparison and caption explanations. It validates complete current fields,
nested rules, canonical types/values, vocabulary, default threshold and recomputed
digest. Missing historical evidence and unsupported versions are explicitly
unavailable; malformed present evidence rejects. It never substitutes current model
settings or defaults. Raw score > cutoff behavior, caption policy, offline evidence,
assistant filtering and calibration/held-out separation remain intact. Rejection
precedes evaluation publication and comparison-exposure writes.

Use [model selection and saved rules](MODEL-RULE-CONTRACT.md) for operating and
recovery behavior. Identity binding is not publisher authentication or model-quality
acceptance. The broader SC06 central schema/legacy-reader proposal remains queued,
including stricter typing at export-only `caption_analysis_version` readers; this
batch preserves that existing contract and does not add it to scored-run metadata.

### Original scheduled tasks, now completed within their bounded scope

- [x] **CF24 — bind configured model selection to the verified bundle.** Before
  fetch reuse, tagging, preparation/resume, cache inspection or model-recovery
  success, verify the requested model, repository and resolved full revision
  against the loaded bundle. Preserve generic artifact inspection and existing
  artifact/file checksum checks. Reject mismatches before inference or threshold
  selection; retain mismatched artifacts through existing recovery mechanisms.
  Verify each mismatch, matching/custom-revision reuse, resume rejection,
  inspection without writes, preserved recovery backups and a generated ONNX
  execution. Give synthetic fixtures an explicit identity contract.
- [x] **SC06 — unify the bounded saved-caption rule contract.** Reuse one checked
  resolver in label evaluation, model comparison and caption explanations.
  Validate supported version, complete recorded rules, saved default threshold,
  canonical values, vocabulary and recomputed rule digest. Missing historical
  evidence must be explicitly unavailable or produce a precise operation failure;
  malformed present evidence must reject. Never substitute current defaults or
  load the current model to interpret saved scores. Preserve valid offline
  artifacts, caption semantics, human/assistant filtering and calibration/held-out
  separation. Verify missing versus malformed fields, unsupported versions,
  digest mismatch, threshold boundaries and consumer parity.
- [x] **Qualify and archive the bounded batch.** Run focused regressions, the full
  suite, installed CLI/recovery checks and the affected rendered comparison flow.
  Preserve source/model/evaluation artifacts and prior evidence. Record exact
  implementation identity, retained failures and qualification limits. Close
  CF24 after delivery; record only the saved-rule portion under SC06, leaving its
  broader schema/legacy-reader proposal explicitly queued within that row.


Dependencies and limits retained: completed CF21/CF23, existing bundle checks,
score readers and saved-rule replay. No general schema rewrite, model adoption,
threshold change or human reattribution was performed. Synthetic ONNX fixtures
now declare the configured model identity while retaining generated bytes and
their actual hashes; production validation has no fixture bypass.

### Verification and retained evidence

Evidence root: `.cache/model-rule-contract-20261112/`.

- Final regression coverage: **1473 passed, 16 skipped**,
  matched by exact test identity to the final collection. `regression-coverage.json`
  retains full-run counts and the complete CLI fixture rerun. Ten setup errors in
  the initial full invocation came from an older synthetic checkpoint that omitted
  model identity. The corrected fixture's **20 tests passed**; runtime source did
  not change. This is reconciled full-plus-focused coverage, not a claim that the
  initial full invocation exited cleanly.
- CF24 focused/regression checks: **128 passed** (`cf24-contract.json`). Final
  saved-rule checks: **230 passed** (`saved-rules-focused-final.*`). Independent
  caption UI entrypoints: **18 passed**. Ruff and format checks pass across source,
  tests and scripts (`ruff-final-*`, `format-final-*`).
- Independent review corrected two saved-rule error-classification edges before
  final qualification: unsupported future grammar and malformed present vocabulary
  combined with missing identity. Both fixes have regressions and independent
  reprobes. Initial evidence is retained in `retained-findings.md` and the focused
  logs; `independent-review.md` records the final bounded review.
- `installed-01/result.json`: isolated installed **0.19.0** qualification passed
  **145 command checks**, with generated ONNX interruption/resume and the existing
  recovery flows. New `model-binding-contract.json` checks model/repository/revision
  mismatches through read-only CLI cache inspection, generic inspection and exact
  backup preservation in managed recovery. Its injected fetch uses generated bytes;
  no publisher model was downloaded.
- `saved-rule-contract.json`: valid installed evaluation/comparison/explanation,
  missing rules, null rules, wrong digest and unsupported version were exercised.
  Invalid runs publish no evaluation and append no exposure. Exact fixture metadata
  and judgment bytes are restored; valid comparison succeeds afterward.
- `browser-qualification.json`: actual installed browser controls showed score
  **0.5 / cutoff 0.5 → Absent**, and **0.5 / cutoff 0.25 → Present**. A valid first
  model followed by an invalid second digest displayed the error without changing
  judgment bytes, attribution, revision or exposure. Reopening the verified runs
  succeeded without duplicate exposure. All generated judgments/viewers are
  assistant-attributed. Accessibility/DOM observations verify this functional flow;
  repeated screenshot-tool timeouts prevented a fresh pixel-layout review. Browser
  HTML/JavaScript was unchanged. Owned tabs and servers were closed.
- `actual-source.json` and `actual-installed.json`: read-only inspection preserved
  **399 source files / 564,441,065 bytes**, **14 protected records**, the selected
  model's three bundle files and **782 saved-run files**. Its existing saved rules
  and one saved caption explanation pass. Assessment revision **63**, review
  revision **109** and three label workspaces remain intact; human acceptance is
  false. No inference or actual-collection writes occurred.
- Runtime payload:
  `0eb1c6c19ecb48749180c3658df591a33d69f66a824947934c4f488885007a18`
  (**81 runtime files**). `qualification-start.json` preserves the initial frozen
  inputs; `qualification-final.json` records the one corrected test fixture.
  `package-parity.json` binds final source/wheel/sdist/installed bytes, all **62 test
  files**, documentation and command ledgers. `document-validation.json` checks
  workflow IDs, preserved task bodies, prior completion history and local links.

This qualifies source, generated fixtures, installed commands and live-browser
functional behavior. It does not establish a new visual layout review, physical
GPU/platform qualification, real-image model accuracy or human dataset acceptance.
No global installation, commit or release was performed.

CF24 is completed in SHELVED. SC06 returns to queued with this saved-rule delivery
linked and its broader remainder explicit. TODO now schedules **CF22** artifact
snapshot coherence in PLAN order; it is not implemented by this delivery. Required
M4 human acceptance and M5/M6 acceptance remain separate and open. No new IDENTIFIED
cycle has begun.

<a id="review-integrity-0180"></a>

## Judgment integrity and label-save recovery — 0.18.0 — 2026-11-12

Completed the scheduled **CF21/CF23** source batch in the existing cycle.
Assessment, correction-review and label records now receive strict shape,
attribution and history/current-state checks on reads and locked writes. A shared
pure replay validator aligns ordinary review edits with history/batch operations.
Invalid JSON, malformed actors/exposures/revisions and replay divergence fail
without rewriting the original evidence. Valid legacy unknown attribution,
record-carried attribution, restore/batch/clear semantics and offline reads remain
supported. Assessment membership stays bound to exact report/pilot identities.

The label reviewer uses one eligibility predicate for click, form submit,
Ctrl+Enter and Save + next. Empty filters hide the old image editor; pending,
failed or stale image requests cannot enable a save. Image retry preserves drafts;
Show all images restores a valid queue; conflict/reload failures retain unsaved
input until an explicit saved-label reload. The existing assistant/API judgment
contract remains available. See [the operating guide](REVIEW-INTEGRITY.md).

### Original scheduled tasks, now completed

- [x] **CF21 — validate persisted judgments consistently before use or mutation.**
  Validate and replay assessment current state/conclusion against history, check
  exact report/pilot image identities and supported record shapes, and use the
  same complete review-state validation for ordinary edits as history/batch
  operations. Close the label workspace's schema/revision, clear-event actor and
  exposure-validation gaps. Validate again under the existing write lock before
  appending. Keep legacy missing attribution explicitly `unknown`, retain valid
  historical event semantics and distinguish an absent legacy actor field from a
  present malformed actor. Preserve valid attribution carried by the record when
  an old event lacks a separate actor; do not downgrade it to unknown. Preserve
  invalid files unchanged with an
  actionable diagnosis; never silently repair or reattribute evidence.
- [x] **CF23 — enforce one label-save eligibility rule.** Route button clicks,
  form submission, save-next and Ctrl+Enter through the same current-selection,
  visible-membership, preview-ready and not-busy checks. Empty filters and failed
  or pending previews must not submit a hidden/stale image. Fence late image
  load/error events to their selection, preserve unsaved input during recoverable
  failures, and provide a usable return to a valid queue. Keep the existing
  nonbrowser judgment API and explicit assistant/human attribution contract.
- [x] **Qualify and archive the bounded delivery.** Add meaningful regressions
  for current/history divergence, malformed/legacy events, attribution, lock-time
  changes, absent-versus-malformed actors and rejected-write byte preservation.
  Exercise each label save path,
  delayed image events, empty-filter recovery and conflict retry. Inspect the
  rendered label and assessment/review journeys; run focused/full checks and
  installed-resource/command qualification appropriate to the actual changes.
  Record exact results, retained failures, implementation identity and limits in
  COMPLETED, then reconcile these two queue states. Do not reuse past test totals
  as evidence for the new implementation.


Dependencies and boundary retained: existing review-history replay and store
locking, frozen QA/label selections, and controller/browser harnesses. This is not
a database migration or general persistence rewrite. SC05/SC06/SC15 broader scope
is not completed by this batch.

### Verification and retained evidence

Evidence root: `.cache/review-integrity-20261112/`.

- Final regression coverage: **1356 passed, 16 skipped**
  across the full run and the final four-file focused run, matched against the
  final collected test identities. `regression-coverage.json` records the exact
  per-test reconciliation, source hashes and retained failures. The initial full
  run's fixture-construction failure is superseded by the corrected focused run;
  it is not presented as a clean full-suite invocation. The focused rerun also
  covers tests added after the full run collected.
- Ruff check and format check passed across source, tests and scripts
  (`ruff-*`, `format-*`). JavaScript controller syntax and the 12 actual-controller
  tests passed, including delayed callbacks, every save entry, empty membership,
  reload failure, revision conflict and draft preservation.
- `package-01-*` and `installed-01/result.json`: isolated installed **0.18.0**
  candidate passed existing command/recovery qualification and **17 new HTTP
  integrity requests**. Corrupt stores reject both reads and saves with damaged
  bytes preserved; exact restoration works; a programmatic assistant save,
  stale-revision rejection and correct retry succeed. Existing commands and
  HTTP checks are retained in their ledgers, not borrowed from earlier versions.
- `browser-qualification.json`: installed rendered desktop label and assessment/
  correction journeys passed on generated fixtures. Ctrl+Enter, empty-filter
  recovery, unavailable-image retry with a retained draft, two-tab conflict,
  explicit reload, Save + next and restored record diagnostics were observed.
  Browser-generated judgments are all assistant judgments. Delayed image races
  are controller-test evidence rather than manually timed browser evidence.
- `actual-source.json` and `actual-installed.json`: read-only compatibility with
  the selected collection preserved **399 source files, 564,441,065 bytes and
  14 protected records**. Assessment revision **63**, review revision **109** and
  all three label workspaces remain intact; human acceptance remains false.
- Runtime payload:
  `73f310a47d18778dc78a963a972b5c3fa57279c304f364cb90025e2801414a67`
  (**80 runtime files**). `package-parity.json` binds the final wheel, source
  archive, installed candidate, runtime/test sources and current documentation.
  `document-validation.json` checks workflow IDs, task preservation and links.
- Prior Windows temp-root permission failures, assessment/review test-fixture
  construction failures, the initial installed-path assertion and browser receipt
  assembly correction remain in logs and `retained-harness-failures.md`.
  They were corrected at the harness boundary; damaged application evidence was
  never automatically repaired or reattributed.

Qualification is source, generated-fixture, installed-command and rendered desktop
evidence. Full-history ordinary reads now cost O(history); no larger-scale
performance claim is made. This does not establish new model accuracy, GPU/native
device qualification, human review or M4–M6 dataset acceptance. Existing collection
files and acceptance records were not changed. No global install, commit or release
was performed.

CF21/CF23 are completed in SHELVED. TODO now schedules **CF24 + bounded SC06**
model-binding/saved-rule correctness in PLAN order; that implementation remains
unfinished. SC06's broader schema-reader proposal remains queued within its row.
M4 human acceptance is still the next required dataset acceptance. No new
IDENTIFIED cycle is opened.

<a id="workflow-source-reconciliation-20261112"></a>

## Source and backlog reconciliation — 2026-11-12

Completed the user's requested MIVIM review/planning task against the current
**0.17.0 working tree**, without changing runtime source, tests, package settings,
actual collection data or saved acceptance records. This is planning completion,
not implementation of the new findings or closure of the open cycle.

- Reconciled all **102 existing finding IDs**, preserving their actions,
  completion evidence, proposal conditions and original priorities; added
  **CF21–CF24, QOL21, TM21 and DP03**, for **109** queue entries.
- Refined the remaining scope of partially delivered candidates and added exact
  source observations, dependencies and verification boundaries in the
  [comprehensive source review](SOURCE-REVIEW-2026-11-12.md).
- Promoted only **CF21/CF23** into the next [TODO batch](../TODO.md#review-evidence-integrity).
  All eight prior unfinished TODO task bodies remain; M4–M6 human acceptance
  remains separately attributed and open. PLAN and IDENTIFIED received an
  in-cycle addendum, not a replacement review cycle.
- Retained generated fixtures/probes for persisted-judgment validation, label
  save eligibility, publication response ordering, metadata snapshot races,
  requested-model binding, saved-rule validation, configuration aliasing and
  atomic-write failure behavior. Performance proposals remain unmeasured. An
  unsuccessful malformed-receipt hypothesis and initial harness mistakes are
  retained as such rather than reported as application defects.
- Three independent subsystem reviews checked the final contracts. Two wording
  refinements were applied: absent versus malformed legacy actors, and explicit
  saved-rule version/digest handling without current-default reconstruction.

Evidence: `.cache/workflow-source-review-20261112/` contains before documents,
source hashes, subsystem audit notes, probe scripts/results and
`document-validation.json`. Document checks cover ID/state/link consistency,
retained task/action text and unchanged runtime/test/package inputs. No full
application suite, installed run, real browser, physical GPU/platform, model
quality or human acceptance check was rerun for this documentation task.

Return to [TODO](../TODO.md#review-evidence-integrity) for source development, then
archive actual delivery evidence and replenish from [SHELVED](SHELVED.md#current-source-priorities)
in PLAN order. The runtime payload remains
`73de3c746b8f06d06d5f29bd62bc9b20eff37fd58d27641ab1fd3932c1d720f1`.

<a id="review-preferences-0170"></a>

## Saved review filters and resume — 0.17.0, 2026-11-12

The promoted **QOL07** M4 batch is complete. The existing reviewer now keeps named
image-filter views and image/pair resume positions separately from corrections,
assessments and dataset acceptance. See [the guide](REVIEW-PREFERENCES.md) and
[qualification receipt](../.cache/review-preferences-20261112/result.json).
Required M4–M6 human acceptance remains open.

### Original promoted TODO tasks — completed

### Active continuation — recover review browsing

<!-- WORKFLOW_TASK_GROUP: review-preferences; SOURCES: QOL07; MILESTONE: M4 -->

Recover the exact report's image filters and last queue position across reviewer
relaunches, with named filter combinations. Depends on the existing immutable QA
identity and reviewer; browsing preferences remain separate from review decisions.

- [x] Implement bounded, atomic per-report browsing preferences outside source,
  report and review records. Preserve concurrent edits and invalid stored evidence;
  preference failures must not prevent reviewing the dataset.
- [x] Add named image-filter views and restore image/pair queue positions through
  the existing reviewer, including changing server ports. Honor explicit image
  links, preserve unsaved forms and provide clear preference retry/reset actions.
- [x] Verify restart/isolation, stale responses, invalid preferences, concurrent
  sessions and offline sources through core, HTTP, installed-package and rendered
  checks. Preserve original images/judgments and keep human acceptance open.

### Delivered behavior

Live preferences use a bounded application-data record keyed by canonical report
location and metadata hash. Atomic revision checks protect concurrent writers;
invalid stored evidence is preserved and preference failures leave review usable.
Saved filters, named views and the image position survive a different server port.
An explicit image fragment wins when opening the report URL. Dirty forms and stale
responses cannot silently replace current navigation or unfinished judgments.

Pair resume looks for its exact identity within the saved 20-row page. A changed
queue shows an explicit fallback and retains the old checkpoint until a user
selects a pair; it does not search all pages. Clear saved resume retains filters,
named views and the current on-screen forms. Standalone reports use content-based,
origin-dependent browser storage with best-effort cross-tab conflict detection;
identical copies under the same origin may share that browsing state.

### Verification

- Frozen complete suite: **1216 passed, 16 skipped**,
  zero failures/errors. All **56 test-source files** and **79
  runtime files** match the qualification freeze and tested wheel.
- Isolated installed-package qualification retained **120 existing command checks
  + 17 caption-explanation command checks**, and added **24 preference HTTP checks**.
  Different-port restart, report isolation, stale and invalid updates, source-offline
  reads, corrupt-store recovery and bounded preference-only writes passed.
- Browser interaction and layout evidence is linked through the qualification
  receipt. Screenshot availability and appearance qualification are recorded in the browser receipt.
  Assistant operational checks do not establish human usability acceptance.
- Read-only actual-report inspection preserved **399 source files** and **14
  protected records**, without creating a preference record or adding judgments.
  Source images, report artifacts, correction history and assessments stay unchanged.
- Closure preserves **102 source IDs**, **8 original TODO task bodies**, these exact
  **3 promoted task bodies**, and all prior completion history. Earlier interrupted
  or failing diagnostic evidence remains retained. Final source-archive document
  parity and the independent postclosure audit follow this workflow update.

Evidence is retained under `.cache/review-preferences-20261112/`. Source relocation
(NF09/CF19), broader model/training qualification and M4–M6 human acceptance remain
separate. This delivery does not start another IDENTIFIED cycle or imply a global
installation, commit, push or hosted-CI result.

<a id="caption-explanations-0160"></a>

## Saved caption rule explanations — 0.16.0, 2026-11-12

The promoted **TM09** M4 core-feature batch is complete. Exact image/tag inspection
now explains a saved model draft from its verified scores and frozen rules, without
inference, changing captions or recording judgments. See
[the guide](CAPTION-EXPLANATIONS.md) and
[qualification receipt](../.cache/caption-explanations-20261112/result.json).
Required M4–M6 human acceptance remains separate and open.

### Original promoted TODO tasks — completed

### Active continuation — explain saved caption rules

<!-- WORKFLOW_TASK_GROUP: caption-explanations; SOURCES: TM09; MILESTONE: M4 -->

Explain the saved draft for an exact image using verified saved scores and frozen
rules, so directory-preparation users can diagnose caption omissions and subset
proposals without inference or changing reviews. Depends on existing scored runs
and the delivered QOL09 comparison; it does not schedule source relocation.

- [x] Implement a reusable read-only explanation for selected, omitted, near-threshold
  and rating tags, exact threshold sources, subset predicates and literal additions.
  Replay the pinned caption rules against checked scores; reject inconsistent
  evidence and make unsupported historical versions explicitly unavailable.
- [x] Expose exact image/tag inspection through a configuration-independent command
  and the existing reviewer. Support prepared-workspace selection and offline source
  images; keep draft explanations distinct from overrides and effective captions.
- [x] Verify rule boundaries, corrupted/stale evidence, aliases, unavailable drafts,
  browser selection fences and preserved unsaved work. Qualify installed commands
  and read-only selected-collection examples; preserve source bytes, judgments and
  historical artifacts, with human acceptance separately open.

### Delivered behavior

The shared caption engine supplies a derived trace while preserving prior caption
outputs. It explains strict threshold comparisons and cutoff sources, explicit
drops, disabled character tags, rating-only evidence and inclusive near-threshold
margins. Every subset predicate uses observed raw tags, including caption-omitted
tags; expected-tag findings and overlapping matches remain visible. Literal
trigger/forced phrases and case-insensitive duplicate handling retain their origins.

`dataset caption-explain` uses an exact saved run or a checked prepared workspace,
collection and optional historical job. It supports relevant-tag pages and explicit
raw tag selection without current configuration, source images, model loading or
network access. Verified manifests remain authoritative over loose editable draft
text. Inconsistent evidence is rejected; unsupported or incomplete historical rules
are explicitly unavailable instead of replayed with current defaults.

The existing caption-comparison pane exposes lazy **Explain draft rules** inspection,
exact-tag search, bounded pages and separate subset/phrase details. Exact report,
image and captured-export bindings are checked. Missing original scores remain
unavailable even when an export retained caption text. Request and page fences
preserve unsaved corrections, assessments and other forms. The explanation describes
the saved draft; it does not establish the effective override, exported caption,
image truth, subset acceptance or model quality.

### Verification

- Final frozen-source suite: **1113 passed, 16 platform skips**,
  zero failures/errors, from `pytest-fresh.xml` with a fresh bytecode cache.
  Whole-repository Ruff check, format and JavaScript syntax checks passed.
  All **53 test-source files** match the freeze; exact skips and timings are retained.
- Isolated installed-wheel qualification: **120 existing command checks + 17 caption
  explanation command checks**. All **77 runtime files** match source, tested wheel,
  installed package and qualification source archive. Generated checks cover offline
  sources, exact current/historical job selection, aliases, requested/relevant tags,
  Unicode output, unavailable/corrupt evidence and missing optional score support.
- Independent frozen qualification: **108 passed** (88 core/related and 20 CLI),
  plus **1,024 deterministic differential cases** matching the previous caption
  engine's outputs. Review findings and their fixes remain in the independent receipt.
- Browser interaction records cover **12 observations**: relevant pages, exact-tag
  Enter activation, threshold equality, subset/phrase origins, unknown-tag recovery,
  preserved unsaved fields, offline sources and alias navigation. At a **390px**
  viewport the document measured **375px**; desktop geometry was checked at
  **1280px**, without horizontal document overflow. Both screenshot APIs timed out:
  **no screenshots or pixel-appearance acceptance are claimed**. DOM interaction and
  geometry evidence do not establish human usability or dataset acceptance.
- The installed package inspected **3 deterministic actual saved drafts through the
  core and the same 3 through report sessions**, plus **1 exact current-job CLI
  inspection**. These were read-only diagnostic explanations, not new image judgments
  or caption acceptance. All **399 source files / 564,441,065 bytes** and **14 protected
  records** retain their hashes; all **39 generated browser-fixture files** are
  restored unchanged. No source or historical artifact was rewritten.
- The first full-suite process was stopped after inherited pytest bytecode exposed
  an old checkout in `co_filename`. The stopped process, failed diagnostic recheck,
  pre-fix test failures and investigation receipts remain retained. Fresh-cache
  diagnostics passed, and only the complete fresh-cache suite supplies the final
  count above. This environmental failure did not require changing frozen source.
  The single offending cache entry was preserved and regenerated; the ordinary
  diagnostic test command also passes from the current checkout.
- This closure preserves **102 source IDs**, **8 prior TODO task bodies**, the exact
  **3 promoted task bodies**, and all earlier completion history. The coordinating
  agent rebuilds and checks the final source archive after this document closure;
  the tested wheel and runtime bytes remain frozen.

Evidence is retained under `.cache/caption-explanations-20261112/`, including the
fresh-suite JUnit/timings, package qualification, actual inspections, browser
observations/preservation, independent contract review and workflow audit.
NF09/CF19 relocation and M4–M6 human acceptance remain open. No new IDENTIFIED cycle,
global installation, training/model-quality qualification, hosted CI, commit or push
is implied by this delivery.

<a id="reviewer-recovery-0150"></a>

## Reviewer recovery — 0.15.0, 2026-11-12

The promoted **QOL08** M4 operational batch is complete. Empty queues and failed
reads now explain their state and offer relevant recovery controls. The existing
correction and assessment forms can recover after initial read failures without
reopening the page. See [the guide](REVIEWER-RECOVERY.md) and
[qualification receipt](../.cache/reviewer-recovery-20261111/result.json).
Required M4–M6 human acceptance remains separate and open.

### Original promoted TODO tasks — completed

### Active continuation — actionable reviewer empty states and recovery

<!-- WORKFLOW_TASK_GROUP: reviewer-recovery; SOURCES: QOL08; MILESTONE: M4 -->

Make the existing reviewer explain empty and unavailable states and provide direct,
read-only recovery actions. Build on QOL09's observed offline correction-form issue;
preserve exact selection, unsaved work, source checks and separate human acceptance.

- [x] Distinguish a report with no images from an image queue emptied by filters,
  and distinguish no unresolved pairs from no saved/proposed pairs or a failed
  pair load. Offer direct reset, all-pairs, snapshot or manual-comparison navigation
  only when applicable; do not imply empty queues establish dataset acceptance.
- [x] Show actionable missing/failed image and pair previews with bounded explicit
  retry and existing full-image access where applicable. Retrying a preview must
  preserve unsaved correction, assessment and pair fields and retain image identity.
- [x] Keep correction/assessment reload available after initial reads fail; allow
  recovery after source restoration without reopening the page. Fence late replies,
  prevent overlapping reload/save races and retain revision/reason checks. Only an
  explicit form reload may replace its unsaved values; recovery must not save data.
- [x] Verify no-data/filtered/pair/preview states, offline-to-online recovery,
  stale responses and preserved unsaved work. Retain rendered desktop/narrow,
  installed-resource and read-only actual evidence, original workflow tasks and
  source/judgment hashes; leave M4–M6 human acceptance separate.

### Delivered behavior

The reviewer distinguishes no report images, filters with no matches, no unresolved
pairs, no indexed/saved pairs and failed pair reads. Context-specific actions reset
filters, show all pairs, open the snapshot summary or reach manual comparison.
Empty queues never establish dataset acceptance; failed reads clear stale targets.

Preview failures expose explicit retry and existing full-image access where
applicable. A retry requests the same recorded image once and preserves unsaved
correction, assessment and pair fields. Browser inspection found that decoded-image
reuse could hide a changed or unavailable file even with `Cache-Control: no-store`.
Initial loads and retries now use fresh page/request identities, with stale-response
guards and the loaded image node reused rather than a second unguarded request.

Correction and assessment reload controls remain available after initial failure.
Successful explicit reload replaces only that form's unsaved values; failed reload
preserves its edits and revision baseline. Preview retry never reloads saved values.
Reload/save serialization and selection fences prevent late replies from replacing
newer forms. Existing reason, revision and source-content checks remain unchanged.
Recovery performs no save, inference, publication, source relocation or acceptance.

### Verification

- Final frozen-source suite: **987 passed, 16 platform skips**,
  zero failures/errors. Ruff check and format passed. All **50 test-source files**
  match the amended freeze; exact skips, UTF-8 logs and timings are retained.
- Isolated installed wheel: **120 command checks**, **21 recovery HTTP GETs**, and
  the existing **2 caption core inspections / 16 caption HTTP requests**. All
  **74 runtime files** match source, wheel, installation and source archive.
- Independent controller probes check empty/failed states, dirty-field preservation,
  overlapping requests, stale replies and fresh media request identities. The first
  qualification was superseded after the browser exposed decoded-image caching;
  its full-suite process was interrupted before completion. Earlier artifacts and
  that incomplete log remain under `first-qualification/`; they are not reported as
  a failing source-test result or used as the final freeze's qualification.
- Desktop/narrow browser interaction checks cover populated, all-pairs-reviewed,
  no-pair and legitimate zero-image reports, filter recovery, preview failures and
  source restoration. DOM, accessibility-tree, geometry and functional evidence are
  retained. Screenshot capture was unavailable: **no pixel-appearance acceptance is
  claimed**. This does not establish human usability or dataset acceptance.
- Installed actual read-only inspection covers the **355-image report**, **6 saved
  correction reads**, all/unreviewed pair queues (**96 / 46**)
  and existing assessments at correction revision **109**. Writes, directory
  creation and mutation entry points are guarded. No judgments or corrections change.
- All **399 original files / 564,441,065 bytes** and
  **14 protected records** retain their hashes. The 62-image assistant assessment
  remains revision 63, `human_accepted=false`. Generated faults restore all **95**
  fixture files, including hashes and modification times.
- The archive preserves all **159** prior paths and adds exactly the recovery guide
  and regression-test module (**161** files total). Final archive checks bind the
  completed documents, manifests and frozen tests; the final wheel must remain
  byte-identical to the isolated tested wheel.

### Handoff and limits

QOL08 closes the initial offline-form recovery limitation recorded in 0.14.0.
Retries use existing identities and original paths; they do not repair corrupt
source files, relocate a source, regenerate previews or add filter persistence.
A changed historical report can still require reopening it. Human acceptance,
broader relocation and storage changes retain their separate PLAN scope.

No model/GPU/trainer qualification, hosted CI, global installation update, commit
or push is claimed. The PLAN remains open for independently attributed M4 human
acceptance and later M5/M6 requirements. Continue eligible SHELVED work in PLAN
order; do not begin a new IDENTIFIED cycle before required acceptance is complete.

<a id="caption-comparison-0140"></a>

## Caption comparison — 0.14.0, 2026-11-11

The promoted **QOL09** M4 operational batch is complete. The image correction editor
shows the saved override, recorded source sidecar and pinned draft, with effective
keep/replace/remove outcomes before saving. See [the guide](CAPTION-COMPARISON.md)
and [qualification receipt](../.cache/caption-comparison-20261111/result.json).
Required M4–M6 human acceptance remains separate and open.

### Original promoted TODO tasks — completed

### Active continuation — compare caption candidates before correction

<!-- WORKFLOW_TASK_GROUP: caption-comparison; SOURCES: QOL09; MILESTONE: M4 -->

Compare the saved override, source sidecar and report-bound draft in the existing
image correction editor before saving. Reuse authoritative caption precedence;
preserve historical snapshots, source bytes and separately attributed acceptance.

- [x] Add one read-only caption comparison core bound to the exact QA image,
  input provenance and current review revision. Reuse override/sidecar/draft
  resolution; validate available captured or source evidence and distinguish
  absent, invalid and unavailable candidates without searching for a newer draft.
- [x] Explain the effective caption and keep/replace/clear outcomes, including
  literal phrase changes and full candidate text. Label frozen evidence and
  historical snapshot text accurately; do not claim derivative-specific export
  output, source-image validation, inference or semantic correctness.
- [x] Integrate a compact accessible comparison into the existing correction
  form. Preserve unsaved captions, labels, subsets and assessments on refresh or
  late responses; retain existing reason/revision guards and separate publication.
  Comparison requests must not save reviews or modify source sidecars/drafts.
- [x] Qualify group/export provenance, precedence and invalid evidence, aliases,
  offline inspection, read races, unsaved form state and desktop/narrow behavior.
  Retain installed-package/resource and actual read-only evidence, preserve the
  original workflow tasks, and leave M4–M6 human acceptance separate.

### Delivered behavior

One read-only comparison core binds the selected QA image, exact input provenance,
captured review history and current revision. It reuses export caption precedence
and whitespace normalization. Export reports use captured sidecar/draft evidence;
group reports inspect exact recorded sidecars and the pinned draft manifest. Group
draft-run metadata is checked against current recorded bindings, not described as
a captured digest when that digest was never recorded. No newer tagging run is chosen.

Candidate states distinguish present, absent, invalid and unavailable evidence.
Invalid or unavailable winning evidence does not silently fall through. A valid
override can remain effective while lower candidates report errors. Captions and
new snapshot/draft artifact reads are bounded at 1 MiB and 64 MiB respectively;
existing selected-inventory and whole-JSON review-history loading remains unchanged.
Read consistency checks cover changed, missing and unavailable evidence.

The existing correction form displays full candidate text with expandable provenance,
effective text beside the caption input and a bounded literal phrase comparison.
Changes count comma-separated phrase occurrences, not semantic meaning. Historical
snapshot text remains distinct from current and proposed text. Late responses and
revision changes cannot silently advance the save baseline or overwrite unsaved
captions, labels, subsets or assessments. Existing reason/revision guards and separate
publication remain in effect. Comparison reads neither open source image payloads
nor save corrections, create directories, run inference or publish output.

### Verification

- Frozen-source suite: **981 passed, 16 platform skips**,
  zero failures/errors. Ruff check and format passed; exact skips, logs and timings
  are retained. The full run uses UTF-8 in both runner and pytest processes.
- Isolated installed wheel: **120 command checks**, plus **2 caption core inspections
  and 16 HTTP requests**. All **74 runtime files** match source, wheel, installation
  and source archive. Checks cover candidate precedence, normalization, alias identity,
  read-only requests, invalid actions, offline group/export evidence and packaged UI.
- Independent generated-fixture probes cover exact lineage, strict histories,
  missing/corrupt evidence, malformed drafts, read races, metadata-only inspection
  and the distinct normalization/derivative boundary. An initial smoke exercise had
  a test-only tuple-versus-JSON-list comparison error; that failed evidence is retained,
  and the corrected smoke exercise and installed qualification passed.
- Rendered desktop and 390-pixel narrow checks verify accessible full captions,
  provenance wrapping, adjacent effective preview, preserved unsaved fields, stale
  save rejection, explicit reload, clear/replacement saves, exact aliases, source-offline
  evidence and changed-report failure/recovery. Generated-fixture corrections advance
  revision 11 to 14 while the report remains historical. Final frozen runtime and
  earlier iteration checks are distinguished in the rendered receipt.
- Installed read-only inspection of **3 actual images / 4 comparisons** at current
  and captured revision **109** matches frozen export source captions. The selection
  includes draft and override evidence and an image with derivative caption adjustment.
  The selected actual report has no sidecars; sidecar cases use generated fixtures.
  Actual review bytes and mtime remain unchanged; writes, directories, source-image
  reads and mutation entry points are guarded. No new judgments are recorded.
- All **399 original files / 564,441,065 bytes** and
  **14 protected records** retain their hashes.
  The 62-caption assistant assessment remains revision 63, `human_accepted=false`;
  earlier pilot judgments, exports and correction history are preserved.
- The archive retains all **155** prior paths and adds exactly
  four feature/test/guide files (**159** total). Final package
  checks bind completed documents, manifests and frozen tests; the final wheel must
  remain byte-identical to the isolated tested wheel.

### Handoff and limits

QOL09 is complete. These are source-caption choices, not derivative-specific export
predictions, semantic quality acceptance or proof that publication will succeed.
Existing offline correction-form recovery can require reopening the page after the
source returns; comparison refresh preserves form state and does not restore save
controls. This observed pre-existing limitation is recorded under queued QOL08.
NF09/CF19 relocation and whole-JSON history scaling remain separate work.

No model/GPU/trainer qualification, hosted CI, normal installation update, commit or
push is claimed. The PLAN stays open for independently attributed M4 human acceptance
and subsequent M5/M6 requirements. Continue eligible SHELVED work in PLAN order;
do not begin another IDENTIFIED cycle before required PLAN acceptance is complete.

<a id="review-changes-0130"></a>

## Review snapshot changes — 0.13.0, 2026-11-11

The scheduled **QOL10** M4 source-support batch is complete. The CLI and existing
Publish pane explain exact saved review differences before publication. See the
[review-changes guide](REVIEW-CHANGES.md) and [qualification receipt](../.cache/review-changes-20261111/result.json).
Required M4–M6 human acceptance remains separate and open.

### Original promoted TODO tasks — completed

### Active continuation — changes since a published review snapshot

<!-- WORKFLOW_TASK_GROUP: review-changes; SOURCES: QOL10; MILESTONE: M4 -->

Explain which saved corrections differ from an exact QA report and connect that
explanation to existing publication actions. Preserve the report, source files,
review history and separately attributed assessments.

- [x] Validate the report/input/captured-review lineage and compare its frozen
  records with current validated review state. Distinguish no change, history-only
  advancement and net image/pair changes; reject missing, truncated, divergent or
  inconsistent evidence rather than inferring continuity from revision numbers.
- [x] Expose exact changed identities and fields with bounded pages, report
  membership and selected-inventory compatibility. Use metadata only; distinguish
  saved-record changes from actual caption/export effects or live-source validity.
- [x] Connect one shared inspection core to `review-history changes` and the existing
  reviewer Publish pane. Resolve only explicit reports or the selected job's checked
  QA checkpoint, preserve request/selection identity, show the inspected revision,
  and provide existing guarded publication navigation without automatic writes.
- [x] Qualify group/export reports, restored-to-original and bulk history, missing
  or changed lineage, offline inspection, UI refresh and pagination, installed
  commands and rendered desktop/narrow behavior. Retain actual read-only evidence
  and original tasks; leave M4–M6 human acceptance separate.

### Delivered behavior

`dataset review-history changes` compares current saved reviews with an exact QA
report's captured group/export review evidence. Collection/workspace selectors use
the recorded completed QA checkpoint, or an explicit report; explicit run/config
selection requires a report. Bounded metadata checks bind checkpoint ownership,
input identity and declared artifacts without opening preview or source media.
Both histories use strict shared replay validation, including restoration and batch
events. The captured history must be an exact prefix of current history.

Results distinguish unchanged records, history-only advancement and net record
changes. Exact image/pair identities, before/after fields, full counts, report
membership and inventory compatibility are paged. A comparison identity binds
subsequent CLI pages. These are record differences, not predicted caption/export
effects or live-source validation. Unavailable or divergent evidence is an error.

The Publish pane refreshes after saved corrections, rejects late responses and
restarts pagination if inspected evidence changes. Bounded scrolling and collapsed
details keep publication controls accessible. Refresh preserves unsaved publication
settings; report changes after page opening require reopening. Inspection itself
does not save, publish, lock, repair, transfer acceptance or create directories.

### Verification

- Frozen-source suite: **922 passed, 16 platform skips**,
  zero failures/errors; Ruff check and format passed. Exact skips and logs are retained.
  An initial runner omitted the required UTF-8 mode and failed a Unicode recovery
  fixture; that failed run and reproduction remain recorded. Correcting the runner
  resolved the fixture without source changes; the final suite uses UTF-8 throughout.
- Isolated installed wheel: **120 command checks**, with
  **73 runtime files** identical across source, wheel, installation and source archive.
  New checks cover checked and explicit reports, group/export evidence, changes,
  assistant restoration to history-only, fresh unchanged snapshots, offline source,
  stale page identity and preservation of inspected files.
- Independent generated fixtures cover strict lineage, missing digests, truncated
  and divergent history, out-of-report records, batch/pair changes, portability,
  metadata-only reads and read races. Review corrected default checkpoint selection
  that unnecessarily read preview assets; dedicated coverage now guards that boundary.
- Rendered desktop and 390-pixel narrow checks verify filtered/paged differences,
  stale-page recovery, correction refresh, preserved unsaved settings, unavailable
  evidence and publication to a fresh unchanged report. A long expanded list found
  during visual review was replaced with bounded scrolling and disclosure controls.
  This is assistant interface qualification, not human usability acceptance.
- Installed read-only inspection of actual job `20261110T030017203730Z-0f3c5fa8` finds **unchanged**
  records at captured/current revision **109**, both for its exact QA checkpoint
  and the later explicitly selected corrected QA report. Actual review bytes and
  mtime remain unchanged, with write/live-source validation entry points guarded;
  the independent explicit-report probe also forbids source-media opens.
- All **399 original files / 564,441,065 bytes** and
  **14 protected records** retain their hashes.
  The 62-caption assistant assessment remains revision 63, `human_accepted=false`;
  earlier pilot judgments, exports and correction history are preserved.
- The archive retains all **150** prior paths and adds exactly
  five feature/test/guide files (**155** total). Final package
  checks bind the completed documents, manifests and frozen tests; the final wheel
  must remain byte-identical to the isolated tested wheel.

### Handoff and limits

QOL10 is complete for review-record comparison and existing publication navigation.
QOL09 caption comparison, NF09/CF19 relocation and whole-JSON history scaling remain
queued. No model/GPU/trainer qualification, hosted CI, normal installation update,
commit or push is claimed. The PLAN stays open for independently attributed M4 human
acceptance and subsequent M5/M6 requirements; continue eligible SHELVED work without
starting another IDENTIFIED cycle prematurely.

<a id="bulk-review-0120"></a>

## Reviewed bulk annotation — 0.12.0, 2026-11-11

The scheduled **NF11/QOL06** M4 source-support batch is complete. Exact image
membership, full previews and one atomic attributed batch improve review throughput.
See [bulk-review commands](BULK-REVIEW.md) and the
[qualification receipt](../.cache/bulk-review-20261111/result.json).
This CLI delivery preserves the separate M4–M6 human acceptance requirements.

### Original promoted TODO tasks — completed

### Active continuation — reviewed bulk annotation

<!-- WORKFLOW_TASK_GROUP: bulk-review; SOURCES: NF11,QOL06; MILESTONE: M4 -->

Improve correction throughput for an explicit finite image selection. Preview every
selected path/hash and its before/after state independently of filters; keep source
images, captions, published artifacts and human assessments unchanged.

- [x] Add validated bulk label/subset/inclusion changes for exact image paths, with
  complete visible membership, canonical operations and a read-only preview bound
  to current review bytes/revision and selected artifact context. Reject duplicate,
  missing, invalid or ineligible targets; do not infer selection or accept model tags.
- [x] Apply the inspected changes atomically under the existing review lock after
  revalidating all selected source identities and graph consistency. Record one
  attributed batch with contiguous per-image history revisions, preserving unrelated
  fields and prior events; retain individual history inspection/restoration and
  reject stale, malformed, linked, conflicting or partially writable work.
- [x] Expose cohesive preview/apply CLI commands for registered collections,
  preparation workspaces and explicit runs, sharing selection/continuation contracts
  with review history. Show every selected member and exact changes, provide guarded
  continuation commands, and keep publication and acceptance separate from editing.
- [x] Qualify atomic success/failure, operation semantics, no-op behavior, source
  and selection drift, history compatibility, package commands and actual read-only
  preview. Preserve existing source/judgment evidence and archive original task
  bodies without completing M4–M6 human acceptance.

### Delivered behavior

`dataset review-batch` previews by default. Registered collection, preparation
workspace and explicit run/configuration selectors use shared contracts with
`review-history`. Supply repeated exact image paths or a bounded UTF-8 JSON path
list. Every selected path/hash, current/proposed record and changed/unchanged count
is visible independently of filters. Labels, subsets and inclusion decisions are
explicit reviewed values; there is no model-tag acceptance or bulk caption edit.

Apply requires the current revision, exact preview identity, reason and actor kind.
The preview binds operations, complete membership, review bytes/revision, artifact
context and CLI selection; selection files also bind their exact bytes. Under the
shared writer lock, apply rechecks these identities and all selected source files,
including unchanged members, then validates group consistency before one atomic
publication. Failure cannot partially save image changes. True no-ops retain the
revision and history; explicit reviewed-empty states remain distinct from absence.

Changed images receive contiguous history revisions linked by one batch identity.
The complete membership descriptor is stored once; subsequent events carry compact
references. History validation checks the batch's membership, operations, ordering
and reconstructed state. Original events and unrelated caption/annotation fields
survive. Individual batch members can be restored through review history, and
ordinary later edits remain compatible. Publication remains a separate continuation;
guidance failure cannot misreport a committed batch as failed.

### Verification

- Final frozen-source suite: **848 passed, 13 skipped**,
  zero failures/errors. Ruff check/format passed. Exact platform skip reasons and
  commands remain in the receipt; unavailable host capabilities are not qualified.
- Isolated installed package: **102 command checks** and
  **72 payload files** matching source, wheel, archive and installation. Twelve new
  bulk commands exercise complete membership, atomic apply, stale-preview rejection,
  unchanged batches, changed no-op sources, selection-file drift, per-image history
  restoration, offline preview and duplicate rejection. Ordinary later edits and
  source/export/caption preservation are checked in the generated fixture.
- Focused source tests and independent generated-fixture review cover complete or
  rejected publication, reviewed-empty semantics, malformed provenance, source and
  selection drift, lock contention and compatibility with existing review history.
  Independent injection exposed a source-replacement window between hash checking
  and file-state capture. Pre/post-verification identity checks close that window;
  the exact failed probe and its successful rejection after the fix are both retained.
- Installed read-only preview of **two explicitly selected actual images** succeeds
  against job `20261110T030017203730Z-0f3c5fa8` at correction revision **109**. Write and live-source
  validation entry points were guarded. The diagnostic preview reports
  **0 changed members**; apply was not invoked and no new
  actual judgments were saved.
- All **399 original files / 564,441,065 bytes** and
  **14 protected records** retain their hashes.
  The 62-caption assessment remains revision 63 with assistant attribution and
  `human_accepted=false`. Earlier pilot judgments, exports and revision-109 history
  remain unchanged.
- The archive retains all **144** previous paths and adds
  exactly the six feature/test/guide files (**150** total).
  Final package qualification checks the completed documentation and manifests;
  its wheel must be byte-identical to the isolated tested wheel.

### Handoff and limits

NF11/QOL06 is complete for CLI batch review with visible explicit membership.
No graphical bulk controls or bulk undo are claimed. History uses the existing
whole-JSON store; this is not completion of SC10/TM18 scaling work. NF09/CF19 source
relocation remains queued. Source images, sidecars, published artifacts and report
assessments are unchanged by editing. This batch adds no real-model/GPU/trainer
qualification, hosted CI, normal installation update, commit or push.

The next required PLAN acceptance remains the independently attributed M4 human
conclusion, followed by M5/M6 acceptance. The PLAN stays open; continue eligible
source support through SHELVED without starting another IDENTIFIED cycle.

<a id="review-history-0110"></a>

## Review history and guarded restoration — 0.11.0, 2026-11-11

The scheduled **NF10** M4 operational enabler is complete. This adds a CLI history
viewer and explicit correction recovery within the existing PLAN; human acceptance
remains separate. See [review-history commands](REVIEW-HISTORY.md) and the
[qualification receipt](../.cache/review-history-20261111/result.json).

### Original promoted TODO tasks — completed

### Active continuation — review history and guarded restoration

<!-- WORKFLOW_TASK_GROUP: review-history; SOURCES: NF10; MILESTONE: M4 -->

Make saved image/pair corrections recoverable through the existing review store.
This is operational review support; pilot assessments and human acceptance remain
separate. Original images, sidecars, published exports and prior history stay intact.

- [x] Add read-only, validated image/pair history with bounded result pages, exact
  event identity and before/after changes. Preserve unattributed legacy events and
  distinguish the initial absence of a decision from explicitly reviewed emptiness.
- [x] Preview restoration of a selected revision's before or after state. Apply only
  with a matching preview identity and current revision, verify affected source
  identities and group consistency under the review lock, and append an attributed
  restore event. Replace/remove the exact target record without merging later fields
  or changing unrelated reviews; reject stale, malformed, linked or conflicting work.
- [x] Expose history and preview/apply through a cohesive CLI with named-collection,
  workspace and explicit-run selection. Bind collection selection to its job and
  configuration, retain offline read-only history, and print exact continuation
  commands. Keep source relocation, bulk edits and acceptance records outside scope.
- [x] Qualify image/caption/annotation and pair/evaluation restoration, first-edit
  removal, restoring a restore, concurrency/conflict/source failures, immutable prior
  artifacts, isolated installed commands and read-only actual history inspection.
  Archive evidence and original task bodies without completing M4–M6 human acceptance.

### Delivered behavior

`dataset review-history list|show|restore` accepts a registered collection,
preparation workspace, or explicit similarity run/configuration. Lists show exact
image/pair identities, revisions, actor/reason and before/after changes with bounded
result pages. Show distinguishes the historical edit from the current restoration
preview. Legacy actors remain unknown. Historical content that no longer matches
the selected inventory or pair policy cannot be restored to new content.

Restore defaults to a read-only preview. Its checksum binds current review bytes,
revision, selected event, target state and artifact context; CLI selection also
binds registry/job/configuration identity. Explicit apply rechecks selection under
the existing writer lock, verifies affected source bytes and graph consistency,
and atomically appends an attributed restore event. It replaces the complete
selected record or removes it when restoring before a first edit. Later fields
cannot survive through merging, and restoring a restore uses the same contract.
Unchanged targets do not append a duplicate revision. Existing normal edits remain
compatible with the new event history.

History sequence, typed records, identity continuity, restore provenance and
replayed current-state equality are checked before trusting a target. Duplicate
JSON keys and nonfinite values are rejected. Read-only operations create no locks,
logs, directories or reports; rejected selections do not trigger repairs. Failures
in post-save continuation guidance remain separate from an already committed
revision. Existing exports and assessments are immutable; continuation commands
respect the preparation implementation guard and point to refresh or a new job.

### Verification

- Final-source suite: **790 passed, 13 skipped**, with
  zero failures/errors. Exact commands, timings and platform limitations remain
  in the receipt; skipped filesystem capabilities are not treated as qualified.
- Isolated installed package: **90 command checks** and
  **69 payload files** matching the source, wheel,
  source archive and installation. Thirteen added history commands cover exact
  caption/annotation and pair/evaluation restoration, stale-plan rejection,
  first-edit removal, reversing a restore and offline reads/previews. Fixture
  restoration events are explicitly assistant; source/export bytes are preserved.
- Focused tests cover source/context/store drift, history corruption, graph
  conflicts, atomic failure, shared locking, selection changes, ordinary subsequent
  edits, malformed data, source links and post-commit guidance failures. Independent
  review identified an identity-switch risk within a pair key and a misleading
  post-commit failure response; focused regressions verified both fixes before
  final qualification.
- Installed read-only inspection of the selected collection reads all **109**
  historical correction events (**57 image, 52 pair**) and previews selected image
  and pair states. Legacy actor metadata remains **unknown for all 109 events**;
  historical reasons are retained without inventing attribution. The correction
  store's bytes and mtime remain unchanged. Writes and live source-validation entry
  points were guarded during these inspections; no restoration was applied.
- All **399 original files / 564,441,065 bytes**,
  **14 protected records**, and frozen source payloads
  retain their hashes. The additional protected record is the actual revision-109
  correction store. Separately, the 62-caption assessment stays at revision 63 with
  assistant attribution and `human_accepted=false`; prior pilots and exports remain.

Supporting development runs, review findings and their limits remain retained in
the phase directory. They are not substituted for the final frozen-source suite
or isolated installed-package evidence.

The first package build was deliberately stopped after 318 seconds while the
backend traversed ignored cache/model/test trees. Its failed exit and logs are
retained. Enabling `skip-excluded-dirs` completed the rebuilt archive in
3.86 seconds with the runtime payload unchanged.
Archive coverage checks preserve all 139 prior paths and
add exactly five NF10 files (144 total); ignored operational
trees remain excluded. This is measured build evidence, not a general performance
benchmark or completion of the separate storage/scaling proposals.

### Handoff and limits

NF10 is complete for CLI history viewing and guarded recovery. No new graphical
panel is claimed. Pagination bounds responses, not the existing whole-JSON store's
memory or replay cost; SC10/TM18 scaling proposals remain separate. NF09/CF19 source
relocation and bulk edits remain queued. This batch performs no user-collection
restore, new real-model inference, GPU/trainer qualification, hosted CI, normal
installation update, commit or push.

The next required PLAN acceptance remains M4 human review, followed by M5/M6
dataset and user conclusions. This operational feature neither supplies those
judgments nor opens a new IDENTIFIED cycle. Follow SHELVED's promotion rules for
the next eligible bounded continuation.

<a id="cache-readiness-0100"></a>

## Verified inference-cache readiness — 0.10.0, 2026-11-10

This completes **CF17's live-cache remainder**, following the preparation,
publication and receipt-navigation work recorded below. The
[qualification receipt](../.cache/cache-readiness-20261110/result.json) retains
source identity, test/package results, actual collection inspection and limits.
Use [the preparation guide](PREPARATION.md#check-cached-inference-progress).

### Original promoted TODO tasks — completed

### Active continuation — verified inference-cache readiness

<!-- WORKFLOW_TASK_GROUP: cache-readiness; SOURCES: CF17 -->

Finish CF17's cache-progress support for preparation jobs using an explicit
inspection. Exact cache identity requires the active ONNX providers and options;
the requested check may load the locally retained model and initialize its session.
It performs no image inference, downloads, cache repair or source/application writes.

- [x] Add bounded, identity-checked score-cache reads shared with inference, with
  separate valid, missing and invalid entries; preserve corrupt files and reject
  linked or oversized archives without scanning unrelated namespaces.
- [x] Add `dataset status --verify-cache` for the selected preparation job. Validate
  its inventory and model binding, determine the actual current-session namespace,
  and report eligible occurrences, unique contents and current cached progress.
  Check current source membership/bytes separately; unavailable prerequisites must
  remain explicit rather than becoming zero hits or a claim of resumability.
- [x] Keep cache inspection separate from completed artifact integrity, current
  versus historical jobs, implementation compatibility and human acceptance. Existing
  caption-only jobs need no model/session; default status and artifact verification
  remain offline-safe. Provide exact-job continuation guidance without auto-resume.
- [x] Qualify interrupted inference and verified cache reuse on generated ONNX
  fixtures, corrupt/missing cache entries, source/model/provider changes, read-only
  actual collection inspection and installed commands. Archive task bodies, evidence
  and limits while preserving prior reviews and the open human acceptance tasks.

### Delivered behavior

`dataset status --verify-cache` verifies the selected job's inventory and local
model binding, then initializes its configured ONNX session to observe the exact
provider/options namespace. It checks only expected eligible content, separating
image occurrences, unique vectors, valid/missing/invalid cache entries and source
availability. Compressed inputs, expanded members and NPY allocation headers are
bounded before loading; inference uses the same checksum/identity validator.
Corrupt entries remain untouched. The check performs no predictions, downloads,
cache repair or application-artifact writes.

Whole-source membership and bytes, including caption sidecars, are checked
separately from stored vectors. Current and historical job selection, application
compatibility and completed artifacts retain their independent meaning. Completed
tagging and verified recoverable publications do not depend on live cache/model
availability for continuation. Missing entries alone are normal remaining work.
Ordinary status and `--verify` remain offline-safe; existing-caption checks do not
load the optional model runtime. Diagnostics show bounded corrupt paths and exact
job commands without resuming or selecting another job.

### Verification

- Final-source suite: **743 passed, 12 platform skips**,
  zero failures/errors; exact commands, durations and skip reasons are retained.
- Isolated installed package: **77 command checks** and
  **67 payload files** matching source, wheel, source
  archive and installation. Generated ONNX interruption leaves a valid cached
  vector; resume reuses one vector, infers one and reuses one exact-byte alias.
  Corruption, offline sources and missing optional runtime remain separate checks.
- Generated source tests cover changed providers/options/preprocessing, changed
  model/source/inventory, oversized and deceptive arrays, unavailable prerequisites,
  historical jobs, and publication recovery after checkpoint failure. No GPU
  execution is implied by synthetic provider identity changes.
- Installed read-only inspection of the actual selected `pilot-dir` verifies
  **396 eligible occurrences** and
  **381 unique contents**: cache counts
  **381 valid, 0 missing,
  0 invalid** under the observed current runtime.
  Completed artifacts verify; the older job remains separately identified and no
  resume is attempted. Prediction, download and cache publication entry points were
  guarded, and inspected cache bytes/mtimes remained unchanged.
- All **399 original files / 564441065 bytes** and
  **13 protected records** retain their hashes.
  The 62-caption assessment remains revision 63 with assistant attribution and
  `human_accepted=false`. Earlier pilot labels, representative judgments, review
  revisions, exports and trainer receipts remain intact.

Development failures are retained rather than erased: an initial test command
named a nonexistent doctor test, the default Windows pytest temp root was denied,
and the first new smoke helper omitted its required validation configuration.
Corrected fresh-local tests and the final installed run supersede those attempts.
An independent review reproduced a false new-job recommendation after tagging
publication/checkpoint interruption; the final regression verifies recovery without
new inference. Supporting focused evidence is not relabeled as final-suite evidence.

### Handoff and limits

CF17 is complete within its recorded preparation/publication/repair-recovery scope.
No user-collection repair, new real-model inference, GPU qualification, hosted CI,
global installation change, commit or push occurred. Cache inspection establishes
current reuse evidence, not model accuracy, a guarantee about later runtime state,
or human acceptance. M4 human review remains the next required PLAN acceptance,
followed by M5/M6 dataset and user conclusions. Optional proposals retain their
SHELVED conditions; the next eligible support batch must be promoted with its IDs.
No new IDENTIFIED cycle is opened.

<a id="recovery-browser-090"></a>

## Recovery receipt navigation and guarded restoration — 0.9.0, 2026-11-10

The scheduled operational continuation completes **QOL18** and **CF17's recovery
receipt-navigation portion**. The live inference-cache progress remainder of CF17
stays queued. This uses the existing PLAN and source findings, without opening a
new IDENTIFIED cycle or recording human acceptance. The [qualification receipt](../.cache/recovery-browser-20261110/result.json)
retains executable identity, test/package evidence, preservation checks and limits.
See the [recovery browser guide](RECOVERY-BROWSER.md) and [recovery contract](RECOVERY.md).

### Original promoted TODO tasks — completed

### Active continuation — recovery receipt navigation

<!-- WORKFLOW_TASK_GROUP: recovery-browser; SOURCES: QOL18,CF17 -->

Continue the authorized directory usability/recovery phase with QOL18 and the
receipt-navigation portion of CF17. Existing removal, restore, collision and package
repair receipts provide the inputs. Human acceptance stays separate; NF10's review
history viewer is not collision undo and is not part of this batch.

- [x] Deliver QOL18's read-only recovery operation browser over known application
  receipt locations, showing affected paths, retained recovery locations and saved
  status. Support exact source/kind/status filtering, offline sources and isolated
  errors for malformed or unavailable records without modifying receipts or backups.
- [x] Bind selected receipts to exact path and metadata identity; show checked,
  copyable continuation commands. Caption restore must reject stale selected
  receipts. Collision retry must explicitly retain its existing whole-source scope;
  package recovery must use current installation diagnosis, never historical targets.
- [x] Connect diagnosis and operation results to recovery navigation without new
  Home choices. Keep list/show reachable without optional/native dependencies,
  nonmutating even on errors, and separate saved history from current integrity.
- [x] Qualify interrupted/conflicting/legacy receipts, multiple repair kinds,
  offline reads, malformed peers, identity changes and installed command journeys;
  archive this batch's evidence and preserve existing human acceptance and history.

### Delivered behavior

`dataset recovery` lists known application-owned removal, restoration, collision
and package-repair receipts. Source, kind and saved-status filters help locate an
operation without searching image trees. Missing or malformed metadata appears as
an isolated error while valid peers remain visible. Listings expose recorded paths,
backup locations and progress; source images can be offline. Neither listing nor
`show` opens workers, hashes source or backup contents, creates logs/locks, or repairs
journals. Saved `running` and failed states remain historical evidence, not claims
of liveness, current damage or artifact integrity.

`dataset recovery show <full-id>` selects an exact path-and-metadata identity.
Removal IDs also bind the dependent plan. Selection is rechecked before returning
commands; shortened IDs, stale records and changed plans reject. Shell examples
preserve spaces, Unicode and alternate application homes, with structured argument
arrays and environment settings available in JSON.

Removal actions reuse the existing preview and explicit restoration commands with
`--expected-sha256` and `--expected-plan-sha256`. The selected receipt and plan are
checked before changes and reloaded under the source lock. Existing journal, backup,
source-image and no-clobber checks still govern restoration. Legacy receipts do not
gain missing image evidence from browsing. Invalid selected previews return locally
without creating error logs, captions, locks or operation reports.

Collision actions deliberately offer the registered source-wide tf001 preview;
they do not imply selected-receipt execution, filename undo or automatic assignment
of ambiguous captions. Package actions inspect the current installation through
`trainime doctor --dryrun`, never execute a historical wheel or installation target.
Restoration receipts point back to the original removal and are not an undo action.
QOL18's original NF10 cross-reference is retained as historical wording; NF10 is the
separate review-history viewer and is not delivered by this receipt browser.

Both installed and module launchers route navigation before optional UI/native
imports. Diagnosis distinguishes recovery history from current package health;
unreadable history is a separate warning. Removal and collision summaries print
copyable navigation back to their recorded home and source. The four-choice
Trainime Home menu and existing repair dispatch remain unchanged.

### Verification

- Full final-source suite: **684 passed, 8 skipped**, zero
  failures or errors. Skips and exact command timing remain in the qualification
  receipt; platform skips do not qualify unavailable filesystem behavior.
- Isolated installed 0.9.0 package: **70 command checks**;
  **66 executable/resource payload files** match the
  source, wheel, source archive and isolated installation. This is installed
  generated-fixture evidence, not qualification of the user's normal installation.
- Recovery journeys exercise real generated removal/restore receipts, selected
  receipt and plan guards, source-wide collision preview and retained ambiguous
  captions, current-installation package guidance, offline mixed history and
  malformed peers. Missing UI, image, lock and native dependencies do not prevent
  read-only navigation. Previews and rejected selections preserve fixture bytes.
- Focused tests retain legacy, partial/interrupted, conflict, traversal/link,
  metadata-change and error-path cases. Browser reads do not substitute for explicit
  restoration verification or independent source-preservation checks.

The initial CLI development test's Unicode fixture failure is retained in
`.cache/recovery-cli-090-tests-initial.xml`; its fixture was corrected and the final
suite supersedes that development result. Earlier focused passes are supporting
evidence, not relabeled as full final-source qualification. Historical receipts and
earlier 0.6/0.7/0.8 evidence remain intact.

### Workflow handoff and limits

QOL18 is complete. CF17's preparation inspection and recovery receipt navigation
are delivered; its live inference-cache progress remainder remains queued. No
automatic cleanup, collision undo, new model inference, GPU qualification, hosted
CI run, global installation change, commit or push is claimed. All repairs in the
new execution checks target generated fixtures; no actual user collection repair
or new human judgment is performed by this batch.

The next required PLAN acceptance remains CF07/M4 human review, followed by CF08/M5
dataset acceptance and CF10/M6 user conclusion. Existing assistant judgments remain
assistant evidence. Further candidates retain their source IDs and scheduling
conditions in SHELVED; follow its TODO promotion handoff while PLAN stays open.

<a id="collection-navigation-recovery-080"></a>

## Saved collections, exact selection and recovery inspection — 0.8.0, 2026-11-09

The user-directed operational batch completes **NF07** and **QOL14** for explicitly
registered preparation collections and delivers the scheduled **CF17** preparation
recovery portion. Human acceptance remains independently recorded in M4–M6. Broader
repair browsing and live inference-cache inspection were not silently included.
The [qualification receipt](../.cache/collection-recovery-20261109/result.json)
links source identity, actual collection checks, test/build evidence and limits.
See [collection commands](COLLECTIONS.md) and [recovery](RECOVERY.md).

### Original promoted TODO tasks — completed

### Active continuation — saved collections and actionable recovery

<!-- WORKFLOW_TASK_GROUP: collection-recovery; SOURCES: NF07,QOL14,CF17 -->

The user authorizes the next directory-to-dataset usability/recovery batch while
human acceptance stays separate. PLAN's operational addendum permits this work.

- [x] Deliver NF07's local catalog of explicitly registered preparation workspaces:
  persist stable collection identity and optional names, list only registered
  roots, and expose current reviews, jobs, run/export/receipt metadata with errors
  isolated per entry. Listing must be read-only and work with source images offline.
- [x] Complete QOL14 selection by collection and exact job/run identity, with
  source/stage/status/date filters and usable commands. Detect stale selections,
  reject ambiguous names and never silently choose another collection or job.
- [x] Complete bounded CF17 preparation recovery visibility: show ordered stage
  state, retained current/prior attempts and pending outputs; distinguish verified
  reuse, retry, review refresh and manual artifact inspection. Fix deterministic
  retry loops and preserve every retained artifact. Publication inspection must
  not instantiate recovery workers or mutate their journals.
- [x] Verify generated failure/recovery journeys, multi-collection isolation,
  offline/read-only listing, stale selection rejection and installed commands;
  reconcile this batch into COMPLETED and retain the existing human acceptance.

### Delivered behavior

CLI preparation remembers a validated workspace, including a retained interrupted
job, without changing its preparation outcome if registration fails. Preview never
registers anything. `dataset collections` lists only explicit registrations;
`collections add <workspace> --name artwork` names an older workspace. Registration
uses stable workspace/source identity, an atomic locked registry and unique names.
Unregistering removes only the navigation entry, preserving all application data.

`collections show` presents compact job history and guarded continuation commands.
`dataset runs --collection artwork` filters by source-bound collection, stage,
recorded status and inclusive UTC dates. Exact record IDs bind canonical artifact
path and metadata checksum, with the source checked against the selected collection.
Malformed/missing records are isolated rather than hiding valid peers. Current
review revision is separate from snapshot revision; trainer receipts are associated
with exact export metadata/manifest identities, and stale same-path receipts remain
distinct. Listing works while original images are offline and never instantiates
reviewer/publication workers, scans source image trees or repairs journals.

`collections review` verifies the chosen QA record, source, payloads and compatible
configuration/write roots before opening the existing loopback reviewer. Generated
commands carry exact identities and shell quoting. Metadata-only listing and saved
status remain distinct from artifact verification, process liveness and human
acceptance. The four-choice Trainime Home menu is unchanged.

`dataset status` now shows ordered stages, failed/uncheckpointed work, current and
superseded attempt paths, pending outputs and per-stage integrity. `--verify`
retains healthy checks when another stage is invalid. Verified partial score vectors
are described as retained evidence; runtime cache reuse is checked during resume.
Similarity artifact checks use frozen inputs without requiring the original source.
Resume retains its separate live-source checks.

`status --job <id>` inspects a historical job without rebinding the workspace.
`resume --job <id>` checks that the exact job is still current under the workspace
lock; named collections additionally recheck source identity there. Ambiguous or
malformed published candidates require inspection rather than repeated retries.
Failure replies preserve the original error, exit status, saved stages and usable
commands even if logging, registry storage or the registry module is unavailable.
Cancellation still exits 130; catalog failure does not invalidate a completed export.

### Verification

- Full frozen-source suite: **630 passed, 7 skipped**, zero failures/errors.
  Platform skips remain explicit. Ruff lint/format and diff checks pass.
- Isolated installed 0.8.0 package: **59 command checks**,
  with **64 source/wheel/installed payload files** matched. The installed loopback
  reviewer handoff serves the selected fixture QA through the new command, with
  HTTP checks and controlled shutdown. These checks are not human usability acceptance.
- Generated recovery cases cover interrupted publication before/after checkpoint,
  ambiguous/malformed outputs, partial tagging evidence, source drift, stale job
  selection, historical inspection, corrupted checkpoints, unavailable logging and
  registry, cancellation, linked/traversing paths and offline read-only behavior.
- Actual selected collection: seven CLI navigation/status commands using an isolated registry find
  **3 jobs and 33 source-bound runs**, no catalog errors, review revision **109** and
  the exact corrected **62-image QA** record. Current and historical jobs both pass
  full artifact verification for **355 pairs**. The current export has one exactly
  bound existing pinned trainer receipt. No new trainer execution is claimed.
- All **13 protected artifact/review records**, the current binding and all **399
  original files / 564,441,065 bytes** remain unchanged. Hashing source files was a
  separate preservation check; catalog commands themselves do not scan originals.
  The 512 and earlier 400 assistant judgments and their histories are untouched.

Retained unsuccessful attempts are distinguished from qualification: two development
tests hit the executable-identity guard during concurrent source edits, and their
summaries/per-file drift proof remain. An initial full run was deliberately stopped
after independent review found unavailable error logging could hide recovery output;
the fix and regressions precede the final passing suite. A navigation harness's
incorrect `qa.json` assumption was corrected to the public QA reader, with its
failure retained. No application test was weakened to hide these outcomes.

### Workflow handoff and limits

NF07/QOL14 are complete for registered preparation workspaces. CF17's scheduled
preparation inspection is complete; its broader recovery candidates remain queued
with this partial-delivery evidence. QOL18's standalone removal/collision receipt
browser is still a separate proposal. No automatic cleanup, new caption inference,
human judgment, global installation, hosted CI execution, commit or push occurred.

The next required PLAN acceptance remains M4 human review, followed by M5/M6 dataset
acceptance. Optional source proposals retain their original IDs and conditions.
Keep using the SHELVED → TODO → COMPLETED handoff; no new IDENTIFIED cycle begins.

<a id="representative-assistant-review-070"></a>

## Representative assistant review and verified correction comparison — 0.7.0, 2026-11-09

The authorized representative continuation is complete. Source IDs: **NF05,
CF04, CF05, CF06, NF02, CF07, CF08, CF10 and NF06**. M3 measurement/comparison and
diagnostic threshold fitting close for the explicitly authorized assistant scope;
no fitted threshold or quality winner is adopted. M4–M6 human dataset acceptance
remains open. The original M3 findings require measured review, not a newly invented
human-label gate; the existing M4/M6 human conclusion is preserved.

The [review record](../data/reviews/representative/20261109/full-source/REVIEW.md)
contains the sampling method, observations and limits. The
[qualification receipt](../.cache/representative-review-20261109/result.json)
links exact artifacts, tests and retained attempts.

### Completed continuation tasks

### Active continuation — representative assistant review

<!-- WORKFLOW_TASK_GROUP: representative-assistant-review; SOURCES: NF05,CF04,CF05,CF06,CF07,CF08,CF10 -->

The user explicitly authorizes representative image/caption review as assistant
judgments. Preserve that attribution throughout sampling, assessments, corrections
and evaluation; it supplies no human acceptance conclusion.

- [x] Complete NF05 probability-sampling support and freeze a model-independent
  sample of all readable source content, including training-excluded images.
  Record the complete frame, separate selection/partition seeds, exact inclusion
  probability, aliases, verified grouping and earlier-review overlap before
  inspecting images or predictions. Preserve the earlier prepared-only draft.
- [x] Review original images for critical-label presence, then inspect effective
  training captions against their derivatives. Record every judgment and rationale
  as assistant evidence; preserve ambiguity and the original review history.
- [x] Complete the CF07 assessment attribution gap: persist reviewer kind, keep
  assistant/legacy judgments distinct from human acceptance, and support explicit
  pilot membership in QA so label and caption reviews share the frozen population.
- [x] Evaluate saved model scores on the reviewed population with group-disjoint
  partitions, assess caption/subset policy, save justified corrections, and publish
  verified updated QA/export/import evidence without adopting unsupported thresholds.
- [x] Reconcile this evidence with M3–M6 and promote the next necessary SHELVED
  source task from actual review findings before implementing it.

### Active enabler — verified snapshot comparison

<!-- WORKFLOW_TASK_GROUP: representative-correction-diff; SOURCES: NF06 -->

The representative review found caption errors, differently captioned exact aliases
and related families needing regrouping. NF06 is promoted to make the resulting
training-input changes inspectable before accepting the corrected export.

- [x] Add a reusable CLI/API comparison of verified group or export snapshots,
  retaining occurrence and content identities, added/removed members, caption and
  annotation changes, group merges/splits and exported split moves. Reject
  incompatible sources and tampered inputs; report unavailable group-caption or
  split information explicitly rather than inferring it.
- [x] Verify meaningful same/different/tampered snapshot cases and use the command
  on this review's original and corrected exports. Preserve both immutable inputs.

### Completed original milestone tasks

Original task bodies are retained below. Their earlier evidence descriptions
describe the starting state; the measured 0.7.0 evidence follows. Completion
of review tasks here means assistant review, not human acceptance.

#### M3 — representative measurement and diagnostic calibration

- [x] Expand per-label precision/recall, composition-error and actual anime-caption
  review to a representative sample across the selected collection. Current label
  evidence covers five images with 20 labels and 24 disagreement-selected images
  with 8 labels; both samples are diagnostic, not representative.
- [x] Calibrate thresholds from reviewed evidence and check them on held-out images.

#### M4 — assistant caption and policy review

- [x] Review nonempty pilot captions against their images and correct inaccurate
  or missing critical labels.
- [x] Assess configured subset rules, composition/conflict findings and caption
  policy for suitability on the representative pilot.
- [x] Verify the corrected pilot retains manual overrides and makes disagreements,
  exclusions and accepted subset decisions visible.

#### M5 — corrected publication and actual import

- [x] Publish an export from the representative reviewed M2–M4 inputs and verify
  membership, nonempty captions, unique filenames and absence of group/byte leakage
  or unresolved blocking decisions.
- [x] Run the pinned trainer import on that export and check actual caption,
  repeat and bucket behavior; retain its export-bound receipt.

### Preserved original task wording and disposition

The earlier root TODO also used the exact task bodies below. Their later evidence
was retained in prose and expanded task lists; this restores the original wording
without enlarging the recorded qualification.

Completed at the [bounded M2 checkpoint](#m2-selected-pilot-similarity-evaluation):

- [x] Select a representative local pilot and review positive/negative anime artwork pairs, including known related variants outside the proposal radius.
- [x] Evaluate saved judgments to calibrate the pHash threshold and measure false-match/missed-match behavior; verify that unique variants are preserved.
- [x] Measure similarity time, disk use and throughput at the intended collection size, retaining the input identities, settings and results.

Completed as bounded assistant measurement here and pinned CPU execution in the
[same-pilot comparison](#m3-same-pilot-wd-model-comparison):

- [x] Measure per-label precision/recall, composition errors and actual anime caption accuracy on the selected collection.
- [x] Measure tagging throughput and memory use on that collection.
- [x] Qualify other selectable WD weights before making local quality claims for them; published benchmarks are not collection acceptance.

These results concern the selected mixed collection, eight measured labels, actual
caption observations and the three pinned CPU model runs. They do not establish
general caption accuracy, a model winner or physical GPU execution. The original
conditional physical-CUDA task is preserved in TODO and remains untriggered.

### Sampling, judgments and calibration

NF05 now supports a reproducible hash-ranked probability sample of the entire
verified source-content frame. It records all aliases, an exact inclusion fraction,
selection and partition seeds, frame checksum and separately verified grouping.
Reading replays the draw; refreshing preserves the frame, membership and judgment
history while updating group partitions. Training exclusion does not remove an
original from this sampling population. Explicit QA membership and its reason
survive reviewer publication; missing/excluded selected members fail rather than
silently redrawing.

The final frame contains **381 unique images / 396 source occurrences**. A frozen
64-content draw has 68 aliases and inclusion probability **64/381**. Selection seed
is `20261110`; partition seed is `20261011`. A prepared-only 354-content draft was
superseded before any visual/prediction review and retained. Ten selected contents
overlap the previous 50-image pilot; other prior diagnostic/caption exposure is not
exhaustively catalogued. This is representative sampling of this selected mixed
collection, not proof of general model accuracy or a pristine unseen holdout.

All **512 judgments** are explicitly assistant: **140 present, 317 absent and
55 uncertain**, across eight critical labels. Original images were inspected
before their scores/captions. The original 50-image/400-judgment history and its
two audit revisions remain unchanged. Four reviewed family links yield 53 sampled
groups, 46 calibration images and 18 held-out images. Uncertainty is excluded from
confusion/fitting counts; human-only evaluation excludes all 512 assistant entries.

Three saved CPU model runs are evaluated on identical membership. All saved general
baselines are 0.35, including EVA02; this is a common-cutoff comparison. Fitted
held-out `solo` F1 regresses 0.857→0.769 for SwinV2 and 0.800→0.769 for EVA02;
ViT-Large `gloves` regresses 1.000→0.800. There is only one held-out positive for
`from_behind` and two for `gloves`. No configuration threshold changes follow.
Per-label precision, recall, denominators and proposed cutoffs remain in the
immutable evaluation and review summary.

### Caption corrections and attribution

The 64 selected originals correspond to **62 exported occurrences / 61 unique
contents**. Three excluded-only originals remain not applicable, without replacement.
All 62 effective captions were checked against the actual derivatives; exact byte
or decoded-pixel equivalence connects unchanged derivatives to inspected originals.
The first assessment records 16 accepted and 46 needing changes. These include
unsupported specificity and missing useful content, not 46 hallucinations.

Saved **46 caption overrides**, four related-family links and two explicit
previously automatic exact-alias exclusions through existing review APIs. The
collection review revision advances 57→109; all nine older overrides and history
prefixes remain. The final export retains 54 overrides; the remaining saved override
belongs to an excluded tiny image. Generic empty trigger/forced phrases/subset
rules remain appropriate to this mixed collection; no anime-only profile or human
semantic subset was invented. Original source membership and all **399 file bytes
and sizes** are unchanged.

CF07 now requires explicit reviewer kind on new assessment saves. Legacy missing
kinds remain unknown; reviewer display names never imply attribution. Human
acceptance requires every pilot member and the conclusion to be accepted by a
human. The corrected report has **62/62 assistant-accepted captions**, an explicitly
assistant conclusion and `human_accepted=false`, at assessment revision 63. Original
needs-changes assessment remains bound to the original report. Critical-label truth
is stored separately in the 512-entry workspace, not inferred from caption checks.

### Corrected export and NF06 comparison

The 0.7.0 preparation job completes all seven stages in **131.17 seconds**, reusing
saved model vectors. Verified resume takes **5.88 seconds** and reuses all stages.
The corrected export contains **355 pairs / 354 unique contents**, with 337 train
and 18 validation occurrences. It retains 289 export groups and 41 explained
exclusions. Pinned Kohya `sd-scripts` v0.12.3 at
`cb70b96858477e716a2096292ab8aab433277f38` imports all 355 pairs, checking actual
captions, repeats, buckets and CPU tensors in **18.69 seconds**. This does not run
tokenization, training steps or GPU qualification.

NF06 compares verified group/group or export/export snapshots without scanning
the original directory. It separates caption text from provenance changes,
membership, aliases, annotations, decisions, group merges/splits, exported media
and split moves. Incompatible/tampered inputs and unsafe output roots fail. A
published receipt captures normalized records and can replay without parent inputs.
See [snapshot comparison commands](SNAPSHOT-COMPARISON.md).

The actual old/new export comparison records **46 text edits**, 46 corresponding
provenance changes and two family-merge events (293→289 groups). There are **zero
added/removed contents, changed image bytes, alias changes or train/validation
moves**. Both immutable exports remain. The corresponding full group comparison
records all 396 occurrences and the two saved exclusion decisions separately.

### Verification and retained attempts

- Full suite: **559 passed, 5 skipped** in 325.68 seconds using a fresh Python cache.
  Ruff lint and format checks pass. The skips retain their existing platform/data
  prerequisites; they are not counted as passes.
- Isolated 0.7.0 wheel: **48 command checks**, with all **61 package payload files**
  matching source, wheel, installed package and source archive. No global installation
  or hosted CI execution is claimed. Exact package hashes are in the receipt.
- Rendered attribution fixture: five workflow groups, eight screenshots, no browser
  errors or overflow, 63 protected files unchanged and legacy history preserved.
  New assistant image/conclusion saves remain nonhuman; no real human interaction
  is inferred from browser automation.
- Retained unsuccessful attempts: the original `uv` pytest launcher could not
  canonicalize its script path. A direct run then exposed stale Python bytecode
  referring to the prior checkout, causing the traceback-source assertion to fail.
  The focused check and complete fresh-cache run pass. These attempts remain in
  the qualification folder; no test was weakened to make them pass.

Implementation payload SHA-256:
`e42c874c65af6c91bc19f68618794d516dd1b611cc283687d2a5db3adadd41be`.

### Handoff

NF05 and NF06 source delivery and bounded M3 CF04/CF05/CF06/NF02 measurement are
complete. The next required task is the existing **M4 human assessment** on the
corrected report, followed by M5 dataset acceptance and the M6 human conclusion.
Assistant sampling, correction, publication and import portions are already done;
do not repeat them or fabricate human attribution. Conditional backends, profiles,
performance work and optional queue proposals retain their stated prerequisites.
The PLAN remains open; no new IDENTIFIED cycle is started.

<a id="directory-preparation-060"></a>

## Directory preparation, recovery and portable ingestion — 0.6.0, 2026-11-09

The authorized product phase in [PLAN](PLAN.md#directory-preparation-product-phase--authorized-2026-11-09)
is delivered. Source IDs: **DP01, DP02, NF05, QOL02, QOL03, NF08, SC17, SC18,
SC19, TM14, QOL11 and TM20**; bounded caption and collection support also advances
CF07–CF10. The [qualification receipt](../.cache/directory-preparation-20261109/result.json)
links the exact artifacts, tests, build and limits. The PLAN remains open for
representative and human collection acceptance. CI configuration is delivered;
hosted CI execution is not claimed.

### Completed operational TODO tasks

- [x] Deliver a source-preserving `dataset prepare` workflow with useful defaults,
  a durable job record, verified stage reuse, preview, status, resume and failure
  recovery. Distinguish structural preparation from human quality acceptance.
- [x] Publish portable indexed metadata with new verified exports and expose
  checked catalog queries, retaining compatibility with historical exports.
- [x] Correct literal caption phrases invalidated by deterministic image conversion,
  retaining original caption evidence and replayable derivative adjustments.
- [x] Add explicit pilot membership and a local image-first critical-label reviewer
  with atomic saves, optional model comparison and clear reviewer attribution.
- [x] Persist reviewer publication stages and failed attempts, recover verified
  output after restart and expose completed outputs and retry through the existing
  Publish panel (TM14/QOL11).
- [x] Repair all packaged runtime resources, restore backed-up captions without
  overwriting newer work, and add repeatable isolated-wheel/CI verification.
- [x] Complete SC17's shared executable provenance: bind new stage receipts,
  including QA, catalog builds and trainer checks, to the same versioned package
  payload identity used by durable preparation/publication jobs. Preserve legacy
  readers and verify identity parity across source and installed artifacts.
- [x] Exercise the assembled pipeline, interruption/retry, source preservation,
  catalog portability, rendered review UI and pinned trainer import; retain measured
  evidence and reconcile the active workflow documents.

Completed M6 execution tasks, preserving their original bodies:

- [x] Process the explicitly selected collection and record real-image readability,
  size distribution, caption collisions and duplicate rate.
- [x] Reconcile final intake, review, snapshot, tagging, split and export counts
  and identities; resolve unexplained discrepancies.
- [x] Record actual batch processing time and disk measurements with their scope
  and unavailable measurements stated.

Completed interface/package tasks for this delivery:

- [x] Complete rendered-layout acceptance for reviewer panels whose recorded
  milestone checks lacked visual evidence; keep functional browser checks separate
  from visual and human usability acceptance.
- [x] Requalify the installed command when delivering later source changes through
  an installation; technical-pipeline checks do not automatically qualify that build.

### Delivered behavior

`dataset prepare <directory>` composes intake, similarity, pinned local tagging,
policy decisions, export and QA without a repository configuration. Preview is
read-only and offline. Durable jobs retain settings, input/output identities,
implementation fingerprints, attempts and errors. Resume verifies source bytes and
stage artifacts, recovers its own published output after checkpoint interruption,
and reuses completed stages. JSON failures retain the current error separately
from saved-job status and print exact recovery commands; changed requested options
survive the suggested `--new` command. See [PREPARATION](PREPARATION.md).

The `conservative-v1` policy records automatic decisions without changing the
review store. It preserves explicit decisions, captions and annotations; keeps
unresolved similarity candidates together for splitting; and never declares their
semantic relationship established. Exact-byte aliases are excluded from training
only when captions agree and explicit review intent does not require preservation.
Technically unusable undecided images remain in the source and provenance. The
strict reviewed-export path keeps its original requirements.

New exports contain an indexed SQLite catalog and split-local ImageFolder metadata
with relative paths, complete occurrence records, separate model observations and
review annotations. Historical exports still verify and can receive a separate
metadata-only index. Checked queries do not imply fresh media verification.
[DATASET-CATALOG](DATASET-CATALOG.md) documents the contract.

An opaque RGB derivative removes only the exact comma-separated phrase
`transparent background`; original effective captions and versioned adjustments
remain frozen evidence. Source sidecars and saved overrides stay unchanged. No
background label is inferred, and captions emptied by the adjustment require
correction. The final collection has ten such replayable derivative adjustments.

Explicit pilot membership and the label reviewer support image-first atomic
judgments, reviewer identity/kind, notes, saved-model comparison and durable
comparison-exposure history. Original values and attribution are never rewritten
as human judgments. The two real 50-image workspaces still have revision 402,
400 assistant judgments (66 present, 284 absent, 50 uncertain), zero unreviewed
cells and unchanged judgment history; the original matches its frozen parent copy.

[Publication](PUBLICATION.md) now persists requests, settings, outputs and attempts
across restart, uses process locking and adopts only verified outputs from its own
attempt. The Publish form restores captured custom settings after reload while
polling and explicit refresh preserve unsaved edits. Recovery tests terminate real
processes after each published stage and before checkpointing.

[Recovery](RECOVERY.md) covers all owned packaged resources and a receipt-bound
caption restore command. Restore verifies image/backup identities, creates only
missing captions, retains newer files/conflicts and supports preview and retry.
Legacy receipts without image identities remain explicitly unverifiable. Shared
SC17 identity now covers new stage receipts including QA, label workspaces,
evaluations, standalone catalogs and trainer checks; historical readers remain
compatible. Tracked wheel smoke and pinned Windows/Linux CI configuration complete
the delivery tooling; the normal user installation was not modified.
SC18 is complete for CLI/package smoke; browser harness promotion remains an
optional queued portion, with the actual rendered evidence retained under `.cache`.

### Selected collection execution and trainer qualification

The [final job](../data/prepared/pilot-dir/jobs/20261110T004108922422Z-18e52db6) uses the existing source `pilot-dir`, model
and score caches, and review store. Every stage records implementation identity
`d26db4a6071c01225d59d3a96054ce1ecb244f9409d5bc28eb03acec77d653ea`,
which matches the separately installed wheel. Earlier jobs and candidate builds
are retained as history; the final artifacts supersede their qualification scope.

| Measure | Final result |
| --- | --- |
| Source preservation/readability | All 399 original files unchanged; 396/396 images decoded; 3 unsupported files recorded. |
| Image bytes and duplicates | 424,014,533 source image bytes; 381 unique hashes; 15 duplicate occurrences (3.79%). |
| Geometry | Short side 1–4000 px, median 947.5; long side 2–4000 px, median 1536. Full quartiles/aspect distribution are recorded. |
| Caption collisions | Two ambiguous same-stem image occurrences flagged; no matched existing sidecars. Unique exported occurrence filenames avoid collisions. |
| Tagging | All 381 unique vectors reused from the verified SwinV2 cache; 15 alias reuses; zero new inference. |
| Policy | 396 occurrences, 318 groups, 46 provisional split constraints; 41 exclusions: 27 below the trainer bucket minimum and 14 equivalent byte/caption aliases. |
| Export | 355 pairs in 293 groups: 337 train, 18 validation. One intentional exact-byte alias remains with its evidence. No group/byte leakage or missing captions. |
| Saved corrections | Review revision 57 and all nine overrides retained; eight included, one technically too narrow for the trainer bucket. |
| Derivatives | 258 opaque/orientation/format conversions and 97 byte copies; ten caption adjustments verified. |
| Export payload | 729 files, 372,859,089 bytes, including frozen provenance and metadata. |
| End-to-end preparation | 130.491 s; cached-model execution, including verification, concurrent with local tests. |
| Verified resume | 4.447 s; same job and all seven stage outputs reused. |
| Pinned CPU import | 28.578 s; all 355 captions/repeats/buckets and decoded finite tensors checked. |

[Collection measurements](../.cache/directory-preparation-20261109/collection-measurements.json)
and per-stage receipts retain the measured scope. Peak process memory and temporary
storage were not sampled. These are observed timings for this selected collection,
not cold-inference, larger-production-scale or comparative performance claims.

The [export](../data/prepared/pilot-dir/jobs/20261110T004108922422Z-18e52db6/attempts/export-47aa70bf6938/exports/20261110T004216165960Z-export-5398132e) and
[QA report](../data/prepared/pilot-dir/jobs/20261110T004108922422Z-18e52db6/attempts/qa-ff0d6b998767/runs/20261110T004316045743Z-qa-4a216b09/report.html) are immutable. Independent verification
reconciled original hashes, every exclusion, override, constraint and model/annotation
separation, and decoded every exported image. A relocated copy was fully verified.
Actual Hugging Face Datasets 4.8.5 loaded and decoded all 355 images offline, outside
the checkout, with an audit hook blocking reads from the original source and export.
The [independent receipts](../.cache/directory-preparation-20261109/independent/)
retain exact evidence and commands; both old and final runs remain distinguishable.

The [actual trainer receipt](../data/prepared/pilot-dir/runs/20261110T004414377489Z-trainer-e8c32044/result.json)
is bound to the final export. Pinned sd-scripts v0.12.3 at
`cb70b96858477e716a2096292ab8aab433277f38` accepted 337 train and 18 validation images,
with repeats=1, matching captions and bucket tensors. The current receipt lookup
reports `passed`. No training step, target tokenization, CUDA qualification or
human acceptance was performed. Static export/QA metadata stays frozen; the live
reviewer's Training import view reads the separate receipt.

### Source, browser and installed-package verification

- Fresh complete source suite: **474 passed, 5 skipped**, zero failures/errors;
  [JUnit](../.cache/pytest-060-final.xml) and [log](../.cache/pytest-060-final.log).
  Four skips require Windows link privileges; one needs case-only filenames.
- Ruff lint/format and Git whitespace checks passed. Fault tests cover cancellation,
  malformed contracts, changed inputs/settings/builds, concurrent workers, foreign
  artifacts, failed publication, exact aliases and preserved explicit intent.
- The critical-label UI passed rendered desktop/narrow checks with saves, comparison,
  stale-form preservation, keyboard navigation and no overflow or page errors.
  [Receipt](../.cache/label-ui-render-final/browser-result.json): 68 protected fixture
  files unchanged. Existing reviewer image/assessment/pair/publication/trainer views
  passed [rendered checks](../.cache/reviewer-render-settings/browser-result.json),
  including custom-settings recovery and 28 protected fixture files unchanged.
  [Snapshot/accounting checks](../.cache/reviewer-snapshot-render/browser-result.json)
  add 18 inspected screenshots of group/export reports, reconciliation and resource
  tables, including desktop/narrow views and DPR=2/CSS zoom=125% emulation. All 83
  retained fixture files stayed unchanged; GET-only requests produced no page errors
  or document overflow. Browser emulation is not physical Windows display scaling.
- The [installed 0.6.0 qualification](../.cache/directory-preparation-20261109/package-qualification.json)
  passed **41 CLI commands** outside the checkout with all **58 payload files**
  matching wheel and source archive. It covers resource repair, caption restore,
  prepare/preview/verified resume, alpha-caption normalization, catalog relocation,
  full export verification and tamper rejection. The generated-fixture command
  journey took 24.90 s; isolated setup took 4.11 s, recorded separately.
- Wheel SHA256: `d0d6811fb9ab8d0dd7341526d6413bcaf349f5ed640f35b0a205997f4d1c7ee5`.
  [Wheel/source archive](../.cache/directory-preparation-20261109/dist/) and exact
  dependency constraints are retained. Hosted Windows/Linux CI has not run.

Earlier candidate receipts and interrupted development checks are preserved,
including the first uncorrected-alpha pilot job, the candidate wheel, the corrected
browser harness URL error, and tests rerun after concurrent source edits stopped.
They do not replace the final frozen-build evidence above.

### Remaining acceptance and queue disposition

This completes the authorized operational product phase and the selected-collection
execution/measurement tasks. M3/M4 representative label, caption and subset quality,
M5 acceptance based on those reviewed inputs, and M6's human conclusion remain open.
Assistant judgments, preparation-policy decisions and loader compatibility retain
their own attribution. No fitted threshold was automatically adopted. NF05's source
support is delivered; its representative membership acceptance remains active.
Conditional backends/platforms and unmeasured performance proposals remain in
SHELVED with their original IDs and conditions. They are not silently completed or
promoted. Do not start a new IDENTIFIED cycle while required PLAN acceptance is open.

<a id="m3-assistant-pilot-review-and-group-refresh"></a>

## M3 assistant pilot review and corrected group partitions — 2026-11-09

The user-authorized visual review covered all 50 frozen images and all eight raw
labels per image, independently of saved predictions, captions and evaluation-set
assignments. All **400 current judgments are attributed to assistants**: 66 present,
284 absent and 50 uncertain. There are no unreviewed label cells or human judgments.
The original [label workspace](../data/reviews/label-evaluations/20261109T194816515323Z-labels-b313e382)
retains revision 402 and its complete history. The first 400 revisions recorded
the observations; revision 401 changed one ambiguous segmented-hand `gloves`
judgment to uncertain, and revision 402 clarified a transparent-background note
without changing its absent value. Evidence:
[initial judgment receipt](../.cache/m3-assistant-review-20261109/judgment-receipt.json),
[consistency audit](../.cache/m3-assistant-review-20261109/audit-receipt.json) and
[alpha audit](../.cache/m3-assistant-review-20261109/audit-alpha-receipt.json).

Completed active-continuation checklist archived from TODO:

- [x] Record the visually reviewed related links and publish a new group snapshot,
  preserving every source image and existing review history.
- [x] Add NF05 support to refresh a label workspace against corrected groups while
  preserving the exact selected identities, vocabulary and attributed judgments.
  Publish new immutable lineage evidence; retain the original QA viewing context,
  and reject changed/missing/excluded members rather than narrowing the population.
- [x] Verify group-disjoint repartitioning, unchanged judgment provenance, stale
  revision rejection and input/output preservation, then run all three saved models
  with explicit assistant-diagnostic inclusion and retain human-only coverage too.

Visual review found that five selected animation frames belonged to one related
family but crossed the original calibration/held-out boundary. Four attributed
related links were saved through the existing review API. The new
[group snapshot](../data/runs/20261109T200411043412Z-59ad428b) at review revision 48
contains all 396 images in 351 groups, with zero conflicts or similarity errors.
It retains 46 unresolved candidate pairs and 396 unreviewed inclusion decisions;
no image was deleted or excluded. The
[group-correction receipt](../.cache/m3-assistant-review-20261109/group-correction.json)
records the visual reasons, original split assignments and new family group.

NF05's generic `dataset label-refresh` creates a new workspace against a complete
corrected group snapshot. It retains exactly the selected paths/hashes, vocabulary,
judgment values, notes, timestamps, reviewer attribution and history. New group
membership includes transitive relationships through unselected images; the same
seed and fraction determine the new partition without optimizing for scores or
label coverage. Missing, changed or excluded selected occurrences, source mismatch,
stale revisions and output overlap with input lineage are rejected. Immutable
parent metadata, selection and judgment snapshots identify the carry-forward;
later reads recheck their hashes. Evaluation archives retain those immediate-parent
snapshots even if the original workspaces become unavailable. This is immediate
parent evidence, not recursive copying of every ancestral artifact. See the
[refresh contract](LABEL-EVALUATION.md#refresh-corrected-groups-without-changing-the-pilot).

The [refreshed workspace](../data/reviews/label-evaluations/20261109T201049106615Z-labels-066af8f6)
preserves all 50 selected identities and revision 402's judgments/history. It has
46 known groups, **35 calibration and 15 held-out images**; the corrected animation
family is wholly in calibration. The original QA remains historical viewing and
selection context. Both workspaces retain the model-dependent selection reason;
the refresh is a reuse of reviewed data, not a fresh independent validation set.
All 399 source paths retained their bytes and the parent judgments were preserved.
The [refresh/evaluation receipt](../.cache/m3-assistant-review-20261109/refresh-evaluation-receipt.json)
also retains the initial preservation-helper error and successful final recheck.

The [three-model diagnostic evaluation](../data/runs/20261109T201050685494Z-label-evaluation-b786e6ff)
uses saved SwinV2, EVA02-Large and ViT-Large scores with explicit assistant inclusion.
All saved baseline cutoffs are **0.35, including EVA02**; this is not a native-default
threshold comparison. Threshold fitting uses only calibration judgments; the 50
uncertain cells stay outside confusion counts and fitting. The separate
[human-only evaluation](../data/runs/20261109T201054751281Z-label-evaluation-e0cd1ef4)
excludes all 400 assistant judgments and supplies no accuracy or fitting evidence.
No thresholds or configuration were adopted or changed.

The held-out labels contain only two to four positive observations each, except
`from_behind`, which has **zero positives**, 13 negatives and two uncertain cases.
Its recall/F1 is therefore unestablished. On this small diagnostic population,
SwinV2's fitted thresholds leave held-out F1 unchanged. EVA02 improves four labels;
ViT-Large improves four but regresses `solo` F1 from **0.750 to 0.667**. These outcomes
do not establish a preferred model or generalizable threshold gains. Full per-label
counts, precision/recall, errors and fitted cutoffs are retained in the evaluation.

The [coverage audit](../.cache/m3-assistant-review-20261109/review-coverage.json)
records 24 UI screenshots, ten anime artworks, four anime stills, four icons/logos,
and eight other mixed-domain images. This selection cannot establish representative
anime accuracy. Independent representative review, sufficiently supported held-out
labels, composition/caption acceptance and unresolved group review remain open.
NF05 is partially delivered; targeted-case authoring and representative membership
review remain queued. CF04/CF05/CF06/NF02 and PLAN acceptance remain active.

Verification: the 15 new refresh regressions cover unchanged identity/history,
transitive grouping outside the pilot, successor edits, stale revisions, source and
membership drift, protected output trees, inherited-evidence tampering, live-read
rechecks, archived evaluation provenance and CLI assistant exclusion. The full
suite records **317 passed, two skipped** (319 cases, zero failures or errors) in
[pytest.xml](../.cache/m3-assistant-review-20261109/pytest.xml). Existing skips are
Windows symlink privilege and distinct case-only filenames. Ruff lint and format
checks pass for 69 files; wheel and source distribution builds pass. Source and
package checks do not supply human dataset acceptance or qualify the user's normal
installed command. No new IDENTIFIED cycle began.

The [consolidated result](../.cache/m3-assistant-review-20261109/result.json)
links review, evaluation, caption, source-test, package and preservation evidence
with selected artifact digests for this continuation.

The [isolated wheel receipt](../.cache/m3-assistant-review-20261109/wheel-smoke.json)
verifies all 47 source-package files match the installed wheel, with imports from
its `site-packages` rather than the editable checkout. Installed `label-review`,
`label-refresh` and human-only `tag-evaluate` commands succeed, preserve all 400
attributed judgments/history, and exclude them from human-only accuracy and fitting.
All 1,192 protected input files remain unchanged, including the 399 pilot files.
The commands ran from the repository's evidence subdirectory with dependencies
reused through `PYTHONPATH`; this qualifies the isolated package path, not a fully
independent dependency installation or the normal user installation, which was
unchanged. The retained
[initial harness attempt](../.cache/m3-assistant-review-20261109/wheel-smoke-harness-attempt.json)
records a wrapper `KeyError` corrected before final qualification, not an application
failure.

<a id="m4-assistant-caption-corrections"></a>

## M4 assistant caption audit and retained corrections — 2026-11-09

The [verified caption audit](../.cache/m3-assistant-review-20261109/caption-audit-verified.json)
examined all 150 nonempty saved captions for the same 50 identities across SwinV2,
EVA02 and ViT-Large. The caption auditor visually checked 33 originals, including
all 18 artwork/still images, and identified 17 images with candidate corrections.
All three saved drafts use the common 0.35 general threshold; the audit does not
claim model-specific native-default evaluation. The original 400 label judgments
were created before model-output inspection and their values remain unchanged.

Nine high-confidence corrections to the selected SwinV2 baseline were saved through
`ReviewStore` as caption overrides, advancing collection review revision 48 to 57.
Assistant attribution appears in the correction reasons and separate audit; these
are not human acceptance decisions. The other eight candidates concern alternate
model drafts, not eight additional corrections to this baseline. The corrected
[group snapshot](../data/runs/20261109T201742962852Z-c2f6282a) retains all 396 images
in 351 groups. Pair and inclusion decisions were unchanged.

The new [QA report](../data/runs/20261109T201809926829Z-qa-f2c1df96/report.html)
includes all 396 snapshot members so the retained overrides are visible. It has
nine overrides and 387 draft captions, all nonempty, with zero source errors. Text,
hashes, reasons and raw-draft analysis survived publication. The original 50 label
identities and their groups match the refreshed label workspace; the 396-member
report is not a newly reviewed representative sample. All inclusion decisions
remain unreviewed, all splits unassigned, and 46 relation proposals unresolved.
QA's `labels_reviewed: 0` and `subset_reviewed: 0` describe collection annotation
decisions. The separate critical-label workspace still contains all 400 assistant
judgments; those observations have not been erased or converted into annotations.

The [correction receipt](../.cache/m3-assistant-review-20261109/caption-correction-receipt.json)
verifies preservation of all 399 source files, all three original score/draft runs,
both label workspaces and their revision-402 observations. No fitted threshold was
applied. Its initial preflight failure is retained: the first audit hashed stripped
caption text rather than raw files with trailing newlines. The helper stopped
before any mutation; the verified audit now distinguishes both hashes and checked
all 150 caption files before corrections proceeded. Original audit evidence remains.

This closes bounded assistant caption review/correction and override-retention
checks under CF07. It does not close the original M4 tasks: representative caption
accuracy, subset/rule suitability, inclusion/exclusion decisions and recorded human
judgments remain required. M5 accepted export/import and M6 collection acceptance
continue to depend on that work. No source change was needed for these corrections.

<a id="m3-reusable-label-evaluation"></a>

## M3 reusable critical-label evaluation — 2026-11-09

Delivered NF03/CF04/CF06 source support with NF02 model-comparison context and
partial NF05 frozen-membership support. The commands `dataset label-pilot`,
`label-review` and `tag-evaluate` implement the
[critical-label evaluation contract](LABEL-EVALUATION.md). NF03 source support is
complete; representative independent judgment and calibration acceptance remain
active under CF04/CF06. NF05 retains its targeted-case and representative-selection
remainder rather than being marked wholly complete.

Completed source tasks archived from TODO:

- [x] Record explicit present, absent and uncertain judgments for a chosen raw WD
  critical-label vocabulary independently of model predictions, captions and
  inclusion; retain whether each judgment came from a human or assistant reviewer.
- [x] Freeze the evaluated image identities and related-group membership from an
  explicitly verified QA pilot and its snapshot; record selection provenance and group-disjoint calibration
  and held-out membership so aliases or related variants cannot cross that boundary.
- [x] Evaluate saved model scores against those judgments, reporting per-label
  counts, denominators, excluded unknown/uncertain examples and separately scoped
  calibration/held-out results. Count exact-byte aliases once and preserve the
  production strict score-greater-than-cutoff semantics. Threshold fitting must use calibration only and
  must not apply proposed thresholds to configuration or captions.
- [x] Verify actual label semantics, identity mismatch rejection, group/alias leakage
  prevention and held-out isolation with focused regression checks; run the reusable
  path on existing pilot scores without presenting assistant judgments as human
  acceptance or changing the selected pilot's files.

The implementation retains revisioned, attributed judgment history, rejects stale
saves and mismatched identities, validates bounded score payloads, and publishes
immutable evidence snapshots. Human judgments alone are eligible by default;
assistant diagnostics require an explicit flag. Unknown/uncertain cases remain
outside confusion counts and fits. Known groups remain disjoint; unresolved
relationships can still hide leakage. Independent review corrected an output-path
guard so results cannot be published inside frozen input artifacts.

Real saved-score execution prepared
[workspace 20261109T194816515323Z-labels-b313e382](../data/reviews/label-evaluations/20261109T194816515323Z-labels-b313e382)
from the existing 50-image QA coverage sample. It has 50 unique images, 50 known
groups, 34 calibration and 16 held-out images, eight raw labels, and zero judgments
at revision 0. Its 400 image/label checks remain unreviewed; freezing the existing
model-dependent coverage sample does not make it representative. No earlier
assistant label checks were silently converted into independent truth.

Those counts describe the initial publication checkpoint. The later
[assistant review and corrected-group refresh](#m3-assistant-pilot-review-and-group-refresh)
records the completed 400 judgments and superseding diagnostic partitions while
preserving this original evidence.

The [three-model CLI evaluation](../data/runs/20261109T194817436682Z-label-evaluation-6751c673)
read saved SwinV2, EVA02 and ViT-Large scores successfully with no inference or
threshold fit/adoption. Evidence:
[verification.json](../.cache/m3-label-evaluation-20261109/verification.json).
All 399 selected pilot paths and the configuration file retained their bytes.
Zero judgments produce coverage gaps, not model-accuracy evidence.

The wheel and source distribution built successfully. An isolated wheel's console
entry point ran the same three-model evaluation from the evidence directory,
with its installed module path verified;
[its result](../data/runs/20261109T195004695463Z-label-evaluation-250890ba) and
[wheel-verification.json](../.cache/m3-label-evaluation-20261109/wheel-verification.json)
record exact source-package file parity. Dependencies were reused from the locked
project environment via `PYTHONPATH`. The normal user installation was unchanged;
this qualifies the isolated package/console path, not a complete installer run or
the user's installed command.

Verification includes 26 new evaluation cases and one assessment regression.
Ruff lint and format checks passed for 69 files. The initial full suite recorded
301 passed, two skipped and one failure caused by a traceback retaining an old
checkout path in compiled bytecode (`co_filename` under
`C:/Users/ryanf/github/_active/`). That run remains in
[pytest.xml](../.cache/m3-label-evaluation-20261109/pytest.xml). The qualification
rerun uses `PYTHONPYCACHEPREFIX=.cache/pyc-m3-label-final` and retains
[pytest-qualified.xml](../.cache/m3-label-evaluation-20261109/pytest-qualified.xml):
**302 passed, two skipped in 51.64 seconds**, with zero failures or errors. The
existing skips cover Windows symlink privilege (`WinError 1314`) and inability to
create distinct case-only filenames. The consolidated
[result.json](../.cache/m3-label-evaluation-20261109/result.json) links source,
package and final-suite evidence for this source-support checkpoint.

The next dependency is independent review of the frozen population and actual
labels, followed by held-out calibration evidence and representative caption
review. M3 acceptance, M4–M6 and PLAN remain open. No new IDENTIFIED cycle began.

<a id="onboarding-workflow-authority-review"></a>

## Onboarding workflow authority review — 2026-11-09

Completed the requested review of the current workflow documents before further
source development. The existing design has usable scope, preservation contracts,
milestone order and evidence boundaries; the main defect was contradictory routing
after the recorded M2 pilot work. Reconciled PLAN, SHELVED and TODO to the current
M3 batch, retaining IDENTIFIED as the dated findings record rather than starting a
new review cycle. Preserved prior completion evidence and annotated its scope.

Checked all 100 stable finding IDs in IDENTIFIED against SHELVED and validated the
five workflow documents' local links/anchors. All matched. Inspected the referenced
M2 group snapshot: 396 images, 355 groups, review revision 44, zero conflicts and
zero similarity errors; its 46 unresolved pairs and 396 unreviewed image decisions
remain explicit. Its completion is a bounded evaluation checkpoint, not full
collection or independent human acceptance.

Archived the already completed M3 execution checklist below. Scheduled reusable
critical-label evaluation under NF03/CF04/CF06, with NF02 comparison context and
NF05 frozen-membership support, before implementation. Representative independent
judgments, M4–M6 acceptance and final user review remain outstanding. This entry
closes onboarding's workflow-authority review only; it does not close PLAN.

Verification: document ID/link/anchor checks passed. No application behavior or
new model/dataset qualification is claimed by this document reconciliation.

<a id="m2-selected-pilot-similarity-evaluation"></a>

## M2 selected pilot similarity evaluation — 2026-11-09

Pilot supplied by the user: `C:\github\image_dataset_train\pilot-dir`.
Inventory [20261109T161301693210Z-5e3dd546](../data/runs/20261109T161301693210Z-5e3dd546)
recorded 399 files (396 images, 3 unsupported files) and 15 exact-byte duplicate
groups. Similarity run [20261109T161326172630Z-77e16a67](../data/runs/20261109T161326172630Z-77e16a67)
used 64-bit `phash64-padded-white-gray-v1` at radius 8 and hashed all 381 eligible
unique images in 17.962 seconds (21.2 images/second). It emitted 80 proposals with
zero errors. The two payload artifacts total 115,753 bytes; the complete run
directory totals 118,173 bytes. This measures the full selected 399-file pilot,
not a projection to a larger collection. A final recheck found all 399 manifest
paths present with matching SHA256 values; the pilot remained unchanged.

At review revision 44, the store contains 42 pair decisions: 41 scored
unique-content pairs and one exact-byte pair (excluded from pHash precision and
recall). The scored set covers 34 proposals and 7 manually linked comparisons;
all anime-artwork proposals were reviewed. The remaining 46 proposals are pairs
of dated screenshots or small skull/application icons. Calibration has 13 pairs
(11 related, 2 distinct); held-out has 28 (22 related, 6 distinct). Across all 41
scored pairs, radius 8 produces 27 true positives, 7 false positives, 6 false
negatives and 1 true negative: precision 0.794, recall 0.818, F1 0.806. The
calibration fit selects radius 6 (precision 1.0, recall 0.909 on calibration);
held-out at radius 6 has precision 0.813 and recall 0.591. Held-out at the
original radius 8 has precision and recall 0.773. The sample is curated and
imbalanced, with related pairs sharing some character families, so these metrics
describe this reviewed pilot sample rather than general collection accuracy. The
radius 6 versus radius 8 tradeoff does not justify changing the provisional default.

The sample includes six known related misses outside radius 8 at distances 10,
16, 18, 22 and 24, including alternate poses of the same green-beach, witch,
thermal-band and red-devil artwork families. Eight visually distinct comparisons
were marked distinct, including different outfits and characters that had nearby
pHashes. Exact-byte duplicates remain separate inventory evidence. The isolated
fixture under `.cache/m2-duplicate-probe/` confirmed that inventory finds an
exact-byte copy and pHash proposes a same-pixel re-encode at distance 0; its
center crop was distance 22 and missed at radius 8. Fixture steps and run IDs are
in its README.

Group snapshot [20261109T173157995920Z-d841bd18](../data/runs/20261109T173157995920Z-d841bd18)
retained all 396 images in 355 groups with zero conflicts and zero similarity
errors. All 8 reviewed distinct pairs remain in separate groups; no image was
discarded. The snapshot is not export-ready: 46 non-anime proposals and all
per-image inclusion decisions remain unreviewed.

The M2 pilot review, pHash evaluation and performance measurements are complete
at the selected pilot scope. They do not qualify a larger future collection.
Focused review tests previously passed (**8 passed**); `git diff --check` passes.

Onboarding clarification: this is the completed pilot evaluation checkpoint used
to proceed with M3 source work. The frozen review store has no reviewer-identity
field, so it does not prove independent human judgments. The unresolved proposals
and image decisions above remain export/collection acceptance dependencies.

<a id="m3-same-pilot-wd-model-comparison"></a>

## M3 same-pilot WD model comparison — 2026-11-09

Completed checklist archived from TODO during onboarding reconciliation:

- [x] Compare SwinV2 and EVA02 on the same reviewed pilot; qualify the alternate
  WD weights used in that comparison.
- [x] Measure CPU tagging throughput on the selected pilot for all three selectable
  WD models; see the same-pilot run table in COMPLETED.
- [x] Measure peak process working set for all three uncached full-pilot CPU runs;
  measurements and scope are recorded in COMPLETED.
- [x] Qualify the selected CPU provider for the three pilot runs; no CUDA provider
  was requested, so GPU-specific qualification was not triggered.
- [x] Run the remaining selectable WD weight, ViT-Large, on the same pilot and
  compare its common-threshold output; quality evidence remains diagnostic only.

The three selectable pinned WD models ran on the user's 399-file `pilot-dir` inventory
[20261109T161301693210Z-5e3dd546](../data/runs/20261109T161301693210Z-5e3dd546),
with the same 381 unique image hashes, 15 duplicate-score reuses, 10,861-label
vocabulary, WD preprocessing, batch size 4, Python 3.12.10, ONNX Runtime 1.31.0,
and `CPUExecutionProvider`. These uncached full inference runs provide the
resource/timing comparison:

| Model | Run | Pinned revision | ONNX SHA256 | Tag-stage time | Unique images/sec | Peak process WS | Payload |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| SwinV2 | [20261109T185259750503Z-tagging-b46fc209](../data/runs/20261109T185259750503Z-tagging-b46fc209) | `627aef95638667ddcaa3ac8ae625e88ea5b02f51` | `e6774bff34d43bd49f75a47db4ef217dce701c9847b546523eb85ff6dbba1db1` | 154.588 s | 2.46 | 1.70 GiB | 19,559,885 bytes |
| EVA02-Large | [20261109T185957405860Z-tagging-f5db34c7](../data/runs/20261109T185957405860Z-tagging-f5db34c7) | `b25b82a03f7282e41aa2f257a52c7583b710bd1c` | `9e768793060c7939b277ccb382783e8670e8a042d29d77aa736be0c8cc898bfc` | 401.942 s | 0.95 | 2.18 GiB | 20,184,773 bytes |
| ViT-Large | [20261109T190653977565Z-tagging-27a14562](../data/runs/20261109T190653977565Z-tagging-27a14562) | `ae469aa2e4706a3af08d3673cf73a11d1add314c` | `e4c8001b000a6c98f2db10794f7c406daa79873d071d6ca924330fa053fa1845` | 400.334 s | 0.95 | 2.38 GiB | 19,685,491 bytes |

EVA02 took 2.60 times as long as SwinV2; ViT-Large took 2.59 times as long.
Each run freshly inferred 381 unique images and reused 15 exact duplicate scores.
The recorded CPU provider had no fallback. Peak working set came from Windows'
process memory counters queried in the same Python inference process after each
run. These timings and peaks describe this machine and this pilot only.

The repeated runs' score checksums match all 381 per-image vectors from the
earlier quality runs for their respective models. The common-threshold recaptions
and visual assessments below therefore remain bound to identical raw scores.

Score-only recaptions at the shared general threshold 0.35
([SwinV2](../data/runs/20261109T175345589807Z-recaption-857d4896),
[EVA02](../data/runs/20261109T175403124455Z-recaption-528a1e9a)) cover the same
381 content hashes. Their mean per-image tag-set Jaccard is 0.505 (median 0.50);
none of the 381 tag sets is identical. EVA02 emits more tags on average (22.38
versus 16.01). Differences such as `gameplay_mechanics` (74 versus 13),
`upper_teeth_only` (66 versus 3), and `user_interface` (64 versus 15) show
substantial vocabulary/threshold disagreement, not a quality ranking. The
default thresholds differ by model, so this shared-threshold view is a controlled
disagreement comparison, not each model's production-default caption.

ViT-Large's common-threshold recaption
([run](../data/runs/20261109T183055444382Z-recaption-628a3a15)) averages 17.40
tags per unique image. Its mean tag-set Jaccard is 0.587 against SwinV2 (median
0.600; 6 identical sets) and 0.547 against EVA02 (median 0.545; no identical
sets). This confirms material model disagreement while qualifying the pinned
ViT-Large CPU execution path; it does not establish a quality ranking.

Six side-by-side sheets under `.cache/m3-caption-review/` show 24 selected anime
artwork examples with the lowest SwinV2/EVA02 tag-set agreement. Both models
usually identify the main subject and outfit; EVA02 is more verbose and often adds
narrower attributes. The sheets are disagreement-selected diagnostic material,
not a random sample or full caption acceptance pass.

Those 24 images were checked against an eight-label controlled vocabulary in all
three full-pilot QA reports. The image judgments and reviewer notes are retained
in each report's assessment record ([SwinV2](../data/runs/20261109T183940985952Z-qa-dde6d94b),
[EVA02](../data/runs/20261109T183940984951Z-qa-3e1aea16),
[ViT-Large](../data/runs/20261109T183211480029Z-qa-19cfb244)). Selected per-label
results are:

| Label | SwinV2 P/R (TP/FP/FN/TN) | EVA02 P/R (TP/FP/FN/TN) | ViT-Large P/R (TP/FP/FN/TN) |
| --- | --- | --- | --- |
| `boots` | 0.917 / 1.000 (11/1/0/12) | 0.917 / 1.000 (11/1/0/12) | 0.909 / 0.909 (10/1/1/12) |
| `from behind` | 0.857 / 0.857 (6/1/1/16) | 0.857 / 0.857 (6/1/1/16) | 0.857 / 0.857 (6/1/1/16) |
| `gloves` | 1.000 / 1.000 (8/0/0/16) | 1.000 / 0.875 (7/0/1/16) | 1.000 / 0.875 (7/0/1/16) |
| `weapon` | 1.000 / 1.000 (4/0/0/20) | 1.000 / 1.000 (4/0/0/20) | 1.000 / 1.000 (4/0/0/20) |

These visual labels were assigned by the Codex assistant, not independently
confirmed by the user. Treat the metrics as self-evaluation diagnostics rather
than human gold-label accuracy or collection acceptance.

An exploratory per-label threshold fit used explicit judgments on the same 24
disagreement-selected images. A deterministic SHA256 split by seed `20261109`
assigned 16 images to calibration and 8 to held-out; candidate cutoffs ran from
0.01 to 0.99 in 0.01 steps, maximizing calibration F1 and preferring the native
profile cutoff on ties. The fitted cutoffs were SwinV2 0.35 for all four labels;
EVA02 `boots` 0.37, `from behind` 0.53, `gloves` 0.14 and `weapon` 0.53; ViT-Large
`boots` 0.30, `from behind` 0.62, `gloves` 0.18 and `weapon` 0.35. On the eight
held-out images, EVA02 did not improve F1 over its native cutoffs; ViT-Large's
`from behind` F1 fell from 1.000 to 0.667 while its other three labels were
unchanged; SwinV2 was unchanged. No defaults were adopted. Full per-label counts,
split provenance and metric values are in
`.cache/m3-threshold-evaluation/threshold-fit.json`. Since both subsets come from
the same low-agreement selection and the judgments are assistant diagnostics,
this is a method check, not representative calibration or independent validation.

All three recorded `1girl`, `solo`, `full body`, and `white background` correctly
on these 24 examples. The five-image, 20-label review separately found a false
`boots` label on Sarada's sandals for all three models; SwinV2 missed `open mouth`
on the tactical-outfit image, EVA02 added a false `jacket` label on the black-cat
bodysuit, and ViT-Large missed `boots` on the black-cat image and `open mouth` on
two images. Some labels had only one or four positive examples. This selected
sample contains repeated characters and variants, so the figures describe these
24 difficult comparisons only and cannot rank general caption quality.

For an additional initial label check, five anime images were visually reviewed
against a controlled 20-label vocabulary in all three model reports. The SwinV2
and EVA02 examples are common to their 50-image QA selections; the ViT-Large
report includes all 396 images. Per-model judgments are stored with the QA reports
([SwinV2](../data/runs/20261109T175753685526Z-qa-9a8c4bb5),
[EVA02](../data/runs/20261109T175821592925Z-qa-8a1a886f),
[ViT-Large](../data/runs/20261109T183211480029Z-qa-19cfb244)). The summaries
from this sample appear above. These 20-label checks cover only the five named
images; caption review is partial and no collection-wide accuracy or model
superiority is established.

The assessment summary now derives per-label TP/FP/FN/TN, precision, recall and
specificity from explicit present/missing/absent judgments, and the QA report
displays those metrics. Unchecked labels stay outside all denominators. Same-pilot
CPU throughput, in-process peak working set, and provider execution are recorded
above. Representative label/composition and caption review, and threshold
calibration on independent reviewed examples, remain open in
[TODO M3](../TODO.md#m3--tagging-quality-comparison-and-runtime-qualification).

An isolated fixture under `.cache/m2-duplicate-probe/` used a re-encoded copy,
an exact-byte duplicate, a manually cropped version of the same artwork, and a
distinct pilot image. Inventory caught the exact-byte copy; pHash proposed the
same-pixel re-encode at distance 0. The known crop was distance 22 and appeared
as a known miss at radius 8. The crop was deliberately kept outside `pilot-dir`;
fixture details and run IDs are in its README. The probe demonstrates a real
crop failure mode, not collection-wide accuracy.

Verification: focused review suite **8 passed** with an isolated basetemp at
`.cache/pytest-review-split`. `git diff --check` passed. Representative pair
coverage, known pilot misses outside the proposal radius, expected-scale
performance and collection acceptance remain open in
[M2 completion evidence](#m2-selected-pilot-similarity-evaluation).

Chronology clarification: the preceding M2-open statement preserves the earlier
source-support boundary. The later selected-pilot checkpoint at the start of this
log supplies its scoped pair/performance evidence; unresolved full-directory
decisions and independent acceptance are not supplied by that checkpoint.

<a id="m2-pair-evaluation-sets-and-calibration-fit"></a>

## M2 pair evaluation sets and calibration fit — 2026-11-09

- Added durable `calibration` / `held_out` membership for saved related/distinct
  pair judgments, including manually linked pairs outside pHash proposals. The CLI
  and browser reviewer can assign or clear set membership; older records remain
  valid and unassigned pairs retain the descriptive combined sweep.
- Added a calibration-only F1 fit with a deterministic smaller-radius tie-break,
  separate held-out metrics at the selected radius, sample counts, per-split sweeps,
  and undefined metrics where a class is absent. Conflicting alias assignments are
  excluded and reported.
- Updated reviewer output and similarity/review guidance. Marked NF01 and CF02
  source support complete in [SHELVED](SHELVED.md#m2).

Verification at this source-support checkpoint: `git diff --check` passed.
Automated tests and collection judgments had not yet been run; later pilot review
and verification are recorded in the M2 section above. This source-support change
alone did not establish collection acceptance.

## MIVIM workflow routing and queue setup — 2026-11-09

Completed the user-requested document workflow setup:

- Incorporated all 100 findings from [IDENTIFIED.md](IDENTIFIED.md) into
  [SHELVED.md](SHELVED.md), ordered by PLAN milestones with stable finding IDs,
  original actions/priorities, source links and explicit queue states.
- Preserved all 26 existing TODO task bodies and added only contextual workflow
  tags, upstream links and the completion-to-next-task handoff.
- Linked IDENTIFIED, PLAN, SHELVED, TODO and this log at their document ends.
  TODO completion now returns to SHELVED; a new IDENTIFIED cycle requires all
  required PLAN acceptance to be complete.
- Installed the reusable `mivim-milestone-workflow` skill under
  `~/.codex/skills/mivim-milestone-workflow/SKILL.md` and saved the explicitly
  requested memory note as
  `~/.codex/memories/extensions/ad_hoc/notes/20261109T153337Z-mivim-milestone-workflow.md`.

Verification: all 100 unique finding IDs and full actions are retained; all 87
prior completed checklist items and all existing TODO task bodies are preserved;
local links/anchors and whitespace checks pass. The installed skill passes the
skill-creator validator, and both profile files match their prepared copies.
These are workflow/document checks; no application test or new collection
qualification is claimed. This setup does not complete any queued feature or
close the current PLAN.

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

## End-of-document handoff

Pull completed steps and their actual evidence from [TODO.md](../TODO.md), retaining
dates, source finding IDs, milestone, verification scope and unresolved acceptance.
Update the corresponding [SHELVED.md](SHELVED.md) state and link it to the completion
entry. Do not rewrite historical evidence as stronger qualification.

Continue any unfinished TODO work; when its active batch is complete, refill it
from SHELVED using [PLAN.md](PLAN.md) order and
[IDENTIFIED.md](IDENTIFIED.md) provenance. Only when all required PLAN acceptance is
complete should the next IDENTIFIED cycle begin. This handoff does not itself mark
the plan complete.
