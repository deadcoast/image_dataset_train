"use strict";
const $ = id => document.getElementById(id);
let workspace = null, selected = null, matched = [], dirty = false, busy = false;
let loaded = {}, controls = new Map(), imageReady = false;
let imageRequest = 0, imageLoading = false;
const imagePageNonce = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
const text = (id, value) => { $(id).textContent = value; };
function message(value, error = false) {
  text("status", value); $("status").classList.toggle("error", error);
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
function complete(member) {
  return workspace.labels.every(label => workspace.judgments[member.sha256]?.[label]);
}
function currentMember() {
  return !!workspace && !!selected && matched.includes(selected);
}
function canSave() {
  return currentMember() && imageReady && !busy;
}
function canReveal() {
  return canSave() && !dirty && complete(selected) && !!workspace.comparison_models;
}
function lock() {
  const blocked = dirty || busy;
  ["previous", "next", "search", "pendingOnly"].forEach(id => { $(id).disabled = blocked; });
  const position = matched.indexOf(selected);
  $("previous").disabled = blocked || position <= 0;
  $("next").disabled = blocked || position < 0 || position + 1 >= matched.length;
  $("showAll").disabled = blocked;
  $("queue").querySelectorAll("button").forEach(button => { button.disabled = blocked; });
  $("save").disabled = $("saveNext").disabled = !canSave();
  $("reload").disabled = busy;
  text("reload", dirty ? "Discard label edits and reload" : "Reload saved labels");
  $("retryWorkspace").disabled = busy;
  $("retryImage").hidden = !currentMember();
  text("retryImage", imageReady ? "Reload image" : "Retry image");
  $("retryImage").disabled = busy || imageLoading || !currentMember();
  $("reveal").disabled = !canReveal();
  $("editor").querySelectorAll("input,select,textarea").forEach(el => { el.disabled = !canSave(); });
  $("reviewer").disabled = $("reviewerKind").disabled = busy;
}
function queue() {
  const query = $("search").value.toLocaleLowerCase();
  matched = workspace.members.filter(member =>
    (!$('pendingOnly').checked || !complete(member)) &&
    member.paths.some(path => path.toLocaleLowerCase().includes(query)));
  $("queue").replaceChildren();
  for (const member of matched) {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = member.paths[0]; button.setAttribute("aria-current", String(member === selected));
    const status = document.createElement("small");
    const count = Object.keys(workspace.judgments[member.sha256] || {}).length;
    status.textContent = `${count}/${workspace.labels.length} labels saved`;
    button.append(status); button.onclick = () => show(member); $("queue").append(button);
  }
  text("queueStatus", `${matched.length} matching images · ${workspace.members.length} frozen images`);
  const pending = workspace.summary.unreviewed_labels;
  text("progress", `${workspace.members.length * workspace.labels.length - pending}/${workspace.members.length * workspace.labels.length} label judgments saved`);
  text("position", currentMember() ? `Image ${matched.indexOf(selected) + 1} of ${matched.length} matching images` : "No matching image");
  $("emptyQueue").hidden = !!matched.length;
  text("emptyQueueMessage", workspace.members.length ? "No images match these filters. Show all images to continue." : "This frozen workspace contains no images. Reload it after checking the workspace.");
  $("showAll").hidden = !workspace.members.length;
  lock();
}
function changed() {
  dirty = [...controls].some(([label, row]) =>
    row.value.value !== (loaded[label]?.value || "unreviewed") ||
    row.notes.value !== (loaded[label]?.notes || ""));
  lock();
  message(dirty ? "Unsaved label edits. Save or reload before changing images." : "No unsaved changes.");
}
function renderLabels() {
  loaded = workspace.judgments[selected.sha256] || {};
  controls = new Map(); $("editor").replaceChildren();
  for (const name of workspace.labels) {
    const row = document.createElement("section"); row.className = "label-row";
    const head = document.createElement("div"); head.className = "label-head";
    const label = document.createElement("label"); label.className = "label-name"; label.textContent = name;
    const select = document.createElement("select"); select.id = "value-" + controls.size;
    label.htmlFor = select.id;
    for (const [value, title] of [["unreviewed", "Unreviewed"], ["present", "Present"], ["absent", "Absent"], ["uncertain", "Uncertain"]]) {
      const option = document.createElement("option"); option.value = value; option.textContent = title; select.append(option);
    }
    select.value = loaded[name]?.value || "unreviewed";
    head.append(label, select); row.append(head);
    const noteLabel = document.createElement("label"); noteLabel.textContent = "Visual evidence / reason";
    const notes = document.createElement("textarea"); notes.rows = 2; notes.value = loaded[name]?.notes || "";
    notes.setAttribute("aria-label", name + " evidence"); noteLabel.append(notes); row.append(noteLabel);
    const saved = document.createElement("p"); saved.className = "saved";
    const record = loaded[name];
    saved.textContent = record ? `Saved by ${record.reviewer} (${record.reviewer_kind})${record.comparison_exposure?.length ? " · model comparison exposure recorded" : ""}` : "No saved judgment";
    row.append(saved); controls.set(name, {value: select, notes});
    select.onchange = notes.oninput = changed; $("editor").append(row);
  }
  dirty = false;
}
function clearSelection() {
  ++imageRequest; imageReady = imageLoading = false;
  selected = null; loaded = {}; controls = new Map();
  $("editor").replaceChildren();
  $("original").hidden = true; $("original").removeAttribute("src");
  $("labelDetail").hidden = $("comparisonPanel").hidden = true;
  $("comparison").hidden = true; $("comparison").replaceChildren();
  text("position", "No matching image"); text("imageStatus", "");
  message(workspace.members.length ? "No images match these filters. Show all images to continue." : "This frozen workspace contains no images.");
  lock();
}
function loadImage() {
  if (!currentMember() || busy || imageLoading) return;
  const digest = selected.sha256, ticket = ++imageRequest;
  const active = () => ticket === imageRequest && selected?.sha256 === digest && currentMember();
  imageReady = false; imageLoading = true;
  const previous = $("original"); previous.hidden = true; previous.removeAttribute("src");
  text("imageStatus", "Checking and loading the source image…"); lock();
  const image = new Image();
  image.onload = () => {
    if (!active()) return;
    image.onload = image.onerror = null;
    image.id = "original"; image.alt = "Source image: " + selected.paths[0];
    image.className = previous.className; image.hidden = false;
    previous.replaceWith(image);
    imageLoading = false; imageReady = true;
    text("imageStatus", "Source image checked and loaded."); lock();
  };
  image.onerror = () => {
    if (!active()) return;
    imageLoading = imageReady = false;
    text("imageStatus", "Image unavailable or changed. Restore access to the recorded source, then retry. Your edits are preserved."); lock();
  };
  const address = new URL("image/" + digest, location.href);
  address.searchParams.set("preview", imagePageNonce + "-" + ticket);
  image.src = address.href;
}
function show(member) {
  if (dirty || busy || !member || !matched.includes(member)) return;
  ++imageRequest; imageLoading = false;
  selected = member; imageReady = false; renderLabels();
  $("labelDetail").hidden = $("comparisonPanel").hidden = false;
  text("imageTitle", `Image ${workspace.members.indexOf(member) + 1}`);
  text("paths", member.paths.join(" · "));
  $("comparison").replaceChildren(); $("comparison").hidden = true;
  text("comparisonStatus", workspace.comparison_models ? `${workspace.comparison_models} saved model run(s) available after label review.` : "Start label-ui with saved model runs to enable comparison.");
  loadImage();
  message("Labels are saved independently of captions and inclusion decisions."); queue();
}
function move(offset) {
  if (dirty || busy || !matched.length) return;
  const index = matched.indexOf(selected);
  show(matched[Math.max(0, Math.min(matched.length - 1, index + offset))]);
}
function actor() {
  const reviewer = $("reviewer").value.trim(), reviewer_kind = $("reviewerKind").value;
  if (!reviewer || !reviewer_kind) throw new Error("Enter a reviewer name and explicitly choose human or assistant.");
  return {reviewer, reviewer_kind};
}
async function save(next) {
  if (!canSave()) return;
  try {
    const identity = actor(), judgments = [];
    for (const [label, row] of controls) {
      const value = row.value.value, notes = row.notes.value.trim();
      if (value === (loaded[label]?.value || "unreviewed") && notes === (loaded[label]?.notes || "")) continue;
      if (!notes) throw new Error(`Add visual evidence or a reason for ${label}.`);
      judgments.push({label, value, notes, ...identity});
    }
    if (!judgments.length) { message("No changed judgments to save."); if (next) move(1); return; }
    const digest = selected.sha256, nextMember = matched[matched.indexOf(selected) + 1];
    busy = true; lock(); message("Saving this image's judgments together…");
    workspace = await api("api/save", {image: digest, expected_revision: workspace.revision, judgments});
    selected = workspace.members.find(member => member.sha256 === digest);
    renderLabels(); busy = false; queue(); message(`Saved atomically at revision ${workspace.revision}.`);
    const target = (next && nextMember && matched.find(member => member.sha256 === nextMember.sha256)) ||
      (currentMember() ? selected : matched[0]);
    if (!target) clearSelection();
    else if (target !== selected) show(target);
  } catch (error) { message(error.message + " Your edits remain in the form.", true); }
  finally { busy = false; lock(); }
}
$("judgmentForm").onsubmit = event => { event.preventDefault(); return save(false); };
$("saveNext").onclick = () => save(true);
$("previous").onclick = () => move(-1); $("next").onclick = () => move(1);
$("search").oninput = $("pendingOnly").onchange = () => {
  if (dirty || busy || !workspace) return;
  queue();
  if (!matched.includes(selected) && matched.length) show(matched[0]);
  if (!matched.length) clearSelection();
};
$("showAll").onclick = () => {
  if (dirty || busy || !workspace) return;
  $("search").value = ""; $("pendingOnly").checked = false; queue();
  if (matched.length) show(matched[0]); else clearSelection();
};
$("retryImage").onclick = loadImage;
async function reloadWorkspace() {
  if (busy) return;
  try {
    const digest = selected?.sha256;
    busy = true; lock(); message("Loading saved labels…");
    workspace = await api("api/state"); dirty = busy = false;
    $("loading").hidden = $("retryWorkspace").hidden = true; $("reviewPanel").hidden = false;
    queue();
    const member = matched.find(member => member.sha256 === digest) || matched[0];
    if (member) show(member); else clearSelection();
  } catch (error) {
    message(error.message + " Your edits remain in the form.", true);
    if (!workspace) {
      text("loading", error.message); text("progress", "Workspace could not be opened");
      $("retryWorkspace").hidden = false;
    }
  }
  finally { busy = false; lock(); }
}
$("reload").onclick = $("retryWorkspace").onclick = reloadWorkspace;
$("reveal").onclick = async () => {
  if (!canReveal()) return;
  try {
    const identity = actor(); busy = true; lock(); text("comparisonStatus", "Checking saved scores and recording comparison exposure…");
    const result = await api("api/compare", {image: selected.sha256, expected_revision: workspace.revision, ...identity});
    workspace = result.workspace; selected = workspace.members.find(member => member.sha256 === selected.sha256);
    renderLabels(); $("comparison").replaceChildren();
    for (const model of result.models) {
      const card = document.createElement("article"), title = document.createElement("h2");
      title.textContent = model.model.model || model.model.repo || "Saved model"; card.append(title);
      for (const item of model.captions) {
        const path = document.createElement("p"); path.className = "muted path"; path.textContent = item.source_path;
        const caption = document.createElement("p"); caption.className = "caption"; caption.textContent = item.caption || "Empty saved caption";
        card.append(path, caption);
      }
      const table = document.createElement("table"); table.className = "scores"; table.setAttribute("aria-label", "Raw critical-label scores");
      const heading = document.createElement("tr");
      for (const name of ["Label", "Score", "Cutoff", "Prediction"]) { const cell = document.createElement("th"); cell.textContent = name; cell.scope = "col"; heading.append(cell); }
      table.append(heading);
      for (const [name, score] of Object.entries(model.scores)) {
        const row = document.createElement("tr");
        for (const content of [name, score.toPrecision(6), model.thresholds[name].toPrecision(6), score > model.thresholds[name] ? "Present" : "Absent"]) {
          const cell = document.createElement("td"); cell.textContent = content; row.append(cell);
        }
        table.append(row);
      }
      const method = document.createElement("p"); method.className = "muted";
      method.textContent = "Prediction uses score > saved cutoff. Caption rules may omit or add phrases.";
      const run = document.createElement("p"); run.className = "muted path"; run.textContent = model.run;
      card.append(table, method, run); $("comparison").append(card);
    }
    $("comparison").hidden = false; text("comparisonStatus", "Exposure recorded. Scores are model observations, not verified labels."); queue();
  } catch (error) { text("comparisonStatus", error.message); }
  finally { busy = false; lock(); }
};
$("zoom").onclick = () => { const full = $("imageArea").classList.toggle("full"); text("zoom", full ? "Fit image" : "Actual pixels"); };
$("backdrop").onchange = () => {
  const mode = $("backdrop").value; $("imageArea").style.backgroundImage = mode === "checker" ? "" : "none";
  $("imageArea").style.backgroundColor = mode === "dark" ? "#242a33" : "#fff";
};
document.addEventListener("keydown", event => {
  if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); save(false); }
  if (!/INPUT|TEXTAREA|SELECT/.test(event.target.tagName) && !dirty && !busy) {
    if (event.key === "ArrowRight") move(1);
    if (event.key === "ArrowLeft") move(-1);
  }
});
window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
reloadWorkspace();
