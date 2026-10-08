/* 只在本机 JobPilot 页面转交一次连接；绝不把主页面访问凭据发给 BOSS。 */
if (location.pathname === "/" && document.title.startsWith("JobPilot")) {
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== location.origin) return;
    if (event.data?.type === "jobpilot-boss-ping") {
      window.postMessage({type:"jobpilot-boss-installed"}, location.origin);
    } else if (event.data?.type === "jobpilot-boss-connect" && /^[A-Za-z0-9_-]{40,60}$/.test(event.data.connection)) {
      try {
        await chrome.runtime.sendMessage({type:"connect", connection:event.data.connection});
        window.postMessage({type:"jobpilot-boss-opened"}, location.origin);
      } catch {
        window.postMessage({type:"jobpilot-boss-reload"}, location.origin);
      }
    }
  });
}
