# Resume browsing a review report

The reviewer remembers image filters, the last selected image and the related-pair
queue position for the exact report. **Saved browsing** in the image sidebar also
lets you name filter combinations and apply them again.

These preferences contain navigation choices only. Captions, unsaved form text,
pair decisions, assessments and human acceptance remain in their existing flows.

## Return to a report

Open the same report with `dataset review-ui --run <qa-run>`. Live review preferences
are saved on this computer and survive restarting the server on a different port.
The report's location and metadata identify its preferences; a new, changed or
relocated report gets a separate identity.
Wait for the saved-status message before closing a live reviewer while it shows
**Saving browsing…**.

The image queue restores its filters and saved image when that image still matches.
When opening a report URL, an explicit image fragment takes priority over the
saved position. If that image does not match the restored filters, the reviewer
clears those filters so the requested image is visible. This applies when the
page loads.

When you first open **Related pairs**, the reviewer restores the saved decision
filter and 20-row page, then looks for the saved pair on that page. If decisions
have moved or removed the pair, it explains the stale position and shows an
available fallback. The previous checkpoint remains saved until you select a
pair; restoration does not search other pages. A failed pair request preserves
the last successful position for retry.

The saved position does not change which tab opens first. It does not imply that
an image or pair has been judged, or that everything before it is complete.

## Save a filter view

1. Set the image filters you want to reuse: finding, label, subset, split,
   decision, search text, pilot selection or group.
2. Open **Saved browsing**, enter a name and choose **Save view**.
3. Select a saved name and choose **Apply view** to restore its filters.

Named views contain filters, not an image cursor or form edits. **Delete view**
removes the selected named combination. Ordinary filter changes and image/pair
navigation update the resume position without creating a named view.
You can keep up to 20 named views, with names up to 80 characters.

**Clear saved resume** clears the remembered image and pair positions while
retaining image filters, the pair decision filter and named views. It leaves the
currently displayed image and forms unchanged. **Reload saved browsing** reads the
latest preferences and applies them when navigation is safe. Save or explicitly
discard unfinished form edits through that form's existing controls before
changing the browsing view.

## Another tab or unavailable storage

Preferences use a separate revision from review decisions. Live reviewer saves
check and update that revision atomically. If another session saves a newer
browsing state, the reviewer reports the conflict instead of overwriting it.
Use **Reload saved browsing** to inspect the latest state before continuing.
A delayed response cannot move a newer image selection or replace unsaved
correction, assessment or pair-form edits.

An unavailable or invalid preference record does not prevent dataset review.
Continue browsing and use **Reload saved browsing** after resolving the reported
storage problem. Invalid saved evidence is preserved rather than silently
replaced. Preference reads and writes never change source images, report artifacts
or saved judgments.

## Standalone reports

Opening `report.html` directly uses browser storage for browsing preferences.
Availability depends on the browser and origin; local-file restrictions, another
browser profile or a changed origin may prevent recovery. The status message
distinguishes this browser-local storage from the live reviewer's saved state.
Standalone reports identify their browsing state by saved report content, so
identical copies can share preferences when opened under the same browser origin.
Conflict detection between standalone browser tabs is best effort; browser storage
does not provide the live server's atomic protection against concurrent writes.
The standalone report remains read-only for dataset corrections and assessments.

See [pilot QA](QA.md), [reviewer recovery](REVIEWER-RECOVERY.md) and
[saved review history](REVIEW-HISTORY.md).
