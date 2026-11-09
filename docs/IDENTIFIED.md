# Project review and identified improvements
<!--
WORKFLOW_UTILIZED: "MIVIM.spec":"IDENTIFY"
--------
1. REVIEW THE PROJECT.
2. IDENTIFY THE PROJECTS CURRENT STATE VS ITS INTENDED DESIGN.
3. IDENTIFY ITS STRENGTHS AND WEAKNESSES.
4. IDENTIFY LARGE BULLET POINT LISTS OF;
   1. NEW-FEATURES-AND-ADDITIONS,
   2. SOURCE-CODE-CHANGES,
   3. QOL-ENHANCEMENTS,
   4. CORE-FUNCTION-IMPROVEMENTS.
   5. TECHNICAL-MODULE-ENHANCEMENTS
5. Utilize the contextual knowledge gained [1, 2, 3, 4] and create a document of your findings, and the data collected in [4], The document should be titled IDENTIFIED.md , and placed in the docs directory.
-->

Reviewed **2026-11-09**, against the working tree at Git HEAD **574673e**.
Declared package version: **0.5.1**. This review includes existing uncommitted
implementation work; it is not a statement that all reviewed features are in an
installed or released 0.5.1 build.

## Scope and authority

The governing design is [PLAN.md](PLAN.md), especially its work order and
completion boundaries. [TODO.md](../TODO.md) tracks unfinished work;
[COMPLETED.md](COMPLETED.md) records implementation and evidence;
[TRAINIME.md](TRAINIME.md) defines the separate directory-action contract.
[TAGGING-METHODS.md](TAGGING-METHODS.md) preserves the original rough notes and
examples, including defects explicitly superseded by PLAN.md. Those examples are
not an alternative specification to implement literally.

The review covered the design documents, command surfaces, configuration,
application module/function inventory, important execution paths, browser resources,
installer/recovery scripts, tests, and retained verification artifacts. The source
inventory contains **37 Python files, 9,265 Python lines, and 290 function/method
definitions**, including private and nested functions; there are four JavaScript
files, one browser HTML template, and 13 test modules. These are scope measurements,
not quality scores. The assessment is global and at subsystem level, not an
independent proof of every branch of every method.

No repository AGENTS.md or CodeGraph index was present. The supplied instruction to
use CodeGraph when indexed therefore did not apply. No proprietary agent workflow
was required. No user collection was selected, searched for, modified, or assessed.

The proposal lists below identify development opportunities. They do **not** amend
the approved plan or turn optional extensions into missing original requirements.
Application source was not changed for this review.

## Current state versus intended design

The application already implements a substantial local dataset-preparation system.
It can inventory images, propose and review related pairs, run pinned local tagging,
regenerate captions from scores, retain corrections, balance whole related groups,
publish verified exports, exercise a pinned trainer's CPU dataset loader, and
produce navigable QA reports. M5 exists in source and has actual upstream loader
evidence. It is incorrect to describe exports or the review-to-export chain as
wholly missing.

The largest remaining gap is the distance between implemented mechanics and a
qualified representative collection. M2 pair calibration, M3 model/label evaluation,
M4 caption suitability, M5 representative export acceptance, and M6 full-collection
acceptance are still open. Some supporting capabilities also remain incomplete:
there is no dedicated model-comparison/label-ground-truth evaluation workflow,
resource measurements are deliberately partial, and several operations retain
collection-sized data in memory.

| Area | Intended behavior | Current implementation | Remaining boundary |
| --- | --- | --- | --- |
| M1 — intake | Complete inventory, validated decoding, exact identities, preserved sources | Full SHA256, deterministic traversal, EXIF-aware dimensions, decode/file limits, sidecar associations, exact aliases, reports and strict config | No new missing core M1 stage identified. Collection-scale throughput and unsupported formats need evidence before extending scope. |
| M2 — similarity and groups | Propose likely relations, preserve variants, record human decisions, keep groups together | Indexed 64-bit pHash; durable related/distinct and image decisions; manual pairs; transitive groups; graphical comparison; 0–64 threshold evaluation over saved judgments | Representative positive/negative judgments, known misses outside proposals, threshold calibration, and expected-size performance remain unqualified. |
| M3 — local tagging | Pinned reference preprocessing, explicit providers, full scores, resumable inference and local evaluation | SwinV2/ViT-Large/EVA02 profiles, artifact hashes, CPU/CUDA/auto handling, complete score caching, duplicate reuse and score-only recaption | SwinV2 has historical real CPU smoke evidence. Alternate weights, physical CUDA, same-pilot model comparison, measured label accuracy and held-out calibration remain open. |
| M4 — captions/review | Versioned normalization, preserved overrides, explicit annotations, appropriate subset rules | Threshold/drop/character policies; optional trigger and forced phrases; composition/conflict findings; subset proposals and explicit acceptance; manual captions/labels/subsets; pilot judgments | Representative caption accuracy and rule suitability are unaccepted. Saved label checks do not yet constitute a complete ground-truth classification evaluation. |
| M5 — split/export | Deterministic group splits, paired captions, immutable snapshots, trainer-compatible configuration | Semantic or size allocation; copy/re-encode publication; independent verification; Kohya TOML; actual pinned CPU import; export-bound receipts and graphical status | Representative reviewed export/import acceptance remains open. The bounded split heuristic does not promise optimal balance; import does not test tokenization or training. |
| M6 — full collection/QA | Qualified batch, reconciled counts, resource data, corrected pilot findings, recorded acceptance | Pilot selection/navigation, corrections, assessments, content/rating/tag/provenance reporting, identity/count reconciliation, stage timing and logical payload sizes | Full-collection run and user acceptance remain open. Peak memory, peak temporary disk and complete storage cost are not measured. Geometry/caption lengths are primarily per-image data rather than aggregate report distributions. |
| Trainime directory actions | Exact four-choice menu; create missing captions; back up and remove matched captions; concise operation output | Menu, direct commands, saved/session paths, read-only previews, progress, journals, locks, automatic model setup and registered collision repair | No automatic caption-restore command; recovery uses retained backup files. Current installed build was not requalified during this audit. |
| Installation/recovery | Runnable Windows installation with actionable diagnosis and repeatable repair | install.cmd/install.ps1, pinned uv bootstrap, isolated native probe, retained wheel/pins/receipts, doctor/logs and package repair | Historical Windows x64 evidence exists. ARM64 and other OS installer qualification are absent; no repository CI configuration was found. |

## Workflow and interface alignment

