# Directory preparation

Design authority: the user-directed 2026-11-09 product phase in [PLAN](PLAN.md).
The directory workflow is implemented in 0.6.0; completion evidence belongs in
[COMPLETED](COMPLETED.md), with unfinished scope in [TODO](../TODO.md).

## Product outcome

One local directory command produces a traceable image/caption dataset, portable
metadata, QA and continuation commands. It works outside this checkout.
Trainime's four-choice source-side caption workflow remains available;
`dataset prepare` owns the source-preserving preparation workflow.

Use the existing pinned local WD baseline, caption precedence, source validation,
whole-group splitting and Kohya export. Network access is limited to obtaining a
missing pinned model when needed; preview is read-only and offline. An offline
option explains which missing artifact prevents execution.

## Everyday commands

```powershell
dataset prepare 'D:\images\collection' --workspace 'D:\datasets\collection' --dryrun
dataset prepare 'D:\images\collection' --workspace 'D:\datasets\collection'
dataset status 'D:\datasets\collection' --verify
dataset resume 'D:\datasets\collection'
```

No configuration file is required. Omit `--workspace` to use a stable directory
under the application home, keyed by the absolute source path. The printed
workspace is the argument for status/resume. Source and workspace/cache trees
must be separate. `--config` optionally supplies advanced settings, shared model
and score caches, and an existing review store; the positional source takes
precedence and stage outputs stay in the job workspace.

CLI preparation also remembers its validated workspace in the local collection
registry, including retained interrupted jobs. `dataset collections` lists these
explicit registrations; `collections add <workspace> --name artwork` assigns a
convenient name. Then use `dataset status --collection artwork --verify` or
`dataset runs --collection artwork --stage qa`. Preview never registers anything,
and a registry-write failure is reported separately from the preparation result.
See [collection navigation and exact selection](COLLECTIONS.md).

The default profile uses pinned SwinV2, automatic provider selection, batch size 4,
1024-pixel target resolution and a 5% group-aware validation split. WD labels are
intended for anime-style images; technical preparation does not establish model
accuracy on a different domain. Existing source captions and saved overrides take
precedence over model drafts. `--captions existing --offline` skips inference and
downloads entirely, and excludes undecided images without usable captions.

Use `--model`, `--device`, `--batch-size`, `--resolution` or `--validation-ratio`
for explicit changes. `--max-distance` controls similarity candidate generation
(default 8), and `--sample-size` controls the displayed QA pilot (default 50).
Preview reports intake only; it does not predict generated captions or final
membership. `--json` provides machine-readable results and failures.

A completed result prints the immutable export and QA locations. The export
contains images and `.txt` captions under `train/` and `validation/`, split-local
`metadata.jsonl`, `catalog.sqlite`, manifests, trainer configuration and frozen
provenance. Transfer the complete export, not only the database file. See
[catalog queries and ImageFolder loading](DATASET-CATALOG.md).

To diagnose a generated caption without running the model again:

```powershell
dataset caption-explain --workspace 'D:\datasets\collection' --image 'portraits/001.png' --tag solo
```

This reads the completed tagging stage's saved scores and rules. It explains
thresholds, omissions, subset predicates and literal additions; source images can
be offline. See [saved draft explanations](CAPTION-EXPLANATIONS.md). Existing-caption
jobs have no generated draft to explain; saved corrections remain separate.

## Job and recovery contract

Persist the source identity, workspace, complete effective settings and stage
attempts before execution. Each completed checkpoint binds verified output
metadata and input identities. Resume reads that contract and verifies artifacts;
it must not guess that an existing directory means a completed stage. Isolate
attempt outputs so an interrupted checkpoint can identify its own published run
without adopting unrelated runs. Retain failed attempts, logs and completed work.

`collection.json` identifies the current job. Each `jobs/<id>/job.json` retains
settings, option/configuration hashes, application version and package payload
identity, stage attempts and history. Each attempt owns its output directory.
The shared identity contains the application version and a canonical hash of
relative package payload paths and bytes, including Python, HTML, JavaScript and
runtime requirement files. New stage metrics, standalone catalogs, label workspaces
and trainer receipts retain the same identity. It excludes installation paths,
bytecode caches, models and third-party dependencies; model/runtime pins remain
separate evidence. Historical receipts without this field remain readable.
Completed artifacts are checked structurally and byte for byte; valid artifacts
must also match that job's source, predecessor, model/rule and review identities.
Published output left just before a checkpoint failure is recovered from that
attempt. Failed, incomplete or ambiguous output is retained and never treated as
a completed stage.

