# TODO

Updated **2026-11-09**. Only unfinished work is tracked here. Completed steps,
verification results and historical qualification boundaries are in
[docs/COMPLETED.md](docs/COMPLETED.md).

Follow [PLAN.md's work order](docs/PLAN.md#work-order-and-completion-boundaries).
The earliest open milestone is **M2**. M2–M4 need an explicitly selected collection
and reviewed examples; M5 representative export acceptance follows that pilot,
and M6 collection execution follows correction of its findings. Do not search
unrelated directories for images.

## Remaining work against the existing plan

### M2 — similarity calibration and collection performance

- [ ] Select a representative local pilot and review positive/negative anime
  artwork pairs, including known related variants outside the proposal radius.
- [ ] Evaluate saved judgments to calibrate the pHash threshold and measure
  false-match/missed-match behavior; verify that unique variants are preserved.
- [ ] Measure similarity time, disk use and throughput at the intended collection
  size, retaining the input identities, settings and results.

Acceptance: representative pair behavior and expected-scale performance, as
specified in [PLAN section 2](docs/PLAN.md#2-deduplication-and-related-image-groups)
and [the similarity contract](docs/SIMILARITY.md).

### M3 — tagging quality, comparison and runtime qualification

- [ ] Compare SwinV2 and EVA02 on the same reviewed pilot; qualify the alternate
  WD weights used in that comparison.
- [ ] Measure per-label precision/recall, composition errors and actual anime
  caption accuracy on the selected collection.
- [ ] Measure tagging throughput and memory use on that collection.
- [ ] Calibrate thresholds from reviewed evidence and check them on held-out images.
- [ ] Qualify physical GPU inference if using CUDA; record actual providers,
  runtime compatibility, performance and observed behavior.
- [ ] Qualify other selectable WD weights before making local quality claims for
  them; published benchmarks are not collection acceptance.

Acceptance: collection-specific evidence and separately scoped model/provider
qualification. See [PLAN section 3](docs/PLAN.md#3-local-tagging) and
[docs/TAGGING.md](docs/TAGGING.md).

### M4 — representative caption and subset acceptance

- [ ] Review nonempty pilot captions against their images and correct inaccurate
  or missing critical labels.
- [ ] Assess configured subset rules, composition/conflict findings and caption
  policy for suitability on the representative pilot.
- [ ] Verify the corrected pilot retains manual overrides and makes disagreements,
  exclusions and accepted subset decisions visible.
- [ ] Record the pilot's human judgments and conclusion for the corresponding
  report; generated fixture judgments do not supply this acceptance.

Acceptance: accurate reviewed pilot captions and suitable rules, following
[PLAN section 4](docs/PLAN.md#4-caption-normalization-and-review).

### M5 — representative export and trainer import acceptance

- [ ] Publish an export from the representative reviewed M2–M4 inputs and verify
  membership, nonempty captions, unique filenames and absence of group/byte leakage
  or unresolved blocking decisions.
- [ ] Run the pinned trainer import on that export and check actual caption,
  repeat and bucket behavior; retain its export-bound receipt.
- [ ] Address representative export/import findings and record acceptance of the
  resulting image/caption dataset.

Acceptance: the selected pilot's verified export and actual pinned import, following
[PLAN section 5](docs/PLAN.md#5-split-export-and-trainer-adapters) and
[docs/EXPORT.md](docs/EXPORT.md).

### M6 — full-collection execution and recorded acceptance

- [ ] Process the explicitly selected collection and record real-image readability,
  size distribution, caption collisions and duplicate rate.
- [ ] Reconcile final intake, review, snapshot, tagging, split and export counts
  and identities; resolve unexplained discrepancies.
- [ ] Record actual batch processing time and disk measurements with their scope
  and unavailable measurements stated.
- [ ] Address pilot findings, publish the corrected dataset/QA artifacts and record
  user review and dataset acceptance.

Acceptance: a qualified collection run with reconciled counts, measured resources,
corrected pilot problems and recorded human review, following
[PLAN section 6](docs/PLAN.md#6-report-and-qa).

## Outstanding interface and platform qualification

- [ ] Complete rendered-layout acceptance for reviewer panels whose recorded
  milestone checks lacked visual evidence; keep functional browser checks separate
  from visual and human usability acceptance.
- [ ] Requalify the installed command when delivering later source changes through
  an installation; technical-pipeline checks do not automatically qualify that build.

These checks must preserve the separate Trainime menu, preview, source-caption,
backup and recovery contracts in [docs/TRAINIME.md](docs/TRAINIME.md) and
[docs/INSTALLATION.md](docs/INSTALLATION.md).

## Conditional extensions — not the next required milestones

- [ ] Consider normalized-pixel matching as a later extension; evaluate embeddings
  only if representative pHash misses justify them (PLAN section 2).
- [ ] Evaluate a separate Camie backend only if selected after baseline comparison;
  it is not a drop-in WD model or the next required integration (docs/TAGGING.md).
- [ ] Add natural-language caption adapters and tokenizer/truncation checks only
  for an actual target profile (PLAN design decision 6 and section 6).
- [ ] Qualify ARM64 native installation or other operating-system installer flows
  if extending supported deployment beyond the qualified Windows x64 scope.

ComfyUI inspection remains optional. Model training and training-quality evaluation
belong to the downstream trainer, outside this preparation backlog.
[docs/IDENTIFIED.md](docs/IDENTIFIED.md) contains additional improvement proposals;
they are not automatically approved TODO requirements.
