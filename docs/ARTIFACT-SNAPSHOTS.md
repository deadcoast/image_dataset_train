# Reading coherent artifact snapshots

Catalog inspection and trainer status bind the values they report to the exact
artifact bytes they checked. Published exports, indexes and receipts are immutable
evidence. Replacing a file under the same run or receipt ID changes its identity.

## Catalog inspection

```powershell
dataset catalog-info --run 'D:/datasets/export' --json
dataset catalog-query --run 'D:/datasets/export' --limit 20 --json
```

The reader parses captured metadata and derives its identity from those same
bytes. It checks the manifest, frozen provenance and catalog payload together,
and rejects detected changes before returning a summary or query result. Query
results come from the verified database snapshot. Modification times alone are
not sufficient evidence of unchanged content.

Embedded export catalogs remain readable after relocation and without the
original source directory. A standalone metadata index also remains readable
without its original export. Catalog inspection verifies metadata and the index;
use `dataset verify-export --run <export>` to verify packaged media as well.

## Trainer status and saved receipts

```powershell
dataset trainer-status --run 'D:/datasets/export' --config config.toml --json
```

Status checks bind the export metadata, manifest and verified artifacts to one
snapshot. Receipt identity, result and loader log are checked together. A changed
export cannot retain a current passed status from an earlier inspection. A
changed or malformed associated receipt remains visible as invalid or incomplete
history instead of allowing an older pass to hide the problem.

Receipts for different export bytes remain historical; receipts for a different
trainer pin remain separate. Byte-identical relocated exports retain matching
evidence. Inspection requires neither the source images nor a trainer runtime,
and does not execute a new import or training step.

The reviewer's Training import tab uses the same status checks. Its artifact
links are bound to the receipt snapshot offered by that inspection. A receipt
replaced under the same ID must be inspected again before its new artifacts can
be opened. Human dataset acceptance stays separate from import status.

## Recovering from a change

Preserve the changed artifact and its diagnostic. Restore the exact intended
immutable files or select a separately published valid snapshot, then repeat the
read command or refresh Training import. Inspection does not repair, rewrite or
relabel the evidence. Do not edit checksums to suppress a mismatch.

These checks detect drift observed during a read; they do not lock external
writers or guarantee that files remain unchanged after the result is returned.
No new acceptance or model-quality conclusion follows from a successful read.

See [catalogs](DATASET-CATALOG.md), [exports and trainer receipts](EXPORT.md),
[QA](QA.md) and [the active workflow](../TODO.md).
