"""将平台 DOM 转换为统一岗位；过滤、匹配和跟踪不接触选择器。"""

import re
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup
from app.adapters.base import JobSourceAdapter
from app.adapters.cities import normalize_cities, city_query
from app.browser.selectors import SiteSpec
from app.exceptions import JobParseError, SelectorChangedError
from app.models.job import JobPosting


class PageReader(Protocol):
    """浏览器与公开 HTTP 共用的读取契约；业务解析不关心传输方式。"""

    def validate_url(self, url: str) -> None: ...
    def read(self, url: str, expected_selector: str) -> str: ...


class ReadonlyBrowserAdapter(JobSourceAdapter):
    """平台共用的只读解析与有限分页，不触发沟通或投递按钮。"""

    def __init__(self, session: PageReader, site: SiteSpec, limit: int = 10, cities=None, known_jobs=None, attempted_ids=None) -> None:
        if not 1 <= limit <= 1000:
            raise ValueError("单次搜索上限必须在 1 到 1000 之间")
        self.session, self.site, self.limit = session, site, limit
        self.cities = normalize_cities(cities)
        self.known_jobs = {job.source_job_id: job for job in known_jobs or []}
        self.known_attempted = list(dict.fromkeys([*(attempted_ids or []), *self.known_jobs]))
        self.read_warnings = []
        self.search_coverage = {}

    def search_pages(self, queries, next_selector, max_pages=20):
        """按城市分配读取额度，避免第一座城市占满其他城市的机会。"""
        queries = list(dict.fromkeys(queries or [""]))[:5]
        cities = self.cities or [""]
        ids, warnings, pages = list(self.known_attempted), [], 0
        limit_reached = False
        for city_index, city in enumerate(cities):
            remaining = self.limit - len(ids)
            if remaining <= 0:
                limit_reached = True
                break
            # 空城市的未用额度自动留给后面的城市，总详情数不超过本轮上限。
            quota = (remaining + len(cities) - city_index - 1) // (len(cities) - city_index)
            found, notes, count, limited = self.collect_city_links(
                queries, city, next_selector, quota, set(ids), max_pages, 100 - pages)
            ids.extend(found)
            warnings.extend(notes)
            pages += count
            limit_reached = limit_reached or limited
            if pages >= 100:
                warnings.append("本轮已读取 100 个搜索页，其他页面尚未覆盖。")
                break
        self.read_warnings = warnings
        self.search_coverage = {"pages": pages, "queries": queries, "cities": self.cities,
            "complete": not warnings, "limit_reached": limit_reached, "attempted_ids": ids,
            "detail_limit": self.limit, "scope": "本轮城市和关键词的公开搜索页"}
        from app.exceptions import UnreadableJobError, UnavailableJobError
        jobs, unreadable = [], 0
        for job_id in ids:
            if job_id in self.known_attempted and job_id not in self.known_jobs:
                continue
            try:
                jobs.append(self.known_jobs[job_id] if job_id in self.known_jobs else self.get_job_detail(job_id))
            except UnavailableJobError:
                self.read_warnings.append(f"岗位 {job_id} 已删除或下线，已跳过。")
            except UnreadableJobError:
                unreadable += 1
                self.read_warnings.append(f"岗位 {job_id} 的详情文字无法可靠解释，已跳过，请人工查看原页。")
        if unreadable and not jobs:
            raise UnreadableJobError("找到了岗位链接，但本轮详情全部不可读，未生成任何匹配结论")
        return jobs

    def collect_city_links(self, queries, city, next_selector, quota, previous, max_pages, page_budget):
        """同一城市交替搜索关键词；下一页必须继续携带原城市条件。"""
        ended, seen, ids, warnings, pages = set(), {query: set() for query in queries}, [], [], 0
        label = f"{city}：" if city else ""
        for page in range(1, max_pages + 1):
            for query in queries:
                if query in ended:
                    continue
                html = self.read_search_page(query, page, city)
                pages += 1
                found = self.parse_links(html)
                signature = tuple(found)
                if not found:
                    ended.add(query)
                elif signature in seen[query]:
                    warnings.append(f"{label}关键词“{query}”返回重复页，已停止翻页。")
                    ended.add(query)
                else:
                    seen[query].add(signature)
                    ids.extend(job_id for job_id in found if job_id not in ids and job_id not in previous)
                    button = BeautifulSoup(html, "html.parser").select_one(next_selector)
                    has_next = button is not None and not button.has_attr("disabled") and button.get("aria-disabled") != "true" and "disabled" not in button.get("class", [])
                    if not has_next:
                        ended.add(query)
                    if len(ids) >= quota:
                        limited = len(ids) > quota or has_next or len(ended) < len(queries)
                        if limited:
                            warnings.append(f"{label}达到本轮 {quota} 条读取上限，可继续扩大搜索。")
                        return ids[:quota], warnings, pages, limited
                if pages >= page_budget:
                    return ids[:quota], warnings + ["搜索页读取次数达到上限。"], pages, False
            if len(ended) == len(queries):
                return ids, warnings, pages, False
        return ids, warnings + [f"{label}达到每个关键词 {max_pages} 页上限。"], pages, False

    def read_search_page(self, query, page, city=""):
        """公开 HTML 直接使用页码；动态页面可在平台 Adapter 中使用只读翻页。"""
        url = self.site.home + self.site.search_path.format(query=quote(query, safe="")) + city_query(self.site.source, city)
        if page > 1:
            url += f"&page={page}"
        return self.session.read(url, f"{self.site.links}, {self.site.empty}")

    def parse_links(self, html: str) -> list[str]:
        """丢弃站外链接，保留平台岗位编号；无有效链接时要求检查页面。"""
        soup = BeautifulSoup(html, "html.parser")
        ids = []
        for link in soup.select(self.site.links):
            url = urljoin(self.site.home, str(link.get("href", "")))
            try:
                self.session.validate_url(url)
            except JobParseError:
                continue
            match = re.fullmatch(self.site.detail_pattern, urlsplit(url).path)
            if match and match[1] not in ids:
                ids.append(match[1])
        if not ids and not soup.select_one(self.site.empty):
            raise SelectorChangedError("搜索页缺少岗位链接和空结果标志，请检查登录状态或选择器")
        return ids

    def detail_url(self, source_job_id: str) -> str:
        """由平台子类给出详情地址，避免接受任意 URL。"""
        raise NotImplementedError

    def parse_detail(self, html: str, source_job_id: str) -> JobPosting:
        """必要字段缺失则失败；城市和薪资未知时保留空值。"""
        soup = BeautifulSoup(html, "html.parser")
        def value(selector: str) -> str:
            elements = soup.select(selector)
            return "\n".join(element.get_text(" ", strip=True) for element in elements)
        title, company, description = [value(s) for s in (
            self.site.title, self.site.company, self.site.description)]
        if not all((title, company, description)):
            raise SelectorChangedError("岗位标题、公司或 JD 缺失，请检查详情页面选择器")
        return JobPosting(id=f"{self.site.source}:{source_job_id}", source=self.site.source,
                          source_job_id=source_job_id, title=title, company=company,
                          description=description, city=value(self.site.city) or None,
                          salary=value(self.site.salary) or None, url=self.detail_url(source_job_id))

    def search_jobs(self, queries: list[str] | None = None) -> list[JobPosting]:
        """按关键词读取详情；最多五个查询，总岗位数受 limit 限制。"""
        ids = []
        for query, city in [(query, city) for city in self.cities or [""] for query in (queries or [""])[:5]]:
            url = self.site.home + self.site.search_path.format(query=quote(query)) + city_query(self.site.source, city)
            html = self.session.read(url, f"{self.site.links}, {self.site.empty}")
            for job_id in self.parse_links(html):
                if job_id not in ids:
                    ids.append(job_id)
            if len(ids) >= self.limit:
                break
        return [self.get_job_detail(job_id) for job_id in ids[:self.limit]]

    def get_job_detail(self, source_job_id: str) -> JobPosting:
        html = self.session.read(self.detail_url(source_job_id), self.site.description)
        return self.parse_detail(html, source_job_id)
