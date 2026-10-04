"""BOSS 直聘只读入口，平台路径和页面结构留在 Adapter 内。"""

import re
from app.adapters.browser_adapter import ReadonlyBrowserAdapter
from app.browser.selectors import BOSS


class BossAdapter(ReadonlyBrowserAdapter):
    """搜索和详情读取不含发起沟通等副作用。"""

    def __init__(self, session, limit: int = 10):
        super().__init__(session, BOSS, limit)

    def detail_url(self, source_job_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", source_job_id):
            raise ValueError("BOSS 岗位编号格式无效")
        return f"{self.site.home}/job_detail/{source_job_id}.html"
