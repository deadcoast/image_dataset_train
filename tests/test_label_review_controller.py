"""Exercise the actual label controller's save, preview and recovery boundaries."""

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / "src/image_dataset_train"


def test_label_recovery_controls_remain_outside_hidden_or_disabled_editors():
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.parents = [], {}

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
    page.feed((ASSETS / "label_review.html").read_text(encoding="utf-8"))
    for name in ("reload", "showAll", "status", "retryWorkspace"):
        assert not any(
            attrs.get("id") in {"labelDetail", "judgmentForm"} or tag == "fieldset"
            for tag, attrs in page.parents[name]
        )
    assert not any(attrs.get("id") == "reviewPanel" for _, attrs in page.parents["retryWorkspace"])
    assert not any(tag in {"form", "fieldset"} for tag, _ in page.parents["retryImage"])


@pytest.mark.parametrize(
    "scenario",
    [
        "eligibility",
        "save_button",
        "save_form",
        "save_keyboard",
        "save_next",
        "empty",
        "media_races",
        "dirty_retry",
        "reload_conflict",
        "initial_retry",
        "pending_completion",
    ],
)
def test_actual_label_controller(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the label controller")
    result = subprocess.run(
        [node, "-", str(ASSETS), scenario],
        input=HARNESS,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


HARNESS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const assets=process.argv[2],scenario=process.argv[3];
const elements=new Map(),events=new Map(),requests=[],images=[],media=[];
class Element {
  constructor(tag='div',id='') {
    this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.value='';
    this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';
    this.dataset={};this.style={};this.attributes={};this.className='';
    this.classList={toggle(){return false;}};
  }
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];}
  replaceWith(value){elements.set(this.id,value);}
  querySelectorAll(selector) {
    const tags=selector.toUpperCase().split(',');
    return this.children.flatMap(child=>[...(tags.includes(child.tagName)?[child]:[]),
      ...(child.querySelectorAll?.(selector)||[])]);
  }
  click(){if(!this.disabled)return this.id==='save'?
    $('judgmentForm').onsubmit({preventDefault(){}}):this.onclick?.();}
  set src(value){this.attributes.src=value;media.push({image:this,url:value});}
  get src(){return this.attributes.src;}
}
const html=fs.readFileSync(assets+'/label_review.html','utf8');
for(const match of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"[^>]*>/g)){
  const el=new Element(match[1],match[2]);el.hidden=/\bhidden(?:>|\s)/.test(match[0]);
  elements.set(match[2],el);
}
const $=id=>{assert.ok(elements.has(id),'Missing '+id);return elements.get(id);};
const context=vm.createContext({console,URL,location:{href:'http://127.0.0.1:1234/session/'},
  document:{getElementById:$,createElement:tag=>new Element(tag),
    addEventListener:(name,fn)=>events.set(name,fn)},
  window:{addEventListener:(name,fn)=>events.set(name,fn)},
  Image:class extends Element{constructor(){super('img');images.push(this);}},
  fetch:(path,options={})=>new Promise((resolve,reject)=>requests.push({path,options,reject,
    resolve:(value,ok=true)=>resolve({ok,json:async()=>value})}))});
vm.runInContext(fs.readFileSync(assets+'/label_review.js','utf8'),context);
const state=(revision=0,judgments={})=>({revision,judgments,labels:['blue_hair','red_eyes'],
  members:[{sha256:'a'.repeat(64),paths:['a.png']},{sha256:'b'.repeat(64),paths:['b.png']}],
  summary:{unreviewed_labels:4-Object.values(judgments).reduce((sum,row)=>sum+Object.keys(row).length,0)},comparison_models:1});
const turn=()=>new Promise(resolve=>setImmediate(resolve));
function take(path){
  const index=requests.findIndex(item=>item.path===path);assert.notEqual(index,-1,'Missing '+path);
  return requests.splice(index,1)[0];
}
const inspect=()=>vm.runInContext(`({selected:selected?.sha256,dirty,busy,imageReady,
  imageLoading,revision:workspace?.revision})`,context);
function edit(){
  $('reviewer').value='Fixture assistant';$('reviewerKind').value='assistant';
  vm.runInContext(`for(const [label,row] of controls){row.value.value='present';
    row.notes.value='Evidence '+label;}changed()`,context);
}
function contents(){return vm.runInContext(`JSON.stringify([...controls].map(
  ([label,row])=>[label,row.value.value,row.notes.value]))`,context);}
function key(){return events.get('keydown')({ctrlKey:true,key:'Enter',
  target:{tagName:'TEXTAREA'},preventDefault(){}});}
