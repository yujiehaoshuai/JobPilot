"""牛客实习岗位读取；平台字段解析全部留在此 Adapter。"""

import re
from bs4 import BeautifulSoup
from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.browser.selectors import NOWCODER, NOWCODER_EXTRA, NOWCODER_NEXT, NOWCODER_STATUS, NOWCODER_ACTIVE_PAGE
from app.enums import EmploymentType


class NowcoderAdapter(ReadonlyBrowserAdapter):
    """复用可信导航和详情校验，牛客只提供自己的路径与字段。"""

    def __init__(self, session, limit=10, cities=None, known_jobs=None, attempted_ids=None):
        super().__init__(session, NOWCODER, limit, cities, known_jobs, attempted_ids)
        self.current_query, self.current_page = None, 0

    def detail_url(self, source_job_id):
        if not re.fullmatch(r"[0-9]+", source_job_id):
            raise ValueError("牛客岗位编号必须为数字")
        return f"{self.site.home}/jobs/detail/{source_job_id}"

    def search_jobs(self, queries=None):
        self.current_query, self.current_page = None, 0
        return self.search_pages(queries, NOWCODER_NEXT)

    def read_search_page(self, query, page, city=""):
        """牛客重载带 page 的 URL 可能回到首屏，使用网站自己的只读下一页。"""
        if not hasattr(self.session, "read_next"):
            return super().read_search_page(query, page, city)  # 本地固定 HTML 测试读取器。
        if (query, city) != self.current_query or page <= self.current_page:
            html = super().read_search_page(query, 1, city)
            self.current_query, self.current_page = (query, city), 1
        else:
            html = self.session.page.content()
        while self.current_page < page:
            html = self.session.read_next(NOWCODER_NEXT, NOWCODER_ACTIVE_PAGE, self.current_page + 1)
            self.current_page += 1
        return html

    def parse_detail(self, html, source_job_id):
        job = super().parse_detail(html, source_job_id)
        extra = BeautifulSoup(html, "html.parser").select_one(NOWCODER_EXTRA)
        text = extra.get_text(" ", strip=True) if extra else ""
        days = re.search(r"([1-7])\s*天[/／]周", text)
        months = re.search(r"(?:最少)?\s*([1-9][0-9]?)\s*个月", text)
        if days:
            job.required_days_per_week = int(days[1])
        if months:
            job.internship_duration_months = int(months[1])
        if days and months:
            job.employment_type = EmploymentType.INTERN
        status = BeautifulSoup(html, "html.parser").select(NOWCODER_STATUS)
        for item in status:
            text = item.get_text(" ", strip=True)
            if text in {"已结束", "职位已下线", "已停止招聘", "招聘已结束", "职位已关闭"}:
                job.closed_reason = text
        return job
