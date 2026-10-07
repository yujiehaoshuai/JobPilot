/** 诊断只允许公开首页、搜索页和岗位详情页；聊天、设置等页面不能采集。 */
export function readableUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || url.port) return false;
    if (url.hostname === "example.com") return url.pathname === "/";
    if (!["www.zhipin.com", "zhipin.com"].includes(url.hostname)) return false;
    return url.pathname === "/" || /^\/web\/geek\/job\/?$/.test(url.pathname)
      || /^\/job_detail\/[A-Za-z0-9_-]+\.html$/.test(url.pathname)
      // 城市首页只读取页面概要；登录及账号页面明确排除。
      || /^\/(beijing|shanghai|guangzhou|shenzhen|hangzhou|tianjin|chengdu|wuhan|nanjing|suzhou)\/$/.test(url.pathname);
  } catch { return false; }
}

/** 报告去掉查询参数和片段，导航时需要的原始链接仅保留在面板内存中。 */
export function safeUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "about:") return `about:${url.pathname}`;
    if (!["http:", "https:"].includes(url.protocol)) return `${url.protocol}<hidden>`;
    return `${url.origin}${url.pathname}`;
  } catch { return "<unknown>"; }
}

/** 搜索词由 URL 编码处理，禁止把用户输入拼成脚本或任意站点地址。 */
export function searchUrl(query, site) {
  const keyword = query.trim();
  if (!keyword || keyword.length > 80) throw new Error("关键词需要 1 到 80 个字符");
  return new URL(site.search_path.replace("{query}", encodeURIComponent(keyword)), site.home).href;
}

/** 页面返回的数据需要再次校验；缺少标题、公司或 JD 时不能伪装成完整岗位。 */
export function jobFromDetail(detail, fetchedAt) {
  if (!detail || !readableUrl(detail.url)) return null;
  const match = new URL(detail.url).pathname.match(/^\/job_detail\/([A-Za-z0-9_-]+)\.html$/);
  if (!match || !detail.title?.trim() || !detail.company?.trim() || !detail.description?.trim()) return null;
  return {id: `boss:${match[1]}`, source: "boss", source_job_id: match[1],
    title: detail.title, company: detail.company, description: detail.description,
    city: detail.city || null, salary: detail.salary || null, url: safeUrl(detail.url), fetched_at: fetchedAt};
}
