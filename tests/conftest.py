"""提供离线测试共用的候选人和岗位样例，减少重复准备数据的代码。"""

from collections.abc import Callable
from typing import Any

import pytest

from app.enums import EmploymentType
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting


@pytest.fixture
def candidate() -> CandidateProfile:
    """提供明确的求职方向、排除条件和到岗时间，用于验证筛选规则。"""
    return CandidateProfile(
        id="candidate-test",
        name="Example Candidate",
        target_roles=["Agent Engineer", "LLM Application Engineer"],
        target_cities=["杭州", "上海", "Remote"],
        excluded_roles=["前端", "测试", "销售"],
        excluded_keywords=["数据标注"],
        preferred_keywords=["RAG", "大模型"],
        employment_type=EmploymentType.INTERN,
        internship_duration_months=4,
        available_days_per_week=4,
    )


@pytest.fixture
def make_job() -> Callable[..., JobPosting]:
    """返回岗位生成函数；测试只需传入要改变的字段，其余字段使用有效默认值。"""
    def factory(**changes: Any) -> JobPosting:
        """先准备完整岗位，再覆盖当前测试需要调整的字段。"""
        values = {
            "id": "mock-job-1",
            "source": "mock",
            "source_job_id": "job-1",
            "title": "Agent Engineer Intern",
            "company": "Example AI",
            "city": "杭州",
            "description": "Use Python to build RAG and Agent applications.",
            "url": "https://jobs.example.test/jobs/1",
            "employment_type": EmploymentType.INTERN,
            "internship_duration_months": 3,
            "required_days_per_week": 3,
        }
        values.update(changes)
        return JobPosting(**values)

    return factory
