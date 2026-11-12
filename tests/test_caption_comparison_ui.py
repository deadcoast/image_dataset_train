"""Caption previews are read-only and never replace the editor's saved baseline."""

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

from image_dataset_train.review_ui import ReviewSession, make_server
from image_dataset_train.reviews import review_image


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


def selected(server, path="a.png"):
    return next(
        entry["id"]
        for entry in server.review_sessions[""].data["entries"]
        if entry["source_path"] == path
    )


def request(server, identifier, proposed=None, *, origin=True):
    headers = {}
    if proposed is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://{server.authority}"
    with urlopen(
        Request(
            server.url + "api/caption-comparison/" + identifier,
            data=None if proposed is None else json.dumps(proposed).encode(),
            headers=headers,
        ),
        timeout=10,
    ) as response:
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


def test_get_and_proposed_actions_preserve_all_saved_bytes(live, tmp_path):
    identifier = selected(live)
    before = snapshot(tmp_path)
    current = request(live, identifier)
    assert current["image_id"] == identifier
    assert current["snapshot_revision"] == 0 and current["current_revision"] == 3
    assert current["candidates"]["override"]["text"] == "second caption"
    assert current["candidates"]["sidecar"]["text"] == "caption a"
    assert current["candidates"]["draft"]["status"] == "absent"
    assert current["snapshot"]["caption"] == "caption a"
    assert current["effective"]["keep"]["text"] == "second caption"
    assert current["effective"]["clear"]["text"] == "caption a"
    assert current["source_revalidated"] is False and current["derivative_preview"] is False
    replaced = request(
        live, identifier, {"action": "replace", "caption": "  new,\n caption 日本語 "}
    )
    assert replaced["effective"]["proposed"]["text"] == "new, caption 日本語"
    assert replaced["proposed_action"] == "replace" and replaced["literal_changes"]
    cleared = request(live, identifier, {"action": "clear"})
    assert cleared["effective"]["proposed"]["text"] == "caption a"
    assert snapshot(tmp_path) == before


def test_frozen_export_comparison_is_available_when_corrections_are_offline(
    live, history, tmp_path
):
    config, _, _, _, _, _ = history
    config.source.rename(config.source.with_name("offline source"))
    before = snapshot(tmp_path)
    identifier = selected(live)
    with pytest.raises(HTTPError):
        urlopen(live.url + "api/review/" + identifier, timeout=10)
    value = request(live, identifier, {"action": "clear"})
    assert value["effective"]["proposed"]["text"] == "caption a"
    assert value["candidates"]["sidecar"]["provenance"]["evidence"] == "captured_export"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "proposed",
    [
        {},
        {"action": "publish"},
        {"action": "replace", "caption": 42},
        {"action": "clear", "save": True},
        {"action": "clear", "expected_revision": 3},
    ],
)
def test_preview_rejects_unknown_mutation_fields(live, tmp_path, proposed):
    before = snapshot(tmp_path)
    with pytest.raises(HTTPError) as caught:
        request(live, selected(live), proposed)
    assert caught.value.code == 400
    assert json.load(caught.value)["error"]
    assert snapshot(tmp_path) == before


def test_preview_post_requires_the_session_origin(live, tmp_path):
    before = snapshot(tmp_path)
    with pytest.raises(HTTPError) as caught:
        request(live, selected(live), {"action": "clear"}, origin=False)
    assert caught.value.code == 403
    assert snapshot(tmp_path) == before


def test_unknown_image_and_changed_cached_report_are_rejected(live, tmp_path):
    with pytest.raises(HTTPError) as caught:
        request(live, "unknown-image")
    assert caught.value.code == 400
    session = live.review_sessions[""]
    metadata = session.run / "run.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["fixture_note"] = "Valid report metadata changed after browser load"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(HTTPError) as caught:
        request(live, selected(live), {"action": "clear"})
    assert caught.value.code == 409
    assert "reopen the report" in json.load(caught.value)["error"]
    fresh = ReviewSession(session.config, session.run)
    assert fresh.caption_comparison(selected(live))["current_revision"] == 3
    assert snapshot(tmp_path) == before


