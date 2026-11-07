import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const noop={addListener(){}};
const listeners={tab:null,download:null};let clickEffect=null;let gameFrames=[];
let state,events,cancelSearch=false,playError=false,wrongPlayback=false;
const tabs=new Map();
function reset(url='https://www.youtube.com/'){
 state={};events=[];tabs.clear();tabs.set(1,{id:1,windowId:1,active:true,url,status:'complete'});cancelSearch=false;playError=false;wrongPlayback=false;
}
globalThis.chrome={storage:{session:{async get(){return {...state};},async set(v){Object.assign(state,v);}}},
 tabs:{onCreated:{addListener(f){listeners.tab=f;},removeListener(){listeners.tab=null;}},async query(query={}){const all=[...tabs.values()];return query.active?all.filter(t=>t.active):all;},async get(id){return {...tabs.get(id)};},
 async update(id,changes){events.push(['update',changes]);if(changes.active)for(const tab of tabs.values())if(tab.windowId===tabs.get(id).windowId)tab.active=false;Object.assign(tabs.get(id),changes);return {...tabs.get(id)};},
 async create(changes){events.push(['create',changes]);if(changes.active)for(const tab of tabs.values())if(tab.windowId===1)tab.active=false;const t={id:tabs.size+1,windowId:1,url:'brave://newtab/',status:'complete',...changes};tabs.set(t.id,t);return {...t,url:undefined};}},
 windows:{async update(){}},downloads:{onCreated:{addListener(f){listeners.download=f;},removeListener(){listeners.download=null;}}},scripting:{async executeScript({target,args:[req]}){
  if(target.allFrames){events.push(['allFrames']);return gameFrames;}
    events.push(['op',req.op,!!req.prepareOnly]);const tab=tabs.get(target.tabId);let result;
  if(req.prepareOnly)return [{result:true}];
  if(req.op==='inspect')result={url:tab.url,title:'Fixture',page:'fixture-page',controls:[{name:req.target||'Save',role:'button',editable:false,disabled:false}],control:req.target?{id:'control-1',name:req.target,role:'button',editable:false,disabled:false,fingerprint:'button|save|button||'}:undefined};
  else if(req.op==='search'){
   tab.url=req.site==='spotify'?'https://open.spotify.com/search/'+encodeURIComponent(req.query):'https://www.youtube.com/results?search_query='+encodeURIComponent(req.query);
   if(cancelSearch)state.epoch='cancelled';result={message:'Submitted'};
  }else if(req.op==='search_ready')result=true;
  else if(req.op==='result'){assert.equal(req.index,2);result={url:'https://www.youtube.com/watch?v=second',title:'Second video'};}
  else if(req.op==='video_ready')result=true;
  else if(req.op==='video_play'||req.op==='video_playing')result={playing:true};
  else if(req.op==='play')result=playError?{blokError:'The click result is uncertain'}:{track:'Baby',trackUrl:'https://open.spotify.com/track/baby'};
  else if(req.op==='playing'){assert.equal(req.trackUrl,'https://open.spotify.com/track/baby');result={playing:!wrongPlayback};}
  else if(req.op==='click'){if(clickEffect)clickEffect(tab);assert.equal(req.control?.id,'control-1');assert.equal(req.control?.fingerprint,'button|save|button||');assert.equal(req.page,'fixture-page');result={message:'Clicked Save · result not verified',verified:false};}
  else if(req.op==='snapshot')result={url:tab.url,title:'Fixture',page:'fixture-page',total:1,truncated:false,controls:[{ref:'e1',role:'button',name:'Save'}]};
  else if(req.op==='hints')result={message:'Hid the numbers'};
  else if(req.op==='github_user')result={user:'fixture-user'};
  else if(req.op==='github_filter')result={message:'Filtered'};
  else if(req.op==='github_repository')result={url:'https://github.com/fixture-user/ClickyAI',title:'ClickyAI'};
  else throw Error('Unexpected op '+req.op);
  return [{result}];
 }},runtime:{onStartup:noop,onInstalled:noop,onMessage:noop},alarms:{onAlarm:noop},action:{onClicked:noop}};
