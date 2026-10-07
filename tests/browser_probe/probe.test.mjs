/** 模拟浏览器公开 API 的事件顺序，不连接真实网站或 CDP。 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {observeTab} from "../../extensions/boss_readonly/probe.mjs";
import {collectPage} from "../../extensions/boss_readonly/collector.mjs";
import {readableUrl, safeUrl, searchUrl, jobFromDetail} from "../../extensions/boss_readonly/core.mjs";

const config = JSON.parse(readFileSync(new URL("../../extensions/boss_readonly/selectors.json", import.meta.url)));
const boss = "https://www.zhipin.com/web/geek/job?query=Python";
const detailUrl = "https://www.zhipin.com/job_detail/test-job.html";
function eventSource() {
  const listeners = new Set();
  return {addListener: handler => listeners.add(handler), removeListener: handler => listeners.delete(handler),
    emit: (...args) => [...listeners].forEach(handler => handler(...args)), size: () => listeners.size};
}
function environment(snapshot = {}) {
  let clock = 0, closed = false;
  const tab = {id: 9, url: "about:blank", status: "complete", discarded: false};
  const reads = [], navigations = [], tasks = [];
  const api = {tabs: {
    onUpdated: eventSource(), onRemoved: eventSource(), onReplaced: eventSource(),
    get: async id => { assert.equal(id, 9); if (closed) throw new Error("已关闭"); return {...tab}; },
    update: async (id, change) => {
      navigations.push(change);
      tab.url = change.url;
      api.tabs.onUpdated.emit(id, change, {...tab});
      return {...tab};
    },
  }, scripting: {executeScript: async spec => {
    assert.equal(spec.world, "ISOLATED");
    assert.deepEqual(spec.target, {tabId: 9, frameIds: [0]});
    reads.push(clock);
    return [{documentId: "fixture-document", result: {url: safeUrl(tab.url), title: "虚构测试页面",
      ready_state: "complete", body_length: 100, blocked: false, listings: [], detail: null, ...snapshot}}];
  }}};
  return {api, tab, reads, navigations, tasks,
    options: {duration: 4000, now: () => clock, wait: async ms => {
      clock += ms;
      for (const task of tasks) if (!task.done && clock >= task.at) { task.done = true; task.run(); }
    }},
    close: () => { closed = true; api.tabs.onRemoved.emit(9); },
    navigate: url => { tab.url = url; api.tabs.onUpdated.emit(9, {url}, {...tab}); },
  };
}

test("对照和 BOSS 页面使用同一观察入口，只有目标地址不同", async () => {
  for (const destination of [boss, "https://example.com/"]) {
    const env = environment();
    const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: destination});
    assert.equal(report.outcome, "page_observed");
    assert.equal(report.navigation_count, 1);
    assert.deepEqual(env.navigations, [{url: destination}]);
    assert.equal(report.blank_grace.observed_ms, null);
    assert.equal(env.api.tabs.onUpdated.size(), 0);
  }
});

test("导航后同一标签页变空白，再观察两秒且停止 DOM 读取", async () => {
  const env = environment();
  env.tasks.push({at: 1000, run: () => env.navigate("about:blank")});
  const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.equal(report.outcome, "blank");
  assert.equal(report.blank_grace.observed_ms, 2000);
  assert.equal(report.blank_grace.completed, true);
  assert.deepEqual(env.reads, [0]);
  assert.equal(env.navigations.length, 1);
});

test("空白后窗口提前关闭，不能声称两秒观察完成", async () => {
  const env = environment();
  env.tasks.push({at: 500, run: () => env.navigate("about:blank")}, {at: 1000, run: env.close});
  const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.equal(report.outcome, "tab_closed");
  assert.equal(report.blank_grace.completed, false);
});

test("标签页替换单独记录，不跟踪到新标签页继续操作", async () => {
  const env = environment();
  env.tasks.push({at: 500, run: () => env.api.tabs.onReplaced.emit(10, 9)});
  const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.equal(report.outcome, "tab_replaced");
  assert.equal(report.events.find(e => e.kind === "tabs.replaced").replacement_tab_id, 10);
  assert.equal(env.navigations.length, 1);
});

test("验证界面立即暂停，不导出岗位，不自动重试", async () => {
  const env = environment({blocked: true, reason: "manual_verification_required"});
  const {report, privateLinks} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.equal(report.outcome, "manual_verification_required");
  assert.deepEqual(report.jobs, []);
  assert.deepEqual(privateLinks, []);
  assert.equal(env.navigations.length, 1);
});

test("旧文档读取结果不会被认作当前页面成功", async () => {
  const env = environment({url: detailUrl});
  const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.equal(report.outcome, "page_not_ready");
  assert.equal(report.observations.length, 0);
});

test("无关标签页事件不会进入本次报告", async () => {
  const env = environment();
  env.tasks.push({at: 500, run: () => env.api.tabs.onUpdated.emit(100, {url: "https://private.example/"}, {url: "https://private.example/"})});
  const {report} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss});
  assert.ok(!JSON.stringify(report).includes("private.example"));
});

test("导航参数留在内存，JSON 只保留脱敏岗位链接", async () => {
  const navigationUrl = detailUrl + "?securityId=private-token#secret";
  const env = environment({listings: [{url: navigationUrl, link_text: "虚构 Python 岗位", navigation_url: navigationUrl}]});
  const {report, privateLinks} = await observeTab(env.api, 9, config, {...env.options, navigateTo: boss + "&token=private-token"});
  assert.equal(privateLinks[0].navigation_url, navigationUrl);
  assert.equal(report.listings[0].url, detailUrl);
  assert.ok(!JSON.stringify(report).includes("private-token"));
});

test("账号、聊天、外站和危险协议不能作为读取目标", async () => {
  for (const url of ["https://www.zhipin.com/web/geek/chat", "https://www.zhipin.com/login",
    "https://www.zhipin.com/job_detail/id.html/extra", "https://evil.example/", "javascript:alert(1)",
    "http://www.zhipin.com/", "https://user:pass@www.zhipin.com/", "https://www.zhipin.com:444/"]) {
    assert.equal(readableUrl(url), false, url);
    const env = environment();
    await assert.rejects(observeTab(env.api, 9, config, {...env.options, navigateTo: url}));
    assert.equal(env.navigations.length, 0);
  }
});

test("搜索词编码，完整岗位只使用真实读取的字段", () => {
  assert.equal(new URL(searchUrl("Python & SQL", config.site)).searchParams.get("query"), "Python & SQL");
  assert.throws(() => searchUrl("   ", config.site));
  const detail = {url: detailUrl, title: "虚构岗位", company: "虚构公司", description: "Python 开发"};
  const job = jobFromDetail(detail, "2026-10-07T00:00:00.000Z");
  assert.equal(job.source_job_id, "test-job");
  assert.equal(job.salary, null);
  assert.equal(jobFromDetail({...detail, company: ""}, job.fetched_at), null);
});

/** 给读取器提供最小可见 DOM；访问 Cookie/存储会直接失败。 */
function collectFixture({url = detailUrl, challenge = false} = {}) {
  const make = (value, extra = {}) => ({innerText: value, getClientRects: () => [1], ...extra});
  const map = new Map([
    [config.site.title, [make("虚构 Python 岗位")]], [config.site.company, [make("虚构公司")]],
    [config.site.description, [make("需要 Python 与 SQL")]], [config.site.city, [make("北京")]],
    [config.site.salary, []], [config.site.links, [make("虚构岗位", {href: detailUrl + "?token=private-token"}),
      make("重复岗位", {href: detailUrl}), make("外站链接", {href: "https://evil.example/job_detail/id.html"})]],
    [config.challenge_selectors[0], challenge ? [make("", {hidden: true}), make("")] : []],
  ]);
  const document = {title: "虚构详情", readyState: "complete", body: {innerText: "虚构页面"},
    querySelectorAll: selector => map.get(selector) || []};
  Object.defineProperty(document, "cookie", {get() { throw new Error("禁止访问 Cookie"); }});
  return vm.runInNewContext(`(${collectPage.toString()})(config)`, {
    URL, config, document, location: {href: url},
    getComputedStyle: element => ({display: element.hidden ? "none" : "block", visibility: "visible"}),
  });
}

test("读取可见岗位字段、去重详情链接、排除外站链接", () => {
  const page = collectFixture();
  assert.equal(page.detail.title, "虚构 Python 岗位");
  assert.equal(page.detail.salary, "");
  assert.equal(page.listings.length, 1);
  assert.equal(page.listings[0].url, detailUrl);
});

test("第一个隐藏验证码不妨碍发现后面的可见验证框", () => {
  const page = collectFixture({challenge: true});
  assert.equal(page.blocked, true);
  assert.equal(page.detail, null);
  assert.equal(page.listings.length, 0);
});

test("读取期间跳到聊天页时返回暂停，不读取聊天正文或标题", () => {
  const page = collectFixture({url: "https://www.zhipin.com/web/geek/chat"});
  assert.equal(page.reason, "unsupported_page");
  assert.equal(page.title, "");
  assert.equal(page.body_length, 0);
});
