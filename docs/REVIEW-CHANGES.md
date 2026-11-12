# See changes since a report

Compare saved review records with the exact state captured by a QA report before
publishing again. The original report, captions, exports and assessments stay intact.

## Inspect in the terminal

```powershell
dataset review-history changes --collection artwork
dataset review-history changes --workspace 'D:\datasets\collection' --job <current-job-id> --json
dataset review-history changes --collection artwork --report 'data/runs/<qa-id>' --limit 20 --offset 0
dataset review-history changes --run 'data/runs/<similarity-id>' --config config.toml --report 'data/runs/<qa-id>'
```

Without `--report`, collection/workspace selection uses its recorded, completed QA
checkpoint. It does not search for a newer report. An explicit similarity run also
requires an explicit report. The report must have compatible, intact provenance.

The result distinguishes three conditions:

- **Unchanged:** captured and current review state have the same history and records.
- **History only:** new events exist, but the records are back to their captured
  values—for example, a correction was restored to its original state.
- **Changed:** saved image or pair records differ from the captured records.

Each page shows exact affected identities and field changes, including removed
records. Counts describe all net changes; pagination limits the displayed records.
Changes outside the report's image membership remain visible and are labeled.
Compatibility with the selected inventory does not establish that source files
are currently available or unchanged.

Use `--kind images` or `--kind pairs` to narrow the page. The printed next-page
command includes `--expected-inspection-sha256`, which binds the report, selection
and inspected review evidence. If those change, restart at the first page rather
than combining pages from different saved states.

These are **review-record differences**, not predicted changes to exported captions,
splits or dataset membership. A reason or annotation change can advance history
without changing a training caption. Republish and inspect the resulting artifacts
to assess their actual effect.

For the text candidates behind an individual correction, use the separate
[caption comparison](CAPTION-COMPARISON.md) inside the image editor.

## Inspect in the reviewer

Open the report with `dataset review-ui` and use the existing **Publish** pane.
Its changes section shows the report revision, inspected current revision and
affected image/pair records. Refresh after another process edits reviews; use the
page controls to inspect further results. Saving corrections in the reviewer also
refreshes the comparison without replacing unsaved publication settings.

Use the existing publication controls when ready. Inspection never publishes,
saves corrections or transfers a report's acceptance. When records differ, the
terminal prints a continuation: compatible preparation builds can refresh reviews;
different saved builds require a new job using the saved settings.

## Evidence and unavailable states

Inspection checks the report's declared input, frozen group/export review evidence
and both review histories. The captured history must be an exact prefix of current
history. Revision numbers alone cannot establish continuity. Missing, altered,
truncated or divergent evidence produces an explicit failure instead of a misleading
empty change list.

The comparison reads metadata only and works with source images offline when the
retained evidence is intact. It creates no directories, locks, reports or repair
logs. The existing whole-document history storage and replay cost are unchanged.

See [review history](REVIEW-HISTORY.md), [bulk review](BULK-REVIEW.md),
[publication](PUBLICATION.md) and [preparation](PREPARATION.md).
