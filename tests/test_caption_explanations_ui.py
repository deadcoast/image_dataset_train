"""Saved-draft explanations keep their report binding and every unsaved form intact."""

import json
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from test_caption_comparison import build, tree

from image_dataset_train.review_ui import ReviewSession, make_server

ASSETS = Path(__file__).parents[1] / "src/image_dataset_train"


@contextmanager
def serving(fixture):
    with make_server(fixture["config"], fixture["report"]) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def request(server, fixture, *, image="a.png", query=None):
    identifier = fixture["entries"][image]["id"]
    address = server.url + "api/caption-explanation/" + identifier
    if query:
        address += "?" + urlencode(query, doseq=True)
    with urlopen(address, timeout=10) as response:
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


@pytest.mark.parametrize("export", [False, True])
def test_explanation_and_exact_alias_selection_work_offline_without_writes(tmp_path, export):
    fixture = build(tmp_path, export=export)
    fixture["config"].source.rename(tmp_path / "offline-source")
    with serving(fixture) as server:
        before = tree(tmp_path)
        result = request(server, fixture, query={"tag": "blue_hair", "limit": 1})
        assert result["status"] == "available"
        assert result["caption"] == "blue hair"
        assert result["caption"] != fixture["entries"]["a.png"]["caption"]
        assert result["identity"] == {
            "source_path": "a.png",
            "sha256": fixture["entries"]["a.png"]["sha256"],
        }
        assert result["tags"][0]["reasons"] == ["selected"]
        assert result["inference_performed"] is False
        assert result["source_files_read"] is False
        alias = request(server, fixture, image="alias.png")
        assert alias["identity"]["source_path"] == "alias.png"
        assert alias["identity"]["sha256"] == result["identity"]["sha256"]
        assert alias["image_id"] != result["image_id"]
        assert tree(tmp_path) == before


def test_no_draft_and_missing_original_scores_are_explicitly_unavailable(tmp_path):
    (tmp_path / "without-draft").mkdir()
    (tmp_path / "exported").mkdir()
    no_draft = build(tmp_path / "without-draft", draft=False)
    with serving(no_draft) as server:
        result = request(server, no_draft)
        assert result["status"] == "unavailable" and result["reason_code"] == "no_draft"
    exported = build(tmp_path / "exported", export=True)
    exported["drafts"].rename(exported["drafts"].with_name("moved-scored-run"))
    with serving(exported) as server:
        before = tree(tmp_path)
        result = request(server, exported)
        assert result["status"] == "unavailable"
        assert result["reason_code"] == "scored_run_unavailable"
        assert "Restore" in result["reason"]
        assert tree(tmp_path) == before


def test_empty_draft_still_explains_omissions_without_claiming_an_effective_caption(tmp_path):
    from image_dataset_train.qa import create_qa
    from image_dataset_train.tagging import recaption

    fixture = build(tmp_path)
    config = replace(
        fixture["config"], captions=replace(fixture["config"].captions, general_threshold=1.0)
    )
    fixture["drafts"], _ = recaption(config, fixture["drafts"])
    fixture["report"], _ = create_qa(config, fixture["groups"], captions_run=fixture["drafts"])
    with serving(fixture) as server:
        before = tree(tmp_path)
        result = request(server, fixture, query={"tag": "blue_hair"})
        assert result["status"] == "available" and result["caption"] == ""
        assert result["tags"][0]["reasons"] == ["below_or_equal_threshold"]
        assert fixture["entries"]["a.png"]["caption"] == "saved, portrait, portrait"
        assert tree(tmp_path) == before


def test_unsupported_historical_rule_version_is_unavailable(tmp_path):
    from image_dataset_train.qa import create_qa

    fixture = build(tmp_path)
    metadata = fixture["drafts"] / "run.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["caption_version"] = "unknown-historical-version"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    fixture["report"], _ = create_qa(
        fixture["config"], fixture["groups"], captions_run=fixture["drafts"]
    )
    with serving(fixture) as server:
        before = tree(tmp_path)
        result = request(server, fixture)
        assert result["status"] == "unavailable"
        assert result["reason_code"] == "unsupported_caption_version"
        assert tree(tmp_path) == before


def test_missing_optional_score_reader_returns_actionable_unavailable(tmp_path, monkeypatch):
    import builtins

    fixture = build(tmp_path)
    original = builtins.__import__

    def without_numpy(name, *args, **kwargs):
        if name == "image_dataset_train.caption_explanations":
            raise ModuleNotFoundError("No module named numpy", name="numpy")
        return original(name, *args, **kwargs)

    with serving(fixture) as server:
        before = tree(tmp_path)
        monkeypatch.setattr(builtins, "__import__", without_numpy)
        result = request(server, fixture)
        assert result["status"] == "unavailable"
        assert result["reason_code"] == "score_reader_unavailable"
        assert "NumPy" in result["reason"]
        assert tree(tmp_path) == before


