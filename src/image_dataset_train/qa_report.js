"use strict";

const $ = id => document.getElementById(id);
const data = JSON.parse($("data").textContent);
const filters = ["finding", "label", "subset", "split", "decision"];
const fields = {finding: "findings", label: "labels", subset: "subset", split: "split", decision: "decision"};
let matched = [], current = 0, group = "", generation = 0;
let savedReview = null, assessment = null;
let correctionDirty = false, assessmentDirty = false, conclusionDirty = false;
let imageAssessmentRevision = null, conclusionRevision = null;
let workflowDirty = false;
let workflowBusy = false;
let acceptingSubsetProposal = false;
let reviewRequest = 0, assessmentRequest = 0;
let reviewBusy = false, assessmentBusy = false, conclusionBusy = false;
let browsingPreferences = null, browsingActivity = 0;
const mediaRequests = new Map();
const mediaPageNonce = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
let mediaSequence = 0;

function text(id, value) { $(id).textContent = value; }
function status(id, value, error = false) {
  text(id, value);
  $(id).classList.toggle("error", error);
}
function badge(parent, value, warning = false) {
  const el = document.createElement("span");
  el.className = "badge" + (warning ? " finding" : "");
  el.textContent = value;
  parent.append(el);
}
function options(id, values) {
  [...new Set(values.filter(v => v !== null))].sort().forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    $(id).append(option);
  });
}
filters.forEach(id => options(id, data.entries.flatMap(e => e[fields[id]])));
text("context", (data.summary.split_state === "preview" ? "Preview split assignments" : "Published export splits") +
  " · Snapshot review revision " + data.summary.review_revision + " · " + data.summary.unresolved_pairs + " unresolved pairs");
[["images", data.summary.images], ["pilot images", data.summary.pilot_images], ["groups", data.summary.groups]].forEach(([name, value]) => {
  const span = document.createElement("span"), strong = document.createElement("strong");
  strong.textContent = value;
  span.append(strong, document.createTextNode(name));
  $("metrics").append(span);
});

function browsingBlocked() {
  return correctionDirty || assessmentDirty || conclusionDirty || workflowDirty ||
    reviewBusy || assessmentBusy || conclusionBusy || workflowBusy;
}
function lockNavigation() {
  const dirty = correctionDirty || assessmentDirty || conclusionDirty || workflowDirty;
  const blocked = browsingBlocked();
  document.querySelectorAll("#workflowTabs button").forEach(button => button.disabled = blocked);
  [...filters, "search", "pilot", "reset", "sameGroup", "showAllImages", "emptySnapshot"].forEach(id => $(id).disabled = blocked);
  document.querySelectorAll(".queue button, #coverage button").forEach(button => button.disabled = blocked);
  $("previous").disabled = blocked || !matched.length || current === 0;
  $("next").disabled = blocked || !matched.length || current === matched.length - 1;
  const entry = matched[current];
  $("correctionFields").disabled = $("saveReview").disabled = reviewBusy || !entry || !savedReview;
  $("assessmentFields").disabled = $("saveAssessment").disabled = assessmentBusy || conclusionBusy || imageAssessmentRevision === null || !entry?.pilot;
  $("reloadReview").disabled = reviewBusy || !entry;
  $("reloadAssessment").disabled = assessmentBusy || conclusionBusy || !entry;
  $("conclusionFields").disabled = assessmentBusy || conclusionBusy;
  text("reloadReview", correctionDirty ? "Discard correction edits and reload" : savedReview ? "Reload saved values" : "Retry corrections");
  text("reloadAssessment", assessmentDirty ? "Discard assessment edits and reload" : imageAssessmentRevision !== null ? "Reload assessment" : "Retry assessment");
  text("saveNotice", dirty ? "Unsaved edits — save or reload the edited form before changing images." : "");
  browsingPreferences?.locks();
}

