"""岗位工具白名单，禁止通过此入口执行任意 URL、脚本或发送操作。"""

from time import perf_counter
from pydantic import Field
from app.models.base import DomainModel
from app.adapters.base import JobSourceAdapter


class SearchArguments(DomainModel):
    """确定查询词与数量上限，防止一次工具请求无限抓取。"""
    queries: list[str] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=10, ge=1, le=50, strict=True)


class DetailArguments(DomainModel):
    """详情工具只接收平台岗位编号，不接受任意链接。"""
    source_job_id: str = Field(min_length=1, max_length=200)


SCHEMAS = {"search_jobs": SearchArguments, "get_job_detail": DetailArguments}


class JobTools:
    """普通 Tool Calling：校验名称与 Pydantic 参数后调用 Python 方法。"""

    def __init__(self, adapter):
        self.adapter, self.events = adapter, []

    def call(self, name: str, arguments: dict):
        start, success = perf_counter(), False
        try:
            if name not in SCHEMAS:
                raise ValueError("未开放的工具名称")
            values = SCHEMAS[name].model_validate(arguments)
            if name == "search_jobs":
                jobs = self.adapter.search_jobs(values.queries)[:values.limit]
            else:
                jobs = [self.adapter.get_job_detail(values.source_job_id)]
            success = True
            return jobs
        finally:
            self.events.append({"tool": name, "arguments": arguments, "success": success,
                                "latency_ms": (perf_counter() - start) * 1000})


class ToolCallingAdapter(JobSourceAdapter):
    """给同一个图提供普通工具调用路径，方便与 MCP 路径比较。"""

    def __init__(self, adapter, search_limit: int | None = None):
        self.tools = JobTools(adapter)
        self.search_limit = SearchArguments(limit=50 if search_limit is None else search_limit).limit
        self.read_warnings: list[str] = []

    def search_jobs(self, queries=None):
        jobs = self.tools.call("search_jobs", {"queries": queries or [], "limit": self.search_limit})
        self.read_warnings = list(getattr(self.tools.adapter, "read_warnings", []))
        return jobs

    def get_job_detail(self, source_job_id):
        return self.tools.call("get_job_detail", {"source_job_id": source_job_id})[0]
