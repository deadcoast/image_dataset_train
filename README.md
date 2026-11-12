# Trainime

Point at an image directory and prepare a portable training dataset with captions,
indexed metadata, train/validation splits and a local QA report. Source images and
existing captions stay unchanged.

```powershell
dataset prepare 'D:\images\collection' --workspace 'D:\datasets\collection'
```

The command inspects the collection, reuses or downloads the pinned local tagger,
preserves saved caption corrections, resolves technical eligibility and publishes
verified image/caption pairs. The default WD tagger is intended for anime-style
images. To prepare a collection using its existing captions without downloading
or running a model, add `--captions existing --offline`.

The result prints the export, SQLite catalog and QA report locations. Each nonempty
split also contains ImageFolder-compatible `metadata.jsonl`; the complete export
can move to another computer without its original source directory.

```powershell
dataset prepare 'D:\images\collection' --workspace 'D:\datasets\collection' --dryrun
dataset status 'D:\datasets\collection' --verify
dataset resume 'D:\datasets\collection'
```

Preview reads the images without writes, downloads or inference. Resume checks
saved stage inputs and outputs before reusing them. Saved review changes use
`resume --refresh-reviews`; changed source files or settings use a new `prepare
... --new` job. Earlier attempts and outputs remain available. Commands work
outside this checkout without a `config.toml`.

Automatic exclusions and conservative similarity split constraints carry their
policy reasons. They preserve every source file and remain separate from semantic
label judgments and human acceptance. Review conflicts produce a report and a
specific continuation command. See [directory preparation](docs/PREPARATION.md),
[catalog queries](docs/DATASET-CATALOG.md) and [recovery](docs/RECOVERY.md).

Preparation remembers the workspace in a local collection list. Find it later or
give an older workspace a convenient name:

```powershell
dataset collections
dataset collections add 'D:\datasets\collection' --name artwork
dataset status --collection artwork --verify
dataset runs --collection artwork --stage qa
```

The list only contains registered workspaces. Run records show their source,
stage and identity with commands for the selected report. Recovery status retains
failed and superseded attempts; generated resume commands name the expected job.
See [collection navigation](docs/COLLECTIONS.md).

To find retained caption backups and repair history:

```powershell
dataset recovery --source 'D:\images\collection'
dataset recovery show <full-receipt-id>
```

The [recovery browser](docs/RECOVERY-BROWSER.md) shows affected paths and exact
continuation commands. Listing works with source images offline and keeps saved
history separate from current integrity. Caption restore checks the selected
receipt before writing; collision retry retains its existing source-wide scope.

## Review and compare prepared datasets

Freeze representative membership before judging model labels, preserve assistant
or human attribution, and inspect effective captions against their exported images.
The [label reviewer](docs/LABEL-EVALUATION.md) supports a reproducible probability
sample of all source content, including images excluded from training. The
[QA reviewer](docs/QA.md) records caption judgments separately from model predictions.
Its [caption comparison](docs/CAPTION-COMPARISON.md) shows the saved override,
sidecar and pinned draft together, with the effective keep/replace/clear outcome
before a correction is saved.
Use [draft rule explanations](docs/CAPTION-EXPLANATIONS.md) to see why a tag was
selected or omitted, inspect subset predicates and trace forced phrases from saved
scores without rerunning inference.
The [recovery controls](docs/REVIEWER-RECOVERY.md) explain empty queues and retry
unavailable previews or saved form reads while preserving unrelated unsaved work.
[Saved browsing](docs/REVIEW-PREFERENCES.md) restores image filters and image/pair
positions when you reopen the same report, and keeps named filter views.
[Judgment integrity](docs/REVIEW-INTEGRITY.md) keeps persisted state, history and
attribution consistent. Label shortcuts obey the same eligibility checks as Save;
unavailable images can be retried without losing edits.
[Model selection and saved rules](docs/MODEL-RULE-CONTRACT.md) bind configured
inference to the requested bundle and interpret saved scores using their checked
recorded thresholds, with explicit mismatch and historical-evidence recovery.
[Artifact snapshot checks](docs/ARTIFACT-SNAPSHOTS.md) keep catalog results and
trainer status tied to verified bytes, with recovery after detected changes.

After saving corrections and publishing an updated export, compare the exact inputs:

```powershell
dataset snapshot-compare --before 'D:\datasets\old-export' --after 'D:\datasets\new-export'
```

