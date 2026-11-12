# TODO

<!--
WORKFLOW_UTILIZED: "MIVIM.spec":"TODO"
WORKFLOW_CYCLE: dataset-preparation-2026-10-11
WORKFLOW_UPSTREAM: docs/SHELVED.md
WORKFLOW_COMPLETION: docs/COMPLETED.md
-->

Updated **2026-11-12**. Only unfinished work is tracked here. Completed steps,
verification results and historical qualification boundaries are in
[docs/COMPLETED.md](docs/COMPLETED.md).

Task source: [docs/SHELVED.md](docs/SHELVED.md), derived from IDENTIFIED + PLAN.

The [onboarding authority review](docs/COMPLETED.md#onboarding-workflow-authority-review)
is complete. The bounded M3 source-support batch is delivered. This closes
the workflow-document review gate, not the remaining product or dataset acceptance.

Follow [PLAN.md's work order](docs/PLAN.md#work-order-and-completion-boundaries).
The next required acceptance is **M4 human review** of the corrected report. The
user-selected `pilot-dir` now has representative assistant label/caption evidence,
corrected export and pinned trainer import. M3 measurement and diagnostic calibration
are complete within that authorized scope; no threshold or model winner is adopted.
M5/M6 dataset acceptance remains separately attributed. Do not search unrelated
directories for images or repeat completed assistant review to fill a human record.

## Remaining work against the existing plan

<a id="artifact-snapshot-coherence"></a>

### Artifact snapshot coherence — next source batch

<!-- WORKFLOW_TASK_GROUP: M5; SHELVED: docs/SHELVED.md#m5; ACTIVE_FINDINGS: CF22 -->

Promoted from [CF22](docs/SHELVED.md#cf22) after CF24/bounded SC06 delivery,
following [PLAN's order](docs/PLAN.md#source-reconciliation-and-next-batch). This
batch is scheduled, not yet implemented. It makes catalog and trainer-status
inspection report one verified artifact snapshot while preserving offline access
and historical receipts. Human dataset acceptance remains separate.

- [ ] **CF22 — return coherent catalog snapshots.** Derive parsed metadata and
  reported identity from the same captured bytes. Verify referenced artifacts
  against that snapshot and reject detected drift before returning catalog/query
  results. Preserve valid relocated exports and source-offline inspection. Do not
  rely on timestamps alone or require the whole SC02 reader-layer refactor.
- [ ] **CF22 — bind trainer status to verified receipt/export snapshots.** Prevent
  an earlier passed receipt from appearing current after its receipt, manifest or
  export metadata changes during inspection. Preserve historical receipt identity,
  current versus historical distinctions and explicit stale/invalid diagnostics.
  Keep inspection read-only and avoid rewriting receipts or inferring acceptance.
- [ ] **Qualify and archive the bounded batch.** Reproduce the retained deterministic
  read races, then verify metadata/manifest/receipt changes, same-ID rewrites,
  valid relocation, offline reads and unchanged artifact bytes. Run focused/full
  regression, installed catalog/trainer-status commands and affected status views.
  Record exact implementation identity, failures and qualification limits in
  COMPLETED, then reconcile CF22 and promote the next bounded candidate.

Dependencies: existing checked artifact reads, catalog metadata and trainer-receipt
contracts, with race probes in the [source review](docs/SOURCE-REVIEW-2026-11-12.md#cf22).
SC02's general reader extraction and TM21's query optimization remain queued.
Next after this batch: QOL21/localized SC15 publication reconnect and response
ordering. The required M4–M6 human acceptance tasks below remain unchanged.

<a id="model-binding-rule-contract"></a>

### Model identity and saved-caption rules — delivered

CF24 and the bounded SC06 saved-rule contract are complete in
[COMPLETED](docs/COMPLETED.md#model-rule-contract-0190). Configured models are
checked against their requested identity; saved scores use complete verified
recorded rules. Original tasks and qualification are archived. See
[the operating guide](docs/MODEL-RULE-CONTRACT.md). Broader SC06 schema-reader work
remains queued, and human acceptance remains separate and open.

<a id="review-evidence-integrity"></a>

### Judgment integrity and label-save recovery — delivered

CF21/CF23 are complete in [COMPLETED](docs/COMPLETED.md#review-integrity-0180).
Persisted evidence now has consistent strict validation, and label saves require
a current visible image with a loaded preview across buttons and shortcuts.
Original tasks and qualification are archived; see [the guide](docs/REVIEW-INTEGRITY.md).
M4–M6 human acceptance remains open.

### Saved review browsing — delivered

The promoted QOL07 continuation is complete in
[COMPLETED](docs/COMPLETED.md#review-preferences-0170). Named image-filter views and image/pair
positions survive live reviewer restarts, with explicit conflict and storage
recovery. Browsing preferences stay separate from judgments. Original tasks and
evidence are archived; see [the guide](docs/REVIEW-PREFERENCES.md). M4–M6 human
acceptance remains open.

### Saved caption rule explanations — delivered

The promoted TM09 continuation is complete in
[COMPLETED](docs/COMPLETED.md#caption-explanations-0160). Exact saved image/tag inspection now explains
thresholds, omissions, subset predicates and literal additions through the CLI and
existing reviewer, including offline source directories. Original tasks and evidence
are archived; see [the guide](docs/CAPTION-EXPLANATIONS.md). M4–M6 human acceptance
remains separate and open.

### Reviewer recovery — delivered

The promoted QOL08 continuation is complete in
[COMPLETED](docs/COMPLETED.md#reviewer-recovery-0150). Empty and unavailable states expose direct
navigation, explicit preview retry and form reload after source restoration.
Preview retry preserves unsaved values; explicit form reload replaces only its own
values. Use [the recovery guide](docs/REVIEWER-RECOVERY.md). Original tasks and
qualification are archived; M4–M6 human acceptance stays open.

### Caption comparison — delivered

The promoted QOL09 continuation is complete in
[COMPLETED](docs/COMPLETED.md#caption-comparison-0140). Open **Compare caption choices** in the
image correction editor to inspect override, sidecar and pinned draft precedence,
then preview a replacement or removal before saving. Use [the guide](docs/CAPTION-COMPARISON.md).
Original tasks and qualification are archived; M4–M6 human acceptance stays open.

### Review snapshot changes — delivered

The promoted QOL10 continuation is complete in
[COMPLETED](docs/COMPLETED.md#review-changes-0130). `dataset review-history changes` and the
reviewer's Publish pane explain exact saved differences, including history-only
advancement, before a separate publication. Use [the guide](docs/REVIEW-CHANGES.md).
Original tasks and qualification are archived; M4–M6 human acceptance stays open.

### Reviewed bulk annotation — delivered

The promoted NF11/QOL06 continuation is complete in
[COMPLETED](docs/COMPLETED.md#bulk-review-0120). `dataset review-batch` previews every
explicitly selected member and saves reviewed annotation/inclusion changes in one
atomic attributed batch. Captions, prior history and published artifacts survive.
Use [the bulk-review guide](docs/BULK-REVIEW.md). Original tasks and verification
are archived; M4–M6 human acceptance remains separate.

### Review-history recovery — delivered

The promoted NF10 continuation is complete in
[COMPLETED](docs/COMPLETED.md#review-history-0110). Inspect image/pair history and preview or
apply exact restoration through `dataset review-history`. Restores append a new
revision and preserve original history, source bytes and published artifacts.
Use [the recovery guide](docs/REVIEW-HISTORY.md). Original task bodies and
qualification evidence are archived; M4–M6 human acceptance remains separate.

### Inference-cache readiness — delivered

The scheduled CF17 continuation is complete in
[COMPLETED](docs/COMPLETED.md#cache-readiness-0100). `dataset status --verify-cache` checks
current-session cache progress, source availability and exact-job recovery without
inference or repair. Artifact integrity and human acceptance remain separate.
Use [the preparation guide](docs/PREPARATION.md#check-cached-inference-progress).
Original task bodies and qualification limits are archived with the evidence.

### Recovery receipt navigation — delivered

The authorized QOL18/CF17 receipt-navigation batch is complete in
[COMPLETED](docs/COMPLETED.md#recovery-browser-090). Removal, restoration, collision and package
history can be browsed without source images or optional runtime dependencies.
Selected restoration commands bind receipt and plan checksums; collision preview
retains its source-wide scope. Original task bodies and qualification limits are
archived with the delivery evidence.

CF17's live inference-cache progress is delivered above. The existing M4–M6 human
acceptance remains separate. NF10 review-history recovery is delivered above as
its own operational continuation.
Use [the recovery browser](docs/RECOVERY-BROWSER.md) for current commands.

### Saved collections and actionable recovery — delivered

The authorized NF07/QOL14 and bounded CF17 batch is complete in
[COMPLETED](docs/COMPLETED.md#collection-navigation-recovery-080). Named collections, filtered exact run
selection, guarded resume and per-stage recovery inspection are implemented and
qualified on generated fixtures, the installed package and read-only inspection
of the actual selected collection. Existing source bytes and assistant judgments
remain unchanged. Original task bodies and retained failures are archived there.

The next required task remains M4 human acceptance below. Further optional recovery
or storage work retains its SHELVED scope; this completion does not expand PLAN or
start another IDENTIFIED cycle.

### Representative review and correction support — delivered

The authorized assistant continuation and NF06 enabler are complete in
[COMPLETED](docs/COMPLETED.md#representative-assistant-review-070), including the
original task bodies and source IDs. A frozen 64-content probability sample has
512 assistant label judgments; all 62 applicable training captions were reviewed,
46 corrected, and the new 355-pair export passed actual pinned trainer import.
NF05 sampling, explicit QA membership, CF07 attribution and NF06 snapshot comparison
are delivered. Completed M3 work is scoped to these assistant measurements;
the existing M4–M6 human acceptance remains open.

<a id="active-product-phase--directory-preparation-and-recovery"></a>

### Directory preparation phase — delivered

The user-directed 0.6.0 operational phase is complete. Its original task bodies,
source IDs and verification are archived in
[COMPLETED](docs/COMPLETED.md#directory-preparation-060). `dataset prepare` now
produces verified training pairs, a portable catalog and QA from a directory;
recovery, independent label review and installed-package checks are delivered.
The selected collection produced 355 pairs and passed the pinned trainer import.
Use [PREPARATION](docs/PREPARATION.md) for commands and exact recovery behavior.

The remaining required work below concerns independently attributed human dataset
acceptance. Representative sampling and assistant label/caption review are now
complete within their recorded scope. Assistant judgments remain assistant evidence.
Conditional and unmeasured candidate features
retain their scope in SHELVED; none is silently treated as completed or mandatory.

<a id="m3--tagging-quality-comparison-and-runtime-qualification"></a>

### M3 — tagging quality, comparison and runtime qualification

<!-- WORKFLOW_TASK_GROUP: M3; SHELVED: docs/SHELVED.md#m3; DELIVERED: CF04,CF05,CF06,NF02,NF03,NF05 -->

The original representative measurement and calibration tasks are completed and
archived in [0.7.0 evidence](docs/COMPLETED.md#representative-assistant-review-070).
The [64-content workspace](data/reviews/label-evaluations/20261110T030358166483Z-labels-6b260027)
contains all 512 assistant judgments across eight labels, with uncertainty retained.
Four reviewed family links yield 53 groups, 46 calibration and 18 held-out images.
Three models use identical membership and saved 0.35 baselines, including EVA02.
Fitted cutoffs were tested and retained as proposals; regressions and small positive
classes do not support adoption. Human-only evaluation excludes all 512 judgments.

The sampling frame covers all 381 source contents, including training-excluded originals,
at exact inclusion probability 64/381. Ten contents overlap the earlier 50-image
pilot, whose 400 judgments and revision-402 history remain unchanged. Other prior
exposure is incompletely catalogued, so this is no pristine independent holdout.
The prior five-/24-/50-image diagnostics remain in COMPLETED; none is overwritten.

The authorized assistant work satisfies the bounded measurement tasks without
introducing a human-only M3 gate. It does not qualify new thresholds for adoption,
establish general model accuracy or replace the M4/M6 human dataset conclusion.
Conditional model/provider extensions retain their existing prerequisites.

Acceptance scope: collection-specific measurements and separately scoped runtime
qualification. See [PLAN section 3](docs/PLAN.md#3-local-tagging),
[label evaluation](docs/LABEL-EVALUATION.md) and [tagging](docs/TAGGING.md).

<a id="m4--representative-caption-and-subset-acceptance"></a>

### M4 — representative caption and subset acceptance

<!-- WORKFLOW_TASK_GROUP: M4; SHELVED: docs/SHELVED.md#m4; ACTIVE_FINDINGS: CF07 -->

- [ ] Record the pilot's human judgments and conclusion for the corresponding
  report; generated fixture judgments do not supply this acceptance.

The representative assistant review is complete: 62 training occurrences reviewed,
46 saved caption corrections, and all 62 corrected captions accepted as assistant
judgments. Empty trigger/forced phrases/subset rules were assessed for this mixed
collection. Nine older overrides and all source bytes survive. Evidence and original
task bodies are in [COMPLETED](docs/COMPLETED.md#representative-assistant-review-070).

Use the [corrected report](data/prepared/pilot-dir/runs/20261110T030356375040Z-qa-4c5ae254/report.html)
and its matching assessment. Current revision 63 is explicitly assistant, with
`human_accepted=false`; it must not be relabeled or transferred into human acceptance.
The pending human review is an existing requirement, not missing source support.

Acceptance: accurate reviewed pilot captions and suitable rules, following
[PLAN section 4](docs/PLAN.md#4-caption-normalization-and-review).

<a id="m5--representative-export-and-trainer-import-acceptance"></a>

### M5 — representative export and trainer import acceptance

<!-- WORKFLOW_TASK_GROUP: M5; SHELVED: docs/SHELVED.md#m5; ACTIVE_FINDINGS: CF08 -->

- [ ] Address representative export/import findings and record acceptance of the
  resulting image/caption dataset.

The corrected 0.7.0 export carries the representative assistant corrections into
all 355 verified pairs and passes actual pinned CPU trainer import for captions,
repeats, buckets and tensors. Its comparison with 0.6.0 shows 46 caption edits,
two family-merge events, and no membership, media or split changes. Original
publication/import tasks are archived in
[COMPLETED](docs/COMPLETED.md#representative-assistant-review-070).
The remaining acceptance depends on the existing M4 human conclusion; automated
verification and assistant sample acceptance remain separately recorded evidence.

Acceptance: the selected pilot's verified export and actual pinned import, following
[PLAN section 5](docs/PLAN.md#5-split-export-and-trainer-adapters) and
[docs/EXPORT.md](docs/EXPORT.md).

<a id="m6--full-collection-execution-and-recorded-acceptance"></a>

### M6 — full-collection execution and recorded acceptance

<!-- WORKFLOW_TASK_GROUP: M6; SHELVED: docs/SHELVED.md#m6; ACTIVE_FINDINGS: CF09,CF10 -->

- [ ] Address pilot findings, publish the corrected dataset/QA artifacts and record
  user review and dataset acceptance.

The three execution/measurement tasks are complete for the explicitly selected
`pilot-dir` and archived in [COMPLETED](docs/COMPLETED.md#directory-preparation-060):
399 files, 396 readable images, 381 unique image hashes, 355 exported pairs and
41 explained membership exclusions. At that checkpoint all original bytes and saved
reviews remained unchanged. Processing time, logical disk payload, dimensions and duplicate rates
are recorded; peak process memory and temporary-disk sampling were unavailable.
The 0.7.0 continuation has addressed representative assistant findings, published
corrected dataset/QA artifacts and re-imported all 355 pairs. All 399 source files
remain unchanged; saved reviews append 46 overrides, four family links and two
duplicate exclusions, with earlier history retained. The completed portion of the
compound task above is in [COMPLETED](docs/COMPLETED.md#representative-assistant-review-070).
Only the independently attributed human review/acceptance conclusion remains.

Acceptance: a qualified collection run with reconciled counts, measured resources,
corrected pilot problems and recorded human review, following
[PLAN section 6](docs/PLAN.md#6-report-and-qa).

<a id="outstanding-interface-and-platform-qualification"></a>

## Interface and package qualification — recorded scope

<!-- WORKFLOW_TASK_GROUP: interface-platform; SHELVED: docs/SHELVED.md#m1 + docs/SHELVED.md#m6 -->

The 0.6.0 rendered-panel and isolated installed-command checks are complete and
archived in [COMPLETED](docs/COMPLETED.md#directory-preparation-060). Actual browser
checks cover label review, images, assessment, pairs, publication/recovery, trainer
receipts and snapshot/count/resource tables at desktop and narrow widths. Browser
DPR/CSS-zoom emulation is recorded separately from physical Windows scaling.
The installed 0.6.0 wheel passed its own command/resource/recovery journey.
The 0.7.0 wheel adds 48 isolated command checks and 61 matching payload files;
rendered attribution checks preserve assistant/unknown status and legacy history.
The normal user installation remains unchanged. Human usability and additional native
platform qualification are not implied by these checks.

These checks must preserve the separate Trainime menu, preview, source-caption,
backup and recovery contracts in [docs/TRAINIME.md](docs/TRAINIME.md) and
[docs/INSTALLATION.md](docs/INSTALLATION.md).

The latest retained package/browser qualification is
[0.17.0](docs/COMPLETED.md#review-preferences-0170): 1,216 passing tests, 16 platform
skips, 137 installed commands and 24 preference HTTP checks, with rendered browsing
observations recorded separately. These are prior results. The 2026-11-12 source
reconciliation adds generated fault probes and planning evidence, not a new full
qualification run; the next implementation must record its own results.

## Conditional extensions — not the next required milestones

<!-- WORKFLOW_TASK_GROUP: conditional; SHELVED: docs/SHELVED.md; PROMOTION: condition_must_apply -->

- [ ] Consider normalized-pixel matching as a later extension; evaluate embeddings
  only if representative pHash misses justify them (PLAN section 2).
- [ ] Evaluate a separate Camie backend only if selected after baseline comparison;
  it is not a drop-in WD model or the next required integration (docs/TAGGING.md).
- [ ] Qualify physical GPU inference if using CUDA; record actual providers, runtime compatibility, performance and observed behavior.
- [ ] Add natural-language caption adapters and tokenizer/truncation checks only
  for an actual target profile (PLAN design decision 6 and section 6).
- [ ] Qualify ARM64 native installation or other operating-system installer flows
  if extending supported deployment beyond the qualified Windows x64 scope.

ComfyUI inspection remains optional. Model training and training-quality evaluation
belong to the downstream trainer, outside this preparation backlog.
Additional proposals from [docs/IDENTIFIED.md](docs/IDENTIFIED.md) are ordered in
[docs/SHELVED.md](docs/SHELVED.md); they become active only when promoted into TODO.

## End-of-document handoff

When this active TODO is complete, move its completed steps and evidence to
[docs/COMPLETED.md](docs/COMPLETED.md), then pull the next eligible tasks from
[docs/SHELVED.md](docs/SHELVED.md#promotion-and-completion). Carry the finding IDs
and PLAN milestone into the next TODO tasks; do not regenerate this backlog from
scratch or copy every shelved proposal into it.

SHELVED gets its context from [IDENTIFIED](docs/IDENTIFIED.md) and
[PLAN](docs/PLAN.md). **An empty TODO does not trigger another IDENTIFIED workflow.**
Only completion of the PLAN, including its required acceptance evidence, does.
