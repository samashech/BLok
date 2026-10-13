import {pageAction} from './page.js';
import {execution} from './execution.js';
// Only the native connection is global. Cancellation survives worker restarts.
let port;
const sites={google:'https://www.google.com/',youtube:'https://www.youtube.com/',spotify:'https://open.spotify.com/search'};
const siteOf=url=>{try{const h=new URL(url).hostname;return h==='www.youtube.com'||h==='youtube.com'?'youtube':h==='open.spotify.com'?'spotify':/(^|\.)google\.[a-z.]+$/.test(h)?'google':null;}catch{return null;}};
const sameDestination=(actual,expected)=>{
  try {const a=new URL(actual),b=new URL(expected);return a.hostname===b.hostname && a.pathname.replace(/\/$/,'')===b.pathname.replace(/\/$/,'') && [...b.searchParams].every(([k,v])=>a.searchParams.get(k)===v);}catch{return false;}
};
export async function run(req, progress=()=>{}) {
  if(req.action==='cancel'){await chrome.storage.session.set({epoch:crypto.randomUUID()});return {message:'Cancelled'};}
  if(req.action==='ping')return {message:'Brave connected',version:'phase5-reusable-routines'};
  const {epoch:turn}=await chrome.storage.session.get('epoch');
  const flow=execution({progress,check:async()=>{
    const {epoch}=await chrome.storage.session.get('epoch');
    if(turn!==epoch)throw Error('Cancelled');
  }});
  let tab;
  const confirmed=(message,evidence,extra={})=>({message,verified:true,evidence,tabId:tab?.id,...extra});
  async function page(args) {
    await flow.guard();
    const [active]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!active||active.id!==tab?.id||active.windowId!==tab.windowId)throw Error('The active tab changed. Inspect the current screen again.');
    const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:pageAction,args:[args,true]});
    const result=results[0]?.result;
    if(result?.hyprashError)throw Error(result.hyprashError);
    if(result===undefined)throw Error('The page action did not return a result.');
    return result;
  }
  async function loaded() {
    return flow.observe('Waiting for the page to load',async()=>{
      const current=await chrome.tabs.get(tab.id);
      if(current.status!=='complete'||current.pendingUrl)return false;
      tab=current;return current;
    });
  }
  async function focus(target) {
    await flow.act('Focusing the browser tab',async()=>{
      await chrome.tabs.update(target.id,{active:true});
      await chrome.windows.update(target.windowId,{focused:true});
      tab=await chrome.tabs.get(target.id);
    });
  }
  async function navigate(url) {
    if(!/^https?:\/\//.test(url))throw Error('Only web URLs are supported.');
    await flow.act('Opening '+new URL(url).hostname,async()=>{
      if(tab)await chrome.tabs.update(tab.id,{url});
      else tab=await chrome.tabs.create({url,active:true});
    });
    await loaded();
    await flow.verify('Checking the destination',async()=>{
      tab=await chrome.tabs.get(tab.id);
      return sameDestination(tab.url,url);
    });
  }
  async function siteTab(url) {
    const host=new URL(url).hostname;
    const candidates=await chrome.tabs.query({currentWindow:true});
    const matching=t=>{try{return new URL(t.url).hostname===host;}catch{return false;}};
    const existing=candidates.find(t=>t.active&&matching(t))||candidates.find(matching);
    if(existing)await focus(existing);
    else await flow.act('Opening a browser tab',async()=>{
      tab={...await chrome.tabs.create({url,active:true}),url};
      await chrome.windows.update(tab.windowId,{focused:true});
    });
  }
  async function execute(task) {
    await flow.guard();
    if(task.action==='inspect') {
      if(task.site&&sites[task.site])await siteTab(sites[task.site]);
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await loaded();
      const observation=await flow.observe('Observing visible controls',()=>page({op:'inspect'}));
      return confirmed('Observed '+observation.controls.length+' visible controls','Current tab and document observed',{
        observation:{url:observation.url,title:observation.title,
          controls:observation.controls.map(({name,role,editable,disabled})=>({name,role,editable,disabled}))}
      });
    }
    if(task.action==='sequence') {
      if(!Array.isArray(task.steps)||task.steps.length<1||task.steps.length>6||task.steps.some(s=>s.action==='sequence'))throw Error('Invalid task sequence.');
      let result;
      for(let i=0;i<task.steps.length;i++) {
        try {
          const step=result?.context?{...task.steps[i],context:result.context}:task.steps[i];
          result=await execute(step);
          if(result.verified!==true && i<task.steps.length-1)throw Error('The previous result is unverified; remaining steps were not run.');
        }catch(error){throw Error('Step '+(i+1)+' of '+task.steps.length+' failed: '+error.message);}
      }
      return result;
    }
    if(task.action==='new_tab') {
      await flow.act('Creating a new tab',async()=>{
        tab=await chrome.tabs.create({active:true});
        await chrome.windows.update(tab.windowId,{focused:true});
      });
      await flow.verify('Checking the new tab',async()=>{
        tab=await chrome.tabs.get(tab.id);return tab.active;
      });
      return confirmed('Opened a new tab','Created tab exists and is active');
    }
    if(task.action==='github_repo') {
      await siteTab('https://github.com/');await loaded();
      const {user}=await flow.observe('Reading your GitHub account',()=>page({op:'github_user'}));
      await navigate('https://github.com/'+encodeURIComponent(user)+'?tab=repositories');
      await flow.observe('Finding the repository filter',()=>page({op:'github_filter',query:task.query,prepareOnly:true}));
      await flow.act('Filtering your repositories',()=>page({op:'github_filter',query:task.query}));
      const repo=await flow.observe('Finding the matching repository',()=>page({op:'github_repository',query:task.query}));
      await navigate(repo.url);
      return confirmed('Opened repository '+repo.title,'Requested repository URL loaded',{url:tab.url});
    }
    if(['search','play','navigate'].includes(task.action)) {
      const site=task.site||siteOf(tab?.url)||'google';
      const url=task.action==='navigate'?task.url:sites[site];
      if(!url||!/^https?:\/\//.test(url))throw Error('Only supported web destinations can be searched.');
      await siteTab(url);
      if(task.action==='navigate') {
        await navigate(url);return confirmed('Opened '+new URL(tab.url).hostname,'Requested destination URL loaded',{url:tab.url});
      }
      if(site==='spotify') {
        const destination=sites.spotify+'/'+encodeURIComponent(task.query);
        if(tab.url!==destination)await navigate(destination);
      }
      await loaded();
      if(site!=='spotify') {
        await flow.observe('Finding the '+site+' search field',()=>page({op:'search',site,query:task.query,prepareOnly:true}));
        await flow.act('Submitting '+site+' search',()=>page({op:'search',site,query:task.query}));
      }
      await flow.verify('Waiting for '+site+' search results',async()=>{
        const current=await chrome.tabs.get(tab.id),u=new URL(current.url);
        const matched=site==='google'?u.searchParams.get('q')===task.query:site==='youtube'?u.searchParams.get('search_query')===task.query:decodeURIComponent(u.pathname).toLowerCase()==='/search/'+task.query.toLowerCase();
        return siteOf(current.url)===site && matched && await page({op:'search_ready',site,query:task.query});
      });
      // The browser can replace its URL during form submission. Context must
      // use the verified current tab rather than the pre-search snapshot.
      tab=await chrome.tabs.get(tab.id);
      if(task.action==='play') {
        if(site==='youtube')return execute({action:'result',index:task.index||1,play:true});
        if(site!=='spotify')throw Error('Playback is supported on Spotify and YouTube.');
        await flow.observe('Finding a playable Spotify song',()=>page({op:'play',query:task.query,mode:task.mode,prepareOnly:true}));
        const selected=await flow.act('Starting Spotify playback',()=>page({op:'play',query:task.query,mode:task.mode}));
        await flow.verify('Confirming Spotify playback',async()=> (await page({op:'playing',query:selected.track,trackUrl:selected.trackUrl})).playing,12000);
        return confirmed('Playing '+selected.track+' on Spotify','Matching track and playing controls observed');
      }
      return confirmed('Searched '+site+' for '+task.query,'Matching search URL and rendered results observed',{
        url:tab.url,context:{tabId:tab.id,url:tab.url,site,query:task.query}
      });
    }
    if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
    await focus(tab);
    if(task.action==='result') {
      if(!task.context || task.context.tabId!==tab.id || task.context.url!==tab.url) {
        throw Error('Those search results are no longer current. Search again before choosing a result.');
      }
      const selected=await flow.observe('Finding the requested result',()=>page({op:'result',index:task.index,resolve:true}));
      await navigate(selected.url);
      if(task.play) {
        if(siteOf(tab.url)!=='youtube')throw Error('This result is not a YouTube video.');
        await flow.observe('Waiting for the video player',()=>page({op:'video_ready'}));
        await flow.act('Starting the video',()=>page({op:'video_play'}));
        await flow.verify('Confirming video playback',async()=> (await page({op:'video_playing'})).playing);
      }
      return confirmed((task.play?'Playing ':'Opened ')+selected.title,task.play?'Requested video URL and playing media observed':'Requested result URL loaded',{url:tab.url});
    }
    if(task.action==='fill') {
      const observation=await flow.observe('Observing the requested field',()=>page({op:'inspect',...task}));
      const guarded={...task,control:observation.control,page:observation.page};
      const result=await flow.act('Filling the requested field',()=>page({op:'fill',...guarded}));
      await flow.verify('Checking the field value',()=>page({op:'fill',...guarded,verifyOnly:true}));
      return confirmed(result.message,'Field value read back exactly');
    }
    if(task.action==='click') {
      const observation=await flow.observe('Observing the requested control',()=>page({op:'inspect',...task}));
      return flow.act('Clicking the requested control',()=>page({op:'click',...task,control:observation.control,page:observation.page}));
    }
    return page({op:task.action,...task});
  }
  try {
    const tabs=await chrome.tabs.query({currentWindow:true});tab=tabs.find(t=>t.active);
    const result=await execute(req);
    return {...result,trace:flow.trace};
  }catch(error){error.trace=flow.trace;throw error;}
}
function connect() {
  if(port)return;
  const connection=chrome.runtime.connectNative('io.hyprash.browser');port=connection;
  connection.onMessage.addListener(async req=>{
    let response;
    try {
      const progress=req.progress?event=>connection.postMessage({id:req.id,progress:event}):undefined;
      response={id:req.id,result:await run(req,progress)};
    }catch(error){response={id:req.id,error:error.message,trace:error.trace};}
    try{connection.postMessage(response);}catch(error){console.warn('Native connection closed',error.message);}
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
