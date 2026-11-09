# Pilot QA and review navigation

## Snapshot content report

**Snapshot report** is available in both the saved `report.html` and `review-ui`.
Choose **Included images** or **All snapshot images** to inspect reviewed labels and
subsets, model composition, proposed subsets, rating counts, and the top 100 tags.
Counts use source occurrences (including exact-byte aliases); unique hashes and
evidence coverage are shown separately. Exports contain only included occurrences.

Each rating is the unique highest saved score; equal maxima remain ties. Missing
scores remain unavailable. Observed tags include threshold-passing tags omitted by
caption policy; caption-selected tags reflect scored draft selections. Neither
list includes forced phrases, triggers, source-side captions, or manual overrides.
These are model/rule observations, not reviewed accuracy measurements.

Model revision/artifact hashes, runtime providers/options, fallback, preprocessing,
and caption rules come from the matching caption run. Recaptioning retains the
original inference provenance. Group reports join on source path and image hash;
export reports use the frozen caption manifest and metadata without reopening the
source or original tagging run. Older exports without that manifest report missing
observations rather than reconstructing them from captions.

`dataset qa --run <groups-or-export> [--captions <run>] --json` publishes the same
report and prints its complete summary and output path. The hashed `summary.json`
stores these fields under `content`; normal CLI output prints the included counts,
ratings, leading tags, and model/provider information. Existing QA reports remain
readable; generate a new report to add these aggregates.

## Graphical corrections and pilot assessment

```powershell
dataset review-ui --run 'data/runs/<qa-id>'
dataset assessment --run 'data/runs/<qa-id>' --json
```

`review-ui` opens a local browser app and stays running until Ctrl+C. It uses the
configuration captured by QA; `--config <file>` overrides it. `--no-open` prints
the URL without launching a browser, and `--port` selects a loopback port.

**Correct saved review** edits inclusion, caption overrides, labels, and subsets
with a required reason. Typing a caption selects replacement; the caption action
can also remove an override. Label and subset checkboxes make explicit empty
choices possible without changing untouched fields. Saves use the same locked,
hash-bound review store as `dataset review`. Reload saved values after another
editor changes the review revision. Source images and sidecars remain unchanged.

**Caption rule analysis** shows neutral composition, proposed subsets, overlapping
rule matches, missing expected tags, and the rule identity from the selected draft
run. This evidence stays visible when a source or manual caption takes precedence.
**Use proposed subset** fills the correction form; a reason and **Save corrections**
record acceptance and its provenance. Conflicting proposals have no acceptance
button. Existing reviewed choices remain unchanged until an explicit correction.
`qa-list --json` exposes the same analysis; plain output also prints proposals.

**Assess pilot image** judges the saved snapshot displayed above the editor.
Record a verdict, caption judgment, critical-label checks (correct, missing,
spurious, or unchecked), reviewer name, and notes. Additional critical labels
can be added. Progress and per-label checked/error counts cover the selected
pilot only. These are human-entered judgments, not model scores or population
accuracy estimates. Names are attribution, not authenticated identities.

**Record pilot conclusion** saves an explicit accepted/needs-changes/rejected
decision. Acceptance requires every selected pilot image to be accepted, with
its caption and listed critical labels checked as correct. Revising an image
assessment clears the previous conclusion; its history remains. No conclusion
automatically approves an export, trains a model, or establishes collection quality.

Assessments persist under `paths.reviews/pilot-assessments/<qa-hash>/assessment.json`,
including revision history and the exact QA manifest hash. They survive server
restarts and can be inspected with `dataset assessment`. Export QA previews and
assessment remain usable with the source collection offline; corrections need the
original source and similarity inventory. Full-image links serve only recorded,
hash-verified images through the local app.

The snapshot caption, findings, and coverage stay frozen while edits are saved.
Publish new groups after corrections, then create a new QA report or export.
Pilot judgments do not silently carry forward to changed snapshots. The **Related
pairs** and **Publish** tabs complete this workflow in the same reviewer.

## Related pairs and publication

**Related pairs** shows proposed and manually recorded comparisons side by side,
with source-relative paths, pHash distance when available, saved decisions, and
reasons. Filter by unreviewed/related/distinct or view all pairs; pages contain 20
pairs. Save a relationship with a reason, or reset it to unreviewed. The pending
queue advances after saving. **Compare another pair** accepts any two eligible
inventory paths, including relationships the similarity pass did not propose.
CLI and graphical edits share the same revision checks and group-conflict rules.

**Publish** shows the current review revision, unresolved pairs, pending image
decisions, and output directories. Choose:

- **Publish groups + QA** to capture current decisions and open a fresh report.
  Incomplete reviews can be published for further work.
- **Publish groups + verified export** to capture groups, copy and verify training
  pairs, and create QA with the published split assignments. Export requires a
  complete review and uses the same validation as `dataset export`.

Caption draft run, validation percentage, split strategy, seed, resolution, and
training repeats are editable for that publication. These settings do not rewrite
the configuration file. New export metadata retains its caption draft run for
subsequent publication; older exports may need that path supplied explicitly.