@pytest.mark.parametrize(
    "query",
    [
        {"tag": "not_a_model_tag"},
        {"tag": ["blue_hair", "blue_hair"]},
        {"tag": ""},
        {"limit": 201},
        {"offset": -1},
        {"limit": [1, 2]},
        {"caption": "must not save"},
        {"expected_run_sha256": "0" * 64},
    ],
)
def test_explanation_rejects_invalid_selection_and_writes_nothing(tmp_path, query):
    fixture = build(tmp_path)
    with serving(fixture) as server:
        before = tree(tmp_path)
        with pytest.raises(HTTPError) as caught:
            request(server, fixture, query=query)
        assert caught.value.code == 400
        assert json.load(caught.value)["error"]
        assert tree(tmp_path) == before


def test_export_rule_metadata_change_is_not_interpreted_as_frozen_evidence(tmp_path):
    fixture = build(tmp_path, export=True)
    metadata = fixture["drafts"] / "run.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["fixture_note"] = "Different full run than the export captured"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    with serving(fixture) as server:
        before = tree(tmp_path)
        with pytest.raises(HTTPError) as caught:
            request(server, fixture)
        assert "hash mismatch" in json.load(caught.value)["error"]
        assert tree(tmp_path) == before


def test_cached_report_and_late_saved_evidence_change_are_rejected(tmp_path, monkeypatch):
    from image_dataset_train import caption_explanations

    fixture = build(tmp_path)
    session = ReviewSession(fixture["config"], fixture["report"])
    identifier = fixture["entries"]["a.png"]["id"]
    original = caption_explanations.explain_caption

    def mutate_report_after_explanation(*args, **kwargs):
        result = original(*args, **kwargs)
        path = fixture["report"] / "run.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["fixture_note"] = "late metadata change"
        path.write_text(json.dumps(value), encoding="utf-8")
        return result

    monkeypatch.setattr(caption_explanations, "explain_caption", mutate_report_after_explanation)
    with pytest.raises(ValueError, match="changed while explaining"):
        session.caption_explanation(identifier)
    monkeypatch.setattr(caption_explanations, "explain_caption", original)
    with pytest.raises(ValueError, match="reopen the report"):
        session.caption_explanation(identifier)