| Surface | Actual responsibility and output | Alignment assessment |
| --- | --- | --- |
| `trainime tag <directory>` | Writes missing image-adjacent `.txt` files; preserves existing captions. Operational evidence lives under the Trainime application directory. | Deliberately mutates source-side captions. It is not equivalent to technical draft generation. |
| `trainime remove <directory>` | Copies and verifies matched captions into operation recovery, then removes originals, including manual captions. | Matches the explicit directory contract. It is not a dataset exclusion command. |
| `trainime fix` / `--fix` | Dispatches registered repairs; current production repair `tf001` renames colliding image stems and preserves ambiguous captions. | Image bytes remain unchanged, but names can change. This authorized exception must remain separate from technical source preservation. |
| `dataset scan` / `similarity` | Publishes inventories, fingerprints and proposal artifacts under configured run paths. | Read-only sources, separate artifacts, full identity checks. |
| `dataset fetch-model` / `tag` / `recaption` | Fetches a pinned bundle; publishes model scores and technical drafts; regenerates drafts without inference. | Source sidecars remain unchanged. Drafts alone are not a trainer export. |
| `dataset review` / `groups` | Records current decisions separately, then freezes them into a group snapshot. | Corrections survive unchanged-source reruns. A new snapshot is necessary to publish later decisions. |
| `dataset export` / `verify-export` | Produces new image/caption pairs and frozen provenance under exports; verifies without the original collection. | Shared membership, caption precedence, split and integrity rules are implemented. |
| `dataset qa` / `qa-list` | Publishes a report and previews; filters saved entries from CLI. | Shares QA data with the browser. Group reports preview assignments; export reports retain published assignments. |
| Static `report.html` | Browses saved evidence, captions, findings and coverage; exposes copyable review commands. | A read-only report. It cannot persist corrections by itself. |
| `dataset review-ui` | Starts a loopback reviewer for direct corrections, pair review/evaluation, pilot assessments and group/export/QA publication. | Uses the same Python review/export functions as CLI. It is a focused reviewer, not a graphical replacement for every intake/model command. |
| `trainer-setup` / `trainer-check` / `trainer-status` | Prepares an isolated runtime, checks a specific export with the upstream CPU loader, and reads bound receipts. | GUI displays receipts/status; imports are started through CLI. Starting imports from GUI is an optional proposal, not an original missing requirement. |

The intended route is:

```text
explicitly selected originals and existing captions
  -> scan -> similarity -> reviewed pair/image decisions
  -> pinned tag scores -> caption rules / recaption -> saved corrections
  -> group snapshot -> semantic split -> verified export
  -> export QA + pinned CPU trainer import + recorded pilot assessment
  -> downstream training, separately evaluated
```

Tagging and relation review can proceed from the same inventory; publication must
reconcile their identities. CLI/GUI alignment is strongest at the shared core-function
boundary. Convenience remains uneven: the reviewer needs an existing report and
lineage, technical commands need explicit run paths, and persistent review identity
is tied to the source location. These are usability/portability opportunities,
not evidence that the two interfaces should be merged.

## Module and feature inventory

Every Python module is represented below. Public/private helper families are grouped
by responsibility so the inventory remains useful without a 290-symbol dump.

