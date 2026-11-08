# Tagging research and implementation

Research checked 2026-10-11. The tagging pipeline was first qualified with project
version 0.2.0; the package version is now 0.5.1. The evidence in this document is
milestone-specific: it establishes local execution and preprocessing parity, not
current anime-collection accuracy, physical CUDA behavior, or training readiness.
See [TODO.md](../TODO.md) for the latest recorded package-level checks and their
dates. Research references below have not been rechecked in this status update.

## Research decisions

The first backend supports WD v3 ONNX models, with selectable pinned profiles.
SwinV2 remains the baseline from the notes and is the model actually exercised
here. EVA02-Large is the next comparison candidate. Bigger or newer does not by
itself justify replacing every caption.

| Candidate | Publisher evidence | Pipeline decision |
| --- | --- | --- |
| WD SwinV2 v3 | Reports macro-F1 0.4541 and P=R threshold 0.2653 for its v2.0 weights. | Implemented and CPU smoke-tested. Retain the demo's 0.35 initial general threshold for continuity. [Model card](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3) |
| WD ViT-Large v3 | Reports macro-F1 0.4674 and P=R threshold 0.2606. | Implemented selectable profile; its weights have not been locally qualified. [Model card](https://huggingface.co/SmilingWolf/wd-vit-large-tagger-v3) |
| WD EVA02-Large v3 | Reports macro-F1 0.4772 and P=R threshold 0.5296 on the WD v3 benchmark. | Implemented selectable profile; use 0.5296 as an initial general threshold, then calibrate locally. [Model card](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) |
| Camie v2 | Reports 70,527 labels, micro-F1 0.673 at 0.614, and macro-F1 0.506 at 0.492. Its card lists GPL-3.0; WD cards list Apache-2.0. | Research candidate for a separate adapter. Different vocabulary, preprocessing, outputs, and evaluation prevent treating it as a drop-in replacement. [Model card](https://huggingface.co/Camais03/camie-tagger-v2) |

Camie's test distribution and label coverage differ from WD's benchmark. Comparing
its micro-F1 with WD macro-F1 is misleading. Published metrics do not establish
accuracy on this collection. Automatic averaging or union of model tags is not
implemented because disagreements need evaluation, not an assumption of consensus.

Camie's ONNX reference uses normalized RGB, channel-first tensors, and sigmoid
over model logits. WD expects channel-last BGR values in the 0-255 range and returns
scores. Reusing WD's input/output processing for Camie would be incorrect.
[Camie inference source](https://huggingface.co/Camais03/camie-tagger-v2/blob/7d40c1b85b86ab4f607b2caf26b1b50c99db743e/onnx_inference.py)

The checked publisher model list contains these WD v3 releases. This research does
not claim an exhaustive ranking of every anime tagger. The pinned revisions are:

| Profile | Repository | Commit |
| --- | --- | --- |
| `swinv2-v3` | `SmilingWolf/wd-swinv2-tagger-v3` | `627aef95638667ddcaa3ac8ae625e88ea5b02f51` |
| `vit-large-v3` | `SmilingWolf/wd-vit-large-tagger-v3` | `ae469aa2e4706a3af08d3673cf73a11d1add314c` |
| `eva02-large-v3` | `SmilingWolf/wd-eva02-large-tagger-v3` | `b25b82a03f7282e41aa2f257a52c7583b710bd1c` |

## Implemented contract

- Check one float32 input, square NHWC geometry, one float32 output, and exact
  agreement between output width and CSV length. Support dynamic batches and
  fixed batch one. Reject invalid score shapes, NaNs, infinities, and logits.
- Apply EXIF orientation, composite alpha over white, pad to square, resize with
  bicubic interpolation, and produce contiguous BGR float32 data. No cropping or
  source conversion. Both decoded pixels and the padded square are bounded.
  EXIF handling is an explicit addition to the publisher reference.
- Preserve CSV positions and explicit categories: general `0`, character `4`,
  rating `9`. Do not guess character categories from punctuation. Retain every
  category's scores; render underscores as spaces while preserving emoticons.

These choices follow the inspected input and category handling in the
[WD reference](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/fbd35b187d6e8cb8a00c529d52999f82d6b5193b/app.py).
ICC profiles and unusual modes remain review flags. Pillow conversion matches the
WD input path; a color-managed training derivative workflow is still pending.

## Captions and review

Thresholds are applied after inference. Character captions are opt-in at 0.85 by
default. General thresholds come from the model profile unless overridden.
Per-tag thresholds and exclusions use raw CSV names; misspelled names fail clearly.
Selection uses strict `score > threshold`, matching the publisher demo. Scores
are model outputs, not calibrated probabilities of correctness.

Record near-threshold tags on either side of the cutoff. Flag contradictory counts
and `solo` conflicts without erasing evidence. No style, relationship, nudity, or
action is forced from a folder name. Nudity does not cause rejection. Automatic
count repair, tag implication expansion, and generic blacklists are not enabled.

Caption drafts are named by a hash of the source's relative path, avoiding
same-stem collisions. The manifest maps drafts back to images. These are review
artifacts, not trainer-ready pairs. Existing source captions remain untouched.
Durable manual overrides and reviewed export eligibility are pending; editing a
draft `.txt` does not establish a persistent override.

## Provenance, cache, and offline operation

`fetch-model` downloads weights and labels from one full commit hash, records
their SHA256 values, and executes no repository Python code. Hashes are checked
before inference. [Hub revision downloads](https://huggingface.co/docs/huggingface_hub/guides/download)

Tagging verifies its inventory hash and rechecks each eligible image's SHA256,
including on cache hits. Changed files, newly introduced links, and exceeded
limits become errors. Intake rejection skips inference. Intake review and duplicate
decisions remain attached to scored records; scoring does not approve export.

Cache identity includes source bytes, model/label hashes, preprocessing version,
library versions, and registered provider settings. Byte-identical images share
inference. Atomic score writes let completed batches survive an interrupted run.
Corrupt cache entries are reported and retained for inspection.

Every published run also keeps its own complete float32 score vectors and label
index. Clearing the reusable cache cannot erase that run's evidence. `recaption`
verifies these saved files, writes a new run, and loads neither model weights nor
source images. It records `source_revalidated=false`; a later export must check
current sources again. Prior caption drafts remain unchanged.

Explicit CUDA refuses initialization fallback to CPU; `auto` reports fallback.
Runtime inference fallback is disabled. Registered providers/options are recorded,
which does not prove every operator ran on GPU. GPU execution has not been tested
on physical hardware here. [ONNX Runtime providers](https://onnxruntime.ai/docs/api/python/api_summary.html)

## Commands

```powershell
uv sync --locked --extra tag-cpu --cache-dir .cache/uv
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset fetch-model
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset scan --source 'D:\images\anime'
```

Use the inventory directory printed by `scan`:

```powershell
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset tag --inventory 'data/runs/<inventory-id>'
```

Change caption rules or try a threshold without inference:

```powershell
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset recaption --run 'data/runs/<tagging-id>' --threshold 0.45
```

Compare EVA02 using the same inventory:

```powershell
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset fetch-model --model eva02-large-v3
uv run --locked --extra tag-cpu --cache-dir .cache/uv dataset tag --inventory 'data/runs/<inventory-id>' --model eva02-large-v3
```

An explicit config `general_threshold` or `--threshold` overrides the selected
profile. CPU/GPU extras are mutually exclusive. GPU installation requires a
compatible driver/runtime. [CUDA requirements](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
Tagging and recaptioning use local artifacts; the explicit fetch command is the
only network stage. There is no caption-API or dataset-upload path.

## Evidence and remaining work

Completed local evidence:

- Pinned SwinV2 loads with 10,861 labels and a 448-pixel input.
- CPU inference succeeds on two generated geometric images; a duplicate shares scores.
- The rerun uses two cached vectors with zero image inference.
- Changed caption thresholds reuse saved scores with zero inference.
- Source-image and manual-sidecar hashes stay unchanged.
- Four generated RGBA fixtures match the publisher preprocessing method exactly
  at the tensor level: portrait, landscape, square, and small input.
- Automated tests additionally exercise small ONNX graphs, batching, category
  indexing, corrupted scores, source mutation, interrupted inference, and
  source-independent recaptioning.

Evidence files are ignored local artifacts:
`.cache/tagging-research/preprocessing-parity.json` and
`.cache/tagging-smoke/2cdfa67d186b40329528ccb25ddd4478/verification.json`.
Generated fixtures establish execution, not anime tagging accuracy.

Next, compare SwinV2/EVA02 on the same representative anime pilot with reviewed
labels. Measure label precision/recall, composition-specific mistakes, and
speed/memory. Tune thresholds on reviewed examples, then check them on held-out
images. Camie requires its own adapter and the same evaluation. Alternate WD
weights, GPU execution, collection-scale behavior, human review acceptance, and
downstream training quality remain unqualified.