async function allSavePaths(){
  $('save').click();await $('judgmentForm').onsubmit({preventDefault(){}});
  await $('saveNext').onclick();key();await turn();
}
async function opened(){take('api/state').resolve(state());await turn();}
function ready(){const image=images.at(-1);image.onload();return image;}
function accepted(payload,revision=2,prior={}){
  const judgments=JSON.parse(JSON.stringify(prior));judgments[payload.image]||={};
  for(const row of payload.judgments)judgments[payload.image][row.label]={...row};
  return state(revision,judgments);
}
(async()=>{
  if(scenario==='initial_retry'){
    take('api/state').reject(new Error('workspace unavailable'));await turn();
    assert.equal($('retryWorkspace').hidden,false);assert.equal($('retryWorkspace').disabled,false);
    await allSavePaths();assert.equal(requests.length,0);
    const retry=$('retryWorkspace').click();const request=take('api/state');
    await $('retryWorkspace').onclick();assert.equal(requests.length,0);
    request.resolve(state());await retry;assert.equal($('reviewPanel').hidden,false);
    assert.equal($('retryWorkspace').hidden,true);assert.equal($('save').disabled,true);
    ready();assert.equal($('save').disabled,false);return;
  }
  await opened();
  if(scenario==='eligibility'){
    edit();assert.equal($('save').disabled,true);await allSavePaths();
    assert.equal(requests.length,0);
    images.at(-1).onerror();await allSavePaths();assert.equal(requests.length,0);
    assert.equal($('retryImage').disabled,false);const before=contents();
    $('retryImage').click();assert.equal($('retryImage').disabled,true);
    ready();assert.equal(contents(),before);assert.equal(inspect().dirty,true);
    key();assert.equal(requests.length,1);return;
  }
  if(scenario==='media_races'){
    const a=images.at(-1),aLoad=a.onload,aError=a.onerror;
    $('next').click();const b=images.at(-1);assert.notEqual(a,b);
    const loading=$('imageStatus').textContent;aLoad();aError();
    assert.equal($('imageStatus').textContent,loading);assert.equal(inspect().imageReady,false);
    const count=media.length;b.onload();assert.equal($('original'),b);
    assert.equal(media.length,count);
    aLoad();aError();assert.equal(inspect().imageReady,true);assert.equal($('original'),b);
    $('previous').click();const reloaded=images.at(-1);
    assert.notEqual(reloaded.src,a.src);
    assert.equal(new URL(reloaded.src).pathname,new URL(a.src).pathname);
    assert.equal(media.length,count+1);return;
  }
  if(scenario==='empty'){
    const staleLoad=images.at(-1).onload;
    $('search').value='no matches';$('search').oninput();
    assert.equal(inspect().selected,undefined);assert.equal($('labelDetail').hidden,true);
    assert.equal($('emptyQueue').hidden,false);assert.equal($('showAll').hidden,false);
    staleLoad();assert.equal(inspect().imageReady,false);await allSavePaths();
    await $('reveal').onclick();assert.equal(requests.length,0);
    $('showAll').click();assert.equal($('emptyQueue').hidden,true);assert.equal($('labelDetail').hidden,false);
    assert.equal($('search').value,'');assert.equal($('save').disabled,true);ready();
    assert.equal($('save').disabled,false);return;
  }
  ready();
  if(scenario==='dirty_retry'){
    edit();const before=contents(),baseline=inspect().revision;
    $('retryImage').click();const failed=images.at(-1),oldLoad=failed.onload;failed.onerror();
    assert.equal(contents(),before);assert.equal(inspect().dirty,true);await allSavePaths();
    assert.equal(requests.length,0);assert.equal($('reload').disabled,false);
    $('retryImage').click();const restored=images.at(-1);assert.notEqual(restored.src,failed.src);
    oldLoad();assert.equal(inspect().imageReady,false);restored.onload();
    assert.equal(contents(),before);assert.equal(inspect().revision,baseline);
    assert.equal(inspect().dirty,true);assert.equal($('save').disabled,false);return;
  }
  if(scenario.startsWith('save_')){
    edit();const method=scenario.slice(5);
    const action=method==='button'?$('save').click():method==='form'?
      $('judgmentForm').onsubmit({preventDefault(){}}):method==='next'?$('saveNext').click():key();
    const request=take('api/save'),payload=JSON.parse(request.options.body);
    assert.equal(payload.image,'a'.repeat(64));assert.equal(payload.expected_revision,0);
    assert.equal(payload.judgments.length,2);assert.ok(payload.judgments.every(row=>row.reviewer_kind==='assistant'));
    await allSavePaths();await $('reload').onclick();await $('reveal').onclick();
    assert.equal(requests.length,0);request.resolve(accepted(payload));await action;await turn();
    assert.equal(inspect().revision,2);assert.equal(inspect().dirty,false);
    assert.equal(inspect().selected,(method==='next'?'b':'a').repeat(64));
    assert.equal(inspect().imageReady,method!=='next');return;
  }
  if(scenario==='reload_conflict'){
    edit();const before=contents();const saving=$('save').click();
    take('api/save').resolve({error:'Revision changed; reload'},false);await saving;
    assert.equal(contents(),before);assert.equal(inspect().revision,0);assert.equal(inspect().dirty,true);
    const failed=$('reload').click();take('api/state').reject(new Error('still unavailable'));
    await failed;
    assert.equal(contents(),before);assert.equal(inspect().revision,0);assert.equal(inspect().dirty,true);
    const reload=$('reload').click(),request=take('api/state');
    await $('reload').onclick();await allSavePaths();assert.equal(requests.length,0);
    request.resolve(state(7));await reload;assert.equal(inspect().revision,7);
    assert.equal(inspect().dirty,false);
    assert.equal(inspect().imageReady,false);ready();edit();const next=$('save').click();
    const save=take('api/save'),payload=JSON.parse(save.options.body);
    assert.equal(payload.expected_revision,7);
    save.resolve(accepted(payload,9));await next;assert.equal(inspect().revision,9);return;
  }
  if(scenario==='pending_completion'){
    $('pendingOnly').checked=true;$('pendingOnly').onchange();edit();
    const first=$('save').click(),request=take('api/save'),payload=JSON.parse(request.options.body);
    const after=accepted(payload);request.resolve(after);await first;
    assert.equal(inspect().selected,'b'.repeat(64));assert.equal($('save').disabled,true);ready();edit();
    const second=$('saveNext').click(),last=take('api/save');
    const lastPayload=JSON.parse(last.options.body);
    last.resolve(accepted(lastPayload,4,after.judgments));await second;
    assert.equal(inspect().selected,undefined);assert.equal($('emptyQueue').hidden,false);
    await allSavePaths();assert.equal(requests.length,0);$('showAll').click();ready();
    assert.equal($('pendingOnly').checked,false);assert.equal($('save').disabled,false);return;
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
