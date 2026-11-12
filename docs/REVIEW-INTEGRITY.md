# Judgment integrity and label-save recovery

Review corrections, pilot assessments and critical-label judgments retain their
current state and event history. Reads and saves check those records consistently.
A contradictory history, unsupported record or invalid attribution is an error;
it cannot supply an acceptance summary or be carried into a new saved revision.
The original evidence stays in place.

## Recovering an invalid record

Keep the reported file and its history. Restore an exact known-good copy from a
trusted backup when one is available, then reload the relevant review panel or
retry the command. Do not erase history, change attribution, or reset a revision
number merely to make a validation error disappear. There is no automatic evidence
repair in this feature. If no verified backup exists, retain the record for diagnosis.

Valid historical records remain readable. Missing historical attribution stays
unknown; a valid actor recorded on an old judgment stays attributed even when its
event lacks a newer separate actor field. A present malformed actor is an error.
Reading historical metadata does not require the original images to be online;
operations that change image judgments retain their existing source checks.

## Saving critical labels

The label reviewer's Save, Save + next, form submit and Ctrl+Enter use the same
eligibility rules. An image must be selected in the current matching queue, its
current preview must have loaded successfully, and no save or reload may be busy.
An empty filter or unavailable image cannot submit the previous image through a
shortcut. Late callbacks from an older image cannot enable saving another image.

Use **Retry image** after restoring an unavailable source. It requests the image
again and keeps unsaved label values and evidence notes. **Show all images** clears
an empty filter so browsing can continue. Reloading saved judgments is a separate
action; a failed reload preserves edits. Revision conflicts require reloading the
current saved state before submitting another judgment.

Explicit programmatic label judgments remain supported. A loaded browser image
does not prove visual review, and the application does not authenticate whether a
reviewer is a human. Use the correct explicit reviewer kind: assistant work remains
assistant work. Source validation, generated-fixture tests, installed checks and
human dataset acceptance are separate evidence.

See [label evaluation](LABEL-EVALUATION.md), [review history](REVIEW-HISTORY.md)
and [the active workflow](../TODO.md).
