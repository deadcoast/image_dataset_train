# Dataset preparation plan

Design reviewed: 2026-10-11. Implementation status refreshed: 2026-11-09.
Intake, local tagging, Trainime directory actions, similarity proposals, durable
review decisions, caption overrides, and group snapshots are implemented.
Group-aware splitting, verified image/caption exports, and Kohya configuration
generation are implemented. Pinned CPU trainer imports pass on generated fixtures;
representative collection acceptance remains pending. Model training belongs to
the downstream trainer, as defined in Purpose and scope below.
Pilot QA reports and browser/CLI navigation now connect captions, reviewed
annotations, and semantic split coverage. The local reviewer saves image and pair
corrections and report-bound pilot assessments. It publishes group snapshots,
verified exports, and refreshed QA through the same core functions as the CLI.
Its Training import view and `dataset trainer-status` expose export-bound receipts,
the current pinned import result, and separate pilot qualification status.

Installation and operational recovery are implemented in 0.4.0:
[install.cmd](../install.cmd) owns setup, and [the recovery coINSTALLATION.mdATION.md)
defines logs, diagnosis, automatic repairs, and actionable fixes for remaining failures.

## Purpose and scope

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
shares this evaluation and links errors back to image comparison. Representative
pilot calibration remains required; unreviewed pairs are not presumed distinct.
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
frozen evidence; unavailable observations remain explicit. Measured collection
accuracy and tokenizer checks remain future work.

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
Representative anime pair evaluation remains pending. M2-M6 require a
representative local collection before quality/performance claims. The code should
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