| Modules/resources | Implemented responsibility | Material limitation or improvement target |
| --- | --- | --- |
| [`__init__.py`](../src/image_dataset_train/__init__.py), [`__main__.py`](../src/image_dataset_train/__main__.py), [bootstrap.py](../src/image_dataset_train/bootstrap.py) | Version, module/command entry points, lazy startup and failure/cancellation handling | Version alone cannot distinguish recent uncommitted feature sets. Bootstrap's generic resume wording is broader than some stages' actual resume behavior. |
| [cli.py](../src/image_dataset_train/cli.py) | 17 technical commands; parsing, config overrides, invocation, text/JSON output and exit status | Large parser/dispatch module; stage discovery and repeat run selection still require manual path management. |
| [config.py](../src/image_dataset_train/config.py), [annotations.py](../src/image_dataset_train/annotations.py) | Strict TOML keys, typed settings, finite thresholds, subset predicates, annotation normalization and summaries | Frozen dataclasses contain mutable lists/dicts. Annotation names are normalized but there is no collection vocabulary/alias management. |
| [inventory.py](../src/image_dataset_train/inventory.py) | Traversal, complete hashing, image validation, sidecar association, exact duplicate records and counts | All records are materialized; all regular file bytes are hashed, including unsupported files. No visual blank/blur/watermark classifier is implemented or implied. |
| [inventory_data.py](../src/image_dataset_train/inventory_data.py), [runs.py](../src/image_dataset_train/runs.py) | Checked inventory loading, stage publication, HTML/JSON evidence and intake timing | Common artifact validation/publication patterns are repeated in later stages. No incremental scan protocol is provided. |
| [similarity.py](../src/image_dataset_train/similarity.py) | Versioned DCT pHash, BK-tree queries, streamed proposal files and source rechecks | Index and image data are memory-resident; dense neighborhoods can still produce quadratic output. No normalized-pixel or embedding backend. |
| [similarity_evaluation.py](../src/image_dataset_train/similarity_evaluation.py) | Explicit-judgment threshold sweep, unique SHA-pair weighting, false/known-miss examples, saved evidence | Metrics describe the judged set, not unseen pairs. Sampling/held-out protocols are not built into the evaluator. |
| [model_bundle.py](../src/image_dataset_train/model_bundle.py) | Three WD profiles, pinned downloads, CSV category/index validation and artifact identities | WD-specific registry; alternate backends need explicit preprocessing/output contracts. Its “only stage” network docstring predates trainer setup. |
| [wd_tagger.py](../src/image_dataset_train/wd_tagger.py) | Reference preparation, tensor validation, provider setup/fallback reporting and inference | Only dynamic batch or fixed batch one; no measured adaptive batching or physical GPU qualification. |
| [score_cache.py](../src/image_dataset_train/score_cache.py), [tagging.py](../src/image_dataset_train/tagging.py) | Complete checked vectors, verified cache reuse, batch inference, self-contained scored runs and recaption | Tagging/recaption retain all unique vectors in memory. Each scored run copies its score payload; storage grows with recaption history. |
| [captions.py](../src/image_dataset_train/captions.py) | Deterministic caption records, versioned rule identity, observed/selected separation, neutral composition and subset proposals | No ground-truth evaluator, target tokenizer, natural-language adapter or automatic implication engine. None should be inferred from ordinary caption output. |
| [reviews.py](../src/image_dataset_train/reviews.py) | Source/run context, revisioned image/pair store, overrides, annotations, conflict checks and group publication | One JSON file contains current state plus full history. Each save rereads/rewrites it and rebuilds grouping; relocation and large histories need attention. |
| [splitting.py](../src/image_dataset_train/splitting.py) | Seeded whole-group size allocation, semantic moves/swaps and category coverage | Ratio has priority over semantic improvement; bounded search may miss better allocations. No explicit reviewed allocation constraints or comparison of candidate seeds. |
| [exporting.py](../src/image_dataset_train/exporting.py) | Caption precedence, source checks, derivatives, immutable pairs, Kohya configuration, frozen analysis and offline verification | Large module also owns helpers consumed by QA/reviews/receipts. ICC conversion and multiple target export profiles are not implemented. |
| [qa.py](../src/image_dataset_train/qa.py) | Snapshot loading, per-image findings, previews, coverage-aware pilot selection, HTML and CLI filtering | Generates previews for all snapshot entries before selecting the pilot; embeds all entries in HTML. Sampling is deterministic but not proof of statistical representation. |
| [reporting.py](../src/image_dataset_train/reporting.py) | Snapshot/included content scopes, ratings, top tags, model provenance and count/identity reconciliation | Top tags capped at 100. No shared aggregate geometry/caption-length distributions or quantitative model-comparison report. |
| [execution.py](../src/image_dataset_train/execution.py) | Monotonic stage receipts, source byte counts, membership digest and deduplicated processing history | Logical payload bytes exclude final root reports, shared caches/models, allocation overhead and peak temporary space; timing excludes human waits/final presentation work. |
| [assessments.py](../src/image_dataset_train/assessments.py) | Report-bound human image/caption/label judgments, revisions and explicit pilot conclusions | “Correct/missing/spurious” checks lack the full predicted/actual presence matrix needed for general label precision/recall. Acceptance applies to that report's pilot only. |
| [review_ui.py](../src/image_dataset_train/review_ui.py) | Loopback HTTP session, checked image/receipt serving, correction/pair/evaluation/assessment endpoints | Local single-operator tool, not a remote collaboration service. Whole report/session state remains in memory; several private core helpers are imported. |
| [review_publication.py](../src/image_dataset_train/review_publication.py) | Background group/export/QA publication, progress and preservation of successful earlier outputs on failure | Job status is process-local; there is no durable restart queue or cooperative cancel control. Published artifacts survive independently. |
| [qa_report.html](../src/image_dataset_train/qa_report.html), [qa_report.js](../src/image_dataset_train/qa_report.js) | Layout, image filters/queue, captions, direct edits, assessment forms, dirty-state navigation and command copying | Functional plain JavaScript UI; shared global state and DOM IDs couple features. Keyboard, accessibility and varied display acceptance need broader evidence. |
| [qa_workflow.js](../src/image_dataset_train/qa_workflow.js), [qa_content.js](../src/image_dataset_train/qa_content.js), [qa_training.js](../src/image_dataset_train/qa_training.js) | Pair/evaluation/publication, snapshot accounting/content, and trainer receipt views | Shared script ordering/state; larger reports and stale multi-session workflows need focused usability work. |
| [trainer.py](../src/image_dataset_train/trainer.py), [trainer_worker.py](../src/image_dataset_train/trainer_worker.py), [trainer_receipts.py](../src/image_dataset_train/trainer_receipts.py) | Isolated pinned setup; upstream parser/loader/buckets/tensors; immutable export checks; current-pin receipt history | One trainer adapter and CPU dataset-import scope. Receipt discovery scans run directories and verifies exports on status reads. |
| [trainer-requirements.in](../src/image_dataset_train/trainer-requirements.in), [trainer-requirements.txt](../src/image_dataset_train/trainer-requirements.txt) | Separate dependency intent and exact trainer runtime pins | Pin maintenance needs a repeatable compatibility process; application and trainer dependencies must remain separated. |
| [trainime.py](../src/image_dataset_train/trainime.py), [preferences.py](../src/image_dataset_train/preferences.py) | Four-choice terminal UX, direct commands, progress, settings and path normalization | Keep menu scope stable. Technical workflow profiles belong outside these two path settings. |
| [operations.py](../src/image_dataset_train/operations.py) | Directory planning, source locks, exclusive caption creation, verified backup/removal and journals | No user-facing restore workflow. Repeated pair rechecks enumerate directories and rehash files; cost needs real-size measurement. |
| [terror.py](../src/image_dataset_train/terror.py), [repairs.py](../src/image_dataset_train/repairs.py), [collision_fix.py](../src/image_dataset_train/collision_fix.py) | Numeric error/fix registry, multi-handler dispatch, collision planning, preserved captions and interruption recovery | Only `tf001` is a production directory repair. Extensibility is implemented; other repair behaviors are not. Do not mistake test handlers for shipping fixes. |
| [diagnostics.py](../src/image_dataset_train/diagnostics.py) | Structured/redacted logs, diagnosis mapping, atomic JSON and bounded publication retries | Diagnosis often interprets exception messages. Paths remain in local logs; no complete support-bundle/export policy exists. |
| [doctor.py](../src/image_dataset_train/doctor.py), [repair_package.py](../src/image_dataset_train/repair_package.py) | Stdlib-accessible probes, settings/model/cache/runtime/PATH repair and verified wheel restoration | Broad operational responsibility and platform branches; installed-runtime qualification is separate from editable-source tests. |
| [install.cmd](../install.cmd), [install.ps1](../install.ps1) | Windows bootstrap, isolated installation checks, PATH registration, retained repair assets and receipts | Windows-specific deployment; current source changes do not automatically update the installed tool. |
| [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock), [tests](../tests) | Package metadata, mutually exclusive runtime extras, locked development environment and automated regression suite | No checked-in CI workflow or test-coverage measurement found. Passing tests are not representative image-quality evidence. |

## Verification evidence and its limits

This audit inspected retained results; it did not rerun model downloads, installation,
the full regression suite, browser acceptance, or trainer execution. The technical
CLI help path was exercised successfully. Evidence files under `.cache` are local,
ignored development artifacts, not guaranteed contents of a checkout or release.

