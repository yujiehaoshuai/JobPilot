// 点击扩展图标只打开本地面板，不自动访问、采集或操作招聘网站。
async function openHelper(fragment="") {
  const url=chrome.runtime.getURL("helper.html");
  const tabs=await chrome.tabs.query({});
  const existing=tabs.find(tab=>tab.url?.split("#")[0]===url);
  if(existing) {
    await chrome.tabs.update(existing.id,{active:true,...(fragment?{url:url+"#"+fragment}:{})});
    if(fragment)await chrome.tabs.reload(existing.id);
  } else await chrome.tabs.create({url:url+(fragment?"#"+fragment:"")});
}
chrome.action.onClicked.addListener(() => {void openHelper();});

// 只处理本机首页发出的连接，不能把任意网页传来的地址当作后台网络请求。
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  let source;
  try { source = new URL(sender.url); } catch { return; }
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || source.protocol !== "http:"
      || source.hostname !== "127.0.0.1" || source.pathname !== "/" || source.username || source.password
      || message.type !== "connect" || !/^[A-Za-z0-9_-]{40,60}$/.test(message.connection)) return;
  const fragment = new URLSearchParams({server:source.origin, connection:message.connection});
  openHelper(fragment.toString())
    .then(() => reply({opened:true}), () => reply({opened:false}));
  return true;
});
