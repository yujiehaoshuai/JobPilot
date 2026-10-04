"""独立 stdio MCP 服务器，只暴露岗位搜索和详情两个只读工具。"""

import argparse
import asyncio
from typing import Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from app.models.base import DomainModel
from app.models.job import JobPosting
from app.adapters.factory import open_adapter
from app.tools.jobs import JobTools
from app.exceptions import BrowserPausedError, JobPilotError


class ToolReply(DomainModel):
    """通过结构化状态传递人工验证，客户端不会把暂停当成空结果。"""
    status: Literal["ok", "paused", "error"]
    jobs: list[JobPosting] = Field(default_factory=list)
    message: str | None = None


def create_server(source: str):
    server = FastMCP("JobPilot read-only jobs", log_level="ERROR")
    def call(name, arguments):
        try:
            with open_adapter(source) as adapter:
                return ToolReply(status="ok", jobs=JobTools(adapter).call(name, arguments))
        except BrowserPausedError as exc:
            return ToolReply(status="paused", message=str(exc))
        except JobPilotError:
            return ToolReply(status="error", message="岗位读取失败，请检查页面或来源配置")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    async def search_jobs(queries: list[str], limit: int = 10) -> ToolReply:
        """按关键词只读搜索平台岗位，最多返回 50 条。"""
        return await asyncio.to_thread(call, "search_jobs", {"queries": queries, "limit": limit})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    async def get_job_detail(source_job_id: str) -> ToolReply:
        """根据平台岗位编号读取完整 JD，不执行任何申请或沟通。"""
        return await asyncio.to_thread(call, "get_job_detail", {"source_job_id": source_job_id})
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["mock", "boss", "nowcoder"], default="mock")
    args = parser.parse_args()
    # stdout 专用于 MCP 协议，不能在这里 print 普通日志。
    create_server(args.source).run(transport="stdio")


if __name__ == "__main__":
    main()
