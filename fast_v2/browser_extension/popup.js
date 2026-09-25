const site = document.getElementById('site');
const status = document.getElementById('status');
const button = document.getElementById('enable');
let tab;
let pattern;

async function refresh() {
  [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  if (!tab?.url || !/^https?:\/\//.test(tab.url)) {
    site.textContent = 'Hãy mở trang bài tập HTTP/HTTPS.';
    button.disabled = true;
    return;
  }
  const url = new URL(tab.url);
  pattern = `${url.protocol}//${url.hostname}/*`;
  site.textContent = `Trang: ${url.hostname}`;
  const allowed = await chrome.permissions.contains({origins: [pattern]});
  button.textContent = allowed ? 'Đã cho phép — kết nối lại' : 'Cho phép đọc trang này';
  try {
    const config = await (await fetch(chrome.runtime.getURL('bridge-config.json'),
      {cache: 'no-store'})).json();
    const response = await fetch(`http://127.0.0.1:${config.port}/state`,
      {headers: {'X-Web-MCQ-Token': config.token}, cache: 'no-store'});
    status.textContent = response.ok ? 'Ứng dụng đã kết nối trên máy này.' : 'Ứng dụng chưa kết nối.';
  } catch (_) {
    status.textContent = 'Mở ứng dụng trước, rồi tải lại extension.';
  }
}

button.addEventListener('click', async () => {
  try {
    if (!(await chrome.permissions.request({origins: [pattern]}))) return;
    const id = 'webmcq-' + [...pattern].reduce((hash, char) =>
      ((hash * 31 + char.charCodeAt(0)) >>> 0), 0).toString(16);
    const existing = await chrome.scripting.getRegisteredContentScripts({ids: [id]});
    if (!existing.length) {
      await chrome.scripting.registerContentScripts([{id, matches: [pattern],
        js: ['heartbeat.js'], runAt: 'document_idle'}]);
    }
    await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['heartbeat.js']});
    chrome.runtime.sendMessage({type: 'webmcq-poll-now', tabId: tab.id});
    status.textContent = 'Đã bật. Vẽ vùng trên trang rồi dùng phím giải.';
    button.textContent = 'Đã cho phép — kết nối lại';
  } catch (error) {
    status.textContent = `Chưa bật được: ${error.message}`;
  }
});

refresh().catch(error => { status.textContent = error.message; });
