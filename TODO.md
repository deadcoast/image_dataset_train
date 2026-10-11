# Implementation status

## Current boundary

M1 is implemented; verification is in progress. No real dataset has been scanned.
No model has been downloaded, no inference has run, and no training export exists.
`PLAN.md` is the working design. `OVERVIEW.md` remains historical source material.

## M1: inventory and validation

- [x] Package layout, Python 3.12, `uv`, CLI, strict TOML configuration.
- [x] Read-only inventory with complete SHA256 hashes and existing sidecar records.
- [x] Decode checks, frame checks, EXIF dimensions, alpha/mode/ICC and size flags.
- [x] Exact duplicate references and caption-conflict detection.
- [x] New report directory per run, deterministic manifest, atomic publication.
- [ ] Preservation/failure/rerun tests, lint, format, package build, installed CLI smoke test.

## Next implementation

1. M2: pHash pair proposals and reviewable related-image groups; no automatic moves.
2. M3: pinned WD model fetch, correct preprocessing/category handling, raw score cache.
3. M4: deterministic normalization and durable per-image review overrides.
4. M5: group-aware splitting, verified image/caption exports, Kohya adapter.
5. M6: pilot qualification, then full collection run and QA.

## Pending evidence

- Real images: readability, size distribution, caption collisions, duplicate rate.
- Similarity: calibrated false-match/missed-match behavior on anime artwork.
- Tagging: reference parity, throughput, and accuracy on this collection.
- Export: pinned trainer import and repeat/bucket behavior.
- Dataset acceptance: image/caption review; automated tests cannot establish it.
