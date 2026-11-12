# Reviewed training exports

```powershell
dataset export --groups 'data/runs/<groups-id>' --captions 'data/runs/<tagging-or-recaption-id>'
dataset verify-export --run 'data/exports/<export-id>'
dataset trainer-setup
dataset trainer-check --run 'data/exports/<export-id>'
dataset trainer-status --run 'data/exports/<export-id>' --json
```

`--captions` is optional when every included image has a manual override or source
caption. Export reads a completed group snapshot; it does not read mutable current
review state. After changing reviews, publish new groups before exporting again.

Each export creates a new directory under `paths.exports` (default `data/exports`).
`--output <root>` overrides that root. Source files remain untouched. Compatible
images are copied byte-for-byte; TIFF, EXIF-oriented images, and transparent images
receive RGB PNG derivatives (`png-exif-white-v1`). This applies EXIF orientation
and composites alpha over white, with no resize or upscaling. ICC color conversion
is not performed. The manifest records original and exported hashes separately.
Exports are not hardlinks, and existing snapshots are never overwritten.

Caption precedence is manual override, recorded source sidecar, then the supplied
tagging/recaption manifest. Drafts must reference the same inventory as the groups.
Loose draft `.txt` edits are not overrides. Captions are normalized to one line;
empty captions stop publication. Included image bytes and recorded sidecars are
rechecked against their inventory hashes, including sidecars superseded by overrides.
Excluded images stay in provenance but do not receive exported files.

## Splits and files

The default validation ratio is 5%, with seed `20261011`. Override these with
`--validation-ratio` and `--seed`, or the `[export]` configuration table. Seeded
group ordering and image-count-aware allocation are deterministic. No related
group or exact-byte alias crosses splits. Multiple included aliases retain their
individual captions. The summary reports their count and the achieved ratio.

Training always retains at least one group. A positive ratio with at least two
included groups creates a validation split; one group remains entirely in training
and produces a warning. A zero ratio produces training only.

Semantic balancing is enabled by default (`[export] split_strategy = "semantic"`).
It uses only the reviewed labels and subset choices captured in the group snapshot.
The overall image ratio has priority; deterministic whole-group moves and swaps
then reduce label/subset imbalance without worsening that ratio. Overlapping
labels count independently, and related groups remain intact even when their
members have different subsets. Excluded images contribute nothing to balancing.

Use `--split-strategy size` to retain image-count-only allocation. With no semantic
annotations, the original size allocator is used automatically. Missing annotations
do not block export or become invented labels. Both algorithms record actual counts.

`splits.json` reports each label/subset's target and actual validation counts,
training counts, group coverage, missing split coverage, and mixed-subset groups.
Categories confined to one group cannot appear in both splits. The optimizer is a
bounded heuristic (32 improvement passes, up to 64 distinct candidate group profiles
per split for swaps), not a guarantee of a global optimum or complete coverage.
Its version and pass-limit status are recorded. Published assignments remain frozen;
new annotations require a new group snapshot and export.

- `train/`, `validation/`: uniquely named image/UTF-8 caption pairs.
- `manifest.jsonl`: source identities, groups, split, caption origin, dimensions,
  and checksums for each exported pair.
- `splits.json`: frozen assignments, algorithm, seed, ratio, and semantic balance report.
- `summary.json`: counts, caption origins, actual ratio, exclusions, and warnings.
- `provenance/`: captured groups, review history, and input-run metadata.
- `train.toml`, `validation.toml`: separate Kohya dataset configurations for nonempty
  splits. Validation is never included in the training configuration.
- `run.json`, `verification.json`: artifact checksums and publication verification.

When a caption run is supplied, new exports also freeze its manifest and include
per-image `caption_analysis`: rule identity, scored observations, composition,
subset proposals and findings. This is distinct from `caption_origin` and the
reviewed `subset`/`subset_origin`. Verification reconciles analysis against the
captured caption evidence and accepted subset provenance against the group snapshot.
Older exports remain verifiable. Frozen analysis is available to QA with the source
and original caption run offline.

The Kohya configurations set captions, repeats, resolution, and aspect-ratio buckets
using the [upstream dataset configuration format](https://github.com/kohya-ss/sd-scripts/blob/main/docs/config_README-en.md).
Run the trainer with the export directory as its working directory so relative
split paths resolve. `--resolution` changes bucket configuration, not source pixels;
`--repeats` changes training repeats. Defaults are 1024 and 1, with upscaling disabled.
Images whose effective short side falls below the 64-pixel bucket step are refused
with an actionable message; they previously produced zero-sized trainer buckets.

## Pinned trainer import

`trainer-setup` installs an isolated Python 3.12 CPU runtime under `.cache/trainer`
using Git and uv. The source pin is [sd-scripts v0.12.3,
cb70b96858477e716a2096292ab8aab433277f38](https://github.com/kohya-ss/sd-scripts/tree/cb70b96858477e716a2096292ab8aab433277f38).
All runtime dependencies are pinned separately from the application's environment.
Initial setup downloads packages; repeat setup is offline when the pins still match.
Both trainer commands accept `--runtime <directory>`.

`trainer-check` invokes the unmodified upstream configuration parser, DreamBooth
dataset loader, bucketing, image decoder, resize/crop path, and tensor transform.
It reconciles discovered image paths, captions, and repeat counts with the export,
checks finite CPU tensors, and confirms the trainer did not add another random split.
The check runs offline without downloading model weights or tokenizers.

Reports and loader logs go to a new directory under `paths.runs` (`--config` is
supported). Receipts bind the exact export, trainer commit, dependency versions,
and observed buckets. Export contents are checked before and after and stay
unchanged. A failed import also retains its report and returns 1; setup failures
and invalid inputs return 2. Successful import returns 0.

On 2026-11-08, Windows CPU imports passed for both an ordinary generated export and
a mixed TIFF/transparent-PNG/rotated-JPEG export, including separate validation
and training repeats. This qualifies dataset loading for those fixtures. It does
not execute tokenization, a training step, GPU operations, or collection acceptance.
Exports retain `trainer_qualified: false`; their separate, hash-bound check receipt
records qualification for that specific export and scope.

`trainer-status` reads receipts under the selected configuration's `paths.runs`,
reverifies the export and receipt artifacts, and reports the latest matching result
for the current trainer/dependency pin. It retains associated history, including
failures, changed export identities, and older pins. Exit 0 means the current CPU
import passed; 1 means no current pass can be established; invalid command or
configuration errors return 2. The [reviewer's Training import tab](QA.md) shows
the same evidence, split counts, buckets, result JSON, and loader logs. Reading
receipts requires neither the original collection nor an installed trainer runtime.

Status and receipt downloads use the [artifact snapshot contract](ARTIFACT-SNAPSHOTS.md).
Changed export or receipt bytes cannot retain an earlier current pass, and
historical receipts remain separate from current qualification.

Export verifies membership, hashes, nonempty paired captions, split consistency,
and absence of orphan files before publication. `verify-export` repeats those
snapshot checks without source images, prior runs, tagging extras, or config.toml.
Both commands return 0 on success and 2 on failure. Failed exports may retain a
`.pending-export-` directory for diagnosis; this is not a published snapshot.
Treat published snapshots as immutable; extra files also fail verification.