| Evidence inspected or referenced | What it establishes | What it does not establish |
| --- | --- | --- |
| `.cache/m2-evaluation-final.xml`, 2026-11-09: 276 cases, **274 passed, 2 skipped**, no failures/errors | Recorded broad source regression result, including recent evaluation work | A new test run for this audit, line coverage, representative accuracy, or installed-release parity |
| `.cache/m2-evaluation-version.xml`: **2 passed** after the final evaluation metadata refinement | Focused check of the subsequent metadata change | A second full-suite run |
| Latest skips: symlink privilege unavailable; case-only caption names unsupported in standard Windows directories | Precisely bounded platform coverage omissions | Proof that those behaviors work on every platform; junction tests are distinct from the symlink skip |
| `.cache/m2-evaluation-build/resource-check.json` | Retained wheel/sdist comparison says six changed evaluation resources match source | Byte identity of every installed package file, or a published release |
| `.cache/m2-evaluation-smoke/verification.json` | CLI/GUI summary equality, all 65 threshold rows, error-to-pair navigation; screenshot retained alongside | Representative pair accuracy or broad visual/accessibility acceptance |
| `.cache/m6-accounting-smoke/verification.json` | Live/static accounting checks, source/upstream-offline export reporting, visible legacy gaps | Full visual qualification: screenshot capture timed out in that check |
| `.cache/trainer-ui-smoke/3d779627/runs/20261109T092828423603Z-trainer-9602f377/result.json` | Actual pinned CPU import: two train images/four repeated instances, one validation image, 384×256 buckets, `qualified: true` | Tokenization or a training step: both explicitly false. No physical GPU or collection acceptance |
| [TAGGING.md](TAGGING.md) and historical [COMPLETED.md](COMPLETED.md) smoke records | Documented real SwinV2 CPU execution and publisher preprocessing parity, on generated images | New inference during this audit, alternate-model accuracy, or a current collection benchmark |
| Historical installation/Trainime entries in [COMPLETED.md](COMPLETED.md) | Documented installed Windows command, repair, source preservation and backup behavior for their recorded versions | Fresh installation acceptance of all current working-tree changes |

No current data corruption incident or reproducible core failure was established by
this review. That is a bounded finding, not a claim of defect-free software. The
strongest confirmed weaknesses are missing qualification, scaling characteristics,
workflow gaps and maintainability costs visible in source.

## Strengths

- **Original intent is preserved.** Technical preparation is local and source-preserving;
  explicit Trainime caption mutations are documented separately.
- **Useful end-to-end functionality exists.** Intake through reviewed export and actual
  upstream dataset import is implemented, with both CLI and graphical review paths.
- **Content identity is substantive.** Full hashes, occurrence paths, artifact checksums
  and frozen provenance prevent counts or names alone from being treated as identity.
- **Scored evidence is reusable.** Caption policy can change without another model run;
  complete vectors retain ratings and omitted character evidence.
- **Preprocessing/provider behavior is explicit.** Category indices, tensor shapes,
  alpha/EXIF policy, requested CUDA failure and automatic fallback are represented.
- **Human corrections are durable.** Separate review state and snapshot publication
  prevent a model rerun from silently overwriting accepted corrections.
- **Related variants are preserved.** Similarity proposes; humans decide. Exact aliases
  retain occurrence-level provenance and captions; exclusions do not delete files.
- **Split leakage is addressed at the right level.** Whole connected groups and exact
  aliases stay together, with actual semantic coverage reported.
- **Exports are independently checkable.** Copied pairs, frozen inputs and portable
  verification make the export more than an untracked sidecar folder.
- **Trainer evidence uses the real loader.** It exercises upstream discovery, repeats,
  buckets and tensors instead of only validating locally invented TOML assumptions.
- **Operational recovery is substantial.** Backup verification, journals, exclusive
  publication, targeted repairs and a dependency-light doctor go beyond happy paths.
- **Qualification language is mostly disciplined.** Current documents distinguish
  generated fixtures, CPU execution, import, human acceptance and training results.
- **Dependencies are restrained by role.** Core operation, optional tagging and the
  isolated trainer runtime do not require one universal heavy environment.
- **The GUI reuses core actions.** Reviews, publication, evaluation and receipt status
  share source with CLI rather than implementing parallel business rules in JavaScript.

## Weaknesses and unresolved risks

The labels below distinguish observed omissions from engineering risks. A risk is
not a reproduced failure, and an optional extension is not a missed commitment.

| Finding | Basis and consequence | Classification |
| --- | --- | --- |
| No representative collection acceptance | PLAN/TODO explicitly leave M2–M6 collection evidence open. Correct artifact mechanics can still produce unsuitable captions or weak groups. | Confirmed acceptance gap; highest priority |
| Missing complete tagger evaluation workflow | Pair evaluation exists, but critical-label checks do not store full predicted/actual presence or provide same-pilot model comparison and held-out threshold evaluation. | Confirmed capability gap supporting M3 |
| Pilot sampling cannot establish prevalence | `select_pilot` favors new findings/categories/geometry and group variety; it is not a probability sample with known inclusion weights. | Confirmed scope limitation |
| Tagging memory grows with collection size and vocabulary | `tag_inventory` and `recaption` retain all unique score arrays, while batch size bounds only active inference tensors. | Source-backed scaling risk; no measured failure claimed |
| Review saves grow with history and collection size | `ReviewStore.update` reads/revalidates and rewrites complete state/history and rebuilds groups even for image changes. | Source-backed latency/scaling risk |
| QA has collection-sized startup cost | `create_qa` decodes/previews all members before pilot selection; HTML embeds all entries and the browser filters them locally. | Source-backed memory/disk/latency risk |
| Indexed similarity can still emit huge results | BK-tree pruning avoids naive unconditional all-pairs distance checks, but many near-identical fingerprints still produce dense pair output. | Algorithmic output-size risk |
| Resource reporting is incomplete by design | Stage payload/timing excludes shared storage, final report files, peak temporary space, process memory and GPU usage. | Confirmed measurement limit, not false accounting |
| Snapshot geometry/length overview is thin | Dimensions/orientation and caption character/word counts are stored per entry; aggregate distributions/outlier navigation are not yet first-class. | Report improvement within PLAN section 6 |
| Split quality has a bounded optimum | Size priority, 32 passes and limited swap candidates can leave semantic imbalances; exact ratios can be impossible for whole groups. | Explicit algorithm limitation |
| Portability differs between artifacts and editing | Export verification can work offline; live correction requires compatible review lineage/source context. Review namespaces depend on absolute source roots. | Confirmed workflow limitation |
| Publication recovery is only partially surfaced | Successful artifacts survive a later failure, but worker status is in memory and no restart/cancel workflow exists. | Confirmed operational limitation |
| Cross-module contracts are too implicit | QA imports ten private exporter helpers; reviews, receipts, UI and repairs also reach into other modules' private helpers. Many records are untyped dicts. | Confirmed maintainability weakness |
| Shared low-level behavior is duplicated | Atomic JSON implementations and bounded/hash-checked source reads exist in multiple modules with different details. | Confirmed divergence risk; not proof that current variants are wrong |
| Release state is difficult to infer from version alone | Extensive recent changes still report 0.5.1; `execution.py` and `similarity_evaluation.py` were untracked at audit start. | Confirmed release/provenance ambiguity |
| Qualification automation is local | No `.github`, GitLab CI or Azure pipeline configuration was found. Retained checks rely on local ignored evidence and manual invocation. | Repository automation gap; external CI was not inspected |
| Browser acceptance is narrower than feature breadth | Retained smoke checks cover important flows, but no comprehensive keyboard, screen-reader, high-DPI or large-report acceptance is recorded. | Evidence gap, not a claim of inaccessible UI |
| Recovery is technically possible but not fully guided | Removed captions have verified copies and journals; the application has no caption restore command or history browser. | Confirmed QOL capability gap |
| Derivative policy is intentionally limited | EXIF/white-alpha PNG conversion exists; ICC color management and target-specific tokenizer behavior do not. | Documented future/conditional work |

