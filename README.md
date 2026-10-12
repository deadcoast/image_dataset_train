# Trainime

Prepare local anime images for training: inventory, validation, deduplication,
tagging, caption review, and reproducible image/sidecar exports. Image files stay
untouched. Images are processed locally.

**Run `trainime` to tag a directory or remove its captions.** The menu is:

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
duplicates, local WD tagging, score caching, caption regeneration, and reports.
Reviewed training exports are pending.

- [PLAN.md](PLAN.md): review of the rough notes, pipeline design, acceptance criteria.
- [TODO.md](TODO.md): implementation status and next work.
- [docs/TAGGING.md](docs/TAGGING.md): model research, tagging commands, and qualification limits.
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
flagged. Near-duplicate detection is not included yet. Same-stem images such as
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
