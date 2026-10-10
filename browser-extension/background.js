import {pageAction} from './page.js';
// The native port is a live resource; cancellation state survives worker restarts.
let port;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sites={google:'https://www.google.com/',youtube:'https://www.youtube.com/',spotify:'https://open.spotify.com/search'};
const siteOf=url=>{try{const h=new URL(url).hostname;return h==='www.youtube.com'||h==='youtube.com'?'youtube':h==='open.spotify.com'?'spotify':/(^|\.)google\.[a-z.]+$/.test(h)?'google':null;}catch{return null;}};
async function run(req) {
  if(req.action==='cancel'){await chrome.storage.session.set({epoch:crypto.randomUUID()});return {message:'Cancelled'};}
  if(req.action==='ping') return {message:'Brave connected'};
  const {epoch:turn}=await chrome.storage.session.get('epoch');
  const check=async()=>{const {epoch}=await chrome.storage.session.get('epoch');if(turn!==epoch)throw Error('Cancelled');};
  let tabs=await chrome.tabs.query({currentWindow:true});
  let tab=tabs.find(t=>t.active);
  async function act(args){await check(); const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:pageAction,args:[args]});return results[0].result;}
  async function until(fn,timeout=15000){const start=Date.now();let last;while(Date.now()-start<timeout){await check();try{const r=await fn();if(r)return r;}catch(e){last=e;}await sleep(250);}throw last||Error('Page did not finish loading.');}
  async function focus(t){await check();await chrome.tabs.update(t.id,{active:true});await chrome.windows.update(t.windowId,{focused:true});tab=t;}
  if(req.action==='search'||req.action==='play'||req.action==='navigate') {
    let site=req.site||siteOf(tab?.url)||'google';
    const url=req.action==='navigate'?req.url:sites[site];
    if(!/^https?:\/\//.test(url)) throw Error('Only web URLs are supported');
    const host=new URL(url).hostname;
    const existing=tabs.find(t=>{try{return new URL(t.url).hostname===host;}catch{return false;}});
    if(existing) await focus(existing); else {await check();tab=await chrome.tabs.create({url,active:true});}
    if(req.action==='navigate') {
      if(existing) {await check();await chrome.tabs.update(tab.id,{url});}
      await until(async()=>{const t=await chrome.tabs.get(tab.id);return t.status==='complete';});
      return {message:'Opened '+host,tabId:tab.id};
    }
    if(existing&&site==='spotify'&&!new URL(existing.url).pathname.startsWith('/search')) {await check();await chrome.tabs.update(tab.id,{url:sites.spotify});}
    await until(async()=>{const t=await chrome.tabs.get(tab.id);return t.status==='complete';});
    await until(()=>act({op:'search',site,query:req.query}));
    await until(async()=>{const t=await chrome.tabs.get(tab.id),u=new URL(t.url);return site==='google'?u.searchParams.get('q')===req.query:site==='youtube'?u.searchParams.get('search_query')===req.query:decodeURIComponent(u.pathname).toLowerCase().includes(req.query.toLowerCase());});
    if(req.action==='play') {
      await until(()=>act({op:'play',query:req.query}));
      await until(async()=>{const s=await act({op:'playing',query:req.query});return s.playing;},12000);
      return {message:'Playing '+req.query+' on Spotify',tabId:tab.id};
    }
    return {message:'Searched '+site+' for '+req.query,tabId:tab.id};
  }
  if(!tab||!/^https?:/.test(tab.url)) throw Error('Focus a web page first.');
  await focus(tab);
  const before=tab.url;
  const result=await act({op:req.action,...req});
  if(req.action==='result') await until(async()=>{const t=await chrome.tabs.get(tab.id);return t.url!==before&&t.status==='complete';});
  return result;
}
function connect(){
  if(port) return;
  const connection=chrome.runtime.connectNative('io.hyprash.browser');
  port=connection;
  connection.onMessage.addListener(async req=>{
    let response;
    try {response={id:req.id,result:await run(req)};}
    catch(e) {response={id:req.id,error:e.message};}
    try {connection.postMessage(response);} catch(e) {console.warn('Native connection closed',e.message);}
  });
  connection.onDisconnect.addListener(()=>{
    const error=chrome.runtime.lastError;
    if(error) console.warn(error.message);
    if(port===connection) port=undefined;
    chrome.alarms.create('reconnect',{delayInMinutes:0.5}).catch(console.error);
  });
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='reconnect')connect();});
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.action.onClicked.addListener(connect);
connect();
