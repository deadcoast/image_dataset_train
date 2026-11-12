# Recover an empty or unavailable review view

The reviewer distinguishes an empty saved report from a filter with no matches,
an empty pair queue, and unavailable image or saved-review reads. Its recovery
actions keep the current report and recorded source identities.

## Find images or pairs

If image filters hide every image, clear the filters to return to the report's
image queue. This includes search, pilot selection and group filters. A report
that contains no images instead points to its snapshot summary; clearing filters
cannot add missing membership to a historical report.

An empty unreviewed-pair queue means there are no unresolved pairs in the saved
pair index. It does not establish caption accuracy, image inclusion or dataset
acceptance. Use all pairs to inspect existing decisions. When there are no
indexed or saved pairs, inspect the snapshot report or use manual comparison
for two exact inventory paths. A failed pair read is shown as unavailable, rather
than as an empty or completed queue; retry after resolving the reported problem.

## Recover previews

A missing saved preview differs from a preview that failed to load. Retry loads
the same recorded preview; it does not regenerate one, search for another image
or change source bindings. Existing full-image access remains available where
the report provides it. Pair preview retry uses the same two selected images.

Preview retry preserves unsaved captions, labels, subsets, assessment notes and
pair decisions. It does not reload form values or save anything. If an original
source file is unavailable or changed, restore the expected file before retrying.
A retry cannot bypass the application's source-content checks.

## Reload saved form values

The correction and assessment reload controls remain reachable when their first
read fails. Restore the source or resolve the reported error, then reload the
affected form. Reopening the page is no longer required for this initial-read
failure. Other forms retain their unsaved values.

Reloading a form deliberately replaces its unsaved values with the current saved
record. A failed reload preserves existing edits and their save baseline. Preview
retry and unrelated recovery never perform this replacement. Reload and save do
not run concurrently for the same form; stale responses cannot replace a newer
image or form. Existing revision and reason checks still govern saving.

Read-only recovery does not publish snapshots, record judgments or establish
human acceptance. A changed historical report may still require reopening it;
source relocation is a separate operation.

See [review](REVIEW.md), [caption comparison](CAPTION-COMPARISON.md),
[publication](PUBLICATION.md) and [operational recovery](RECOVERY.md).
