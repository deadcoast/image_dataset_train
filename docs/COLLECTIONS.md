# Find collections and recorded runs

Use the collection registry to return to preparation workspaces without remembering
their generated run paths. It is a local navigation index. The portable SQLite
[dataset catalog](DATASET-CATALOG.md) contains training-image metadata and serves a
different purpose.

```powershell
dataset collections
dataset collections --json
dataset collections --source 'D:\images\collection'
```

Listing is read-only and does not discover unrelated image directories. A normal
`dataset prepare` command remembers its workspace on a best-effort basis; preview
does not register anything. An older workspace can be registered and given a name:

```powershell
dataset collections add 'D:\datasets\collection' --name artwork
dataset collections show artwork
```

Registration requires an existing preparation workspace, not merely an image
directory. The record binds its absolute workspace and source paths. Names are
unique without regard to case; the full collection ID remains an exact selector.
Registering the same workspace again without `--name` keeps its existing name.
The registry lives in application data under `TRAINIME_HOME` or the normal app-data
directory. It does not modify source images, captions, preparation jobs or exports.

```powershell
dataset collections remove artwork
```

Remove unregisters the navigation entry only. It does not delete the workspace,
source directory, review history or exported datasets. Registering the workspace
again makes its retained records available.

## Inspect jobs and run records

```powershell
dataset collections show artwork --json
dataset runs --collection artwork
dataset runs --collection artwork --stage qa --status completed
dataset runs --collection artwork --since 2026-11-01 --until 2026-11-09 --json
```

`show` reports the current job ID, current review revision, retained jobs, run records
and catalog errors. `runs` filters the same collection's records. Stage and status
filters match their saved values exactly. Date bounds are inclusive UTC calendar
dates in `YYYY-MM-DD` form; records without a usable date are excluded by date
filters and counted separately.

Each record includes its full record ID, artifact path, `run.json` SHA256, source,
stage, saved status, owning job when known, and configuration locator. The record ID
binds the path and metadata digest. A basename or shortened ID is not an exact
selection. Changed metadata requires a new listing and selection.

```powershell
dataset runs --collection artwork --run <full-record-id> --json
```

These are **metadata-only** listings. A recorded `running` state does not prove a
process is alive, and `completed` does not establish full artifact integrity or
human dataset acceptance. Invalid or unavailable records appear as catalog errors.
Listing does not instantiate the reviewer, resume a job, repair artifacts or rewrite
publication checkpoints. It can inspect retained metadata while source images are
offline.

Records show relevant existing commands as literal arguments and quoted shell
examples. An export suggests `verify-export`; a QA record suggests the checked
review action below. These commands are displayed, not executed by listing.

## Open the selected QA report

Copy the QA record ID and checksum from the same listing:

```powershell
dataset collections review artwork --run <full-record-id> `
  --expected-sha256 <run-json-sha256>
```

The action accepts a QA record only. It checks the current record identity, QA
artifacts and matching source/configuration before starting the existing loopback
reviewer. The expected checksum rejects a stale selection. Configuration from an
owning preparation job is checked against that job's saved digest; an unbound or
incompatible configuration cannot silently redirect review writes.

Add `--no-open` to print the local URL without opening a browser. `--port` selects a
local port; its default `0` lets the operating system choose one. Ctrl+C stops the
server. This action uses the existing reviewer and its preservation, revision and
publication contracts; it does not add another browser interface or change the
Trainime Home menu.

Opening a report does not grant acceptance. Image and conclusion judgments retain
their explicit human or assistant attribution. New edits and publications still
perform the existing source, revision and artifact checks.

## Return to preparation or recovery

```powershell
dataset status --collection artwork
dataset status --collection artwork --job <exact-job-id> --verify

dataset status --collection artwork --job <exact-job-id> --verify-cache
dataset resume --collection artwork --job <current-job-id>
```

Historical status reads the requested job without changing the current-job binding.
For resume, `--job` is an expected-current-job guard; it does not switch the workspace
back to an older job. If the current job changed, inspect it and use the printed
continuation command. Historical inspection does not resume work.

For correction recovery, `dataset review-history list --collection artwork` opens
the current collection's saved image/pair changes. Select a revision to inspect or
preview restoring it; apply uses the printed job and preview guards. See
[review history](REVIEW-HISTORY.md) for exact replacement, source checks and the
separate publication step.

Use [bulk review](BULK-REVIEW.md) to preview and apply label/subset/inclusion changes
to an explicit set of images in the selected collection. The saved job and every
member are bound to the preview; publication and human acceptance remain separate.

`dataset review-history changes --collection artwork` compares current saved
reviews with that job's checked QA checkpoint. Use an explicit `--report` to inspect
a compatible historical report. See [snapshot changes](REVIEW-CHANGES.md).

For interrupted tagging, `--verify-cache` verifies expected score entries against
the locally loaded model and actual current ONNX providers. It reports source
availability separately and performs no inference or repair. Model initialization
can use substantial memory; ordinary status remains lightweight. See
[cache readiness](PREPARATION.md#check-cached-inference-progress) for the evidence
and recovery boundaries.

Use [preparation](PREPARATION.md), [recovery](RECOVERY.md) and
[durable reviewer publication](PUBLICATION.md) for the existing retry and correction
paths. Registering or listing a collection makes no new claim of source validation,
model quality or dataset acceptance.
