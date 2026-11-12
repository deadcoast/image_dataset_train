# Inspect and restore review history

Recover a mistaken caption, annotation, inclusion decision or pair relationship
by restoring an earlier state. Restoration appends a new review revision. Original
images, sidecars, prior history, published datasets and pilot assessments stay intact.

## Find a correction

```powershell
dataset review-history list --collection artwork
dataset review-history list --collection artwork --image 'art.png' --limit 20 --offset 0
dataset review-history show --collection artwork --revision 7
dataset review-history list --workspace 'D:\datasets\collection' --json
dataset review-history list --run 'data/runs/<similarity-id>' --config config.toml
```

Events show exact identity, before/after records, changed fields and actor information.
`--image` matches an exact relative path; `--pair` requires a full pair ID. Pagination
bounds returned events; the existing JSON store is still loaded as a whole document.

Named collections and workspaces use their current preparation job and saved
configuration. Add `--job` with the printed job ID to reject a changed selection.
Explicit-run workflows instead supply a similarity run and configuration. These
selectors never switch jobs or search unrelated directories.

Lists and previews work with source images offline when retained artifacts and
review metadata remain valid. They create no directories, locks, logs or reports.
Historical decisions that no longer match the selected image bytes or pair policy
remain inspectable but cannot be restored onto changed content. Legacy actors stay
unknown. Restoring a record retains its original decision provenance; the new event
separately records the restoring actor and reason.

## Preview and apply

```powershell
dataset review-history restore --collection artwork --revision 7
dataset review-history restore --collection artwork --revision 7 --before
```

Restore defaults to the selected event's **after** state. `--before` restores the
state immediately before it, including removing a record created by a first edit.
Absence is distinct from explicitly reviewed empty labels or an unassigned subset.
Use the same mechanism to reverse a previous restore.

[Bulk review](BULK-REVIEW.md) saves linked per-image events in one atomic batch.
Restoring one member changes only that image; it does not reverse the entire batch.

The preview compares the entire target record with its proposed replacement. It
prints the current revision, plan checksum and exact apply command. Restoring a
caption revision can also restore that record's earlier inclusion, labels and subset.
Other records are unchanged. Use ordinary `dataset review --caption` to change only
a caption while keeping the rest of the current record.

Copy the guards from the preview and supply a reason and actor. The revision numbers
below are examples:

```powershell
dataset review-history restore --collection artwork --job <current-job-id> --revision 7 --apply --expected-revision 12 --expected-plan-sha256 <preview-sha256> --reason 'Restore the inspected correction' --reviewer 'Your name' --reviewer-kind human
```

Assistant actions use `--reviewer-kind assistant`. Neither kind grants acceptance.
Apply rechecks the preview, affected source bytes and related/distinct graph
constraints under the review lock, then publishes one atomic state update. Newer
reviews or changed selection/context invalidate the preview. Missing sources,
malformed history, links and conflicts fail without silently repairing evidence.
An unchanged target does not append a duplicate revision.

With `--json`, an applied response's `revision` identifies the saved revision;
`current_revision` and `current_record` retain the inspected pre-apply state.
Obtain a fresh preview before another restore. Use the top-level `plan_sha256`
as the CLI apply guard. The checksum stored in the restoration event covers the
core history/context plan and is not interchangeable with the CLI selection guard.

## Publish the restored corrections

Use [changes since a report](REVIEW-CHANGES.md) to see which image/pair records
currently differ from its captured state. Restoring an original value may leave
new history with no net record changes.

Restoration does not rewrite existing reports or exports. Follow the printed
continuation: compatible preparation jobs use guarded `resume --refresh-reviews`;
different saved builds require a new job with the saved settings. Explicit-run
workflows publish new groups and exports through their existing commands.

Human assessments remain bound to their original reports. Inspect a new report
separately; restoration never transfers or changes acceptance. See
[preparation](PREPARATION.md), [review storage](REVIEW.md) and
[collection navigation](COLLECTIONS.md).