// One explicit media request at a time; callbacks are bound to the displayed identity.
function loadReviewMedia(imageId, messageId, retryId, url, isCurrent, description, retry = false) {
  const request = ++mediaSequence;
  mediaRequests.set(imageId, request);
  const currentRequest = () => mediaRequests.get(imageId) === request && isCurrent();
  const image = $(imageId), message = $(messageId), button = $(retryId);
  image.hidden = true; image.removeAttribute("src"); message.hidden = false;
  button.hidden = !url; button.disabled = !!url;
  if (!url) { message.textContent = "No preview was saved. Open the full image to inspect it."; return; }
  message.textContent = "Loading " + description + "…";
  const address = new URL(url, location.href);
  // Decoded-image reuse can bypass a fresh response even with Cache-Control: no-store.
  address.searchParams.set("retry", `${mediaPageNonce}-${retry ? "retry" : "load"}-${request}`);
  const pending = new Image();
  pending.onload = () => {
    if (!currentRequest()) return;
    pending.onload = pending.onerror = null;
    pending.id = imageId; pending.alt = image.alt; pending.className = image.className;
    pending.hidden = false; image.replaceWith(pending);
    message.hidden = true; button.hidden = true; button.disabled = false;
  };
  pending.onerror = () => {
    if (!currentRequest()) return;
    message.textContent = "Could not load " + description + ". Restore access to the recorded file, then retry.";
    button.disabled = false;
  };
  pending.src = address.href;
}
function loadImagePreview(retry = false) {
  const entry = matched[current], ticket = generation;
  if (!entry) return;
  $("preview").alt = "Preview of " + entry.source_path;
  loadReviewMedia("preview", "noPreview", "retryPreview", entry.preview,
    () => generation === ticket && matched[current]?.id === entry.id, "this preview", retry);
}
$("retryPreview").onclick = () => loadImagePreview(true);
function imageBrowsingFilters() {
  return {...Object.fromEntries(filters.map(id => [id, $(id).value])),
    search: $("search").value, pilot: $("pilot").checked, group};
}
function restoreImageBrowsing(last) {
  filters.forEach(id => $(id).value = last.filters[id]);
  $("search").value = last.filters.search; $("pilot").checked = last.filters.pilot;
  group = last.filters.group; apply(last.image_id, last.position);
}
function matchesImageBrowsing(entry, selected) {
  const query = selected.search.trim().toLocaleLowerCase();
  return (!selected.group || selected.group === entry.group_id) && (!selected.pilot || entry.pilot) &&
    filters.every(id => !selected[id] || (Array.isArray(entry[fields[id]]) ? entry[fields[id]].includes(selected[id]) : entry[fields[id]] === selected[id])) &&
    (!query || [entry.source_path, entry.caption, ...entry.labels, entry.subset || ""].join(" ").toLocaleLowerCase().includes(query));
}
function apply(preferred, position = 0) {
  ++browsingActivity;
  const selected = imageBrowsingFilters();
  matched = data.entries.filter(entry => matchesImageBrowsing(entry, selected));
  const found = matched.findIndex(entry => entry.id === preferred);
  current = found >= 0 ? found : Math.max(0, Math.min(position, matched.length - 1));
  render();
}
function render() {
  ++browsingActivity;
  const entry = matched[current], ticket = ++generation;
  if (!entry) {
    ++reviewRequest; ++assessmentRequest;
    reviewBusy = assessmentBusy = false;
    savedReview = null; imageAssessmentRevision = null;
  }
  if (data.session) { resetCaptionComparison(entry); resetCaptionExplanation(entry); }
  text("position", entry ? `${current + 1} of ${matched.length} matching images` : "0 matching images");
  $("detail").hidden = !entry;
  $("empty").hidden = !!entry;
  text("emptyMessage", data.entries.length ? "No images match the current filters." : "This report contains no images. Inspect the snapshot report for its recorded counts and findings.");
  $("showAllImages").hidden = !data.entries.length;
  $("groupFilter").hidden = !group;
  text("groupFilter", "Showing group " + group.slice(0, 12));
  $("queue").replaceChildren();
  const start = Math.floor(current / 30) * 30;
  matched.slice(start, start + 30).forEach((item, i) => {
    const button = document.createElement("button"), small = document.createElement("small");
    button.className = "item";
    button.setAttribute("aria-current", String(i + start === current));
    button.append(document.createTextNode(item.source_path));
    small.textContent = `${item.split} · ${item.findings.length} findings` + (item.pilot ? " · pilot" : "");
    button.append(small);
    button.onclick = () => { current = start + i; render(); };
    $("queue").append(button);
  });
  lockNavigation();
  browsingPreferences?.captureImage({filters: imageBrowsingFilters(), image_id: entry?.id || null, position: current});
  if (!entry) return;
  history.replaceState(null, "", "#" + entry.id);
  text("path", entry.source_path);
  $("badges").replaceChildren();
  [entry.decision, entry.split, entry.pilot ? "pilot" : null].filter(Boolean).forEach(v => badge($("badges"), v));
  loadImagePreview();
  $("openImage").href = data.session ? "image/" + entry.id : entry.image_uri;
  text("caption", entry.caption || "No usable caption");
  text("captionMeta", `${entry.caption_origin} · ${entry.caption_characters} characters · ${entry.caption_words} words (not tokenizer tokens)`);
  $("facts").replaceChildren();
  [
    ["Labels", entry.labels.join(", ") || (entry.labels_reviewed ? "Reviewed empty" : "Not reviewed")],
    ["Subset", entry.subset || (entry.subset_reviewed ? "Unassigned by review" : "Not reviewed")],
    ["Dimensions", entry.width ? `${entry.width} × ${entry.height}` : "Unavailable"],
    ["Group", entry.group_id.slice(0, 16)], ["Reason", entry.reason || "—"]
  ].forEach(([name, value]) => {
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = name; dd.textContent = value; $("facts").append(dt, dd);
  });
  const analysis = entry.caption_analysis;
  $("ruleAnalysis").hidden = !analysis;
  if (analysis) {
    const proposal = analysis.subset_proposal;
    text("ruleAnalysisText", `Composition: ${analysis.composition} · ` +
      (proposal?.value ? `Proposed subset: ${proposal.value}` :
        proposal?.matches?.length ? `Conflicting subsets: ${proposal.matches.join(", ")}` : "No subset proposed"));
    text("ruleMissingTags", Object.entries(proposal?.missing_tags || {})
      .map(([name, tags]) => `${name}: missing expected ${tags.join(", ")}`).join(" · "));
    text("ruleIdentity", `${analysis.caption_version || "Legacy rules"} · ${analysis.rules_sha256 || "No rule digest recorded"}`);
  }
  $("findings").replaceChildren();
  entry.findings.forEach(v => badge($("findings"), v, true));
  text("errors", entry.errors.join(" "));
  $("command").value = entry.review_commands.powershell;
  text("copyState", "");
  if (data.session) loadForms(entry, ticket);
}
function reset() {
  filters.forEach(id => $(id).value = "");
  $("search").value = "";
  $("pilot").checked = false;
  group = "";
}
filters.forEach(id => $(id).onchange = () => apply());
$("search").oninput = () => apply();
$("pilot").onchange = () => apply();
$("reset").onclick = () => { reset(); apply(); };
$("showAllImages").onclick = () => { reset(); apply(); };
$("emptySnapshot").onclick = () => showPane("content");
$("previous").onclick = () => { if (current > 0) { current--; render(); } };
$("next").onclick = () => { if (current + 1 < matched.length) { current++; render(); } };
$("sameGroup").onclick = () => { const entry = matched[current]; reset(); group = entry.group_id; apply(entry.id); };
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("command").value); text("copyState", "Copied"); }
  catch {
    $("command").focus(); $("command").select();
    text("copyState", "Command selected. Press Ctrl+C to copy.");
  }
};
document.addEventListener("keydown", event => {
  if ($("imagesPane").hidden) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (event.key === "ArrowRight" || event.key === "j") $("next").click();
  if (event.key === "ArrowLeft" || event.key === "k") $("previous").click();
});
data.coverage.strata.forEach(row => {
  const tr = document.createElement("tr"), name = document.createElement("td"), button = document.createElement("button");
  button.textContent = row.kind + ": " + row.name;
  button.onclick = () => {
    reset(); $(row.kind === "label" ? "label" : "subset").value = row.name; apply();
    $("position").scrollIntoView({block: "start"});
  };
  name.append(button); tr.append(name);
  const missing = [];
  if (row.single_group) missing.push("single group");
  if (row.missing_train) missing.push("missing train");
  if (row.missing_validation && data.summary.validation_ratio > 0) missing.push("missing validation");
  [row.groups, row.train_images, row.validation_images + " / " + Number(row.target_validation_images.toFixed(2)),
    missing.join(", ") || (data.summary.validation_ratio > 0 ? "Both splits" : "Validation disabled")].forEach(value => {
    const td = document.createElement("td"); td.textContent = value; tr.append(td);
  });
  $("coverage").append(tr);
});
if (!data.coverage.strata.length) {
  const row = document.createElement("tr"), cell = document.createElement("td");
  cell.colSpan = 5; cell.textContent = "No reviewed categories in this snapshot.";
  row.append(cell); $("coverage").append(row);
}

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Save failed");
  return result;
}

