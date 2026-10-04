"""牛客实习岗位读取；平台字段解析全部留在此 Adapter。"""

import re
from bs4 import BeautifulSoup
from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.browser.selectors import NOWCODER, NOWCODER_EXTRA
from app.enums import EmploymentType


class NowcoderAdapter(ReadonlyBrowserAdapter):
    """复用可信导航和详情校验，牛客只提供自己的路径与字段。"""

    def __init__(self, session, limit=10):
        super().__init__(session, NOWCODER, limit)

    def detail_url(self, source_job_id):
        if not re.fullmatch(r"[0-9]+", source_job_id):
            raise ValueError("牛客岗位编号必须为数字")
        return f"{self.site.home}/jobs/detail/{source_job_id}"

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
        return job
