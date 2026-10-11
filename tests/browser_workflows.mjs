import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const noop={addListener(){}};
let state,events,cancelSearch=false;
const tabs=new Map();
function reset(url='https://www.youtube.com/'){
 state={};events=[];tabs.clear();tabs.set(1,{id:1,windowId:1,active:true,url,status:'complete'});cancelSearch=false;
}
globalThis.chrome={storage:{session:{async get(){return {...state};},async set(v){Object.assign(state,v);}}},
 tabs:{async query(){return [...tabs.values()];},async get(id){return {...tabs.get(id)};},
 async update(id,changes){events.push(['update',changes]);Object.assign(tabs.get(id),changes);return {...tabs.get(id)};},
 async create(changes){events.push(['create',changes]);const t={id:tabs.size+1,windowId:1,url:'brave://newtab/',status:'complete',...changes};tabs.set(t.id,t);return {...t,url:undefined};}},
 windows:{async update(){}},scripting:{async executeScript({target,args:[req]}){
  events.push(['op',req.op]);const tab=tabs.get(target.tabId);let result;
  if(req.op==='search'){
   tab.url=req.site==='spotify'?'https://open.spotify.com/search/'+encodeURIComponent(req.query):'https://www.youtube.com/results?search_query='+encodeURIComponent(req.query);
   if(cancelSearch)state.epoch='cancelled';result={message:'Submitted'};
  }else if(req.op==='search_ready')result=true;
  else if(req.op==='result'){assert.equal(req.index,2);result={url:'https://www.youtube.com/watch?v=second',title:'Second video'};}
  else if(req.op==='video_play'||req.op==='video_playing')result={playing:true};
  else if(req.op==='play')result={track:'Baby',trackUrl:'https://open.spotify.com/track/baby'};
  else if(req.op==='playing'){assert.equal(req.trackUrl,'https://open.spotify.com/track/baby');result={playing:true};}
  else if(req.op==='github_user')result={user:'fixture-user'};
  else if(req.op==='github_filter')result={message:'Filtered'};
  else if(req.op==='github_repository')result={url:'https://github.com/fixture-user/ClickyAI',title:'ClickyAI'};
  else throw Error('Unexpected op '+req.op);
  return [{result}];
 }},runtime:{onStartup:noop,onInstalled:noop},alarms:{onAlarm:noop},action:{onClicked:noop}};
let source=await readFile(new URL('../browser-extension/background.js',import.meta.url),'utf8');
source=source.replace("import {pageAction} from './page.js';",'const pageAction=()=>{};').replace(/connect\(\);\s*$/,'');
const {run}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
reset('brave://extensions/');
assert.match((await run({action:'new_tab'})).message,/new tab/);
assert.equal(events.filter(e=>e[0]==='create').length,1);
reset('brave://newtab/');
const steps=[{action:'search',site:'youtube',query:'bbs'},{action:'result',index:2,play:true}];
assert.match((await run({action:'sequence',steps})).message,/Playing Second video/);
assert.deepEqual(events.filter(e=>e[0]==='op').map(e=>e[1]),['search','search_ready','result','video_play','video_playing']);
reset();cancelSearch=true;
await assert.rejects(run({action:'sequence',steps}),/Step 1.*Cancelled/);
assert.ok(!events.some(e=>e[1]==='result'));
reset('brave://newtab/');
assert.match((await run({action:'play',site:'spotify',query:'justin bieber',mode:'artist'})).message,/Playing Baby/);
reset('https://github.com/');
assert.match((await run({action:'github_repo',query:'clickyai'})).message,/ClickyAI/);
assert.ok(events.some(e=>e[0]==='update'&&e[1].url==='https://github.com/fixture-user?tab=repositories'));
console.log('PASS: native new tab, ordered search/play, cancellation stops sequence, artist playback verification, signed-in repository navigation');
