# Image Dataset Train

Prepare local anime images for training: inventory, validation, deduplication,
tagging, caption review, and reproducible image/sidecar exports. Originals stay
untouched. Images are processed locally.

**Current implementation: inventory, validation, exact duplicate identification,
and JSON reports.** Tagging and training exports are planned, not implemented.

- [PLAN.md](PLAN.md): review of the rough notes, pipeline design, acceptance criteria.
- [TODO.md](TODO.md): implementation status and next work.
- [OVERVIEW.md](OVERVIEW.md): preserved original notes and example snippets.

## Run on Windows

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

Exit codes: `0` means the inventory completed, even if images were rejected;
`1` means it completed with file access/change errors; `2` means a configuration,
directory access, or publication failure. No inventory result means training-ready.

## Development

```powershell
uv run --locked --cache-dir .cache/uv ruff check .
uv run --locked --cache-dir .cache/uv ruff format --check .
uv run --locked --cache-dir .cache/uv pytest --basetemp .cache/pytest-local
uv build --cache-dir .cache/uv
```

Tests use generated, non-sensitive fixtures. No model download or GPU is required
for the implemented stage. Large datasets, real-image QA, inference quality, and
trainer compatibility have not yet been qualified.
