let busy = false;
let cachedConfig;

async function config() {
  if (!cachedConfig) {
    const response = await fetch(chrome.runtime.getURL('bridge-config.json'), {cache: 'no-store'});
    if (!response.ok) throw new Error('Mở ứng dụng trước, rồi tải lại extension.');
    cachedConfig = await response.json();
  }
  return cachedConfig;
}

function extractRegions(regions) {
  const ratio = window.devicePixelRatio || 1;
  const sideInset = Math.min(16, Math.max(0, (window.outerWidth - window.innerWidth) / 2));
  const chromeHeight = Math.max(0, window.outerHeight - window.innerHeight);
  const bottomInset = chromeHeight > 24 ? Math.min(8, chromeHeight / 5) : 0;
  const originX = (window.screenX + sideInset) * ratio;
  const originY = (window.screenY + chromeHeight - bottomInset) * ratio;
  const results = [];
  for (const region of regions) {
  const selection = {
    left: (region[0] - originX) / ratio,
    top: (region[1] - originY) / ratio,
    right: (region[2] - originX) / ratio,
    bottom: (region[3] - originY) / ratio
  };
  const width = region[2] - region[0];
  const height = region[3] - region[1];
  const overlapWidth = Math.max(0, Math.min(selection.right, innerWidth) - Math.max(selection.left, 0));
  const overlapHeight = Math.max(0, Math.min(selection.bottom, innerHeight) - Math.max(selection.top, 0));
  const overlap = overlapWidth * overlapHeight /
      Math.max(1, (selection.right - selection.left) * (selection.bottom - selection.top));
  if (overlap < 0.85) return {boxes: [], sections: [], overlap};

  const boxes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode()) && boxes.length < 250) {
    const parent = node.parentElement;
    if (!parent || parent.closest('script,style,noscript,template,[aria-hidden="true"]')) continue;
    const style = getComputedStyle(parent);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    const code = Boolean(parent.closest('pre')) || style.whiteSpace.startsWith('pre');
    const raw = node.textContent;
    const chunks = code && raw.includes('\n')
      ? [...raw.matchAll(/[^\r\n]*(?:\r?\n|$)/g)]
      : [{0: raw, index: 0}];
    for (const chunk of chunks) {
      const source = chunk[0].replace(/\r?\n$/, '');
      const text = code ? source.replace(/\t/g, '    ').replace(/\s+$/, '')
                        : source.replace(/\s+/g, ' ').trim();
      if (!text.trim() || text.length > 2000) continue;
      const range = document.createRange();
      range.setStart(node, chunk.index);
      range.setEnd(node, chunk.index + source.length);
      const rects = [...range.getClientRects()].filter(rect =>
        rect.width > 1 && rect.height > 1 && rect.right > selection.left &&
        rect.left < selection.right && rect.bottom > selection.top && rect.top < selection.bottom);
      if (!rects.length) continue;
      const left = Math.max(0, (Math.min(...rects.map(r => r.left)) - selection.left) * ratio);
      const top = Math.max(0, (Math.min(...rects.map(r => r.top)) - selection.top) * ratio);
      const right = Math.min(width, (Math.max(...rects.map(r => r.right)) - selection.left) * ratio);
      const bottom = Math.min(height, (Math.max(...rects.map(r => r.bottom)) - selection.top) * ratio);
      if (right <= left || bottom <= top) continue;
      boxes.push({text, code, left, top, right, bottom});
    }
  }
  boxes.sort((a, b) => a.top - b.top || a.left - b.left);
  results.push(boxes);
  }
  const sections = results.map(boxes => boxes.map(box => box.text));
  return {boxes: regions.length === 1 ? results[0] : [], sections, overlap: 1};
}

async function poll(tabId) {
  if (busy) return;
  busy = true;
  try {
    const {port, token} = await config();
    const base = `http://127.0.0.1:${port}`;
    const headers = {'X-Web-MCQ-Token': token};
    const stateResponse = await fetch(`${base}/state`, {headers, cache: 'no-store'});
    if (!stateResponse.ok) return;
    const state = await stateResponse.json();
    if (!state.regions?.length) return;
    const tab = await chrome.tabs.get(tabId);
    const lastWindow = await chrome.windows.getLastFocused();
    if (!tab.active || tab.windowId !== lastWindow.id || !/^https?:\/\//.test(tab.url || '')) return;
    const injected = await chrome.scripting.executeScript({
      target: {tabId}, func: extractRegions, args: [state.regions]
    });
    const result = injected?.[0]?.result;
    if (!result || result.sections.length !== state.regions.length ||
        result.sections.some(section => !section.length) ||
        (state.regions.length === 1 && result.boxes.length < 5)) return;
    await fetch(`${base}/snapshot`, {
      method: 'POST', headers: {...headers, 'Content-Type': 'application/json'},
      body: JSON.stringify({generation: state.generation, regions: state.regions,
                            boxes: result.boxes, sections: result.sections,
                            tab_url: tab.url})
    });
  } catch (_) {
    // App closed, permission not granted, or unsupported page: OCR remains active.
  } finally {
    busy = false;
  }
}

async function clearSnapshot() {
  try {
    const {port, token} = await config();
    await fetch(`http://127.0.0.1:${port}/clear`, {
      method: 'POST', headers: {'X-Web-MCQ-Token': token}
    });
  } catch (_) { /* App closed. */ }
}

chrome.tabs.onActivated.addListener(clearSnapshot);
chrome.tabs.onUpdated.addListener((_, change) => {
  if (change.url || change.status === 'loading') clearSnapshot();
});
chrome.windows.onFocusChanged.addListener(clearSnapshot);

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === 'webmcq-heartbeat' && sender.tab?.id) poll(sender.tab.id);
  if (message?.type === 'webmcq-poll-now' && message.tabId) poll(message.tabId);
  if (message?.type === 'webmcq-hidden') clearSnapshot();
});
