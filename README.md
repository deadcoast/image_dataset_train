# Trainime

Prepare local anime images for training: inventory, validation, deduplication,
tagging, caption review, and reproducible image/sidecar exports.

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
| `trainime tag <directory>` | Interactive or direct directory tagging. | Writes only missing `.txt` sidecars beside source images; existing captions are kept. Uses app data under `%LOCALAPPDATA%\trainime` on Windows. |
| `trainime remove <directory>` | Remove paired captions after backup. | Backs up and removes source `.txt` sidecars; images and unrelated files remain. |
| `dataset scan` | Technical intake inventory. | Read-only; publishes an inventory under the configured `paths.runs`. |
| `dataset similarity --inventory <inventory-run>` | Find visually similar pair candidates. | Read-only; publishes `images.jsonl` and unreviewed `pairs.jsonl` under `paths.runs`. Pairs require human review and do not remove or group images. |
| `dataset similarity-evaluate --run <similarity-run>` | Measure thresholds against saved related/distinct judgments. | Writes an evaluation and replayable pair evidence under `paths.runs`; reads saved hashes without changing sources, reviews, or the proposal radius. |
| `dataset review --run <similarity-run>` | List pairs; use `--images` to list images. Save decisions with `--pair`, `--link`, or `--image`. | Reads by default. Edits persist under `paths.reviews`, bound to source paths and hashes; source images and captions remain unchanged. |
| `dataset groups --run <similarity-run>` | Publish the current related-image groups and review state. | Writes a new snapshot under `paths.runs`, retaining every eligible occurrence and its decisions. Does not split, copy, or export images. |
| `dataset export --groups <groups-run>` | Split whole groups and select reviewed captions. | Copies included images and captions to a new verified snapshot under `paths.exports`; preserves source files. Optional `--captions <tagging-run>` supplies missing drafts. |
| `dataset verify-export --run <export-run>` | Recheck a published export. | Read-only; verifies pairs, hashes, membership, and split consistency without the source collection. |
| `dataset qa --run <groups-or-export-run>` | Inspect captions, content/rating distributions, top tags, provenance, and split coverage. | Writes a new local browser report, image previews, and reproducible pilot selection under `paths.runs`; `--json` prints the snapshot summary; source files and review state stay unchanged. |
| `dataset qa-list --run <qa-run>` | Filter and page through QA findings in the terminal. | Reads the saved report and prints commands for the matching review records. |
| `dataset review-ui --run <qa-run>` | Review images and related pairs, assess the pilot, and publish from a local browser. | Saves decisions and judgments under `paths.reviews`; publishes new groups/QA under `paths.runs` and verified exports under `paths.exports`; preserves source files. |
| `dataset assessment --run <qa-run>` | Inspect recorded pilot results. | Reads progress, critical-label errors, reviewer notes, and the explicit pilot conclusion. |
| `dataset trainer-setup` | Prepare the pinned CPU dataset-loader runtime. | Downloads into `.cache/trainer`; keeps tagging dependencies separate. |
| `dataset trainer-check --run <export-run>` | Import pairs with the pinned sd-scripts loader. | Writes a qualification receipt under `paths.runs`; checks captions, repeats, buckets, and CPU tensors without model training. |
| `dataset trainer-status --run <export-run>` | Inspect the current import result and receipt history. | Reads export-bound receipts under `paths.runs`; the reviewer's Training import tab shows the same evidence and loader logs. |
| `dataset tag --inventory <inventory-run>` | Local WD inference. | Writes score vectors and caption drafts to a new run under `paths.runs`; source images and captions are not changed. |
| `dataset recaption --run <tagging-run>` | Reapply caption rules to saved scores. | Writes a new draft run; does not load the model or infer again. |

The technical preparation path is:

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
image pairs before making any grouping or exclusion decision.
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
Grouping joins exact-byte aliases and human-confirmed related pairs; it never
selects a keeper or deletes a variant. [Export](docs/EXPORT.md) applies manual
overrides, then source captions, then optional model drafts. It copies included
images into whole-group splits and writes separate Kohya configurations.
Pinned trainer import has generated-fixture CPU evidence; each export can receive
its own `trainer-check` receipt. Draft regeneration stays independent of review overrides.

- [PLAN.md](PLAN.md): review of the rough notes, pipeline design, acceptance criteria.
- [TODO.md](TODO.md): unfinished requirements and acceptance work.
- [docs/COMPLETED.md](docs/COMPLETED.md): completed steps and dated verification evidence.
- [docs/TAGGING.md](docs/TAGGING.md): model research, tagging commands, and qualification limits.
- [docs/SIMILARITY.md](docs/SIMILARITY.md): pHash proposal policy, artifacts, and evidence.
- [docs/REVIEW.md](docs/REVIEW.md): persistent decisions, caption overrides, and group snapshots.
- [docs/EXPORT.md](docs/EXPORT.md): split/export commands, caption precedence, and verification.
- [docs/TRAINIME.md](docs/TRAINIME.md): workflow design, preservation, recovery, and evidence.
- [docs/INSTALLATION.md](docs/INSTALLATION.md): installer, error logs, doctor, and repair behavior.
- [TAGGING-METHODS.md](TAGGING-METHODS.md): original notes and example snippets.

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
Large datasets, real-image QA, model accuracy, and trainer compatibility remain
unqualified. A real pinned SwinV2 CPU smoke run is documented in the tagging guide.
