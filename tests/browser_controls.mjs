import {chromium} from 'playwright';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {pageAction,gameFrameText}=await import('data:text/javascript;base64,'+Buffer.from(await readFile(new URL('../browser-extension/page.js',import.meta.url))).toString('base64'));
const browser=await chromium.launch({executablePath:'/usr/bin/brave-origin',headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage();
 await page.route('https://www.google.com/**',r=>r.fulfill({contentType:'text/html',body:`<form action="/search"><textarea name="q"></textarea><button type="submit">Google Search</button></form><div id="tads"><a href="https://example.com/ad"><h3>Sponsored first</h3></a></div><div id="search"><a href="https://example.com/normal"><h3>Normal second</h3></a></div>`}));
 await page.route('https://example.com/**',r=>r.fulfill({contentType:'text/html',body:'<h1>Selected result</h1>'}));
 await page.goto('https://www.google.com');
 assert.equal(await page.evaluate(pageAction,{op:'search',site:'google',query:'rock and roll',prepareOnly:true}),true);
 assert.equal(await page.locator('textarea').inputValue(),'');
 await page.evaluate(pageAction,{op:'search',site:'google',query:'rock and roll'});
 await page.waitForURL('**/search?q=rock+and+roll');
 await page.evaluate(pageAction,{op:'result',index:1});
 await page.waitForURL('https://example.com/ad');
 console.log('PASS: Google field submission and first sponsored result');
 await page.route('https://www.youtube.com/**',r=>r.fulfill({contentType:'text/html',body:'<form action="/results"><input name="search_query"><button class="ytSearchboxComponentSearchButton">Search</button></form>'}));
 await page.goto('https://www.youtube.com');
 await page.evaluate(pageAction,{op:'search',site:'youtube',query:'bbs'});
 await page.waitForURL('**/results?search_query=bbs');
 console.log('PASS: YouTube search stays on YouTube');
 await page.setContent('<label>Name<input></label><button onclick="this.textContent=\'Done\'">Save</button>');
 await page.evaluate(pageAction,{op:'fill',target:'Name',text:'hello'});
 assert.equal(await page.locator('input').inputValue(),'hello');
 assert.equal(await page.evaluate(pageAction,{op:'fill',target:'Name',text:'hello',verifyOnly:true}),true);
 assert.equal(await page.evaluate(pageAction,{op:'fill',target:'Name',text:'HELLO',verifyOnly:true}),false);
 await page.evaluate(pageAction,{op:'click',target:'Save'});
 assert.equal(await page.locator('button').textContent(),'Done');
	await page.setContent('<span id=label>Search</span><input aria-labelledby=label><button aria-label=Search>Search</button>');
 await page.evaluate(pageAction,{op:'click',target:'Search',role:'field'});
 assert.equal(await page.locator('input').evaluate(e=>document.activeElement===e),true);
	await page.evaluate(pageAction,{op:'click',target:'Search button'});
	await page.setContent('<label>Name<input></label><button>Save</button>');
	const observed=await page.evaluate(pageAction,{op:'inspect',target:'Save',action:'click'});
	assert.equal(observed.control.role,'button');
	await page.evaluate(pageAction,{op:'click',target:'Save',control:observed.control,page:observed.page});
	await page.locator('button').evaluate(e=>e.outerHTML='<button>Save</button>');
	await assert.rejects(page.evaluate(pageAction,{op:'click',target:'Save',control:observed.control,page:observed.page}),/changed after observation/);
	await page.setContent('<div id=host></div>');
	await page.locator('#host').evaluate(host=>{const root=host.attachShadow({mode:'open'});root.innerHTML='<button aria-label="Shadow save">Save</button>';});
	const shadow=await page.evaluate(pageAction,{op:'inspect',target:'Shadow save',action:'click'});
	assert.equal(shadow.controls.some(control=>control.name==='Shadow save'),true);
	await page.evaluate(pageAction,{op:'click',target:'Shadow save',control:shadow.control,page:shadow.page});
	await page.setContent('<button>Save</button><button>Save</button>');
 await assert.rejects(page.evaluate(pageAction,{op:'click',target:'Save'}),/More than one/);
 console.log('PASS: named controls, field verification and ambiguous match rejection');
 await page.setContent(`<div style="height:3000px"><header><nav aria-label="Top"><a href="/pricing">Pricing</a></nav></header>
  <main><label>Email<input value="me@example.com"></label><label>Password<input type="password" value="hunter2secret"></label><input type="submit" value="Log in">
  <a href="/x"><button>Inner same</button></a><a href="/y"><span>Outer</span><button>Inner different</button></a>
  <button aria-label="Close"><svg></svg></button><button title="Share"></button><button><img alt="Profile"></button><button></button><button style="display:none">Hidden</button>
  <button disabled>Off</button><button aria-expanded="true">Menu</button></main></div><footer style="position:absolute;top:2900px"><button>Save</button></footer>`);
 const snap=await page.evaluate(pageAction,{op:'snapshot'});
 const byName=Object.fromEntries(snap.controls.map(c=>[c.name,c]));
 assert.equal(JSON.stringify(snap).includes('hunter2secret'),false);
 assert.equal(JSON.stringify(snap).includes('me@example.com'),false);
 assert.deepEqual(byName['Password'].state,['password']);
 assert.deepEqual(byName['Email'].state,['filled']);
 assert.equal(byName['Log in'].role,'button');
 assert.equal(byName['Pricing'].section,'Top');
 assert.equal(byName['Log in'].section,'main');
 assert.equal(byName['Save'].section,'footer');
 assert.equal(byName['Save'].in_view,false);
 assert.equal(snap.controls.at(-1).name,'Save');              // what's on screen comes first
 assert.ok(byName['Close']&&byName['Share']&&byName['Profile']);  // icon-only buttons still get names
 assert.equal(byName['Hidden'],undefined);
 assert.equal(byName['Off'].disabled,true);
 assert.deepEqual(byName['Menu'].state,['expanded']);
 assert.equal(snap.controls.filter(c=>c.name==='Inner same').length,1);   // a link wrapping its button is one control
 assert.ok(byName['Inner different']&&snap.controls.some(c=>c.name.startsWith('Outer')));   // different names stay separate
 assert.match(byName['Save'].ref,/^e\d+$/);
 assert.equal((await page.evaluate(pageAction,{op:'snapshot',limit:2})).truncated,true);
 await page.evaluate(pageAction,{op:'click',control:byName['Menu'].control,page:snap.page});  // a reference ID clicks that control
 await page.locator('button:text-is("Menu")').evaluate(e=>e.outerHTML='<button aria-expanded="true">Changed</button>');
 await assert.rejects(page.evaluate(pageAction,{op:'click',control:byName['Menu'].control,page:snap.page}),/changed after observation/);
 console.log('PASS: page snapshots: compact, on-screen first, no field contents');
 await page.route('https://gulper.io/**',r=>r.fulfill({contentType:'text/html',body:'<div>Score: 40</div><div style="display:none">hidden 999</div><input value="secret typed text">'}));
 await page.route('https://ads.example.com/**',r=>r.fulfill({contentType:'text/html',body:'<div>Score: 7, buy now</div>'}));
 await page.goto('https://gulper.io/');
 const seenText=await page.evaluate(gameFrameText,['gulper.io']);
 assert.match(seenText.text,/Score: 40/);
 assert.doesNotMatch(seenText.text,/hidden 999|secret typed text/);
 await page.goto('https://ads.example.com/');
 assert.equal(await page.evaluate(gameFrameText,['gulper.io']),null);   // other frames, like ads, stay out of it
 console.log('PASS: only allowed game frames answer, with only what is showing');
 await page.setContent('<button>Save</button>');
 assert.equal((await page.evaluate(pageAction,{op:'click',target:'Save'})).verified,false);
 await page.setContent('<label>Name<input oninput="queueMicrotask(()=>this.value=\'original\')"></label>');
 await page.evaluate(pageAction,{op:'fill',target:'Name',text:'replacement'});
 assert.equal(await page.evaluate(pageAction,{op:'fill',target:'Name',text:'replacement',verifyOnly:true}),false);
 await page.setContent(`<div data-testid="tracklist-row"><a href="/track/1">God's Plan</a><button aria-label="Play God's Plan" onclick="document.querySelector('#transport').setAttribute('aria-label','Pause')">Play</button></div><button id="transport" data-testid="control-button-playpause" aria-label="Play"></button><a data-testid="context-item-link">God's Plan</a>`);
 await page.evaluate(pageAction,{op:'play',query:"God's Plan"});
 assert.equal((await page.evaluate(pageAction,{op:'playing',query:"God's Plan"})).playing,true);
 console.log('PASS: matching Spotify track activation and playback-state check');
 await page.setContent(`<div data-testid="tracklist-row"><a href="/track/wrong">Unrelated song</a><a href="/artist/other">Someone else</a><button aria-label="Play unrelated">Play</button></div><div data-testid="tracklist-row"><a href="/track/baby">Baby</a><a href="/artist/justin">Justin Bieber</a><button aria-label="Play Baby" onclick="this.dataset.played='yes'">Play</button></div>`);
 assert.equal((await page.evaluate(pageAction,{op:'play',query:'justin bieber',mode:'artist',prepareOnly:true})).track,'Baby');
 assert.equal(await page.locator('[aria-label="Play Baby"]').getAttribute('data-played'),null);
 const selected=await page.evaluate(pageAction,{op:'play',query:'justin bieber',mode:'artist'});
 assert.equal(selected.track,'Baby');
 assert.equal(await page.locator('[aria-label="Play Baby"]').getAttribute('data-played'),'yes');
 await page.setContent(`<input value="justin bieber"><main><div role="row"><a href="/artist/justin">Justin Bieber</a><button aria-label="Play">Play</button></div><section><a href="/track/wrong">Another song</a><a href="/artist/other">Someone else</a><button aria-label="Play Another song">Play</button></section><section><div><a href="/track/baby">Baby</a><a href="/artist/justin">Justin Bieber</a></div><button aria-label="Play Baby" onclick="this.dataset.played='yes'">Play</button></section></main>`);
 assert.equal(await page.evaluate(pageAction,{op:'search_ready',site:'spotify',query:'justin bieber'}),true);
 assert.equal((await page.evaluate(pageAction,{op:'play',query:'justin bieber',mode:'artist'})).track,'Baby');
 assert.equal(await page.locator('[aria-label="Play Baby"]').getAttribute('data-played'),'yes');
 await page.setContent('<main></main>');
 assert.equal(await page.evaluate(pageAction,{op:'search_ready',site:'spotify',query:'justin bieber'}),false);
 console.log('PASS: Spotify song cards and delayed search rendering');
 await page.setContent(`<main><section><a href="/track/baby">Baby</a><a href="/artist/justin">Justin Bieber</a><button aria-label="Pause Baby" onclick="this.dataset.clicked='yes'">Pause</button></section></main><footer><a href="/track/baby">Baby</a><button aria-label="Pause">Pause</button></footer>`);
 const alreadyPlaying=await page.evaluate(pageAction,{op:'play',query:'justin bieber',mode:'artist'});
 assert.equal(await page.locator('[aria-label="Pause Baby"]').getAttribute('data-clicked'),null);
 assert.equal((await page.evaluate(pageAction,{op:'playing',trackUrl:alreadyPlaying.trackUrl})).playing,true);
 assert.equal((await page.evaluate(pageAction,{op:'playing',trackUrl:'https://www.youtube.com/track/other'})).playing,false);
 await page.locator('footer').evaluate(e=>{const div=document.createElement('div');div.innerHTML=e.innerHTML;e.replaceWith(div);});
 assert.equal((await page.evaluate(pageAction,{op:'playing',trackUrl:alreadyPlaying.trackUrl})).playing,true);
 console.log('PASS: current Spotify transport and already-playing song');
 await page.route('https://github.com/**',r=>r.fulfill({contentType:'text/html',body:`<meta name="user-login" content="fixture-user"><form><input id="your-repos-filter" name="q"></form><div id="user-repositories-list"><h3><a href="/fixture-user/ClickyAI" itemprop="name codeRepository">ClickyAI</a></h3></div>`}));
 await page.goto('https://github.com/fixture-user?tab=repositories');
 assert.equal((await page.evaluate(pageAction,{op:'github_user'})).user,'fixture-user');
 assert.equal((await page.evaluate(pageAction,{op:'github_repository',query:'clickyai'})).url,'https://github.com/fixture-user/ClickyAI');
 console.log('PASS: artist matches track artist, and GitHub resolves repository within signed-in owner');
 await page.route('https://downloads.example.org/**',r=>r.fulfill({contentType:'text/html',body:`<title>SuperTux download</title><nav><a href="/about">About</a></nav><a href="/files/supertux.AppImage">Download SuperTux for Linux</a><a href="/files/supertux.exe">Download for Windows</a><button>Donate</button>`}));
 await page.goto('https://downloads.example.org/');
 const found=await page.evaluate(pageAction,{op:'links',query:'supertux',download:true});
 assert.deepEqual(found.links.map(l=>l.name),['Download SuperTux for Linux','Download for Windows']);
 await page.evaluate(pageAction,{op:'click',control:found.links[0].control,page:found.page}).catch(()=>{});
 await page.goto('https://www.google.com/search?q=x');
 const results=await page.evaluate(pageAction,{op:'result_links'});
 assert.deepEqual(results.links.map(l=>l.name),['Normal second']);
 console.log('PASS: download links ranked (Linux first, non-downloads dropped) and Google result list');
 await page.setContent(`<div style="padding:40px"><button id=sub style="width:120px;height:40px" onclick="this.dataset.clicked='yes'"><span>Subscribe</span></button><p style="margin-top:80px">plain text</p></div>`);
 await page.evaluate(await readFile(new URL('../browser-extension/pointer.js',import.meta.url),'utf8'));
 const box=await page.locator('#sub').boundingBox();
 await page.mouse.move(box.x+30,box.y+20);
 const pointed=await page.evaluate(pageAction,{op:'pointer'});
 assert.equal(pointed.name,'Subscribe');
 await page.evaluate(pageAction,{op:'click',control:pointed.control,page:pointed.page});
 assert.equal(await page.locator('#sub').getAttribute('data-clicked'),'yes');
 await page.mouse.move(box.x+30,box.y+150);
 await assert.rejects(page.evaluate(pageAction,{op:'pointer'}),/not over a button/);
 await page.route('https://shop.example.net/**',r=>r.fulfill({contentType:'text/html',body:`<header><form action="/find"><input type="search" name="term" placeholder="Search the store"></form></header>`}));
 await page.goto('https://shop.example.net/');
 await page.evaluate(pageAction,{op:'site_search',query:'phantom blade'});
 await page.waitForURL('**/find?term=phantom+blade');
 console.log('PASS: click what the mouse points at (and refuse plain text), on-page site search');
 await page.setContent(`<div style="height:3000px"><a href="https://example.com/a">Alpha</a> <button id=b onclick="this.dataset.clicked='yes'">Beta</button> <input id=f placeholder="Name"><a href="#"><span>Nested</span></a></div>`);
 const shown=await page.evaluate(pageAction,{op:'hints'});
 assert.equal(shown.count,4);
 assert.equal(await page.evaluate(()=>!!document.getElementById('__blok_hints')),true);
 const second=await page.evaluate(pageAction,{op:'hint',n:2});
 assert.equal(second.name,'Beta');
 assert.equal((await page.evaluate(pageAction,{op:'hint',n:1})).href,'https://example.com/a');
 assert.equal((await page.evaluate(pageAction,{op:'hint',n:3})).editable,true);
 await page.evaluate(pageAction,{op:'click',control:second.control,page:second.page});
 assert.equal(await page.locator('#b').getAttribute('data-clicked'),'yes');
 await assert.rejects(page.evaluate(pageAction,{op:'hint',n:9}),/no number 9/);
 await page.locator('#b').evaluate(e=>e.textContent='Changed');
 await assert.rejects(page.evaluate(pageAction,{op:'hint',n:2}),/changed/);
 await page.evaluate(pageAction,{op:'scroll',direction:'down'});
 await page.waitForFunction(()=>scrollY>100);
 assert.equal(await page.evaluate(()=>!!document.getElementById('__blok_hints')),false);
 await page.evaluate(pageAction,{op:'hints',show:false});
 await assert.rejects(page.evaluate(pageAction,{op:'hint',n:1}),/Say "show numbers"/);
 console.log('PASS: numbered hints (labels, lookup, stale refusal, clear on scroll) and scrolling');
 await page.setContent(`<nav>Home About Pricing Login</nav><main><article><h1>Solar panels</h1><p>Solar panels turn sunlight into electricity using photovoltaic cells made of silicon.</p><p>A typical home system costs ₹2,40,000 and pays for itself in about six years.</p></article><aside>Related links</aside></main><footer>Copyright</footer>`);
 const read=await page.evaluate(pageAction,{op:'read_page'});
 assert.match(read.text,/photovoltaic/); assert.doesNotMatch(read.text,/Login|Copyright|Related links/);
 await page.evaluate(()=>{const r=document.createRange();r.selectNodeContents(document.querySelector('p'));getSelection().addRange(r);});
 assert.match((await page.evaluate(pageAction,{op:'read_page'})).selection,/^Solar panels turn sunlight/);
 await page.setContent(`<button style="background:#d22" onclick="this.dataset.c='red'">Download</button><button style="background:#2563eb;color:white" onclick="this.dataset.c='blue'">Download</button>`);
 await assert.rejects(page.evaluate(pageAction,{op:'click',target:'Download'}),/More than one/);
 await page.evaluate(pageAction,{op:'click',target:'Download',color:'blue'});
 assert.equal(await page.locator('button').nth(1).getAttribute('data-c'),'blue');
 assert.equal(await page.locator('button').nth(0).getAttribute('data-c'),null);
 console.log('PASS: page text without menus, selected text, and "click the blue Download button"');
 const form=`<form onsubmit="event.preventDefault();document.body.dataset.sent=document.querySelector('#amt').value+'/'+document.querySelector('#note').value">
   <label>Amount <input id=amt></label><label>Note <input id=note></label><label>PIN <input type=password id=pin></label>
   <button type=button onclick="document.body.dataset.category='travel'">Travel</button><button>Submit</button></form>`;
 await page.route('https://expenses.example.org/**',r=>r.fulfill({contentType:'text/html',body:form}));
 await page.goto('https://expenses.example.org/new');
 await page.evaluate(()=>{window.__sent=[];window.chrome={runtime:{sendMessage:m=>{window.__sent.push(m);return Promise.resolve({watching:true});},onMessage:{addListener(){}}}};});
 await page.evaluate(await readFile(new URL('../browser-extension/recorder.js',import.meta.url),'utf8'));
 await page.waitForTimeout(50);
 await page.fill('#amt','450'); await page.locator('#amt').dispatchEvent('change');
 await page.click('text=Travel');
 await page.fill('#pin','1234'); await page.locator('#pin').dispatchEvent('change');
 await page.fill('#note','lunch'); await page.press('#note','Enter');
 const recorded=(await page.evaluate(()=>window.__sent)).filter(m=>m.type==='blok-step').map(m=>m.step);
 assert.deepEqual(recorded.map(s=>[s.op,s.name,s.value]),[['fill','Amount','450'],['click','Travel',undefined],['secret','PIN',undefined],
   ['fill','Note','lunch'],['enter','Note',undefined]]);
 assert.ok(!JSON.stringify(recorded).includes('1234'));
 await page.goto('https://expenses.example.org/new');
 for(const step of [{op:'fill',name:'Amount',role:'textbox',value:'999'},{op:'click',name:'Travel',role:'button'},{op:'enter',name:'Note',role:'textbox'}]){
   const found=await page.evaluate(pageAction,{op:'find_control',name:step.name,role:step.role});
   assert.ok(found,step.name);
   const op=step.op==='fill'?'fill':step.op==='enter'?'submit':'click';
   await page.evaluate(pageAction,{op,control:found.control,page:found.page,text:step.value});
 }
 assert.equal(await page.evaluate(()=>document.body.dataset.category),'travel');
 assert.equal(await page.evaluate(()=>document.body.dataset.sent),'999/');
 assert.equal(await page.evaluate(pageAction,{op:'find_control',name:'Delete',role:'button'}),false);
 console.log('PASS: watch me records names and values (never passwords), and replay finds the same controls again');
 await page.setContent(`<header><a href="#p" onclick="document.body.dataset.went='header'">Pricing</a> <a href="#d">Docs</a></header>
   <main style="height:1500px"><button onclick="document.body.dataset.went='button'">See pricing details</button></main>
   <footer><a href="#p2" onclick="document.body.dataset.went='footer'">Pricing</a></footer>`);
 await page.evaluate(pageAction,{op:'click',target:'pricing',navigate:true});
 assert.equal(await page.evaluate(()=>document.body.dataset.went),'header');
 await assert.rejects(page.evaluate(pageAction,{op:'click',target:'pricing'}),/More than one/);   // plain "click" stays strict
 console.log('PASS: "go to pricing" picks the topmost matching link');
}finally{await browser.close();}
