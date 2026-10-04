"""验证数据模型能在筛选和入库前拦住无效数据，并保留有效信息。"""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.enums import ApplicationStatus, SkillLevel
from app.models.application import Application
from app.models.candidate import CandidateProfile, CandidateSkill
from app.models.job import JobPosting


def test_candidate_defaults_do_not_share_mutable_lists() -> None:
    """修改一个候选人的列表，不应影响另一个候选人的默认值。"""
    first = CandidateProfile(id="first", name="First")
    second = CandidateProfile(id="second", name="Second")

    first.target_roles.append("Agent Engineer")

    assert second.target_roles == []
    assert second.skills == []


def test_skill_keeps_candidate_supplied_evidence() -> None:
    """去除技能和证据两端的空格，同时保留候选人填写的内容与等级。"""
    skill = CandidateSkill(
        skill=" FastAPI ",
        level=SkillLevel.PROJECT_EXPERIENCE,
        evidence=" Used in my course project ",
    )

    assert skill.skill == "FastAPI"
    assert skill.evidence == "Used in my course project"
    assert skill.level == SkillLevel.PROJECT_EXPERIENCE


@pytest.mark.parametrize("field", ["id", "name"])
def test_candidate_rejects_blank_identity_fields(field: str) -> None:
    """逐项检查候选人标识和姓名，只有空白字符也应视为无效。"""
    values = {"id": "candidate-1", "name": "Candidate", field: " \t "}

    with pytest.raises(ValidationError):
        CandidateProfile(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [("available_days_per_week", 0), ("available_days_per_week", 8),
     ("internship_duration_months", 0), ("internship_duration_months", -1)],
)
def test_candidate_rejects_impossible_availability(field: str, value: int) -> None:
    """覆盖天数和月数的越界值，避免无法满足现实含义的到岗安排。"""
    with pytest.raises(ValidationError):
        CandidateProfile(id="candidate-1", name="Candidate", **{field: value})


@pytest.mark.parametrize("field", ["id", "source", "source_job_id", "title", "company"])
def test_job_rejects_missing_identity_and_display_fields(make_job, field: str) -> None:
    """逐项验证岗位的标识、来源、名称和公司都不能留空。"""
    with pytest.raises(ValidationError):
        make_job(**{field: " \n "})


@pytest.mark.parametrize("url", ["", "not-a-url", "file:///tmp/private", "ftp://jobs.test/1", "javascript:alert(1)"])
def test_job_rejects_non_web_urls(make_job, url: str) -> None:
    """覆盖空地址、格式错误和非网页协议，确保岗位链接是有效网页地址。"""
    with pytest.raises(ValidationError):
        make_job(url=url)


@pytest.mark.parametrize(
    ("field", "value"),
    [("required_days_per_week", 0), ("required_days_per_week", 8),
     ("internship_duration_months", 0)],
)
def test_job_rejects_impossible_availability(make_job, field: str, value: int) -> None:
    """岗位要求也要检查天数和月数范围，不能只校验候选人的时间。"""
    with pytest.raises(ValidationError):
        make_job(**{field: value})


def test_empty_description_is_a_filter_decision(make_job) -> None:
    """空岗位描述可进入模型，是否排除由后续筛选规则决定。"""
    job = make_job(description=" \n ")

    assert job.description == ""


def test_job_json_round_trip_preserves_unicode_and_utc_time(make_job) -> None:
    """岗位转为 JSON 再读回后，中文内容和 UTC 时间应保持完整。"""
    job = make_job(title="大模型应用开发实习生", company="示例科技")
    restored = JobPosting.model_validate_json(job.model_dump_json())

    assert restored == job
    assert job.fetched_at.utcoffset() == timedelta(0)


def test_new_applications_have_distinct_ids_and_aware_timestamps() -> None:
    """新申请应有独立标识、初始状态和带时区的创建、更新时间。"""
    first = Application(candidate_id="candidate-1", job_id="job-1")
    second = Application(candidate_id="candidate-1", job_id="job-2")

    assert UUID(str(first.id))
    assert first.id != second.id
    assert first.status == ApplicationStatus.NEW
    assert first.created_at.utcoffset() == timedelta(0)
    assert first.updated_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("field", ["candidate_id", "job_id"])
def test_application_requires_nonblank_links(field: str) -> None:
    """申请必须关联候选人和岗位，两种关联标识都不能为空。"""
    values = {"candidate_id": "candidate-1", "job_id": "job-1", field: " "}

    with pytest.raises(ValidationError):
        Application(**values)
