// The same saved summary drives offline reports and the live reviewer.
function showPane(name) {
  ["images", "content", "pairs", "publish", "training"].forEach(item => {
    $(item + "Pane").hidden = item !== name;
    $(item + "Tab").setAttribute("aria-pressed", String(item === name));
  });
}
$("imagesTab").onclick = () => showPane("images");
$("contentTab").onclick = () => showPane("content");

function reportTable(id, rows, columns = 2) {
  $(id).replaceChildren();
  if (!rows.length) rows = [["No recorded values"]];
  rows.forEach(values => {
    const tr = document.createElement("tr");
    values.forEach(value => {
      const td = document.createElement("td");
      td.textContent = value;
      if (values.length === 1) td.colSpan = columns;
      tr.append(td);
    });
    $(id).append(tr);
  });
}
function renderContent() {
  const report = data.summary.content;
  $("contentUnavailable").hidden = !!report;
  $("contentDetails").hidden = !report;
  $("contentScope").disabled = !report;
  if (!report) return;
  const scope = report.scopes[$("contentScope").value], annotations = scope.reviewed_annotations;
  text("contentCoverage", `${scope.images} occurrences · ${scope.unique_images} unique image hashes · ` +
    `${scope.tagged_images} with matching tagged evidence · ${scope.untagged_images} without evidence. ` +
    Object.entries(scope.decisions).map(([name, count]) => `${name}: ${count}`).join(" · "));
  text("annotationCoverage", `Labels reviewed: ${annotations.labels_reviewed}/${scope.images}; ` +
    `subset reviewed: ${annotations.subset_reviewed}/${scope.images}; unassigned subset: ${annotations.unassigned_subset}. Labels can overlap.`);
  reportTable("contentAnnotations", [
    ...Object.entries(annotations.labels).map(([name, count]) => ["Label: " + name, count]),
    ...Object.entries(annotations.subsets).map(([name, count]) => ["Subset: " + name, count])
  ]);
  text("compositionCoverage", `${scope.composition.unavailable_images} images without composition evidence; unknown means scored but unresolved.`);
  reportTable("contentComposition", Object.entries(scope.composition.counts));
  const proposals = scope.subset_proposals;
  text("proposalCoverage", `${proposals.unmatched_images} unmatched · ${proposals.ambiguous_images} conflicting · ${proposals.unavailable_images} unavailable. Proposals do not assign reviewed subsets.`);
  reportTable("contentProposals", Object.entries(proposals.counts));
  text("ratingCoverage", `${scope.ratings.available_images}/${scope.images} with scores · ${scope.ratings.tied_images} ties · ${scope.ratings.unavailable_images} unavailable.`);
  reportTable("contentRatings", Object.entries(scope.ratings.counts));
  [["observed", scope.observed_tags], ["selected", scope.selected_tags]].forEach(([name, tags]) => {
    text(name + "Coverage", `${tags.available_images}/${scope.images} with recorded ${name} tags · ${tags.unavailable_images} unavailable. Showing ${tags.top_tags.length} of ${tags.distinct_tags} tags, ranked by image count.`);
    reportTable(name === "observed" ? "contentObserved" : "contentSelected", tags.top_tags.map(tag =>
      [tag.name, ({0: "General", 4: "Character"})[tag.category] || String(tag.category), tag.images]), 3);
  });
  const provenance = report.provenance || {}, model = provenance.model || {}, runtime = provenance.runtime || {};
  $("contentProvenance").replaceChildren();
  [
    ["Evidence", report.manifest_available ? "Saved caption manifest" : report.provenance ? "Metadata only; observations unavailable" : "No tagging run supplied"],
    ["Caption run", provenance.run_id], ["Stage", provenance.stage],
    ["Model", model.repo || model.model], ["Revision", model.revision], ["Artifact", model.artifact_id],
    ["Providers", runtime.providers?.join(", ")], ["Requested device", provenance.requested_device],
    ["Fallback", Object.hasOwn(provenance, "provider_fallback") ? (provenance.provider_fallback || "None") : null],
    ["Preprocessing", provenance.preprocessing], ["Caption rules", provenance.caption_version],
    ["Rules digest", provenance.caption_rules_sha256], ["Manifest digest", provenance.manifest_sha256]
  ].forEach(([name, value]) => {
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = name; dd.textContent = value == null || value === "" ? "Not recorded" : String(value);
    $("contentProvenance").append(dt, dd);
  });
  text("contentProvenanceJson", JSON.stringify(report.provenance, null, 2));
}
$("contentScope").onchange = renderContent;
renderContent();

