"use strict";

const $ = id => document.getElementById(id);
const data = JSON.parse($("data").textContent);
const filters = ["finding", "label", "subset", "split", "decision"];
const fields = {finding: "findings", label: "labels", subset: "subset", split: "split", decision: "decision"};
let matched = [], current = 0, group = "", generation = 0;
let savedReview = null, assessment = null;
let correctionDirty = false, assessmentDirty = false;
let workflowDirty = false;
let acceptingSubsetProposal = false;

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

function lockNavigation() {
  const dirty = correctionDirty || assessmentDirty || workflowDirty;
  document.querySelectorAll("#workflowTabs button").forEach(button => button.disabled = dirty);
  [...filters, "search", "pilot", "reset", "sameGroup"].forEach(id => $(id).disabled = dirty);
  document.querySelectorAll(".queue button, #coverage button").forEach(button => button.disabled = dirty);
  $("previous").disabled = dirty || !matched.length || current === 0;
  $("next").disabled = dirty || !matched.length || current === matched.length - 1;
  text("saveNotice", dirty ? "Unsaved edits — save or reload the edited form before changing images." : "");
}
function apply(preferred) {
  const query = $("search").value.trim().toLocaleLowerCase();
  matched = data.entries.filter(e => (!group || group === e.group_id) && (!$("pilot").checked || e.pilot) &&
    filters.every(id => !$(id).value || (Array.isArray(e[fields[id]]) ? e[fields[id]].includes($(id).value) : e[fields[id]] === $(id).value)) &&
    (!query || [e.source_path, e.caption, ...e.labels, e.subset || ""].join(" ").toLocaleLowerCase().includes(query)));
  current = Math.max(0, matched.findIndex(e => e.id === preferred));
  render();
}
function render() {
  const entry = matched[current], ticket = ++generation;
  text("position", entry ? `${current + 1} of ${matched.length} matching images` : "0 matching images");
  $("detail").hidden = !entry;
  $("empty").hidden = !!entry;
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
  if (!entry) return;
  history.replaceState(null, "", "#" + entry.id);
  text("path", entry.source_path);
  $("badges").replaceChildren();
  [entry.decision, entry.split, entry.pilot ? "pilot" : null].filter(Boolean).forEach(v => badge($("badges"), v));
  $("preview").hidden = !entry.preview;
  $("noPreview").hidden = !!entry.preview;
  if (entry.preview) {
    $("preview").src = entry.preview;
    $("preview").alt = "Preview of " + entry.source_path;
  } else $("preview").removeAttribute("src");
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
}
function addLabelCheck(name, check = "not_checked") {
  const label = document.createElement("label"), select = document.createElement("select");
  label.className = "label-check";
  label.append(document.createTextNode(name)); select.dataset.label = name;
  [["not_checked", "Not checked"], ["correct", "Correct"], ["missing", "Missing"], ["spurious", "Spurious"]].forEach(([value, title]) => {
    const option = document.createElement("option"); option.value = value; option.textContent = title; select.append(option);
  });
  select.value = check;
  label.append(select); $("labelChecks").append(label);
}
function fillAssessment(entry, result) {
  assessment = result;
  const record = result.state.images[entry.id];
  $("assessmentFields").disabled = !entry.pilot;
  $("verdict").value = record?.verdict || "unreviewed";
  $("captionCheck").value = record?.caption_check || "not_checked";
  $("assessmentNotes").value = record?.notes || "";
  $("reviewer").value = record?.reviewer || $("reviewer").value;
  $("labelChecks").replaceChildren();
  const checks = {...Object.fromEntries(entry.labels.map(label => [label, "not_checked"])), ...record?.label_checks};
  Object.entries(checks).sort().forEach(([name, check]) => addLabelCheck(name, check));
  $("newCriticalLabel").value = "";
  status("assessmentStatus", entry.pilot ? (record ? "Saved judgment by " + record.reviewer : "This pilot image has not been assessed.") : "This image is outside the saved pilot selection.");
  assessmentDirty = false;
  showProgress(result.summary);
  lockNavigation();
}
function showProgress(summary) {
  text("pilotProgress", `${summary.assessed_images} of ${summary.pilot_images} assessed · ${summary.remaining_images} remaining`);
  text("pilotErrors", Object.entries(summary.critical_labels).map(([label, counts]) => `${label}: ${counts.errors} errors / ${counts.checked} checked`).join(" · ") || "No critical labels assessed yet.");
  const conclusion = summary.conclusion;
  text("pilotConclusion", conclusion ? `${conclusion.verdict} · ${conclusion.reviewer} · ${conclusion.notes}` : "No pilot conclusion recorded.");
}
async function loadForms(entry, ticket) {
  $("correctionFields").disabled = $("assessmentFields").disabled = true;
  savedReview = null;
  status("reviewStatus", "Loading saved review…"); status("assessmentStatus", "Loading assessment…");
  const results = await Promise.allSettled([api("api/review/" + entry.id), api("api/assessment")]);
  if (ticket !== generation) return;
  if (results[0].status === "fulfilled") fillReview(entry, results[0].value);
  else status("reviewStatus", "Corrections unavailable: " + results[0].reason.message, true);
  if (results[1].status === "fulfilled") fillAssessment(entry, results[1].value);
  else status("assessmentStatus", results[1].reason.message, true);
}
$("correctionForm").oninput = event => {
  if (event.target.id === "editCaption") $("captionAction").value = "replace";
  if (event.target.id === "editLabels") $("writeLabels").checked = true;
  if (event.target.id === "editSubset") { $("writeSubset").checked = true; acceptingSubsetProposal = false; }
  correctionDirty = true; lockNavigation();
};
$("useSubsetProposal").onclick = () => {
  const proposal = matched[current]?.caption_analysis?.subset_proposal?.value;
  if (!proposal) return;
  $("editSubset").value = proposal; $("writeSubset").checked = true;
  acceptingSubsetProposal = correctionDirty = true; lockNavigation();
};
$("assessmentForm").oninput = () => { assessmentDirty = true; lockNavigation(); };
$("addCriticalLabel").onclick = () => {
  const name = $("newCriticalLabel").value.trim().normalize("NFC").toLocaleLowerCase();
  if (!name || [...$("labelChecks").querySelectorAll("select")].some(el => el.dataset.label === name)) return;
  addLabelCheck(name); $("newCriticalLabel").value = "";
  assessmentDirty = true; lockNavigation();
};
$("correctionForm").onsubmit = async event => {
  event.preventDefault();
  if (!savedReview) return;
  const entry = matched[current];
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
  $("correctionFields").disabled = true;
  try {
    fillReview(entry, await api("api/review/" + entry.id, changes));
    status("reviewStatus", `Corrections saved · revision ${savedReview.revision}. Snapshot remains unchanged.`);
  } catch (error) { status("reviewStatus", error.message, true); }
  finally { $("correctionFields").disabled = false; }
};
$("reloadReview").onclick = async () => {
  const entry = matched[current], ticket = generation;
  try {
    const record = await api("api/review/" + entry.id);
    if (ticket === generation) fillReview(entry, record);
  } catch (error) {
    if (ticket === generation) status("reviewStatus", error.message, true);
  }
};
$("reloadAssessment").onclick = async () => {
  const entry = matched[current], ticket = generation;
  try {
    const result = await api("api/assessment");
    if (ticket === generation) fillAssessment(entry, result);
  } catch (error) {
    if (ticket === generation) status("assessmentStatus", error.message, true);
  }
};
$("assessmentForm").onsubmit = async event => {
  event.preventDefault();
  if (!assessment) return;
  const entry = matched[current];
  const payload = {
    image_id: entry.id, expected_revision: assessment.state.revision,
    verdict: $("verdict").value, caption_check: $("captionCheck").value,
    reviewer: $("reviewer").value, notes: $("assessmentNotes").value,
    label_checks: Object.fromEntries([...$("labelChecks").querySelectorAll("select")].map(el => [el.dataset.label, el.value]))
  };
  $("assessmentFields").disabled = true;
  try {
    fillAssessment(entry, await api("api/assessment", payload));
    status("assessmentStatus", "Assessment saved for this snapshot.");
  } catch (error) { status("assessmentStatus", error.message, true); }
  finally { $("assessmentFields").disabled = false; }
};
$("conclusionForm").onsubmit = async event => {
  event.preventDefault();
  if (!assessment) return;
  try {
    assessment = await api("api/assessment", {
      expected_revision: assessment.state.revision, verdict: $("conclusion").value,
      reviewer: $("conclusionReviewer").value, notes: $("conclusionNotes").value
    });
    showProgress(assessment.summary); status("conclusionStatus", "Pilot conclusion saved.");
  } catch (error) { status("conclusionStatus", error.message, true); }
};
if (data.session) {
  $("live").hidden = $("pilotAssessment").hidden = false;
  if (!data.entries.length) {
    api("api/assessment").then(result => { assessment = result; showProgress(result.summary); })
      .catch(error => status("conclusionStatus", error.message, true));
  }
}
apply(location.hash.slice(1));
