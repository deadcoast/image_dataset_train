# Critical-label evaluation

This is M3 source support for NF03, CF04 and CF06, with NF02 comparison and
NF05 probability sampling and frozen-membership support. It uses saved WD scores
without inference.
Evaluation and model comparison use the [checked saved-rule contract](MODEL-RULE-CONTRACT.md)
to interpret recorded thresholds without current defaults or local model access.
Collection representativeness, caption suitability and human acceptance remain
separate requirements in [PLAN](PLAN.md#work-order-and-completion-boundaries).

## Freeze a comparison population

Use a published QA report based on a group snapshot and a matching tagging or
recaption run. Choose the raw WD vocabulary explicitly (`blue_hair`, for example,
rather than its caption rendering `blue hair`). Ratings are not binary tag labels.

```powershell
dataset label-pilot --run <group-qa-run> --reference <scored-run> `
  --label blue_hair --label red_eyes --reason "Selection rationale and known limitations" `
  --seed 20261011 --held-out-fraction 0.33 --config config.toml --json
```

The result is a new workspace under the configured reviews directory. Its
`selection.json` freezes the QA pilot's paths, content hashes, known group IDs,
vocabulary, selection reason and input checksums. All selected source occurrences
must have matching reference scores. Exact-byte aliases share one judgment and one
metric observation. The creator verifies QA entries against the original group
snapshot and verifies the selected score vectors before publishing the workspace.

Groups are sorted by seeded hash, then the requested fraction of groups is assigned
to `held_out`; the rest go to `calibration`. The rounded fraction is clamped to
retain both sets when at least two groups exist. One group supplies calibration
only. This is a fraction of groups, so the image ratio may differ. Selection and
partitions cannot be edited through the judgment interface. Changed membership,
vocabulary or grouping requires a new workspace.

The existing QA selector favors coverage of findings and categories and can depend
on a model's output. Freezing it makes comparison reproducible; it does not make
the sample representative. Record that limitation in the reason. Known groups
remain disjoint, but unresolved relationships may still conceal related examples
across the sets. The workspace retains group-review status and unresolved counts.

## Draw a probability sample of original content

Use `--probability-sample-size` to select from every original-image identity in a
verified group QA report, independently of the QA report's displayed pilot,
caption findings, model scores or training inclusion decisions:

```powershell
dataset label-pilot --run <full-source-group-qa> --reference <scored-run> `
  --label blue_hair --label red_eyes --reason "Predeclared source-content sample" `
  --probability-sample-size 64 --selection-seed 20261110 `
  --seed 20261011 --held-out-fraction 0.33 --partition-groups <complete-policy-groups> `
  --config config.toml --json
```

The sample size must be between one and the full unique-content population size;
it is never silently reduced. An explicit selection seed is required. `--image`
cannot be combined with probability sampling. The existing `--seed` continues to
control evaluation partitions and is separate from the selection seed.

The versioned algorithm ranks each unique original content SHA256 by
`SHA256("representative-source-content-v1\0{selection_seed}\0{sha256}")`, using
UTF-8 bytes, then sorts by `(rank, sha256)` and takes the first requested count.
Each content hash has the same sampling-design inclusion probability `n/N`.
`selection.json` stores the complete canonical population frame, its SHA256,
algorithm, seed, rational probability, draw order and every selected source alias.
Aliases receive one shared label judgment; their distinct captions/provenance are
still separate occurrences. A fixed draw is reproducible, not a guarantee that
every rare content type appears. Do not replace difficult, excluded or previously
seen selections after inspecting them. Record targeted additions separately.

The optional `--partition-groups` snapshot must match the same source and every
path/content identity in the complete population. Its training inclusion/exclusion
decisions do not filter the sample: even excluded-only originals remain available
for label review. Prepared groups can conservatively constrain partitions without
claiming their semantic relationships are confirmed. The full partition mapping,
origin checksum and membership checksum are frozen separately from the sampling
design. Reads replay the hash draw, alias identities, complete group identities
and partition assignment from immutable workspace bytes. They do not reopen the
original QA, grouping artifacts, scores or images merely to read that evidence.
Group-review completion and unresolved-pair counts describe the chosen partition
snapshot, which may differ from the original QA's historical group context.

Reference scores are checked only after membership is chosen. Existing saved
score comparisons still require every selected alias to have matching evidence.
Prior review or model exposure is not exhaustively known: retain an external,
attributed audit overlay identifying known overlaps and its completeness limits.
An overlap with an earlier review is not newly blind, and a non-overlap does not
prove that an image was never exposed. Current fitting does not remove previously
exposed observations automatically. Report that scope and keep fitted cutoffs
diagnostic unless separately adequate validation supports deliberate adoption.

Original-image labels and training-caption judgments answer different questions.
Label the original content first, with assistant observations marked `assistant`.
Then assess an exported caption against its actual derivative image, binding both
hashes and retaining original-caption/transform evidence. Excluded-only originals
have no training caption to assess; they are not silently replaced or counted as
missing-caption errors.

## Refresh corrected groups without changing the pilot

If visual review discovers related images that the frozen groups missed, save the
relations with `dataset review --link` and publish a new `dataset groups` snapshot.
Use the existing label workspace to retain exactly the selected population:

```powershell
dataset label-review --workspace <parent-workspace> --json
dataset label-refresh --workspace <parent-workspace> --groups <new-group-snapshot> `
  --reason "Newly reviewed related-image connections" --expected-revision <revision> `
  --config config.toml --json
```

The command creates a new workspace. Every selected source path/content hash must
still exist in the new snapshot. For non-probability workspaces, selected members
must also remain unexcluded. Violations reject the operation rather than silently
reducing the sample. Vocabulary,
aliases and selection rationale remain fixed. Group IDs come from the complete
snapshot, including transitive connections through images outside the pilot. The
original seed and held-out fraction recompute partitions over those corrected
groups; there is no fit-driven selection or threshold adoption.

For a probability workspace, training exclusions are intentionally permitted.
Refresh must preserve the entire original population frame, including unselected
identities, not just the reviewed sample. It retains the sampling design,
probabilities and draw exactly, updates the separately frozen complete grouping,
and recomputes evaluation partitions without redrawing. Missing or changed
population identities reject the refresh. Original non-probability workspaces
retain their existing rule that selected members cannot become excluded.

The new workspace carries the captured parent revision, judgments and history
forward unchanged, including each value, uncertainty, reviewer kind, name, note
and timestamp. Only the judgment state's selection checksum is rebound. New
corrections append to that inherited history. Immutable `parent-run.json`,
`parent-selection.json` and `parent-judgments.json` snapshots record the exact
parent metadata/selection and captured judgment state, with hashes and explicit
carry-forward provenance. They are not presented as a new review. A stale expected
revision rejects the refresh.

The original QA remains the historical selection and image-viewing context; its
group display is not rewritten. The refreshed selection's `input_run` identifies
the corrected group snapshot. Input lineage retains the old QA, group/reference
runs and ancestor workspaces so future refreshes and evaluations cannot publish
inside any of those artifacts. Existing workspaces, results and source files remain
unchanged. Refreshing also works from a previously refreshed workspace.

These partitions reuse reviewed data. Correcting known leakage does not create a
new independent validation population or establish representative sampling.
Assistant judgments retain their attribution and still require
`tag-evaluate --include-assistant` to enter diagnostic metrics.

## Review images in the browser

```powershell
dataset label-ui --workspace <workspace> --config config.toml
```

The local reviewer starts with the image and frozen label checklist. Save all of
an image's present/absent/uncertain judgments together with a reviewer name, explicit
human or assistant kind and notes. Atomic saves and expected revisions prevent
partial image saves or silently overwriting concurrent changes. Unsaved form edits
remain recoverable after a rejected save; reload explicitly to replace them.

Save shortcuts require the current matching image to be ready, just like the
visible buttons. Retry image preserves drafts after source restoration; Show all
images recovers an empty filter. Persisted label history, clearing actors and
comparison exposure are validated before use or mutation. See
[judgment integrity and recovery](REVIEW-INTEGRITY.md) for invalid records and
legacy attribution behavior.

Add repeated `--run <scored-run>` arguments to make saved-model comparison available.
Model predictions remain separate from judgments; opening comparison records
exposure in the workspace history. Save image-first judgments before consulting
predictions when the protocol requires it. Neither an assistant save nor viewing
model scores implies human acceptance. See [preparation review](PREPARATION.md)
for the surrounding publication and recovery workflow.

## Record actual presence

```powershell
dataset label-review --workspace <workspace> --json
dataset label-review --workspace <workspace> --image <exact-source-path-or-sha256> `
  --label blue_hair --value present --reviewer "Reviewer name" --reviewer-kind human `
  --notes "Observed evidence" --expected-revision 0
```

`label-review --json` exposes frozen image identities, partitions, current truth,
history and revision. View the images in the originating QA report. Every change
requires the revision that was read; a concurrent update rejects a stale save.
Each save retains the reviewer, reviewer kind, note and time. Use `assistant` for
assistant observations. The tool records this attribution; it does not authenticate
reviewers or independently establish who reviewed an image.

Values are `present`, `absent` and `uncertain`. `unreviewed` clears a judgment while
retaining its history. Missing judgments are never inferred to mean absent.
Different aliases of identical bytes update the same judgment. Truth is independent
of caption checks, include/exclude decisions, manual overrides and model predictions.
Existing report-specific `correct`/`missing`/`spurious` checks are not automatically
converted into independent truth.

## Compare saved scores and fit thresholds

```powershell
dataset tag-evaluate --workspace <workspace> `
  --run <swin-run> --run <eva-run> --run <vit-run> --config config.toml --json
```

Every scored run must cover the complete frozen path/hash population and vocabulary.
Missing scores, mismatched source identities, changed artifacts or unsupported
labels fail the comparison; models cannot silently use different image subsets.
Recorded model metadata is retained; label indexes, score-index hashes,
individual vector hashes and score checksums are validated. Evaluation does not
reload the model weights or authenticate the original run's metadata. It can run
with the source images offline.

By default only judgments attributed to humans enter metrics. Use
`--include-assistant` explicitly for diagnostics. Missing, uncertain and excluded
assistant judgments are counted separately. Each label reports TP/FP/FN/TN,
precision, recall and F1, retaining undefined rates as null. These denominators
count unique image bytes. Empty evidence produces coverage gaps, not an accuracy
claim. Reviewer attribution and sample selection still determine the strength of
the result.

Prediction uses the production **score > cutoff** rule. Baselines use each saved
run's general, character and per-tag thresholds. Evaluation concerns observed
tags: caption exclusions, character inclusion and forced phrases do not change
the predicted presence of a raw label.

The fit uses calibration judgments only and requires both present and absent
examples for a label. Candidate cutoffs are 0 through 1 in steps of 0.01, plus
the exact baseline. The highest calibration F1 wins; ties prefer the baseline,
then the nearest cutoff to it, then the higher cutoff. Held-out judgments are used
only to report baseline/fitted results. Sample counts, missing classes and errors
remain visible. Repeatedly selecting models or rules from these held-out results
would require a fresh independent validation population.

Each invocation publishes a new immutable result under configured runs, including
the exact selection and judgment snapshot, revision, model identities, scores and
metrics. For a refreshed workspace it also copies the checked immediate-parent
metadata, selection and judgment snapshots; `result.json` maps their archived
filenames under `workspace_provenance`. Earlier ancestry remains recorded by paths
and digests rather than recursively copying whole workspaces. The captured parent
judgment state includes its complete inherited history. Proposed cutoffs never
modify configuration, captions, source files or
existing results. Reusable approved-profile adoption (NF04) remains separate.

## Workflow handoff

Source implementation and fixture checks establish the evaluation mechanism.
The authorized 0.7.0 representative assistant labels, composition/caption review
and bounded measurements are recorded in
[COMPLETED](COMPLETED.md#representative-assistant-review-070). Human dataset acceptance
remains in [TODO](../TODO.md#m4--representative-caption-and-subset-acceptance).
Record delivered evidence in [COMPLETED](COMPLETED.md), reconcile
[SHELVED](SHELVED.md#m3), and continue the existing PLAN before starting a new review cycle.
