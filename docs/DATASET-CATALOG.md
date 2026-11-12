# Dataset catalogs and portable ingestion

New training exports contain a SQLite catalog and `metadata.jsonl` in each
nonempty split. They are created before publication, included in the export's
checksums, and verified against its authoritative manifest. Moving the complete
export preserves its image paths, captions, metadata and review provenance.
Original images and previous runs are not required to query it.

```powershell
dataset catalog-info --run 'D:/datasets/my-export' --json
dataset catalog-query --run 'D:/datasets/my-export' --split train --limit 20
dataset catalog-query --run 'D:/datasets/my-export' --label portrait
dataset catalog-query --run 'D:/datasets/my-export' --text 'blue hair'
dataset verify-export --run 'D:/datasets/my-export'
```

These commands work from any directory and do not require `config.toml`.
`catalog-query` returns JSON export records, ordered by occurrence ID. Filters
can be combined: `--split`, exact `--group`, explicit annotation `--label`, and
literal caption substring `--text`. Text matching is case-insensitive for ASCII;
it does not treat SQL syntax or `%`/`_` as wildcards. `--limit` accepts 1–1000
(default 100); `--offset` starts at zero. Queries use fixed, parameterized SQL
and read-only SQLite connections. They never change saved reviews or captions.

Catalog reads verify the checksums and consistency of the database, manifest,
ImageFolder metadata and frozen provenance. They report
`verification_scope: "catalog_and_metadata"` and `media_reverified: false`.
Use `verify-export` to rehash image/caption files and check the full exported
dataset. Query results describe the frozen manifest; they do not prove that
the current media bytes are undamaged or that a person accepted the dataset.

## ImageFolder layout

```text
<export>/
  catalog.sqlite
  manifest.jsonl
  train/
    <occurrence-id>.png
    <occurrence-id>.txt
    metadata.jsonl
  validation/
    <occurrence-id>.png
    <occurrence-id>.txt
    metadata.jsonl
  provenance/
  run.json
```

Image extensions may differ, and an empty split has no metadata file. Each
metadata row's `file_name` is relative to its own split directory and `text` is
the exact exported caption, following the
[Hugging Face ImageFolder metadata contract](https://github.com/huggingface/datasets/blob/main/docs/source/image_dataset.mdx).
The existing caption sidecars and Kohya adapters remain available.

In an environment with Hugging Face Datasets installed:

```python
from datasets import load_dataset

dataset = load_dataset("imagefolder", data_dir="D:/datasets/my-export")
print(dataset["train"][0]["text"])
```

The application does not require or install Datasets. An isolated Windows smoke
on 2026-11-09 used Datasets 4.8.5, PyArrow 26.0.1 and Pillow 12.3.0 to load and
decode a moved four-image generated export, offline and outside this checkout,
with its original source unavailable. Captions, splits, hashes, annotations and
model observations matched the manifest and all export files remained unchanged.
The receipt is `.cache/dataset-catalog-smoke/imagefolder-smoke.json`. This qualifies
that loader/fixture combination; collection quality remains separate.

Rows retain occurrence ID, original relative source path and SHA256, exported
image SHA256, caption SHA256, dimensions, split, group and caption origin.
Exports with derivative caption adjustments also retain `source_caption` before
those adjustments; `text` remains the actual training caption. Earlier catalogs
without these fields retain their original format and remain readable.
Variable provenance uses JSON string columns so different splits have stable
tabular types:

| Column | Meaning |
| --- | --- |
| `caption_origin_json` | Existing caption precedence/provenance: saved override, source sidecar or draft. |
| `caption_transforms_json` | Explicit derivative caption adjustments, when the export records them; an empty list is serialized as `"[]"`. |
| `decision_origin_json` | Recorded automatic policy or saved-review origin, when supplied. Missing legacy attribution stays `null`. |
| `review_annotations_json` | Explicit saved labels/subset and their annotation provenance. |
| `model_observations_json` | Separate model/rule analysis captured by the export. These are not ground-truth labels. |
| `preparation_json` | Preparation fields attached to the exported occurrence. |

`--label` searches only the explicit annotation relation. A model prediction in
`model_observations_json` does not become a reviewed label. Retained legacy
reviews do not acquire an invented human actor. Automatic inclusion is a
preparation decision, not semantic ground truth or human acceptance.

SQLite stores complete export records, preserving fields beyond the tabular
ImageFolder projection. Indexes cover split, group, original and exported hashes,
subset, and explicit annotations. The database is derived immutable evidence;
edit reviews through the review APIs and publish a new export for changes.

## Historical exports

Existing exports without catalogs still pass their original verification.
Build a separate index when they need queries:

```powershell
dataset catalog-build --run 'D:/datasets/old-export' --output 'D:/dataset-indexes' --json
dataset catalog-query --run 'D:/dataset-indexes/<catalog-id>' --limit 20
```

The builder first verifies the complete export and creates a new directory. It
copies the export manifest, original run metadata and full frozen provenance,
then writes the same catalog payload. It never edits the original export or
duplicates its media. The resulting index reports `media_packaged: false` and
retains the original export locator and metadata identity.

This standalone index remains queryable if the source export is unavailable,
but it is a metadata/provenance database, not a self-contained training dataset.
Its split metadata refers to media that is not included. Transfer the complete
original export for training. Do not insert the new files into an old immutable
export; doing so invalidates that export's recorded file membership.

Tampered metadata, an index inconsistent with its manifest, unexpected standalone
files, or linked artifact paths cause verification to fail. A rebuild publishes
a new artifact; it does not overwrite damaged evidence. Output directories cannot
overlap the source collection or be placed inside the original export.

## Developer integration

`write_catalog(staging, rows)` writes only into unpublished staging without an
existing `run.json`. It returns the descriptor stored as `run.json.catalog`.
The exporter hashes `catalog.sqlite` and each split's `metadata.jsonl`, and calls
`verify_catalog_payload(directory, descriptor, rows)` during verification.
That verifier reconciles every indexed field, explicit annotation and metadata
row with the export manifest, including when a changed file's checksum was
recomputed.

Public `read_catalog(directory)` and `query_catalog(directory, ...)` need no
configuration or source directory. `build_catalog(export_run, *, output_root)`
creates the standalone historical index. This slice implements the portable
data/query contract in [PREPARATION](PREPARATION.md); it is not a global collection
registry or source-relocation mechanism.