def test_comparison_reads_new_revision_without_advancing_saved_editor_guard(
    live, history, tmp_path
):
    config, _, _, similarity, _, _ = history
    identifier = selected(live)
    session = live.review_sessions[""]
    editor = session.review(identifier)
    review_image(config, similarity, "b.png", caption="other editor", reason="fixture")
    before = snapshot(tmp_path)
    inspected = request(live, identifier)
    assert inspected["current_revision"] == editor["revision"] + 1
    with pytest.raises(ValueError, match="changed"):
        session.review(
            identifier,
            {"caption": "stale edit", "reason": "fixture", "expected_revision": editor["revision"]},
        )
    assert snapshot(tmp_path) == before


def test_comparison_is_hidden_in_static_report_and_independent_of_disabled_editor(history):
    _, _, prepared, _, _, _ = history

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.ancestors = None

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if attributes.get("id") == "captionComparison":
                self.ancestors = list(self.stack)
            if tag not in {"input", "meta", "link", "img", "br", "hr"}:
                self.stack.append((tag, attributes))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

    page = Tags()
    page.feed((Path(prepared["outputs"]["qa"]["path"]) / "report.html").read_text(encoding="utf-8"))
    assert page.ancestors is not None
    assert any(attrs.get("id") == "live" and "hidden" in attrs for _, attrs in page.ancestors)
    assert any(attrs.get("id") == "correctionForm" for _, attrs in page.ancestors)
    assert not any(tag == "fieldset" for tag, _ in page.ancestors)