## How to read the improvement lists

There are **100 identified opportunities**, grouped by the five requested categories.
They are a development inventory, not 100 equal-priority tasks or an instruction to
build everything. Related entries describe different product or implementation
layers; linked entries should be scoped together rather than counted as independent
roadmap commitments.

- **P1:** directly supports the next documented qualification work or removes a
  practical obstacle to it. Follow M2 → M3 → M4 → M5 → M6 when scheduling.
- **P2:** improves an existing core path, maintainability or everyday use after the
  relevant need is demonstrated.
- **P3:** conditional extension; requires a concrete use case or chosen target.
- **Plan support** means it helps meet an existing requirement. **Proposal** means a
  newly identified option. **Conditional** means it should wait for supporting evidence.

### NEW-FEATURES-AND-ADDITIONS

- **NF01 — P1 / Plan support: Pair evaluation sets.** Add an explicitly saved M2
  calibration/held-out pair set, including manually selected pairs outside proposals,
  so the existing threshold sweep has a reproducible evaluation population.
- **NF02 — P1 / Plan support: Same-pilot model comparison.** Run SwinV2 and EVA02
  against identical selected image identities and produce one comparison artifact for
  quality, disagreement, runtime and memory. Reuse existing model profiles and caches.
- **NF03 — P1 / Plan support: Label ground-truth workspace.** Record actual presence,
  absence and uncertainty for chosen critical labels, separately from inclusion,
  caption checks and predicted tags. Supply the missing inputs to M3 accuracy metrics.
- **NF04 — P1 / Plan support: Calibration results as reusable profiles.** Save approved
  per-tag thresholds, model/rule identity and evaluation-set provenance as an explicit
  profile. Adoption remains deliberate; the evaluator must not silently rewrite config.
- **NF05 — P1 / Plan support: Frozen representative pilot membership.** Let a reviewer
  pin the pilot and add targeted cases, retaining selection reasons and unchanged
  membership across model and caption comparisons.
- **NF06 — P2 / Proposal: Snapshot comparison.** Compare two group/export snapshots
  by added/removed identities, caption edits, annotations, group merges and split moves,
  so changed training inputs can be understood without diffing raw JSONL.
- **NF07 — P2 / Proposal: Collection/run catalog.** Offer a local catalog of explicitly
  registered collections and their existing runs, current review revisions, exports and
  receipts. It should never discover unrelated image directories automatically.
- **NF08 — P2 / Proposal: Caption restore.** Add a direct restore command for a selected
  removal receipt, with preview and per-file results; retain newly created captions and
  require an explicit decision for conflicts. Keep the four-choice Home menu intact.
- **NF09 — P2 / Proposal: Source relocation.** Rebind a collection to a new root using
  relative paths and verified content identities, preserving aliases and review history
  without assuming that matching filenames establish continuity.
- **NF10 — P2 / Proposal: Review history viewer.** Show the changes to an image/pair
  and allow an explicit revert that creates a new review revision rather than erasing
  the original decision history.
- **NF11 — P2 / Proposal: Reviewed bulk annotation.** Apply a label/subset or decision
  to an explicitly selected set of images, with visible selection and one coherent
  recorded action. Do not add automatic “accept all model tags” behavior.
- **NF12 — P2 / Proposal: Named caption/export profiles.** Save technical workflow
  settings for distinct training targets, with profile identity in resulting artifacts.
  This belongs in the technical pipeline, not Trainime's simple path settings.
- **NF13 — P2 / Proposal: Evidence bundle export.** Package a chosen export's QA,
  assessments and trainer receipts as a separate portable review bundle, leaving the
  immutable training export unchanged.
- **NF14 — P2 / Proposal: Storage inventory and retention preview.** Report models,
  caches, snapshots, backups and pending runs by ownership and referenced status.
  Any cleanup is a separate explicit operation, not automatic backup expiry.
- **NF15 — P3 / Conditional: Normalized-pixel duplicate candidates.** Add the later
  PLAN option for metadata-only variants after defining a versioned decode/color/alpha
  policy. Preserve occurrence provenance and conflicting captions.
- **NF16 — P3 / Conditional: Embedding similarity.** Add a separately measured backend
  only if reviewed pilot misses show pHash is insufficient; keep its metric and
  threshold distinct from Hamming distance.
- **NF17 — P3 / Conditional: Another local caption backend.** Investigate Camie or a
  target-appropriate natural-language backend only after baseline evaluation, with its
  own vocabulary, preprocessing, model pin and compatibility review.
- **NF18 — P3 / Conditional: Target tokenizer analysis.** For a chosen training model,
  report token length/truncation and affected captions without confusing words or
  comma-separated phrases with tokenizer tokens.
- **NF19 — P3 / Conditional: Additional export adapters.** Support another trainer
  only when selected by a real workflow, with its own immutable configuration and
  actual import receipt rather than renaming the Kohya output.
- **NF20 — P3 / Conditional: Artwork/source identity metadata.** Add explicit reviewed
  artwork/series/source identifiers when available so known shared origins can assist
  leakage review. Do not infer them from arbitrary folder names.

### SOURCE-CODE-CHANGES

- **SC01 — P1 / Plan support: Separate score iteration from caption publication.**
  Refactor `tagging.py` to consume persisted vectors incrementally instead of requiring
  every vector in one dictionary; retain duplicate reuse and self-contained artifacts.
- **SC02 — P2 / Proposal: Public artifact reader layer.** Extract the shared checked
  run/JSONL/path/hash readers from `exporting.py` into a small public module used by
  QA, review and receipts. Preserve compatibility with existing exports.
- **SC03 — P2 / Proposal: Shared bounded source reads.** Consolidate repeated
  source-path containment, link, byte-limit and SHA checks while retaining each stage's
  explicit decode/preprocessing limits and source-availability contract.
- **SC04 — P2 / Proposal: One atomic JSON primitive.** Reconcile `model_bundle` and
  `diagnostics` writers, including encoding, temporary-file cleanup and durability
  expectations; route callers through the common implementation.
- **SC05 — P2 / Proposal: Typed artifact records.** Introduce lightweight typed records
  or TypedDicts for stage metadata, captions, reviews, split plans and receipts at
  subsystem boundaries; avoid a wholesale framework migration.
