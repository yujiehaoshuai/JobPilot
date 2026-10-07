"""实习僧公开页面适配：列表取编号，详情取正文，拒绝猜测特殊字体内容。"""

import re
import unicodedata
from urllib.parse import quote
from bs4 import BeautifulSoup

from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.browser.selectors import SHIXISENG, SHIXISENG_DAYS, SHIXISENG_MONTHS, SHIXISENG_NEXT
from app.enums import EmploymentType
from app.exceptions import JobParseError, SelectorChangedError, UnreadableJobError


def readable(text: str) -> bool:
    """私用区字符通常需要网站字体才能解释，不能当作真实文字交给模型。"""
    return not any(unicodedata.category(char) == "Co" or char == "\ufffd" for char in text)


class ShixisengAdapter(ReadonlyBrowserAdapter):
    """默认走公开 HTTP；读取失败会明确停止，不切换指纹或尝试绕过限制。"""

    def __init__(self, session, limit=5):
        super().__init__(session, SHIXISENG, limit)
        self.read_warnings: list[str] = []

    def parse_links(self, html: str) -> list[str]:
        """只有可见的空列表占位图才表示零岗位，隐藏模板不能证明搜索成功。"""
        ids = super().parse_links(html)
        if ids:
            return ids
        soup = BeautifulSoup(html, "html.parser")
        for image in soup.select(self.site.empty):
            hidden = any(
                parent.has_attr("hidden") or parent.get("aria-hidden") == "true"
                or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                             str(parent.get("style", "")), re.I)
                for parent in [image, *image.parents]
            )
            if not hidden:
                return []
        raise SelectorChangedError("实习僧没有岗位链接或可见空结果，请检查页面是否加载完整")

    def search_jobs(self, queries: list[str] | None = None):
        """每个关键词最多读两页；达到数量上限或无下一页就停止。"""
        self.read_warnings = []
        ids = []
        for query in (queries or [""])[:5]:
            for page in range(1, 3):
                url = self.site.home + self.site.search_path.format(query=quote(query, safe=""))
                if page > 1:
                    url += f"&page={page}"
                html = self.session.read(url, f"{self.site.links}, {self.site.empty}")
                found = self.parse_links(html)
                new_ids = [job_id for job_id in found if job_id not in ids]
                # 服务端可能忽略页码或反复返回同一页；不继续空转或重复读详情。
                if not new_ids:
                    break
                ids.extend(new_ids)
                next_button = BeautifulSoup(html, "html.parser").select_one(SHIXISENG_NEXT)
                if len(ids) >= self.limit or next_button is None or next_button.has_attr("disabled"):
                    break
            if len(ids) >= self.limit:
                break
        jobs = []
        for job_id in ids[:self.limit]:
            try:
                jobs.append(self.get_job_detail(job_id))
            except UnreadableJobError:
                self.read_warnings.append(f"岗位 {job_id} 的详情文字无法可靠解释，已跳过，请人工查看原页。")
        if ids and not jobs:
            raise UnreadableJobError("找到了岗位链接，但本轮详情全部不可读，未生成任何匹配结论")
        return jobs

    def detail_url(self, source_job_id: str) -> str:
        if not re.fullmatch(r"inn_[A-Za-z0-9]+", source_job_id):
            raise JobParseError("实习僧岗位编号格式不正确")
        return f"{self.site.home}/intern/{source_job_id}"

    def parse_detail(self, html: str, source_job_id: str):
        """只认页面明确给出的到岗要求；刷新时间不冒充发布时间。"""
        job = super().parse_detail(html, source_job_id)
        if not all(readable(value) for value in (job.title, job.company, job.description)):
            raise UnreadableJobError("实习僧详情含无法可靠解释的文字，已停止解析，请人工查看原页")
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
