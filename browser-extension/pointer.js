// Remembers only where the mouse last was on this page, so "click that button"
// can find what the user is pointing at. Nothing leaves the page.
addEventListener('pointermove', event => {
  globalThis.__blokPointer = {x: event.clientX, y: event.clientY, t: Date.now()};
}, {capture: true, passive: true});
