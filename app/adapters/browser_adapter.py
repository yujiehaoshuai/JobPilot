"""将平台 DOM 转换为统一岗位；过滤、匹配和跟踪不接触选择器。"""

import re
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup
from app.adapters.base import JobSourceAdapter
from app.browser.selectors import SiteSpec
from app.exceptions import JobParseError, SelectorChangedError
from app.models.job import JobPosting


class PageReader(Protocol):
    """浏览器与公开 HTTP 共用的读取契约；业务解析不关心传输方式。"""

    def validate_url(self, url: str) -> None: ...
    def read(self, url: str, expected_selector: str) -> str: ...


class ReadonlyBrowserAdapter(JobSourceAdapter):
    """有上限地读取当前搜索页，不自动翻页，也不触发沟通按钮。"""

    def __init__(self, session: PageReader, site: SiteSpec, limit: int = 10) -> None:
        if not 1 <= limit <= 50:
            raise ValueError("单次搜索上限必须在 1 到 50 之间")
        self.session, self.site, self.limit = session, site, limit

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
        return ids[:self.limit]

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
        for query in (queries or [""])[:5]:
            url = self.site.home + self.site.search_path.format(query=quote(query))
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