function renderAccounting() {
  const counts = data.summary.reconciliation, processing = data.summary.processing;
  $("runAccounting").hidden = !counts || !processing;
  if (!counts || !processing) return;
  const snapshot = counts.snapshot, intake = counts.intake, review = counts.review;
  status("reconciliationStatus", `Count reconciliation: ${counts.status}. ` + counts.unavailable.join(" "), counts.status === "mismatch");
  reportTable("reconciliationCounts", [
    ["Inventory files", intake?.files ?? "Unavailable"],
    ["Inventory images", intake?.images ?? "Unavailable"],
    ["Eligible / ineligible at intake", intake ? `${intake.eligible_images} / ${intake.ineligible_images}` : "Unavailable"],
    ["Grouped images", review.images],
    ["Included / excluded / unreviewed", ["include", "exclude", "unreviewed"].map(d => review.decisions[d] || 0).join(" / ")],
    ["Snapshot images / unique hashes", `${snapshot.images} / ${snapshot.unique_images}`],
    ["Tagged / without tagged evidence", `${snapshot.tagged_images} / ${snapshot.without_tagged_evidence}`],
    ["Tagged rows outside this snapshot", snapshot.tagged_outside_snapshot],
    ["Available / missing captions", `${snapshot.captions} / ${snapshot.missing_captions}`],
    ["Train / validation images", `${snapshot.split_images.train || 0} / ${snapshot.split_images.validation || 0}`],
    ["Verified export pairs", snapshot.exported_pairs ?? "Group preview"]
  ]);
  text("sourceDisk", intake ? `Recorded source: ${intake.source_bytes.toLocaleString()} bytes across files with known sizes; ${intake.source_image_bytes.toLocaleString()} image bytes; ${intake.files_without_size} file sizes unavailable.` : "Source disk sizes were not captured in this snapshot.");
  reportTable("reconciliationChecks", counts.checks.map(check => [
    check.name, typeof check.expected === "string" ? "Recorded identities" : check.expected,
    typeof check.actual === "string" ? (check.matches ? "Same identities" : "Different identities") : check.actual,
    check.matches ? "Matches" : "MISMATCH"
  ]), 4);
  text("processingTotals", `${processing.recorded_processing_seconds.toFixed(3)} recorded processing seconds · ${processing.recorded_payload_bytes.toLocaleString()} payload bytes · ${processing.recorded_payload_files.toLocaleString()} files across referenced runs.`);
  const gaps = [];
  if (processing.missing_stages.length) gaps.push("Missing stage receipts: " + processing.missing_stages.join(", "));
  if (processing.unmeasured_runs.length) gaps.push(`${processing.unmeasured_runs.length} runs have no measurements`);
  if (processing.partial_scope_runs.length) gaps.push(`${processing.partial_scope_runs.length} runs measure publication only`);
  text("processingGaps", gaps.length ? gaps.join(" · ") + ". Totals cover only recorded work." : "All referenced stages have processing measurements.");
  reportTable("processingStages", processing.stages.map(stage => [
    `${stage.stage} · ${stage.run_id}` + (stage.metrics && stage.metrics.timing_scope !== "stage_processing" ? " (publication only)" : ""),
    stage.metrics?.elapsed_seconds.toFixed(3) ?? "Unavailable",
    stage.metrics?.payload_bytes.toLocaleString() ?? "Unavailable",
    stage.metrics?.payload_files ?? "Unavailable"
  ]), 4);
}
renderAccounting();
