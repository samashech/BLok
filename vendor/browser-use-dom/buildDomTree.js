/**
 * Vendored and adapted from browser-use (https://github.com/browser-use/browser-use)
 * browser_use/dom/serializer/clickable_elements.py & buildDomTree.js
 *
 * Implements interactive element discovery, open Shadow DOM traversal,
 * visibility filtering, and media playback state detection for browser automation.
 */

export const INTERACTIVE_TAGS = new Set([
  'button',
  'input',
  'select',
  'textarea',
  'a',
  'details',
  'summary',
  'option',
  'optgroup'
]);

export const INTERACTIVE_ROLES = new Set([
  'button',
  'link',
  'menuitem',
  'option',
  'radio',
  'checkbox',
  'tab',
  'textbox',
  'combobox',
  'slider',
  'spinbutton',
  'search',
  'searchbox',
  'row',
  'cell',
  'gridcell'
]);

export const SEARCH_INDICATORS = [
  'search',
  'magnify',
  'glass',
  'lookup',
  'find',
  'query',
  'search-icon',
  'search-btn',
  'search-button',
  'searchbox'
];

/**
 * Check if element is visible and interactive according to computed style and geometry.
 */
export function isElementVisible(element) {
  if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;

  const style = window.getComputedStyle(element);
  if (
    style.visibility === 'hidden' ||
    style.display === 'none' ||
    style.opacity === '0' ||
    style.pointerEvents === 'none'
  ) {
    return false;
  }
  return true;
}

/**
 * Check if element is interactive using browser-use heuristics.
 */
export function isElementInteractive(element) {
  if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

  const tagName = element.tagName.toLowerCase();
  if (tagName === 'html' || tagName === 'body') return false;

  // 1. Tag check
  if (INTERACTIVE_TAGS.has(tagName)) {
    if (tagName === 'a' && !element.hasAttribute('href')) return false;
    return true;
  }

  // 2. Form control descendant check (for labels / spans wrapping inputs)
  if (tagName === 'label' || tagName === 'span') {
    if (element.querySelector('input, select, textarea')) return true;
  }

  // 3. Search indicator heuristics
  const className = String(element.className || '').toLowerCase();
  const id = String(element.id || '').toLowerCase();
  if (SEARCH_INDICATORS.some(ind => className.includes(ind) || id.includes(ind))) {
    return true;
  }

  // 4. Role check
  const role = element.getAttribute('role');
  if (role && INTERACTIVE_ROLES.has(role.toLowerCase())) return true;

  // 5. Interactive attributes
  if (
    element.hasAttribute('onclick') ||
    element.hasAttribute('tabindex') ||
    element.hasAttribute('contenteditable') ||
    element.getAttribute('contenteditable') === 'true'
  ) {
    return true;
  }

  // 6. Pointer cursor fallback
  try {
    const style = window.getComputedStyle(element);
    if (style.cursor === 'pointer') return true;
  } catch (e) {
    // Ignore style read errors
  }

  return false;
}

/**
 * Collect all visible interactive elements including those inside open Shadow DOMs.
 */
export function buildInteractiveDomTree(root = document) {
  const elements = [];

  function traverse(node) {
    if (!node) return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_ELEMENT);
    let current;
    while ((current = walker.nextNode())) {
      if (isElementInteractive(current) && isElementVisible(current)) {
        elements.push(current);
      }
      if (current.shadowRoot) {
        traverse(current.shadowRoot);
      }
    }
  }

  traverse(root);
  return elements;
}

/**
 * Check active HTMLMediaElement playback state.
 */
export function isMediaElementPlaying(element) {
  if (!element) return false;
  return !element.paused && !element.ended && element.currentTime > 0 && element.readyState >= 2;
}