def test_explanation_controls_are_live_only_outside_disabled_fields():
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.parents, self.attributes = [], {}, {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("id"):
                self.parents[attrs["id"]] = list(self.stack)
                self.attributes[attrs["id"]] = attrs
            if tag not in {"input", "img", "meta", "link", "br", "hr"}:
                self.stack.append((tag, attrs))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

    page = Tags()
    page.feed((ASSETS / "qa_report.html").read_text(encoding="utf-8"))
    for name in ("explainDraftRules", "captionExplanationTag", "inspectCaptionTag"):
        assert not any(tag == "fieldset" for tag, _ in page.parents[name])
        assert any(
            attrs.get("id") == "live" and "hidden" in attrs for _, attrs in page.parents[name]
        )
        assert any(attrs.get("id") == "captionComparison" for _, attrs in page.parents[name])
    assert page.attributes["explainDraftRules"]["type"] == "button"
    assert page.attributes["explainDraftRules"]["aria-controls"] == "captionExplanation"


def test_explanation_client_races_paging_unavailable_and_dirty_form_isolation():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the browser request-race regression")
    result = subprocess.run(
        [node, "-", str(ASSETS / "qa_report.js")],
        input=HARNESS,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


HARNESS = r"""
const assert = require('node:assert/strict'), fs = require('node:fs');
const source = fs.readFileSync(process.argv[2], 'utf8');
const controller = source.slice(source.indexOf('// Draft explanation reads'),
  source.indexOf('// Caption comparison only renders'));
assert.ok(controller.length > 100);
function element() {
  return {value:'',textContent:'',hidden:false,disabled:false,children:[],attributes:{},
    append(...children){this.children.push(...children)},
    replaceChildren(...children){this.children=children},
    setAttribute(name,value){this.attributes[name]=value}};
}
const elements=new Map(), requests=[];
const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
const text=(id,value)=>$(id).textContent=value;
const status=(id,value,error=false)=>{text(id,value);$(id).error=error};
const document={createElement:element};
const api=path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}));
const create=new Function('$','document','text','status','api',`
let data={session:true},matched=[{id:'a',source_path:'a.png',sha256:'aaa'}],current=0,generation=1;
let savedReview={revision:3},correctionDirty=true,assessmentDirty=true,conclusionDirty=true;
${controller}
return {loadCaptionExplanation,resetCaptionExplanation,
baseline:()=>savedReview,dirty:()=>[correctionDirty,assessmentDirty,conclusionDirty],
navigate:()=>{generation++;matched=[{id:'b',source_path:'b.png',sha256:'bbb'}];resetCaptionExplanation(matched[0])}};`);
const controls=create($,document,text,status,api);
function response({id='a',offset=0,run='run1',name='blue_hair',total=25}={}){
 return {status:'available',image_id:id,identity:{source_path:id+'.png',sha256:id.repeat(3)},
 report_sha256:'report1',run:'/saved/run',run_sha256:run,rules_sha256:'rules1',caption_version:'wd-caption-v2',
 caption:'blue hair',summary:{selected:1,omitted:24,near_threshold:1,ratings:0},
 tags:[{name,score:0.3500000238418579,threshold:0.35,threshold_source:'default_general_threshold',
 observed:true,selected:true,near_threshold:true,reasons:['selected'],phrase_status:'emitted'}],
 offset,limit:20,total,has_more:offset+20<total,tag_scope:name==='blue_hair'?'relevant':'requested',
 uncertainty_margin:0.05,subset_rules:[],subset_proposal:{value:null,matches:[]},
 phrases:[{kind:'trigger',text:'<literal>',status:'emitted',duplicate_of:null,position:0},
 {kind:'forced',text:'<LITERAL>',status:'duplicate_phrase',duplicate_of:0,position:1}],
 additions:{trigger:'<literal>',force_tags:['<LITERAL>']}};
}
function allText(el){return [el.textContent,...el.children.map(allText)].join(' ')}
(async()=>{
 const dirty={editCaption:'unsaved caption',editLabels:'labels',editSubset:'subset',
 editReason:'reason',
 assessmentNotes:'assessment',conclusionNotes:'conclusion',publicationSeed:'seed'};
 Object.entries(dirty).forEach(([id,value])=>$(id).value=value);
 assert.equal(requests.length,0,'explanation is lazy');
 let old=$('explainDraftRules').onclick(),older=requests.shift();
 let latest=$('explainDraftRules').onclick(),newer=requests.shift();
 newer.resolve(response());await latest;older.reject(new Error('stale failure'));await old;
 assert.equal($('captionExplanationStatus').error,false);
 assert.match(allText($('captionExplanationRows')),/0.3500000238418579 > 0.35/);
 assert.match(allText($('captionExplanationRows')),/saved model default/);
 assert.match(allText($('captionExplanationPhrases')),/<literal>/);
 assert.match(allText($('captionExplanationPhrases')),/duplicate of phrase 1/);
 assert.equal($('nextCaptionTags').disabled,false);

 latest=$('nextCaptionTags').onclick();newer=requests.shift();
 newer.resolve({image_id:'a',identity:{source_path:'a.png',sha256:'aaa'},
 status:'unavailable',reason:'Restore the recorded caption run.'});await latest;
 assert.match($('captionExplanationStatus').textContent,/Restore the recorded caption run/);
 latest=$('explainDraftRules').onclick();newer=requests.shift();
 newer.resolve(response());await latest;
 latest=$('nextCaptionTags').onclick();newer=requests.shift();
 assert.match(newer.path,/offset=20/);assert.match(newer.path,/expected_run_sha256=run1/);
 newer.resolve(response({offset:20,run:'changed'}));await latest;
 assert.match($('captionExplanationStatus').textContent,/from the first page/);
 assert.equal($('captionExplanationResult').hidden,true);

 latest=$('explainDraftRules').onclick();newer=requests.shift();
 newer.resolve(response());await latest;
 old=$('nextCaptionTags').onclick();older=requests.shift();
 $('captionExplanationTag').value='low_score';let stopped=0;
 $('captionExplanationTag').oninput({stopPropagation(){stopped++}});
 assert.equal(stopped,1);assert.equal($('nextCaptionTags').disabled,true);
 let prevented=0;
 $('captionExplanationTag').onkeydown({key:'Enter',preventDefault(){prevented++},stopPropagation(){stopped++}});
 newer=requests.shift();assert.equal(prevented,1);assert.match(newer.path,/tag=low_score/);
 newer.resolve(response({name:'low_score',total:1}));
 await new Promise(resolve=>setImmediate(resolve));
 older.resolve(response({offset:20}));await old;
 assert.match(allText($('captionExplanationRows')),/low_score/);
 assert.doesNotMatch(allText($('captionExplanationRows')),/blue_hair/);

 old=$('explainDraftRules').onclick();older=requests.shift();controls.navigate();
 older.resolve(response({name:'low_score'}));await old;
 assert.equal($('captionExplanation').hidden,true);
 assert.equal($('captionExplanationRows').children.length,0);
 latest=$('explainDraftRules').onclick();newer=requests.shift();
 newer.resolve({...response({id:'b'}),status:'unavailable',
 reason:'Original saved scores unavailable.'});await latest;
 assert.match($('captionExplanationStatus').textContent,/Original saved scores unavailable/);
 assert.equal($('captionExplanationResult').hidden,true);
 latest=$('showCaptionTags').onclick();newer=requests.shift();
 newer.resolve(response({id:'b'}));await latest;
 assert.equal($('captionExplanationResult').hidden,false);
 latest=$('explainDraftRules').onclick();newer=requests.shift();
 newer.reject(new Error('corrupt scores'));await latest;
 assert.equal($('captionExplanationResult').hidden,true);
 assert.equal($('captionExplanationStatus').error,true);
 Object.entries(dirty).forEach(([id,value])=>assert.equal($(id).value,value));
 assert.deepEqual(controls.baseline(),{revision:3});assert.deepEqual(controls.dirty(),[true,true,true]);
 assert.equal(requests.length,0);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
