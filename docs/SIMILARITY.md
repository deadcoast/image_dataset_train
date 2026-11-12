# Similarity proposals

`dataset similarity` reads a completed inventory and proposes image pairs for
human review. It writes a new run under `paths.runs` from `config.toml`. It does
not change images, captions, inventory decisions, or group membership.

Continue with `dataset review --run <similarity-run>` to save human decisions,
then `dataset groups --run <similarity-run>` to publish their related-image groups.
See [the review workflow](REVIEW.md) for image decisions, manual links, caption
overrides, and the difference between review completion and training readiness.

```powershell
dataset scan --source 'D:\images\anime'
dataset similarity --inventory 'data/runs/<inventory-id>'
dataset similarity --inventory 'data/runs/<inventory-id>' --max-distance 4
```

Both commands accept `--config <file>`. Use the inventory directory printed by
`scan`; similarity and WD tagging can consume that same inventory independently.
Similarity requires only the base installation, with no model, download, NumPy,
or ONNX runtime.

The default maximum Hamming distance is 8, inclusive, with accepted values 0–64.
A smaller radius proposes fewer pairs. Zero means identical perceptual hashes;
it does not establish byte equality or visual equivalence. The radius is
provisional and has not been calibrated against reviewed anime artwork.

## Evaluate reviewed pairs

```powershell
dataset similarity-evaluate --run 'data/runs/<similarity-id>' --json
```

The **Related pairs** view offers the same **Evaluate saved judgments** action.
Both publish a new run under `paths.runs`, containing `summary.json`, `pairs.jsonl`
and run metadata with artifact hashes. Source images and review decisions are unchanged. Saved
hashes are used directly; original images can be offline, while the referenced
inventory, similarity artifacts and review store must remain available.

The report compares radii 0–64, inclusive, with true/false positives and negatives,
precision, recall and F1. The all-reviewed-pair sweep remains descriptive. When
reviewers assign pairs to `calibration` and `held_out`, it also fits the radius by
maximum calibration F1 (ties prefer the smaller radius) and reports held-out metrics
at that radius separately. It shows false matches and known misses at the original
proposal radius; graphical examples reopen the pair for correction. The saved
evaluation retains its review revision when judgments later change.

Only explicit related/distinct judgments enter the measurements. Manual comparisons
outside the proposal radius provide known misses; unjudged pairs are never counted
as negatives. Exact-byte pairs are reported separately, and alias judgments collapse
to one content pair. Stale decisions, unavailable hashes and conflicting judgments
are counted outside the scored sample. Undefined ratios are `null`, not perfect scores.

Review both related and distinct examples, including independently selected pairs
outside the proposal queue. A proposal-only sample cannot establish missed-match
behavior for the collection. A fitted radius is exploratory evidence and does not
qualify the collection. Unassigned pairs are excluded from the fit and held-out
evaluation, but remain in the descriptive all-reviewed-pair sweep. `pairs.jsonl`
preserves judged hashes, distances, paths, decisions, reasons and set assignments.

## Input and preservation

The inventory manifest checksum, schema, source paths, and eligible-image SHA256
values are validated before creating outputs. Each considered image is reread
and checked against its recorded hash. Links and Windows junctions introduced
after inventory are refused. Changes and unreadable files become error records
while other images continue.

Intake `candidate` and `review` images are considered. Exact-byte `duplicate`
aliases stay in the inventory and are skipped here; their representative is
considered. Rejected/error images are skipped. The summary reconciles these
categories with the inventory image count. Excluding an alias from pHash work is
not an approval to delete it or discard its sidecar provenance.

Source and output directories must be separate trees. The stage does not lock the
collection against external writers. Recorded hashes describe the bytes read;
a later review/export stage must validate sources again.

## Versioned hash policy

`phash64-padded-white-gray-v1` applies EXIF orientation, composites alpha over
white, centers the image on a white square, converts to Pillow grayscale, and
resizes to 32×32 using Lanczos. The original aspect ratio is retained by padding.
ICC color conversion is not applied. Both image area and padded-square area are
checked against `max_decode_pixels` before decoding; `max_file_bytes` is also
enforced. Multiple-frame images are refused.

The hash uses the top-left 8×8 coefficients of an unnormalized separable DCT-II,
including DC. Each coefficient is compared with the median of those 64 values
using `>=`, in row-major order, yielding 64 bits stored as 16 hexadecimal digits.
This named policy should not be assumed interchangeable with another pHash
implementation. The run records Python/Pillow versions and current limits.

BK-tree lookup prunes Hamming comparisons. Pair records stream to staged files;
the inventory and hash index still use memory proportional to image count.
Dense matches and large radii can produce quadratically many pair records, so
streaming does not establish collection-scale time or disk requirements.

## Artifacts and errors

| File | Contents |
| --- | --- |
| `images.jsonl` | Each considered source path/hash, computed pHash, or error. |
| `pairs.jsonl` | Stable pair ID, both paths/content hashes/pHashes, distance, radius, and `unreviewed` status. |
| `summary.json` | Seen/considered/hashed/skipped/error counts, proposal count, and qualification flags. |
| `run.json` | Inventory reference and checksum, artifact checksums, runtime and hash policy, limits, timestamps, completion status. |

Pair IDs bind the ordered source paths and content hashes to the hash-policy
version. They stay stable across radius changes when the same pair is proposed.
Output order is deterministic for unchanged inventory, sources, policy, and runtime.
Neither pair proximity nor a transitive chain chooses keepers or approves groups.

Exit code `0` means proposal generation completed without image errors; `1` means
it completed with image errors; `2` means the stage could not run or publish.
Cancellation through the console entry point returns `130`. Publication happens
only after artifacts finish writing. Interrupted/failed writes retain a `.pending-`
directory; rerunning creates a new run. Reports are not filesystem-wide snapshots
or power-loss transactions.

## Evidence

On 2026-11-07, the full source suite passed **242 tests with 2 Windows skips**,
including 38 new similarity cases. Generated Pillow variants exercise positive
and negative pair proposals; an exhaustive Hamming oracle checks indexed lookup.
Source changes, malformed inputs, preservation, streamed output, interruption,
publication failure, current limits, and CLI behavior are covered. An isolated
wheel also completed scan/similarity without tagging extras. Receipts and the
scope of each check are recorded in [COMPLETED.md](COMPLETED.md).

Durable pair decisions and group publication are implemented as a separate review
stage. The 2026-11-09 threshold evaluator has generated-fixture evidence for metrics,
manual misses, alias handling, replay, and CLI/graphical parity, recorded in
[COMPLETED.md](COMPLETED.md). No reviewed anime pilot, collection-specific threshold
precision/recall, large-collection benchmark, or downstream training acceptance is established.