Groups and QA are new directories under `paths.runs`; training exports are new
directories under `paths.exports`. Publication runs in the background with progress
and output paths. Successful earlier outputs remain available if a later stage
fails. **Open the new snapshot in reviewer** opens the new QA without restarting
the server. Original reports and source files remain unchanged.

The captured review revision stays fixed even if later edits are saved. Refresh
status before retrying a stale publication request. Job progress survives page
reloads while the server is running; published artifacts persist independently.
Ctrl+C waits for active publication. Pair previews and publication require the
original collection and inventory. Publication does not carry forward pilot
acceptance or run a trainer import; use `dataset trainer-check` for its separate
export-bound receipt.

## Trainer import receipts

For export QA, **Training import** shows export integrity, the latest CPU import
for the current trainer pin, and this report's pilot conclusion separately.
Receipts are discovered under the configuration's `paths.runs`; **Refresh receipts**
picks up checks completed after the reviewer opened. No model runtime is needed
to inspect existing receipts. Group QA directs you to publish an export first.

The history includes completion time, trainer revision, split image/repeat counts,
observed buckets, failures, full result JSON, and the recorded loader log. Export
and receipt artifacts are verified when read. Matching uses both export metadata
and manifest hashes; a relocated byte-identical export can retain its evidence.
A new export does not inherit a predecessor's result. Receipts for different bytes
or trainer pins remain historical, and a newer failed check takes precedence over
an older pass. Damaged evidence is reported without treating it as successful.

Copy the PowerShell or POSIX import command to run `dataset trainer-check` with
the same export and configuration, then refresh. This view does not install or
launch the trainer. `dataset trainer-status --run <export-id> --config <file>` exposes
the same status and history in the CLI; add `--json` for complete records.

CPU import qualifies dataset loading for that exact export and pin. It does not
establish tokenization, GPU execution, model training, or human acceptance. Pilot
judgments remain bound to their QA snapshot, and export qualification flags are
never rewritten to append receipts. Static HTML reports do not refresh receipts;
open them with `dataset review-ui` for this live view.

## Generate or navigate a saved report

```powershell
dataset qa --run 'data/runs/<groups-id>' --captions 'data/runs/<tagging-id>' --sample-size 50
dataset qa --run 'data/exports/<export-id>' --sample-size 50
dataset qa-list --run 'data/runs/<qa-id>' --finding caption_missing
dataset qa-list --run 'data/runs/<qa-id>' --label portrait --split validation --pilot
```

`qa` writes a new report under `paths.runs` and prints its `report.html` path.
Pass `--config <file>` if reviews use a nondefault configuration; copied review
commands retain that configuration so corrections reach the same review store.
Open that file locally. It contains image previews, captions and their origins,
reviewed labels/subsets, findings, group navigation, and clickable split coverage.
Search and filters combine; Previous/Next or left/right arrows navigate matches.
The pilot checkbox narrows the queue to the saved selection. No server, model
download, or browser extension is required.

Group snapshots may have unfinished decisions. Their QA shows **preview** split
assignments for included images, using the current export settings. Unreviewed
and excluded images remain visible but are unassigned. Optional `--captions`
supplies drafts from the same inventory; caption precedence matches export:
manual override, recorded source sidecar, then draft. Unavailable or changed
sources appear as findings. Export QA instead verifies the export first and uses
its frozen images, captions, annotations, and **published** splits; it works with
the original source offline. Export QA covers only exported images.

Findings cover pending decisions/annotations, missing captions, repeated comma
phrases, captions over 1,000 characters, intake flags, selected draft review flags,
unavailable inputs, and rare/missing/mixed split coverage. Explicitly reviewed
empty annotations differ from annotations still awaiting review. Caption words
and characters are reported; these are not tokenizer lengths or accuracy scores.

The default 50-image pilot uses seeded, deterministic selection to cover findings,
labels, subsets, splits, image orientation, and caption origins, then favors new
groups. Excluded images are never sampled. The report retains every input entry
even when the requested pilot is smaller. This is targeted coverage, not a random
sample or a claim of statistical representativeness or human acceptance.
`--seed` changes pilot selection; preview split assignments use `[export]` settings.

The standalone `report.html` is read-only. Use `review-ui` for direct edits.
**Copy review command** opens the selected image's
existing CLI review record; append correction options such as `--caption`,
`--label`, `--subset`, and `--reason` as described in [review](REVIEW.md). Publish
new groups after corrections and regenerate QA/export. A saved report does not
silently follow mutable review state. Source files and review decisions are not
changed by QA.

`qa-list` also accepts `--subset`, `--group`, `--offset`, `--limit`, and `--json`.
It reads the saved report without loading a configuration or the source collection.
`entries.jsonl`, `summary.json`, and `coverage.json` provide machine-readable data;
`previews/` and `report.html` can be moved together for offline inspection.
Full-image links and correction commands retain their original local paths.
