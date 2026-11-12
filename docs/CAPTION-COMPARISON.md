# Compare captions before saving

Open a report in the local reviewer and expand **Compare caption choices** inside
**Correct saved review**. Compare the current manual override, source sidecar and
draft pinned to that report before choosing a correction.

The comparison uses the same source-caption precedence as export:

1. A saved manual override wins when present.
2. Otherwise, a recorded source sidecar wins.
3. Otherwise, use the draft bound to the report.

It never searches for a newer tagging run. Editing a loose generated draft does
not create a manual override.

Choose **Explain draft rules** to inspect why the pinned model draft included or
omitted a raw tag, how subset predicates matched, and which literal phrases were
added or deduplicated. See [saved draft explanations](CAPTION-EXPLANATIONS.md).
The original saved score run is required; effective caption precedence remains the
same even when an explanation is unavailable.

## Preview a correction

The existing **Caption action** control chooses what will be saved:

- **Keep saved override** leaves the saved override as it is.
- **Save this caption as override** previews your edited caption using the exporter's
  normalization, including combining lines into one caption.
- **Remove override; use source/draft** previews the applicable fallback.

The comparison shows the effective source caption and literal phrase differences.
Phrase changes describe text, not semantic accuracy or tokenizer counts. Full
candidate values remain available for inspection and selection.

The **Snapshot caption** remains historical. Export may have adjusted it for a
specific derived image; the comparison does not predict those later adjustments.
Publishing a new snapshot remains a separate action.

Refreshing comparison does not replace your unsaved caption, labels, subset or
assessment. If another process changes saved reviews, reload saved values before
saving against that new revision. Existing reason and revision checks still apply.

## Understand candidate evidence

Export reports compare their captured sidecar and draft provenance. Those values
can remain available with the original source directory offline; they are labeled
as frozen evidence. Group reports inspect the sidecar recorded in their inventory
and use their exact pinned draft manifest.
The correction form can be unavailable while the source is offline. After restoring
the source, use its reload control to load saved values again. Comparison refresh
only refreshes caption evidence and preserves the form's current state. See
[reviewer recovery](REVIEWER-RECOVERY.md) for empty queues and unavailable previews.

**Absent**, **invalid** and **unavailable** mean different things. An absent
sidecar permits draft fallback. An empty or invalid sidecar cannot silently fall
through to a draft. Missing or oversized evidence is unavailable; changed or
inconsistent evidence is invalid. A valid
override may win text resolution while missing sidecar evidence can still prevent
publication. The view does not certify that source images are present or valid.

Comparison reads metadata and caption text, with no image decoding or
inference. Candidate text is limited to 1 MiB; larger values are explicitly
unavailable rather than silently shortened. Phrase differences show up to 40
additions/removals, with up to 240 characters per phrase and explicit truncation.
Inspection does not write sidecars, drafts, saved reviews or assessments.
New snapshot/draft metadata reads are limited to 64 MiB per artifact. Existing
inventory and whole-document review-history loading costs are unchanged; this
feature does not establish a global dataset or history-size limit.

Use **Save corrections** to save an intentional correction, then the existing
**Publish** pane when ready. Assistant assessments remain assistant evidence;
this view never records or transfers human acceptance.

See [reviewing images](REVIEW.md), [review snapshot changes](REVIEW-CHANGES.md),
[publication](PUBLICATION.md) and [export](EXPORT.md).
