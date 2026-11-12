# Model selection and saved caption rules

Configured model use checks the requested model name, repository and resolved
full revision against the loaded bundle before inference or threshold selection.
This applies to fetch reuse, tagging, preparation/resume, cache inspection and
managed model recovery. File hashes and label checks still apply. A valid bundle
in the wrong configured slot is a mismatch, even when its own files agree.

Generic bundle inspection remains available without selecting a configured model.
These checks bind declared identity and recorded bytes; they are not publisher
authentication or evidence that a model's predictions are accurate.

## Recovering a model mismatch

Keep the rejected bundle and the diagnostic, which identifies the mismatched
selection fields. Correct the configured selection or restore the exact intended
bundle before resuming. Fetch reuse refuses to relabel or overwrite a foreign
bundle. Managed default-model recovery preserves the rejected directory before
obtaining and checking its replacement. Explicit custom revisions remain supported.

Preparation checkpoints also check their retained model identity against the
job's frozen selection. A completed checkpoint can still be inspected with its
local model unavailable when its saved evidence is sufficient. An interrupted
inference stage needs its matching local bundle to resume. Changing a job's model
identity is not a supported recovery shortcut.

## Interpreting saved scores

Label evaluation, label-review model comparison and caption explanations share
one checked saved-rule contract. It uses the recorded caption version, complete
rules, default threshold, raw vocabulary and recomputed rule digest. It never
loads today's model or fills missing historical rules from today's defaults.

Missing historical evidence or an unsupported caption version is explicitly
unavailable. Evaluation and comparison stop with a precise error; explanations
report why interpretation is unavailable. Malformed present evidence, invalid
current vocabulary and mismatched rule digests are rejected. Use a complete,
verified saved run; preserve the original artifact for diagnosis. Do not edit
its rules merely to make a comparison succeed.

Valid runs retain their existing semantics: raw label predictions use score
strictly greater than the saved cutoff, while caption drop/keep policies remain
separate. Calibration/held-out partitions and assistant filtering are unchanged.
Rejected comparison does not append exposure history, and rejected evaluation
does not publish a result. Saved-score interpretation works without source images
or a local model; the interactive comparison still requires its existing source
preview checks.

Assistant observations remain assistant observations. Source checks, generated
ONNX execution, installed qualification and human dataset acceptance are separate.
The broader SC06 schema-reader proposal remains queued.

See [tagging](TAGGING.md), [label evaluation](LABEL-EVALUATION.md),
[caption explanations](CAPTION-EXPLANATIONS.md) and [the active workflow](../TODO.md).
