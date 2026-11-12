"""Execute the complete image and pair controllers against delayed browser events."""

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / "src/image_dataset_train"


def test_recovery_buttons_are_outside_their_disabled_fields():
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.parents = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("id"):
                self.parents[attrs["id"]] = list(self.stack)
            if tag not in {"input", "img", "br", "meta", "link", "hr"}:
                self.stack.append((tag, attrs))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

    page = Tags()
    page.feed((ASSETS / "qa_report.html").read_text(encoding="utf-8"))
    for name in ("reloadReview", "reloadAssessment", "reloadPair"):
        assert not any(tag == "fieldset" for tag, _ in page.parents[name])
    assert any(attrs.get("id") == "live" for _, attrs in page.parents["reloadReview"])


@pytest.mark.parametrize("scenario", ["images", "forms", "pairs", "static", "empty"])
def test_full_reviewer_controller_recovery(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to exercise the browser controllers")
    result = subprocess.run(
        [node, "-", str(ASSETS), scenario],
        input=HARNESS,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


HARNESS = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const assets = process.argv[2], scenario = process.argv[3];
const elements = new Map(), listeners = new Map(), requests = [], images = [], mediaLoads = [];
class Element {
  constructor(tag = 'div', id = '') {
    this.tagName = tag.toUpperCase(); this.id = id; this.children = []; this.dataset = {};
    this.value = ''; this.textContent = ''; this.disabled = false; this.hidden = false;
    this.checked = false; this.attributes = {}; this.className = ''; this.alt = '';
    this.classList = {toggle() {}};
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  getAttribute(name) { return this.attributes[name]; }
  replaceWith(replacement) { elements.set(this.id, replacement); }
  focus() { document.activeElement = this; }
  scrollIntoView() {}
  select() {}
  click() { if (!this.disabled) return this.onclick?.({preventDefault(){}}); }
  querySelectorAll(selector) {
    const values = [];
    for (const child of this.children) {
      if (child.tagName === selector.toUpperCase()) values.push(child);
      if (child.querySelectorAll) values.push(...child.querySelectorAll(selector));
    }
    return values;
  }
  set src(value) { this.attributes.src = value; mediaLoads.push({image:this,url:value}); }
  get src() { return this.attributes.src; }
}
const html = fs.readFileSync(assets + '/qa_report.html','utf8');
for (const match of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"[^>]*>/g)) {
  const element = new Element(match[1],match[2]);
  element.hidden = /\bhidden(?:>|\s)/.test(match[0]);
  element.disabled = /\bdisabled(?:>|\s)/.test(match[0]); elements.set(match[2],element);
}
const $ = id => { assert.ok(elements.has(id),'Unknown element '+id); return elements.get(id); };
const document = {
  activeElement: new Element('body'), getElementById:$,
  createElement: tag => new Element(tag), createTextNode: text => ({textContent:text}),
  addEventListener: (name,fn) => { if(!listeners.has(name)) listeners.set(name,[]);
    listeners.get(name).push(fn); },
  dispatchEvent: event => (listeners.get(event.type)||[]).forEach(fn=>fn(event)),
  querySelectorAll: selector => {
    if(selector==='#workflowTabs button')
      return ['images','content','pairs','publish','training'].map(name=>$(name+'Tab'));
    if(selector==='.queue button, #coverage button')
      return ['queue','pairQueue','coverage'].flatMap(id=>$(id).querySelectorAll('button'));
    const match = selector.match(/^#(\w+) (\w+)$/);
    return match ? $(match[1]).querySelectorAll(match[2]) : [];
  }
};
const entry = name => ({id:name,source_path:name+'.png',sha256:name.repeat(64),labels:[],
  findings:[],subset:null,split:'train',decision:'include',group_id:'group-'+name,pilot:true,
  caption:'caption '+name,caption_origin:'sidecar',caption_characters:9,caption_words:2,
  preview:'previews/'+name+'.jpg',image_uri:'file:///fixture/'+name+'.png',
  width:128,height:192,errors:[],review_commands:{powershell:'fixture'}});
const data = {session:scenario!=='static',entries:scenario==='empty'?[]:[entry('a'),entry('b')],
  summary:{split_state:'preview',review_revision:1,unresolved_pairs:0,images:2,pilot_images:2,
    groups:2,validation_ratio:0},coverage:{strata:[]},
  publication:{export:{validation_ratio:0.1,seed:1,split_strategy:'size',resolution:512,
    repeats:1},runs:'runs',exports:'exports'}};
$('data').textContent = JSON.stringify(data); $('pairFilter').value = 'unreviewed';
const context = vm.createContext({document,console,URL,URLSearchParams,Map,Promise,
  location:{hash:'',href:'http://127.0.0.1:1234/session/'},history:{replaceState(){}},
  navigator:{clipboard:{writeText:async()=>{}}},
  Image:class extends Element { constructor(){super('img');images.push(this);} },
  Event:class {constructor(type){this.type=type;}},
  setTimeout:()=>1,clearTimeout(){},
  fetch:(path,options={})=>new Promise((resolve,reject)=>requests.push({path,options,reject,
    resolve:value=>resolve({ok:true,json:async()=>value})})),
  showPane:name=>['images','content','pairs','publish','training'].forEach(item=>
    $(item+'Pane').hidden=item!==name),loadTraining(){},reportTable(){}});
vm.runInContext(fs.readFileSync(assets+'/qa_preferences.js','utf8'),context);
vm.runInContext(fs.readFileSync(assets+'/qa_report.js','utf8'),context);
vm.runInContext(fs.readFileSync(assets+'/qa_workflow.js','utf8'),context);
const controls = vm.runInContext(`({loadForms,readCorrection,readAssessment,apply,render,
  loadImagePreview,lockNavigation,
  get:()=>({savedReview,imageAssessmentRevision,correctionDirty,assessmentDirty,
    conclusionDirty,workflowDirty,reviewBusy,assessmentBusy}),
  select:index=>{current=index;render();}, empty:()=>{data.entries=[];apply();}})`,context);
const turn = () => new Promise(resolve=>setImmediate(resolve));
function take(path, method) {
  const index = requests.findIndex(item=>item.path.startsWith(path) &&
    (!method||(item.options.method||'GET')===method));
  assert.notEqual(index,-1,'Missing request '+path); return requests.splice(index,1)[0];
}
function review(revision=1,caption='saved caption') {
  return {revision,decision:'include',caption_override:caption,labels:[],subset:null};
}
function assessment(revision=1) {
  return {state:{revision,images:{}},summary:{revision,assessed_images:0,pilot_images:2,
    remaining_images:2,critical_labels:{},conclusion:null}};
}
async function initial() {
  take('api/review/a').resolve(review()); take('api/assessment').resolve(assessment());
  await turn();
}
function dirtyReview() {
  $('editCaption').value='unsaved caption';$('editLabels').value='unsaved labels';
  $('editSubset').value='unsaved subset';$('editReason').value='reason';
  $('correctionForm').oninput({target:$('editCaption')});
}
function dirtyAssessment() {
  $('assessmentNotes').value='unsaved assessment';$('assessmentForm').oninput();
  $('conclusionNotes').value='unsaved conclusion';$('conclusionForm').oninput();
}
function pair(id='p1') {return {pair_id:id,left_source_path:'a.png',right_source_path:'b.png',
  left_image:'pair-image/a',right_image:'pair-image/b',decision:'unreviewed',reason:'saved',
  hamming_distance:2};}
function queue(pairs=[pair()],counts={unreviewed:1},total=pairs.length) {
  return {revision:7,pairs,pair_total:total,pair_next_offset:null,pair_counts:counts,
    image_counts:{include:2},groups:2};
}
(async()=>{
  if(scenario==='empty') {
    assert.equal($('saveReview').disabled,true);assert.equal($('saveAssessment').disabled,true);
    assert.equal($('conclusionFields').disabled,true);
    await $('reloadConclusion').onclick();
    assert.equal(requests.filter(item=>item.path==='api/assessment').length,1);
    take('api/assessment').reject(new Error('initial unavailable'));await turn();
    assert.equal($('conclusionFields').disabled,false);
    const reload=$('reloadConclusion').click();take('api/assessment').resolve(assessment(4));
    await reload;assert.match($('conclusionStatus').textContent,/reloaded/);
    assert.equal(controls.get().savedReview,null);
    assert.equal(controls.get().imageAssessmentRevision,null);
    assert.equal($('showAllImages').hidden,true);
    return;
  }
  if(scenario==='static') {
    assert.equal(requests.length,0); assert.equal($('live').hidden,true);
    $('search').value='no matches';$('search').oninput();
    assert.equal($('empty').hidden,false);assert.equal($('showAllImages').hidden,false);
    $('showAllImages').click();assert.equal($('detail').hidden,false);
    controls.empty();assert.match($('emptyMessage').textContent,/contains no images/);
    assert.equal($('showAllImages').hidden,true);assert.equal($('saveReview').disabled,true);
    $('emptySnapshot').click();assert.equal($('contentPane').hidden,false);
    return;
  }
  if(scenario==='images') {
    await initial(); const first = images[0]; const beforeLoads=mediaLoads.length;
    first.onload();assert.equal($('preview'),first);
    assert.equal(mediaLoads.length,beforeLoads,'Loaded image must not be fetched twice');
    const firstURL=first.src;controls.loadImagePreview();const ordinaryReload=images.at(-1);
    assert.notEqual(ordinaryReload.src,firstURL,'Ordinary reload must bypass decoded-image reuse');
    assert.equal(new URL(ordinaryReload.src).pathname,new URL(firstURL).pathname);
    assert.equal(mediaLoads.length,beforeLoads+1);
    ordinaryReload.onload();assert.equal($('preview'),ordinaryReload);
    assert.equal(mediaLoads.length,beforeLoads+1,'Reload must display its already-loaded node');
    dirtyReview();dirtyAssessment();
    controls.loadImagePreview(true);const old=images.at(-1);old.onerror();
    assert.equal($('retryPreview').disabled,false);assert.equal($('noPreview').hidden,false);
    $('retryPreview').click(); const retried=images.at(-1);
    assert.match(retried.src,/retry=/);retried.onload();
    assert.equal($('preview'),retried);assert.equal($('editCaption').value,'unsaved caption');
    assert.equal($('assessmentNotes').value,'unsaved assessment');
    assert.equal($('conclusionNotes').value,'unsaved conclusion');
    assert.equal(controls.get().savedReview.revision,1);
    const mediaBeforeMissing=mediaLoads.length;
    vm.runInContext('data.entries[0].preview=null;loadImagePreview()',context);
    assert.equal(mediaLoads.length,mediaBeforeMissing);
    assert.match($('noPreview').textContent,/No preview was saved/);
    assert.equal($('retryPreview').hidden,true);
    assert.equal($('openImage').href,'image/a');
    controls.select(1);const next=images.at(-1);old.onerror();
    assert.match($('noPreview').textContent,/Loading/);
    next.onerror();assert.equal($('preview').hidden,true);
    assert.equal($('retryPreview').hidden,false);
    // Force a no-entry transition while requests are pending; old baselines cannot revive.
    const oldRead=take('api/review/b');controls.empty();oldRead.resolve(review(99));
    await turn();assert.equal(controls.get().savedReview,null);
    assert.equal(controls.get().imageAssessmentRevision,null);
    assert.equal($('saveReview').disabled,true);assert.equal($('saveAssessment').disabled,true);
    assert.match($('emptyMessage').textContent,/contains no images/);
  }
  if(scenario==='forms') {
    take('api/review/a').reject(new Error('source offline'));
    take('api/assessment').reject(new Error('assessment offline'));await turn();
    assert.equal($('reloadReview').disabled,false);assert.equal($('reloadAssessment').disabled,false);
    assert.equal($('saveReview').disabled,true);assert.equal($('saveAssessment').disabled,true);
    assert.match($('reloadReview').textContent,/Retry/);
    const retry=$('reloadReview').click();const request=take('api/review/a');
    assert.equal($('reloadReview').disabled,true);assert.equal($('next').disabled,true);
    await controls.readCorrection(); await $('correctionForm').onsubmit({preventDefault(){}});
    assert.equal(requests.filter(item=>item.path==='api/review/a').length,0);
    request.resolve(review(2));await retry;
    const assessRetry=$('reloadAssessment').click();take('api/assessment').resolve(assessment(2));
    await assessRetry;dirtyReview();dirtyAssessment();
    const failed=$('reloadReview').click();take('api/review/a').reject(new Error('offline again'));
    await failed;assert.equal($('editCaption').value,'unsaved caption');
    assert.equal(controls.get().savedReview.revision,2);assert.equal(controls.get().correctionDirty,true);
    assert.equal($('assessmentNotes').value,'unsaved assessment');
    const reload=$('reloadReview').click();take('api/review/a').resolve(review(3,'restored'));
    await reload;assert.equal($('editCaption').value,'restored');
    assert.equal($('assessmentNotes').value,'unsaved assessment');
    assert.equal($('conclusionNotes').value,'unsaved conclusion');
    dirtyReview();const save=$('correctionForm').onsubmit({preventDefault(){}});
    const saved=take('api/review/a','POST');await controls.readCorrection();
    assert.equal($('reloadReview').disabled,true);assert.equal($('next').disabled,true);
    assert.equal(JSON.parse(saved.options.body).expected_revision,3);
    saved.resolve(review(4));await save;assert.equal(controls.get().savedReview.revision,4);
    assert.equal($('assessmentNotes').value,'unsaved assessment');
    const ar=$('reloadAssessment').click();const obsolete=take('api/assessment');
    assert.equal($('saveAssessment').disabled,true);assert.equal($('conclusionFields').disabled,true);
    controls.select(1);const newAssessment=take('api/assessment');
    newAssessment.resolve(assessment(8));take('api/review/b').resolve(review(8));await turn();
    obsolete.resolve(assessment(3));await ar;
    assert.equal(controls.get().imageAssessmentRevision,8);
    // Image assessment save and conclusion save share a revision: serialize them.
    const as=$('assessmentForm').onsubmit({preventDefault(){}});
    const assessmentSave=take('api/assessment','POST');
    await $('conclusionForm').onsubmit({preventDefault(){}});
    assert.equal(requests.filter(item=>item.path==='api/assessment').length,0);
    assessmentSave.resolve(assessment(9));await as;
    assert.equal(controls.get().imageAssessmentRevision,9);
  }
  if(scenario==='pairs') {
    await initial();$('pairsTab').click();take('api/pairs').resolve(queue());await turn();
    assert.equal($('pairDetail').hidden,false);
    const left=images.at(-2);left.onerror();
    $('pairDecision').value='related';$('pairReason').value='unsaved pair';$('pairForm').oninput();
    $('retryLeftPairImage').click();images.at(-1).onload();
    assert.equal($('pairReason').value,'unsaved pair');
    assert.equal(controls.get().workflowDirty,true);
    const reload=$('reloadPair').click();const request=take('api/compare');
    assert.equal($('savePair').disabled,true);assert.equal($('reloadPair').disabled,true);
    await $('pairForm').onsubmit({preventDefault(){}});
    assert.equal(requests.filter(item=>item.path==='api/pairs').length,0);
    request.reject(new Error('offline'));await reload;
    assert.equal($('pairReason').value,'unsaved pair');
    assert.equal(controls.get().workflowDirty,true);
    assert.equal($('pairDetail').hidden,false);assert.match($('pairMessage').textContent,/preserved/);
    const recovered=$('reloadPair').click();take('api/compare').resolve({revision:8,pair:pair()});
    await recovered;assert.equal($('pairReason').value,'saved');
    assert.equal(controls.get().workflowDirty,false);
    const unavailable=$('refreshPairs').click();take('api/pairs').reject(new Error('offline'));
    await unavailable;assert.equal($('pairDetail').hidden,true);
    assert.equal($('pairQueue').children.length,0);assert.equal($('savePair').disabled,true);
    assert.match($('pairMessage').textContent,/queue unavailable/);
    const allDone=$('refreshPairs').click();take('api/pairs').resolve(queue([],{related:2},0));
    await allDone;assert.match($('pairMessage').textContent,/No unresolved pairs/);
    assert.equal($('showAllPairs').hidden,false);
    $('showAllPairs').click();const all=take('api/pairs');assert.match(all.path,/decision=all/);
    all.resolve(queue([pair()],{related:1}));await turn();
    const empty=$('refreshPairs').click();take('api/pairs').resolve(queue([],{},0));await empty;
    assert.match($('pairMessage').textContent,/No saved or proposed/);
    assert.equal($('openManualPair').hidden,false);$('openManualPair').click();
    assert.equal($('manualPair').open,true);assert.equal(document.activeElement,$('manualLeft'));
    const manual=$('comparePair').click();take('api/compare').reject(new Error('wrong path'));
    await manual;assert.equal($('pairDetail').hidden,true);
    assert.equal($('savePair').disabled,true);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
