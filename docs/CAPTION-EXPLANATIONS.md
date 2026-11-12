# Explain a saved draft

Inspect why a model draft contains or omits a tag before changing caption rules or
saving a correction. Explanations use the exact saved scores, label index and rules.
They do not run inference, download a model, open source images or change anything.

For a prepared directory:

```powershell
dataset caption-explain --workspace 'D:\datasets\collection' --image 'portraits/001.png'
dataset caption-explain --collection artwork --image 'portraits/001.png' --tag solo
```

Use the exact relative image path, including its case and subdirectories. A named
collection must already be registered. `--job` selects an exact historical job;
otherwise the command uses the workspace's current completed tagging stage. A job
prepared with existing captions alone has no model scores to explain.

To inspect a particular tagging or recaption run without a workspace or config:

```powershell
dataset caption-explain --run 'D:\datasets\runs\saved-tagging-run' --image 'portraits/001.png' --tag solo --tag 1girl --json
```

Repeat `--tag` for exact raw label names, such as `long_hair`, rather than display
phrases such as `long hair`. This also finds low-scoring tags that do not appear in
the default view. Without `--tag`, the view includes observed tags, near-threshold
tags, configured drops/overrides, subset-rule inputs and ratings. Tag rows use
stable label-index order; `--limit 50 --offset 50` reads the next page. The maximum
page size is 200. Unknown image paths or tag names fail explicitly.

In the live QA reviewer, open **Compare caption choices**, then **Explain draft
rules**. Search for an exact raw tag or page through relevant tags. These controls
preserve unsaved captions, annotations and assessment notes. The panel describes
the pinned draft even when an override or sidecar supplies the effective caption.
Static reports still show their saved content; live inspection requires `review-ui`.

## What the explanation means

- **Observed:** the score is strictly greater than its threshold. A score equal to
  the threshold is omitted. Threshold precedence is a per-tag override, then the
  character or general threshold, with the recorded model default used when the
  general threshold is unset.
- **Selected:** an observed tag also passes the drop list and character-tag policy.
  Dropped or disabled character tags remain observed evidence for subset rules and
  composition findings. Selection does not establish visual correctness.
- **Near threshold:** the absolute score difference is within the recorded margin,
  including its boundary. A zero margin disables this flag. Scores are model
  outputs, not calibrated probabilities of correctness.
- **Ratings:** shown separately as scores; they do not become caption phrases or
  subset predicates.
- **Subset rules:** every `all`, `any` and `none` predicate reports its observed
  inputs and whether it passed. Expected tags apply only to a matching rule.
  Multiple matches remain a conflict; they do not silently choose the first rule.
- **Phrase order:** literal trigger, selected tags sorted by score/index, then
  literal forced phrases. Underscores become spaces except in preserved kaomoji.
  Case-insensitive duplicates keep the first phrase; the trace names that earlier
  position. Literal additions never become model observations.

## Integrity and unavailable evidence

The reader checks saved metadata, manifest, labels and the selected score vector,
then replays the recorded rules and compares all retained caption-analysis fields.
It rechecks those artifacts before returning. Current config changes have no effect
on this historical explanation. Source paths with identical image bytes remain
separate occurrences even when they share a score vector.

The hashed manifest is the saved draft authority. Editing a loose generated `.txt`
file does not change this explanation or save a durable caption correction.

A missing full scored run, an unscored image, incomplete historical evidence or an
unsupported caption-rule version is explicitly unavailable. Corrupted or mismatched
evidence fails; it is never replaced with guessed scores or current defaults.
Exports retain draft text and provenance but do not bundle every original score
vector. The original scored run is required for the full explanation, even when
the exported image and caption remain portable.

Tag rows are paged. The complete explanation payload also has a 2 MiB limit before
presentation formatting and selection/report metadata. Exceptionally large
phrase/subset traces return an explicit unavailable result instead of an incomplete
explanation. Saved-score inspection requires NumPy, but no ONNX Runtime,
model bundle, source images or network connection. Base installations without NumPy
show an actionable dependency result.

This feature does not alter thresholds, captions, reviews, exports or acceptance.
Use [caption comparison](CAPTION-COMPARISON.md) to inspect effective precedence,
[tagging and recaptioning](TAGGING.md) for a new rule run, and
[review corrections](REVIEW.md) for a durable override. Human acceptance remains
separately attributed.
