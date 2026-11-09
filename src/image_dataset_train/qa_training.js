// Receipt discovery is live; the QA snapshot and its pilot judgments stay separate.
let trainingState = null, trainingRequest = 0;
const trainingLabels = {
  passed: "Passed", failed: "Failed", not_checked: "Not checked",
  no_current_receipt: "No current receipt", invalid: "Invalid receipt",
  stale: "Different export bytes", other_pin: "Different trainer pin",
  export_invalid: "Export unavailable or changed", history_incomplete: "Receipt history incomplete"
};
function showReceipt() {
  const receipt = trainingState.receipts.find(item => item.id === $("receiptSelect").value);
  $("receiptDetail").hidden = !receipt;
  if (!receipt) return;
  const result = receipt.result;
  text("receiptHeading", (trainingLabels[receipt.status] || receipt.status) +
    (receipt.id === trainingState.latest_receipt ? " · latest for the current pin" : ""));
  status("receiptMessage", receipt.error || result.error ||
    (receipt.exact_export && receipt.current_pin ? "Bound to this export and the current trainer pin." :
      "Historical evidence only; does not qualify this export with the current trainer pin."),
    ["failed", "invalid"].includes(receipt.status));
  text("receiptDate", receipt.completed_at || "Unknown");
  text("receiptPin", `${result.release || "Unknown release"} · ${result.revision || "Unknown revision"}`);
  text("receiptPath", receipt.path);
  text("receiptResult", JSON.stringify(result, null, 2));
  $("receiptSplits").replaceChildren();
  Object.entries(result.splits || {}).forEach(([split, counts]) => {
    const row = document.createElement("tr");
    [split, counts?.images, counts?.images_with_repeats, counts?.batches,
      Object.entries(counts?.buckets || {}).map(([size, count]) => `${size}: ${count}`).join(", ")].forEach(value => {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    });
    $("receiptSplits").append(row);
  });
  $("receiptLinks").replaceChildren();
  Object.entries(receipt.artifacts || {}).forEach(([name, url]) => {
    const link = document.createElement("a"); link.href = url;
    link.target = "_blank"; link.rel = "noopener";
    link.textContent = name === "loader.log" ? "Open loader log" : "Open receipt JSON";
    $("receiptLinks").append(link);
  });
}
function trainingCommand() {
  text("trainingCopyStatus", "");
  $("trainingCommand").value = trainingState?.commands?.[$("trainingShell").value] || "";
}
async function loadTraining() {
  const ticket = ++trainingRequest, preferred = $("receiptSelect").value;
  $("refreshTraining").disabled = true;
  status("trainingMessage", "Checking export and recorded imports…");
  try {
    const result = await api("api/training");
    if (ticket !== trainingRequest) return;
    trainingState = result;
    const exported = result.status !== "not_export";
    $("trainingContent").hidden = !exported;
    $("trainingIndicator").hidden = !exported;
    if (!exported) {
      status("trainingMessage", "This is a group snapshot. Publish a verified export and open its new QA report to inspect trainer receipts.");
      return;
    }
    status("trainingMessage", result.error || "Receipts refreshed. Export integrity and CPU import are evaluated separately.", !!result.error);
    const label = trainingLabels[result.status] || result.status;
    text("trainingIndicator", "CPU dataset import: " + label);
    text("exportIntegrity", result.verification ? "Verified" : "Unavailable or changed");
    text("exportCounts", result.verification ? `${result.verification.images} images · ${result.verification.groups} groups` : result.error);
    text("trainingOutcome", label);
    const pilot = result.pilot_assessment;
    text("trainingPilot", pilot.conclusion?.verdict?.replaceAll("_", " ") || "No conclusion recorded");
    text("trainingPilotProgress", `${pilot.assessed_images} of ${pilot.pilot_images} images assessed. Applies to this QA snapshot only.`);
    text("trainingExport", result.export);
    text("trainingExportHash", result.export_run_sha256 || "Not verified");
    text("trainingPin", `${result.pin.release} · ${result.pin.revision}`);
    text("trainingDependencyPin", result.pin.requirements_sha256);
    text("trainingReceiptRoot", result.receipt_root);
    text("trainingCheckedAt", result.checked_at);
    status("trainingIssues", result.discovery_errors.map(item => item.path + ": " + item.error).join("\n"), true);
    $("receiptSelect").replaceChildren();
    result.receipts.forEach(item => {
      const option = document.createElement("option"); option.value = item.id;
      option.textContent = `${item.completed_at || "Unknown time"} · ${trainingLabels[item.status] || item.status} · ${item.id}`;
      $("receiptSelect").append(option);
    });
    $("receiptSelection").hidden = !result.receipts.length;
    $("noReceipts").hidden = !!result.receipts.length;
    $("receiptSelect").value = result.receipts.some(item => item.id === preferred) ? preferred :
      result.latest_receipt || result.receipts[0]?.id || "";
    showReceipt(); trainingCommand();
  } catch (error) {
    if (ticket !== trainingRequest) return;
    $("trainingContent").hidden = true;
    text("trainingIndicator", "CPU dataset import: unable to refresh");
    status("trainingMessage", error.message, true);
  } finally { if (ticket === trainingRequest) $("refreshTraining").disabled = false; }
}
if (data.session) {
  $("refreshTraining").onclick = loadTraining;
  $("receiptSelect").onchange = showReceipt;
  $("trainingShell").onchange = trainingCommand;
  $("copyTrainingCommand").onclick = async () => {
    try { await navigator.clipboard.writeText($("trainingCommand").value); text("trainingCopyStatus", "Copied"); }
    catch { $("trainingCommand").focus(); $("trainingCommand").select(); text("trainingCopyStatus", "Command selected. Copy it to your terminal."); }
  };
  if (data.summary.split_state === "published") loadTraining();
}
