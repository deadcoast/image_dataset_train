// Live pair review and publication share the image reviewer's API and save state.
if (data.session) {
  let pairResult = null, currentPair = null, pairRevision = null, pairOffset = 0;
  let pairRequest = 0, pairLoading = false, publicationRevision = null, publicationTimer = null;
  let evaluatingPairs = false, evaluationRevision = null;
  ["pairs", "publish", "training"].forEach(name => $(name + "Tab").hidden = false);
  data.entries.forEach(entry => {
    const option = document.createElement("option");
    option.value = entry.source_path;
    $("imagePaths").append(option);
  });

  function switchPane(name) {
    showPane(name);
    if (name === "pairs") loadPairs();
    if (name === "publish") loadPublication();
    if (name === "training") loadTraining();
    if (name === "images" && matched[current]) loadForms(matched[current], ++generation);
  }
  ["images", "pairs", "publish", "training"].forEach(name => $(name + "Tab").onclick = () => switchPane(name));

  function pairLocks() {
    const locked = workflowDirty || pairLoading || evaluatingPairs;
    ["pairFilter", "refreshPairs", "comparePair", "manualLeft", "manualRight", "evaluatePairs"].forEach(id => $(id).disabled = locked);
    document.querySelectorAll("#pairEvaluationErrors button").forEach(button => button.disabled = locked);
    $("pairPrev").disabled = locked || pairOffset === 0;
    $("pairNext").disabled = locked || pairResult?.pair_next_offset == null;
    document.querySelectorAll("#pairQueue button").forEach(button => button.disabled = locked);
    lockNavigation();
  }
  function showPair(pair, revision) {
    currentPair = pair; pairRevision = revision;
    workflowDirty = false;
    $("pairDetail").hidden = !pair;
    if (pair) {
      ["left", "right"].forEach(side => {
        text(side + "PairName", pair[side + "_source_path"]);
        const image = $(side + "PairImage");
        image.onerror = () => status("pairMessage", "A comparison image is unavailable. Check that the recorded source is still accessible and unchanged.", true);
        image.src = pair[side + "_image"];
      });
      text("pairInfo", "Review revision " + revision + (pair.hamming_distance == null ? " · manual comparison" : " · pHash distance " + pair.hamming_distance));
      $("pairDecision").value = pair.decision;
      $("pairReason").value = pair.reason || "";
    }
    document.querySelectorAll("#pairQueue button").forEach(button => button.setAttribute("aria-current", String(button.dataset.pair === pair?.pair_id)));
    pairLocks();
  }
  async function loadPairs(preferred) {
    const ticket = ++pairRequest;
    pairLoading = true; $("pairFields").disabled = true; pairLocks();
    try {
      const result = await api("api/pairs?decision=" + $("pairFilter").value + "&offset=" + pairOffset);
      if (ticket !== pairRequest) return;
      if (pairOffset && !result.pairs.length) {
        pairOffset = Math.max(0, Math.floor((result.pair_total - 1) / 20) * 20);
        return loadPairs(preferred);
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
        button.append(small); button.onclick = () => showPair(pair, result.revision);
        $("pairQueue").append(button);
      });
      status("pairMessage", result.pairs.length ? "" : "No pairs match this filter. Use All pairs or compare two inventory paths.");
      showPair(result.pairs.find(pair => pair.pair_id === preferred) || result.pairs[0], result.revision);
    } catch (error) { status("pairMessage", error.message, true); }
    finally {
      if (ticket === pairRequest) { pairLoading = false; $("pairFields").disabled = false; pairLocks(); }
    }
  }
  async function compare(left, right) {
    const ticket = ++pairRequest;
    pairLoading = true; $("pairFields").disabled = true; pairLocks();
    try {
      const result = await api("api/compare?" + new URLSearchParams({left, right}));
      if (ticket === pairRequest) { status("pairMessage", ""); showPair(result.pair, result.revision); }
    } catch (error) { status("pairMessage", error.message, true); }
    finally { pairLoading = false; $("pairFields").disabled = false; pairLocks(); }
  }
  $("pairFilter").onchange = () => { pairOffset = 0; loadPairs(); };
  $("refreshPairs").onclick = () => loadPairs(currentPair?.pair_id);
  $("pairPrev").onclick = () => { pairOffset = Math.max(0, pairOffset - 20); loadPairs(); };
  $("pairNext").onclick = () => { pairOffset = pairResult.pair_next_offset; loadPairs(); };
  $("comparePair").onclick = () => compare($("manualLeft").value, $("manualRight").value);
  $("reloadPair").onclick = () => compare(currentPair.left_source_path, currentPair.right_source_path);
  $("pairForm").oninput = () => { workflowDirty = true; pairLocks(); };
  $("pairForm").onsubmit = async event => {
    event.preventDefault();
    if (!currentPair) return;
    $("pairFields").disabled = true;
    try {
      const saved = await api("api/pairs", {
        left: currentPair.left_source_path, right: currentPair.right_source_path,
        expected_revision: pairRevision, decision: $("pairDecision").value, reason: $("pairReason").value
      });
      workflowDirty = false;
      await loadPairs(saved.pair_id);
      status("pairMessage", "Pair decision saved · revision " + saved.revision);
    } catch (error) { status("pairMessage", error.message, true); }
    finally { $("pairFields").disabled = false; pairLocks(); }
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

  const defaults = data.publication;
  $("publicationCaptions").value = defaults.captions_run;
  $("publicationRatio").value = defaults.export.validation_ratio * 100;
  $("publicationSeed").value = defaults.export.seed;
  $("publicationStrategy").value = defaults.export.split_strategy;
  $("publicationResolution").value = defaults.export.resolution;
  $("publicationRepeats").value = defaults.export.repeats;
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
    $("publicationFields").disabled = true;
    try {
      const [state, job] = await Promise.all([api("api/pairs?decision=all"), api("api/publication")]);
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