Reject conflicting concurrent work, changed source membership/content and altered
checkpoint artifacts with a specific recovery path. Cancellation is recorded at
safe boundaries. A new job is the explicit path for changed settings or collection
contents. Status is read-only and reports the latest useful stage/output and next
action rather than a generic error or an unqualified success flag.

| Situation | Continuation |
| --- | --- |
| Interrupted stage or transient failure | Correct the reported cause, then `dataset resume <workspace>`. |
| Missing model in offline mode | Run the printed pinned-model fetch command, then resume. |
| Saved review changes | `dataset resume <workspace> --refresh-reviews` republishes groups, policy, export and QA; earlier outputs stay intact. |
| Source membership/bytes, settings or unfinished-job implementation changed | Run the printed `dataset prepare ... --new` command. Prior jobs remain readable. |
| Altered or ambiguous artifacts | Inspect the retained job and restore verified evidence, or start a new job. |
| Conflicting saved decisions or no usable images | Open the printed review report, correct decisions/captions and resume with `--refresh-reviews`. |

Completed jobs remain verifiable after upgrades; generating new stages or
refreshing reviews requires the recorded implementation or a new job. Status
without `--verify` explicitly reports artifacts as not rechecked. With it, status
checks artifact contents and input bindings, but does not require or revalidate
the live source tree. Resume rechecks source membership and bytes before further
preparation. Exit codes are 0 for a completed command, 1 for required review, 2
for an execution error and 130 for cancellation.

