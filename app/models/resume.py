"""页面提交的当前表单；沿用 CandidateProfile，不保存另一份确认状态。"""

from pydantic import Field
from app.enums import SkillLevel, EmploymentType
from app.models.base import DomainModel, NonEmptyStr


class ResumeSkill(DomainModel):
    """技能名称和程度由本人填写，quote 必须逐字来自简历正文。"""

    skill: NonEmptyStr = Field(max_length=80)
    level: SkillLevel
    quote: NonEmptyStr = Field(max_length=10000)


class ResumeProfileRequest(DomainModel):
    """只使用用户填写的内容；没有填写的学历、年限等字段保持未知。"""

    text: NonEmptyStr = Field(max_length=100000)
    name: NonEmptyStr = Field(max_length=100)
    skills: list[ResumeSkill] = Field(min_length=1, max_length=50)
    target_roles: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    target_cities: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    employment_type: EmploymentType = EmploymentType.ANY
    available_days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)
    internship_duration_months: int | None = Field(default=None, ge=1, le=120, strict=True)