def test_client_action_races_dirty_fields_offline_and_reordered_phrases():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the browser request-race regression")
    script = Path(__file__).parents[1] / "src/image_dataset_train/qa_report.js"
    harness = r"""
const assert = require("node:assert/strict"), fs = require("node:fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const controller = source.slice(source.indexOf("// Caption comparison only renders"),
  source.indexOf("function fillReview("));
assert.ok(controller.length > 100);
function element() {
  return {value: "", textContent: "", disabled: false, children: [],
    classList: {toggle() {}}, append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }};
}
const elements = new Map(), requests = [], timers = new Map(); let timerID = 0;
const $ = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
const document = {createElement: element};
const text = (id, value) => $(id).textContent = value;
const status = (id, value, error = false) => { text(id, value); $(id).error = error; };
const api = (path, payload) => new Promise((resolve, reject) =>
  requests.push({path, payload, resolve, reject}));
const setTimeout = callback => { timers.set(++timerID, callback); return timerID; };
const clearTimeout = id => timers.delete(id);
const context = `let data = {session:true}, matched = [{id:"a",source_path:"a.png",sha256:"aaa"}],
  current = 0, generation = 1, savedReview = {revision:3};`;
const create = new Function("$", "document", "text", "status", "api",
  "setTimeout", "clearTimeout", context + controller + `
  return {loadCaptionComparison, scheduleCaptionComparison, resetCaptionComparison,
    captionEvidenceLabel,
    baseline: () => savedReview, setBaseline: value => savedReview = value,
    navigate: () => { generation++; matched = [{id:"b",source_path:"b.png",sha256:"bbb"}];
      resetCaptionComparison(matched[0]); }};`);
const controls = create($, document, text, status, api, setTimeout, clearTimeout);
function response(action = "keep", revision = 3, caption = "new, caption", id = "a") {
  const outcome = {status:"present", text:caption,
    provenance:{kind:"override",evidence:"current_review"},error:null};
  const candidate = {...outcome, normalized_text:caption};
  return {image_id:id, identity:{source_path:id+".png",sha256:id.repeat(3)},
    snapshot_revision:0, current_revision:revision, proposed_action:action,
    candidates:{override:candidate, sidecar:{...candidate,
      provenance:{kind:"sidecar",evidence:"captured_export"}},
      draft:{...candidate,status:"absent",text:null,provenance:{}}},
    effective:{keep:outcome,clear:outcome,proposed:outcome}, evidence_warnings:[],
    literal_changes_available:true,literal_changes_total:0,literal_changes:[],
    literal_changes_truncated:false,literal_text_changed:false};
}
function flushTimer() {
  assert.equal(timers.size, 1); const [id, callback] = [...timers.entries()][0];
  timers.delete(id); return callback();
}
(async () => {
  assert.equal(controls.captionEvidenceLabel({evidence:"source_sidecar",source_checked:false}),
    "Recorded source sidecar");
  assert.equal(controls.captionEvidenceLabel({evidence:"source_sidecar",source_checked:true}),
    "Checked source sidecar");
  assert.equal(controls.captionEvidenceLabel({evidence:"captured_export"}),
    "Export snapshot evidence");
  $("captionAction").value = "keep";
  const dirty = {editCaption:"unsaved caption", editLabels:"unsaved labels",
    editSubset:"unsaved subset", editReason:"reason", assessmentNotes:"unsaved assessment",
    conclusionNotes:"unsaved conclusion", publicationSeed:"unsaved seed"};
  Object.entries(dirty).forEach(([id,value]) => $(id).value = value);
  let old = controls.loadCaptionComparison(), previous = requests.shift();
  assert.equal(previous.payload, undefined);
  $("captionAction").value = "clear"; controls.scheduleCaptionComparison();
  let current = flushTimer(), latest = requests.shift();
  assert.equal(latest.payload.action, "clear");
  $("captionAction").value = "replace"; $("editCaption").value = "typed, <caption>";
  controls.scheduleCaptionComparison();
  const replacement = flushTimer(), replacementRequest = requests.shift();
  assert.equal(replacementRequest.payload.caption, "typed, <caption>");
  replacementRequest.resolve(response("replace", 3, "typed, <caption>")); await replacement;
  latest.resolve(response("clear", 3, "old clear")); await current;
  previous.reject(new Error("old network error")); await old;
  assert.equal($("captionComparisonEffective").textContent, "typed, <caption>");
  assert.equal($("captionComparisonStatus").error, false);

  old = controls.loadCaptionComparison(); previous = requests.shift();
  $("editCaption").value = "newer typed text"; controls.scheduleCaptionComparison();
  previous.resolve(response("replace", 3, "stale text")); await old;
  assert.notEqual($("captionComparisonEffective").textContent, "stale text");
  current = flushTimer(); latest = requests.shift();
  latest.resolve(response("replace", 4, "newer typed text")); await current;
  assert.match($("captionComparisonStatus").textContent, /form still uses revision 3/);
  assert.equal(controls.baseline().revision, 3);
  assert.equal($("editCaption").value, "newer typed text");
  Object.entries(dirty).filter(([id]) => id !== "editCaption").forEach(([id,value]) =>
    assert.equal($(id).value, value));

  old = controls.loadCaptionComparison(); previous = requests.shift();
  controls.setBaseline({revision:4});
  previous.resolve(response("replace", 3, "late before reload")); await old;
  assert.notEqual($("captionComparisonEffective").textContent, "late before reload");
  current = controls.loadCaptionComparison(); latest = requests.shift();
  latest.resolve({...response("replace", 4, "caption, new"),literal_text_changed:true});
  await current;
  assert.match($("captionComparisonChangesStatus").textContent, /phrase counts are unchanged/);

  old = controls.loadCaptionComparison(); previous = requests.shift(); controls.navigate();
  previous.resolve(response("replace", 4, "wrong image")); await old;
  assert.equal($("captionComparisonEffective").textContent, "");
  controls.setBaseline(null);
  current = $("refreshCaptionComparison").onclick(); latest = requests.shift();
  assert.equal(latest.payload, undefined);
  latest.resolve(response("keep", 4, "frozen offline caption", "b")); await current;
  assert.equal($("captionComparisonEffective").textContent, "frozen offline caption");
  assert.equal(controls.baseline(), null);

  current = controls.loadCaptionComparison(); latest = requests.shift();
  latest.reject(new Error("missing provenance")); await current;
  assert.match($("captionComparisonStatus").textContent, /Comparison unavailable: missing/);
  assert.equal($("captionComparisonCandidates").children.length, 0);
  assert.equal($("captionComparisonEffective").textContent, "");
  assert.equal($("editLabels").value, dirty.editLabels);
  assert.equal($("assessmentNotes").value, dirty.assessmentNotes);
  assert.equal(requests.length, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-", str(script)], input=harness, text=True, capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr
