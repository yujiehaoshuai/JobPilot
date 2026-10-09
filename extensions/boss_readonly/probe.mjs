import {collectPage} from "./collector.mjs";
import {readableUrl, safeUrl, jobFromDetail} from "./core.mjs";

/**
 * 只调用普通扩展 API；不连接 debugger/CDP。监听仅限选中的标签页。
 * 使用独立面板保持本次观察存活；关闭面板就结束观察，不继续后台采集。
 */
export async function observeTab(api, tabId, config, options = {}) {
  const now = options.now || (() => Date.now());
  const wait = options.wait || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const started = now(), duration = options.duration ?? 12000;
  if (!Number.isInteger(tabId) || duration < 2000 || duration > 30000) throw new Error("无效的观察参数");
  if (options.navigateTo && !readableUrl(options.navigateTo)) throw new Error("不允许访问这个页面");
  let closed = false, replaced = false, sawPage = false, blankAt = null, lastReadAt = -Infinity;
  let privateLinks = [], latestPage = null;
  const report = {schema_version: 1, transport: "extension-isolated", started_at: new Date(started).toISOString(),
    tab_id: tabId, outcome: "observing", authentication_verified: false, events: [], observations: [],
    jobs: [], listings: [], dropped_events: 0, navigation_count: 0};
  function record(kind, values = {}) {
    const event = {kind, tab_id: tabId, elapsed_ms: now() - started, ...values};
    if (report.events.length < 300) report.events.push(event); else report.dropped_events++;
  }
  function observeUrl(url) {
    if (!url) return;
    if (safeUrl(url) !== "about:blank") sawPage = true;
    else if (sawPage && blankAt === null) { blankAt = now(); record("blank.observed"); }
  }
  const updated = (id, change, tab) => {
    if (id !== tabId) return;
    observeUrl(change.url || tab.url);
    record("tabs.updated", {url: safeUrl(tab.url || change.url), status: change.status || tab.status,
      discarded: Boolean(tab.discarded)});
  };
  const removed = id => { if (id === tabId) { closed = true; record("tabs.removed"); } };
  const replacement = (addedId, removedId) => {
    if (removedId === tabId) { replaced = true; record("tabs.replaced", {replacement_tab_id: addedId}); }
  };
  api.tabs.onUpdated.addListener(updated);
  api.tabs.onRemoved.addListener(removed);
  api.tabs.onReplaced.addListener(replacement);
  try {
    const initial = await api.tabs.get(tabId);
    // 导航前的新标签页 about:blank 属于正常初始状态，不算故障。
    if (safeUrl(initial.url) !== "about:blank") observeUrl(initial.url);
    record("observation.started", {url: safeUrl(initial.url)});
    if (options.navigateTo) {
      report.navigation_count = 1;
      record("navigation.requested", {target_url: safeUrl(options.navigateTo)});
      await api.tabs.update(tabId, {url: options.navigateTo});
    }
    while (true) {
      if (closed || replaced) { report.outcome = closed ? "tab_closed" : "tab_replaced"; break; }
      const tab = await api.tabs.get(tabId);
      observeUrl(tab.url);
      if (blankAt !== null) {
        // blank 后只收集标签页元数据，至少再等待两秒，不重新导航或读取 DOM。
        if (now() - blankAt >= 2000) { report.outcome = "blank"; break; }
      } else if (tab.discarded) { report.outcome = "tab_discarded"; break; }
      else if (!tab.pendingUrl && readableUrl(tab.url) && now() - lastReadAt >= 3000) {
        lastReadAt = now();
        const [injection] = await api.scripting.executeScript({target: {tabId, frameIds: [0]},
          world: "ISOLATED", func: collectPage, args: [config]});
        const page = injection?.result;
        const afterRead = await api.tabs.get(tabId);
        observeUrl(afterRead.url);
        if (blankAt !== null) continue;
        if (!page || safeUrl(page.url) !== safeUrl(afterRead.url)) {
          record("read.stale_document");
        } else {
          latestPage = page;
          record("dom.read", {url: safeUrl(page.url), document_id: injection.documentId,
            listing_count: page.listings.length, body_length: page.body_length});
          report.observations.push({elapsed_ms: now() - started, url: safeUrl(page.url),
            title: page.title, body_length: page.body_length, listing_count: page.listings.length,
            blocked: page.blocked, ready_state: page.ready_state});
          if (page.blocked) { report.outcome = page.reason || "manual_verification_required"; break; }
          privateLinks = page.listings.filter(item => readableUrl(item.navigation_url));
          report.listings = privateLinks.map(({url, link_text}) => ({url: safeUrl(url), link_text}));
          const job = jobFromDetail(page.detail, new Date(now()).toISOString());
          report.jobs = job ? [job] : [];
          if (page.detail && !job) report.detail_warning = "岗位字段不完整，未作为 JobPosting 导出";
          options.onProgress?.(report);
        }
      }
      if (blankAt === null && now() - started >= duration) {
        report.outcome = latestPage && !tab.pendingUrl && ["interactive","complete"].includes(latestPage.ready_state)
          && latestPage.body_length > 0 && safeUrl(tab.url) === safeUrl(latestPage.url)
          ? "page_observed" : "page_not_ready";
        break;
      }
      await wait(500);
    }
  } catch (error) {
    report.outcome = closed ? "tab_closed" : "observation_error";
    // 浏览器异常可能带完整 URL；仅保存异常类型，具体状态由事件说明。
    record("observation.error", {error_type: error.name || "Error"});
  } finally {
    api.tabs.onUpdated.removeListener(updated);
    api.tabs.onRemoved.removeListener(removed);
    api.tabs.onReplaced.removeListener(replacement);
    report.elapsed_ms = now() - started;
    report.blank_grace = {requested_ms: 2000, observed_ms: blankAt === null ? null : now() - blankAt,
      completed: blankAt !== null && now() - blankAt >= 2000};
    record("observation.finished", {outcome: report.outcome});
  }
  // 原始详情链接可能含导航用参数，仅交给同一面板，不写 JSON 报告。
  return {report, privateLinks, page: latestPage};
}
