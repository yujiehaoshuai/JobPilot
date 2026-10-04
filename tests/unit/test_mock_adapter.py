"""验证模拟适配器能稳定读取离线样例，并在数据有误时提供清楚的错误信息。"""

from pathlib import Path

import pytest

from app.adapters.base import JobSourceAdapter
from app.adapters.mock.adapter import MockJobAdapter
from app.exceptions import JobParseError


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "jobs"


def test_bundled_source_contains_twenty_typed_jobs() -> None:
    """内置样例应读取出 20 个岗位，并具备展示和识别岗位所需的字段。"""
    adapter = MockJobAdapter(FIXTURES)

    jobs = adapter.search_jobs()

    assert isinstance(adapter, JobSourceAdapter)
    assert len(jobs) == 20
    assert all(job.title and job.company and job.source_job_id for job in jobs)


def test_detail_lookup_returns_the_requested_source_job() -> None:
    """按平台岗位编号读取详情时，应返回对应岗位及其描述。"""
    adapter = MockJobAdapter(FIXTURES)
    first = adapter.search_jobs()[0]

    detail = adapter.get_job_detail(first.source_job_id)

    assert detail.source_job_id == first.source_job_id
    assert detail.description == first.description


def test_search_queries_are_case_insensitive_and_limit_matches(tmp_path, make_job) -> None:
    """关键词搜索不区分大小写，并且只返回匹配岗位。"""
    agent_job = make_job(title="Agent Engineer")
    frontend_job = make_job(id="second", source_job_id="job-2", title="Frontend Developer", description="Build web interfaces.")
    (tmp_path / "01-agent.json").write_text(agent_job.model_dump_json(), encoding="utf-8")
    (tmp_path / "02-frontend.json").write_text(frontend_job.model_dump_json(), encoding="utf-8")

    results = MockJobAdapter(tmp_path).search_jobs(["AGENT"])

    assert [job.id for job in results] == [agent_job.id]


@pytest.mark.parametrize("contents", ["{broken json", "{}", "[]", '{"id": "incomplete"}'])
def test_malformed_fixture_reports_filename(tmp_path, contents: str) -> None:
    """覆盖 JSON 语法错误、结构错误和字段缺失，报错应指出样例文件名。"""
    bad_file = tmp_path / "broken-job.json"
    bad_file.write_text(contents, encoding="utf-8")

    with pytest.raises(JobParseError, match="broken-job.json"):
        MockJobAdapter(tmp_path).search_jobs()


def test_missing_fixture_directory_is_reported(tmp_path) -> None:
    """样例目录不存在时应明确报错，避免误认为没有可用岗位。"""
    with pytest.raises(JobParseError):
        MockJobAdapter(tmp_path / "not-present").search_jobs()


def test_unknown_source_id_is_reported() -> None:
    """查找不存在的岗位编号时应抛出解析错误，不能返回其他岗位。"""
    with pytest.raises(JobParseError):
        MockJobAdapter(FIXTURES).get_job_detail("never-seen-id")
