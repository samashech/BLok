// "Watch me": while BLoK is watching this tab, report what the user does as named
// steps (the control's label and role, never screen coordinates). Typed values are
// recorded so a skill can replay them; password fields are never read.
let watching = false;
const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
const labelOf = e => norm(e.getAttribute('aria-label') || (e.labels && [...e.labels].map(l => l.innerText).join(' ')) ||
  e.getAttribute('placeholder') || e.getAttribute('title') || (e.matches('input[type="submit"],input[type="button"]') ? e.value : '') ||
  e.innerText || e.getAttribute('name') || '').slice(0, 120);
const editable = e => e.matches?.('input:not([type="button"],[type="submit"],[type="reset"],[type="checkbox"],[type="radio"]),textarea,[contenteditable="true"]');
const roleOf = e => e.getAttribute('role') || (e.matches('a[href]') ? 'link' : e.matches('button,input[type="button"],input[type="submit"]') ? 'button' :
  e.matches('select') ? 'combobox' : editable(e) ? 'textbox' : e.tagName.toLowerCase());
const control = e => e?.closest?.('a[href],button,input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="menuitem"],[role="option"],[contenteditable="true"]');
const send = step => chrome.runtime.sendMessage({type: 'blok-step', step: {...step, url: location.href}}).catch(() => {});
const lastValue = new Map();   // field label → value already recorded, so change-after-Enter isn't logged twice
let lastEnter = 0;

chrome.runtime.sendMessage({type: 'blok-watching?'}).then(reply => { watching = !!reply?.watching; }).catch(() => {});
chrome.runtime.onMessage.addListener(message => { if (message?.type === 'blok-watch') watching = !!message.on; });

addEventListener('click', event => {
  const e = control(event.target);
  if (!watching || !e || editable(e) || !event.isTrusted) return;
  // Enter in a form makes the browser "click" its submit button; that's the same step.
  if (Date.now() - lastEnter < 300 && e.matches('button:not([type]),button[type="submit"],input[type="submit"]')) return;
  const name = labelOf(e);
  if (name) send({op: 'click', name, role: roleOf(e)});
}, true);
const typed = e => {
  if (e.matches('input[type="password"]')) return send({op: 'secret', name: labelOf(e)});
  const name = labelOf(e), value = String(e.isContentEditable ? e.innerText : e.value).slice(0, 2000);
  if (lastValue.get(name) === value) return;
  lastValue.set(name, value);
  send({op: 'fill', name, role: roleOf(e), value});
};
addEventListener('change', event => { const e = event.target; if (watching && event.isTrusted && editable(e)) typed(e); }, true);
addEventListener('keydown', event => {
  const e = event.target;
  if (!watching || !event.isTrusted || event.key !== 'Enter' || event.isComposing || !editable(e) || e.matches('textarea')) return;
  typed(e);
  lastEnter = Date.now();
  send({op: 'enter', name: labelOf(e), role: roleOf(e)});
}, true);