- **SC06 — P2 / Proposal: Central schema compatibility.** Make schema/analysis versions
  and legacy defaults explicit in one reader layer. Preserve the existing
  `caption_analysis_version: 1` verification contract when evolving fields.
- **SC07 — P2 / Proposal: Smaller CLI handlers.** Separate parsing from stage handlers
  and rendering in `cli.py`; keep command names, flags and exit semantics stable.
- **SC08 — P2 / Proposal: Decouple review graph computation.** Expose a tested public
  grouping/conflict service used by status, publication and evaluation instead of
  spreading dependencies on private review helpers.
- **SC09 — P2 / Proposal: Avoid graph rebuilds for unrelated edits.** Make caption or
  annotation changes reuse the graph for the same relation revision, while pair changes
  still trigger the required consistency calculation.
- **SC10 — P2 / Proposal: Separate review current state from growing history.** Design
  bounded current-state reads and append-only history/checkpoints after measuring
  save latency. Preserve atomic revision semantics and existing-store migration.
- **SC11 — P2 / Proposal: Shared operation primitives.** Move path rechecks, journals
  and short commit handling out of private `operations.py` imports used by collision
  repair, retaining the same source-lock and recovery behavior.
- **SC12 — P2 / Proposal: Real immutable configuration values.** Normalize mutable
  collections inside frozen settings to immutable forms or defensive copies, so a
  validated configuration cannot be modified unexpectedly through a list reference.
- **SC13 — P2 / Proposal: Common run publication lifecycle.** Factor allocation,
  completion metadata and staged publication into a small shared utility; keep
  stage-specific evidence and partial-run retention explicit.
- **SC14 — P2 / Proposal: Explicit frontend state boundaries.** Separate report,
  correction, assessment, pair and publication state from shared globals; retain the
  lightweight static-report architecture rather than adding a framework by default.
- **SC15 — P2 / Proposal: Shared frontend request handling.** Centralize JSON errors,
  stale response handling and revision conflicts across browser panels while allowing
  each form to preserve its unsaved edits.
- **SC16 — P2 / Proposal: Structured operational errors.** Use stable error codes and
  contextual fields where diagnosis currently depends on exception text; preserve
  readable original causes in logs.
- **SC17 — P2 / Proposal: Consistent executable provenance.** Record build/source
  identity in new stage receipts, including QA, so multiple feature sets carrying
  version 0.5.1 can be distinguished without interpreting timestamps alone.
- **SC18 — P2 / Proposal: Promote repeatable smoke commands.** Turn the useful retained
  CLI/GUI/package comparison procedures into small repository scripts, instead of
  leaving reproducibility dependent on one ignored development directory.
- **SC19 — P2 / Proposal: Proportionate automated CI.** Add lint, focused/full source
  regression, package-resource checks and a Windows operational lane. Keep heavy
  downloaded-model/trainer checks separate and explicitly scheduled.
- **SC20 — P2 / Proposal: Remove stale implementation claims in source comments.**
  Correct narrow inaccuracies such as the model module's “only stage” network claim
  and generic resume messages; derive practical help from actual stage behavior.

### QOL-ENHANCEMENTS

- **QOL01 — P1 / Plan support: Evaluation evidence coverage.** Extend the existing
  positive/negative and evidence-gap counts with calibration/held-out membership and
  case-type coverage, so reviewers can see which kinds of pair remain untested.
- **QOL02 — P1 / Plan support: Side-by-side model disagreements.** In NF02 comparisons,
  open the same image with each model's scores/caption changes and direct critical-label
  judgment controls; avoid making reviewers reconcile separate run folders.
- **QOL03 — P1 / Plan support: Critical-label checklist.** Present the selected
  evaluation vocabulary consistently, including absent/uncertain ground truth, while
  keeping ordinary caption correction separate from evaluation.
- **QOL04 — P2 / Proposal: Broader keyboard workflow.** Preserve existing arrow/j/k
  image navigation; add discoverable pair-comparison and save-and-next shortcuts with
  clear focus behavior and no activation while typing captions or notes.
- **QOL05 — P2 / Proposal: Better pair inspection.** Add synchronized zoom/pan and
  original-size toggles to compare crops, small edits and artifacts while retaining
  whole-image context.
- **QOL06 — P2 / Proposal: Visible membership before bulk edits.** For NF11, show the
  actual selected paths and count independently of the current filter, making it easy
  to see what an operation will change.
- **QOL07 — P2 / Proposal: Saved review filters.** Retain named filter combinations,
  last image and queue position per report; distinguish these browsing preferences
  from durable review decisions.
- **QOL08 — P2 / Proposal: More actionable empty states.** Explain whether an empty
  queue means no data, filtered-out data, no unresolved pairs or unavailable previews,
  with a direct way to reach the relevant populated view.
- **QOL09 — P2 / Proposal: Caption comparison view.** Display manual override, source
  sidecar and current draft together, with precedence and changed phrases visible
  before the reviewer saves a correction.
- **QOL10 — P2 / Proposal: Stale snapshot explanation.** Extend existing revision and
  unchanged-snapshot notices with a list of affected images/pairs and a direct path
  to republishing them; preserve the old report as historical evidence.
- **QOL11 — P2 / Proposal: Resumable publication presentation.** After a late-stage
  failure, show completed group/export paths and offer retry from the failed stage,
  instead of requiring the user to reconstruct the sequence from directories.
- **QOL12 — P2 / Proposal: Progress with meaningful units.** Report images processed,
  bytes copied, pairs produced or receipts checked where known; reserve indeterminate
  progress for phases without a defensible total.
- **QOL13 — P2 / Proposal: Copyable path and command actions.** Provide consistent copy
  controls for run paths, exports, reports and exact CLI equivalents, using the existing
  shell quoting helpers for spaces and Unicode.
- **QOL14 — P2 / Proposal: Run selection without path transcription.** Build on NF07
  with source/stage/date filters and visible input identity; avoid unsafe implicit
  “latest run” selection across different collections.
- **QOL15 — P2 / Proposal: Accessible review status.** Check form labels, error focus,
  status announcements, keyboard order and contrast on actual rendered pages; improve
  controls where evidence shows a problem rather than redesigning for appearance alone.
- **QOL16 — P2 / Proposal: High-DPI and narrow-window polish.** Verify long paths,
  paired-image comparison, receipt logs and accounting tables at practical Windows
  zoom/scaling settings, with usable scrolling and no hidden actions.
- **QOL17 — P2 / Proposal: Explain count units in place.** Show occurrence versus
  unique-image counts together where aliases matter, and distinguish untagged,
  unreviewed, excluded and missing-caption populations next to totals.
- **QOL18 — P2 / Proposal: Recovery operation browser.** List caption-removal and
  collision-repair receipts with affected paths and recovery locations, connecting
  diagnosis output directly to NF08/NF10 without adding Home menu choices.
