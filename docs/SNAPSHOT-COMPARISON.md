# Snapshot comparison

NF06 compares two published group snapshots or two verified exports from the same
source identity. It reads frozen artifacts without scanning the original source
directory. A group snapshot and an export have different membership and caption
semantics, so comparisons across those kinds are rejected.

```powershell
dataset snapshot-compare --before <old-export> --after <new-export> --json
dataset snapshot-compare --before <old-groups> --after <new-groups>
```

Exports receive full `verify-export` validation, including media and provenance.
Groups use the existing checked group-snapshot reader, including preparation
provenance when applicable. Invalid artifacts or different source identities fail
the comparison. Original source images, sidecars and reviews are never changed.

Occurrences match only when both relative source path and original content hash
match. The report separates added and removed occurrences from changed content at
an existing path. A changed hash therefore contributes one removal, one addition
and one `changed_content` diagnostic. These are overlapping descriptions of the
same event, not three independent images.

The deterministic JSON records:

- Membership and unique-content counts, including changes to exact-byte aliases.
- Caption text edits (`caption_changes`) separate from origin, original-text and
  transformation changes (`caption_provenance_changes`). A fresh model run with
  identical caption text changes provenance without inflating the text-edit count.
  Different captions on identical-byte aliases remain separate.
- Explicit annotation, subset and decision provenance changes. No reviewer kind
  or human acceptance is inferred from a saved-review label or a display name.
- Group-ID changes, merges and splits among identities present in both snapshots.
  Added or removed members can also change group IDs without constituting a merge.
- Published train/validation moves and exported media transformations.

For groups, caption changes concern saved overrides only. Effective captions and
export splits are explicitly unavailable; missing overrides are `null`, not empty
caption judgments. Export comparisons use the effective frozen captions, original
caption text and recorded transformations. Predictions are never converted into
reviewed annotations by this command.

The command succeeds with or without differences; differences are data rather than
an error exit. Invalid input returns exit code 2, with structured errors when
`--json` is requested. The read-only command does not require a configuration file.

## Retain an immutable receipt

```powershell
dataset snapshot-compare --before <old-export> --after <new-export> `
  --publish --config config.toml --json

dataset snapshot-compare --before <old-export> --after <new-export> `
  --output <comparison-root> --json
```

`--publish` creates a new directory under configured runs. `--output` selects an
explicit receipt root instead. Outputs cannot be written inside either snapshot
or overlap the source tree; the usual runs parent is allowed, creating a sibling
artifact. Existing snapshots and receipts are not overwritten.

The receipt stores `comparison.json`, checked copies of both input `run.json`
files, and the normalized records used for comparison. Its own `run.json` hashes
every file and records the implementation identity. Training media are not copied.
`read_comparison()` verifies those hashes and replays the differences from the
captured records without either input snapshot being available. This preserves
the recorded verification and comparison evidence; rechecking original export
media still requires the exports and `verify-export`.

Python callers can use `compare_snapshots(before, after)` for a result dictionary,
`publish_comparison(before, after, output_root=...)` for a new receipt and that
dictionary, or `read_comparison(directory)` for a verified saved receipt. This
mechanism audits changes; choosing corrections or accepting dataset quality
remains a separately attributed review action.
