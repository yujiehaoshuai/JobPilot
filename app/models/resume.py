"""简历导入的中间数据；用户确认后才生成现有 CandidateProfile。"""

from typing import Literal
from pydantic import Field
from app.enums import SkillLevel
from app.models.base import DomainModel, NonEmptyStr


class ResumeSkill(DomainModel):
    """技能名称和程度由本人填写，quote 必须逐字来自简历正文。"""

    skill: NonEmptyStr = Field(max_length=80)
    level: SkillLevel
    quote: NonEmptyStr = Field(max_length=10000)


class ResumeProfileRequest(DomainModel):
    """只接收已确认的信息；没有填写的学历、年限等字段保持未知。"""

    text: NonEmptyStr = Field(max_length=100000)
    name: NonEmptyStr = Field(max_length=100)
    skills: list[ResumeSkill] = Field(min_length=1, max_length=50)
    target_roles: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    target_cities: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    confirmed: Literal[True]