// Draft explanation reads frozen model evidence without touching any editor state.
let captionExplanationRequest = 0, captionExplanationPage = null;
function clearCaptionExplanation() {
  captionExplanationPage = null;
  $("captionExplanationResult").hidden = true;
  ["captionExplanationRows", "captionExplanationSubset", "captionExplanationPhrases"].forEach(id => $(id).replaceChildren());
  ["captionExplanationSummary", "captionExplanationCaption", "captionExplanationIdentity", "captionExplanationPage"].forEach(id => text(id, ""));
  $("previousCaptionTags").disabled = $("nextCaptionTags").disabled = true;
}
function resetCaptionExplanation(entry) {
  ++captionExplanationRequest; clearCaptionExplanation();
  $("captionExplanation").hidden = true;
  $("explainDraftRules").disabled = !entry;
  $("explainDraftRules").setAttribute("aria-expanded", "false");
  $("captionExplanationTag").value = "";
  status("captionExplanationStatus", "");
}
function captionExplanationItem(parent, heading, lines) {
  const item = document.createElement("article"), title = document.createElement("h3");
  title.textContent = heading; item.append(title);
  lines.filter(Boolean).forEach(line => {
    const paragraph = document.createElement("p"); paragraph.textContent = line; item.append(paragraph);
  });
  parent.append(item);
}
function renderCaptionExplanation(result) {
  clearCaptionExplanation();
  if (result.status !== "available") {
    status("captionExplanationStatus", "Draft explanation unavailable: " + result.reason);
    return;
  }
  captionExplanationPage = result;
  $("captionExplanationResult").hidden = false;
  status("captionExplanationStatus", "Saved draft rules inspected. No caption or judgment has changed.");
  const summary = result.summary;
  text("captionExplanationSummary", `${summary.selected} selected · ${summary.omitted} omitted · ${summary.near_threshold} near threshold · ${summary.ratings} rating scores. ` +
    "Relevant tags include observed tags, near-threshold tags and rule inputs. Inspect an exact model tag to check other omissions.");
  text("captionExplanationCaption", result.caption || "The saved draft is empty.");
  text("captionExplanationIdentity", `Image: ${result.identity.source_path}\nImage SHA-256: ${result.identity.sha256}\nSaved run: ${result.run}\nRun SHA-256: ${result.run_sha256}\nRules: ${result.caption_version}\nRule SHA-256: ${result.rules_sha256}`);
  const reasons = {selected: "Selected for the draft", below_or_equal_threshold: "Omitted: score does not exceed the threshold",
    explicit_drop: "Omitted by the drop-tags rule", characters_disabled: "Omitted: character tags are disabled",
    rating_only: "Rating evidence only; never a caption or subset tag"};
  const thresholds = {tag_override: "tag-specific threshold", character_threshold: "character threshold",
    general_threshold: "configured general threshold", default_general_threshold: "saved model default"};
  result.tags.forEach(tag => {
    const cutoff = tag.threshold === null ? null : `Score ${tag.score} ${tag.observed ? ">" : "≤"} ${tag.threshold} (${thresholds[tag.threshold_source] || tag.threshold_source}). Selection requires strict >.`;
    const phrase = tag.phrase_status === "duplicate_phrase" ? "Its displayed phrase was already present; only the first occurrence is emitted." :
      tag.phrase_status === "emitted" ? "Its displayed phrase is in the saved draft." : null;
    captionExplanationItem($("captionExplanationRows"), tag.name, [
      tag.reasons.map(reason => reasons[reason] || reason).join(" · "),
      cutoff || `Rating score ${tag.score}.`,
      tag.near_threshold ? `Near threshold: within the saved margin ${result.uncertainty_margin} (inclusive).` : null,
      tag.observed ? "Observed above threshold; available to subset rules even when omitted from caption text." : null,
      phrase
    ]);
  });
  if (!result.tags.length) text("captionExplanationRows", "No tags in this selection.");
  text("captionExplanationPage", result.total ? `${result.offset + 1}–${result.offset + result.tags.length} of ${result.total} ${result.tag_scope === "requested" ? "requested" : "relevant"} tags` : "0 tags");
  $("previousCaptionTags").disabled = result.offset === 0;
  $("nextCaptionTags").disabled = !result.has_more;
  const list = values => values.length ? values.join(", ") : "none";
  const proposal = result.subset_proposal;
  captionExplanationItem($("captionExplanationSubset"), proposal.value ? `Proposed subset: ${proposal.value}` :
    proposal.matches.length > 1 ? `Overlapping matches: ${proposal.matches.join(", ")}` : "No subset proposed", [
    "Predicates use observed raw tags, including tags dropped from caption text. Reviewed subsets remain separate."
  ]);
  result.subset_rules.forEach(rule => captionExplanationItem($("captionExplanationSubset"), `${rule.name} · ${rule.matched ? "matched" : "not matched"}`, [
    `All required: ${list(rule.all_tags.required)} · ${rule.all_tags.passed ? "passed" : "failed"}. Missing: ${list(rule.all_tags.missing)}.`,
    `Any required: ${list(rule.any_tags.required)} · ${rule.any_tags.passed ? "passed" : "failed"}. Present: ${list(rule.any_tags.present)}.`,
    `None allowed: ${list(rule.none_tags.forbidden)} · ${rule.none_tags.passed ? "passed" : "failed"}. Present: ${list(rule.none_tags.present)}.`,
    `Expected: ${list(rule.expect_tags.expected)} · ${rule.expect_tags.applies ? "applies to this match" : "not applied because the rule did not match"}. Missing: ${list(rule.expect_tags.missing)}.`
  ]));
  if (!result.subset_rules.length) captionExplanationItem($("captionExplanationSubset"), "No subset rules configured", []);
  captionExplanationItem($("captionExplanationPhrases"), "Literal additions", [
    `Trigger: ${result.additions.trigger || "none"}`, `Forced phrases: ${list(result.additions.force_tags)}`,
    "These additions are literal phrases, not model scores. Case-insensitive duplicates keep their first occurrence."
  ]);
  const phrases = document.createElement("ol");
  result.phrases.forEach(phrase => {
    const item = document.createElement("li");
    const origin = {trigger: "Trigger", tag: "Model tag " + phrase.name, forced: "Forced phrase"}[phrase.kind];
    item.textContent = `${origin}: ${phrase.text} · ${phrase.status === "emitted" ? "emitted" : `duplicate of phrase ${phrase.duplicate_of + 1}`}`;
    phrases.append(item);
  });
  $("captionExplanationPhrases").append(phrases);
}
async function loadCaptionExplanation(offset = 0, paging = false) {
  if (!data.session || !matched[current]) return;
  const entry = matched[current], imageGeneration = generation, ticket = ++captionExplanationRequest;
  const requestedTag = $("captionExplanationTag").value.trim(), previous = paging ? captionExplanationPage : null;
  const active = () => ticket === captionExplanationRequest && imageGeneration === generation &&
    matched[current]?.id === entry.id && $("captionExplanationTag").value.trim() === requestedTag;
  $("captionExplanation").hidden = false; $("explainDraftRules").setAttribute("aria-expanded", "true");
  $("previousCaptionTags").disabled = $("nextCaptionTags").disabled = true;
  status("captionExplanationStatus", "Inspecting saved draft rules…");
  const query = new URLSearchParams({limit: "20", offset: String(offset)});
  if (requestedTag) query.set("tag", requestedTag);
  if (previous) query.set("expected_run_sha256", previous.run_sha256);
  try {
    const result = await api("api/caption-explanation/" + entry.id + "?" + query);
    if (!active()) return;
    if (result.image_id !== entry.id || result.identity.source_path !== entry.source_path || result.identity.sha256 !== entry.sha256) {
      throw new Error("Draft explanation no longer matches this image. Inspect again.");
    }
    if (previous && result.status === "available" && (result.run_sha256 !== previous.run_sha256 || result.report_sha256 !== previous.report_sha256)) {
      throw new Error("Saved draft evidence changed. Explain it again from the first page.");
    }
    if (result.status === "available" && (result.offset !== offset || requestedTag && result.tags.some(tag => tag.name !== requestedTag))) {
      throw new Error("Draft explanation does not match this tag selection. Inspect again.");
    }
    renderCaptionExplanation(result);
  } catch (error) {
    if (!active()) return;
    clearCaptionExplanation();
    status("captionExplanationStatus", "Draft explanation unavailable: " + error.message, true);
  }
}
$("explainDraftRules").onclick = () => loadCaptionExplanation();
$("inspectCaptionTag").onclick = () => {
  if ($("captionExplanationTag").value.trim()) return loadCaptionExplanation();
  status("captionExplanationStatus", "Enter an exact model tag, or choose Show relevant tags.");
};
$("showCaptionTags").onclick = () => { $("captionExplanationTag").value = ""; return loadCaptionExplanation(); };
$("previousCaptionTags").onclick = () => captionExplanationPage && loadCaptionExplanation(Math.max(0, captionExplanationPage.offset - captionExplanationPage.limit), true);
$("nextCaptionTags").onclick = () => captionExplanationPage && loadCaptionExplanation(captionExplanationPage.offset + captionExplanationPage.limit, true);
$("captionExplanationTag").oninput = event => {
  event.stopPropagation(); ++captionExplanationRequest; clearCaptionExplanation();
  status("captionExplanationStatus", "Choose Inspect tag to check this exact model tag.");
};
$("captionExplanationTag").onkeydown = event => {
  if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); $("inspectCaptionTag").onclick(); }
};

