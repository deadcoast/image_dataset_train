# Human review and group snapshots

The technical workflow now preserves human decisions between runs:

```text
dataset scan -> inventory -> dataset similarity -> pair proposals
                                  -> dataset review -> dataset groups
inventory -> dataset tag -> drafts -> human inspection -> caption overrides
group snapshots -> dataset export -> verified train/validation pairs
```

Review is available through the CLI and the [local graphical reviewer](QA.md).
For CLI review, inspect images in your preferred viewer and use the printed paths.
These commands never write, move, or delete source images or source captions.
`trainime tag` remains a separate workflow that writes missing source sidecars.

## Review commands

Use the published similarity directory printed by `dataset similarity` for `--run`.
Every command also accepts `--config <file>`; use the same configuration throughout.

```powershell
# Read pending pair proposals, with IDs, paths, and Hamming distances.
dataset review --run 'data/runs/<similarity-id>'

# Read pending images, including exact-byte aliases skipped during similarity.
dataset review --run 'data/runs/<similarity-id>' --images

# Save a pair decision using an unambiguous ID prefix printed by the first command.
dataset review --run 'data/runs/<similarity-id>' --pair <pair-prefix> --decision related --reason 'Variants of the same artwork'

# Link related artwork even if pHash did not propose it.
dataset review --run 'data/runs/<similarity-id>' --link 'art.png' 'edits/art.png' --decision related --reason 'Original and edited version'

# Save image eligibility and an optional manual caption independently of drafts.
dataset review --run 'data/runs/<similarity-id>' --image 'art.png' --decision include --caption '1girl, blue hair' --reason 'Inspected image and corrected draft'
dataset review --run 'data/runs/<similarity-id>' --image 'edits/art.png' --decision exclude --reason 'Visible compression damage'

# Inspect one saved image review without changing it.
dataset review --run 'data/runs/<similarity-id>' --image 'art.png'

# Publish a new group snapshot, retaining all eligible occurrences and decisions.
dataset groups --run 'data/runs/<similarity-id>'
```

Pair decisions are `related`, `distinct`, or `unreviewed`. Image decisions are
`include`, `exclude`, or `unreviewed`. Every mutation requires a reason. Setting
`unreviewed` resets that decision while preserving history. Repeating an identical
edit does not create another revision.

Listings default to 20 pending entries. Use `--limit 100` for a larger page or
`--all` to include completed decisions; saving decisions removes them from the
pending view. `--json` exposes the complete returned records and counts, including
intake flags in the image view. `--all` still respects `--limit`.
Saved manual links appear alongside proposals. Resetting either kind to
`unreviewed` returns it to the pending queue and makes group review incomplete.

Use `--caption-file <utf8-file>` instead of `--caption` for longer text. To clear
only the override, use `--image <path> --clear-caption --reason <reason>`.
Changing inclusion does not erase a caption override, and changing a caption
does not implicitly approve the image. Overrides carry the `manual-v1` rule
version. They do not overwrite model drafts or source sidecars; recaption continues
to produce drafts from scores. [Export](EXPORT.md) applies overrides before source
captions and optional model drafts.

## Reviewed labels and subsets

```powershell
dataset review --run 'data/runs/<similarity-id>' --image 'art.png' --label portrait --label outdoors --subset solo --reason 'Inspected composition'
dataset review --run 'data/runs/<similarity-id>' --image 'art.png' --remove-label outdoors --reason 'Corrected background classification'
dataset review --run 'data/runs/<similarity-id>' --unannotated

# Accept this image's unambiguous configured-rule proposal after inspecting it.
dataset review --run 'data/runs/<similarity-id>' --image 'art.png' --subset-from 'data/runs/<caption-id>' --reason 'Reviewed proposed subset'
```

Labels are additive; repeat `--label` or `--remove-label` for multiple changes.
`--subset` replaces the single semantic subset choice. Names are case-folded and
whitespace-normalized. These are explicit human annotations, independent of model
tags, caption text, filenames, and include/exclude decisions. Edits require a
reason, preserve captions, and merge under the same review lock.

