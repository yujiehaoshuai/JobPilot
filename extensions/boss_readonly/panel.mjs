import {observeTab} from "./probe.mjs";
import {readableUrl, safeUrl, searchUrl} from "./core.mjs";

const config = await (await fetch(chrome.runtime.getURL("selectors.json"))).json();
const element = id => document.getElementById(id);
let lastReport = null, detailLinks = [], busy = false;

function buttons() {
  for (const button of document.querySelectorAll("button")) button.disabled = busy;
  element("export").disabled = busy || !lastReport;
  element("detail").disabled = busy || !detailLinks.length;
}

/** 只列出可读取站点的标签页，不收集用户的其他浏览记录。 */
async function refresh() {
  const tabs = await chrome.tabs.query({url: ["https://www.zhipin.com/*", "https://zhipin.com/*", "https://example.com/*"]});
  element("target").replaceChildren();
  for (const tab of tabs.filter(tab => readableUrl(tab.url))) {
    const option = document.createElement("option");
    option.value = tab.id;
    option.textContent = `tab-${tab.id} · ${tab.title || safeUrl(tab.url)}`;
    element("target").append(option);
  }
}

/** 每次动作都有结果；不因超时、验证或空白自动重新访问网站。 */
async function run(destination = null) {
  if (busy) return;
  busy = true;
  lastReport = null;
  detailLinks = [];
  element("result").textContent = "观察中，等待本次结果…";
  buttons();
  element("status").textContent = "观察中，请保持面板打开；可切到网页查看。";
  try {
    let tabId;
    if (destination) {
      if (!readableUrl(destination)) throw new Error("目标不属于允许的只读页面");
      const tab = await chrome.tabs.create({url: "about:blank", active: true});
      tabId = tab.id;
    } else {
      if (!element("target").value) throw new Error("请先打开 BOSS 岗位页面，再刷新列表");
      tabId = Number(element("target").value);
    }
    const {report, privateLinks} = await observeTab(chrome, tabId, config, {
      navigateTo: destination, onProgress: report => {
        element("status").textContent = `tab-${tabId}：已读到 ${report.listings.length} 个岗位链接，继续观察…`;
      },
    });
    lastReport = report;
    detailLinks = report.outcome === "page_observed" ? privateLinks : [];
    element("result").textContent = JSON.stringify(report, null, 2);
    element("status").textContent = report.outcome === "page_observed"
      ? `观察完成：${report.listings.length} 个岗位链接，${report.jobs.length} 个完整岗位。这不等于已验证整个采集流程。`
      : `本次暂停：${report.outcome}。请查看记录；需要登录或验证时，由你在网页中处理。`;
    await refresh();
  } catch (error) {
    // 不显示浏览器提供的完整异常，它可能包含带参数的 URL。
    element("status").textContent = "未能完成本次操作。请检查页面是否打开、扩展是否有站点权限，然后手动重试。";
  } finally { busy = false; buttons(); }
}

element("control").addEventListener("click", () => run("https://example.com/"));
element("home").addEventListener("click", () => run(config.site.home));
element("search").addEventListener("click", () => {
  try { run(searchUrl(element("query").value, config.site)); }
  catch (error) { element("status").textContent = error.message; }
});
element("detail").addEventListener("click", () => {
  if (detailLinks.length) run(detailLinks[0].navigation_url);
});
element("read").addEventListener("click", () => run());
element("refresh").addEventListener("click", () => refresh().catch(() => {
  element("status").textContent = "无法刷新标签页列表，请检查扩展权限。";
}));
element("export").addEventListener("click", () => {
  if (!lastReport) return;
  const blob = new Blob([JSON.stringify(lastReport, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `jobpilot-extension-${Date.now()}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
});
await refresh();
element("status").textContent = "准备就绪。建议先运行普通网页对照，再测试 BOSS。";
buttons();
