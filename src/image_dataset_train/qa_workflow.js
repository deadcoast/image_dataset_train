// Live pair review and publication share the image reviewer's API and save state.
if (data.session) {
  let pairResult = null, currentPair = null, pairRevision = null, pairOffset = 0;
  let pairRequest = 0, pairLoading = false, pairSaving = false, publicationRevision = null, publicationTimer = null;
  let evaluatingPairs = false, evaluationRevision = null;
  let publicationSettingsLoaded = false;
  let pairBrowsingLoaded = false, pendingPairResume = null;
  browsingPreferences.onPairRestore(pair => { pairBrowsingLoaded = false; pendingPairResume = pair; });
  ["pairs", "publish", "training"].forEach(name => $(name + "Tab").hidden = false);
  data.entries.forEach(entry => {
    const option = document.createElement("option");
    option.value = entry.source_path;
    $("imagePaths").append(option);
  });

  function switchPane(name) {
    showPane(name);
    if (name === "pairs") {
      if (!pairBrowsingLoaded) {
        pendingPairResume = browsingPreferences.pair(); pairBrowsingLoaded = true;
      }
      loadPairs(currentPair?.pair_id);
    }
    if (name === "publish") loadPublication();
    if (name === "training") loadTraining();
    if (name === "images" && matched[current]) loadForms(matched[current], ++generation);
  }
  ["images", "pairs", "publish", "training"].forEach(name => $(name + "Tab").onclick = () => switchPane(name));

  function pairLocks() {
    workflowBusy = pairLoading || pairSaving || evaluatingPairs;
    lockNavigation();
    const locked = workflowDirty || workflowBusy;
    ["pairFilter", "refreshPairs", "comparePair", "manualLeft", "manualRight", "evaluatePairs"].forEach(id => $(id).disabled = locked);
    document.querySelectorAll("#pairEvaluationErrors button").forEach(button => button.disabled = locked);
    $("pairPrev").disabled = locked || pairOffset === 0;
    $("pairNext").disabled = locked || pairResult?.pair_next_offset == null;
    document.querySelectorAll("#pairQueue button").forEach(button => button.disabled = locked);
    $("pairFields").disabled = $("savePair").disabled = pairLoading || pairSaving || !currentPair;
    $("reloadPair").disabled = pairLoading || pairSaving || !currentPair;
    text("reloadPair", workflowDirty ? "Discard pair edits and reload" : "Reload this pair");
    ["showAllPairs", "openManualPair", "pairSnapshot"].forEach(id => $(id).disabled = locked);
  }
  function loadPairPreview(side, retry = false) {
    const pair = currentPair;
    if (!pair) return;
    loadReviewMedia(side + "PairImage", side + "PairUnavailable", "retry" + (side === "left" ? "Left" : "Right") + "PairImage",
      pair[side + "_image"], () => currentPair === pair, side + " comparison image", retry);
  }
  ["left", "right"].forEach(side => $("retry" + (side === "left" ? "Left" : "Right") + "PairImage").onclick = () => loadPairPreview(side, true));
  function clearPairTarget() {
    currentPair = null; pairRevision = null; pairResult = null; pairOffset = 0;
    $("pairQueue").replaceChildren(); $("pairDetail").hidden = true;
    text("pairProgress", "");
    ["showAllPairs", "openManualPair", "pairSnapshot"].forEach(id => $(id).hidden = true);
  }
  function emptyPairQueue(result) {
    const allPairs = Object.values(result.pair_counts).reduce((sum, count) => sum + count, 0);
    const images = Object.values(result.image_counts).reduce((sum, count) => sum + count, 0);
    ["showAllPairs", "openManualPair", "pairSnapshot"].forEach(id => $(id).hidden = true);
    if (result.pairs.length) { status("pairMessage", ""); return; }
    if (!allPairs) {
      status("pairMessage", images >= 2 ? "No saved or proposed pairs. Compare two inventory images if you want to review a relationship." : "No saved or proposed pairs. At least two eligible inventory images are needed for a comparison.");
      $("openManualPair").hidden = images < 2; $("pairSnapshot").hidden = false;
    } else {
      status("pairMessage", $("pairFilter").value === "unreviewed" ? "No unresolved pairs remain in this queue. You can inspect the saved pair decisions." : "No pairs match this decision filter.");
      $("showAllPairs").hidden = false;
    }
  }
  function showPair(pair, revision, remember = true) {
    currentPair = pair; pairRevision = revision;
    workflowDirty = false;
    $("pairDetail").hidden = !pair;
    if (pair) {
      ["left", "right"].forEach(side => {
        text(side + "PairName", pair[side + "_source_path"]);
        loadPairPreview(side);
      });
      text("pairInfo", "Review revision " + revision + (pair.hamming_distance == null ? " · manual comparison" : " · pHash distance " + pair.hamming_distance));
      $("pairDecision").value = pair.decision;
      $("pairEvaluationSet").value = pair.evaluation_set || "";
      $("pairReason").value = pair.reason || "";
    }
    document.querySelectorAll("#pairQueue button").forEach(button => button.setAttribute("aria-current", String(button.dataset.pair === pair?.pair_id)));
    if (remember && pairResult) browsingPreferences.capturePair({decision: $("pairFilter").value,
      offset: pairOffset, pair_id: pair?.pair_id || null});
    pairLocks();
  }
  async function loadPairs(preferred, restoring = false) {
    if (pairLoading || pairSaving || workflowDirty) return;
    if (pendingPairResume) {
      $("pairFilter").value = pendingPairResume.decision; pairOffset = pendingPairResume.offset;
      preferred = pendingPairResume.pair_id; pendingPairResume = null; restoring = true;
    }
    const requested = {decision: $("pairFilter").value, offset: pairOffset, pair_id: preferred || null};
    const ticket = ++pairRequest;
    pairLoading = true; $("pairFields").disabled = true; pairLocks();
    try {
      const result = await api("api/pairs?decision=" + $("pairFilter").value + "&offset=" + pairOffset);
      if (ticket !== pairRequest) return;
      if (pairOffset && !result.pairs.length) {
        pairOffset = Math.max(0, Math.floor((result.pair_total - 1) / 20) * 20);
        pairLoading = false;
        return loadPairs(preferred, restoring);
      }
      pairResult = result;
      if (evaluationRevision !== null && result.revision !== evaluationRevision) {
        text("pairEvaluationStatus", `Saved evaluation covers revision ${evaluationRevision}; current reviews are revision ${result.revision}. Evaluate again to include changes.`);
      }
      text("pairProgress", `${result.pair_counts.unreviewed || 0} unresolved · ${result.groups} current groups · ${result.pair_total} matching pairs`);
      $("pairQueue").replaceChildren();
      result.pairs.forEach(pair => {
        const button = document.createElement("button");
        button.className = "item"; button.dataset.pair = pair.pair_id;
        button.textContent = pair.left_source_path + " ↔ " + pair.right_source_path;
        const small = document.createElement("small"); small.textContent = pair.decision;
        button.append(small); button.onclick = () => { pendingPairResume = null; showPair(pair, result.revision); };
        $("pairQueue").append(button);
      });
      emptyPairQueue(result);
      const selected = result.pairs.find(pair => pair.pair_id === preferred);
      const missingResume = restoring && preferred && !selected;
      showPair(selected || result.pairs[0], result.revision, !missingResume);
      if (missingResume) {
        pendingPairResume = browsingPreferences.pair();
        status("pairMessage", "The saved pair is no longer on this page. The current queue is shown; choose a pair or navigate to save a new position. " + $("pairMessage").textContent);
      }
    } catch (error) {
      if (ticket !== pairRequest) return;
      pendingPairResume = requested;
      clearPairTarget(); $("pairSnapshot").hidden = false;
      status("pairMessage", "Pair queue unavailable: " + error.message + " Restore access, then reload the pair queue.", true);
    }
    finally {
      if (ticket === pairRequest) { pairLoading = false; pairLocks(); }
    }
  }
  async function compare(left, right, discard = false) {
    if (pairLoading || pairSaving || (workflowDirty && !discard)) return;
    const reloading = discard && currentPair !== null;
    $("manualLeft").value = left; $("manualRight").value = right;
    const ticket = ++pairRequest;
    pairLoading = true; $("pairFields").disabled = true; pairLocks();
    try {
      const result = await api("api/compare?" + new URLSearchParams({left, right}));
      if (ticket === pairRequest) {
        clearPairTarget(); status("pairMessage", ""); text("pairProgress", "Selected comparison");
        showPair(result.pair, result.revision);
      }
    } catch (error) {
      if (ticket !== pairRequest) return;
      if (reloading) {
        status("pairMessage", "Pair reload unavailable: " + error.message + " Your edits and saved revision are preserved. Restore access, then reload this pair.", true);
      } else {
        clearPairTarget(); $("openManualPair").hidden = false;
        status("pairMessage", "Comparison unavailable: " + error.message + " Check the recorded paths and source access, then compare again.", true);
      }
    } finally { if (ticket === pairRequest) { pairLoading = false; pairLocks(); } }
  }
  $("pairFilter").onchange = () => { pendingPairResume = null; pairOffset = 0; loadPairs(); };
  $("refreshPairs").onclick = () => loadPairs(currentPair?.pair_id);
  $("pairPrev").onclick = () => { pendingPairResume = null; pairOffset = Math.max(0, pairOffset - 20); loadPairs(); };
  $("pairNext").onclick = () => { pendingPairResume = null; pairOffset = pairResult.pair_next_offset; loadPairs(); };
  $("comparePair").onclick = () => compare($("manualLeft").value, $("manualRight").value);
  $("reloadPair").onclick = () => currentPair && compare(currentPair.left_source_path, currentPair.right_source_path, true);
  $("showAllPairs").onclick = () => { pendingPairResume = null; $("pairFilter").value = "all"; pairOffset = 0; loadPairs(); };
  $("openManualPair").onclick = () => { $("manualPair").open = true; $("manualLeft").focus(); };
  $("pairSnapshot").onclick = () => switchPane("content");
  $("pairForm").oninput = () => { workflowDirty = true; pairLocks(); };
  $("pairForm").onsubmit = async event => {
    event.preventDefault();
    if (!currentPair || pairLoading || pairSaving) return;
    const pair = currentPair, ticket = ++pairRequest;
    pairSaving = true; pairLocks();
    try {
      const saved = await api("api/pairs", {
        left: pair.left_source_path, right: pair.right_source_path,
        expected_revision: pairRevision, decision: $("pairDecision").value,
        evaluation_set: $("pairEvaluationSet").value, reason: $("pairReason").value
      });
      if (ticket !== pairRequest) return;
      workflowDirty = false;
      pairSaving = false;
      await loadPairs(saved.pair_id);
      if (pairResult) status("pairMessage", "Pair decision saved · revision " + saved.revision);
      else status("pairMessage", "Pair decision saved · revision " + saved.revision + ". The queue could not reload; restore access and reload the pair queue.", true);
      document.dispatchEvent(new Event("reviews-saved"));
    } catch (error) { if (ticket === pairRequest) status("pairMessage", error.message, true); }
    finally { if (ticket === pairRequest) { pairSaving = false; pairLocks(); } }
  };

  $("evaluatePairs").onclick = async () => {
    evaluatingPairs = true; pairLocks();
    status("pairEvaluationStatus", "Evaluating saved judgments…");
    try {
      const result = await api("api/similarity-evaluation", {}), counts = result.counts, point = result.current;
      evaluationRevision = result.review_revision;
      $("pairEvaluation").hidden = false;
      status("pairEvaluationStatus", `Saved evaluation · review revision ${result.review_revision}`);
      text("pairEvaluationCoverage", `${result.related_pairs} related / ${result.distinct_pairs} distinct evaluated content pairs · ${counts.alias_judgments_collapsed || 0} alias judgments combined · ${counts.exact_byte_judgments || 0} exact-byte judgments separate · ${counts.hash_unavailable || 0} pairs without hashes · ${counts.conflicting_judgments || 0} conflicting pairs · ${counts.stale_decisions || 0} stale decisions. ` +
        (result.both_classes_reviewed ? "Both classes are represented." : "Both related and distinct examples are needed for a useful threshold comparison."));
      text("pairEvaluationCurrent", `Proposal radius ${point.max_distance}: ${point.false_positive} false matches · ${point.false_negative} known misses. ${counts.unjudged_indexed_pairs} indexed content pairs have no usable judgment.`);
      const split = result.evaluation_sets, splitCounts = split.counts, held = split.held_out_at_fit;
      const metric = value => value === null ? "undefined" : (100 * value).toFixed(1) + "%";
      text("pairEvaluationSplit", split.fit_radius === null
        ? `Calibration/held-out sets: ${splitCounts.calibration} / ${splitCounts.held_out} pairs. A fit radius needs both related and distinct calibration examples (${splitCounts.calibration_related} / ${splitCounts.calibration_distinct}); held-out metrics are not selected.`
        : `Calibration/held-out sets: ${splitCounts.calibration} / ${splitCounts.held_out} pairs. Fitted radius ${split.fit_radius} (maximum calibration F1, stricter radius wins ties); held-out at that radius: precision ${metric(held.precision)}, recall ${metric(held.recall)}, F1 ${metric(held.f1)}.`);
      const percent = value => value === null ? "—" : (100 * value).toFixed(1) + "%";
      reportTable("pairThresholds", result.thresholds.map(row => [
        row.max_distance + (row.max_distance === point.max_distance ? " (proposal radius)" : ""),
        row.true_positive, row.false_positive, row.false_negative, row.true_negative,
        percent(row.precision), percent(row.recall), percent(row.f1)
      ]), 8);
      text("pairEvaluationErrorCount", `Showing ${result.error_examples.length} of ${result.error_examples_total} evaluated errors. All evaluated pairs are saved in pairs.jsonl.`);
      $("pairEvaluationErrors").replaceChildren();
      result.error_examples.forEach(pair => {
        const example = pair.judgments[0], button = document.createElement("button");
        button.textContent = `${pair.finding}: ${example.left_source_path} ↔ ${example.right_source_path} (distance ${pair.distance})`;
        button.onclick = async () => { await compare(example.left_source_path, example.right_source_path); $("pairMessage").scrollIntoView({block:"start"}); };
        $("pairEvaluationErrors").append(button);
      });
      text("pairEvaluationPath", "Saved evaluation: " + result.run);
    } catch (error) { status("pairEvaluationStatus", error.message, true); }
    finally { evaluatingPairs = false; pairLocks(); }
  };

  let reviewChangesRequest = 0, reviewChangesResult = null, reviewChangesLoading = false;
  function reviewChangesLocks() {
    $("reviewChangesPrev").disabled = reviewChangesLoading || !reviewChangesResult?.offset;
    $("reviewChangesNext").disabled = reviewChangesLoading || reviewChangesResult?.next_offset == null;
  }
  function renderReviewChanges(result, restarted) {
    const labels = {unchanged: "Saved reviews match this report.",
      history_only: "Review history advanced; the saved records now match this report.",
      changed: `${result.net_change_count} saved records differ from this report.`};
    status("reviewChangesStatus", (restarted ? "Saved reviews changed while paging; showing the first page. " : "") + labels[result.state]);
    text("reviewChangesRevision", `Report revision ${result.snapshot_revision} · Inspected current revision ${result.current_revision} · ${result.history_delta_count} later history events`);
    const counts = [`${result.counts.images} image records`, `${result.counts.pairs} pair records`, `${result.counts.outside_report} outside this report`];
    if (result.counts.partial_report) counts.push(`${result.counts.partial_report} partly in this report`);
    if (result.counts.incompatible) counts.push(`${result.counts.incompatible} differ from selected inventory`);
    text("reviewChangesCounts", counts.join(" · "));
    $("reviewChangesList").replaceChildren();
    result.differences.forEach(change => {
      const item = document.createElement("li"), heading = document.createElement("strong");
      heading.textContent = change.kind === "images" ? change.identity.source_path : `${change.identity.left_source_path} ↔ ${change.identity.right_source_path}`;
      const scope = document.createElement("p"); scope.className = "muted";
      const membership = {in_report: "In this report", outside_report: "Outside this report", partial_report: "Partly in this report"};
      scope.textContent = `${membership[change.report_membership]} · ${change.inventory_compatible ? "Matches selected inventory" : "Different from selected inventory"}`;
      const details = document.createElement("details"), summary = document.createElement("summary"), values = document.createElement("pre");
      summary.textContent = "Content identities"; values.textContent = JSON.stringify(change.identity, null, 2);
      details.append(summary, values); item.append(heading, scope, details);
      const fields = document.createElement("details"), fieldsSummary = document.createElement("summary");
      const names = change.changes.slice(0, 3).map(field => field.field).join(", ");
      const remaining = change.changes.length - 3;
      fieldsSummary.textContent = `${change.changes.length} changed fields: ${names}${remaining > 0 ? `, +${remaining} more` : ""}`;
      fields.append(fieldsSummary);
      change.changes.forEach(field => {
        const label = document.createElement("p"), value = document.createElement("pre");
        label.textContent = field.field;
        const before = field.before_present ? JSON.stringify(field.before) : "<absent>";
        const after = field.after_present ? JSON.stringify(field.after) : "<absent>";
        value.textContent = `Snapshot: ${before}\nCurrent: ${after}`;
        fields.append(label, value);
      });
      item.append(fields);
      $("reviewChangesList").append(item);
    });
    const shown = result.differences.length;
    text("reviewChangesPage", shown ? `${result.offset + 1}–${result.offset + shown} of ${result.filtered_count} matching records` : "No matching changed records on this page.");
    reviewChangesLocks();
  }
  async function loadReviewChanges(offset = 0, expectedIdentity = null, restarted = false) {
    const ticket = ++reviewChangesRequest;
    reviewChangesLoading = true; reviewChangesLocks();
    status("reviewChangesStatus", "Inspecting saved changes…");
    try {
      const query = new URLSearchParams({limit: "20", offset: String(offset)});
      if ($("reviewChangesKind").value) query.set("kind", $("reviewChangesKind").value);
      const result = await api("api/review-changes?" + query);
      if (ticket !== reviewChangesRequest) return;
      if (expectedIdentity && result.inspection_sha256 !== expectedIdentity) {
        reviewChangesResult = null;
        return loadReviewChanges(0, null, true);
      }
      reviewChangesResult = result;
      renderReviewChanges(result, restarted);
    } catch (error) {
      if (ticket !== reviewChangesRequest) return;
      reviewChangesResult = null;
      $("reviewChangesList").replaceChildren();
      text("reviewChangesRevision", ""); text("reviewChangesCounts", ""); text("reviewChangesPage", "");
      status("reviewChangesStatus", "Changes unavailable: " + error.message, true);
    } finally {
      if (ticket === reviewChangesRequest) { reviewChangesLoading = false; reviewChangesLocks(); }
    }
  }
  $("refreshReviewChanges").onclick = () => loadReviewChanges(0);
  $("reviewChangesKind").onchange = () => loadReviewChanges(0);
  $("reviewChangesPrev").onclick = () => loadReviewChanges(Math.max(0, reviewChangesResult.offset - 20), reviewChangesResult.inspection_sha256);
  $("reviewChangesNext").onclick = () => loadReviewChanges(reviewChangesResult.next_offset, reviewChangesResult.inspection_sha256);
  document.addEventListener("reviews-saved", () => loadReviewChanges(0));

  const defaults = data.publication;
  function restorePublicationSettings(settings) {
    $("publicationCaptions").value = settings.captions_run || "";
    $("publicationRatio").value = settings.export.validation_ratio * 100;
    $("publicationSeed").value = settings.export.seed;
    $("publicationStrategy").value = settings.export.split_strategy;
    $("publicationResolution").value = settings.export.resolution;
    $("publicationRepeats").value = settings.export.repeats;
  }
  restorePublicationSettings(defaults);
  text("publicationDestinations", "Groups and QA: " + defaults.runs + " · Training exports: " + defaults.exports);

  function showPublication(result) {
    clearTimeout(publicationTimer);
    status("publicationStatus", result.message, result.status === "failed");
    $("publicationFields").disabled = result.status === "running" || publicationRevision === null;
    $("publicationOutputs").replaceChildren();
    Object.entries(result.outputs).forEach(([kind, output]) => {
      const item = document.createElement("li"), path = document.createElement("code");
      const summary = output.summary;
      let description = kind === "groups" ? `Groups · revision ${summary.review_revision} · ${summary.groups} groups · ${summary.review_complete ? "decisions complete" : "review incomplete"}` :
        kind === "export" ? `Verified export · ${summary.images} images · ${summary.split_images.train || 0} train / ${summary.split_images.validation || 0} validation` :
          `QA · ${summary.images} images · ${summary.pilot_images} pilot images`;
      item.append(document.createTextNode(description), document.createElement("br"));
      path.textContent = output.path; item.append(path); $("publicationOutputs").append(item);
    });
    $("openPublication").hidden = !result.outputs.qa;
    if (result.outputs.qa) $("openPublication").href = result.outputs.qa.url;
    if (result.status === "running") publicationTimer = setTimeout(pollPublication, 750);
  }
  async function pollPublication() {
    try { showPublication(await api("api/publication")); }
    catch (error) { status("publicationStatus", error.message + " Refresh to reconnect to the publication job.", true); }
  }
  async function loadPublication() {
    loadReviewChanges(0);
    $("publicationFields").disabled = true;
    try {
      const [state, job] = await Promise.all([api("api/pairs?decision=all"), api("api/publication")]);
      if (!publicationSettingsLoaded) {
        if (job.settings) restorePublicationSettings(job.settings);
        publicationSettingsLoaded = true;
      }
      publicationRevision = state.revision;
      text("publicationReadiness", `Current revision ${state.revision} · ${state.groups} groups · ${state.pair_counts.unreviewed || 0} unresolved pairs · ${state.image_counts.unreviewed || 0} unreviewed images · ${state.similarity_errors} similarity errors`);
      showPublication(job);
    } catch (error) { publicationRevision = null; status("publicationReadiness", error.message, true); }
  }
  $("refreshPublication").onclick = loadPublication;
  $("publicationForm").onsubmit = async event => {
    event.preventDefault();
    if (publicationRevision === null) return;
    $("publicationFields").disabled = true;
    try {
      showPublication(await api("api/publication", {
        mode: event.submitter?.value || "groups", expected_revision: publicationRevision,
        captions_run: $("publicationCaptions").value.trim(),
        export: {validation_ratio: Number($("publicationRatio").value) / 100,
          seed: Number($("publicationSeed").value), split_strategy: $("publicationStrategy").value,
          resolution: Number($("publicationResolution").value), repeats: Number($("publicationRepeats").value)}
      }));
    } catch (error) { status("publicationStatus", error.message, true); $("publicationFields").disabled = false; }
  };
}
