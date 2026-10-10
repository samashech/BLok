// Executed in Chrome's isolated world. Page text is data, never executable input.
export async function pageAction(request) {
  const visible = e => { const r=e.getBoundingClientRect(),s=getComputedStyle(e); return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'; };
  const norm = s => String(s||'').toLowerCase().replace(/[’]/g,"'").replace(/\s+/g,' ').trim();
  const name = e => e.getAttribute('aria-label') || (e.labels && [...e.labels].map(l=>l.innerText).join(' ')) || e.getAttribute('placeholder') || e.innerText || e.title || '';
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
  if(request.op==='result') {
    let links=[];
    if(/(^|\.)google\./.test(location.hostname)) {
      // Result headings include sponsored results; nav/chips/sitelinks do not.
      links=[...document.querySelectorAll('#search a:has(h3),#rso a:has(h3),#tads a:has(h3),#tads a[data-pcu],#tads [role="heading"]')].map(e=>e.closest('a')||e.querySelector('a')).filter(Boolean);
    } else if(/(^|\.)youtube\.com$/.test(location.hostname)) {
      links=[...document.querySelectorAll('a#video-title,a#video-title-link,ytd-ad-slot-renderer a[href*="watch"]')];
    } else throw Error('Open a Google or YouTube results page first.');
    links=[...new Set(links)].filter(e=>visible(e)&&/^https?:/.test(e.href));
    links.sort((a,b)=>a.getBoundingClientRect().top-b.getBoundingClientRect().top||a.getBoundingClientRect().left-b.getBoundingClientRect().left);
    const e=links[(request.index||1)-1];
    if(!e) throw Error('That result is not present on this results page.');
    const label=name(e).slice(0,150);e.scrollIntoView({block:'center'});e.click();return message('Opened '+label);
  }
  if(request.op==='play') {
    const rows=[...document.querySelectorAll('[data-testid="tracklist-row"],[role="row"]')].filter(visible);
    const words=norm(request.query);
    const row=rows.find(r=>[...r.querySelectorAll('a[href*="/track/"],[data-testid="internal-track-link"]')].some(a=>norm(a.innerText)===words));
    if(!row) throw Error('No matching playable track appeared. Check the song title and your Spotify account.');
    const play=row.querySelector('button[aria-label^="Play"],button[data-testid="play-button"]');
    if(!play) throw Error('Spotify has not provided a play control for this track.');
    play.click();return message('Requested playback');
  }
  if(request.op==='playing') {
    const pause=document.querySelector('[data-testid="control-button-playpause"][aria-label="Pause"]');
    const track=document.querySelector('[data-testid="context-item-link"]');
    return {playing:!!pause&&norm(track?.innerText)===norm(request.query),track:track?.innerText||''};
  }
  if(request.op==='click'||request.op==='fill') {
    const target=norm(request.target).replace(/^(the )/,'').replace(/ (button|link|field)$/,'');
    const eligible=request.op==='fill'?nodes.filter(e=>e.matches('input,textarea,[contenteditable="true"]')):nodes;
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
