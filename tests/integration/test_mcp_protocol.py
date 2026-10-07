"""真实 MCP 子进程握手与工具调用；没有以函数替身冒充协议测试。"""

import pytest
from pydantic import ValidationError
from app.mcp_client import MCPJobAdapter
from app.tools.jobs import JobTools
from app.adapters.mock.adapter import MockJobAdapter
from app.config import load_settings


def test_stdio_search_and_detail_match_direct():
    direct = JobTools(MockJobAdapter(load_settings().jobs_path))
    client = MCPJobAdapter("mock")
    expected = direct.call("search_jobs", {"queries": ["Python"], "limit": 50})
    actual = client.search_jobs(["Python"])
    assert [job.id for job in actual] == [job.id for job in expected]
    detail = client.get_job_detail(actual[0].source_job_id)
    assert detail.description == actual[0].description
    assert len(client.events) == 2 and all(event["success"] for event in client.events)


def test_tool_boundary_rejects_writes_and_invalid_arguments():
    client = MCPJobAdapter()
    with pytest.raises(ValueError):
        client.call("send_message", {"content": "不能发送"})
    with pytest.raises(ValidationError):
        client.call("search_jobs", {"queries": [], "limit": 5000})


def test_mcp_and_direct_preserve_requested_limit():
    """真实 MCP 握手仍执行同一数量约束，不只在页面上截断结果。"""
    client = MCPJobAdapter("mock", search_limit=2)
    expected = MockJobAdapter(load_settings().jobs_path).search_jobs(["Python"])[:2]
    assert [job.id for job in client.search_jobs(["Python"])] == [job.id for job in expected]
    assert client.events[-1]["arguments"]["limit"] == 2
