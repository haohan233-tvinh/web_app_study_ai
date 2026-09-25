// The page only wakes the extension; page code never sees the local bridge token.
if (!globalThis.__webMcqHeartbeat) {
  globalThis.__webMcqHeartbeat = true;
  const ping = () => {
    if (document.visibilityState === 'visible') {
      chrome.runtime.sendMessage({type: 'webmcq-heartbeat'}).catch(() => {});
    }
  };
  setInterval(ping, 400);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') ping();
    else chrome.runtime.sendMessage({type: 'webmcq-hidden'}).catch(() => {});
  });
  ping();
}
