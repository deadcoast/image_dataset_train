"""Execute browsing persistence and real reviewer navigation with delayed requests."""

import shutil
import subprocess
from pathlib import Path

import pytest
from test_reviewer_recovery_ui import HARNESS as REVIEWER_HARNESS

ASSETS = Path(__file__).parents[1] / "src/image_dataset_train"


def run_node(script, scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for reviewer browsing regressions")
    result = subprocess.run(
        [node, "-", str(ASSETS), scenario],
        input=script,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "scenario", ["coalescing", "conflict", "reload", "views", "static", "invalid"]
)
def test_browsing_storage_controller(scenario):
    run_node(FACTORY_HARNESS, scenario)


@pytest.mark.parametrize("scenario", ["resume", "hash", "pair_resume", "pair_clamp", "dirty"])
def test_browsing_integrates_with_the_complete_reviewer(scenario):
    script = REVIEWER_HARNESS.replace("id:name,source_path:", "id:name.repeat(64),source_path:")
    script = script.replace(
        "document,console,URL,URLSearchParams,Map,Promise,",
        "document,console,URL,URLSearchParams,Map,Promise,TextEncoder,",
    )
    script = script.replace("$('data').textContent = JSON.stringify(data);", INTEGRATION_SEED)
    script = script.replace(
        "location:{hash:'',href:", "location:{hash:scenario==='hash'?'#'+'a'.repeat(64):'',href:"
    )
    script = script.replace("(async()=>{", "(async()=>{" + INTEGRATION_CASES, 1)
    run_node(script, scenario)


FACTORY_HARNESS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const scenario=process.argv[3],elements=new Map(),requests=[],timers=new Map(),listeners=new Map();
function element(){return {value:'',textContent:'',disabled:false,children:[],
 classList:{toggle(){}},append(...items){this.children.push(...items)},
 replaceChildren(...items){this.children=items}}}
const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
const stored=new Map();let storageFailure=null,sets=0,activity=0,blocked=false;
const storage={getItem(key){if(storageFailure)throw storageFailure;return stored.get(key)??null},
 setItem(key,value){if(storageFailure)throw storageFailure;sets++;stored.set(key,value)}};
const report='f'.repeat(64),image='a'.repeat(64),key='trainime.review-browsing.v1:'+report;
const filters=()=>({finding:'',label:'',subset:'',split:'',decision:'',search:'',
 pilot:false,group:''});
const state=()=>({schema_version:1,report_id:report,revision:0,last:{filters:filters(),
 image_id:null,position:0,pair:{decision:'unreviewed',offset:0,pair_id:null}},views:[]});
const entries=[{id:image,findings:['caption_missing'],labels:['café'],subset:'portraits',
 split:'train',decision:'include',group_id:'g'}];
let seed=state();const restores=[];
const context=vm.createContext({document:{createElement:element},console,TextEncoder,
 localStorage:storage,addEventListener:(name,fn)=>listeners.set(name,fn),
 setTimeout:fn=>{const id=timers.size+1;timers.set(id,fn);return id},
 clearTimeout:id=>timers.delete(id),
 fetch:(path,options={})=>new Promise((resolve,reject)=>requests.push({path,options,reject,
 resolve:(value,ok=true)=>resolve({ok,json:async()=>value})}))});
vm.runInContext(fs.readFileSync(process.argv[2]+'/qa_preferences.js','utf8'),context);
function make(session=true,override=seed,error=null){
 const data={entries,session,browsing:{report_id:report,state:override,error}};
 return context.createReviewBrowsing({data,element:$,blocked:()=>blocked,
 restoreImage:value=>restores.push(value),activity:()=>activity});
}
const payload=request=>JSON.parse(request.options.body);
const accept=request=>{const value=payload(request);return {schema_version:1,report_id:report,
 revision:value.expected_revision+1,last:value.last,views:value.views}};
const turn=()=>new Promise(resolve=>setImmediate(resolve));
function capture(manager,search){manager.captureImage({filters:{...filters(),search},
 image_id:image,position:0})}
(async()=>{
 if(scenario==='coalescing'){
  const manager=make();capture(manager,'first');const first=manager.flush(),r1=requests.shift();
  assert.equal(payload(r1).expected_revision,0);capture(manager,'second');
  assert.equal(requests.length,0);r1.resolve(accept(r1));await first;
  assert.match($('browsingStatus').textContent,/Saving/);
  const second=manager.flush(),r2=requests.shift();
  assert.equal(payload(r2).expected_revision,1);assert.equal(payload(r2).last.filters.search,'second');
  r2.resolve(accept(r2));await second;
  assert.equal(restores.length,0);
  assert.match($('browsingStatus').textContent,/Saved on this computer/);
  await manager.flush();assert.equal(requests.length,0);
  return;
 }
 if(scenario==='conflict'){
  const manager=make();capture(manager,'local');const save=manager.flush(),request=requests.shift();
  request.resolve({error:'changed in another session'},false);await save;
  assert.match($('browsingStatus').textContent,/not saved/);assert.equal(restores.length,0);
  capture(manager,'still local');await manager.flush();assert.equal(requests.length,0);
  assert.equal($('saveBrowsingView').disabled,true);
  const reload=$('reloadBrowsing').onclick(),read=requests.shift();const remote=state();
  remote.revision=5;remote.last.filters.search='remote';read.resolve(remote);await reload;
  assert.equal(restores.length,1);assert.equal(restores[0].filters.search,'remote');
  capture(manager,'after reload');const fresh=manager.flush(),next=requests.shift();
  assert.equal(payload(next).expected_revision,5);next.resolve(accept(next));await fresh;return;
 }
 if(scenario==='reload'){
  const manager=make();const loading=$('reloadBrowsing').onclick(),old=requests.shift();
  activity++;blocked=true;capture(manager,'new local');old.resolve(state());await loading;
  assert.equal(restores.length,0);assert.match($('browsingStatus').textContent,/continued working/);
  await $('reloadBrowsing').onclick();assert.equal(requests.length,0);
  blocked=false;manager.locks();const retry=$('reloadBrowsing').onclick(),fresh=requests.shift();
  fresh.resolve(state());await retry;assert.equal(restores.length,1);return;
 }
 if(scenario==='views'){
  const manager=make();capture(manager,'named search');$('browsingViewName').value='Cafe\u0301';
  $('saveBrowsingView').onclick();assert.equal($('savedBrowsingViews').value,'Café');
  const save=manager.flush(),request=requests.shift();
  assert.equal(payload(request).views[0].name,'Café');
  assert.deepEqual(Object.keys(payload(request).views[0]).sort(),['filters','name']);
  request.resolve(accept(request));await save;
  blocked=true;manager.locks();$('applyBrowsingView').onclick();assert.equal(restores.length,0);
  blocked=false;manager.locks();$('applyBrowsingView').onclick();
  assert.equal(restores[0].filters.search,'named search');
  manager.capturePair({decision:'all',offset:40,pair_id:'b'.repeat(64)});
  $('clearBrowsingResume').onclick();const clear=manager.flush(),clearing=requests.shift();
  const last=payload(clearing).last;
  assert.equal(last.filters.search,'named search');assert.equal(last.image_id,null);
  assert.deepEqual(last.pair,{decision:'all',offset:0,pair_id:null});
  assert.equal(payload(clearing).views.length,1);clearing.resolve(accept(clearing));await clear;
  $('deleteBrowsingView').onclick();const remove=manager.flush(),removing=requests.shift();
  assert.equal(payload(removing).views.length,0);removing.resolve(accept(removing));await remove;
  assert.equal(restores.length,1);return;
 }
 if(scenario==='static'){
  let manager=make(false);capture(manager,'offline');await manager.flush();
  assert.equal(requests.length,0);assert.equal(JSON.parse(stored.get(key)).last.filters.search,'offline');
  manager=make(false);assert.equal(manager.initial().filters.search,'offline');
  listeners.get('storage')({key});assert.match($('browsingStatus').textContent,/another window/);
  const before=sets;capture(manager,'local only');await manager.flush();assert.equal(sets,before);
  await $('reloadBrowsing').onclick();assert.equal(restores.at(-1).filters.search,'offline');
  storageFailure=Object.assign(new Error('blocked'),{name:'SecurityError'});
  manager=make(false);capture(manager,'memory');await manager.flush();
  assert.match($('browsingStatus').textContent,/only while this page/);assert.equal(sets,before);
  storageFailure=null;manager=make(false);capture(manager,'quota failure');
  storageFailure=Object.assign(new Error('quota exceeded'),{name:'QuotaExceededError'});
  await manager.flush();assert.match($('browsingStatus').textContent,/not saved/);
  assert.equal(sets,before);return;
 }
 if(scenario==='invalid'){
  for(const invalid of ['{broken',JSON.stringify({...state(),schema_version:2}),
    JSON.stringify({...state(),report_id:'0'.repeat(64)}),
    JSON.stringify({...state(),last:{...state().last,image_id:'b'.repeat(64)}}),
    JSON.stringify({...state(),last:{...state().last,filters:{...filters(),search:'a\n'}}}),
    JSON.stringify({...state(),views:[{name:'__proto__',filters:filters()},
      {name:'__proto__',filters:filters()}]})]){
   stored.set(key,invalid);const manager=make(false);capture(manager,'should not overwrite');
   await manager.flush();assert.equal(stored.get(key),invalid);
   assert.equal($('saveBrowsingView').disabled,true);assert.equal(requests.length,0);
  }
  const manager=make(true,null,'invalid stored file');capture(manager,'normal browsing');
  await manager.flush();assert.equal(requests.length,0);
  assert.match($('browsingStatus').textContent,/still review/);return;
 }
 throw new Error('unknown scenario');
})().catch(error=>{console.error(error);process.exitCode=1});
"""


INTEGRATION_SEED = r"""
const preferences={schema_version:1,report_id:'f'.repeat(64),revision:3,last:{
 filters:{finding:'',label:'',subset:'',split:'',decision:'',search:'b.png',pilot:false,group:''},
 image_id:'b'.repeat(64),position:0,pair:{decision:'all',offset:20,pair_id:'c'.repeat(64)}},
 views:[{name:'first',filters:{finding:'',label:'',subset:'',split:'',decision:'',
 search:'a.png',pilot:false,group:''}}]};
data.browsing={report_id:preferences.report_id,state:preferences,error:null};
$('data').textContent = JSON.stringify(data);
"""


INTEGRATION_CASES = r"""
 if(['resume','hash','pair_resume','pair_clamp','dirty'].includes(scenario)){
  const selected=scenario==='hash'?'a':'b';
  assert.equal($('path').textContent,selected+'.png');
  assert.equal($('search').value,scenario==='hash'?'':'b.png');
  take('api/review/'+selected).resolve(review());
  take('api/assessment').resolve(assessment());await turn();
  assert.equal(requests.filter(item=>item.path==='api/browsing-preferences').length,0);
  if(scenario==='resume'||scenario==='hash')return;
  if(scenario==='dirty'){
   dirtyReview();dirtyAssessment();
   $('savedBrowsingViews').value='first';$('savedBrowsingViews').onchange();
   $('applyBrowsingView').onclick();await $('reloadBrowsing').onclick();
   assert.equal($('path').textContent,'b.png');
   assert.equal($('editCaption').value,'unsaved caption');
   assert.equal($('assessmentNotes').value,'unsaved assessment');
   assert.equal($('conclusionNotes').value,'unsaved conclusion');
   assert.equal(requests.filter(item=>item.path==='api/browsing-preferences').length,0);return;
  }
  $('pairsTab').click();let request=take('api/pairs');
  assert.match(request.path,/decision=all&offset=20/);
  if(scenario==='pair_clamp'){
   request.resolve(queue([],{unreviewed:1},1));await turn();
   request=take('api/pairs');assert.match(request.path,/offset=0/);
   request.resolve(queue([pair('d'.repeat(64))],{unreviewed:1},1));await turn();
   const checkpoint=vm.runInContext('browsingPreferences.pair()',context);
   assert.equal(checkpoint.offset,20);assert.equal(checkpoint.pair_id,'c'.repeat(64));
   assert.match($('pairMessage').textContent,/saved pair is no longer/);return;
  }
  request.reject(new Error('source offline'));await turn();
  let saved=vm.runInContext('browsingPreferences.pair()',context);
  assert.equal(saved.offset,20);assert.equal(saved.pair_id,'c'.repeat(64));
  const retry=$('refreshPairs').click();request=take('api/pairs');
  assert.match(request.path,/offset=20/);
  request.resolve(queue([pair('d'.repeat(64))],{unreviewed:21},21));await retry;
  assert.match($('pairMessage').textContent,/saved pair is no longer/);
  saved=vm.runInContext('browsingPreferences.pair()',context);
  assert.equal(saved.pair_id,'c'.repeat(64),'unmatched restore must retain checkpoint');
  $('pairQueue').children[0].click();saved=vm.runInContext('browsingPreferences.pair()',context);
  assert.equal(saved.pair_id,'d'.repeat(64));assert.equal(saved.offset,20);
  return;
 }
"""
