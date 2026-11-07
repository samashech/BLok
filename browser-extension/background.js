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
  if(req.action==='ping')return {message:'Brave connected',version:'phase12-v1'};
  if(req.action==='active') {
    // Tab metadata only; no page script runs.
    const [current]=await chrome.tabs.query({active:true,lastFocusedWindow:true});
    if(!current)throw Error('No browser tab is active.');
    return {tabId:current.id,tab_id:current.id,url:current.url,title:current.title,verified:true};
  }
  const {epoch:turn}=await chrome.storage.session.get('epoch');
  // Replaying a taught skill can take a few minutes; everything else keeps the short budget.
  const flow=execution({progress,budget:req.action==='replay'?170000:undefined,check:async()=>{
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
    if(result?.blokError)throw Error(result.blokError);
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
  const isBlankOrNewTab=u=>!u||u==='about:blank'||u==='chrome://newtab/'||u==='brave://newtab/';
  async function siteTab(url, targetTabId) {
    if(targetTabId) {
      try {
        const t=await chrome.tabs.get(targetTabId);
        if(t) {
          tab=t;await focus(tab);
          if(isBlankOrNewTab(tab.url)) {
            await navigate(url);return;
          }
        }
      } catch(e) {
        throw Error('The targeted tab '+targetTabId+' was closed or no longer exists.');
      }
    }
    const host=new URL(url).hostname;
    const candidates=await chrome.tabs.query({currentWindow:true});
    const matching=t=>{try{return new URL(t.url).hostname===host;}catch{return false;}};
    const activeTab=candidates.find(t=>t.active);
    const existing=candidates.find(t=>t.active&&matching(t))||candidates.find(matching);
    if(existing)await focus(existing);
    else if((tab && tab.active && isBlankOrNewTab(tab.url)) || (activeTab && isBlankOrNewTab(activeTab.url))) {
      tab = (tab && tab.active && isBlankOrNewTab(tab.url)) ? tab : activeTab;
      await navigate(url);
    }
    else await flow.act('Opening a browser tab',async()=>{
      tab={...await chrome.tabs.create({url,active:true}),url};
      await chrome.windows.update(tab.windowId,{focused:true});
    });
  }
  async function execute(task) {
    await flow.guard();
    if(task.action==='inspect') {
      if(task.site&&sites[task.site])await siteTab(sites[task.site], task.target_tab_id);
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await loaded();
      const observation=await flow.observe('Observing visible controls',()=>page({op:'inspect'}));
      return confirmed('Observed '+observation.controls.length+' visible controls','Current tab and document observed',{
        tab_id:tab.id,tabId:tab.id,observation:{url:observation.url,title:observation.title,
          controls:observation.controls.map(({name,role,editable,disabled})=>({name,role,editable,disabled}))}
      });
    }
    if(task.action==='sequence') {
      if(!Array.isArray(task.steps)||task.steps.length<1||task.steps.length>6||task.steps.some(s=>s.action==='sequence'))throw Error('Invalid task sequence.');
      let result;
      for(let i=0;i<task.steps.length;i++) {
        try {
          let step=task.steps[i];
          if(result?.context) step={...step,context:result.context};
          if((result?.tab_id || result?.tabId) && !step.target_tab_id) step={target_tab_id:result.tab_id||result.tabId,...step};
          result=await execute(step);
          if(result.verified!==true && i<task.steps.length-1)throw Error('The previous result is unverified; remaining steps were not run.');
        }catch(error){throw Error('Step '+(i+1)+' of '+task.steps.length+' failed: '+error.message);}
      }
      return result;
    }
    if(['hints','hint','scroll','focused_field','read_page'].includes(task.action)) {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      const result=await page({op:task.action,...task});
      return {...(typeof result==='object'?result:{}),verified:true,tabId:tab.id,url:tab.url};
    }
    if(task.action==='open_tab') {
      if(!/^https?:\/\//.test(task.url||''))throw Error('That number is not a link.');
      const created=await chrome.tabs.create({url:task.url,active:true});
      return confirmed('Opened it in a new tab','New tab created',{tabId:created.id});
    }
    if(task.action==='watch_start') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Open the page where you want to show me, then say "watch me".');
      await chrome.storage.session.set({watch:{tabId:tab.id,steps:[{op:'navigate',url:tab.url}]}});
      await chrome.tabs.sendMessage(tab.id,{type:'blok-watch',on:true}).catch(()=>{});
      return confirmed('Watching','Recording started in the current tab',{url:tab.url,tabId:tab.id});
    }
    if(task.action==='watch_stop') {
      const {watch}=await chrome.storage.session.get('watch');
      await chrome.storage.session.remove('watch');
      if(watch)await chrome.tabs.sendMessage(watch.tabId,{type:'blok-watch',on:false}).catch(()=>{});
      return {verified:true,message:'Stopped watching',steps:watch?.steps||[]};
    }
    if(task.action==='replay') {
      const steps=task.steps||[];
      if(!steps.length)throw Error('That skill has no steps.');
      for(const [i,step] of steps.entries()) {
        const where='Step '+(i+1)+' of '+steps.length;
        if(step.op==='navigate') {
          const current=tab&&/^https?:/.test(tab.url)?new URL(tab.url):null, wanted=new URL(step.url);
          if(!current||current.origin+current.pathname!==wanted.origin+wanted.pathname)await (tab?navigate(step.url):siteTab(step.url));
          await loaded();continue;
        }
        if(step.op==='secret')throw Error(where+' needs your password for "'+step.name+'". Sign in yourself, then run it again.');
        if(!tab||!/^https?:/.test(tab.url))throw Error(where+': no web page is open.');
        await loaded();
        const found=await flow.observe(where+': finding "'+step.name+'"',()=>page({op:'find_control',name:step.name,role:step.role}),12000);
        const before=tab.url;
        if(step.op==='fill') {
          await flow.act(where+': typing into "'+step.name+'"',()=>page({op:'fill',control:found.control,page:found.page,text:step.value}));
        } else if(step.op==='enter') {
          await flow.act(where+': pressing Enter',()=>page({op:'submit',control:found.control,page:found.page}));
        } else {
          await flow.act(where+': clicking "'+step.name+'"',()=>page({op:'click',control:found.control,page:found.page}));
        }
        // A click may start a navigation; let it settle before looking for the next control.
        await new Promise(r=>setTimeout(r,500));
        tab=await chrome.tabs.get(tab.id);
        if(tab.url!==before||tab.status!=='complete')await loaded();
      }
      return confirmed('Did all '+steps.length+' steps','Each control was found and used in order',{url:tab?.url,tabId:tab?.id});
    }
    if(task.action==='pointer') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      const found=await flow.observe('Finding what the mouse is pointing at',()=>page({op:'pointer'}),1500);
      return confirmed('Pointing at '+found.name,'Control under the mouse observed',{...found,tabId:tab.id});
    }
    if(task.action==='snapshot') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await loaded();
      const seen=await flow.observe('Looking at the page',()=>page({op:'snapshot',limit:task.limit}));
      return confirmed('Saw '+seen.controls.length+' controls','Current tab observed',{...seen,tab_id:tab.id,tabId:tab.id});
    }
    if(task.action==='click_observed') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await focus(tab);
      // Watch what the click causes, so BLoK can say what really happened.
      const created=[],downloads=[],before=tab.url;
      const onTab=t=>created.push(t),onDownload=d=>downloads.push(d);
      chrome.tabs.onCreated.addListener(onTab);chrome.downloads.onCreated.addListener(onDownload);
      let result,current;
      try {
        result=await flow.act('Clicking it',()=>page({op:'click',control:task.control,page:task.page}));
        for(let waited=0;waited<600&&!created.length&&!downloads.length;waited+=50){
          current=await chrome.tabs.get(tab.id).catch(()=>null);
          if(!current||(current.pendingUrl||current.url)!==before)break;
          await new Promise(r=>setTimeout(r,50));
        }
        current=await chrome.tabs.get(tab.id).catch(()=>null);
      } finally {chrome.tabs.onCreated.removeListener(onTab);chrome.downloads.onCreated.removeListener(onDownload);}
      await page({op:'hints',show:false}).catch(()=>{});
      const effects={};
      const moved=current&&(current.pendingUrl||current.url);
      if(created[0])effects.new_tab={tabId:created[0].id,url:created[0].pendingUrl||created[0].url||''};
      if(downloads[0])effects.download=String(downloads[0].filename||downloads[0].finalUrl||downloads[0].url||'a file').split(/[?#]/)[0].split(/[\\/]/).filter(Boolean).pop()||'a file';
      if(moved&&moved!==before)effects.navigated=moved;
      const seen=Object.keys(effects).length>0;
      return {...result,effects,verified:result.verified||seen,evidence:seen?'Browser reported what the click caused':result.evidence,tabId:tab.id};
    }
    if(task.action==='site_search') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await loaded();
      const before=tab.url;
      await flow.act('Searching this site',()=>page({op:'site_search',query:task.query}));
      await flow.verify('Waiting for results',async()=>{const t=await chrome.tabs.get(tab.id);return t.url!==before||t.status==='complete';},10000);
      tab=await chrome.tabs.get(tab.id);
      return confirmed('Searched '+new URL(tab.url).hostname+' for '+task.query,'Search submitted on the page',{url:tab.url,tabId:tab.id});
    }
    if(task.action==='links') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await loaded();
      const found=await flow.observe('Reading links on the page',()=>page({op:task.results?'result_links':'links',query:task.query||'',download:!!task.download}));
      return confirmed('Found '+found.links.length+' candidate links','Visible links observed',{...found,tab_id:tab.id,tabId:tab.id});
    }
    if(task.action==='download') {
      if(!/^https?:\/\//.test(task.url||''))throw Error('Only web URLs can be downloaded.');
      const id=await flow.act('Starting the download',()=>chrome.downloads.download({url:task.url}));
      const item=await flow.verify('Confirming the download',async()=>{const [d]=await chrome.downloads.search({id});return d&&d.state!=='interrupted'&&d.filename?d:false;},10000);
      return confirmed('Downloading '+item.filename.split('/').pop(),'Browser download item created',{download_id:id,filename:item.filename});
    }
    if(task.action==='click_download') {
      if(!tab||!/^https?:/.test(tab.url))throw Error('Focus a web page first.');
      await focus(tab);
      const since=new Date(Date.now()-1000).toISOString();
      await flow.act('Clicking the download link',()=>page({op:'click',control:task.control,page:task.page}));
      try {
        const item=await flow.verify('Waiting for the download to start',async()=>{
          const items=await chrome.downloads.search({startedAfter:since,orderBy:['-startTime']});
          return items.find(d=>d.state!=='interrupted'&&d.filename)||false;
        },15000);
        return confirmed('Downloading '+item.filename.split('/').pop(),'Browser download item created after the click',{filename:item.filename});
      } catch(error) {
        tab=await chrome.tabs.get(tab.id);
        return {message:'Clicked the link, but no download started yet. Now on '+new URL(tab.url).hostname+'. Say "click" and the next button name to continue.',verified:false,evidence:'No download item observed',tabId:tab.id,url:tab.url};
      }
    }
    if(task.action==='new_tab') {
      await flow.act('Creating a new tab',async()=>{
        tab=await chrome.tabs.create({active:true});
        await chrome.windows.update(tab.windowId,{focused:true});
      });
      await flow.verify('Checking the new tab',async()=>{
        tab=await chrome.tabs.get(tab.id);return tab.active;
      });
      return confirmed('Opened a new tab','Created tab exists and is active',{
        tab_id:tab.id,
        tabId:tab.id,
        url:tab.url,
        status:tab.status,
        active:true
      });
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
      await siteTab(url, task.target_tab_id);
      if(task.action==='navigate') {
        await navigate(url);return confirmed('Opened '+new URL(tab.url).hostname,'Requested destination URL loaded',{url:tab.url,tab_id:tab.id,tabId:tab.id});
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
        if(site==='youtube')return execute({action:'result',index:task.index||1,play:true,target_tab_id:tab.id});
        if(site!=='spotify')throw Error('Playback is supported on Spotify and YouTube.');
        await flow.observe('Finding a playable Spotify song',()=>page({op:'play',query:task.query,mode:task.mode,prepareOnly:true}));
        const selected=await flow.act('Starting Spotify playback',()=>page({op:'play',query:task.query,mode:task.mode}));
        await flow.verify('Confirming Spotify playback',async()=> (await page({op:'playing',query:selected.track,trackUrl:selected.trackUrl})).playing,12000);
        return confirmed('Playing '+selected.track+' on Spotify','Matching track and playing controls observed',{url:tab.url,tab_id:tab.id,tabId:tab.id});
      }
      return confirmed('Searched '+site+' for '+task.query,'Matching search URL and rendered results observed',{
        url:tab.url,tab_id:tab.id,tabId:tab.id,context:{tabId:tab.id,url:tab.url,site,query:task.query}
      });
    }
    if(task.action==='next_track') {
      const site='spotify';
      const url=sites.spotify;
      await siteTab(url, task.target_tab_id);
      await loaded();
      await flow.observe('Observing Spotify playback controls',()=>page({op:'spotify_controls_ready'}));
      const result=await flow.act('Skipping to next track on Spotify',()=>page({op:'next_track'}));
      await flow.verify('Confirming Spotify playback',async()=> (await page({op:'playing',query:result.track||''})).playing, 10000);
      return confirmed('Playing next track on Spotify','Skipped to next track and verified playback',{url:tab.url,tab_id:tab.id,tabId:tab.id,track:result.track});
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
        try {
          await flow.verify('Confirming video playback',async()=> (await page({op:'video_playing'})).playing);
        } catch(verifyError) {
          return confirmed('Found results for '+(selected.title||task.context?.query||'video')+' on YouTube, but playback could not be verified',
            'Requested video URL loaded; playback unverified',
            {url:tab.url,tab_id:tab.id,tabId:tab.id,playback_verified:false,partial_success:true});
        }
      }
      return confirmed((task.play?'Playing ':'Opened ')+selected.title,task.play?'Requested video URL and playing media observed':'Requested result URL loaded',{url:tab.url,tab_id:tab.id,tabId:tab.id,playback_verified:true});
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
// Steps reported by recorder.js while "watch me" is on; only from the watched tab.
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message?.type!=='blok-step'&&message?.type!=='blok-watching?')return;
  (async()=>{
    const {watch}=await chrome.storage.session.get('watch');
    const mine=watch&&sender.tab?.id===watch.tabId;
    if(message.type==='blok-watching?')return respond({watching:!!mine});
    if(!mine)return respond({});
    const last=watch.steps[watch.steps.length-1], step=message.step;
    // A field reports its value on change and again on Enter; keep one.
    if(!(last&&last.op==='fill'&&step.op==='fill'&&last.name===step.name&&last.value===step.value))watch.steps.push(step);
    if(watch.steps.length<=200)await chrome.storage.session.set({watch});
    respond({});
  })();
  return true;
});
function connect() {
  if(port)return;
  const connection=chrome.runtime.connectNative('io.blok.browser');port=connection;
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