// Caption comparison only renders inspected evidence; it never replaces form values.
let captionComparisonRequest = 0, captionComparisonTimer = null;
function captionComparisonMessage(message, error = false) {
  status("captionComparisonStatus", message, error);
  status("captionPreviewStatus", message, error);
}
function clearCaptionComparison() {
  ["captionComparisonRevision", "captionComparisonWarnings", "captionComparisonOrigin",
    "captionComparisonEffective", "captionComparisonChangesStatus"].forEach(id => text(id, ""));
  ["captionComparisonCandidates", "captionComparisonAlternatives", "captionComparisonChanges"].forEach(id => $(id).replaceChildren());
  text("captionComparisonAction", "Preview for the selected caption action");
}
function resetCaptionComparison(entry) {
  clearTimeout(captionComparisonTimer); ++captionComparisonRequest;
  clearCaptionComparison();
  $("refreshCaptionComparison").disabled = !entry;
  captionComparisonMessage(entry ? "Loading caption choices…" : "Select an image to compare captions.");
}
function captionComparisonInput() {
  const action = savedReview ? $("captionAction").value : "keep";
  return action === "replace" ? {action, caption: $("editCaption").value} : {action};
}
function captionEvidenceLabel(provenance) {
  if (provenance?.evidence === "source_sidecar") {
    return provenance.source_checked === true ? "Checked source sidecar" : "Recorded source sidecar";
  }
  return {captured_export: "Export snapshot evidence",
    report_draft: "Draft pinned to this report", current_review: "Current saved review",
    proposed_override: "Unsaved replacement"}[provenance?.evidence] || "Recorded caption evidence";
}
function captionIssue(value) {
  return typeof value === "string" ? value : value?.message || "Caption evidence is unavailable.";
}
function captionOutcome(container, title, outcome) {
  const heading = document.createElement("h3"), value = document.createElement("pre"), origin = document.createElement("p");
  heading.textContent = title;
  value.tabIndex = 0;
  value.textContent = outcome.status === "present" ? outcome.text : captionIssue(outcome.error);
  value.className = outcome.status === "present" ? "" : "error";
  origin.className = "muted";
  origin.textContent = `${outcome.status} · ${captionEvidenceLabel(outcome.provenance)}`;
  container.append(heading, origin, value);
}
function renderCaptionComparison(result, baseline) {
  clearCaptionComparison();
  const stale = baseline !== null && baseline !== result.current_revision;
  captionComparisonMessage(stale
    ? `Saved reviews advanced to revision ${result.current_revision}; this form still uses revision ${baseline}. Your edits are preserved. Reload saved values before saving.`
    : "Caption choices inspected. Nothing has been saved.", stale);
  text("captionComparisonRevision", `Snapshot revision ${result.snapshot_revision} · Inspected current revision ${result.current_revision}`);
  text("captionComparisonWarnings", (result.evidence_warnings || []).map(item => `${item.candidate}: ${item.message}`).join("\n"));
  const titles = {override: "Saved manual override", sidecar: "Source sidecar", draft: "Pinned draft"};
  ["override", "sidecar", "draft"].forEach(name => {
    const candidate = result.candidates[name], item = document.createElement("details"), summary = document.createElement("summary");
    item.open = true;
    summary.textContent = `${titles[name]} · ${candidate.status}`;
    const origin = document.createElement("p"), value = document.createElement("pre");
    value.tabIndex = 0;
    origin.className = "muted"; origin.textContent = captionEvidenceLabel(candidate.provenance);
    value.textContent = candidate.text !== null ? candidate.text : candidate.status === "absent" ? "No caption recorded." : captionIssue(candidate.error);
    item.append(summary, origin, value);
    if (candidate.error) {
      const error = document.createElement("p"); error.className = "error";
      error.textContent = captionIssue(candidate.error); item.append(error);
    }
    const provenance = document.createElement("details"), label = document.createElement("summary"), metadata = document.createElement("pre");
    metadata.tabIndex = 0;
    label.textContent = "Exact source and identity"; metadata.textContent = JSON.stringify(candidate.provenance, null, 2);
    provenance.append(label, metadata); item.append(provenance); $("captionComparisonCandidates").append(item);
  });
  const proposed = result.effective.proposed;
  text("captionComparisonAction", {keep: "Keep saved override", clear: "Remove saved override", replace: "Replace saved override"}[result.proposed_action] + " — preview");
  text("captionComparisonOrigin", `${proposed.status} · ${captionEvidenceLabel(proposed.provenance)}`);
  text("captionComparisonEffective", proposed.status === "present" ? proposed.text : captionIssue(proposed.error));
  $("captionComparisonEffective").classList.toggle("error", proposed.status !== "present");
  captionOutcome($("captionComparisonAlternatives"), "Keep the saved override", result.effective.keep);
  captionOutcome($("captionComparisonAlternatives"), "Remove the saved override", result.effective.clear);
  text("captionComparisonChangesStatus", !result.literal_changes_available ? "Changes cannot be compared until both captions are available." :
    result.literal_changes_total ? `${result.literal_changes_total} literal phrase changes${result.literal_changes_truncated ? "; showing the first " + result.literal_changes.length : ""}.` :
    result.literal_text_changed ? "Caption text changed; phrase counts are unchanged." : "No literal phrase additions or removals.");
  result.literal_changes.forEach(change => {
    const item = document.createElement("li");
    item.textContent = `${change.operation === "added" ? "Added" : "Removed"}: ${change.text}${change.text_truncated ? "… (excerpt; see full caption above)" : ""}`;
    $("captionComparisonChanges").append(item);
  });
}
async function loadCaptionComparison() {
  clearTimeout(captionComparisonTimer);
  if (!data.session || !matched[current]) return;
  const entry = matched[current], imageGeneration = generation, ticket = ++captionComparisonRequest;
  const proposed = captionComparisonInput(), requestInput = JSON.stringify(proposed), baseline = savedReview?.revision ?? null;
  const stillCurrent = () => ticket === captionComparisonRequest && imageGeneration === generation &&
    matched[current]?.id === entry.id && requestInput === JSON.stringify(captionComparisonInput()) &&
    baseline === (savedReview?.revision ?? null);
  captionComparisonMessage("Inspecting caption choices…");
  try {
    const result = await api("api/caption-comparison/" + entry.id, proposed.action === "keep" ? undefined : proposed);
    if (!stillCurrent()) return;
    if (result.image_id !== entry.id || result.identity.source_path !== entry.source_path ||
        result.identity.sha256 !== entry.sha256 || result.proposed_action !== proposed.action) {
      throw new Error("Caption comparison no longer matches this image or action. Refresh to inspect again.");
    }
    renderCaptionComparison(result, baseline);
  } catch (error) {
    if (!stillCurrent()) return;
    clearCaptionComparison();
    captionComparisonMessage("Comparison unavailable: " + error.message, true);
  }
}
function scheduleCaptionComparison() {
  clearTimeout(captionComparisonTimer); ++captionComparisonRequest;
  captionComparisonMessage("Updating caption preview…");
  captionComparisonTimer = setTimeout(loadCaptionComparison, 250);
}
$("refreshCaptionComparison").onclick = () => loadCaptionComparison();

