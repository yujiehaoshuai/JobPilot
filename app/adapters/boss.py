"""BOSS 直聘只读入口，平台路径和页面结构留在 Adapter 内。"""

import re
from urllib.parse import urlsplit
from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.adapters.base import JobSourceAdapter
from app.browser.selectors import BOSS
from app.exceptions import BrowserPausedError, JobParseError
from app.models.job import JobPosting


class BossAdapter(ReadonlyBrowserAdapter):
    """搜索和详情读取不含发起沟通等副作用。"""

    def __init__(self, session, limit: int = 10, cities=None, known_jobs=None, attempted_ids=None):
        super().__init__(session, BOSS, limit, cities, known_jobs, attempted_ids)

    def detail_url(self, source_job_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", source_job_id):
            raise ValueError("BOSS 岗位编号格式无效")
        return f"{self.site.home}/job_detail/{source_job_id}.html"


def job_from_extension(detail) -> JobPosting:
    """只信岗位可见文字；来源、身份和链接由 Python 重建，不能导入站外地址。"""
    url = urlsplit(detail.url)
    match = re.fullmatch(BOSS.detail_pattern, url.path)
    if (url.scheme != "https" or url.hostname not in BOSS.hosts or url.port
            or url.username or url.password or url.query or url.fragment or not match):
        raise JobParseError("BOSS 助手只能回传不带查询参数的本站岗位详情地址")
    if not all(value.strip() for value in (detail.title, detail.company, detail.description)):
        raise JobParseError("岗位标题、公司或说明不完整，不能用于匹配")
    text = "\n".join(filter(None, [detail.description.strip(), detail.extra.strip()]))
    days = re.search(r"(?:每周|一周|周到岗)\s*([1-7])\s*天|([1-7])\s*天\s*[/／]\s*周", text)
    months = re.search(r"(?:至少|最少|实习|持续)\s*([1-9]\d?)\s*个?月", text)
    kind = "internship" if "实习" in detail.title + detail.extra else "any"
    closed = detail.closed_reason if detail.closed_reason in {"职位已关闭", "职位已下线", "停止招聘", "招聘已结束"} else None
    return JobPosting(id="boss:" + match[1], source="boss", source_job_id=match[1],
                      title=detail.title.strip(), company=detail.company.strip(), description=text,
                      url=f"{BOSS.home}/job_detail/{match[1]}.html", city=detail.city.strip() or None,
                      salary=detail.salary.strip() or None, employment_type=kind, closed_reason=closed,
                      required_days_per_week=int(next(part for part in days.groups() if part)) if days else None,
                      internship_duration_months=int(months[1]) if months else None)


class BossExtensionAdapter(JobSourceAdapter):
    """接收普通浏览器读到的岗位，后续过滤、评分与其他平台共用。"""

    def __init__(self, bridge, run_id, limit=100, cities=None):
        self.bridge, self.run_id, self.limit = bridge, run_id, limit
        self.cities = cities or []
        self.read_warnings, self.search_coverage = [], {}

    def search_jobs(self, queries=None):
        value = self.bridge.ensure(self.run_id, queries or [], self.limit, self.cities)
        if value["status"] != "ready":
            raise BrowserPausedError("BOSS 搜索交给普通浏览器助手。请保持助手面板打开；遇到登录或验证时手动完成后点击继续。已读取的岗位会保留。")
        self.read_warnings = value["warnings"]
        self.search_coverage = dict(pages=value["pages"], queries=value["queries"], cities=self.cities, complete=value["complete"],
                                    limit_reached=value.get("limit_reached", len(value["attempted"]) >= value["limit"]),
                                    detail_limit=value["limit"], scope="普通浏览器可见的 BOSS 搜索页")
        return [JobPosting.model_validate(job) for job in value["jobs"]]

    def get_job_detail(self, source_job_id):
        value = self.bridge.get(self.run_id)
        for job in (value or {}).get("jobs", []):
            if job["source_job_id"] == source_job_id:
                return JobPosting.model_validate(job)
        raise JobParseError("这个岗位尚未由浏览器助手读取")
