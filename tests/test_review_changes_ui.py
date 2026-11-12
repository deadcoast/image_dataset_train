"""Live metadata inspection remains read-only, report-bound and stable while paging."""

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_preparation import collection as collection
from test_review_history_cli import history as history
from test_review_history_cli import snapshot

from image_dataset_train.review_changes import inspect_review_changes
from image_dataset_train.review_ui import ReviewSession, make_server
from image_dataset_train.reviews import ReviewConflict, review_image


@pytest.fixture
def live(history):
    config, _, prepared, _, _, _ = history
    with make_server(config, Path(prepared["outputs"]["qa"]["path"])) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def get(server, query=""):
    with urlopen(server.url + "api/review-changes" + query, timeout=10) as response:
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


def test_offline_get_pages_filters_and_session_inspection_preserve_bytes(live, history, tmp_path):
    config, _, _, _, _, _ = history
    config.source.rename(config.source.with_name("offline collection"))
    before = snapshot(tmp_path)
    first = get(live, "?limit=1")
    assert first["state"] == "changed" and first["net_change_count"] == 2
    assert first["snapshot_revision"] == 0 and first["current_revision"] == 3
    assert first["source_revalidated"] is False and first["metadata_verified"] is True
    assert len(first["differences"]) == 1 and first["next_offset"] == 1
    second = get(live, "?limit=1&offset=1")
    assert second["inspection_sha256"] == first["inspection_sha256"]
    assert second["differences"][0]["key"] != first["differences"][0]["key"]
    pairs = get(live, "?kind=pairs")
    assert pairs["state"] == "changed" and pairs["filtered_count"] == 0
    assert pairs["counts"]["images"] == 2 and pairs["differences"] == []
    assert live.review_sessions[""].review_changes(limit=1) == first
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "query", ["?limit=0", "?limit=201", "?offset=-1", "?offset=bad", "?kind=unknown"]
)
def test_invalid_get_is_an_explicit_read_only_failure(live, tmp_path, query):
    before = snapshot(tmp_path)
    with pytest.raises(HTTPError) as caught:
        get(live, query)
    assert caught.value.code == 400
    assert json.load(caught.value)["error"]
    assert snapshot(tmp_path) == before


def test_new_review_changes_the_paging_identity(live, history):
    config, _, _, similarity, _, _ = history
    old = get(live, "?limit=1")
    review_image(config, similarity, "c.png", caption="late fixture correction", reason="fixture")
    current = get(live, "?limit=1&offset=1")
    assert current["current_revision"] == 4
    assert current["inspection_sha256"] != old["inspection_sha256"]


def test_report_rewrite_requires_reopening_cached_page(live, tmp_path):
    session = live.review_sessions[""]
    metadata = session.run / "run.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["fixture_note"] = "valid metadata changed after page load"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    before = snapshot(tmp_path)
    # A valid rewritten report is inspectable by a fresh reader, but cannot replace
    # the report already displayed by this cached browser session.
    fresh = inspect_review_changes(session.config, session.similarity, session.run)
    assert fresh["report_sha256"] != session.assessments.digest
    with pytest.raises(ReviewConflict, match="reopen the report"):
        session.review_changes()
    with pytest.raises(HTTPError) as caught:
        get(live)
    assert "reopen the report" in json.load(caught.value)["error"]
    assert ReviewSession(session.config, session.run).review_changes()["state"] == "changed"
    assert snapshot(tmp_path) == before


def test_changes_endpoint_cannot_publish_or_write(live, tmp_path):
    before = snapshot(tmp_path)
    request = Request(
        live.url + "api/review-changes",
        data=b"{}",
        headers={"Content-Type": "application/json", "Origin": f"http://{live.authority}"},
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=10)
    assert caught.value.code == 404
    assert snapshot(tmp_path) == before


def test_static_report_keeps_live_changes_controls_hidden(history):
    _, _, prepared, _, _, _ = history

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if "id" in attrs:
                self.ids[attrs["id"]] = attrs

    page = Tags()
    page.feed((Path(prepared["outputs"]["qa"]["path"]) / "report.html").read_text(encoding="utf-8"))
    assert "hidden" in page.ids["publishPane"] and "hidden" in page.ids["publishTab"]
    assert (
        "disabled" in page.ids["reviewChangesPrev"] and "disabled" in page.ids["reviewChangesNext"]
    )


