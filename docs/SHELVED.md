# Shelved work — milestone-ordered queue

<!--
WORKFLOW_UTILIZED: "MIVIM.spec":"SHELVE"
WORKFLOW_CYCLE: dataset-preparation-2026-10-11
WORKFLOW_UPSTREAM: IDENTIFIED.md + PLAN.md
WORKFLOW_DOWNSTREAM: ../TODO.md
-->

Updated **2026-11-09**. This queue incorporates all **100 actionable findings**
from [IDENTIFIED.md](IDENTIFIED.md), ordered by the responsibilities and acceptance
sequence in [PLAN.md](PLAN.md#work-order-and-completion-boundaries). Original
finding IDs, priorities, proposal/conditional scope and actions are retained.
[TODO.md](../TODO.md) remains the active task list; [COMPLETED.md](COMPLETED.md)
holds completed work and its evidence.

## Workflow contract

```text
[IDENTIFIED + PLAN] -> [SHELVED] -> [TODO] -> [COMPLETED]
                           ^          |
                           +----------+
                      next bounded task batch

All required PLAN acceptance complete -> next IDENTIFIED cycle
```

| Document | Responsibility | Read before its next action |
| --- | --- | --- |
| [IDENTIFIED.md](IDENTIFIED.md) | Findings and source evidence for the current review cycle | PLAN scope and COMPLETED evidence; do not run a new IDENTIFY cycle until the current PLAN is complete |
| [PLAN.md](PLAN.md) | Authoritative scope, milestone order and acceptance boundaries | Existing authorized design and the current findings; a queued proposal does not silently amend the plan |
| SHELVED.md | Traceable, ordered candidates and their queue state | IDENTIFIED findings plus PLAN milestones, reconciled against TODO and COMPLETED |
| [TODO.md](../TODO.md) | The currently scheduled unfinished work | SHELVED for each next task/batch and PLAN for its acceptance boundary |
| [COMPLETED.md](COMPLETED.md) | Delivered changes, dates, verification and qualification limits | Completed TODO steps and actual evidence, then return to TODO or SHELVED |

**TODO completion is a handoff, not a new audit trigger.** When its active work
finishes, archive the completed steps, reconcile queue states and pull the next
eligible tasks from this document. Do not copy the whole queue into TODO.

### States, priority and source identity

- **active:** the existing TODO already schedules the finding's acceptance outcome.
  It does not mean that outcome or every supporting implementation is complete.
- **queued:** a candidate available for a future bounded task. It is not currently
  scheduled and does not reopen a completed milestone by itself.
- **conditional:** wait for the stated need, selected target or demonstrated failure.
  Do not treat this as an unconditional requirement or silently mark it complete.
- **completed:** use only after delivery and the relevant acceptance evidence;
  retain the ID here with a link to its dated COMPLETED entry when that happens.

P1/P2/P3 and Plan support/Proposal/Conditional come from IDENTIFIED unchanged.
Plan support is a relationship to a requirement, not proof that one particular
implementation approach is mandatory. Each finding appears once under its primary
milestone; shared helpers may also support later stages.

If a finding overlaps an active TODO outcome, extend that task's provenance rather
than creating a duplicate. Related findings can form one task with several source
IDs. Keep actual task state in TODO/COMPLETED and reconcile this queue when changing it.

### Current handoff

Continue [the existing TODO](../TODO.md#remaining-work-against-the-existing-plan).
M2 is the earliest open acceptance milestone. Its current pair-calibration task
maps to **CF01**. If that task needs reusable evaluation sets or a fixed pilot,
consider **NF01**, **NF05** and **CF02** as bounded supporting tasks before making
threshold claims; **TM01** supports the required measurements. They remain queued
until explicitly scheduled in TODO.

When collection evidence is unavailable, record that dependency and work on an
eligible source-code enabler within the current milestone. Do not claim acceptance,
skip dependent milestones, search unrelated image folders or start another IDENTIFY
cycle merely because the current acceptance task cannot yet finish.

## Promotion and completion

1. Read the active TODO and its PLAN acceptance boundary. Finish its scheduled work
   first; link any necessary queued enabler before implementing it.
2. On active-batch completion, read this queue in M1–M6 order, starting with the
   earliest unfinished required milestone. Delivered M1 foundations and conditional
   enhancements must not displace M2 merely because they appear earlier in the file.
3. Choose the smallest coherent eligible action or related set. Carry its IDs,
   milestone, dependency, intended outcome and proportionate verification into TODO.
   Preserve existing tasks; change only the scope needed for the selected work.
4. Mark the corresponding queue item active. Prioritize working core source changes
   where implementation is needed; do not substitute documentation/tests for delivery.
5. After completion, move the steps, dates and evidence to COMPLETED, remove them
   from the active TODO, and mark the queue item completed with the completion link.
   If only part is done, record that scope and keep the remainder open.
6. Replenish TODO from SHELVED while the PLAN remains open. An empty TODO, passing
   fixtures or finished source implementation does not establish PLAN completion.
7. Only after **all required PLAN milestones and acceptance evidence** are complete,
   close the cycle in COMPLETED and run the next IDENTIFIED workflow. Reconcile any
   remaining optional candidates into that next cycle without discarding their IDs
   or history. Optional proposals do not silently expand the current PLAN.

<a id="m1"></a>

## M1 — Intake, configuration and operational foundations

Source: [PLAN](PLAN.md#1-inventory-and-validation). Active context:
[TODO](../TODO.md#outstanding-interface-and-platform-qualification).

M1's required source work is already delivered. These are supporting proposals, not a reopened M1 gate. Promote one only when it materially supports an active milestone or an authorized operational improvement. Preserve the separate Trainime menu and explicit source-caption semantics.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf17"></a>[CF17](IDENTIFIED.md#cf17) | P2 / Proposal | queued | **Improve useful recovery after interruption.** Surface verified cached progress, retained pending artifacts and the exact remaining action for each stage. Treat inference resume, publication retry and repair resume distinctly. |
| <a id="nf07"></a>[NF07](IDENTIFIED.md#nf07) | P2 / Proposal | queued | **Collection/run catalog.** Offer a local catalog of explicitly registered collections and their existing runs, current review revisions, exports and receipts. It should never discover unrelated image directories automatically. |
| <a id="nf08"></a>[NF08](IDENTIFIED.md#nf08) | P2 / Proposal | queued | **Caption restore.** Add a direct restore command for a selected removal receipt, with preview and per-file results; retain newly created captions and require an explicit decision for conflicts. Keep the four-choice Home menu intact. |
| <a id="nf14"></a>[NF14](IDENTIFIED.md#nf14) | P2 / Proposal | queued | **Storage inventory and retention preview.** Report models, caches, snapshots, backups and pending runs by ownership and referenced status. Any cleanup is a separate explicit operation, not automatic backup expiry. |
| <a id="qol12"></a>[QOL12](IDENTIFIED.md#qol12) | P2 / Proposal | queued | **Progress with meaningful units.** Report images processed, bytes copied, pairs produced or receipts checked where known; reserve indeterminate progress for phases without a defensible total. |
| <a id="qol13"></a>[QOL13](IDENTIFIED.md#qol13) | P2 / Proposal | queued | **Copyable path and command actions.** Provide consistent copy controls for run paths, exports, reports and exact CLI equivalents, using the existing shell quoting helpers for spaces and Unicode. |
| <a id="qol14"></a>[QOL14](IDENTIFIED.md#qol14) | P2 / Proposal | queued | **Run selection without path transcription.** Build on NF07 with source/stage/date filters and visible input identity; avoid unsafe implicit “latest run” selection across different collections. |
| <a id="qol18"></a>[QOL18](IDENTIFIED.md#qol18) | P2 / Proposal | queued | **Recovery operation browser.** List caption-removal and collision-repair receipts with affected paths and recovery locations, connecting diagnosis output directly to NF08/NF10 without adding Home menu choices. |
| <a id="sc03"></a>[SC03](IDENTIFIED.md#sc03) | P2 / Proposal | queued | **Shared bounded source reads.** Consolidate repeated source-path containment, link, byte-limit and SHA checks while retaining each stage's explicit decode/preprocessing limits and source-availability contract. |
| <a id="sc04"></a>[SC04](IDENTIFIED.md#sc04) | P2 / Proposal | queued | **One atomic JSON primitive.** Reconcile `model_bundle` and `diagnostics` writers, including encoding, temporary-file cleanup and durability expectations; route callers through the common implementation. |
| <a id="sc05"></a>[SC05](IDENTIFIED.md#sc05) | P2 / Proposal | queued | **Typed artifact records.** Introduce lightweight typed records or TypedDicts for stage metadata, captions, reviews, split plans and receipts at subsystem boundaries; avoid a wholesale framework migration. |
| <a id="sc07"></a>[SC07](IDENTIFIED.md#sc07) | P2 / Proposal | queued | **Smaller CLI handlers.** Separate parsing from stage handlers and rendering in `cli.py`; keep command names, flags and exit semantics stable. |
| <a id="sc11"></a>[SC11](IDENTIFIED.md#sc11) | P2 / Proposal | queued | **Shared operation primitives.** Move path rechecks, journals and short commit handling out of private `operations.py` imports used by collision repair, retaining the same source-lock and recovery behavior. |
| <a id="sc12"></a>[SC12](IDENTIFIED.md#sc12) | P2 / Proposal | queued | **Real immutable configuration values.** Normalize mutable collections inside frozen settings to immutable forms or defensive copies, so a validated configuration cannot be modified unexpectedly through a list reference. |
| <a id="sc13"></a>[SC13](IDENTIFIED.md#sc13) | P2 / Proposal | queued | **Common run publication lifecycle.** Factor allocation, completion metadata and staged publication into a small shared utility; keep stage-specific evidence and partial-run retention explicit. |
| <a id="sc16"></a>[SC16](IDENTIFIED.md#sc16) | P2 / Proposal | queued | **Structured operational errors.** Use stable error codes and contextual fields where diagnosis currently depends on exception text; preserve readable original causes in logs. |
| <a id="sc17"></a>[SC17](IDENTIFIED.md#sc17) | P2 / Proposal | queued | **Consistent executable provenance.** Record build/source identity in new stage receipts, including QA, so multiple feature sets carrying version 0.5.1 can be distinguished without interpreting timestamps alone. |
| <a id="sc20"></a>[SC20](IDENTIFIED.md#sc20) | P2 / Proposal | queued | **Remove stale implementation claims in source comments.** Correct narrow inaccuracies such as the model module's “only stage” network claim and generic resume messages; derive practical help from actual stage behavior. |
| <a id="tm03"></a>[TM03](IDENTIFIED.md#tm03) | P2 / Proposal | queued | **Inventory streaming interface.** Separate discovery/inspection iteration from association/duplicate indexing, enabling large scans to publish records without requiring one growing Python object list. |
| <a id="tm04"></a>[TM04](IDENTIFIED.md#tm04) | P2 / Proposal | queued | **Incremental inventory indexes.** Reuse prior discovery data for planning, but retain content verification where snapshots depend on exact bytes; do not substitute size/mtime equality for SHA identity. |
| <a id="tm19"></a>[TM19](IDENTIFIED.md#tm19) | P2 / Proposal | queued | **Platform qualification matrix.** Exercise real filesystem behavior for Windows junctions, permitted symlinks, case variants and installed recovery on supported hosts; do not infer ARM64 or Linux installer support from imports. |
| <a id="cf20"></a>[CF20](IDENTIFIED.md#cf20) | P3 / Conditional | conditional | **Additional quality findings.** Consider calibrated blur, border, watermark or blank-image proposals only after representative errors justify them; retain evidence and review decisions instead of automatic rejection rules. |

<a id="m2"></a>

## M2 — Similarity, pair evaluation and related groups

Source: [PLAN](PLAN.md#2-deduplication-and-related-image-groups). Active context:
[TODO](../TODO.md#m2--similarity-calibration-and-collection-performance).

Current earliest unfinished milestone. Prioritize representative pair selection, judgments, threshold evidence and collection-scale measurements. Evaluation-set tooling and graph explanations can support that work; embeddings remain conditional on demonstrated pHash misses.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf01"></a>[CF01](IDENTIFIED.md#cf01) | P1 / Plan support | active | **Establish representative M2 calibration.** Use NF01 to review known related and distinct pairs across artwork styles, edits, crops and compressions; include examples the original proposal radius missed. |
| <a id="cf02"></a>[CF02](IDENTIFIED.md#cf02) | P1 / Plan support | queued | **Separate threshold fitting from evaluation.** Fit pHash radius on the calibration set and report behavior on the held-out set, preserving sample sizes and undefined metrics instead of selecting the best-looking sweep row. |
| <a id="cf03"></a>[CF03](IDENTIFIED.md#cf03) | P1 / Plan support | queued | **Make graph conflicts explainable.** Show the actual related/exact path connecting a disputed distinct pair, so a reviewer can correct the specific mistaken relationship without dismantling a whole group blindly. |
| <a id="nf01"></a>[NF01](IDENTIFIED.md#nf01) | P1 / Plan support | queued | **Pair evaluation sets.** Add an explicitly saved M2 calibration/held-out pair set, including manually selected pairs outside proposals, so the existing threshold sweep has a reproducible evaluation population. |
| <a id="nf05"></a>[NF05](IDENTIFIED.md#nf05) | P1 / Plan support | queued | **Frozen representative pilot membership.** Let a reviewer pin the pilot and add targeted cases, retaining selection reasons and unchanged membership across model and caption comparisons. |
| <a id="qol01"></a>[QOL01](IDENTIFIED.md#qol01) | P1 / Plan support | queued | **Evaluation evidence coverage.** Extend the existing positive/negative and evidence-gap counts with calibration/held-out membership and case-type coverage, so reviewers can see which kinds of pair remain untested. |
| <a id="tm01"></a>[TM01](IDENTIFIED.md#tm01) | P1 / Plan support | queued | **Collection benchmark harness.** Add a small runner for explicitly chosen inputs that records stage invocation, item counts, cache state, environment and metrics. It supports CF09 without pretending fixtures measure accuracy. |
| <a id="qol05"></a>[QOL05](IDENTIFIED.md#qol05) | P2 / Proposal | queued | **Better pair inspection.** Add synchronized zoom/pan and original-size toggles to compare crops, small edits and artifacts while retaining whole-image context. |
| <a id="sc08"></a>[SC08](IDENTIFIED.md#sc08) | P2 / Proposal | queued | **Decouple review graph computation.** Expose a tested public grouping/conflict service used by status, publication and evaluation instead of spreading dependencies on private review helpers. |
| <a id="tm05"></a>[TM05](IDENTIFIED.md#tm05) | P2 / Proposal | queued | **pHash feature reuse.** Cache fingerprints by content and preprocessing version so threshold experiments do not repeatedly decode unchanged images. Record cache identity in similarity runs. |
| <a id="tm06"></a>[TM06](IDENTIFIED.md#tm06) | P2 / Proposal | queued | **Dense-neighborhood diagnostics.** Report candidate fan-out, index/query time and estimated output growth, allowing an explicit partial exploratory run when requested. Never label truncated proposal output as complete. |
| <a id="tm11"></a>[TM11](IDENTIFIED.md#tm11) | P2 / Proposal | queued | **Versioned graph cache.** Store/reuse exact-alias and reviewed relation components for matching inventory/relation revisions, reducing repeated graph work in status and image saves without hiding conflicts. |
| <a id="nf15"></a>[NF15](IDENTIFIED.md#nf15) | P3 / Conditional | conditional | **Normalized-pixel duplicate candidates.** Add the later PLAN option for metadata-only variants after defining a versioned decode/color/alpha policy. Preserve occurrence provenance and conflicting captions. |
| <a id="nf16"></a>[NF16](IDENTIFIED.md#nf16) | P3 / Conditional | conditional | **Embedding similarity.** Add a separately measured backend only if reviewed pilot misses show pHash is insufficient; keep its metric and threshold distinct from Hamming distance. |
| <a id="nf20"></a>[NF20](IDENTIFIED.md#nf20) | P3 / Conditional | conditional | **Artwork/source identity metadata.** Add explicit reviewed artwork/series/source identifiers when available so known shared origins can assist leakage review. Do not infer them from arbitrary folder names. |

<a id="m3"></a>

## M3 — Local tagging, model comparison and calibration

Source: [PLAN](PLAN.md#3-local-tagging). Active context:
[TODO](../TODO.md#m3--tagging-quality-comparison-and-runtime-qualification).

Use the same selected pilot after M2 grouping evidence. Build comparison/ground-truth support where needed, then measure label quality, thresholds, memory and provider behavior. No alternate backend becomes required merely by appearing here.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf04"></a>[CF04](IDENTIFIED.md#cf04) | P1 / Plan support | active | **Measure label precision and recall.** Use NF03 predicted and actual presence to compute TP/FP/FN, denominators and per-label results; keep unreviewed/uncertain examples outside unsupported accuracy claims. |
| <a id="cf05"></a>[CF05](IDENTIFIED.md#cf05) | P1 / Plan support | active | **Compare models under the same conditions.** Use NF02 to measure composition errors and critical-label behavior on identical inputs, with pinned preprocessing/providers and cold/warm timing distinguished. |
| <a id="cf06"></a>[CF06](IDENTIFIED.md#cf06) | P1 / Plan support | active | **Calibrate caption thresholds on reviewed evidence.** Evaluate per-tag rules and character policy on a held-out pilot before changing defaults; retain disagreements instead of unioning every model prediction. |
| <a id="nf02"></a>[NF02](IDENTIFIED.md#nf02) | P1 / Plan support | queued | **Same-pilot model comparison.** Run SwinV2 and EVA02 against identical selected image identities and produce one comparison artifact for quality, disagreement, runtime and memory. Reuse existing model profiles and caches. |
| <a id="nf03"></a>[NF03](IDENTIFIED.md#nf03) | P1 / Plan support | queued | **Label ground-truth workspace.** Record actual presence, absence and uncertainty for chosen critical labels, separately from inclusion, caption checks and predicted tags. Supply the missing inputs to M3 accuracy metrics. |
| <a id="nf04"></a>[NF04](IDENTIFIED.md#nf04) | P1 / Plan support | queued | **Calibration results as reusable profiles.** Save approved per-tag thresholds, model/rule identity and evaluation-set provenance as an explicit profile. Adoption remains deliberate; the evaluator must not silently rewrite config. |
| <a id="qol02"></a>[QOL02](IDENTIFIED.md#qol02) | P1 / Plan support | queued | **Side-by-side model disagreements.** In NF02 comparisons, open the same image with each model's scores/caption changes and direct critical-label judgment controls; avoid making reviewers reconcile separate run folders. |
| <a id="qol03"></a>[QOL03](IDENTIFIED.md#qol03) | P1 / Plan support | queued | **Critical-label checklist.** Present the selected evaluation vocabulary consistently, including absent/uncertain ground truth, while keeping ordinary caption correction separate from evaluation. |
| <a id="sc01"></a>[SC01](IDENTIFIED.md#sc01) | P1 / Plan support | queued | **Separate score iteration from caption publication.** Refactor `tagging.py` to consume persisted vectors incrementally instead of requiring every vector in one dictionary; retain duplicate reuse and self-contained artifacts. |
| <a id="cf16"></a>[CF16](IDENTIFIED.md#cf16) | P2 / Proposal | queued | **Avoid unnecessary preprocessing allocations.** Investigate memory-bounded padding/resizing for extreme aspect ratios while verifying parity with the versioned WD/pHash preparation; do not silently alter image semantics. |
| <a id="tm07"></a>[TM07](IDENTIFIED.md#tm07) | P2 / Proposal | queued | **Score artifact iterator.** Supply checked lazy vector reads and bounded write batches for SC01; make cache repair and self-contained run copying use the same score checksum/index contract. |
| <a id="tm08"></a>[TM08](IDENTIFIED.md#tm08) | P2 / Proposal | queued | **Measured inference tuning.** Add per-batch timing, effective batch/provider records and optional explicit batch backoff after memory failures, without turning requested CUDA into an undisclosed CPU run. |
| <a id="nf17"></a>[NF17](IDENTIFIED.md#nf17) | P3 / Conditional | conditional | **Another local caption backend.** Investigate Camie or a target-appropriate natural-language backend only after baseline evaluation, with its own vocabulary, preprocessing, model pin and compatibility review. |

<a id="m4"></a>

## M4 — Caption rules, durable correction and review

Source: [PLAN](PLAN.md#4-caption-normalization-and-review). Active context:
[TODO](../TODO.md#m4--representative-caption-and-subset-acceptance).

Review actual captions and subset suitability using the M2/M3 evidence. Improve correction throughput and persistence where they impede that review; preserve overrides, reasons, revisions and human-versus-model distinctions.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf07"></a>[CF07](IDENTIFIED.md#cf07) | P1 / Plan support | active | **Qualify caption/subset semantics.** Review trigger/forced phrase suitability, contradictory counts, overlapping subset predicates and missing expectations on the selected M4 pilot; record corrections and reasons. |
| <a id="cf19"></a>[CF19](IDENTIFIED.md#cf19) | P2 / Proposal | queued | **Portable review continuation.** Combine NF09 relocation with compatible lineage resolution so a moved collection can continue review without rewriting historical exports or misapplying old decisions to changed images. |
| <a id="nf09"></a>[NF09](IDENTIFIED.md#nf09) | P2 / Proposal | queued | **Source relocation.** Rebind a collection to a new root using relative paths and verified content identities, preserving aliases and review history without assuming that matching filenames establish continuity. |
| <a id="nf10"></a>[NF10](IDENTIFIED.md#nf10) | P2 / Proposal | queued | **Review history viewer.** Show the changes to an image/pair and allow an explicit revert that creates a new review revision rather than erasing the original decision history. |
| <a id="nf11"></a>[NF11](IDENTIFIED.md#nf11) | P2 / Proposal | queued | **Reviewed bulk annotation.** Apply a label/subset or decision to an explicitly selected set of images, with visible selection and one coherent recorded action. Do not add automatic “accept all model tags” behavior. |
| <a id="qol04"></a>[QOL04](IDENTIFIED.md#qol04) | P2 / Proposal | queued | **Broader keyboard workflow.** Preserve existing arrow/j/k image navigation; add discoverable pair-comparison and save-and-next shortcuts with clear focus behavior and no activation while typing captions or notes. |
| <a id="qol06"></a>[QOL06](IDENTIFIED.md#qol06) | P2 / Proposal | queued | **Visible membership before bulk edits.** For NF11, show the actual selected paths and count independently of the current filter, making it easy to see what an operation will change. |
| <a id="qol07"></a>[QOL07](IDENTIFIED.md#qol07) | P2 / Proposal | queued | **Saved review filters.** Retain named filter combinations, last image and queue position per report; distinguish these browsing preferences from durable review decisions. |
| <a id="qol08"></a>[QOL08](IDENTIFIED.md#qol08) | P2 / Proposal | queued | **More actionable empty states.** Explain whether an empty queue means no data, filtered-out data, no unresolved pairs or unavailable previews, with a direct way to reach the relevant populated view. |
| <a id="qol09"></a>[QOL09](IDENTIFIED.md#qol09) | P2 / Proposal | queued | **Caption comparison view.** Display manual override, source sidecar and current draft together, with precedence and changed phrases visible before the reviewer saves a correction. |
| <a id="qol10"></a>[QOL10](IDENTIFIED.md#qol10) | P2 / Proposal | queued | **Stale snapshot explanation.** Extend existing revision and unchanged-snapshot notices with a list of affected images/pairs and a direct path to republishing them; preserve the old report as historical evidence. |
| <a id="sc09"></a>[SC09](IDENTIFIED.md#sc09) | P2 / Proposal | queued | **Avoid graph rebuilds for unrelated edits.** Make caption or annotation changes reuse the graph for the same relation revision, while pair changes still trigger the required consistency calculation. |
| <a id="sc10"></a>[SC10](IDENTIFIED.md#sc10) | P2 / Proposal | queued | **Separate review current state from growing history.** Design bounded current-state reads and append-only history/checkpoints after measuring save latency. Preserve atomic revision semantics and existing-store migration. |
| <a id="sc14"></a>[SC14](IDENTIFIED.md#sc14) | P2 / Proposal | queued | **Explicit frontend state boundaries.** Separate report, correction, assessment, pair and publication state from shared globals; retain the lightweight static-report architecture rather than adding a framework by default. |
| <a id="sc15"></a>[SC15](IDENTIFIED.md#sc15) | P2 / Proposal | queued | **Shared frontend request handling.** Centralize JSON errors, stale response handling and revision conflicts across browser panels while allowing each form to preserve its unsaved edits. |
| <a id="tm09"></a>[TM09](IDENTIFIED.md#tm09) | P2 / Proposal | queued | **Caption rule explanations.** Return a compact decision trace for why a tag was selected, dropped, near threshold or used by a subset rule. Keep this derived evidence separate from the exported caption text. |
| <a id="tm10"></a>[TM10](IDENTIFIED.md#tm10) | P2 / Proposal | queued | **Annotation vocabulary support.** Add optional preferred labels/aliases and unknown-label reporting to `annotations.py`; retain free-form reviewed data and distinguish aliases from automatic semantic equivalence. |
| <a id="tm18"></a>[TM18](IDENTIFIED.md#tm18) | P2 / Proposal | queued | **Review-store persistence boundary.** Define a narrow storage interface before choosing JSON checkpoints or SQLite for measured scale needs; preserve revision locking, history and readable export snapshots. |

<a id="m5"></a>

## M5 — Group splits, verified exports and trainer imports

Source: [PLAN](PLAN.md#5-split-export-and-trainer-adapters). Active context:
[TODO](../TODO.md#m5--representative-export-and-trainer-import-acceptance).

Qualify the existing export/import path with reviewed M2–M4 inputs. Diagnostic, recovery and adapter proposals support that path. A new trainer, tokenizer profile or graphical import launcher is conditional, not missing baseline M5 implementation.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf08"></a>[CF08](IDENTIFIED.md#cf08) | P1 / Plan support | active | **Reuse the same accepted pilot downstream.** Carry the approved M2–M4 image identities into M5 export/import checks, linking observed failures to the exact input, caption and configuration that produced them. |
| <a id="cf11"></a>[CF11](IDENTIFIED.md#cf11) | P2 / Proposal | queued | **Improve split diagnostics before changing algorithms.** Quantify the ratio/category objective and explain impossible single-group strata, so users can distinguish structural limits from a heuristic that stopped early. |
| <a id="cf12"></a>[CF12](IDENTIFIED.md#cf12) | P2 / Proposal | queued | **Compare bounded split candidates.** Offer a deterministic technical preview of a small set of seeds/search budgets; report tradeoffs and freeze the chosen assignments. Do not silently reshuffle a published export. |
| <a id="cf13"></a>[CF13](IDENTIFIED.md#cf13) | P2 / Proposal | queued | **Reviewed assignment constraints.** If evaluation requires keeping a specific group in a split, allow explicit group constraints with provenance and coverage reporting; reject contradictory constraints instead of breaking groups. |
| <a id="cf18"></a>[CF18](IDENTIFIED.md#cf18) | P2 / Proposal | queued | **Address content-color policy deliberately.** Define an ICC conversion option for training derivatives, preserving original hashes and conversion provenance. Keep existing `png-exif-white-v1` outputs reproducible. |
| <a id="nf06"></a>[NF06](IDENTIFIED.md#nf06) | P2 / Proposal | queued | **Snapshot comparison.** Compare two group/export snapshots by added/removed identities, caption edits, annotations, group merges and split moves, so changed training inputs can be understood without diffing raw JSONL. |
| <a id="nf12"></a>[NF12](IDENTIFIED.md#nf12) | P2 / Proposal | queued | **Named caption/export profiles.** Save technical workflow settings for distinct training targets, with profile identity in resulting artifacts. This belongs in the technical pipeline, not Trainime's simple path settings. |
| <a id="qol11"></a>[QOL11](IDENTIFIED.md#qol11) | P2 / Proposal | queued | **Resumable publication presentation.** After a late-stage failure, show completed group/export paths and offer retry from the failed stage, instead of requiring the user to reconstruct the sequence from directories. |
| <a id="sc02"></a>[SC02](IDENTIFIED.md#sc02) | P2 / Proposal | queued | **Public artifact reader layer.** Extract the shared checked run/JSONL/path/hash readers from `exporting.py` into a small public module used by QA, review and receipts. Preserve compatibility with existing exports. |
| <a id="sc06"></a>[SC06](IDENTIFIED.md#sc06) | P2 / Proposal | queued | **Central schema compatibility.** Make schema/analysis versions and legacy defaults explicit in one reader layer. Preserve the existing `caption_analysis_version: 1` verification contract when evolving fields. |
| <a id="tm14"></a>[TM14](IDENTIFIED.md#tm14) | P2 / Proposal | queued | **Durable publication job record.** Persist stage/output/error state for `Publication`, enabling QOL11 recovery and an eventual cooperative cancel action between safe stage boundaries. |
| <a id="tm15"></a>[TM15](IDENTIFIED.md#tm15) | P2 / Proposal | queued | **Efficient receipt discovery.** Add a rebuildable index keyed by export hash and trainer pin, then verify the selected receipt/artifacts. Retain visibility of invalid/stale receipts rather than trusting index entries alone. |
| <a id="tm16"></a>[TM16](IDENTIFIED.md#tm16) | P2 / Proposal | queued | **Trainer compatibility harness.** Reuse a compact set of mixed-format/repeat/bucket fixtures when deliberately updating the pinned trainer or dependencies, recording before/after loader behavior and keeping old receipts. |
| <a id="tm17"></a>[TM17](IDENTIFIED.md#tm17) | P2 / Proposal | queued | **Structured derivative policies.** Extract named conversion profiles from exporter branches, with explicit EXIF, alpha, color, encoding and no-upscale behavior. This supports CF18 without changing old profile semantics. |
| <a id="nf18"></a>[NF18](IDENTIFIED.md#nf18) | P3 / Conditional | conditional | **Target tokenizer analysis.** For a chosen training model, report token length/truncation and affected captions without confusing words or comma-separated phrases with tokenizer tokens. |
| <a id="nf19"></a>[NF19](IDENTIFIED.md#nf19) | P3 / Conditional | conditional | **Additional export adapters.** Support another trainer only when selected by a real workflow, with its own immutable configuration and actual import receipt rather than renaming the Kohya output. |
| <a id="qol20"></a>[QOL20](IDENTIFIED.md#qol20) | P3 / Conditional | conditional | **Start a trainer import from the reviewer.** If users demonstrate repeated terminal handoff friction, reuse the existing isolated CLI/core action with progress and receipts. This remains convenience, not a missing M5 stage. |

<a id="m6"></a>

## M6 — Full-collection reporting, acceptance and release evidence

Source: [PLAN](PLAN.md#6-report-and-qa). Active context:
[TODO](../TODO.md#m6--full-collection-execution-and-recorded-acceptance).

Run the representative collection after pilot corrections, reconcile identities/counts, measure resources and record user acceptance. Reuse the M2-owned benchmark harness TM01. Packaging, interface and CI improvements support reproducible delivery; they do not replace human acceptance.

| Finding / audit source | Priority / scope | State | Action |
| --- | --- | --- | --- |
| <a id="cf09"></a>[CF09](IDENTIFIED.md#cf09) | P1 / Plan support | active | **Run the intended collection workload.** Measure M2–M6 throughput, output size and human correction burden at actual expected scale, then use the bottlenecks to choose SC01/SC10 or other performance work. |
| <a id="cf10"></a>[CF10](IDENTIFIED.md#cf10) | P1 / Plan support | active | **Close M6 with corrected evidence.** Publish updated QA after corrections, reconcile the final export, import it, and record human acceptance of that report rather than transferring acceptance from an older snapshot. |
| <a id="tm02"></a>[TM02](IDENTIFIED.md#tm02) | P1 / Plan support | queued | **Peak resource sampling.** Extend `execution.py` with optional peak process memory and temporary-storage measurements; label platform availability and keep existing logical payload accounting compatible. |
| <a id="cf14"></a>[CF14](IDENTIFIED.md#cf14) | P2 / Proposal | queued | **Aggregate geometry and caption lengths.** Extend shared QA summaries with aspect-ratio/resolution and character/word-length distributions, missing-value counts and links to outliers. Tokenizer analysis stays target-specific. |
| <a id="cf15"></a>[CF15](IDENTIFIED.md#cf15) | P2 / Proposal | queued | **Preserve comparability across reruns.** Report whether source bytes, review revision, model/runtime or caption rules changed between two runs; connect the change to NF06 instead of presenting totals without context. |
| <a id="nf13"></a>[NF13](IDENTIFIED.md#nf13) | P2 / Proposal | queued | **Evidence bundle export.** Package a chosen export's QA, assessments and trainer receipts as a separate portable review bundle, leaving the immutable training export unchanged. |
| <a id="qol15"></a>[QOL15](IDENTIFIED.md#qol15) | P2 / Proposal | queued | **Accessible review status.** Check form labels, error focus, status announcements, keyboard order and contrast on actual rendered pages; improve controls where evidence shows a problem rather than redesigning for appearance alone. |
| <a id="qol16"></a>[QOL16](IDENTIFIED.md#qol16) | P2 / Proposal | queued | **High-DPI and narrow-window polish.** Verify long paths, paired-image comparison, receipt logs and accounting tables at practical Windows zoom/scaling settings, with usable scrolling and no hidden actions. |
| <a id="qol17"></a>[QOL17](IDENTIFIED.md#qol17) | P2 / Proposal | queued | **Explain count units in place.** Show occurrence versus unique-image counts together where aliases matter, and distinguish untagged, unreviewed, excluded and missing-caption populations next to totals. |
| <a id="qol19"></a>[QOL19](IDENTIFIED.md#qol19) | P2 / Proposal | queued | **Actionable qualification summary.** Extend the existing separate integrity/import/pilot states with links to the exact failed receipt, unassessed pilot image or changed snapshot that needs attention. |
| <a id="sc18"></a>[SC18](IDENTIFIED.md#sc18) | P2 / Proposal | queued | **Promote repeatable smoke commands.** Turn the useful retained CLI/GUI/package comparison procedures into small repository scripts, instead of leaving reproducibility dependent on one ignored development directory. |
| <a id="sc19"></a>[SC19](IDENTIFIED.md#sc19) | P2 / Proposal | queued | **Proportionate automated CI.** Add lint, focused/full source regression, package-resource checks and a Windows operational lane. Keep heavy downloaded-model/trainer checks separate and explicitly scheduled. |
| <a id="tm12"></a>[TM12](IDENTIFIED.md#tm12) | P2 / Proposal | queued | **Preview cache.** Cache thumbnails by source hash and preview policy, reusing identical content across QA runs while keeping report output portable. Separate pilot-first browsing latency from full-snapshot summary computation. |
| <a id="tm13"></a>[TM13](IDENTIFIED.md#tm13) | P2 / Proposal | queued | **Large-report delivery mode.** Add paged entry/filter endpoints to the live reviewer for measured large workloads, while retaining static report generation as an explicit portable mode with clear size costs. |
| <a id="tm20"></a>[TM20](IDENTIFIED.md#tm20) | P2 / Proposal | queued | **Packaged-resource verification.** Check that the installed wheel contains the same HTML/JS, trainer pins and newly added Python modules as the release candidate, and launch the technical/reviewer help paths from that wheel. |

## End-of-document handoff

Pull source context from [IDENTIFIED.md](IDENTIFIED.md) and the current
[PLAN.md](PLAN.md), then reconcile [TODO.md](../TODO.md) and
[COMPLETED.md](COMPLETED.md). The next execution destination is TODO: promote a
bounded eligible task using the rules above. Return here after TODO completion;
start a new IDENTIFY cycle only after the PLAN's required acceptance is complete.