The verified report shows caption edits, membership, grouping and split changes.
See [snapshot comparison](docs/SNAPSHOT-COMPARISON.md) to retain a portable receipt.

## Source-side caption actions

**`trainime` is the directory-action workflow.** It tags missing source sidecars
or backs up and removes paired captions. The menu is:

```text
[1] Tag Image Directory
[2] Remove Tags
[3] Help
[0] Settings
```

Select an action, enter the image directory if one is not already set, and answer
`Preview only? --dryrun [y/N]:`. Enter applies the action; `y` previews it. There
are no model, threshold, batching, or export menus in this workflow.

- **Tag:** includes subfolders; writes missing `.txt` captions beside images and
  keeps existing captions. The model is downloaded automatically on first use.
- **Remove:** backs up and removes `.txt` captions paired with images, including
  manual captions. Unrelated text files and images remain. The result prints the
  backup directory, which mirrors the original caption paths.
- **Settings:** save a default directory or set a session directory. The session
  directory takes priority and disappears on exit. A path entered during an action
  is remembered for that session only. Blank clears a setting.
- **Help:** `3` shows keys and commands. `q` exits; Ctrl+C cancels an action and
  returns Home. Tab completes paths; quoted Explorer paths work.

**Install:** double-click [install.cmd](install.cmd), or run:

```powershell
.\install.cmd
```

The installer handles Python, dependencies, the `trainime` command, and PATH. It
checks imports and actual ONNX execution before completing installation. Open a
new terminal and run `trainime`; the installer also prints a direct launch command
for the current terminal. Running the installer again updates or repairs the app.

**If something breaks:**

```powershell
trainime doctor --fix
trainime logs
```

Doctor repairs missing dependencies, damaged application files, saved settings,
and model/score caches. Damaged settings and cache files are preserved in recovery.
If the command cannot start, run `install.cmd` again. Failed installs and operations
print a specific recovery action and the log path. See
[installation and recovery](docs/INSTALLATION.md).

Direct commands use the same pipeline, with no prompts:

```powershell
trainime tag 'D:\images\anime' --dryrun
trainime tag 'D:\images\anime'
trainime remove 'D:\images\anime' --dryrun
trainime remove 'D:\images\anime'
```

Omit the path to use the saved default. `--dryrun` performs inspection only: no
model download, inference, caption changes, or report/cache writes. It reports
eligible files; it cannot predict the model's tags. To retag existing captions,
use Remove Tags, then Tag Image Directory.

**Apply detected repairs with `--fix`, or select a repair by number.**

```powershell
trainime tag 'D:\images\anime' --fix --dryrun
trainime tag 'D:\images\anime' --fix
trainime tag 'D:\images\anime' --fix 1
```

Bare `--fix` discovers and applies applicable registered repairs. Numbers such as
`1` or `001` select `tf001`; error codes such as `te001` select their mapped fixes.
Comma-separated or repeated selectors can choose multiple registered fixes.
Unknown numbers are rejected before changes. The menu offers the available fixes
only when an error occurs; no extra normal-path menus are added.

The current directory repair is `[tf001]` for same-stem collision `[te001]`.
It gives colliding images unique stems, then continues tagging. For example,
`art.jpg` and `art.png` become `art-jpg.jpg` and
`art-png.png`; occupied stems get a numeric suffix. Ambiguous captions are copied
and verified in recovery before leaving the image directory, then each renamed
image receives its own generated caption. Unambiguous manual captions stay intact.
For this error the conditional menu prompt is `Apply tf001? --fix [y/N]:`.

