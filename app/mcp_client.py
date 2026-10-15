"""MCP 客户端通过官方 SDK 握手和调用工具，不伪装成本地函数分派。"""

import asyncio
import os
import sys
from time import perf_counter
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import PROJECT_ROOT
from app.adapters.base import JobSourceAdapter
from app.mcp_server import ToolReply
from app.tools.jobs import SCHEMAS
from app.exceptions import BrowserPausedError, JobParseError


class MCPJobAdapter(JobSourceAdapter):
    """每次只读调用启动受控子进程；浏览器登录资料仍持久保存在磁盘。"""

    def __init__(self, source="mock", search_limit: int | None = None, cities=None):
        if source not in {"mock", "boss", "nowcoder", "shixiseng"}:
            raise ValueError("未注册的 MCP 岗位来源")
        self.source, self.events = source, []
        self.cities = cities or []
        self.read_warnings: list[str] = []
        default_limit = 5 if source == "shixiseng" else 50
        self.search_limit = SCHEMAS["search_jobs"].model_validate(
            {"limit": default_limit if search_limit is None else search_limit}).limit

    async def request(self, name, arguments):
        """只运行项目自己的服务器，不接收外部启动命令。"""
        environment = {key: value for key, value in os.environ.items() if key.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
            "BROWSER_CHANNEL", "BROWSER_HEADLESS", "MOCK_JOBS_PATH"}}
        environment["PYTHONIOENCODING"] = "utf-8"
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "app.mcp_server", "--source", self.source], cwd=str(PROJECT_ROOT), env=environment)
        async with asyncio.timeout(900):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if result.isError or result.structuredContent is None:
                        raise JobParseError("MCP 工具未返回有效结构化结果")
                    return ToolReply.model_validate(result.structuredContent)

    def call(self, name, arguments):
        start, success = perf_counter(), False
        try:
            if name not in SCHEMAS:
                raise ValueError("未开放的工具名称")
            arguments = SCHEMAS[name].model_validate(arguments).model_dump()
            reply = asyncio.run(self.request(name, arguments))
            if reply.status == "paused":
                raise BrowserPausedError(reply.message or "平台要求人工验证")
            if reply.status != "ok":
                raise JobParseError(reply.message or "MCP 工具调用失败")
            self.read_warnings = reply.warnings
            self.search_coverage = reply.coverage
            success = True
            return reply.jobs
        finally:
            self.events.append({"tool": name, "arguments": arguments, "success": success,
                                "latency_ms": (perf_counter() - start) * 1000})

    def search_jobs(self, queries=None):
        return self.call("search_jobs", {"queries": queries or [], "limit": self.search_limit, "cities": self.cities})

    def get_job_detail(self, source_job_id):
        return self.call("get_job_detail", {"source_job_id": source_job_id})[0]
