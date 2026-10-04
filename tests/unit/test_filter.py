"""验证规则筛选遵守候选人明确填写的条件，并说明每项拒绝原因。"""

import pytest

from app.enums import EmploymentType
from app.models.candidate import CandidateProfile
from app.services.filter_service import RuleFilter


def test_relevant_available_internship_passes(candidate, make_job) -> None:
    """方向匹配且到岗时间满足要求的实习岗位应通过筛选。"""
    result = RuleFilter().evaluate(candidate, make_job())

    assert result.passed is True
    assert result.reasons == []


@pytest.mark.parametrize(
    "changes",
    [
        {"city": "北京"},
        {"title": "Agent 前端实习生"},
        {"description": "参与数据标注和 Agent 应用开发"},
        {"title": "RAG 数据标注实习生"},
        {"title": "办公室行政助理"},
        {"description": " \n\t "},
        {"employment_type": EmploymentType.FULL_TIME},
        {"internship_duration_months": 6},
        {"required_days_per_week": 5},
    ],
    ids=["city", "excluded-role", "jd-keyword", "title-keyword", "unrelated-title", "empty-jd", "full-time", "duration", "days"],
)
def test_explicit_constraint_violation_is_explained(candidate, make_job, changes) -> None:
    """逐项覆盖城市、排除项、岗位方向和时间要求，拒绝时必须给出原因。"""
    result = RuleFilter().evaluate(candidate, make_job(**changes))

    assert result.passed is False
    assert result.reasons
    assert all(reason.strip() for reason in result.reasons)


def test_all_applicable_rejection_reasons_are_reported(candidate, make_job) -> None:
    """岗位同时违反多项条件时，应一次列出全部适用的拒绝原因。"""
    result = RuleFilter().evaluate(
        candidate,
        make_job(city="北京", description="", required_days_per_week=7),
    )

    assert result.passed is False
    assert len(result.reasons) >= 3


def test_role_exclusions_do_not_reject_collaboration_in_jd(candidate, make_job) -> None:
    """描述中提到与被排除岗位协作，不等于当前岗位本身需要被排除。"""
    job = make_job(description="Develop Agent services and collaborate with 前端 and 测试 colleagues.")

    assert RuleFilter().evaluate(candidate, job).passed


@pytest.mark.parametrize("city", ["Hangzhou", "杭州", "Remote", "远程", "远程办公"])
def test_documented_city_aliases_match(candidate, make_job, city: str) -> None:
    """覆盖城市中英文名称及远程办公别名，验证约定写法能匹配偏好。"""
    assert RuleFilter().evaluate(candidate, make_job(city=city)).passed


def test_title_matching_is_case_insensitive_and_accepts_preferred_keywords(candidate, make_job) -> None:
    """标题匹配不区分大小写，候选人的偏好关键词也能表明岗位相关。"""
    job = make_job(title="rag platform intern")

    assert RuleFilter().evaluate(candidate, job).passed


def test_relevant_jd_cannot_override_an_unrelated_title(candidate, make_job) -> None:
    """标题明显不相关时，描述中的相关业务词不能让岗位绕过方向筛选。"""
    job = make_job(title="Office Assistant", description="The company builds Agent Engineer and RAG products.")

    assert not RuleFilter().evaluate(candidate, job).passed


def test_missing_optional_metadata_is_not_assumed_incompatible(candidate, make_job) -> None:
    """岗位未提供可选信息时，不应自行假定条件不满足并拒绝。"""
    job = make_job(
        city=None,
        employment_type=EmploymentType.ANY,
        internship_duration_months=None,
        required_days_per_week=None,
    )

    assert RuleFilter().evaluate(candidate, job).passed


def test_equal_availability_satisfies_requirement(candidate, make_job) -> None:
    """候选人的可实习月数和每周天数恰好达到要求时，应通过筛选。"""
    job = make_job(internship_duration_months=4, required_days_per_week=4)

    assert RuleFilter().evaluate(candidate, job).passed


def test_unrestricted_candidate_does_not_get_invented_preferences(make_job) -> None:
    """候选人未填写限制时，不应擅自添加岗位方向、城市或用工类型偏好。"""
    candidate = CandidateProfile(id="unrestricted", name="Example")
    job = make_job(title="Frontend Developer", city="北京", employment_type=EmploymentType.FULL_TIME)

    assert RuleFilter().evaluate(candidate, job).passed
