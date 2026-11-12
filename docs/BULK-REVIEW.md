# Review an explicit batch of images

Apply the same reviewed labels, subset or inclusion decision to selected images.
The command previews every selected path and content hash, the current record,
the proposed changes and the changed/unchanged counts. It never selects images
from a filter or automatically accepts model predictions.

## Preview the selection

```powershell
dataset review-batch --collection artwork --image 'first.png' --image 'second.png' --add-label portrait --reason 'Reviewed these two portraits'
dataset review-batch --workspace 'D:\datasets\collection' --image 'first.png' --subset portraits --reason 'Reviewed subset assignment' --json
dataset review-batch --run 'data/runs/<similarity-id>' --config config.toml --image 'first.png' --decision exclude --reason 'Reviewed exclusion'
```

Use exact relative paths from the selected inventory. A batch accepts 1–1,000
distinct image paths; missing, duplicate and ineligible targets reject the entire
operation. Repeated `--image` and `--images-file` are alternatives. A selection file
is a UTF-8 JSON array of exact paths, up to 4 MiB:

```json
["first.png", "folder/second.png"]
```

```powershell
dataset review-batch --collection artwork --images-file selection.json --add-label portrait --reason 'Reviewed the explicit selection'
```

The preview includes all selected members, even ones that would not change.
Selection files remain bound to their bytes during apply. They are not live
queries, and changed file contents require a new preview. Collection/workspace
selection uses its current job and saved settings; use `--job` to pin that job.
Explicit runs require `--config` and do not use `--job`.

## Choose the changes

- `--add-label` and `--remove-label` accept repeated explicit names.
- `--clear-labels` records a reviewed empty label set; it can be combined with
  additions to replace the set. A label cannot be both added and removed.
- `--subset` sets a reviewed subset; `--clear-subset` records it as unassigned.
- `--decision` chooses `include`, `exclude` or `unreviewed`.

Names are normalized with the same rules as individual annotation. Omitted fields
keep their current values. Caption overrides and unrelated annotations survive.
An absent annotation is distinct from a reviewed empty value. The reason describes
the requested change and is part of the preview identity.

## Apply the inspected preview

Copy the exact apply command printed by the preview and supply your actor identity.
It retains the selection, operations, reason, current revision and plan checksum:

```powershell
dataset review-batch --collection artwork --job <current-job-id> --images-file selection.json --add-label portrait --reason 'Reviewed the explicit selection' --apply --expected-revision 12 --expected-plan-sha256 <preview-sha256> --reviewer 'Your name' --reviewer-kind human
```

Assistant actions use `--reviewer-kind assistant`. Neither actor kind grants dataset
acceptance. A batch with no actual changes saves no history. Otherwise, all changed
records are saved together under the existing review lock, with one batch identity
and contiguous per-image revisions. There is no partially successful batch.

Apply rechecks the preview, saved job/collection selection, every selected source
(including unchanged members), and group consistency before writing. Source changes,
missing files, linked paths, concurrent edits or invalid history reject the operation.
Preview is read-only and can work with source images offline while retained metadata
is valid. Apply requires the selected source files to be available.

With `--json`, `revision` is the committed revision after apply; `current_revision`
and member records describe the inspected pre-apply preview. Obtain a fresh preview
before another batch. Use the top-level `plan_sha256` for CLI apply; the batch's
stored core-plan checksum does not include the CLI selection guard.

## Continue review and publication

Inspect [changes since a report](REVIEW-CHANGES.md) to see net image/pair changes
before publishing. The report's original contents and assessment remain intact.

Use [review history](REVIEW-HISTORY.md) to inspect the attributed batch members or
restore an individual image's earlier state. An individual restoration does not
undo the other members. Ordinary image corrections continue to work after a batch.

Follow the printed publication command: matching builds can refresh preparation
reviews; different saved builds require a new job. Existing exports, source images,
sidecars, label-evaluation workspaces and report-bound assessments are unchanged.
Human acceptance must be recorded separately against the report actually reviewed.

See [individual review](REVIEW.md), [preparation](PREPARATION.md), and
[collection selection](COLLECTIONS.md).