`--clear-labels` records a reviewed empty label set; `--clear-subset` records an
explicit choice to leave the image unassigned. Missing annotations on older
records remain unreviewed. `--unannotated` lists included images missing either
reviewed choice. `--images --all --json` exposes the labels, subset, and review flags.
Annotations survive unchanged-source reruns and appear in group snapshots and
export manifests. Changed image bytes do not inherit them.

`--subset-from` accepts a unique proposal from a tagging/recaption run for the
same source inventory and image hash. It records the originating manifest and rule
identity as `subset_origin`. A subsequent manual `--subset` or `--clear-subset`
replaces that origin; unrelated edits preserve it. Recaptioning never changes a
reviewed subset. The graphical **Use proposed subset** action uses this same path.

Publish new groups after edits, then export. Semantic subsets guide split balancing;
they do not create separate trainer directories or change training repeats.

## Storage and content identity

For image previews, caption findings, annotation queues, and category/split
navigation, publish groups and run [`dataset qa`](QA.md). Incomplete group
snapshots are supported. `dataset review-ui --run <qa-id>` provides direct
caption, label, subset, inclusion, and related/distinct pair edits using this same
review store. It also records pilot judgments separately from corrections. Its
Publish tab creates new group snapshots, verified exports, and refreshed QA;
the same operations remain available through the CLI.

`paths.reviews` defaults to `data/reviews`, resolved relative to the configuration
file. A source-specific directory contains `reviews.json` and a writer lock.
The JSON stores current decisions, revision, and reasoned history together and
is replaced atomically under that lock. A listing does not create review files.
Malformed state fails visibly instead of being silently discarded.

Image decisions bind the source directory, relative path, and SHA256. Pair IDs
also bind the pHash policy version. Reviews survive new scan/similarity runs for
unchanged occurrences. Changed bytes or moved paths require new decisions; older
records remain available in history and appear in stale counts. Changing the
pHash radius does not invalidate a decision on the same pair. Prior related links
still affect grouping even when a later run does not propose them.

Saving a decision rechecks the affected image bytes against the inventory.
Publishing groups rechecks every eligible source image, including excluded images.
Changed sources and links introduced since inventory are refused. Listings show
the referenced inventory state; they do not prove the live directory is unchanged.
Keep external writers stopped during review and publication.

## Group rules and publication

Exact-byte aliases always share a group. Human-confirmed related pairs form
connected components: if A relates to B and B relates to C, all three share a
group. All members remain recorded, with their individual inclusion decisions
and caption provenance. No group operation chooses a keeper automatically.

`distinct` means the pair must occupy different groups. A conflicting edit is
rejected before it is saved. Reset the mistaken pair decision to `unreviewed`
before recording a correction; marking identical-byte aliases distinct is not
allowed. Group IDs deterministically bind the member paths and content hashes.

Each invocation publishes a new directory under `paths.runs`:

| File | Contents |
| --- | --- |
| `groups.jsonl` | Groups and every eligible member, intake flags, source/sidecar hashes, review decisions, and caption overrides. |
| `reviews.json` | Review state and history frozen at the captured revision. |
| `summary.json` | Group/image counts, unresolved decisions, conflicts, similarity errors, and completion status. |
| `run.json` | Inventory and similarity references, review revision, artifact hashes, and source-validation boundaries. |

Exit code `0` means every proposed or active manual pair and eligible image has a decision, with
no group conflicts or similarity image errors. Exit code `1` means an incomplete
review snapshot was successfully published; inspect its summary. Exit code `2`
means the command failed. Failed publication may leave a `.pending-groups-`
directory, which is not a completed snapshot.

`review_complete` describes recorded decisions, not dataset quality. These
snapshots always report `training_ready: false`. Sidecar hashes are preserved
from inventory but are not revalidated here. `dataset export` now performs split
assignment, caption selection, source/sidecar validation, and image/caption copying.
`dataset trainer-check` now runs a pinned CPU dataset import and records a separate
receipt. Current checks use generated fixtures; they do not establish acceptance
of an anime collection.