- **QOL19 — P2 / Proposal: Actionable qualification summary.** Extend the existing
  separate integrity/import/pilot states with links to the exact failed receipt,
  unassessed pilot image or changed snapshot that needs attention.
- **QOL20 — P3 / Conditional: Start a trainer import from the reviewer.** If users
  demonstrate repeated terminal handoff friction, reuse the existing isolated CLI/core
  action with progress and receipts. This remains convenience, not a missing M5 stage.

### CORE-FUNCTION-IMPROVEMENTS

- **CF01 — P1 / Plan support: Establish representative M2 calibration.** Use NF01 to
  review known related and distinct pairs across artwork styles, edits, crops and
  compressions; include examples the original proposal radius missed.
- **CF02 — P1 / Plan support: Separate threshold fitting from evaluation.** Fit pHash
  radius on the calibration set and report behavior on the held-out set, preserving
  sample sizes and undefined metrics instead of selecting the best-looking sweep row.
- **CF03 — P1 / Plan support: Make graph conflicts explainable.** Show the actual
  related/exact path connecting a disputed distinct pair, so a reviewer can correct
  the specific mistaken relationship without dismantling a whole group blindly.
- **CF04 — P1 / Plan support: Measure label precision and recall.** Use NF03 predicted
  and actual presence to compute TP/FP/FN, denominators and per-label results; keep
  unreviewed/uncertain examples outside unsupported accuracy claims.
- **CF05 — P1 / Plan support: Compare models under the same conditions.** Use NF02 to
  measure composition errors and critical-label behavior on identical inputs, with
  pinned preprocessing/providers and cold/warm timing distinguished.
- **CF06 — P1 / Plan support: Calibrate caption thresholds on reviewed evidence.**
  Evaluate per-tag rules and character policy on a held-out pilot before changing
  defaults; retain disagreements instead of unioning every model prediction.
- **CF07 — P1 / Plan support: Qualify caption/subset semantics.** Review trigger/forced
  phrase suitability, contradictory counts, overlapping subset predicates and missing
  expectations on the selected M4 pilot; record corrections and reasons.
- **CF08 — P1 / Plan support: Reuse the same accepted pilot downstream.** Carry the
  approved M2–M4 image identities into M5 export/import checks, linking observed
  failures to the exact input, caption and configuration that produced them.
- **CF09 — P1 / Plan support: Run the intended collection workload.** Measure M2–M6
  throughput, output size and human correction burden at actual expected scale, then
  use the bottlenecks to choose SC01/SC10 or other performance work.
- **CF10 — P1 / Plan support: Close M6 with corrected evidence.** Publish updated QA
  after corrections, reconcile the final export, import it, and record human acceptance
  of that report rather than transferring acceptance from an older snapshot.
- **CF11 — P2 / Proposal: Improve split diagnostics before changing algorithms.**
  Quantify the ratio/category objective and explain impossible single-group strata,
  so users can distinguish structural limits from a heuristic that stopped early.
- **CF12 — P2 / Proposal: Compare bounded split candidates.** Offer a deterministic
  technical preview of a small set of seeds/search budgets; report tradeoffs and freeze
  the chosen assignments. Do not silently reshuffle a published export.
- **CF13 — P2 / Proposal: Reviewed assignment constraints.** If evaluation requires
  keeping a specific group in a split, allow explicit group constraints with provenance
  and coverage reporting; reject contradictory constraints instead of breaking groups.
- **CF14 — P2 / Proposal: Aggregate geometry and caption lengths.** Extend shared QA
  summaries with aspect-ratio/resolution and character/word-length distributions,
  missing-value counts and links to outliers. Tokenizer analysis stays target-specific.
- **CF15 — P2 / Proposal: Preserve comparability across reruns.** Report whether
  source bytes, review revision, model/runtime or caption rules changed between two
  runs; connect the change to NF06 instead of presenting totals without context.
- **CF16 — P2 / Proposal: Avoid unnecessary preprocessing allocations.** Investigate
  memory-bounded padding/resizing for extreme aspect ratios while verifying parity
  with the versioned WD/pHash preparation; do not silently alter image semantics.
- **CF17 — P2 / Proposal: Improve useful recovery after interruption.** Surface
  verified cached progress, retained pending artifacts and the exact remaining action
  for each stage. Treat inference resume, publication retry and repair resume distinctly.
- **CF18 — P2 / Proposal: Address content-color policy deliberately.** Define an ICC
  conversion option for training derivatives, preserving original hashes and conversion
  provenance. Keep existing `png-exif-white-v1` outputs reproducible.
- **CF19 — P2 / Proposal: Portable review continuation.** Combine NF09 relocation with
  compatible lineage resolution so a moved collection can continue review without
  rewriting historical exports or misapplying old decisions to changed images.
- **CF20 — P3 / Conditional: Additional quality findings.** Consider calibrated blur,
  border, watermark or blank-image proposals only after representative errors justify
  them; retain evidence and review decisions instead of automatic rejection rules.

### TECHNICAL-MODULE-ENHANCEMENTS

- **TM01 — P1 / Plan support: Collection benchmark harness.** Add a small runner for
  explicitly chosen inputs that records stage invocation, item counts, cache state,
  environment and metrics. It supports CF09 without pretending fixtures measure accuracy.
- **TM02 — P1 / Plan support: Peak resource sampling.** Extend `execution.py` with
  optional peak process memory and temporary-storage measurements; label platform
  availability and keep existing logical payload accounting compatible.
- **TM03 — P2 / Proposal: Inventory streaming interface.** Separate discovery/inspection
  iteration from association/duplicate indexing, enabling large scans to publish records
  without requiring one growing Python object list.
- **TM04 — P2 / Proposal: Incremental inventory indexes.** Reuse prior discovery data
  for planning, but retain content verification where snapshots depend on exact bytes;
  do not substitute size/mtime equality for SHA identity.
- **TM05 — P2 / Proposal: pHash feature reuse.** Cache fingerprints by content and
  preprocessing version so threshold experiments do not repeatedly decode unchanged
  images. Record cache identity in similarity runs.
- **TM06 — P2 / Proposal: Dense-neighborhood diagnostics.** Report candidate fan-out,
  index/query time and estimated output growth, allowing an explicit partial exploratory
  run when requested. Never label truncated proposal output as complete.
- **TM07 — P2 / Proposal: Score artifact iterator.** Supply checked lazy vector reads
  and bounded write batches for SC01; make cache repair and self-contained run copying
  use the same score checksum/index contract.
- **TM08 — P2 / Proposal: Measured inference tuning.** Add per-batch timing, effective
  batch/provider records and optional explicit batch backoff after memory failures,
  without turning requested CUDA into an undisclosed CPU run.