For renaming without tagging: `trainime fix 'D:\images\anime'`, or
`trainime doctor --path 'D:\images\anime' --fix tf001`. All accept `--dryrun`.
Completed repairs do nothing on repeat runs; interrupted repairs resume from
their saved plans. See [the repair contract](docs/TRAINIME.md#tagging-error-repairs).

A preview reports eligibility, not completed tagging:

```text
--dryrun found 166 images that can be serviced for tags.
170 images scanned   ·   166 eligible   ·   4 already tagged (kept)
No files changed. No tags generated.
```

`can` and eligible counts are green. Commands and navigation are cyan; skipped
items are amber and failures red. The preview prints the exact command to apply
the action. Narrow terminals use stacked counts; redirected output and `NO_COLOR`
remain readable without color.

Settings, models, score cache, reports, and removed captions live under
`%LOCALAPPDATA%\trainime` on Windows. `TRAINIME_HOME` overrides that directory.
The image directory must be separate from this application-data tree. The command
works outside this repository and does not depend on a local `config.toml`.

**Current implementation:** interactive workflows, inventory, validation, exact
duplicates, pHash pair proposals, durable human decisions and caption overrides,
related-image group snapshots, local WD tagging, score caching, caption regeneration,
and reports.
Group-aware training exports and independent snapshot verification are implemented.

## Two command workflows

`trainime` and `dataset` are separate interfaces with different outputs:

| Command | Purpose | Output and source effects |
| --- | --- | --- |
| `dataset prepare <directory>` | Prepare an image directory with useful defaults. | Preserves sources; publishes attributed preparation decisions, verified training pairs, a portable catalog and QA in a durable workspace. |
| `dataset status <workspace>`, `dataset resume <workspace>` | Inspect or continue a preparation job. | `--verify` checks completed artifacts; `--verify-cache` loads the local model to check reusable scores without inference. Resume checks source identity and reuses verified stages. |
| `dataset catalog-info`, `dataset catalog-query` | Inspect and filter portable training metadata. | Reads checked catalog/metadata/provenance without requiring the original images. Full media checks remain `verify-export`. |
| `trainime tag <directory>` | Interactive or direct directory tagging. | Writes only missing `.txt` sidecars beside source images; existing captions are kept. Uses app data under `%LOCALAPPDATA%\trainime` on Windows. |
| `trainime remove <directory>` | Remove paired captions after backup. | Backs up and removes source `.txt` sidecars; images and unrelated files remain. |
| `dataset restore-captions --receipt <removal-report>` | Recover backed-up source captions. | Restores verified missing captions without overwriting newer files; preserves conflicts and records the attempt. Supports read-only preview. |
| `dataset scan` | Technical intake inventory. | Read-only; publishes an inventory under the configured `paths.runs`. |
| `dataset similarity --inventory <inventory-run>` | Find visually similar pair candidates. | Read-only; publishes `images.jsonl` and unreviewed `pairs.jsonl` under `paths.runs`. Pairs require explicit review and do not remove or group images. |
| `dataset similarity-evaluate --run <similarity-run>` | Measure thresholds against saved related/distinct judgments. | Writes an evaluation and replayable pair evidence under `paths.runs`; reads saved hashes without changing sources, reviews, or the proposal radius. |
| `dataset review --run <similarity-run>` | List pairs; use `--images` to list images. Save decisions with `--pair`, `--link`, or `--image`. | Reads by default. Edits persist under `paths.reviews`, bound to source paths and hashes; source images and captions remain unchanged. |
| `dataset review-history list\|show\|restore --collection <name>` | Inspect earlier image/pair edits and preview restoring a selected revision. | [Restore](docs/REVIEW-HISTORY.md) requires explicit apply with matching preview/revision guards; it appends history and leaves sources, exports and acceptance intact. |
| `dataset review-history changes --collection <name>` | Explain saved image/pair changes since the selected report. | [Snapshot changes](docs/REVIEW-CHANGES.md) validates captured history, separates net changes from history-only advancement and provides publication navigation without writing. |
| `dataset review-batch --collection <name> --images-file <selection.json> ...` | Preview explicit label, subset or inclusion changes for every selected image. | [Bulk review](docs/BULK-REVIEW.md) applies one guarded atomic batch with actor/reason and per-image history; it preserves captions and published artifacts. |
| `dataset groups --run <similarity-run>` | Publish the current related-image groups and review state. | Writes a new snapshot under `paths.runs`, retaining every eligible occurrence and its decisions. Does not split, copy, or export images. |
| `dataset export --groups <groups-run>` | Split whole groups and select reviewed captions. | Copies included images and captions to a new verified snapshot under `paths.exports`; preserves source files. Optional `--captions <tagging-run>` supplies missing drafts. |
| `dataset verify-export --run <export-run>` | Recheck a published export. | Read-only; verifies pairs, hashes, membership, and split consistency without the source collection. |
| `dataset qa --run <groups-or-export-run>` | Inspect captions, content/rating distributions, top tags, provenance, and split coverage. | Writes a new local browser report, image previews, and reproducible pilot selection under `paths.runs`; `--json` prints the snapshot summary; source files and review state stay unchanged. |
| `dataset qa-list --run <qa-run>` | Filter and page through QA findings in the terminal. | Reads the saved report and prints commands for the matching review records. |
| `dataset review-ui --run <qa-run>` | Review images and related pairs, assess the pilot, and publish from a local browser. | Saves decisions and judgments under `paths.reviews`; publishes new groups/QA under `paths.runs` and verified exports under `paths.exports`; preserves source files. |
| `dataset assessment --run <qa-run>` | Inspect recorded pilot results. | Reads progress, critical-label errors, reviewer notes, and the explicit pilot conclusion. |
| `dataset label-pilot`, `label-ui`, `label-review`, `label-refresh`, `tag-evaluate` | Review critical labels and compare models. | Supports explicit frozen membership, image-first atomic judgments and optional model comparison; retains reviewer attribution, exposure history and group-disjoint evaluation. See [label evaluation](docs/LABEL-EVALUATION.md). |
| `dataset trainer-setup` | Prepare the pinned CPU dataset-loader runtime. | Downloads into `.cache/trainer`; keeps tagging dependencies separate. |
| `dataset trainer-check --run <export-run>` | Import pairs with the pinned sd-scripts loader. | Writes a qualification receipt under `paths.runs`; checks captions, repeats, buckets, and CPU tensors without model training. |
| `dataset trainer-status --run <export-run>` | Inspect the current import result and receipt history. | Reads export-bound receipts under `paths.runs`; the reviewer's Training import tab shows the same evidence and loader logs. |
| `dataset tag --inventory <inventory-run>` | Local WD inference. | Writes score vectors and caption drafts to a new run under `paths.runs`; source images and captions are not changed. |
| `dataset recaption --run <tagging-run>` | Reapply caption rules to saved scores. | Writes a new draft run; does not load the model or infer again. |

`dataset prepare` composes the technical stages below with an explicit automatic
preparation policy. Individual commands retain the stricter reviewed-export path:

```text
source images + existing captions
  -> dataset scan -> inventory
       |-> dataset similarity -> pair proposals
       |-> dataset tag -> scores + caption drafts -> dataset recaption

pair proposals -> dataset review -> dataset groups
caption drafts -> human inspection -> dataset review --image ... --caption ...
  -> dataset qa -> dataset review-ui -> image/pair corrections + pilot assessment
                                  -> Publish -> new groups + QA or verified export + QA
  -> dataset export -> verified train/validation pairs
  -> dataset qa -> inspect frozen export captions and split coverage
  -> dataset trainer-check -> CPU import receipt
```

The similarity command defaults to a maximum Hamming distance of 8 for its
64-bit pHash. This is a candidate-generation threshold, not a calibrated duplicate
rule. It applies a documented orientation, white-padding, grayscale, and resize
policy and records a stable pair ID, both source hashes, hash version, Pillow
version, and inventory hash. Each source is rechecked against its inventory hash
when read; stop external writers to the collection while a stage runs. Review the
image pairs before recording semantic grouping or near-duplicate exclusion decisions.
Automatic preparation can keep unresolved candidates in the same split without
asserting that they depict the same content.
Similarity and tagging each consume the inventory; neither consumes the other's
output. Exact-byte aliases remain in that inventory and are skipped during pHash
proposal generation. Reports and CLI summaries distinguish these aliases from
ineligible images. See [similarity commands and artifacts](docs/SIMILARITY.md).
Use [review commands](docs/REVIEW.md) to record related/distinct pairs, manually
link artwork missed by pHash, include/exclude images, and preserve caption overrides.
Review also supports explicit labels and one semantic subset per image. Export
balances these annotations across whole groups and reports rare/missing categories;
`--split-strategy size` retains image-count-only allocation.
Use [pilot QA](docs/QA.md) to navigate captions, annotations, groups, and split
coverage in a local browser report or the terminal before and after export.
Grouping joins exact-byte aliases and review-confirmed related pairs; it never
selects a keeper or deletes a variant. [Export](docs/EXPORT.md) applies manual
overrides, then source captions, then optional model drafts. It copies included
images into whole-group splits and writes separate Kohya configurations.
Pinned trainer import has generated-fixture CPU evidence; each export can receive
its own `trainer-check` receipt. Draft regeneration stays independent of review overrides.

- [PLAN.md](docs/PLAN.md): review of the rough notes, pipeline design, acceptance criteria.
- [docs/IDENTIFIED.md](docs/IDENTIFIED.md): current review findings and stable source IDs.
- [docs/SHELVED.md](docs/SHELVED.md): findings ordered by PLAN milestones; source for the next TODO tasks.
- [TODO.md](TODO.md): active unfinished requirements and acceptance work.
- [docs/COMPLETED.md](docs/COMPLETED.md): completed steps and dated verification evidence.
- [docs/TAGGING.md](docs/TAGGING.md): model research, tagging commands, and qualification limits.
- [docs/SIMILARITY.md](docs/SIMILARITY.md): pHash proposal policy, artifacts, and evidence.
- [docs/REVIEW.md](docs/REVIEW.md): persistent decisions, caption overrides, and group snapshots.
- [docs/EXPORT.md](docs/EXPORT.md): split/export commands, caption precedence, and verification.
- [docs/TRAINIME.md](docs/TRAINIME.md): workflow design, preservation, recovery, and evidence.
- [docs/INSTALLATION.md](docs/INSTALLATION.md): installer, error logs, doctor, and repair behavior.
- [TAGGING-METHODS.md](docs/TAGGING-METHODS.md): original notes and example snippets.

## Technical stage commands

Use the existing `uv` installation. The project selects Python 3.12 and keeps its
environment and package cache inside the repository.

```powershell
uv sync --locked --cache-dir .cache/uv
uv run --locked --cache-dir .cache/uv dataset scan --source 'D:\images\anime'
```

Or put images in `data/00_inbox` and run:

```powershell
uv run --locked --cache-dir .cache/uv dataset scan
```

`config.toml` contains the implemented settings. Configured paths resolve relative
to that file. `--source` and `--runs` overrides resolve relative to the current
directory. Source and report directories must be separate trees.

The scan reads every regular file, hashes its complete contents, verifies and
decodes supported images, and records existing `.txt` sidecars. It does not copy,
move, rename, convert, or overwrite images or captions. Symlinks and Windows
junctions within the source are recorded without following them.

Supported image extensions: PNG, JPG/JPEG, WebP, BMP, TIF/TIFF. Animated or
multi-page images are rejected for this still-image pipeline. Other file types
remain on disk and appear in the inventory as skipped.

Each invocation creates a new report directory:

```text
data/runs/<run-id>/
  manifest.jsonl   # one row per discovered file/link, paths relative to source
  summary.json    # counts for this invocation only
  run.json        # source, config, versions, completion status, manifest hash
```

Decisions describe intake only:

| Decision | Meaning |
| --- | --- |
| `candidate` | Decodes and meets the configured intake preferences. Further stages remain. |
| `review` | Resolution, transparency, color profile, image mode, or sidecar needs attention. |
| `duplicate` | Byte-identical to the recorded keeper; neither file is changed. |
| `rejected` | Empty, unreadable, multi-frame, or over a decode/file limit. |
| `skipped` | Non-image file, existing sidecar, or link. |
| `error` | File could not be read or changed during inspection. |

The minimum short side of 768 is a provisional review preference. Images below it
are retained. Long sides over 4096 are also flagged, not resized. The separate
50-million-pixel and 256 MiB limits prevent attempting unreasonable decodes.
Pillow's own decoder limits still apply.

Exact duplicates use complete SHA256 hashes. The lexicographically first relative
path is the representative of identical bytes. Conflicting existing sidecars are
flagged. The separate similarity stage proposes near-duplicates for review. Same-stem images such as
`picture.jpg` and `picture.png` are flagged because `picture.txt` is ambiguous.

The manifest is deterministic for unchanged inputs, configuration, and runtime;
run IDs and timestamps are intentionally different. A scan is not a locked
filesystem snapshot: stop other writers while scanning. A later stage must
recheck source hashes before consuming files.

`dataset scan` exit codes: `0` means the inventory completed, even if images were rejected;
`1` means it completed with file access/change errors; `2` means a configuration,
directory access, or publication failure. No inventory result means training-ready.

## Development

```powershell
uv run --locked --extra tag-cpu --cache-dir .cache/uv ruff check .
uv run --locked --extra tag-cpu --cache-dir .cache/uv ruff format --check .
uv run --locked --extra tag-cpu --cache-dir .cache/uv pytest --basetemp .cache/pytest-local
uv build --cache-dir .cache/uv
```

Tests use generated fixtures and small ONNX graphs; no pretrained model or GPU
is needed for the automated suite. Intake does not require tagging extras.
The selected collection has representative assistant image/caption review and a
355-pair pinned CPU trainer import, recorded in
[the completion log](docs/COMPLETED.md#representative-assistant-review-070).
Larger collections, general model accuracy, human dataset acceptance and other
trainer targets remain outside that qualification.