Status includes every stage and its retained current/prior attempts. Verification
reports a failed stage while preserving healthy-stage results. Use `status --job
<id>` to inspect an older job without changing the current binding. Generated
resume commands carry `--job <expected-current-id>`; a stale selection fails before
execution rather than following a newly selected job. Pending artifacts remain
visible and untouched. See [recovery inspection](RECOVERY.md#finding-and-inspecting-preparation-work).

## Check cached inference progress

After an interrupted tagging stage, inspect the saved scores for that exact job:

```powershell
dataset status 'D:\datasets\collection' --job <exact-job-id> --verify-cache
dataset status --collection artwork --job <exact-job-id> --verify --verify-cache
```

`--verify-cache` checks the job's inventory, current source membership and bytes,
and locally retained model. It initializes the configured ONNX session to obtain
the actual providers and options that determine the cache namespace. This may load
a large model and use the configured device. It performs no image inference,
downloads, cache repair or application-data writes. Caption-only jobs report that
inference cache inspection does not apply, without loading a model.

The result separates image occurrences from unique image contents and reports
verified, missing and invalid cache entries. Exact-byte aliases share one vector.
Missing entries are ordinary remaining inference work. Corrupt or oversized files
stay untouched, and unrelated cache namespaces are not searched. A missing model,
unavailable runtime or untrusted inventory is reported explicitly; it is not
represented as an empty cache. Source changes and offline source directories are
reported separately from cache integrity.

These are current-session observations. They do not reconstruct how much work a
past process performed or guarantee that a later resume will use the same runtime.
Completed tagging artifacts, including a verified publication whose checkpoint
was interrupted, no longer need cached scores. Cache findings therefore
do not invalidate a completed export or change artifact verification. Ordinary
status and `--verify` retain their offline behavior. The printed continuation keeps
the exact job guard; historical selection, changed sources and implementation
compatibility still constrain resume. No inspection resumes work or grants human
acceptance. Cache problems or unavailable prerequisites return exit code 1; artifact
verification errors retain exit code 2. Missing scores alone return 0.

## Automated preparation policy

Saved corrections can be recovered through
[review history and guarded restoration](REVIEW-HISTORY.md). Restore updates the
review store with a new revision; it leaves existing exports and assessments intact.
Use its printed continuation to prepare a new dataset with the restored decisions.

For repeated label/subset/inclusion corrections, [bulk review](BULK-REVIEW.md)
previews every explicitly selected image and saves the changes in one atomic batch.
Its printed continuation refreshes compatible jobs or starts a new job as required.

[Saved browsing](REVIEW-PREFERENCES.md) keeps named image-filter views and restores
image/pair positions when reopening the same review report. These preferences are
separate from correction records, preparation checkpoints and acceptance.

[Changes since a report](REVIEW-CHANGES.md) lists net saved-record changes before
publication and distinguishes them from history-only advancement.

Automation can validate readability, preserve or normalize training derivatives,
choose nonempty captions by existing precedence, avoid exact duplicate repetition,
and conservatively keep unresolved similarity candidates together for splitting.
It cannot establish semantic ground truth or human caption acceptance.

An explicit versioned preparation policy records every automatic inclusion,
exclusion and split constraint with source hashes and reasons. Existing saved
review decisions, distinct relationships and caption overrides take precedence;
conflicts become actionable review work. No source image or source caption is
deleted, renamed or overwritten. An exact-byte alias with conflicting captions or
explicit review intent is preserved. Unreadable, changed or uncaptioned inputs are
reported individually; zero usable output is a failure, not an empty ready dataset.

`conservative-v1` excludes technically unsuitable undecided members, including
images whose scaled short side cannot fill a 64-pixel trainer bucket. Resolution
preferences remain review flags rather than destructive quality rules.
Exact aliases are removed from training membership only when effective captions
agree and the occurrence has no explicit inclusion, caption or annotation intent.
Source files are kept. Intake or inference errors retain their failed stage for
inspection and retry instead of silently publishing a partial successful run.

The existing strict reviewed export path remains available. Prepared exports must
say when their decisions come from automation and retain the policy evidence;
they must not set human acceptance or silently promote predictions to reviewed
labels. The structural verifier still requires nonempty captions, complete hashes,
unique names, exact membership and no known related-group or byte leakage.

Image transformations can invalidate literal caption phrases. When the existing
training-image conversion produces an opaque RGB image, remove an exact
comma-separated `transparent background` phrase from the derivative caption.
Retain the original effective caption, the versioned adjustment and frozen source
caption bytes where applicable. Do not rewrite source sidecars or saved overrides,
infer a new background label, or rewrite natural-language sentences. A caption
emptied by this adjustment requires correction instead of an empty training pair.

## Portable data and query contract

New immutable exports include `catalog.sqlite` and split-local `metadata.jsonl`
before their file hashes are frozen. SQLite queries use bounded, parameterized
filters; the catalog is derived evidence, not an alternate mutable review store.
Retain relative exported paths, source/content identity, derivative identity,
dimensions, group/split, caption and origin, explicit decisions and annotations.
Model scores and rule observations stay distinguishable from reviewed labels.

ImageFolder metadata uses `file_name` and caption `text`, following the
[Hugging Face image dataset contract](https://huggingface.co/docs/hub/datasets-image).
The exported directory remains useful offline and after relocation. Existing
exports without the new catalog continue to verify. Catalog rebuilding must not
mutate historical exports or imply that an external-reference index is portable.

## Review and operational delivery

Provide a dedicated critical-label UI bound to frozen image identities and the
existing label workspace. Start with the image and actual-presence checklist;
show optional saved-model comparisons only after initial judgments are saved.
Require explicit reviewer identity/kind, retain notes and revisions, and preserve
unsaved edits on stale saves or failures. Support explicit pilot membership without
model-driven selection and never call an explicit selection representative by fiat.

Use `dataset label-pilot ... --image <relative-path>` repeatedly for explicit
membership, then `dataset label-ui --workspace <label-workspace>`. Saved model runs
are optional `--run` arguments. See [label evaluation](LABEL-EVALUATION.md).

Disaster recovery must include packaged HTML/JS/pins as well as Python modules,
and caption restore must verify backup identity while retaining newer destination
files. Track reproducible source, wheel/resource and Windows command checks in the
repository. Verify the UI in an actual browser and the assembled dataset with the
pinned trainer loader. Neither test execution nor machine preparation substitutes
for collection-specific human quality acceptance.

## Verification boundary

Exercise clean and resumed preparation, crash after publication/before checkpoint,
stale/tampered input rejection, concurrent execution, no-network dry run, preserved
sources/overrides, policy attribution and exact duplicate/caption conflicts. Move
a generated export and query/verify its catalog with original sources unavailable.
Run meaningful recovery fault tests, browser save/reload/conflict checks and an
isolated installed-wheel journey. Record actual elapsed time and payload scope.
Apply the assembled workflow to the explicitly selected `pilot-dir`; do not
discover unrelated user collections. Keep unsupported platform/backend extensions
conditional and publish no general quality superiority claim from this pilot.
