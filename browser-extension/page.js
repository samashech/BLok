// Executed in Chrome's isolated world. Page text is data, never executable input.
export async function pageAction(request) {
  const visible = e => { const r=e.getBoundingClientRect(),s=getComputedStyle(e); return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'; };
  const norm = s => String(s||'').toLowerCase().replace(/[’]/g,"'").replace(/\s+/g,' ').trim();
  const name = e => (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim() || e.getAttribute('aria-label') || (e.labels && [...e.labels].map(l=>l.innerText).join(' ')) || e.getAttribute('placeholder') || e.innerText || e.title || '';
  const nodes = [...document.querySelectorAll('button,a[href],input,textarea,select,[role="button"],[role="link"],[role="textbox"],[contenteditable="true"]')].filter(visible);
  const message = text => ({message:text,url:location.href,title:document.title});
  const setValue = (e,text) => {
    if(e.matches('input[type="password"]')) throw Error('Password fields require you to type directly.');
    e.focus();
    const proto=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
    if(e.isContentEditable) e.textContent=text; else if(setter) setter.call(e,text); else throw Error('That control is not an editable field.');
    e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));
    e.dispatchEvent(new Event('change',{bubbles:true}));
    if(norm(e.value??e.textContent)!==norm(text)) throw Error('The field did not accept the text.');
  };
  if(request.op==='inspect') return {url:location.href,title:document.title,controls:nodes.map(e=>({name:name(e).slice(0,120),role:e.getAttribute('role')||e.tagName.toLowerCase()})).filter(e=>e.name).slice(0,120)};
  if(request.op==='search') {
    const selectors=request.site==='google'?'textarea[name="q"],input[name="q"]':request.site==='youtube'?'input[name="search_query"],input#search': 'input[data-testid="search-input"],input[placeholder*="play"],input[role="searchbox"]';
    const field=[...document.querySelectorAll(selectors)].find(visible);
    if(!field) throw Error('Search field is not available yet. Dismiss any sign-in or consent dialog first.');
    setValue(field,request.query);
    if(request.site==='spotify') return message('Entered Spotify search');
    const form=field.closest('form');
    const button=request.site==='youtube'?document.querySelector('button.ytSearchboxComponentSearchButton,button#search-icon-legacy'):form?.querySelector('[type="submit"]');
    if(button) button.click(); else if(form) form.requestSubmit(); else throw Error('Could not identify the search submit control.');
    return message('Submitted search');
  }
  if(request.op==='search_ready') {
    if(request.site==='youtube') {
      const field=document.querySelector('input[name="search_query"],input#search');
      return location.pathname==='/results' && norm(field?.value)===norm(request.query)
        && !![...document.querySelectorAll('ytd-search ytd-video-renderer a#video-title,ytd-search ytd-reel-item-renderer a[href]')].find(visible)
        && !document.querySelector('yt-page-navigation-progress[aria-valuenow]:not([aria-valuenow="100"])');
    }
    return true;
  }
  if(request.op==='github_user') {
    if(location.hostname!=='github.com') throw Error('Open GitHub first.');
    const user=document.querySelector('meta[name="user-login"]')?.content;
    if(!user) throw Error('Sign into GitHub in this browser first.');
    return {user};
  }
  if(request.op==='github_filter') {
    const field=document.querySelector('input#your-repos-filter,input[name="q"]');
    if(!field || !visible(field)) throw Error('The repository filter is not available yet.');
    setValue(field,request.query);
    const form=field.closest('form');
    if(form) form.requestSubmit();
    return message('Filtered repositories');
  }
  if(request.op==='github_repository') {
    const compact=s=>norm(s).replace(/[-_\s]/g,'');
    const owner=location.pathname.split('/')[1];
    const links=[...document.querySelectorAll('a[itemprop="name codeRepository"],a[itemprop="name"],#user-repositories-list h3 a')].filter(visible);
    const matches=[...new Map(links.filter(e=>{
      const u=new URL(e.href),parts=u.pathname.split('/').filter(Boolean);
      return u.hostname==='github.com' && parts.length===2 && norm(parts[0])===norm(owner) && compact(parts[1])===compact(request.query);
    }).map(e=>[e.href,e])).values()];
    if(matches.length!==1) throw Error(matches.length?'Several repositories match that name. Use the exact name.':'No matching repository appeared in your repository list.');
    return {url:matches[0].href,title:name(matches[0]).trim()};
  }
  if(request.op==='video_play') {
    const video=document.querySelector('video.html5-main-video,video');
    if(!video) throw Error('The video player has not loaded yet.');
    await video.play();
    return {playing:!video.paused && !video.ended && video.readyState>=2};
  }
  if(request.op==='video_playing') {
    const video=document.querySelector('video.html5-main-video,video');
    return {playing:!!video&&!video.paused&&!video.ended&&video.readyState>=2};
  }
  if(request.op==='result') {
    let links=[];
    if(/(^|\.)google\./.test(location.hostname)) {
      // Result headings include sponsored results; nav/chips/sitelinks do not.
      links=[...document.querySelectorAll('#search a:has(h3),#rso a:has(h3),#tads a:has(h3),#tads a[data-pcu],#tads [role="heading"]')].map(e=>e.closest('a')||e.querySelector('a')).filter(Boolean);
    } else if(/(^|\.)youtube\.com$/.test(location.hostname)) {
      links=[...document.querySelectorAll('ytd-search a#video-title,ytd-search a#video-title-link,ytd-search ytd-ad-slot-renderer a[href*="watch"]')];
    } else throw Error('Open a Google or YouTube results page first.');
    links=[...new Set(links)].filter(e=>visible(e)&&/^https?:/.test(e.href));
    links.sort((a,b)=>a.getBoundingClientRect().top-b.getBoundingClientRect().top||a.getBoundingClientRect().left-b.getBoundingClientRect().left);
    const e=links[(request.index||1)-1];
    if(!e) throw Error('That result is not present on this results page.');
    const label=name(e).slice(0,150);
    if(request.resolve)return {url:e.href,title:label};
    e.scrollIntoView({block:'center'});e.click();return message('Opened '+label);
  }
  if(request.op==='play') {
    const rows=[...document.querySelectorAll('[data-testid="tracklist-row"],[role="row"]')].filter(visible);
    const words=norm(request.query);
    const titleLink=r=>r.querySelector('a[href*="/track/"],[data-testid="internal-track-link"]');
    const byArtist=r=>[...r.querySelectorAll('a[href*="/artist/"]')].some(a=>norm(a.innerText)===words);
    const row=request.mode==='artist'?rows.find(byArtist):
      rows.find(r=>norm(titleLink(r)?.innerText)===words)||rows.find(byArtist);
    if(!row) throw Error('No matching playable song appeared. Try an exact song or artist name.');
    const track=titleLink(row);
    const play=row.querySelector('button[aria-label^="Play"],button[data-testid="play-button"]');
    if(!play || play.disabled || play.getAttribute('aria-disabled')==='true') throw Error('Spotify has not provided a playable control for this song.');
    row.scrollIntoView({block:'center'});
    play.click();return {message:'Requested playback',track:track.innerText,trackUrl:track.href};
  }
  if(request.op==='playing') {
    const pause=document.querySelector('[data-testid="control-button-playpause"][aria-label="Pause"]');
    const track=document.querySelector('[data-testid="context-item-link"]');
    const same=request.trackUrl?new URL(track?.href||location.href).pathname===new URL(request.trackUrl).pathname:norm(track?.innerText)===norm(request.query);
    return {playing:!!pause&&same,track:track?.innerText||''};
  }
  if(request.op==='click'||request.op==='fill') {
    const target=norm(request.target).replace(/^(the )/,'').replace(/ (button|link|field)$/,'');
    const role=request.role || (/ (field|button|link)$/.exec(norm(request.target))||[])[1];
    const eligible=request.op==='fill'||role==='field'?nodes.filter(e=>e.matches('input,textarea,[contenteditable="true"]')):role==='button'?nodes.filter(e=>e.matches('button,[role="button"],input[type="submit"]')):role==='link'?nodes.filter(e=>e.matches('a[href],[role="link"]')):nodes;
    let matches=eligible.filter(e=>norm(name(e))===target);
    if(!matches.length) matches=eligible.filter(e=>norm(name(e)).includes(target));
    if(matches.length!==1) throw Error(matches.length?'More than one control matches. Say its full label.':'No visible control named '+request.target);
    const e=matches[0];if(e.disabled||e.getAttribute('aria-disabled')==='true') throw Error('That control is disabled.');
    e.scrollIntoView({block:'center'});
    if(request.op==='fill') {setValue(e,request.text);return message('Filled '+name(e));}
    if(e.matches('input,textarea,[contenteditable="true"]')) {e.focus();return message('Focused '+name(e));}
    e.click();return message('Activated '+name(e));
  }
  throw Error('Unsupported browser action');
}
