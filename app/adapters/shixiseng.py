"""实习僧公开页面适配：列表取编号，详情取正文，拒绝猜测特殊字体内容。"""

import re
import unicodedata
from bs4 import BeautifulSoup

from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.browser.selectors import SHIXISENG, SHIXISENG_DAYS, SHIXISENG_MONTHS
from app.enums import EmploymentType
from app.exceptions import JobParseError


def readable(text: str) -> bool:
    """私用区字符通常需要网站字体才能解释，不能当作真实文字交给模型。"""
    return not any(unicodedata.category(char) == "Co" or char == "\ufffd" for char in text)


class ShixisengAdapter(ReadonlyBrowserAdapter):
    """默认走公开 HTTP；读取失败会明确停止，不切换指纹或尝试绕过限制。"""

    def __init__(self, session, limit=5):
        super().__init__(session, SHIXISENG, limit)

    def detail_url(self, source_job_id: str) -> str:
        if not re.fullmatch(r"inn_[A-Za-z0-9]+", source_job_id):
            raise JobParseError("实习僧岗位编号格式不正确")
        return f"{self.site.home}/intern/{source_job_id}"

    def parse_detail(self, html: str, source_job_id: str):
        """只认页面明确给出的到岗要求；刷新时间不冒充发布时间。"""
        job = super().parse_detail(html, source_job_id)
        if not all(readable(value) for value in (job.title, job.company, job.description)):
            raise JobParseError("实习僧详情含无法可靠解释的文字，已停止解析，请人工查看原页")
        # 非必要字段遇到特殊字体时保留未知，不能按猜测补齐薪资或城市。
        if job.city and not readable(job.city):
            job.city = None
        if job.salary and not readable(job.salary):
            job.salary = None
        soup = BeautifulSoup(html, "html.parser")
        days = soup.select_one(SHIXISENG_DAYS)
        months = soup.select_one(SHIXISENG_MONTHS)
        day_match = re.fullmatch(r"\s*([1-7])\s*天\s*[/／]\s*周\s*", days.get_text() if days else "")
        month_match = re.fullmatch(r"\s*实习\s*([1-9][0-9]?)\s*个月\s*", months.get_text() if months else "")
        job.required_days_per_week = int(day_match[1]) if day_match else None
        job.internship_duration_months = int(month_match[1]) if month_match else None
        job.employment_type = EmploymentType.INTERN
        return job
