# Dataset preparation plan

<!--
WORKFLOW_UTILIZED: "MIVIM.spec":"PLAN"
WORKFLOW_CYCLE: dataset-preparation-2026-10-11
WORKFLOW_PAIRED_SOURCE: IDENTIFIED.md
WORKFLOW_DOWNSTREAM: SHELVED.md
PLAN_STATUS: open
IDENTIFY_GATE: only_after_current_plan_complete
-->

Design reviewed: 2026-10-11. Implementation status refreshed: 2026-11-12.
Intake, local tagging, Trainime directory actions, similarity proposals, durable
review decisions, caption overrides, and group snapshots are implemented.
Group-aware splitting, verified image/caption exports, and Kohya configuration
generation are implemented. Pinned CPU trainer imports pass on generated fixtures
and the corrected 0.7.0 355-image selected collection. Representative assistant
label/caption review and bounded M3 measurement are complete; human collection
acceptance remains pending. Model training belongs to
the downstream trainer, as defined in Purpose and scope below.
Pilot QA reports and browser/CLI navigation now connect captions, reviewed
annotations, and semantic split coverage. The local reviewer saves image and pair
corrections and report-bound pilot assessments. It publishes group snapshots,
verified exports, and refreshed QA through the same core functions as the CLI.
Its Training import view and `dataset trainer-status` expose export-bound receipts,
the current pinned import result, and separate pilot qualification status.

Installation and operational recovery are implemented in 0.4.0:
[install.cmd](../install.cmd) owns setup, and [the recovery contract](INSTALLATION.md)
defines logs, diagnosis, automatic repairs, and actionable fixes for remaining failures.

## Purpose and scope

<a id="source-reconciliation-and-next-batch"></a>

### Source reconciliation and next batch — 2026-11-12