- **TM09 — P2 / Proposal: Caption rule explanations.** Return a compact decision trace
  for why a tag was selected, dropped, near threshold or used by a subset rule. Keep
  this derived evidence separate from the exported caption text.
- **TM10 — P2 / Proposal: Annotation vocabulary support.** Add optional preferred
  labels/aliases and unknown-label reporting to `annotations.py`; retain free-form
  reviewed data and distinguish aliases from automatic semantic equivalence.
- **TM11 — P2 / Proposal: Versioned graph cache.** Store/reuse exact-alias and reviewed
  relation components for matching inventory/relation revisions, reducing repeated
  graph work in status and image saves without hiding conflicts.
- **TM12 — P2 / Proposal: Preview cache.** Cache thumbnails by source hash and preview
  policy, reusing identical content across QA runs while keeping report output portable.
  Separate pilot-first browsing latency from full-snapshot summary computation.
- **TM13 — P2 / Proposal: Large-report delivery mode.** Add paged entry/filter endpoints
  to the live reviewer for measured large workloads, while retaining static report
  generation as an explicit portable mode with clear size costs.
- **TM14 — P2 / Proposal: Durable publication job record.** Persist stage/output/error
  state for `Publication`, enabling QOL11 recovery and an eventual cooperative cancel
  action between safe stage boundaries.
- **TM15 — P2 / Proposal: Efficient receipt discovery.** Add a rebuildable index keyed
  by export hash and trainer pin, then verify the selected receipt/artifacts. Retain
  visibility of invalid/stale receipts rather than trusting index entries alone.
- **TM16 — P2 / Proposal: Trainer compatibility harness.** Reuse a compact set of
  mixed-format/repeat/bucket fixtures when deliberately updating the pinned trainer
  or dependencies, recording before/after loader behavior and keeping old receipts.
- **TM17 — P2 / Proposal: Structured derivative policies.** Extract named conversion
  profiles from exporter branches, with explicit EXIF, alpha, color, encoding and
  no-upscale behavior. This supports CF18 without changing old profile semantics.
- **TM18 — P2 / Proposal: Review-store persistence boundary.** Define a narrow storage
  interface before choosing JSON checkpoints or SQLite for measured scale needs;
  preserve revision locking, history and readable export snapshots.
- **TM19 — P2 / Proposal: Platform qualification matrix.** Exercise real filesystem
  behavior for Windows junctions, permitted symlinks, case variants and installed
  recovery on supported hosts; do not infer ARM64 or Linux installer support from imports.
- **TM20 — P2 / Proposal: Packaged-resource verification.** Check that the installed
  wheel contains the same HTML/JS, trainer pins and newly added Python modules as the
  release candidate, and launch the technical/reviewer help paths from that wheel.

## Recommended development sequence

1. **Resolve M2 evidence first.** Select the collection explicitly, freeze a useful
   pair pilot, review positives/negatives and known misses, evaluate held-out behavior,
   and measure the expected pair workload. Existing evaluation source can already
   support much of this; add NF01/CF03 only where they remove real friction.
2. **Complete M3 comparison and measurement.** The most substantial missing supporting
   feature is NF02/NF03 with CF04–CF06: same-image model comparison, structured label
   truth, measured precision/recall and calibrated thresholds. Address score-memory
   growth as the pilot/benchmark demonstrates the need.
3. **Close M4 on the selected pilot.** Check actual captions, overrides, composition
   and subset rules. Record disagreement and corrections; publish a new report before
   accepting corrected evidence.
4. **Qualify M5 on those reviewed inputs.** Verify the export and run the existing
   pinned trainer import. Diagnose actual split/format issues before adding adapters
   or a new optimizer. M5 is implemented, not a stage to recreate.
5. **Complete M6 at collection scale.** Reconcile final membership/counts, report
   measured resources and unresolved cases, address pilot errors and record user
   acceptance. Include aggregate geometry/length views if needed for this review.
6. **Choose engineering improvements from measured costs.** Prioritize bounded score
   memory, review-save cost, preview reuse and run discovery over broad rewrites.
   Consolidate shared helpers as the touched paths need it; use proportionate tests
   for changed behavior and artifact compatibility.
7. **Prepare a distinct release candidate.** Include all runtime files, record a
   distinguishable build/version, run package/installed smoke checks and preserve the
   evidence scope. Do not assume the current installed command matches this worktree.
8. **Evaluate conditional additions last.** Embeddings, new caption backends,
   tokenizers and other trainers need demonstrated misses or a chosen target.

Without a selected representative collection, meaningful source work can still
improve comparison tooling, bounded-memory execution and review throughput. It
cannot complete the missing human/collection acceptance by generating more fixtures.

## Intent that future work must preserve

- Keep the exact Trainime Home workflow and its explicit source-side effects.
- Keep technical stages source-preserving and model inference local.
- Preserve original images, manual captions, aliases, reviews and recoverable backups.
- Keep model observations, configured phrases, human annotations and export captions
  as distinct evidence layers.
- Keep whole related groups intact across splits; never solve imbalance through leakage.
- Keep completed exports immutable and independently verifiable.
- Keep trainer import, tokenization, actual training and human acceptance distinct.
- Do not invent a universal content/age classifier, infer relationships from subject
  counts, or convert anime-specific visual characteristics into automatic rejection.
- Do not replace missing representative evidence with more documentation or tests
  that merely mirror implementation. New tests should exercise changed outcomes,
  meaningful failures or compatibility boundaries.

## Source and contract references

- [PLAN.md](PLAN.md): reviewed design, artifact flow, M1–M6 ordering and acceptance.
- [TODO.md](../TODO.md): unfinished requirements and acceptance dependencies.
- [COMPLETED.md](COMPLETED.md): implementation history and dated verification evidence.
- [README.md](../README.md): installation, two command workflows and runnable commands.
- [TRAINIME.md](TRAINIME.md) and [INSTALLATION.md](INSTALLATION.md): terminal UX,
  mutation/recovery behavior, installer and operational qualification.
- [SIMILARITY.md](SIMILARITY.md) and [REVIEW.md](REVIEW.md): pair proposals/evaluation,
  durable decisions, annotations and group semantics.
- [TAGGING.md](TAGGING.md): pinned model/preprocessing decisions, historical evidence,
  caption rules and unqualified model comparisons.
- [EXPORT.md](EXPORT.md): splits, immutable pairs, derivatives, verification and pinned imports.
- [QA.md](QA.md): static/live reports, corrections, assessments, reporting and qualification.

External research references in these documents were not refreshed for this audit.
This review evaluates the repository against its own documented contracts and local
evidence, not against an assumed latest ranking of models or software releases.
