import {pageAction} from './page.js';
// Only the live native connection is held in memory. Epoch survives worker restarts.
let port;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sites={google:'https://www.google.com/',youtube:'https://www.youtube.com/',spotify:'https://open.spotify.com/search'};
const siteOf=url=>{try{const h=new URL(url).hostname;return h==='www.youtube.com'||h==='youtube.com'?'youtube':h==='open.spotify.com'?'spotify':/(^|\.)google\.[a-z.]+$/.test(h)?'google':null;}catch{return null;}};
export async function run(req) {
  if(req.action==='cancel'){await chrome.storage.session.set({epoch:crypto.randomUUID()});return {message:'Cancelled'};}
  if(req.action==='ping') return {message:'Brave connected'};
  const {epoch:turn}=await chrome.storage.session.get('epoch');
  const deadline=Date.now()+40000;
  const check=async()=>{
    const {epoch}=await chrome.storage.session.get('epoch');
    if(turn!==epoch)throw Error('Cancelled');
    if(Date.now()>deadline)throw Error('The task timed out. No remaining steps were run.');
  };
  const tabs=await chrome.tabs.query({currentWindow:true});
  let tab=tabs.find(t=>t.active);
  async function act(args){await check();const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:pageAction,args:[args]});return results[0].result;}
  async function until(fn,timeout=15000){const end=Math.min(deadline,Date.now()+timeout);let last;while(Date.now()<end){await check();try{const r=await fn();if(r)return r;}catch(e){last=e;}await sleep(250);}throw last||Error('The page did not reach the expected state.');}
  async function focus(t){await check();await chrome.tabs.update(t.id,{active:true});await chrome.windows.update(t.windowId,{focused:true});tab=await chrome.tabs.get(t.id);}
  async function navigate(url){
    await check();
    if(!/^https?:\/\//.test(url))throw Error('Only web URLs are supported.');
    if(tab)await chrome.tabs.update(tab.id,{url});else tab=await chrome.tabs.create({url,active:true});
    await until(async()=>{const t=await chrome.tabs.get(tab.id);return t.status==='complete'&&!t.pendingUrl;});
    tab=await chrome.tabs.get(tab.id);
  }
  async function siteTab(url){
    const host=new URL(url).hostname;
    const candidates=await chrome.tabs.query({currentWindow:true});
    const matching=t=>{try{return new URL(t.url).hostname===host;}catch{return false;}};
    const existing=candidates.find(t=>t.active&&matching(t))||candidates.find(matching);
    if(existing)await focus(existing);
    else {await check();tab={...await chrome.tabs.create({url,active:true}),url};await chrome.windows.update(tab.windowId,{focused:true});}
  }
  async function execute(task){
    await check();
    if(task.action==='sequence') {
      if(!Array.isArray(task.steps)||task.steps.length<1||task.steps.length>6||task.steps.some(s=>s.action==='sequence'))throw Error('Invalid task sequence.');
      let result;
      for(let i=0;i<task.steps.length;i++){
        try{result=await execute(task.steps[i]);}
        catch(e){throw Error('Step '+(i+1)+' of '+task.steps.length+' failed: '+e.message);}
      }
      return result;
    }
    if(task.action==='new_tab'){
      tab=await chrome.tabs.create({active:true});
      await chrome.windows.update(tab.windowId,{focused:true});
      return {message:'Opened a new tab',tabId:tab.id};
    }
    if(task.action==='github_repo'){
      await siteTab('https://github.com/');
      await until(async()=> (await chrome.tabs.get(tab.id)).status==='complete');
      const {user}=await until(()=>act({op:'github_user'}));
      await navigate('https://github.com/'+encodeURIComponent(user)+'?tab=repositories');
      await until(()=>act({op:'github_filter',query:task.query}));
      const repo=await until(()=>act({op:'github_repository',query:task.query}));
      await navigate(repo.url);
      if(new URL(tab.url).pathname.toLowerCase()!==new URL(repo.url).pathname.toLowerCase())throw Error('GitHub did not open the requested repository.');
      return {message:'Opened repository '+repo.title,url:tab.url,tabId:tab.id};
    }
    if(['search','play','navigate'].includes(task.action)){
      const site=task.site||siteOf(tab?.url)||'google';
      const url=task.action==='navigate'?task.url:sites[site];
      if(!url||!/^https?:\/\//.test(url))throw Error('Only supported web destinations can be searched.');
      await siteTab(url);
      if(task.action==='navigate') {await navigate(url);return {message:'Opened '+new URL(tab.url).hostname,tabId:tab.id};}
      if(site==='spotify'&&!new URL(tab.url).pathname.startsWith('/search'))await navigate(sites.spotify);
      await until(async()=> (await chrome.tabs.get(tab.id)).status==='complete');
      await until(()=>act({op:'search',site,query:task.query}));
      await until(async()=>{
        const t=await chrome.tabs.get(tab.id),u=new URL(t.url);
        const matched=site==='google'?u.searchParams.get('q')===task.query:site==='youtube'?u.searchParams.get('search_query')===task.query:decodeURIComponent(u.pathname).toLowerCase().includes(task.query.toLowerCase());
        return matched&&await act({op:'search_ready',site,query:task.query});
      });
      if(task.action==='play'){
        if(site==='youtube')return execute({action:'result',index:task.index||1,play:true});
        if(site!=='spotify')throw Error('Playback is supported on Spotify and YouTube.');
        const selected=await until(()=>act({op:'play',query:task.query,mode:task.mode}));
        await until(async()=> (await act({op:'playing',query:selected.track,trackUrl:selected.trackUrl})).playing,12000);
        return {message:'Playing '+selected.track+' on Spotify',tabId:tab.id};
      }
      return {message:'Searched '+site+' for '+task.query,tabId:tab.id};
    }
    if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
    await focus(tab);
    if(task.action==='result'){
      const selected=await until(()=>act({op:'result',index:task.index,resolve:true}));
      await navigate(selected.url);
      if(task.play){
        if(siteOf(tab.url)!=='youtube')throw Error('This result is not a YouTube video.');
        await until(()=>act({op:'video_play'}));
        await until(async()=> (await act({op:'video_playing'})).playing);
      }
      return {message:(task.play?'Playing ':'Opened ')+selected.title,url:tab.url,tabId:tab.id};
    }
    return act({op:task.action,...task});
  }
  return execute(req);
}
function connect(){
  if(port)return;
  const connection=chrome.runtime.connectNative('io.hyprash.browser');port=connection;
  connection.onMessage.addListener(async req=>{
    let response;
    try{response={id:req.id,result:await run(req)};}catch(e){response={id:req.id,error:e.message};}
    try{connection.postMessage(response);}catch(e){console.warn('Native connection closed',e.message);}
  });
  connection.onDisconnect.addListener(()=>{
    const error=chrome.runtime.lastError;if(error)console.warn(error.message);
    if(port===connection)port=undefined;
    chrome.alarms.create('reconnect',{delayInMinutes:0.5}).catch(console.error);
  });
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='reconnect')connect();});
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.action.onClicked.addListener(connect);
connect();
