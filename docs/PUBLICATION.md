# Durable reviewer publication

The reviewer's **Publish** tab saves each publication under the configured review
directory. Reopen the same QA report with the same configuration after a server or
machine restart: the reviewer reloads its publication status, verifies saved
outputs, and restores the **Open the new snapshot in reviewer** link. The existing
Publish buttons also retry failed or interrupted work. No extra recovery command
is required.

The Publish form restores the previous attempt's caption and export settings on
initial load after reopening or reloading the page. Polling and refresh preserve
unsaved form edits. This lets a failed attempt with custom settings resume without
silently reverting to configuration defaults.

Before saving a caption correction, use [caption comparison](CAPTION-COMPARISON.md)
in the image editor to inspect the override, sidecar and pinned draft. Its source
caption preview does not certify publication readiness or predict adjustments
for derived export images.

A retry reuses the verified consecutive stages from the previous attempt only
when the original QA, similarity/inventory and caption artifacts, source image
identities and bytes, sidecars, review revision and state, export settings, pilot
settings, destinations, and application implementation still match. An identical
request for an already completed job returns its existing outputs. Changed
settings or a new review revision create a new attempt. Stale review requests and
changed source bytes require refreshing review status or scanning the source
again, respectively.

Publication preserves the existing workflow:

- **Groups + QA** captures incomplete reviews for further inspection. A valid QA
  report can describe missing captions or other review findings; these findings
  do not imply export readiness.
- **Groups + verified export** enforces the existing export review requirements,
  independently verifies the copied dataset, and builds QA from that export.
- Captured decisions remain fixed even when later reviews are saved. Publication
  does not create human acceptance, carry pilot acceptance to a new snapshot, or
  run the trainer import.

## Storage and recovery contract

The Publish pane also shows [saved changes since this report](REVIEW-CHANGES.md).
It identifies affected image/pair records and distinguishes net changes from
history-only advancement. Refreshing that view does not publish or modify evidence.

`paths.reviews/publications/<report-identity>/job.json` contains a versioned report
binding and ordered attempts. Each attempt records its request fingerprint,
settings, review revision and state hash, input artifact hashes, timestamps,
stage outputs and complete output-file hashes, error state, and reused stages.
Successful earlier snapshots and failed attempts remain available. Published
artifacts and the original QA are never rewritten by retry.

Each attempt has separate stage directories under:

```text
paths.runs/reviewer-publications/<report-identity>/<attempt-id>/groups/
paths.runs/reviewer-publications/<report-identity>/<attempt-id>/qa/
paths.exports/reviewer-publications/<report-identity>/<attempt-id>/export/
```

These directories contain the ordinary immutable group, QA, and export runs.
Their existing CLI readers and verifiers continue to work. Stage output metadata
must match the expected source, input snapshots, selected identities, captured
review state, and relevant settings before recovery can adopt it. Published
stages with `completed_with_errors` status are not adopted.

If a process stops after a stage publishes but before its checkpoint is saved,
recovery examines only that attempt's stage directory. One complete, valid output
can be checkpointed; incomplete `.pending-*` directories are left untouched.
Multiple candidates, changed hashes, incorrect bindings, or incomplete status
prevent adoption. Retry starts that stage in a new attempt directory, preserving
the questionable output for inspection. Recovery does not search unrelated runs
or infer success from an output directory's name alone.

A source-scoped operating-system file lock under the configured review directory
rejects concurrent publication from different reviewer sessions or processes
using that review store. The lock is released by process termination. Review
edits remain separately revision-checked. Ctrl+C waits for an active publication;
an abrupt termination is handled on reopening the reviewer. A malformed job file
is reported rather than discarded: preserve it and its output directories before
manual recovery.

The local API keeps `start`, `read`, and `wait`, and the existing `status`,
`message`, and `outputs` response fields. Responses additionally expose
`job_path`, `attempt_id`, `reused_stages`, `error`, captured `settings`, and a compact attempt history.
The job file contains the complete provenance; the browser response omits the
potentially large per-file hash maps.

Tests cover real process termination between publication and checkpoint at all
three stages, restart/retry, idempotent completed submission, changed inputs and
settings, damaged or incorrectly bound outputs, concurrent processes, polling,
and preservation of input and prior output artifacts. These are developer
recovery checks, not human usability or representative dataset acceptance.
