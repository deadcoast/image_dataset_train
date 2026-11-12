# Current-source and workflow reconciliation — 2026-11-12

This review turns the existing improvement inventory into a current, actionable
queue. **All 102 existing finding IDs are retained; seven distinct findings are
added. CF21/CF23 are the next scheduled source batch.** The full list below gives
each finding its current disposition, source evidence, outcome and verification
boundary. [SHELVED](SHELVED.md#current-source-priorities) holds the queue;
[TODO](../TODO.md#review-evidence-integrity) holds only the selected next batch.

## Authority, snapshot and limits

This is the user's requested in-cycle review of `dataset-preparation-2026-10-11`,
following [IDENTIFIED](IDENTIFIED.md#current-source-reconciliation--2026-11-12) and
[PLAN](PLAN.md#source-reconciliation-and-next-batch). It does not close the PLAN or
open a replacement IDENTIFIED cycle. M4 human review remains the next required
acceptance; M5/M6 acceptance depends on it. Assistant judgments remain assistant.

Inspected checkout: `C:/github/image_dataset_train`, branch `main`, HEAD
`c6de8c1fc60681d870985cf4e04057cb0a8854cb`, including existing uncommitted work.
Package **0.17.0**, **79 runtime payload files**, **56 test source files**;
runtime payload SHA-256
`73de3c746b8f06d06d5f29bd62bc9b20eff37fd58d27641ab1fd3932c1d720f1`.
No CodeGraph index was present. Source/test inventory, prior documents and exact
hashes are retained in `.cache/workflow-source-review-20261112/baseline.json` and
`before/`. Locations below refer to this frozen source snapshot.

Review covered intake/preparation/CLI/recovery/configuration, similarity/tagging/
captions/labels, QA/review/attribution/publication, export/catalog/trainer and
packaging/execution, with relevant tests and retained qualification. It was a
subsystem/path audit, not a proof of every branch in every file. New probes used
generated fixtures or constructed inputs only. No actual image collection,
acceptance record, model cache or normal installation was modified.

No application-wide test suite, real browser, trainer/model execution, hosted CI
or scale benchmark was run for this planning request. The existing
[0.17.0 delivery](COMPLETED.md#review-preferences-0170) reports 1,216 passing tests,
16 platform skips, 137 installed commands and 24 preference HTTP checks; those
are prior qualification, not new measurements and not proof that the gaps below
are absent. The application/runtime/tests are unchanged by this review.

## What remains strong

The directory pipeline, immutable export/database, exact source identities,
checkpoint recovery, receipt navigation, assistant attribution, batch/history
operations, snapshot/caption comparisons, saved-rule explanations and browsing
preferences are implemented. Their bounded completion evidence remains valid.
The queue must not recreate delivered features because older findings described
their former absence. Original review/version figures are explicitly historical.

The largest planning weakness was stale scope: TM07 already has a checked lazy
vector reader; TM08 already records providers/effective batches; QOL17 already has
content/reconciliation counts; QOL19 already links receipts; SC18 already has an
installed package harness. Their remaining tasks below target the missing parts.
Storage migrations, feature caches, inference tuning and report paging remain
measurement-led proposals, not established speedups.

## New findings and observed behavior

| ID | Evidence class | Observation and scope |
| --- | --- | --- |
| [CF21](#cf21) | Generated/in-memory validation probes | Current-only assessment attribution changes can yield `human_accepted:true` while history remains assistant; an ordinary edit can append to history rejected by stricter consumers; label clear-event actor/types are incompletely validated. These are deliberately inconsistent fixtures, not evidence of actual user-data damage or identity authentication. |
| [CF22](#cf22) | Generated deterministic read races | Catalog returned old parsed metadata with a new metadata digest; trainer status returned an old passed receipt after export metadata changed during verification. Source/export fixture bytes were restored and runtime hashes preserved. |
| [CF23](#cf23) | Actual controller plus generated session | Ctrl+Enter emitted saves for a pending preview or empty filtered queue while Save was disabled; the explicit payload was accepted by a real generated label session. Browser state is not proof of human review, and legitimate nonbrowser APIs remain supported. |
| [CF24](#cf24) | Constructed bundle/API probe | A self-consistent EVA bundle identity in a requested Swin slot passed generic loading; caption default selection still followed requested Swin. No mismatch was observed in the user's models. |
| [QOL21](#qol21) | Actual controller harness | Publication refresh becomes disabled after failure and older running/readiness replies can replace newer completed state. Backend locks already exist; duplicate publication was not demonstrated. |
| [TM21](#tm21) | Generated SQL trace / static path | A one-row catalog query performed full-table verification first. Control flow is confirmed; large-collection latency and RSS impact are unmeasured. |
| [DP03](#dp03) | Source-backed product proposal | Current dryrun reports inventory/settings but lacks one actionable readiness view; pinned offline model absence is discovered at tagging. Preview cannot predict every later filesystem failure. |

Existing-ID refinements also have concrete evidence: **SC04** retains two JSON
writers with different cleanup/durability behavior (one versus zero pending files
after injected replace failure, originals preserved); **SC12** allows caller
mutation of validated nested settings; **SC06** evaluator/comparison readers can
infer saved rules from current defaults without the stronger explanation-reader
version/hash contract. These keep their existing IDs and are not marked fixed.

Evidence is retained under `.cache/workflow-source-review-20261112/`:
`root-probes.json`, `review-ui-probe.py/json`, `label-ui-probe.py/js/json`,
`export-probes.py/json/log`, `tagging-inmemory-probes.py/json`, and the subsystem
audit notes. The tagging probe script is an explicitly recorded equivalent
reconstruction of the initial interactive probes; its narrow rerun reproduced
all four observations without changing source. The generated
malformed-receipt hypothesis was rejected: existing validation correctly produced
`history_incomplete`. Its initial mistaken harness assertion and corrected result
are retained; it is not an application failure or queued defect. The review-store
probe's initial same-record variant is also retained separately; the confirmed
case edits a different record and establishes the stated persistence gap.

## Complete finding-by-finding disposition

States match SHELVED after promotion. Existing priorities/IDs are preserved;
source support, acceptance, conditional targets and performance proposals remain
distinct. Source locations without a directory are under
[`src/image_dataset_train`](../src/image_dataset_train). Relevant regression
contracts live under [`tests`](../tests). A source-confirmed cost shape does not
establish an unacceptable latency or a particular optimization benefit.

### M1

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf17"></a>[CF17](SHELVED.md#cf17) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="nf07"></a>[NF07](SHELVED.md#nf07) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="nf08"></a>[NF08](SHELVED.md#nf08) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="nf14"></a>[NF14](SHELVED.md#nf14) | queued | `preparation.py:805-998`, `collection_catalog.py:194-387`, `recovery_catalog.py:351-412` expose separate attempts, owned roots and receipts, not storage ownership/reference accounting. | Read-only storage inventory over explicitly registered workspaces and application-owned roots. Deduplicate shared content, distinguish logical/allocated/unknown bytes and referenced/uncertain/orphan candidates. Keep backups and unverified artifacts protected. Test shared caches, missing roots, linked paths and concurrent jobs; cleanup is a separate future explicit operation. |
| <a id="qol12"></a>[QOL12](SHELVED.md#qol12) | queued | `preparation.py:344-350` emits inventory counts only every 100 files; other stages have string callbacks. `operations.py:354-469` already reports selected image/caption counters. | Preserve existing useful progress, add structured stage/unit/completed/total events and final small-job events, distinguish cached/inferred/verified work. Unknown totals remain unknown. Verify interrupted/resumed accounting and stdout JSON purity; avoid inferring elapsed-time guarantees. |
| <a id="qol13"></a>[QOL13](SHELVED.md#qol13) | queued | `qa.py:168-172`, `review_selection.py:243-247` and `recovery_catalog_cli.py:52-69` supply argv/PowerShell/POSIX forms; `preparation_cli.py:75-76,128` only supplies PowerShell text and catalog text always selects PowerShell. | Reuse one command representation without weakening exact job/receipt selectors or environment overrides. Native CLI rendering and UI copy actions should carry the same argv. Test spaces, apostrophes, Unicode, shell metacharacters and environment scope without executing injected text. |
| <a id="qol14"></a>[QOL14](SHELVED.md#qol14) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="qol18"></a>[QOL18](SHELVED.md#qol18) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="sc03"></a>[SC03](SHELVED.md#sc03) | queued | `inventory_data.py:53-85` reads entire metadata/manifest; newer `collection_registry.py:29-39` and score readers use checked/bounded patterns. Source containment/hash logic remains repeated. | Incrementally unify checked byte reads and source identity checks, preserving stage-specific limits and offline artifact browsing. Verify oversized/truncated/changing files, links/junctions, containment and stage-specific diagnostics. Do not perform a repository-wide reader rewrite as a prerequisite for a localized fix. |
| <a id="sc04"></a>[SC04](SHELVED.md#sc04) | queued | `model_bundle.py:73-79` lacks `diagnostics.py:43-54` flush/fsync/final cleanup. `operations.py:38` and tagging still import the former. Synthetic replace-failure probe retained one pending file for model_bundle and zero for diagnostics; both retained original bytes. | Route writers through one durable primitive with documented cleanup/retention rules. Inject serialization, flush and replace failures and verify old bytes, temp cleanup and recoverable error context. The probe does not establish power-loss durability. |
| <a id="sc05"></a>[SC05](SHELVED.md#sc05) | queued | Config uses dataclasses, but stage/job/receipt boundaries still use nested dicts (`preparation.py:207,394,783`; catalog/operations results). | Add lightweight typed records only at changed public boundaries, with explicit validation/conversion. Preserve on-disk formats and legacy readers; malformed/unknown fields need purposeful behavior, not an unmeasured framework migration. |
| <a id="sc07"></a>[SC07](SHELVED.md#sc07) | queued | `cli.py:17-301,304-937` remains a large parser/dispatcher; newer CLI families already live in dedicated modules. | Extract one legacy command family at a time, keeping entrypoints, flags, exits, JSON and stderr behavior. Installed help and representative success/error/cancel checks are the boundary. |
| <a id="sc11"></a>[SC11](SHELVED.md#sc11) | queued | `collision_fix.py:47,120,152,224`, `caption_restore.py:18` and `doctor.py:347` depend on private operations helpers. | Extract checked path, journal and short commit primitives with source locks unchanged. Verify interrupted collision/tag/remove/restore operations and no-clobber recovery across multiple handlers. |
| <a id="sc12"></a>[SC12](SHELVED.md#sc12) | queued | `config.py:19-37,49-98` frozen dataclasses retain caller-owned mutable lists/dicts and nested lists. Synthetic probe mutated a validated threshold from 0.5 to -1.0 and changed drop/subset tags after construction. | Defensively normalize all nested settings to immutable values and explicit serialization. Test caller aliasing, direct/nested mutation, TOML/job roundtrips and deterministic settings hashes; preserve accepted configuration syntax. |
| <a id="sc13"></a>[SC13](SHELVED.md#sc13) | queued | `runs.py:33-77`, preparation stage attempts and module-specific publishers separately allocate/write/publish artifacts. Shared `diagnostics.publish_directory` already exists. | Factor only repeated staging/completion lifecycle around existing publication primitives, retaining stage-specific evidence and pending artifacts. Fault-inject before/after completion metadata and final rename; do not treat staging as complete or erase failed attempts. |
| <a id="sc16"></a>[SC16](SHELVED.md#sc16) | queued | `diagnostics.py:107-174` still infers action from exception text; preparation already carries a narrow structured `PreparationRecoveryError.action`. | Extend stable operational codes/context incrementally so damaged export metadata is not confused with model repair and recovery targets the failed operation. Preserve causes and unknown-code fallback. Verify CLI/API mapping and unchanged retained artifacts. |
| <a id="sc17"></a>[SC17](SHELVED.md#sc17) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="sc20"></a>[SC20](SHELVED.md#sc20) | queued | `model_bundle.py:1` retains a dated network-only claim; current CLI cancellation at `cli.py:901` already describes checkpoints accurately. | Audit remaining comments/help against current code; remove completed examples from the pending scope instead of blindly editing every old observation. Verify actionable help examples and command availability. |
| <a id="tm03"></a>[TM03](SHELVED.md#tm03) | queued | `inventory.py:143-176`, `runs.py:48-51`, `inventory_data.py:68-84` retain records, joined manifest strings/bytes and parsed rows. | Separate discovery/inspection iteration from sidecar/duplicate indexes and publication. Preserve deterministic order, complete hashes and collision decisions. Use bounded synthetic scale measurements and cancellation checks before claiming memory improvement. |
| <a id="tm04"></a>[TM04](SHELVED.md#tm04) | queued | Each preparation run scans anew and `_assert_sources` rehashes membership before similarity/export and after completion (`preparation.py:147-175,600-625`). | Reuse discovery/index data only where useful, with explicit invalidation. Preserve required content revalidation even when size/mtime match. Test same-size changed bytes, rename, sidecar change, missing source and old schema. Benchmark cold/warm behavior before broad adoption. |
| <a id="tm19"></a>[TM19](SHELVED.md#tm19) | queued | Existing tests cover recovery/link guards; this run is Windows source review, not a native multi-platform qualification. | Record actual host/filesystem/runtime and privilege/skips for junctions, symlinks, case collisions and installed repair. Keep Linux CI definition and native installer evidence distinct. ARM64 remains conditional on supported deployment. |
| <a id="cf20"></a>[CF20](SHELVED.md#cf20) | conditional | Inventory checks structure/dimensions/decode and current policy has no calibrated blur/watermark classifier. | Retain the representative-error condition; proposals must remain inspectable suggestions, with false-positive evidence and no automatic content deletion. |
| <a id="dp03"></a>[DP03](SHELVED.md#dp03) | queued | `preparation.py:637-651` previews inventory/settings; pinned offline model absence is checked later at tagging (`:352-365`). Destination/storage and caption-readiness constraints are not a consolidated preview. | Extend existing read-only preview with model readiness, destination constraints, existing-caption blockers, measured/estimated/unknown storage and exact next commands. Test unavailable/corrupt models, custom/shared roots and unwritable destinations; no fetch, inference, repair, job/registry/log/cache mutation. Execution-time validation remains authoritative. |

### M2

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf01"></a>[CF01](SHELVED.md#cf01) | completed | Completed bounded pilot; `similarity_evaluation.py:84` consumes saved explicit/manual judgments. | Preserve recorded scope; no new representative/general recall claim. |
| <a id="cf02"></a>[CF02](SHELVED.md#cf02) | completed | Completed source support: `similarity_evaluation.py:48` separates fit and held-out, undefined metrics explicit. | Regression fit cannot inspect held-out; genuine missing classes remain unavailable. |
| <a id="cf03"></a>[CF03](SHELVED.md#cf03) | queued | Queued, missing conflict witness in `reviews.py:390`, `:418`. | Exact/related path explanation with identities; no automatic relation changes. |
| <a id="nf01"></a>[NF01](SHELVED.md#nf01) | completed | Completed source support: saved pair evaluation sets consumed by `similarity_evaluation.py:122`. | Preserve calibration/held-out/manual-outside-proposal identities. |
| <a id="nf05"></a>[NF05](SHELVED.md#nf05) | completed | Completed source support/authorized probability scope: `label_sampling.py:77`, `:122`, `:186`; workspace create `:157`, refresh `:351`. | Preserve full frame/aliases/seeds/group partitions and inherited judgments; human acceptance belongs CF07/CF10. |
| <a id="qol01"></a>[QOL01](SHELVED.md#qol01) | queued | `similarity_evaluation.py:84` and `tagging_evaluation.py:191` already publish bounded evaluation evidence. | Summarize class/support coverage, missing judgments and unavailable metrics at the selected evaluation entry point. Reuse existing receipts; show calibration versus held-out and assistant versus human scope. Check missing classes and incomplete judgments without inventing zero-valued accuracy. |
| <a id="tm01"></a>[TM01](SHELVED.md#tm01) | queued | Queued; `execution.py:22` records stage elapsed/payload logical bytes but no general chosen-collection harness. | Explicit inputs/cache/environment/counts; support CF09, no accuracy inference. |
| <a id="qol05"></a>[QOL05](SHELVED.md#qol05) | queued | `qa_workflow.js` renders pair previews; `label_review.js` has actual-pixel/backdrop controls, but pairs lack synchronized inspection. | Add optional synchronized pair zoom/pan and predictable focus while preserving image identity and dirty edits. Verify differing aspect ratios, aliases, failed previews, narrow windows and keyboard access; no automatic duplicate decision. |
| <a id="sc08"></a>[SC08](SHELVED.md#sc08) | queued | Open, refine with CF03 | `_groups` remains private in `reviews.py:390`; review batch/history/change modules import it. Extract a tested source+relation service only when needed for conflict explanation or cache; preserve exact aliases, historical inactive relations, distinct conflicts and deterministic groups. No framework needed. |
| <a id="tm05"></a>[TM05](SHELVED.md#tm05) | queued | Queued, pHash recomputed `similarity.py:211`. | Versioned content-feature reuse, parity and invalidation; unmeasured gain. |
| <a id="tm06"></a>[TM06](SHELVED.md#tm06) | queued | Queued, output growth and query metrics absent around `similarity.py:226`. | Dense-neighbor diagnostics; explicit partial cannot pass complete-stage readers. |
| <a id="tm11"></a>[TM11](SHELVED.md#tm11) | queued | Open, depends on SC08/SC09 measurement | No persistent versioned relation cache in `_groups`; inputs include exact aliases, active pair content hashes and decisions. Cache identity must include inventory/policy/relation revision, and corrupt/old caches must be discardable derived data. Do not key solely on overall save revision or mutable path names. |
| <a id="nf15"></a>[NF15](SHELVED.md#nf15) | conditional | `similarity.py` currently proposes pHash neighbors; normalized-pixel equality is a separate algorithm. | Retain the later-extension condition. Specify orientation, alpha, color and normalization identity; test visually meaningful variants and never turn normalized equality into automatic source deletion. |
| <a id="nf16"></a>[NF16](SHELVED.md#nf16) | conditional | `similarity.py` uses pHash; no embedding backend is currently required by evidence. | Promote only after representative pHash misses justify a pinned embedding backend. Record preprocessing, metric, calibration/held-out quality, resource use and false merges; retain explicit review. |
| <a id="nf20"></a>[NF20](SHELVED.md#nf20) | conditional | `inventory.py` records paths/hashes and `reviews.py` records group relationships, not authoritative artwork/source identities. | Keep conditional on a real metadata source and identity requirement. Preserve supplied versus inferred provenance and disagreements; never equate filenames or model guesses with verified identity. |

### M3

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf04"></a>[CF04](SHELVED.md#cf04) | completed | Completed bounded assistant measurement; `_metrics`/`_evaluate_model`, `tagging_evaluation.py:26`, `:89`, assistant exclusion `:165`. | Preserve per-label denominators/uncertain exclusions/human-only exclusion; SC06 reader repair is separate. |
| <a id="cf05"></a>[CF05](SHELVED.md#cf05) | completed | Completed bounded same-membership measurement; `tagging_evaluation.py:106`, `:218`. | Keep saved CPU/common-baseline evidence; no model winner/native-default claim. |
| <a id="cf06"></a>[CF06](SHELVED.md#cf06) | completed | Completed diagnostic fitting only; `tagging_evaluation.py:56` fits calibration with class checks and evaluates held-out. | Keep regressions/small classes visible; no automatic adoption. |
| <a id="nf02"></a>[NF02](SHELVED.md#nf02) | completed | Completed bounded comparison: `tagging_evaluation.py:191`; label UI `compare:124` after recorded independent judgments. | Retain exact frozen population and attributed exposure; not a universal ranking. |
| <a id="nf03"></a>[NF03](SHELVED.md#nf03) | completed (source support) | Completed source support: `LabelWorkspace:464`, CAS `save_many:686`, attributed records `:537`. | Keep frozen selection, uncertainty and human/assistant boundaries; CF21 validation hardening is distinct from feature completion. |
| <a id="nf04"></a>[NF04](SHELVED.md#nf04) | queued | Queued, evaluator returns recommendations/output without adoption; `tagging_evaluation.py:191`. | Explicit profile containing model/rules/evaluation identity and approval/adoption; current diagnostic regressions cannot be silently promoted. |
| <a id="qol02"></a>[QOL02](SHELVED.md#qol02) | completed | `label_review_ui.py:124` compares saved model scores/captions after attributed label review and records exposure. | Retain completed scope and existing CPU/common-population limits. SC06 hardens saved-rule provenance separately; do not requeue the comparison feature or announce a model winner. |
| <a id="qol03"></a>[QOL03](SHELVED.md#qol03) | completed | `label_workspace.py:464` and `label_review.js:52` supply explicit label judgments, uncertainty and visual-evidence notes. | Retain completed checklist scope. CF21/CF23 fix distinct validation/input-method defects; no new labels or human judgments are created by this audit. |
| <a id="sc01"></a>[SC01](SHELVED.md#sc01) | queued | Queued, confirmed eager all-vector publication: `tagging.py:237`, `:338`, `_publish:101`. | Incremental persisted-vector publication; TM07 and measured TM01/TM02 qualification. |
| <a id="cf16"></a>[CF16](SHELVED.md#cf16) | queued | Queued, confirmed square/intermediate allocations: `wd_tagger.py:18`, `similarity.py:119`. | Measure first; parity/versioned preprocessing, not assumed speedup. |
| <a id="tm07"></a>[TM07](SHELVED.md#tm07) | queued | Queued with substantial reader foundation already delivered: `ScoredRun.vector:111`, `score_cache.py:49`; eager consumers remain. | Integrate checked iterator/bounded writes with SC01; preserve checksum contract. |
| <a id="tm08"></a>[TM08](SHELVED.md#tm08) | queued | Queued with provider/effective batch evidence already delivered: `tagging.py:305`, `wd_tagger.py:84`. | Per-batch timing and explicit tuning/backoff; real GPU qualification separate. |
| <a id="nf17"></a>[NF17](SHELVED.md#nf17) | conditional | `model_bundle.py`, `wd_tagger.py` and `tagging.py` implement WD-specific artifact/preprocessing/output contracts. | Retain selection-after-baseline condition. A Camie or natural-language backend needs its own pinned preprocessing/output/cache contract and actual chosen-target comparison; not a WD-name alias. |
| <a id="cf23"></a>[CF23](SHELVED.md#cf23) | active | `label_review.js:20-28,111,188` disables buttons for an unavailable or hidden image but Ctrl+Enter bypasses those conditions. Generated controller requests for pending/empty-filter states were emitted; the real label session accepted the explicit payload. | One eligibility predicate for click/form/shortcut/save-next, current matched image and completed preview; fence late image callbacks and provide recoverable empty/error states without discarding drafts. Verify zero ineligible requests and exactly one eligible atomic attributed save through the actual controller and installed rendered reviewer. Preserve valid nonbrowser assistant judgment APIs. |
| <a id="cf24"></a>[CF24](SHELVED.md#cf24) | queued | `model_bundle.py:98,143`, `tagging.py:228,315`, `preparation.py:353,434`: generic bundle checks accept self-consistent foreign identity while defaults follow the requested slot. A constructed EVA identity in a Swin slot passed the generic loader. | Check expected model/repository/full revision at configured fetch reuse, tagging, preparation and relevant cache/recovery boundaries before inference/default selection. Keep generic inspection possible and mismatch recovery non-destructive. Verify each mismatch, matching reuse/resume and a generated ONNX path; retain an explicit test-fixture identity contract. |

### M4

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf07"></a>[CF07](SHELVED.md#cf07) | active | `assessments.py:124` computes separately attributed human acceptance; current workflow records assistant-only acceptance for the selected report. | Keep the existing human conclusion task open. CF21 repairs validation of persisted evidence; source tests or assistant judgments must not satisfy the human task. |
| <a id="cf19"></a>[CF19](SHELVED.md#cf19) | queued | Open; dependent on NF09 | Same immutable source references plus `review_selection.py:175` and metadata lineage checks. Historical exports already work standalone; do not reimplement DP02. Never rewrite historical QA/export metadata or transfer report-bound human acceptance to newly built reports. Test aliases, changed/missing/additional files, duplicate roots, interrupted relocation and retained old jobs. |
| <a id="nf09"></a>[NF09](SHELVED.md#nf09) | queued | Open; refine, no standalone path edit | `reviews.py:88` requires inventory/similarity source agreement; `ReviewStore.__init__:161` keys storage by absolute source; `preparation.py:207`–257 rejects job source different from active binding; `collection_registry.py:160` rejects rebinding an existing workspace. Needs verified relative-path+byte continuity, explicit new binding/job lineage, failure recovery and review continuation semantics. |
| <a id="nf10"></a>[NF10](SHELVED.md#nf10) | completed | `review_history.py:348` validates/replays history and guarded restoration appends a new revision. | Retain delivered 0.11.0 scope. CF21 aligns older ordinary read/write paths with its stronger validity contract; no repeated undo implementation. |
| <a id="nf11"></a>[NF11](SHELVED.md#nf11) | completed | `review_batch.py` freezes explicit membership and performs guarded atomic batch updates. | Retain delivered 0.12.0 scope and all-or-nothing semantics; CF21 must preserve valid batch replay and reject inconsistent state without changing membership. |
| <a id="qol04"></a>[QOL04](SHELVED.md#qol04) | queued | Partial, still open | `qa_report.js:222` supports arrows/j/k only outside typing controls; pair controller has no keyboard/save-next path. `label_review.js:188` already has Ctrl+Enter and Save + next, but CF23 must fix its eligibility before extending it. Discoverable pair shortcuts/focus should reuse one guarded action, not add parallel saving code. |
| <a id="qol06"></a>[QOL06](SHELVED.md#qol06) | completed | `qa_report.js` bulk controls and `review_batch.py` expose exact selected membership and changes before apply. | Retain completed visible-membership contract. Preserve dirty-state/selection revisions and existing batch qualification when changing shared validators. |
| <a id="qol07"></a>[QOL07](SHELVED.md#qol07) | completed | Delivered, preserve completed | `review_preferences.py:67`–235 plus `qa_preferences.js` stores only allowlisted browsing state, exact report key, lock/CAS and bounded names/filters; `qa_workflow.js:89`–136 resumes exact pair on the saved page and retains the checkpoint on unmatched/failed load. Tests cover conflict/storage/dirty forms/hash precedence/page clamp. Static storage remains origin-dependent and non-atomic across tabs; that is documented scope, not a new live-CAS defect. |
| <a id="qol08"></a>[QOL08](SHELVED.md#qol08) | completed | Delivered scoped recovery, preserve completed | `qa_report.js:75`–108 provides request-bound fresh media/retry; `585`–612 provides per-form recovery; `qa_workflow.js:51`–158 separates empty/failed/manual states and preserves dirty explicit-pair reload. `tests/test_reviewer_recovery_ui.py:16` and full controller cases cover the implemented scope. Register CF23/QOL21 separately; do not undo the historical completion. |
| <a id="qol09"></a>[QOL09](SHELVED.md#qol09) | completed | Delivered, preserve completed | `caption_comparison.py:329`–486 pins report/history/candidates, uses authoritative `_caption` semantics and final checks; `review_ui.py:267` binds cached report identity; JS comparison at `qa_report.js:396`–507 preserves fields and saved baseline. Invalid/unavailable higher candidates are not silently absent. Tests include offline export, exact aliases, raw text, literal count diffs and late replies. |
| <a id="qol10"></a>[QOL10](SHELVED.md#qol10) | completed | Delivered, preserve completed | `review_changes.py:299`–389 distinguishes changed/history-only/unchanged with exact paged differences; `review_selection.py:190`–231 validates only bounded required QA checkpoint metadata, not preview media; `qa_workflow.js:228`–301 fences page identity. New CF21 affects consistency parity in older consumers, not absence of QOL10. |
| <a id="sc09"></a>[SC09](SHELVED.md#sc09) | queued | Open source-backed cost, unmeasured benefit | `ReviewStore.update:262` rebuilds `_groups` for every changed image/caption/annotation; `review_status:481` also rebuilds. New batches compute once per batch, but single saves remain. Separate relation revision from overall record revision before reusing graph results; benchmark first and retain conflict detection. |
| <a id="sc10"></a>[SC10](SHELVED.md#sc10) | queued | Open conditional scale design | `reviews.py:178` loads the full JSON and `update:281` atomically writes current state plus complete history; `review_history.py:348` replays all events. This is a real unbounded growth property, not a measured unacceptable latency claim. CF21 consistency repair precedes storage redesign. Measure history/file/collection dimensions and p50/p95 read/save first. |
| <a id="sc14"></a>[SC14](SHELVED.md#sc14) | queued | Partial isolation, still open | New `qa_preferences.js` is a factory with private state, while report/image/correction/assessment globals remain at `qa_report.js:3`–18 and pair/publication closure shares `workflowBusy/Dirty` in `qa_workflow.js:1`–8. Extract by behavioral boundary only as concrete defects require, preserving static output and current full-controller tests. |
| <a id="sc15"></a>[SC15](SHELVED.md#sc15) | queued | Partial shared helper, refine remaining ordering gap | `qa_report.js:252` already shares fetch/JSON/error handling for most QA panels; preferences/label UI have their own helpers for different storage surfaces. New panels have explicit ticket fences; publication lacks them (QOL21). Preserve per-form dirtiness and distinct preview/read/write semantics; do not simply replace all calls with one global busy lock. |
| <a id="tm09"></a>[TM09](SHELVED.md#tm09) | completed | Delivered, preserve completed | `caption_explanations.py:24` supports exact pinned image/tag selection, saved full rules/version checks and no inference/source-media reads; `review_ui.py:295` supplies report-bound lineage; `qa_report.js:263`–395 is lazy and fenced. Existing tests exercise strict threshold, drops, character/rating behavior, subset predicates, phrases, aliases, missing/unsupported evidence and corruption. Do not requeue generic caption explanations. |
| <a id="tm10"></a>[TM10](SHELVED.md#tm10) | queued | Open | `annotations.py:10` NFC/space/casefold normalization and `label_names:19` canonical sets exist; no configurable vocabulary/alias registry or unknown-label reporting exists. Add opt-in preferred labels without rewriting free-form historic judgments or inferring semantic equivalence. Validate normalized alias collisions and migration-free reads. |
| <a id="tm18"></a>[TM18](SHELVED.md#tm18) | queued | Open, refine toward a narrow validation/read-write contract first | Store persistence is still directly coupled to JSON and path locks (`reviews.py:160`); newer services import private history loaders and write atomically themselves (`review_batch.py:142`, `review_history.py:569`). CF21 should align validity and failure semantics first; a later backend interface requires equivalence tests, migration/recovery and measured scale need. |
| <a id="cf21"></a>[CF21](SHELVED.md#cf21) | active | `assessments.py:40-60,124-132` trusts current records without replay; `reviews.py:173-281` is weaker than `review_history.py:348-477`; `label_workspace.py:588-613` leaves event/clearing-actor type gaps. Generated probes accepted a current-only attribution change and an ordinary save to inconsistent history. | Use strict schema/event/current-state validation at all review/assessment/label read and locked write boundaries, before summaries or publication. Preserve exact report identities, valid legacy unknown attribution, batch/restore/clear semantics and original bytes on rejection. Distinguish absent legacy actors from present malformed actors; retain valid record attribution when an old event has no separate actor. Test replay divergence, malformed actor/exposure/revisions, valid legacy history, CAS and installed HTTP failure/recovery. No automatic evidence repair or human reattribution. |
| <a id="qol21"></a>[QOL21](SHELVED.md#qol21) | queued | `qa_workflow.js:333-349` leaves refresh inside disabled `publicationFields` after failure; unfenced requests can replace revision 9/completed with revision 3/running. `qa_report.html:207-214` contains the recovery control inside that fieldset. | Keep explicit reconnect available independently of disabled mutation settings; fence load/start/poll responses and timers, preserve settings/job identity/output links and recover after offline/restored server. Test delayed success/error ordering and installed reconnect/resume. Backend locking already exists; no duplicate-publication defect was demonstrated. Coordinate only the needed SC15 scope. |

### M5

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf08"></a>[CF08](SHELVED.md#cf08) | active | Keep active, technical work delivered; human acceptance remainder only | `exporting.py:361`, `trainer_worker.py:26`; the current CF08 queue row already distinguishes corrected 355-pair import and 46 caption corrections from M4 human acceptance. Do not schedule another implementation of the downstream path. |
| <a id="cf11"></a>[CF11](SHELVED.md#cf11) | queued | Keep queued; first useful split enhancement | `splitting.py:42,114,120,132,166`. Add objective/start/end/termination/budget explanations without changing assignments. Tiny exhaustive fixtures can check reported objective against an oracle, without promising global optimality. |
| <a id="cf12"></a>[CF12](SHELVED.md#cf12) | queued | Keep queued behind CF11 | `splitting.py:77`; deterministic bounded seed/budget comparison and explicit selection. Preserve old published exports; hash chosen settings/assignments. |
| <a id="cf13"></a>[CF13](SHELVED.md#cf13) | queued | Keep queued behind CF11 and a concrete evaluation need | `splitting.py:17,77` has no constraint argument. Validate group identities, contradictory constraints and impossible split requests; keep aliases/groups indivisible. |
| <a id="cf18"></a>[CF18](SHELVED.md#cf18) | queued | Keep queued; opt-in policy design, not current-output defect | `exporting.py:293,335`. Depends on TM17; exact ICC/orientation/alpha fixtures, preserved old-version replay, actual trainer import for proposed outputs. |
| <a id="nf06"></a>[NF06](SHELVED.md#nf06) | completed | Retain completed | `snapshot_comparison.py:243,250,287`; `tests/test_snapshot_comparison.py:49,176,212,239,267`. Existing normalized differences and replayable portable receipts satisfy the row; CF15 adds context separately. |
| <a id="nf12"></a>[NF12](SHELVED.md#nf12) | queued | Keep queued, target-driven | `config.py` technical export/caption settings plus `exporting.py:361` already configure one workflow. A named profile must freeze its resolved settings/hash, not hide mutable preferences. Design after actual target needs; no current correctness defect. |
| <a id="qol11"></a>[QOL11](SHELVED.md#qol11) | completed | `review_publication.py` persists job/checkpoint state and `qa_workflow.js` exposes outputs/recovery. | Retain completed durable publication presentation. QOL21 is the separate reconnect-control and stale-response correction, not a replacement backend. |
| <a id="sc02"></a>[SC02](SHELVED.md#sc02) | queued | Keep queued; do not make it a prerequisite for CF22 | Private readers in `exporting.py:36,58,65,72,79` and consumers in QA/receipt/snapshot modules justify extraction. Small public checked-byte/path/JSONL contract, exact raw-byte identity and legacy fixture compatibility; migrate incrementally. |
| <a id="sc06"></a>[SC06](SHELVED.md#sc06) | queued | Queued, confirmed incompatible saved-rule/type handling: `tagging_evaluation.py:118`, `label_review_ui.py:148`, `caption_explanations.py:121`. | Explicit current/legacy rules, reject malformed evidence; preserve valid historical readers. Validate complete supported current rule fields, caption version and recomputed rules digest. Use explicit unavailable or known-legacy handling for missing historical evidence; never reconstruct historical rule semantics from current defaults. Verify evaluator/comparison/explanation parity and absent-versus-malformed fields. |
| <a id="tm14"></a>[TM14](SHELVED.md#tm14) | completed | Retain completed durable job scope | `review_publication.py` durable records are already delivered; the current queue row correctly does not claim mid-copy cancellation. Do not reopen merely because cancellation is a future option. |
| <a id="tm15"></a>[TM15](SHELVED.md#tm15) | queued | Keep queued; CF22 first, measure discovery separately | `trainer_receipts.py:74,82,123`. Rebuildable hash+pin index, verify selected artifacts, preserve invalid/stale history and corruption visibility. |
| <a id="tm16"></a>[TM16](SHELVED.md#tm16) | queued | Keep queued for deliberate pin/dependency changes | `trainer.py:36,43,120`, `trainer_worker.py:16,26`; existing source tests and synthetic package fixtures are not a standardized before/after pinned-loader compatibility matrix. Preserve old receipts, compare repeats/buckets/captions/geometry. |
| <a id="tm17"></a>[TM17](SHELVED.md#tm17) | queued | Keep queued, prerequisite to CF18 | `exporting.py:293,335` encodes current versioned branches. Extract explicit policies with unchanged default output bytes and readable provenance, then add new policy versions. |
| <a id="nf18"></a>[NF18](SHELVED.md#nf18) | conditional | Retain conditional | `trainer_worker.py:91` explicitly does not execute tokenization. Require a chosen model/tokenizer and pinned offline analysis; caption words are not tokens. |
| <a id="nf19"></a>[NF19](SHELVED.md#nf19) | conditional | Retain conditional | `_adapter`, `exporting.py:281`, targets Kohya. Another real selected trainer needs its own immutable adapter and actual import fixture, not a renamed TOML. |
| <a id="qol20"></a>[QOL20](SHELVED.md#qol20) | conditional | `qa_training.js` currently inspects exact trainer receipts and offers CLI equivalents; it does not launch a trainer import. | Keep conditional on an explicitly selected local import action. A future UI action needs job identity, progress/cancel/recovery and pinned runtime checks; keep import distinct from training and human acceptance. |
| <a id="cf22"></a>[CF22](SHELVED.md#cf22) | queued | `dataset_catalog.py:449,483,536` can join old parsed metadata to a later digest; `trainer_receipts.py:71-159` can return an old passed receipt after metadata changes during verification. Both races reproduced with generated fixtures. | Derive parsed values and reported identity from the same captured bytes; verify referenced artifacts and reject detected drift before returning catalog/status results. Test metadata/manifest/receipt changes during reads, same-ID rewrites, valid relocated exports and source-offline inspection. Do not require the whole SC02 reader refactor first. |
| <a id="tm21"></a>[TM21](SHELVED.md#tm21) | queued | `dataset_catalog.py:315,343-350,470,579-605`: even limit=1 triggers full metadata/catalog verification and full-table row reads. A SQL trace confirms the path; larger-scale latency/RSS is unmeasured. | After CF22, measure cold validation and repeated pages using TM01/TM02. Introduce a verified snapshot/session or streaming validation only if justified, keyed to exact bytes with explicit revalidation. Preserve standalone/full audits, deterministic filters, corruption detection and source-offline use; do not trust mtime-only caches. |

### M6

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="cf09"></a>[CF09](SHELVED.md#cf09) | active | Keep active; selected workload measured, larger scale/peak/human burden unmeasured | `execution.py:26,85`; the current queue row. Use TM01/TM02 on explicitly selected scale and cache state; historical 399-file measurements do not establish arbitrary scale. |
| <a id="cf10"></a>[CF10](SHELVED.md#cf10) | active | Keep active, only existing human acceptance conclusion remains | `qa.py:461`, the current queue row; technical corrected QA/export/import is delivered. Do not convert assistant conclusions to human. |
| <a id="tm02"></a>[TM02](SHELVED.md#tm02) | queued | Keep queued, pair with TM01 | `execution.py:26,95-97` has logical payload/elapsed metrics only. Optional process/child peak RSS and scratch sampling must record platform/availability/sampling semantics; preserve historical metrics. |
| <a id="cf14"></a>[CF14](SHELVED.md#cf14) | queued | Keep queued; small reusable QA enhancement | `qa.py:374-381,442-483`. Add character/word/geometry distributions, unknowns and stable outlier links; tokenizer remains NF18. |
| <a id="cf15"></a>[CF15](SHELVED.md#cf15) | queued | Keep queued; extend NF06 comparability context | `snapshot_comparison.py:36,133,266,287`. Compare frozen source/review/model/rules/runtime provenance with explicit unavailable fields; equal counts do not mean equivalent processing. |
| <a id="nf13"></a>[NF13](SHELVED.md#nf13) | queued | Keep queued, useful portability continuation after CF22 | Export/catalog/comparison artifacts are portable (`dataset_catalog.py:385`, `snapshot_comparison.py:250`), but QA assessments and trainer receipts remain separate. Bundle verified selected evidence without modifying export or copying acceptance; manifest scope, provenance and read-only replay required. |
| <a id="qol15"></a>[QOL15](SHELVED.md#qol15) | queued | Open; refine to measured gaps | HTML has labels, focus styling, status roles, keyboard routes and focusable long caption text. `qa_report.js:22` changes status text but almost no error-focus or focus-return logic exists; full screen-reader/keyboard order/contrast acceptance is unmeasured. Audit failed save/retry and disclosure focus before broad visual changes; include label CF23. Do not call existing ARIA/status support absent. |
| <a id="qol16"></a>[QOL16](SHELVED.md#qol16) | queued | Open platform acceptance; partial browser evidence | `qa_report.html:42`–54 has responsive layouts, wrapped paths and bounded lists; recent phases exercised narrow DOM/geometry. Real Windows DPI/display scaling, screenshots/pixel review and human ease of use are separate. Target long paths, 20-row pair/diff lists, receipt tables and zoomed captions at actual practical scaling; no speculative redesign. |
| <a id="qol17"></a>[QOL17](SHELVED.md#qol17) | queued | Substantially implemented in report; refine remaining presentation only | `qa_content.js:29`–38 already shows occurrences versus unique hashes, tagging coverage and annotation review counts; `renderAccounting` at 78–99 includes included/excluded/unreviewed, unique hashes and missing captions. `qa_report.js:41`–46 still has generic top-level “images”/“pilot images” metrics. Narrow remaining scope to consistent units at those entry points and any proven ambiguous totals; do not queue recreation of existing reconciliation/content tables. |
| <a id="qol19"></a>[QOL19](SHELVED.md#qol19) | queued | Partial, open actionable navigation | `qa_training.js:10`–40 already selects exact receipts and links logs/results; `loadTraining:47` separates export integrity/import/pilot acceptance and latest receipt. `qa_workflow.js` QOL10 already links changes to publication. Missing: direct navigation from remaining pilot/failed-check counts to exact actionable images/receipts/changed snapshot, with dirty-state guards. Reuse these surfaces rather than another qualification dashboard. |
| <a id="sc18"></a>[SC18](SHELVED.md#sc18) | queued | Keep queued with delivered partial scope | `scripts/package_smoke.py:341,2810` is tracked installed CLI/API/package/recovery tooling; rendered browser/restart/fault procedures still rely on ignored phase scripts. Promote one reusable generated fixture/controller and receipt schema, not every historical helper. |
| <a id="sc19"></a>[SC19](SHELVED.md#sc19) | completed | Retain completed source support; hosted qualification still open evidence | `.github/workflows/ci.yml:12-65` defines pinned Windows/Linux locked lint/tests/build/installed smoke and evidence upload. No hosted run was inspected here. Append current local evidence rather than reopening delivered CI source work. |
| <a id="tm12"></a>[TM12](SHELVED.md#tm12) | queued | Open, performance unmeasured | `qa.py:283`–311 reads/decodes every member to a report-local path-specific preview before `select_pilot` at 422. Aliases and successive runs are regenerated. Consider source-content+orientation/preview-policy cache with atomic checked materialization into portable report, retaining no silent source trust. Measure full-QA and first-use latency before selecting. |
| <a id="tm13"></a>[TM13](SHELVED.md#tm13) | queued | Open, performance unmeasured | `render_qa:106`–131 embeds all entries; `qa_report.js:39` builds option sets and `apply:125` scans them locally; pair endpoints are already paged at 20 (`review_ui.py:126`). Large live image delivery could be paged; static report remains portable. QOL07 named filters/resume and exact fragment semantics must survive; avoid replacing pair paging that already exists. |
| <a id="tm20"></a>[TM20](SHELVED.md#tm20) | completed | Retain completed, append current evidence | `scripts/package_smoke.py:42,2810` checks source archive, wheel/install/runtime resources outside checkout. Row's original 58-file/41-command count is historical, not the latest limit. Current 0.17 qualification reports 137 commands and 24 preference HTTP checks. |

### Delivered product phase

| Finding | State | Current source / disposition | Remaining outcome and verification |
| --- | --- | --- | --- |
| <a id="dp01"></a>[DP01](SHELVED.md#dp01) | completed | Current preparation/status/cache, registry/catalog, restore/recovery and RunClock implementation identity substantiate previously delivered bounded scope. | Keep completion links and human acceptance separate. New correctness defects get new findings or explicit limited remainders; do not reset whole delivered stages. |
| <a id="dp02"></a>[DP02](SHELVED.md#dp02) | completed | `dataset_catalog.py` writes/verifies portable SQLite/JSONL ingest metadata and supports standalone historical exports. | Retain delivered portable ingest scope. CF22 fixes metadata snapshot coherence; TM21 measures query cost. Neither means the database feature is absent. |

## Verification and workflow handoff

The review's document checks verify stable IDs and state counts, source links and
anchors, preservation of all prior queue actions and TODO task bodies, and unchanged
runtime/test/package source hashes. They do not verify the proposed fixes. Exact
results are retained in `.cache/workflow-source-review-20261112/document-validation.json`.

When CF21/CF23 are implemented, qualify their actual changed paths, archive dates,
version, evidence and limits in [COMPLETED](COMPLETED.md), and reconcile SHELVED.
Then promote the next bounded candidate in [PLAN order](PLAN.md#source-reconciliation-and-next-batch).
Do not mark source delivery as human acceptance, copy the whole queue into TODO,
or start a replacement IDENTIFIED cycle while required acceptance remains open.

### Subsequent bounded delivery — 0.18.0

This source review remains the frozen 0.17.0 audit. CF21/CF23 were subsequently
implemented and qualified in [COMPLETED](COMPLETED.md#review-integrity-0180).
Their historical locations and probes above explain the original findings;
they are not current failure claims. The reconciled queue and next source batch
are [SHELVED](SHELVED.md#current-source-priorities) and
[TODO](../TODO.md#model-binding-rule-contract). Human acceptance and the current
PLAN remain open; no replacement IDENTIFIED cycle has begun.

### Subsequent model/rule delivery — 0.19.0

CF24 and the bounded SC06 saved-rule contract were subsequently implemented and
qualified in [COMPLETED](COMPLETED.md#model-rule-contract-0190). This remains the
frozen 0.17.0 audit; the original probes above are historical findings. SC06's
broader schema-reader proposal remains queued. The next scheduled source batch
is [CF22](../TODO.md#artifact-snapshot-coherence), with human acceptance separate
and the existing PLAN still open.

### Subsequent artifact snapshot delivery — 0.20.0

CF22 was subsequently implemented and qualified in
[COMPLETED](COMPLETED.md#artifact-coherence-0200). This remains the frozen 0.17.0
audit; the original race observations remain historical evidence. SC02 and TM21
remain queued. The next scheduled source batch is
[QOL21/localized SC15](../TODO.md#publication-reconnect-ordering), with human
acceptance separate and the existing PLAN still open.