The user requested a comprehensive source/backlog review. The
[dated source review](SOURCE-REVIEW-2026-11-12.md) and
[IDENTIFIED addendum](IDENTIFIED.md#current-source-reconciliation--2026-11-12)
refresh this open cycle without replacing its milestones or earlier evidence.
The next required dataset acceptance remains **M4 human review**; source support
continues independently and does not create, infer or request acceptance on the
user's behalf.

The source review scheduled **review-evidence integrity, CF21 + CF23**, now
delivered in [0.18.0](COMPLETED.md#review-integrity-0180):

1. Make assessment, correction-review and label-workspace reads and writes agree
   on validated persisted state, history and attribution. Preserve legacy unknown
   actors, event semantics, revision guards and original bytes on rejection.
2. Make label click, form-submit and keyboard-save eligibility identical for the
   current visible image, including loading/error/empty-filter and stale-preview
   states. Preserve legitimate explicitly attributed assistant/API judgments.
3. Qualify corruption rejection, normal saves, conflict/retry and the rendered
   review journey using generated fixtures and the installed candidate when
   runtime source changes. Preserve actual collection/assessment records.

This bounded correction supports the M4 acceptance evidence and its M3 label
inputs; it does not depend on human acceptance. The task contracts are in
[TODO](../TODO.md#review-evidence-integrity) and the queue states in
[SHELVED](SHELVED.md#current-source-priorities). The original tasks and exact
qualification are now archived in COMPLETED; human acceptance remains open.

**CF24 + bounded SC06** are delivered in
[0.19.0](COMPLETED.md#model-rule-contract-0190): configured model/repository/full
revision checks before reuse/inference, and shared checked recorded rules across
evaluation/comparison/explanations. Historical offline evidence, recovery backups
and explicit attribution remain supported. SC06's broader schema-reader proposal
remains queued; only the saved-rule portion is complete.

The next scheduled source batch is **CF22 artifact snapshot coherence**, defined
in [TODO](../TODO.md#artifact-snapshot-coherence). Catalog reads and trainer status
must bind parsed data, hashes, verification and reported identity to one checked
snapshot, rejecting detected drift while preserving offline/historical inspection.
Keep SC02 general reader extraction and TM21 query optimization separate. Then
reassess **QOL21 + localized SC15** publication reconnect and
response ordering. Existing M4 workflow improvements such as QOL04/QOL15 follow
the confirmed integrity/recovery gaps. Other operating improvements remain
ordered candidates: SC04/SC12 for reliable writes/settings; DP03/NF14/QOL12/QOL13
for preparation clarity and storage/recovery; CF11 before split search/constraints;
TM01/TM02 measurements before larger storage, inference or report redesigns.
Do not promote that whole sequence at once or make every proposal a new required
PLAN gate. Original priorities remain historical provenance; the source review
explains the present execution priority and any narrowed scope.

Verification must distinguish source checks, generated fault probes, installed
commands, rendered browser behavior, physical platform/GPU qualification and human
dataset acceptance. Keep prior failed runs and completed-feature evidence.
Larger-scale performance, hosted CI and additional native platforms require their
own evidence. The preceding source-review request was planning-only; the subsequent
CF21/CF23 development request is completed with runtime evidence above. Workflow
documentation never substitutes for runtime delivery or human acceptance.

### Review browsing recovery continuation — 2026-11-12

The delivered **QOL07** M4 continuation restores image filters and exact image/queue
position for a saved QA report, with named filter combinations and live pair-queue
resume. The existing reviewer uses random loopback ports, so live preferences use
a separate local application-data store keyed by verified report identity. They
are not review decisions, assessments, captions or exported training metadata.

Bound and validate stored state, use atomic revision-checked updates, and preserve
conflicting or corrupt evidence. Preference read/write failures leave normal review
available. Explicit image links take precedence over resume. Named views, reloads
and delayed responses must never replace unsaved correction/assessment/pair fields.
Restore pair positions against current server results, not saved relationship data.
Static reports may retain browser-local preferences where storage is available;
that fallback is origin-dependent and does not promise portable persistence.

Verify restart on a different port, report isolation, concurrent writers, invalid
state, dirty forms, source-offline browsing and installed assets. Retain read-only
actual-collection evidence and generated rendered tests. NF09/CF19 source relocation
requires a separate lineage transaction and stays queued. Existing M4–M6 human
acceptance remains open; this does not start another IDENTIFIED cycle.

Delivered in [0.17.0 review browsing](COMPLETED.md#review-preferences-0170); required M4–M6 human acceptance remains open.

### Caption rule explanations continuation — 2026-11-12

The delivered **TM09** M4 core-feature improvement explains saved drafts using
their complete score vectors, label indexes and frozen caption rules. Exact image
selection and omission decisions are available without reconstructing rules
manually or repeating inference.

Use the saved run's rule version, thresholds and label identities. Explain strict
threshold comparisons, explicit drops, character gating, rating-only evidence,
near-threshold values, literal trigger/forced phrases and duplicate phrase handling.
Show every subset predicate against observed raw tags, including missing expected
tags and overlapping matches. Keep this evidence separate from a saved correction,
source sidecar, exported caption and human judgment. No rules or captions change.

Provide a configuration-independent CLI for an exact scored run or preparation
workspace, plus read-only access from the existing reviewer. Source images and
model runtimes need not be available; saved evidence must be intact. Exact report
and image bindings, bounded output, stale-response fencing and unsaved correction
preservation apply. Legacy rule versions that cannot be replayed stay explicitly
unavailable rather than being interpreted with current defaults.

Verify generated rule/score boundary cases, installed commands, browser interaction
and read-only actual selected-collection evidence. Source relocation (NF09/CF19)
requires a separate cross-artifact lineage design and remains queued. M4–M6 human
acceptance remains open; this continuation does not start a new IDENTIFIED cycle.

Delivered in [0.16.0 caption explanations](COMPLETED.md#caption-explanations-0160); the existing M4–M6 human acceptance remains open.

### Reviewer recovery continuation — 2026-11-11

The delivered QOL08 M4 operational batch makes empty and unavailable reviewer states
actionable. It is the smallest current-milestone recovery improvement supported by
the observed QOL09 offline form failure. Source relocation remains separate because
it requires cross-artifact lineage migration; this batch retries the existing exact
paths and guards without rebinding a collection or rewriting historical artifacts.

Distinguish absent report membership, filtered-out images, no unresolved pairs,
no saved/proposed pairs and failed pair reads. Provide context-specific navigation
to all images, all pairs, the snapshot summary or manual comparison without treating
queue emptiness as quality acceptance. Preserve static-report use and live-session
boundaries. Missing/failed previews need clear status and an explicit retry or
existing full-image path; never manufacture a valid preview or loop indefinitely.

Correction and assessment reload controls must remain reachable after an initial
read failure, including restoration of the original source root. Explicit reload
can replace that form's unsaved values; preview retries and unrelated recovery must
not. Preserve exact image/pair identity, generation/request fences and save revision
guards; prevent reload/save overlaps and stale responses from reviving obsolete
forms. A failed queue read must not leave stale items looking current. These actions
do not write reviews, judgments, source files or reports.

Qualify real browser behavior at desktop/narrow widths, generated no-data/offline
and failure fixtures, installed resources and read-only actual report inspection.
Human acceptance, automatic corrections, source relocation, new filter persistence
and broader shortcut proposals retain their existing scope.

Delivered in [0.15.0 reviewer recovery](COMPLETED.md#reviewer-recovery-0150); existing M4–M6 human acceptance remains open.

### Caption comparison continuation — 2026-11-11

The delivered QOL09 M4 batch compares caption candidates before a correction
is saved. Place it inside the current image correction editor: current saved manual
override, source sidecar evidence and the exact draft bound to the report. Reuse
the exporter's override > sidecar > draft precedence and normalization. Never select
a latest tagging run or treat an edited loose draft file as an override.

Validate QA/input and image identity, current review state, pinned draft metadata
and authoritative manifests. Export reports use frozen sidecar/draft provenance,
clearly labeled as captured evidence; group reports can inspect exact recorded
sidecar bytes with explicit offline/changed states. Absent, invalid and unavailable
evidence differ: invalid winning evidence must not silently fall through to a lower
candidate. Bound new snapshot/draft metadata and caption-text reads; the existing
selected-inventory and whole-JSON review-history loader remains unchanged. This is
not a global storage or history-size limit. Do not decode source images or run
inference, repair, publication or validation of the whole export media tree.

Show effective keep/replace/clear text before save, literal phrase differences and
accessible full values. Keep the historical snapshot caption distinct from current
saved reviews and the proposed source caption; derivative-specific export caption
adjustments are not predicted. Bind results to report/image/revision and suppress
late responses. Refresh never overwrites unsaved correction or assessment fields.
Retain existing reason/revision conflict checks and separate publication controls.

Qualify generated group/export and offline fixtures, corrupt or missing evidence,
aliases, precedence, read races, rendered desktop/narrow behavior, installed resources
and actual read-only inspection. QOL09 does not amend M4–M6 human acceptance or
authorize source relocation, storage migration, rule tracing or automatic judgments.

Delivered in [0.14.0 caption comparison](COMPLETED.md#caption-comparison-0140); existing M4–M6 human acceptance remains open.

### Review snapshot changes continuation — 2026-11-11

The delivered QOL10 M4 operational batch explains saved review changes since an exact
QA snapshot. Validate QA input identity and declared group/export provenance, then
validate the captured and current review histories through the same grammar.
Captured history must be an exact prefix of current history; equal revision numbers
or current maps do not establish lineage. Preserve explicit unavailable/error states.

Compare net records, distinguishing unchanged, history-only advancement and changed
state. Return exact image/pair identities, changed fields, counts and bounded pages.
Include changes outside report membership with explicit classification; compatibility
with the selected inventory is not validation of live source bytes. These are saved
record differences, not a forecast of transformed export captions or dataset contents.

Add `review-history changes` using existing collection/workspace/run selection and
an explicit report, or the exact selected job's checked QA checkpoint. Connect the
same metadata-only inspection to the reviewer Publish pane, with current inspected
revision, refresh/pagination and stale-response protection. Reuse existing guarded
publication commands/controls; inspection never publishes or transfers acceptance.
Verify the rendered interface on generated fixtures and inspect the selected actual
report read-only. Original reports, assessments and source bytes remain immutable.

QOL09 caption comparison, NF09/CF19 relocation and storage scaling remain separate.
This batch does not change the existing M4–M6 human acceptance requirements.

Delivered in [0.13.0 review snapshot changes](COMPLETED.md#review-changes-0130); existing M4–M6 human acceptance remains open.

### Reviewed bulk annotation continuation — 2026-11-11

The delivered NF11/QOL06 M4 operational batch lets users apply explicit reviewed label, subset
or inclusion changes to a finite list of exact image paths. The preview lists all
members and before/after states, including unchanged members, rather than relying
on a live filter. Canonical operations, source hashes, artifact context, current
store bytes/revision and the saved collection/job selection bind the apply guard.

One locked atomic publication records the batch actor/reason and contiguous
per-image revisions for changed records. This preserves the existing revision and
history replay contract while exposing one coherent action. Exact source validation,
complete selection checks and group consistency precede publication; failures do
not partially save the batch. Labels/subsets are explicit reviewed values, never
predictions accepted automatically. Captions, unrelated fields and prior history
survive. Individual changes remain inspectable/restorable through NF10 history.

Use the existing collection/workspace/explicit-run selection contract through
shared helpers. Keep preview metadata-only and offline-capable; apply requires all
selected current sources. Publication remains a separate guarded continuation.
This batch adds CLI support; graphical bulk controls, root relocation, persistence
scaling and human acceptance remain separate. NF09/CF19 is a larger cross-artifact
migration and is not required for this bounded correction-throughput improvement.

Delivered in [0.12.0 reviewed bulk annotation](COMPLETED.md#bulk-review-0120); existing M4–M6 human acceptance remains open.

### Review-history recovery continuation — 2026-11-11

The delivered NF10 M4 operational enabler lets users inspect image/pair revision
history and explicitly restore one target's earlier state. A read-only preview
binds the selected event, current review bytes/revision, source and similarity
context. Apply rechecks that identity under the existing review lock, verifies
affected source bytes and graph consistency, then atomically appends a new event
and exactly replaces or removes that target record. Restore is not a merge: later
caption, label, subset or evaluation fields must not survive by accident.

History remains append-only; absence before a first edit is an explicit target.
Validate historical records and replay/current-state consistency before trusting
them, preserve legacy attribution as unknown, and record restoration actor/reason
separately from the restored decision's provenance. Offline history and previews
do not create directories, locks, logs or reports. Apply requires current source
identity and a matching preview; no repair or acceptance is implicit. Named
collections and workspaces resolve through their saved job/configuration binding;
explicit similarity-run/configuration use remains available. Ordinary reviewer
saves and immutable exports retain their behavior. NF09/CF19 relocation is a
separate cross-artifact migration task and is not needed for this recovery path.
The existing M4–M6 human acceptance and conditional proposals remain open.

Delivered in [0.11.0 review-history recovery](COMPLETED.md#review-history-0110): source-bound history, preview/apply restoration and exact
record recovery with retained provenance. Existing human acceptance remains open.

Qualification uncovered a build-path issue: the packaging backend traverses ignored
model/cache/test trees before excluding their files. As a necessary packaging enabler
within this batch, skip already-excluded directories during collection, preserving
the existing inclusion rules. Verify source/wheel/archive payload parity and retain
the prior archive's file coverage. This changes build traversal, not runtime behavior
or the queued storage/performance features.

### Inference-cache readiness continuation — 2026-11-10

The next scheduled CF17 step makes live cached progress inspectable for a selected
preparation job. `status --verify-cache` explicitly verifies the saved inventory,
source binding, local pinned model and exact runtime namespace. It may initialize
the local ONNX session, including its configured device, to observe actual provider
options; advertised providers alone are insufficient. It never predicts image
labels, fetches a model, repairs a cache, or mutates source/application artifacts.
Read only expected content hashes under the selected namespace with bounded,
checked cache decoding shared by inference. Report occurrence and unique-content
counts separately. Missing cache is ordinary work remaining, while invalid or
unavailable evidence remains visible. Cache readiness is not completed-artifact
integrity, permission to resume a historical/changed-build job, or human acceptance.
Default status and existing-caption jobs retain their lightweight behavior. This
finishes the scheduled CF17 cache-inspection remainder without changing M4–M6 gates.

Delivered in [0.10.0 cache readiness](COMPLETED.md#cache-readiness-0100): verified current-runtime cache progress, separate source and
artifact evidence, and publication-aware continuation. Human acceptance stays open.

### Recovery receipt navigation continuation — 2026-11-10

The user's continued operational development schedules QOL18 and CF17's remaining
receipt-navigation support. Read only known application-owned removal, restoration,
collision and package-repair metadata; preserve offline readability, exact selection
and failure isolation. Route explicit recovery through existing checked commands.
Collision retry remains source-wide, and package repair uses current installation
diagnosis. Navigation must work without the optional UI/inference runtime and must
not write logs, locks, journals or backups. Retained failed receipts are history,
not proof that an old problem still exists. No automatic cleanup, collision undo or
new Home choices are included. QOL18's historical NF10 reference does not schedule
the separate review-history viewer. Live inference-cache progress remains queued;
M4–M6 human acceptance and conditional extensions retain their scope.

Delivered in [0.9.0 recovery receipt navigation](COMPLETED.md#recovery-browser-090): metadata-only recovery history,
receipt-and-plan-bound restoration, dependency-light navigation and explicit repair
scope. Generated and installed checks remain separate from human acceptance.

### Collection navigation and recovery continuation — 2026-11-09

The user authorizes the next bounded operational batch: NF07 registered collection
and run catalog, QOL14 exact selection/filtering, and CF17 preparation recovery
visibility. Register only explicitly supplied preparation workspaces; do not search
unrelated directories. Keep catalog reads side-effect-free, including publication
inspection. Separate metadata inspection from artifact verification and human
acceptance. Actions selected from the catalog must retain collection/job identity
and reject stale or ambiguous targets. Preserve pending and superseded attempts;
no automatic cleanup or new Trainime Home menu is included. Existing M4–M6 human
acceptance and conditional extensions retain their scope.

Delivered in [0.8.0 collection navigation and recovery](COMPLETED.md#collection-navigation-recovery-080): registered collection navigation,
exact guarded selection, read-only historical/per-stage recovery inspection and
failure replies that survive unavailable application-data logging. Actual source
and saved assistant evidence are preserved; the human acceptance remainder stays open.

### Representative assistant review continuation — 2026-11-09

The user authorizes assistant-attributed representative image and caption review.
Freeze a model-independent probability sample with its population, seed, inclusion
probability and earlier-review overlap; judge image labels before model comparisons.
Review training captions against their actual derivatives while keeping original
image judgments distinct. Explicit QA membership must support the same frozen
population. Caption-assessment records require reviewer kind; assistant and legacy
unattributed records must never satisfy human acceptance. Correct observed problems
through the existing review store, then re-evaluate and publish new immutable
evidence. This advances NF05/CF04–CF08/CF10 without changing the human acceptance gate.

Delivered in [0.7.0](COMPLETED.md#representative-assistant-review-070): a full-source
64/381 probability sample, 512 assistant labels, 62 reviewed training occurrences,
46 caption corrections and verified same-membership export/import. Bounded
CF04/CF05/CF06/NF02 measurement and diagnostic fitting are complete. Unknown prior
exposure, assistant attribution, rare classes and held-out regressions prevent a
threshold-adoption or general accuracy claim. Existing M4/M6 human acceptance is
still required; M3 has no added human-only measurement gate.

### Directory preparation product phase — authorized 2026-11-09

The user has explicitly expanded the current development direction: point at an
image directory and produce a usable image/caption database with metadata for a
generative-model trainer. Complete operational capabilities autonomously, including
opinionated defaults, robust commands, recovery and conservative corrections.
This addendum authorizes the cross-stage product work below while the existing
collection-quality acceptance record remains open. It does not turn assistant or
automated observations into human judgments, or require every optional proposal.

The coherent 0.6.0 delivery is implemented and operationally qualified in
[COMPLETED](COMPLETED.md#directory-preparation-060):

1. **DP01 — one preparation command and durable continuation.** `dataset prepare`
   accepts a directory without requiring a repository configuration. It composes
   intake, similarity, local tagging, policy resolution, verified export and QA.
   Persist stage inputs, attempts, verified outputs and failures so interrupted
   jobs resume without discarding successful stages. Provide read-only preview,
   status and explicit retry commands with useful next actions.
2. **DP02 — portable ingest metadata.** New exports include a checked SQLite
   catalog and split-local `metadata.jsonl` alongside image/caption pairs. Paths
   remain relative, source and derivative identities remain distinct, and model
   predictions remain separate from reviewed labels. Query and verification work
   when the original source is unavailable. Existing exports remain compatible.
3. **NF05/QOL02/QOL03 — usable independent label review.** Allow explicit frozen
   membership, image-first label review, atomic per-image saves, saved-model
   comparison, revision protection and recoverable unsaved forms in a local UI.
4. **SC17/SC18/SC19/TM20/NF08 — recovery and delivery.** Repair packaged Python and
   non-Python resources from a verified wheel, provide conflict-preserving caption
   restore, and promote reproducible package checks into tracked tooling and CI.
   Use one executable-payload identity in all new stage receipts, including QA,
   catalog builds and trainer checks, as well as durable job contracts; retain
   compatibility with historical receipts that lack that field.
5. **TM14/QOL11 — durable reviewer publication.** Preserve settings, stages and
   outputs through restart; retry verified work through the existing Publish panel
   and restore captured custom settings without overwriting unsaved form edits.

The detailed contracts and verification boundaries are in
[PREPARATION.md](PREPARATION.md). Existing review decisions and caption overrides
take precedence. Automatic preparation decisions carry their policy identity and
evidence; source bytes and source-side captions are preserved. Similarity proposals
can conservatively constrain splits without becoming verified semantic truth.
Dataset integrity, machine preparation, trainer import and human quality acceptance
are distinct states. Failed or ambiguous operations retain concrete recovery paths.

The existing 100 findings are a candidate backlog. This phase prioritizes cohesive
operational improvements and their dependencies; backend/platform extensions and
unmeasured performance refactors retain their conditions. Track dispositions and
delivered evidence through SHELVED, TODO and COMPLETED instead of marking proposals
complete merely because this product direction was approved.

Turn a local collection of anime images into a traceable, reviewed dataset of
images and matching captions. The collection includes nude images; nudity alone
is not an image-quality failure. Preserve accurate content labels without adding
attributes that the image does not support.

The requirements established in the original `OVERVIEW.md` (now `TAGGING-METHODS.md`)
are sufficient to start:
Windows, Python, local paths, local inference, batch operation, image/`.txt`
exports, and optional ComfyUI inspection. No hosted caption API. Training itself
belongs to the downstream trainer. No trainer or GPU choice is needed for intake.

## Review of the rough notes

These are design and code defects in the supplied examples, not failures observed
in an existing application. The repository initially contained only `OVERVIEW.md`.

| Finding | Required correction |
| --- | --- |
| Several stage orders, two conflicting configs, multiple output layouts, and 512/768 size cutoffs | Establish one plan, one schema, and one work order. |
| Source preservation contradicts moving/quarantining inbox files and overwriting source captions | Keep sources read-only; record exclusions and write managed artifacts separately. |
| WD14 resizes rectangles directly to squares | Match the model's reference input preparation; preserve composition. |
| Label rows are rearranged and character categories guessed from parentheses | Preserve CSV output index and explicit category `0`, `4`, or `9`. |
| Initial example uses undefined `THRESHOLD` and `DROP`; later CLI imports missing `safety.py` | Replace illustrative snippets with an installable package and tested commands. |
| `rewrite()` returns an empty list for every nonempty tag list; callers unpack two values | Define a typed normalization result and test actual caption behavior before use. |
| Intake hash covers only the first MiB and truncates to eight characters | Hash all bytes; retain full digests and provenance. |
| Deduplication claims largest-image selection but implements first-file wins | Distinguish exact equivalence from near-duplicate candidate selection. |
| Guidance says to raise Hamming distance when false matches occur | A larger maximum accepts more distant pairs; lower it for stricter matching. |
| Flat colors, compressed byte counts, and borders are unconditional rejection rules | Anime often contains intentional flat regions; use review flags until calibrated. |
| Subject count is used to infer relationships | Keep count, relationship, content, and style labels independent. |
| Style tags are forced globally; quality/watermark tags are deleted unconditionally | Default to no forced tags. Keep evidence; configure training-specific caption policy. |
| `missing_nude` is flagged for all proposed buckets | Mixed clothed/nude datasets are expected. Apply expectations only to explicitly configured subsets. |
| Split flattens names, permits missing captions, accumulates copies, and is not stratified | Export from a fixed manifest; use unique IDs, caption checks, group-aware splits, and new snapshots. |
| Repeats are described as caption prefixes | Repeats are trainer sampling configuration. Never put repetition counts in captions. |
| Append-only events are counted as current state | Separate stage events from current records; report a specific run or snapshot. |
| Thirty/fifty random examples are treated as proof of usability | Combine representative sampling, targeted failure review, and measured label accuracy. |

## Design decisions

1. **Preserve images and existing annotations.** Source images are read-only.
   Technical `dataset` stages keep source sidecars read-only as well. The requested
   `trainime` workflow explicitly creates missing source-side captions and removes
   matched captions on demand, after verified backup. It never overwrites an
   existing caption while tagging. Rejections remain records, not image moves or
   deletions. Derivatives and exports use separate paths. See
   [the Trainime workflow contract](TRAINIME.md).
2. **Separate evidence from presentation.** Source hashes, raw scores, model
   revisions, review decisions, normalized tags, and exported captions are distinct.
   Changing thresholds must not require repeating inference.
3. **Make reruns explainable.** Stage identity includes input hashes, configuration,
   code/preprocessing version, and model artifact hashes where applicable.
   Incomplete stages cannot masquerade as complete. Publish to a new run/snapshot.
4. **Keep one source of truth.** Manifests define membership and decisions; folder
   names are outputs. Content hashes identify bytes; relative paths identify source
   occurrences. Do not collapse different provenance or captions into one record.
5. **Start small.** Python 3.12, `uv`, Pillow, standard-library TOML, argparse,
   JSONL. Add ONNX/NumPy/Hub dependencies with tagging. Keep CPU and GPU runtime
   environments mutually exclusive. Avoid a GUI, server, or database until needed.
   DP02 establishes the need for an immutable SQLite ingest catalog; it does not
   replace the existing durable review store or add a database service.
6. **Match the training target through export profiles.** Danbooru-style captions
   are the first profile from the notes. A local natural-language caption adapter
   can be added later if a chosen model benefits. Neither format is universal.

## Pipeline and artifacts

```text
local originals + existing sidecars
  -> inventory + decode validation
  -> exact duplicates + near-duplicate candidates
  -> local tagger scores
  -> deterministic caption rules + review decisions
  -> related-image groups + train/validation assignments
  -> immutable image/caption export + QA report
  -> downstream trainer
```

### 1. Inventory and validation

Record every discovered file, full SHA256, byte count, decoded dimensions, stored
dimensions, format, mode, EXIF orientation, alpha, ICC presence, frame count, and
sidecar association. Retain non-images as skipped records. Catch corrupt/truncated
decodes; inspect dimensions before allocating decoded pixels. Distinguish decode
limits from training-resolution preferences.

No minimum compressed byte count. No blanket PNG conversion or square resize.
Small images, unusual modes, transparency, and color profiles become review
flags. Later derivatives will explicitly define EXIF correction, ICC conversion,
alpha background, interpolation, and output encoding. Large valid originals can
produce bounded derivatives; no automatic upscaling is planned.

Current `scan` implements this stage and exact byte duplicate identification.
It does not detect blank images, borders, watermarks, blur, or visual similarity.

### 2. Deduplication and related-image groups

Run exact SHA256 matching first. A later normalized-pixel hash can find metadata-only
variants; its decode/color/alpha policy must be versioned. Preserve source aliases
and caption conflicts.

Use pHash to propose nearby pairs, with an explicitly documented bit length and
maximum Hamming distance. Do not silently discard similar poses, edits, crops,
or alternate expressions. Use an index instead of all-pairs comparisons at scale.
The initial `dataset similarity` stage uses a versioned 64-bit DCT pHash, validates
source hashes against the inventory, and publishes pair proposals for human review.
Its default Hamming radius is 8 and can be changed per invocation. The threshold is
not calibrated for this collection; proposals never mutate or exclude source files.
`dataset similarity-evaluate` now measures saved related/distinct judgments against
all 65 radii, including manually reviewed pairs outside the proposal radius. It
retains the judged hashes and review revision, collapses exact-byte aliases, and
reports false matches, known misses and sample precision/recall. The pair reviewer
shares this evaluation and links errors back to image comparison. The bounded
[M2 pilot checkpoint](COMPLETED.md#m2-selected-pilot-similarity-evaluation) records
calibration/held-out measurements and leaves radius 8 unchanged; it does not
establish whole-collection accuracy. Unreviewed pairs are not presumed distinct.
Evaluate a local embedding model only if pHash misses important variants on the
pilot. An embedding threshold has its own metric and is not interchangeable with
a pHash threshold.

Review pairs to select keepers using resolution, artifacts, completeness, and
caption/provenance quality. File byte size is not a quality score. Preserve
related-image groups even when multiple variants are retained. Assign the entire
group to one split; include common source artwork/series identities when known.
Document transitive grouping so an A-B-C chain cannot silently erase C.

`dataset review` now records related/distinct relationships, including manual links
outside pHash proposals, and per-image include/exclude decisions. `dataset groups`
publishes the resulting connected components. Exact-byte aliases remain members;
distinct relationships that contradict a group are rejected before saving.
Exclusions are annotations and do not remove group members or source files.
See [the review contract](REVIEW.md) and [group-aware export](EXPORT.md).

### 3. Local tagging

Use WD v3 ONNX as the baseline candidate already named in the notes. SwinV2,
ViT-Large, and EVA02-Large now have selectable pinned profiles. Compare SwinV2
with EVA02 on the same pilot before declaring a quality winner. Camie v2 is a
researched candidate for a separate backend, not a compatible WD model file.
See [tagging research and implementation](TAGGING.md) for sources and commands.
The published benchmark scores do not establish accuracy on this collection.

Implemented M3 evaluation support now freezes an existing verified group-QA pilot
and explicit raw-label vocabulary, records present/absent/uncertain judgments
independently of predictions, and compares saved scores on identical membership.
Exact-byte aliases count once and known groups stay within one calibration or
held-out set. Fitting uses calibration judgments only; proposed cutoffs never
change configuration or captions. Human and assistant attribution remains explicit,
with assistant judgments excluded by default. NF05 now records a full source frame,
hash-ranked probability draw, aliases and separate verified partition groups;
explicit QA membership survives publication. Mechanism checks alone do not establish
review or acceptance; the 0.7.0 assistant judgments are recorded separately. See
[the evaluation contract](LABEL-EVALUATION.md) and
[delivered source evidence](COMPLETED.md#m3-reusable-label-evaluation).
When visual review corrects known related groups, `label-refresh` preserves the
same selected content, vocabulary and attributed judgment history in a new
workspace. Recomputed partitions remain a reuse of reviewed data, not a new
independent validation population.

Pin the chosen repository revision and hash both `model.onnx` and
`selected_tags.csv`; download both from the same revision. Model fetch is a
separate operation; inference can then run offline.

The publisher's reference composites alpha over white, pads to a square, resizes,
and supplies float32 BGR values in NHWC order. Preserve CSV row positions and use
explicit category indexes: general `0`, character `4`, rating `9`. Verify tensor
shape and label count; never silently truncate mismatches. Preserve special
emoticon spellings when replacing underscores. [Reference implementation](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py)

Keep raw scores separately from `.txt` output, including ratings and characters
that a caption profile omits. Start general thresholds at `0.35` for Swin/ViT and
`0.5296` for EVA02; keep character `0.85`. These are initial settings, not calibrated
guarantees. Per-tag overrides and score-only caption reruns are implemented. Support
batches and resumable inference keyed by content/model/preprocessing identity.
The model card documents a dynamic batch dimension and recommends release pins.
[SwinV2 model card](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3)

Expose `cpu`, `cuda`, and `auto`. Requested CUDA must fail clearly if unavailable;
`auto` must report its actual provider and any fallback. Record runtime/provider
versions. Choose the GPU package after inspecting installed hardware and the
official compatibility table; avoid installing CPU and GPU wheels together.
[ONNX Runtime installation](https://onnxruntime.ai/docs/install/)

### 4. Caption normalization and review

Produce captions from scores plus versioned rules and explicit per-image overrides.
Preserve imported captions separately. Never overwrite manual corrections on a
rerun. An override records the source hash, rule version, reason, and decision.

Manual overrides are implemented in the separate review store and copied into
group snapshots. They survive scan/similarity reruns when source path and content
match. Editing a generated draft does not save an override; use `dataset review`.
Export now applies overrides before original sidecars and optional model drafts.

Default forced tags and trigger are empty. A user-defined trigger is text; it is
not necessarily a single tokenizer token. Keep character tags opt-in for the
initial profile. Keep quality/content findings available even when a profile
omits them from training captions.

Flag contradictory counts rather than assuming the largest score is correct.
Keep composition groups neutral (`single_subject`, `multiple_subjects`, `unknown`)
until reliable labels and explicit subset rules exist. Two people do not establish
a relationship. Missing nudity tags on clothed images are expected.

Make explicit include/exclude decisions possible by source path and hash. Content
ratings and filename blocklists cannot establish character age or replace review.
Do not present the missing `safety.py` from the notes as an implemented classifier.

M4 rule semantics: `captions.trigger` prefixes one literal caption phrase and
`captions.force_tags` appends literal phrases, both empty by default. Configured
additions never become scored observations. `captions.subset_rules` use explicit
`all_tags`/`any_tags`/`none_tags` predicates over thresholded raw model names;
`expect_tags` reports missing evidence only for matched rules. One match proposes
a subset; overlapping matches require review rather than first-rule selection.
Neutral composition and conflict findings retain scored evidence even when caption
rules omit those tags. Proposals remain distinct from human subset annotations;
only reviewed annotations drive semantic splits. Score-only recaptioning regenerates
these proposals without editing saved reviews. QA and export retain the rule identity.

### 5. Split, export, and trainer adapters

Implemented: seeded whole-group allocation toward the requested image ratio,
immutable copy publication, independent verification, and separate Kohya train/
validation configurations. A pinned trainer import now checks actual upstream
discovery, captions, repeats, buckets, and CPU tensors. Reviewed labels and subsets
now feed deterministic semantic group balancing, with coverage and imbalance reports.
See [export commands](EXPORT.md).

Default provisional validation ratio: 5%, seed `20261011`. Group before splitting.
Use group-level deterministic assignment with balancing across configured labels;
report actual ratios, rare strata, and conflicts. A target ratio can be impossible
for tiny groups. Freeze assignments for a released snapshot; changed inputs create
a new snapshot rather than silently moving existing validation members.

Export only explicitly eligible records with nonempty captions. Require zero
cross-split related groups, exact duplicates, orphan captions, filename collisions,
and unresolved blocking decisions. Name pairs using stable unique IDs; preserve
original paths in the export manifest. Copy/re-encode to exports; avoid hardlinks
that allow a trainer/editor to mutate source bytes.

Preserve aspect ratios. Configure bucketing and repeats in the trainer adapter,
not in the captions. The first adapter should produce a Kohya dataset TOML with
explicit subsets, `caption_extension`, resolution, bucketing, and `num_repeats`;
verify it against a pinned trainer revision. A sidecar directory alone is not
proof that every trainer imports it correctly. [Kohya dataset configuration](https://github.com/kohya-ss/sd-scripts/blob/main/docs/config_README-en.md)

### 6. Report and QA

Implemented: [`dataset qa` and `qa-list`](QA.md) publish a deterministic
pilot and navigate image previews, caption origins/findings, reviewed annotations,
groups, and category coverage. Group reports preview assignments; verified export
reports preserve published assignments. `dataset review-ui` records caption and
critical-label judgments, notes, and explicit pilot conclusions in a separate
assessment history; `dataset assessment` exposes these results in the CLI.
Snapshot reports now aggregate reviewed content, model composition/subset proposals,
rating distributions, observed/selected top tags, and pinned model/provider/rule
provenance for both all members and explicitly included members. Export reports use
frozen evidence; unavailable observations remain explicit. The 0.7.0 continuation
records bounded assistant label/caption measurements on the selected collection.
General accuracy and human acceptance remain unestablished; tokenizer checks are
conditional on an actual target profile.

Count reconciliation now compares intake eligibility, grouped/reviewed membership,
snapshot identities, tagging coverage, split counts and export pairs. Stage receipts
record monotonic processing time and logical payload bytes, and travel with exports
for offline QA. Inventory timing includes scanning; reuse/publication-only paths are
identified separately. These facilities enable the M6 batch measurements; they do
not establish representative-collection acceptance by themselves.

Report one run/snapshot: decision counts, dimensions/aspect ratios, exact/near
duplicate groups, content/rating distributions, top tags, label conflicts,
caption lengths, overrides, splits, and model/provider provenance. Later add
target-profile tokenizer lengths and truncation checks.

Use a fixed pilot of about 50 representative images plus targeted problem cases:
portrait/landscape, different compositions, clothed/nude, transparency, small and
large images, duplicates, and existing sidecars. Write a reproducible local QA
sample with IDs and captions. Review critical labels against the images and
measure errors per label. A contact sheet alone does not establish correctness.

ComfyUI remains optional for spot checks. If it disagrees, compare model revision,
preprocessing, provider, and thresholds against the reference; do not automatically
trust either implementation. Training quality remains a separate evaluation after
the preparation pipeline passes its own checks.

## Local layout

```text
config.toml
src/image_dataset_train/
tests/
data/                         # ignored; may use an external source instead
  00_inbox/                   # untouched local inputs
  runs/<run-id>/              # inventory/reports, then later stage evidence
  models/                    # pinned local model artifacts
  derived/scores/            # reusable complete score vectors
  reviews/                   # persistent image/pair decisions and caption overrides
  exports/<snapshot-id>/     # verified train/validation image-caption pairs
.cache/                       # ignored repository-local tooling cache
```

Only the implemented settings appear in `config.toml`. Extend the schema with
each stage rather than accepting configuration that silently does nothing.

## Work order and completion boundaries

| Milestone | Deliverable | Acceptance evidence |
| --- | --- | --- |
| M1: intake | Installable CLI, strict config, inventory, validation, exact duplicates, report | Source hashes unchanged; corrupt/animated files handled; EXIF dimensions correct; complete hashes; stable reruns; caption collisions detected; build and CLI pass. |
| M2: similarity | Pair proposals, grouping, review records | Representative positive/negative pairs; no automatic loss of unique variants; performance measured at expected collection size. |
| M3: tagging | Pinned model fetch, reference preprocessing, CPU inference, optional GPU, raw score cache | Offline smoke run; category/index and tensor checks; reference parity; changed rules reuse scores; interrupted run resumes correctly. |
| M4: captions and review | Normalization, overrides, subset rules, local QA artifacts | Nonempty accurate pilot captions; overrides survive reruns; disagreements and exclusions visible. |
| M5: export | Group-aware split, immutable pairs, manifest and trainer adapter | No group leakage/collisions/missing captions; changed sources rejected; trainer import smoke test. |
| M6: full collection | Qualified batch run and dataset QA | Counts reconcile; time/disk measured; pilot errors addressed; user review recorded. Training results remain separate. |

M1 and the tagging execution contract are tested with generated fixtures; pinned
SwinV2 CPU inference and reference preprocessing also have local smoke evidence.
The M2 pHash proposal stage has generated-fixture regression coverage and an
isolated wheel execution check, recorded in [the completion log](COMPLETED.md).
Durable decisions, manual
overrides, and group snapshots have generated-fixture integration coverage.
The bounded [M2 selected-pilot evaluation](COMPLETED.md#m2-selected-pilot-similarity-evaluation)
now records reviewed pair metrics, preservation and measured pilot performance.
It does not establish independent human review, complete decisions for every pilot
proposal or general collection accuracy. M3 was the next unfinished acceptance
milestone at that checkpoint. The 0.7.0 continuation completes bounded
M3 measurement and assistant caption corrections; the next required acceptance is
the existing M4 human conclusion. M3-M6 require representative reviewed examples
before quality claims,
and performance claims remain scoped to their measured inputs. The code should
not search unrelated directories for images. Baseline work continues using these
defaults; target-specific choices are recorded when an actual export profile is
introduced.

## Sources checked

Primary references checked on 2026-10-11. These are engineering references, not
local execution or dataset-quality evidence.

- [WD SwinV2 v3](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3): baseline and release-pinning guidance.
- [WD ViT-Large v3](https://huggingface.co/SmilingWolf/wd-vit-large-tagger-v3): comparison candidate; no claim of universal superiority.
- [Publisher inference code](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py): input processing and category indexes.
- [ONNX Runtime CUDA requirements](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html): runtime compatibility must be checked at installation.
- [Pillow image API](https://pillow.readthedocs.io/en/stable/reference/Image.html): lazy loading, verification, and decompression-bomb handling.
- [Kohya dataset configuration](https://github.com/kohya-ss/sd-scripts/blob/main/docs/config_README-en.md): exporter contract.

## End-of-document handoff

The representative assistant continuation uses NF05 probability sampling over all
readable source content, with caption applicability tracked separately for content
without a training derivative. Freeze the frame and draw before visual review;
retain every alias, exact inclusion probabilities and prior-exposure evidence.
Use verified conservative grouping for partitions without turning training exclusion
into sampling exclusion. Selection and partition seeds have separate meanings.
Any unknown prior exposure limits held-out claims; no threshold adoption follows
from a merely group-disjoint assistant diagnostic. The prepared-only draft draw is
retained as a superseded scope proposal, never silently replaced or cherry-picked.

NF06 snapshot comparison is delivered for this correction batch: verified old/new
exports show 46 caption edits, two family-merge events and no membership, media or
split changes. The reusable command also compares group snapshots and publishes
portable replayable evidence. It does not establish model quality,
human acceptance or silently expand the other conditional proposals.

Use this plan together with [IDENTIFIED.md](IDENTIFIED.md) to maintain
[SHELVED.md](SHELVED.md) in milestone order. Pull the next active task from SHELVED
into [TODO.md](../TODO.md); preserve the acceptance boundaries above. A queued
improvement does not automatically add a required milestone or change product scope.

The current plan remains **open**: the existing M4–M6 human dataset acceptance is
outstanding. Representative assistant review, bounded M3 measurement, corrected
publication/import and the 0.6.0 operational phase are complete within their stated
scope. They do not establish independent human review or larger-collection quality.
Record actual completion evidence in [COMPLETED.md](COMPLETED.md). Until every
required milestone's acceptance is satisfied, continue the SHELVED → TODO →
COMPLETED handoff. Only then close this cycle and run another IDENTIFIED workflow.