def test_client_late_responses_paging_drift_errors_and_unsaved_settings():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the browser request-race regression")
    script = Path(__file__).parents[1] / "src/image_dataset_train/qa_workflow.js"
    # Exercise the actual independent changes controller with deferred requests.
    # Rendering, real DOM controls and responsive layout are qualified separately.
    harness = r"""
const assert = require("node:assert/strict"), fs = require("node:fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const controller = source.slice(source.indexOf("  let reviewChangesRequest"),
  source.indexOf("  const defaults = data.publication;"));
assert.ok(controller.length > 100);
function element() {
  return {value: "", textContent: "", disabled: false, children: [],
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }};
}
const elements = new Map(), listeners = new Map(), requests = [];
const $ = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
const document = {createElement: element,
  addEventListener: (name, handler) => listeners.set(name, handler)};
const text = (id, value) => $(id).textContent = value;
const status = (id, value, error = false) => { text(id, value); $(id).error = error; };
const api = path => new Promise((resolve, reject) => requests.push({path, resolve, reject}));
const create = new Function("$", "document", "text", "status", "api",
  controller + "\nreturn {loadReviewChanges};");
const {loadReviewChanges} = create($, document, text, status, api);
function response(revision, offset = 0) {
  return {state: "changed", snapshot_revision: 0, current_revision: revision,
    history_delta_count: revision, net_change_count: 25,
    counts: {images: 25, pairs: 0, outside_report: 0}, filtered_count: 25,
    offset, next_offset: offset ? null : 20, inspection_sha256: "evidence-" + revision,
    differences: [{kind: "images",
      identity: {source_path: "item-" + revision + ".png", sha256: "a".repeat(64)},
      report_membership: "in_report", inventory_compatible: true,
      changes: [{field: "caption_override", before_present: false,
        after_present: true, after: "<unsafe html>"}]}]};
}
const turn = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  $("publicationRatio").value = "31"; $("publicationSeed").value = "typed unsaved seed";
  let old = loadReviewChanges(), oldRequest = requests.shift();
  let newer = loadReviewChanges(), newRequest = requests.shift();
  newRequest.resolve(response(2)); await newer;
  oldRequest.resolve(response(1)); await old;
  assert.match($("reviewChangesRevision").textContent, /current revision 2/);
  assert.equal($("reviewChangesList").children[0].children[0].textContent, "item-2.png");
  assert.equal($("reviewChangesList").children[0].children[3].children[2].textContent,
    "Snapshot: <absent>\nCurrent: \"<unsafe html>\"");
  old = loadReviewChanges(); oldRequest = requests.shift();
  newer = loadReviewChanges(); newRequest = requests.shift();
  newRequest.resolve(response(2)); await newer;
  oldRequest.reject(new Error("late network failure")); await old;
  assert.equal($("reviewChangesStatus").error, false);
  assert.match($("reviewChangesRevision").textContent, /current revision 2/);

  const paging = $("reviewChangesNext").onclick();
  let request = requests.shift(); assert.match(request.path, /offset=20/);
  request.resolve(response(3, 20)); await turn();
  request = requests.shift(); assert.match(request.path, /offset=0/);
  request.resolve(response(3)); await paging;
  assert.match($("reviewChangesStatus").textContent,
    /changed while paging; showing the first page/);
  assert.match($("reviewChangesRevision").textContent, /current revision 3/);
  assert.equal($("reviewChangesPrev").disabled, true);
  assert.equal($("reviewChangesNext").disabled, false);

  $("reviewChangesKind").value = "pairs";
  const filtering = $("reviewChangesKind").onchange(); request = requests.shift();
  assert.match(request.path, /kind=pairs/); assert.match(request.path, /offset=0/);
  request.resolve({...response(3), differences: [], filtered_count: 0, next_offset: null});
  await filtering;
  assert.match($("reviewChangesStatus").textContent, /25 saved records differ/);
  assert.match($("reviewChangesPage").textContent, /No matching/);

  listeners.get("reviews-saved")(); request = requests.shift();
  assert.match(request.path, /offset=0/); request.resolve(response(4)); await turn();
  assert.match($("reviewChangesRevision").textContent, /current revision 4/);
  const failed = $("refreshReviewChanges").onclick();
  requests.shift().reject(new Error("offline metadata")); await failed;
  assert.match($("reviewChangesStatus").textContent, /Changes unavailable: offline metadata/);
  assert.equal($("reviewChangesList").children.length, 0);
  assert.equal($("reviewChangesRevision").textContent, "");
  assert.equal($("reviewChangesNext").disabled, true);
  assert.equal($("reviewChangesPrev").disabled, true);
  assert.equal($("publicationRatio").value, "31");
  assert.equal($("publicationSeed").value, "typed unsaved seed");
  assert.equal(requests.length, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-", str(script)], input=harness, text=True, capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr
