"use strict";

// Browsing preferences contain only navigation state; never copy an editor form.
function createReviewBrowsing({data, element, blocked, restoreImage, activity}) {
  const fields = {finding: "findings", label: "labels", subset: "subset", split: "split", decision: "decision"};
  const names = Object.keys(fields), filterKeys = [...names, "search", "pilot", "group"];
  const reportID = data.browsing?.report_id;
  const storageKey = "trainime.review-browsing.v1:" + reportID;
  const clone = value => JSON.parse(JSON.stringify(value));
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
  const equal = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
  const emptyFilters = () => ({finding: "", label: "", subset: "", split: "", decision: "", search: "", pilot: false, group: ""});
  const empty = () => ({schema_version: 1, report_id: reportID, revision: 0,
    last: {filters: emptyFilters(), image_id: null, position: 0,
      pair: {decision: "unreviewed", offset: 0, pair_id: null}}, views: []});
  const identifier = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
  const object = (value, keys) => {
    if (!value || Array.isArray(value) || typeof value !== "object" ||
        !equal(Object.keys(value).sort(), [...keys].sort())) throw new Error("Unexpected saved browsing fields.");
  };
  const integer = (value, maximum = 1000000000) => {
    if (!Number.isInteger(value) || value < 0 || value > maximum) throw new Error("Invalid saved browsing position or revision.");
  };
  const string = (value, maximum) => {
    if (typeof value !== "string" || [...value].length > maximum || /\p{C}/u.test(value)) {
      throw new Error("Invalid or oversized saved browsing text.");
    }
  };
  const values = Object.fromEntries(names.map(name => [name, new Set(data.entries.flatMap(entry => {
    const value = entry[fields[name]]; return Array.isArray(value) ? value : [value];
  }))]));
  const images = new Set(data.entries.map(entry => entry.id)), groups = new Set(data.entries.map(entry => entry.group_id));
  const validateFilters = filters => {
    object(filters, filterKeys);
    names.forEach(name => {
      string(filters[name], 4096);
      if (filters[name] && !values[name].has(filters[name])) throw new Error("Saved filter is absent from this report: " + name);
    });
    string(filters.search, 512); string(filters.group, 4096);
    if (typeof filters.pilot !== "boolean" || filters.group && !groups.has(filters.group)) {
      throw new Error("Invalid saved pilot or group filter.");
    }
  };
  // Match the backend's bounded, sorted, indented UTF-8 JSON representation.
  const storedJSON = value => JSON.stringify(canonical(value), null, 2) + "\n";
  const validate = value => {
    object(value, ["schema_version", "report_id", "revision", "last", "views"]);
    if (value.schema_version !== 1 || value.report_id !== reportID) throw new Error("Saved browsing belongs to another report or version.");
    integer(value.revision); object(value.last, ["filters", "image_id", "position", "pair"]);
    validateFilters(value.last.filters);
    if (value.last.image_id !== null && !images.has(value.last.image_id)) throw new Error("Saved image is absent from this report.");
    integer(value.last.position, Math.max(0, images.size - 1));
    const pair = value.last.pair;
    object(pair, ["decision", "offset", "pair_id"]); integer(pair.offset);
    if (!["all", "unreviewed", "related", "distinct"].includes(pair.decision) || pair.offset % 20 ||
        pair.pair_id !== null && !identifier(pair.pair_id)) throw new Error("Invalid saved pair queue.");
    if (!Array.isArray(value.views) || value.views.length > 20) throw new Error("At most 20 saved views are supported.");
    const viewNames = new Set();
    value.views.forEach(view => {
      object(view, ["name", "filters"]); string(view.name, 80);
      if (!view.name || view.name !== view.name.trim().normalize("NFC") || viewNames.has(view.name)) throw new Error("Invalid or repeated saved view name.");
      viewNames.add(view.name); validateFilters(view.filters);
    });
    if (new TextEncoder().encode(storedJSON(value)).length > 65536) throw new Error("Saved browsing exceeds 64 KiB.");
    return clone(value);
  };
  let desired = empty(), base = empty(), available = identifier(reportID), paused = false;
  let memoryOnly = false, writing = false, reading = false, timer = null, changes = 0;
  let pairRestore = () => {}, localStorageObject = null;
  const scope = data.session ? "Saved on this computer for this report." : "Saved in this browser for this report; storage depends on the browser origin.";
  const message = (value, error = false) => {
    element("browsingStatus").textContent = value;
    element("browsingStatus").classList.toggle("error", error);
  };
  const viewList = () => {
    const selected = element("savedBrowsingViews").value;
    element("savedBrowsingViews").replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = ""; placeholder.textContent = "Choose a saved view";
    element("savedBrowsingViews").append(placeholder);
    desired.views.forEach(view => {
      const option = document.createElement("option"); option.value = view.name;
      option.textContent = view.name; element("savedBrowsingViews").append(option);
    });
    element("savedBrowsingViews").value = desired.views.some(view => view.name === selected) ? selected : "";
  };
  function locks() {
    const locked = blocked() || reading;
    ["savedBrowsingViews", "browsingViewName", "applyBrowsingView"].forEach(id => element(id).disabled = locked || !available);
    ["saveBrowsingView", "deleteBrowsingView", "clearBrowsingResume"].forEach(id => element(id).disabled = locked || !available || paused);
    element("reloadBrowsing").disabled = locked || writing || !identifier(reportID);
    element("applyBrowsingView").disabled ||= !element("savedBrowsingViews").value;
    element("deleteBrowsingView").disabled ||= !element("savedBrowsingViews").value;
    const name = element("browsingViewName").value.trim().normalize("NFC");
    element("saveBrowsingView").textContent = desired.views.some(view => view.name === name) ? "Update view" : "Save view";
  }
  function fail(error) {
    paused = true; clearTimeout(timer);
    message("Browsing was not saved: " + error.message + " Your review and current view remain available. Reload saved browsing to retry.", true);
    locks();
  }
  async function request(payload) {
    const response = await fetch("api/browsing-preferences", payload === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload), keepalive: true
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Browsing preferences are unavailable.");
    return validate(result);
  }
  function readLocal() {
    if (!localStorageObject) localStorageObject = globalThis.localStorage;
    if (!localStorageObject) throw new Error("Browser storage is unavailable.");
    const raw = localStorageObject.getItem(storageKey);
    if (raw === null) return empty();
    if (new TextEncoder().encode(raw).length > 65536) throw new Error("Saved browsing exceeds 64 KiB.");
    return validate(JSON.parse(raw));
  }
  async function flush() {
    clearTimeout(timer);
    if (!available || paused || reading || writing || equal(desired.last, base.last) && equal(desired.views, base.views)) return;
    let outgoing;
    try { outgoing = validate(desired); }
    catch (error) { fail(error); return; }
    const ticket = changes;
    writing = true; locks();
    try {
      let result;
      if (data.session) result = await request({expected_revision: base.revision, last: outgoing.last, views: outgoing.views});
      else {
        if (!memoryOnly) {
          const current = readLocal();
          if (current.revision !== base.revision || !equal(current, base)) throw new Error("Browsing changed in another window.");
        }
        result = {...outgoing, revision: base.revision + 1}; validate(result);
        if (!memoryOnly) localStorageObject.setItem(storageKey, storedJSON(result));
      }
      base = clone(result);
      if (ticket === changes) desired = clone(result);
      else desired.revision = result.revision;
      message(ticket !== changes ? "Saving browsing…" : memoryOnly ? "Browser storage is unavailable. Browsing is kept only while this page stays open." : scope);
    } catch (error) { fail(error); }
    finally { writing = false; locks(); if (!paused && ticket !== changes) schedule(); }
  }
  function schedule() {
    clearTimeout(timer);
    if (available && !paused && !reading) timer = setTimeout(flush, 120);
  }
  function update(value) {
    if (!available) return;
    if (equal(desired.last, value.last) && equal(desired.views, value.views)) return;
    desired = value; ++changes;
    if (!paused) message("Saving browsing…");
    schedule(); locks();
  }
  function restore(last, note) {
    restoreImage(clone(last)); pairRestore(clone(last.pair));
    message(note || scope); locks();
  }
  async function reload() {
    if (blocked() || reading || writing || !identifier(reportID)) return;
    clearTimeout(timer); reading = true;
    const ticket = changes, activityTicket = activity();
    message("Loading saved browsing…"); locks();
    try {
      const result = data.session ? await request() : readLocal();
      if (ticket !== changes || activityTicket !== activity() || blocked()) {
        paused = true;
        message("Saved browsing was not applied because you continued working. Your current view and edits are preserved. Reload saved browsing when ready.");
        return;
      }
      desired = clone(result); base = clone(result); available = true; paused = false; memoryOnly = false;
      viewList(); restore(result.last, "Saved browsing restored. " + scope);
    } catch (error) { fail(error); }
    finally { reading = false; locks(); if (!paused) schedule(); }
  }
  function selectedView() { return desired.views.find(view => view.name === element("savedBrowsingViews").value); }
  element("savedBrowsingViews").onchange = () => {
    element("browsingViewName").value = selectedView()?.name || ""; locks();
  };
  element("browsingViewName").oninput = locks;
  element("saveBrowsingView").onclick = () => {
    if (blocked() || reading || !available || paused) return;
    const name = element("browsingViewName").value.trim().normalize("NFC");
    const value = clone(desired), view = {name, filters: clone(value.last.filters)};
    const index = value.views.findIndex(item => item.name === name);
    if (index < 0) value.views.push(view); else value.views[index] = view;
    try { validate(value); update(value); viewList(); element("savedBrowsingViews").value = name; locks(); }
    catch (error) { message(error.message, true); }
  };
  element("applyBrowsingView").onclick = () => {
    const view = selectedView();
    if (blocked() || reading || !available || !view) return;
    restore({...clone(desired.last), filters: clone(view.filters), image_id: null, position: 0}, "Applied saved filters: " + view.name + ".");
  };
  element("deleteBrowsingView").onclick = () => {
    if (blocked() || reading || !available || paused || !selectedView()) return;
    const value = clone(desired);
    value.views = value.views.filter(view => view.name !== element("savedBrowsingViews").value);
    update(value); element("browsingViewName").value = ""; viewList(); locks();
  };
  element("clearBrowsingResume").onclick = () => {
    if (blocked() || reading || !available || paused) return;
    const value = clone(desired);
    value.last.image_id = null; value.last.position = 0;
    value.last.pair.offset = 0; value.last.pair.pair_id = null;
    update(value); pairRestore(clone(value.last.pair));
    message("Saved queue positions cleared; filters and named views are retained. The current image stays open.");
  };
  element("reloadBrowsing").onclick = reload;
  try {
    if (!available) throw new Error("This report has no browsing identity.");
    if (data.session) {
      if (data.browsing.error || !data.browsing.state) throw new Error(data.browsing.error || "Saved browsing is unavailable.");
      desired = validate(data.browsing.state);
    } else {
      try { desired = readLocal(); }
      catch (error) {
        if (error.name === "SecurityError" || !localStorageObject) {
          memoryOnly = true; desired = empty();
        } else throw error;
      }
    }
    base = clone(desired);
    message(memoryOnly ? "Browser storage is unavailable. Browsing is kept only while this page stays open." : scope);
  } catch (error) { available = false; paused = true; message("Saved browsing unavailable: " + error.message + " You can still review this report.", true); }
  viewList(); locks();
  if (globalThis.addEventListener) {
    globalThis.addEventListener("pagehide", () => { if (!writing) flush(); });
    globalThis.addEventListener("storage", event => {
      if (!data.session && event.key === storageKey) {
        paused = true; clearTimeout(timer);
        message("Saved browsing changed in another window. Your current view is unchanged. Reload saved browsing to continue saving."); locks();
      }
    });
  }
  return {
    initial: () => clone(available ? desired.last : empty().last),
    filters: emptyFilters, locks, flush,
    captureImage(last) { update({...clone(desired), last: {...clone(desired.last), ...last}}); },
    capturePair(pair) { update({...clone(desired), last: {...clone(desired.last), pair: clone(pair)}}); },
    pair: () => clone(desired.last.pair),
    onPairRestore(callback) { pairRestore = callback; },
    note: message,
  };
}