function fillReview(entry, record) {
  savedReview = record;
  $("editDecision").value = record.decision;
  $("editCaption").value = record.caption_override ?? entry.caption;
  $("captionAction").value = "keep";
  $("editLabels").value = record.labels.join("\n");
  $("editSubset").value = record.subset || "";
  acceptingSubsetProposal = false;
  $("useSubsetProposal").hidden = !entry.caption_analysis?.subset_proposal?.value;
  $("writeLabels").checked = $("writeSubset").checked = false;
  $("editReason").value = "";
  $("correctionFields").disabled = false;
  correctionDirty = false;
  status("reviewStatus", "Saved review revision " + record.revision +
    (record.caption_override ? " · manual caption override" : " · no manual override"));
  lockNavigation();
  loadCaptionComparison();
}
function addLabelCheck(name, check = "not_checked") {
  const label = document.createElement("label"), select = document.createElement("select");
  label.className = "label-check";
  label.append(document.createTextNode(name)); select.dataset.label = name;
  [["not_checked", "Not checked"], ["correct", "Present / correct"], ["missing", "Present / missing"], ["spurious", "Absent / predicted"], ["absent", "Absent / omitted"]].forEach(([value, title]) => {
    const option = document.createElement("option"); option.value = value; option.textContent = title; select.append(option);
  });
  select.value = check;
  label.append(select); $("labelChecks").append(label);
}
function assessmentKind(record) {
  return record?.reviewer_kind === "human" ? "Human" :
    record?.reviewer_kind === "assistant" ? "Assistant" : "Unknown / legacy attribution";
}
function savedReviewerKind(record) {
  return ["human", "assistant"].includes(record?.reviewer_kind) ? record.reviewer_kind : "";
}
function fillAssessment(entry, result) {
  assessment = result;
  imageAssessmentRevision = result.state.revision;
  const record = result.state.images[entry.id];
  $("assessmentFields").disabled = !entry.pilot;
  $("verdict").value = record?.verdict || "unreviewed";
  $("captionCheck").value = record?.caption_check || "not_checked";
  $("assessmentNotes").value = record?.notes || "";
  $("reviewer").value = record?.reviewer || $("reviewer").value;
  $("reviewerKind").value = record ? savedReviewerKind(record) : $("reviewerKind").value;
  $("labelChecks").replaceChildren();
  const checks = {...Object.fromEntries(entry.labels.map(label => [label, "not_checked"])), ...record?.label_checks};
  Object.entries(checks).sort().forEach(([name, check]) => addLabelCheck(name, check));
  $("newCriticalLabel").value = "";
  status("assessmentStatus", entry.pilot ? (record ? `Saved judgment by ${record.reviewer} · ${assessmentKind(record)}` : "This pilot image has not been assessed.") : "This image is outside the saved pilot selection.");
  assessmentDirty = false;
  showProgress(result.summary);
  lockNavigation();
}
function showProgress(summary) {
  text("pilotProgress", `${summary.assessed_images} of ${summary.pilot_images} assessed · ${summary.remaining_images} remaining`);
  const kinds = summary.reviewer_kinds || {}, accepted = summary.accepted_reviewer_kinds || {};
  text("pilotAttribution", `Assessed judgments: ${kinds.human || 0} human · ${kinds.assistant || 0} assistant · ${kinds.unknown || 0} unknown / legacy attribution.`);
  text("pilotErrors", Object.entries(summary.critical_labels).map(([label, counts]) => `${label}: ${counts.errors} errors / ${counts.checked} checked`).join(" · ") || "No critical labels assessed yet.");
  const metric = value => value == null ? "n/a" : `${(value * 100).toFixed(1)}%`;
  text("pilotMetrics", Object.entries(summary.critical_labels).map(([label, counts]) =>
    `${label}: P ${metric(counts.precision)} · R ${metric(counts.recall)} · TP/FP/FN/TN ${counts.tp}/${counts.fp}/${counts.fn}/${counts.tn}`
  ).join(" · ") || "Per-label precision and recall appear after reviewed checks.");
  const conclusion = summary.conclusion;
  text("pilotConclusion", conclusion ? `${conclusion.verdict} · ${assessmentKind(conclusion)} · ${conclusion.reviewer} · ${conclusion.notes}` : "No pilot conclusion recorded.");
  text("pilotHumanAcceptance", summary.human_accepted ? "Human acceptance recorded for this pilot." :
    `Human acceptance not established. Accepted images: ${accepted.human || 0} human · ${accepted.assistant || 0} assistant · ${accepted.unknown || 0} unknown. An accepted human conclusion and human acceptance of every pilot image are required.`);
  if (!conclusionDirty) {
    conclusionRevision = summary.revision;
    $("conclusion").value = conclusion?.verdict || "needs_changes";
    $("conclusionReviewer").value = conclusion?.reviewer || $("conclusionReviewer").value;
    $("conclusionReviewerKind").value = savedReviewerKind(conclusion);
    $("conclusionNotes").value = conclusion?.notes || "";
  }
}
async function readCorrection(entry = matched[current], imageGeneration = generation) {
  if (!entry || reviewBusy) return;
  const request = ++reviewRequest;
  const active = () => request === reviewRequest && imageGeneration === generation && matched[current]?.id === entry.id;
  reviewBusy = true; lockNavigation(); status("reviewStatus", "Loading saved review…");
  try {
    const record = await api("api/review/" + entry.id);
    if (active()) fillReview(entry, record);
  } catch (error) {
    if (active()) {
      status("reviewStatus", "Corrections unavailable: " + error.message + " Retry after access is restored.", true);
      loadCaptionComparison();
    }
  } finally { if (request === reviewRequest) { reviewBusy = false; lockNavigation(); } }
}
async function readAssessment(entry = matched[current], imageGeneration = generation) {
  if (!entry || assessmentBusy || conclusionBusy) return;
  const request = ++assessmentRequest;
  const active = () => request === assessmentRequest && imageGeneration === generation && matched[current]?.id === entry.id;
  assessmentBusy = true; lockNavigation(); status("assessmentStatus", "Loading assessment…");
  try {
    const result = await api("api/assessment");
    if (active()) fillAssessment(entry, result);
  } catch (error) {
    if (active()) status("assessmentStatus", "Assessment unavailable: " + error.message + " Retry after access is restored.", true);
  } finally { if (request === assessmentRequest) { assessmentBusy = false; lockNavigation(); } }
}
async function loadForms(entry, ticket) {
  ++reviewRequest; ++assessmentRequest;
  reviewBusy = assessmentBusy = false;
  savedReview = null; imageAssessmentRevision = null;
  lockNavigation();
  await Promise.all([readCorrection(entry, ticket), readAssessment(entry, ticket)]);
}
$("correctionForm").oninput = event => {
  if (event.target.id === "editCaption") $("captionAction").value = "replace";
  if (event.target.id === "editLabels") $("writeLabels").checked = true;
  if (event.target.id === "editSubset") { $("writeSubset").checked = true; acceptingSubsetProposal = false; }
  if (["editCaption", "captionAction"].includes(event.target.id)) scheduleCaptionComparison();
  correctionDirty = true; lockNavigation();
};
$("useSubsetProposal").onclick = () => {
  const proposal = matched[current]?.caption_analysis?.subset_proposal?.value;
  if (!proposal) return;
  $("editSubset").value = proposal; $("writeSubset").checked = true;
  acceptingSubsetProposal = correctionDirty = true; lockNavigation();
};
$("assessmentForm").oninput = () => { assessmentDirty = true; lockNavigation(); };
$("conclusionForm").oninput = () => { conclusionDirty = true; lockNavigation(); };
$("addCriticalLabel").onclick = () => {
  const name = $("newCriticalLabel").value.trim().normalize("NFC").toLocaleLowerCase();
  if (!name || [...$("labelChecks").querySelectorAll("select")].some(el => el.dataset.label === name)) return;
  addLabelCheck(name); $("newCriticalLabel").value = "";
  assessmentDirty = true; lockNavigation();
};
$("correctionForm").onsubmit = async event => {
  event.preventDefault();
  if (!savedReview || reviewBusy || !matched[current]) return;
  const entry = matched[current];
  const imageGeneration = generation;
  const changes = {expected_revision: savedReview.revision, reason: $("editReason").value};
  if ($("editDecision").value !== savedReview.decision) changes.decision = $("editDecision").value;
  if ($("captionAction").value === "replace") changes.caption = $("editCaption").value;
  if ($("captionAction").value === "clear") changes.clear_caption = true;
  if ($("writeLabels").checked) {
    changes.clear_labels = true;
    changes.add_labels = $("editLabels").value.split("\n").map(v => v.trim()).filter(Boolean);
  }
  if ($("writeSubset").checked) {
    if (acceptingSubsetProposal) changes.accept_subset_proposal = true;
    else if ($("editSubset").value.trim()) changes.subset = $("editSubset").value;
    else changes.clear_subset = true;
  }
  if (Object.keys(changes).length === 2) { status("reviewStatus", "Choose a correction to save."); return; }
  const request = ++reviewRequest;
  const active = () => request === reviewRequest && imageGeneration === generation && matched[current]?.id === entry.id;
  reviewBusy = true; lockNavigation();
  try {
    const result = await api("api/review/" + entry.id, changes);
    if (!active()) return;
    fillReview(entry, result);
    status("reviewStatus", `Corrections saved · revision ${savedReview.revision}. Snapshot remains unchanged.`);
    document.dispatchEvent(new Event("reviews-saved"));
  } catch (error) { if (active()) status("reviewStatus", error.message, true); }
  finally { if (request === reviewRequest) { reviewBusy = false; lockNavigation(); } }
};
$("reloadReview").onclick = () => readCorrection();
$("reloadAssessment").onclick = () => readAssessment();
$("assessmentForm").onsubmit = async event => {
  event.preventDefault();
  if (!assessment || imageAssessmentRevision === null || assessmentBusy || conclusionBusy || !matched[current]) return;
  const entry = matched[current];
  const imageGeneration = generation, request = ++assessmentRequest;
  const active = () => request === assessmentRequest && imageGeneration === generation && matched[current]?.id === entry.id;
  const payload = {
    image_id: entry.id, expected_revision: imageAssessmentRevision,
    verdict: $("verdict").value, caption_check: $("captionCheck").value,
    reviewer: $("reviewer").value, reviewer_kind: $("reviewerKind").value,
    notes: $("assessmentNotes").value,
    label_checks: Object.fromEntries([...$("labelChecks").querySelectorAll("select")].map(el => [el.dataset.label, el.value]))
  };
  assessmentBusy = true; lockNavigation();
  try {
    const result = await api("api/assessment", payload);
    if (!active()) return;
    fillAssessment(entry, result);
    status("assessmentStatus", `Assessment saved for this snapshot · ${assessmentKind(assessment.state.images[entry.id])}.`);
  } catch (error) { if (active()) status("assessmentStatus", error.message, true); }
  finally { if (request === assessmentRequest) { assessmentBusy = false; lockNavigation(); } }
};
$("conclusionForm").onsubmit = async event => {
  event.preventDefault();
  if (!assessment || conclusionRevision === null || conclusionBusy || assessmentBusy) return;
  conclusionBusy = true; lockNavigation();
  try {
    assessment = await api("api/assessment", {
      expected_revision: conclusionRevision, verdict: $("conclusion").value,
      reviewer: $("conclusionReviewer").value, reviewer_kind: $("conclusionReviewerKind").value,
      notes: $("conclusionNotes").value
    });
    conclusionDirty = false;
    if (!assessmentDirty && matched[current]) fillAssessment(matched[current], assessment);
    else showProgress(assessment.summary);
    status("conclusionStatus", "Pilot conclusion saved.");
  } catch (error) { status("conclusionStatus", error.message, true); }
  finally { conclusionBusy = false; lockNavigation(); }
};
$("reloadConclusion").onclick = async () => {
  if (conclusionBusy || assessmentBusy) return;
  conclusionBusy = true; lockNavigation();
  try {
    const result = await api("api/assessment");
    assessment = result;
    conclusionDirty = false;
    if (!assessmentDirty && matched[current]) fillAssessment(matched[current], result);
    else showProgress(result.summary);
    status("conclusionStatus", "Saved conclusion reloaded.");
  } catch (error) { status("conclusionStatus", error.message, true); }
  finally { conclusionBusy = false; lockNavigation(); }
};
if (data.session) {
  $("live").hidden = $("pilotAssessment").hidden = false;
  if (!data.entries.length) {
    conclusionBusy = true; lockNavigation();
    api("api/assessment").then(result => { assessment = result; showProgress(result.summary); })
      .catch(error => status("conclusionStatus", error.message, true))
      .finally(() => { conclusionBusy = false; lockNavigation(); });
  }
}
document.addEventListener("input", () => { ++browsingActivity; }, true);
document.addEventListener("change", () => { ++browsingActivity; }, true);
browsingPreferences = createReviewBrowsing({data, element: $, blocked: browsingBlocked,
  restoreImage: restoreImageBrowsing, activity: () => browsingActivity});
const initialBrowsing = browsingPreferences.initial();
const linkedImage = data.entries.find(entry => entry.id === location.hash.slice(1));
if (linkedImage) {
  if (!matchesImageBrowsing(linkedImage, initialBrowsing.filters)) initialBrowsing.filters = browsingPreferences.filters();
  initialBrowsing.image_id = linkedImage.id; initialBrowsing.position = 0;
}
restoreImageBrowsing(initialBrowsing);
