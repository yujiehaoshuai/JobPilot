/**
 * 此函数会被浏览器序列化后放入 ISOLATED 环境，不能依赖模块外的变量。
 * 只读取可见 DOM；不访问 Cookie、Web Storage、聊天、隐藏接口或页面的 JS 变量。
 */
export function collectPage(config) {
  const locationUrl = new URL(location.href);
  const cleanUrl = locationUrl.origin + locationUrl.pathname;
  const visible = element => {
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  };
  const text = selector => [...document.querySelectorAll(selector)]
    .filter(visible).map(element => element.innerText?.trim() || "").filter(Boolean).join("\n").slice(0, 30000);
  const result = {url: cleanUrl, title: "", ready_state: document.readyState,
    body_length: 0, blocked: false, listings: [], detail: null, empty: false, next_state: "unknown"};
  // 在函数执行时再校验地址，避免读取前后恰好发生页面跳转。
  const boss = config.site.hosts.includes(locationUrl.hostname);
  const allowedPath = locationUrl.pathname === "/" || /^\/web\/geek\/jobs?\/?$/.test(locationUrl.pathname)
    || /^\/(beijing|shanghai|guangzhou|shenzhen|hangzhou|tianjin|chengdu|wuhan|nanjing|suzhou)\/$/.test(locationUrl.pathname)
    || /^\/job_detail\/[A-Za-z0-9_-]+\.html$/.test(locationUrl.pathname);
  if (locationUrl.protocol !== "https:" || locationUrl.port || locationUrl.username || locationUrl.password
      || !(boss && allowedPath || locationUrl.hostname === "example.com" && locationUrl.pathname === "/")) {
    result.blocked = true;
    result.reason = "unsupported_page";
    return result;
  }
  result.title = document.title.slice(0, 200);
  result.blocked = config.challenge_titles.some(word => document.title.includes(word))
    || config.challenge_selectors.some(selector => [...document.querySelectorAll(selector)].some(visible));
  if (result.blocked) {
    result.reason = "manual_verification_required";
    return result;
  }
  // 只记录正文长度，用于判断空白；不导出整个页面或登录用户的信息。
  result.body_length = document.body?.innerText.length || 0;
  if (!boss) return result;
  result.empty = [...document.querySelectorAll(config.site.empty)].some(visible);
  const next = [...document.querySelectorAll(config.next_selector)].find(visible);
  if (next) result.next_state = next.disabled || next.getAttribute("aria-disabled") === "true"
    || [...next.classList].some(name => name.includes("disabled")) ? "end" : "available";
  const seen = new Set();
  for (const element of document.querySelectorAll(config.site.links)) {
    if (!visible(element)) continue;
    try {
      const url = new URL(element.href, location.href);
      if (url.protocol !== "https:" || !config.site.hosts.includes(url.hostname)
          || url.username || url.password || url.port || !/^\/job_detail\/[A-Za-z0-9_-]+\.html$/.test(url.pathname)) continue;
      const clean = url.origin + url.pathname;
      if (seen.has(clean)) continue;
      seen.add(clean);
      result.listings.push({url: clean, link_text: (element.innerText || "").trim().slice(0, 300),
        navigation_url: url.href});
      if (result.listings.length >= 50) break;
    } catch { /* 非法链接跳过，不访问它。 */ }
  }
  if (/^\/job_detail\/[A-Za-z0-9_-]+\.html$/.test(locationUrl.pathname)) {
    result.detail = {url: cleanUrl, title: text(config.site.title), company: text(config.site.company),
      description: text(config.site.description), city: text(config.site.city), salary: text(config.site.salary),
      extra: text(config.extra_selector), closed_reason: text(config.status_selector)};
  }
  return result;
}

/** 只能点击公开搜索页的下一页；不接受后端发来的选择器或任意页面脚本。 */
export function nextSearchPage(config) {
  if (location.protocol !== "https:" || !config.site.hosts.includes(location.hostname)
      || !/^\/web\/geek\/jobs?\/?$/.test(location.pathname)) return false;
  const next = [...document.querySelectorAll(config.next_selector)].find(element => {
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length;
  });
  if (!next || next.disabled || next.getAttribute("aria-disabled") === "true"
      || [...next.classList].some(name => name.includes("disabled"))) return false;
  next.click();
  return true;
}
