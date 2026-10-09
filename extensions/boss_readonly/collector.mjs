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
    body_length: 0, blocked: false, listings: [], detail: null, empty: false, next_state: "unknown",scroll:[]};
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
      if (result.listings.length >= 200) break;
    } catch { /* 非法链接跳过，不访问它。 */ }
  }
  if (result.next_state === "unknown" && result.listings.length) {
    const box = [...document.querySelectorAll(config.scroll_selector)].find(visible);
    if (box) result.next_state = "scroll";
  }
  // 只记录岗位容器及祖先的尺寸，不记录账号文字，用来判断滚动是否发生在正确位置。
  let container=[...document.querySelectorAll(config.scroll_selector)].find(visible);
  for(let depth=0;container && depth<12;depth++,container=container.parentElement) {
    result.scroll.push({element:(container.tagName+"."+[...container.classList].join(".")).slice(0,120),
      top:Math.round(container.scrollTop),height:container.scrollHeight,viewport:container.clientHeight,
      overflow:getComputedStyle(container).overflowY});
  }
  if (/^\/job_detail\/[A-Za-z0-9_-]+\.html$/.test(locationUrl.pathname)) {
    const contacts = [...document.querySelectorAll(config.contact_selector)].filter(visible)
      .filter(e=>["立即沟通","继续沟通","已沟通"].includes((e.innerText||"").trim()));
    result.detail = {url: cleanUrl, title: text(config.site.title), company: text(config.site.company),
      description: text(config.site.description), city: text(config.site.city), salary: text(config.site.salary),
      extra: text(config.extra_selector), closed_reason: text(config.status_selector),
      contact_button: contacts.map(e=>e.innerText.trim()).join("、").slice(0,100),contact_count:Math.min(30,contacts.length)};
  }
  return result;
}

/** 只操作公开搜索页的续页按钮或岗位列表滚动，不接受后端传入任意脚本。 */
export function nextSearchPage(config) {
  if (location.protocol !== "https:" || !config.site.hosts.includes(location.hostname)
      || location.port || !/^\/web\/geek\/jobs?\/?$/.test(location.pathname)) return false;
  const visible=element=>getComputedStyle(element).display!=="none"
    && getComputedStyle(element).visibility!=="hidden" && element.getClientRects().length>0;
  if(config.challenge_titles.some(word=>document.title.includes(word))
      || config.challenge_selectors.some(selector=>[...document.querySelectorAll(selector)].some(visible)))return false;
  const next = [...document.querySelectorAll(config.next_selector)].find(element => {
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length;
  });
  if (!next || next.disabled || next.getAttribute("aria-disabled") === "true"
      || [...next.classList].some(name => name.includes("disabled"))) {
    if(next)return false;
    // 有些 BOSS 版本通过滚动加载。只滚动包含岗位链接的列表及其滚动祖先。
    let box=[...document.querySelectorAll(config.scroll_selector)].find(element=>
      visible(element) && element.querySelector(config.site.links));
    if(!box)return false;
    const list=box;
    while(box && box!==document.body) {
      if(/auto|scroll/.test(getComputedStyle(box).overflowY) && box.scrollHeight>box.clientHeight) {
        box.scrollTo({top:box.scrollHeight,behavior:"instant"});return true;
      }
      box=box.parentElement;
    }
    const links=[...list.querySelectorAll(config.site.links)].filter(visible);
    links.at(-1)?.scrollIntoView({block:"end",behavior:"instant"});
    return links.length>0;
  }
  next.click();
  return true;
}
