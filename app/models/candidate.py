"""定义候选人资料，只保存本人明确提供的事实和求职条件。"""

from pydantic import Field

from app.enums import EmploymentType, SkillLevel
from app.models.base import DomainModel, NonEmptyStr


class CandidateSkill(DomainModel):
    """保存候选人自述的技能、熟练程度和相关经历。

    evidence 用于说明技能依据，例如项目实践，不由程序推测生成。
    """

    skill: NonEmptyStr
    level: SkillLevel
    evidence: NonEmptyStr


class CandidateProfile(DomainModel):
    """保存个人经历和明确的求职条件，供后续规则筛选使用。

    列表默认各自独立，修改一名候选人的资料不会影响其他候选人。
    可用时长或天数未填写时保留为 None，表示尚不明确。
    """

    id: NonEmptyStr
    name: NonEmptyStr
    education: list[NonEmptyStr] = Field(default_factory=list)
    skills: list[CandidateSkill] = Field(default_factory=list)
    projects: list[NonEmptyStr] = Field(default_factory=list)
    experience: list[NonEmptyStr] = Field(default_factory=list)
    # 目标岗位和偏好关键词用于匹配岗位标题；目标城市用于限制工作地点。
    target_roles: list[NonEmptyStr] = Field(default_factory=list)
    target_cities: list[NonEmptyStr] = Field(default_factory=list)
    excluded_roles: list[NonEmptyStr] = Field(default_factory=list)
    excluded_keywords: list[NonEmptyStr] = Field(default_factory=list)
    # 以下是候选人实际可提供的时间，用来与实习岗位要求比较。
    internship_duration_months: int | None = Field(default=None, ge=1, le=120, strict=True)
    available_days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)
    preferred_keywords: list[NonEmptyStr] = Field(default_factory=list)
    employment_type: EmploymentType = EmploymentType.ANY
