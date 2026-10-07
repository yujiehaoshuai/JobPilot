// 点击扩展图标只打开本地面板，不自动访问、采集或操作招聘网站。
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL("panel.html") });
});