let source=await readFile(new URL('../browser-extension/background.js',import.meta.url),'utf8');
source=source.replace("import {pageAction,gameFrameText} from './page.js';",'const pageAction=()=>{},gameFrameText=()=>{};').replace(/connect\(\);\s*$/,'');
source=source.replace("'./execution.js'",JSON.stringify(new URL('../browser-extension/execution.js',import.meta.url).href));
const {run}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
reset('brave://extensions/');
assert.match((await run({action:'new_tab'})).message,/new tab/);
assert.equal(events.filter(e=>e[0]==='create').length,1);
reset('brave://newtab/');
const steps=[{action:'search',site:'youtube',query:'bbs'},{action:'result',index:2,play:true}];
assert.match((await run({action:'sequence',steps})).message,/Playing Second video/);
assert.deepEqual(events.filter(e=>e[0]==='op'&&!e[2]).map(e=>e[1]),['search','search_ready','result','video_ready','video_play','video_playing']);
reset();cancelSearch=true;
await assert.rejects(run({action:'sequence',steps}),/Step 1.*Cancelled/);
assert.ok(!events.some(e=>e[1]==='result'));
reset('https://www.google.com/search?q=games');
await assert.rejects(run({action:'result',index:1}),/no longer current/);
reset('brave://newtab/');
assert.match((await run({action:'play',site:'spotify',query:'justin bieber',mode:'artist'})).message,/Playing Baby/);
reset('https://github.com/');
assert.match((await run({action:'github_repo',query:'clickyai'})).message,/ClickyAI/);
assert.ok(events.some(e=>e[0]==='update'&&e[1].url==='https://github.com/fixture-user?tab=repositories'));
console.log('PASS: native new tab, ordered search/play, cancellation stops sequence, artist playback verification, signed-in repository navigation');
reset('https://open.spotify.com/search/justin%20bieber');playError=true;
await assert.rejects(run({action:'play',site:'spotify',query:'justin bieber',mode:'artist'}),error=>{
 assert.match(error.message,/Starting Spotify playback.*uncertain/);
 assert.equal(error.trace.at(-1).status,'failed');return true;
});
assert.equal(events.filter(e=>e[1]==='play'&&!e[2]).length,1);
reset();
await assert.rejects(run({action:'sequence',steps:[{action:'click',target:'Save'},{action:'new_tab'}]}),/unverified.*remaining steps/);
assert.ok(!events.some(e=>e[0]==='create'));
reset('https://open.spotify.com/search/justin%20bieber');wrongPlayback=true;
const originalNow=Date.now,originalTimeout=globalThis.setTimeout;let clock=0;
Date.now=()=>clock;globalThis.setTimeout=(fn,ms)=>{clock+=ms;return originalTimeout(fn,0);};
try {
 await assert.rejects(run({action:'play',site:'spotify',query:'justin bieber',mode:'artist'}),error=>{
  assert.match(error.message,/Confirming Spotify playback/);
  assert.equal(error.trace.at(-1).kind,'verify');assert.equal(error.trace.at(-1).status,'failed');return true;
 });
 assert.equal(events.filter(e=>e[1]==='play'&&!e[2]).length,1);
} finally {Date.now=originalNow;globalThis.setTimeout=originalTimeout;}
reset();const progress=[];
const verified=await run({action:'new_tab'},event=>progress.push(event));
assert.equal(verified.verified,true);assert.ok(verified.evidence);
assert.deepEqual(progress.filter(e=>e.status==='running').map(e=>e.kind),['act','verify']);
reset();
const clicked=await run({action:'click',target:'Save'});
assert.equal(clicked.verified,false);
assert.deepEqual(events.filter(e=>e[0]==='op').map(e=>e[1]),['inspect','click']);
console.log('PASS: uncertain actions are not repeated; unverified steps stop; wrong playback fails; verified results carry progress and evidence');

{
 const click=()=>run({action:'click_observed',control:{id:'control-1',fingerprint:'button|save|button||'},page:'fixture-page'});
 reset('https://example.com/');
 assert.equal((await run({action:'snapshot'})).controls[0].ref,'e1');
 reset('https://example.com/');clickEffect=null;
 const quiet=await click();
 assert.deepEqual(quiet.effects,{});
 reset('https://example.com/');clickEffect=()=>listeners.tab({id:9,url:'',pendingUrl:'https://example.com/new'});
 assert.deepEqual((await click()).effects,{new_tab:{tabId:9,url:'https://example.com/new'}});
 reset('https://example.com/');clickEffect=()=>listeners.download({url:'https://example.com/files/game.zip?x=1',filename:''});
 const dl=await click();assert.equal(dl.effects.download,'game.zip');assert.equal(dl.verified,true);
 reset('https://example.com/');clickEffect=tab=>{tab.url='https://example.com/next';};
 assert.equal((await click()).effects.navigated,'https://example.com/next');
 clickEffect=null;
 assert.equal(listeners.tab,null);assert.equal(listeners.download,null);
 console.log('PASS: snapshot action and click effects');
}
{
 reset('https://slithergame.io/');
 gameFrames=[{result:null},{result:{url:'https://gulper.io/home',text:'About the game'}},{result:{url:'https://gulper.io/',text:'Score: 10\nRank: 2 of 14'}}];
 const seen=await run({action:'game_text',hosts:['gulper.io']});
 assert.equal(seen.found,true);assert.match(seen.text,/Score: 10/);          // the frame with a score wins
 gameFrames=[{result:null},{result:null}];
 assert.equal((await run({action:'game_text',hosts:['gulper.io']})).found,false);
 reset('brave://newtab/');
 assert.equal((await run({action:'game_text',hosts:['gulper.io']})).found,false);
 console.log('PASS: game text comes from the game frame only');
}
