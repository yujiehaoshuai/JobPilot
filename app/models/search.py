"""简历驱动的搜索输入与 AI 输出；原文证据和排序判断分开保存。"""

from typing import Literal
from pydantic import Field
from app.models.base import DomainModel, NonEmptyStr
from app.models.resume import ResumeSkill
from app.models.analysis import JobAnalysis
from app.enums import EmploymentType


class ResumeSearch(DomainModel):
    """页面只提交正文和意向，不要求用户手工整理技能。"""

    text: NonEmptyStr = Field(max_length=30000)
    intent: NonEmptyStr = Field(max_length=200)
    cities: list[NonEmptyStr] = Field(default_factory=list, max_length=10)
    employment_type: EmploymentType = EmploymentType.INTERN
    available_days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)
    internship_duration_months: int | None = Field(default=None, ge=1, le=120, strict=True)
    source: Literal["mock", "boss", "nowcoder", "shixiseng"] = "shixiseng"
    mode: Literal["offline", "live"] = "live"
    # 这是一次任务的资源边界，不是声称已经搜索全站。
    search_limit: int = Field(default=100, ge=1, le=200, strict=True)


class ResumeExtraction(DomainModel):
    """姓名、经历必须逐字引用；搜索同义词属于计划，不属于候选人事实。"""

    name: str | None = None
    skills: list[ResumeSkill] = Field(default_factory=list, max_length=40)
    education: list[str] = Field(default_factory=list, max_length=10)
    projects: list[str] = Field(default_factory=list, max_length=15)
    experience: list[str] = Field(default_factory=list, max_length=15)
    available_days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)
    days_quote: str | None = None
    internship_duration_months: int | None = Field(default=None, ge=1, le=120, strict=True)
    months_quote: str | None = None
    search_queries: list[NonEmptyStr] = Field(min_length=1, max_length=3)


class SearchJobAnalysis(JobAnalysis):
    """沿用 JD 引用校验，另判断岗位方向是否与用户意向接近。"""

    intent_fit: Literal["related", "adjacent", "unrelated", "unclear"] = "unclear"
    intent_quote: str = Field(default="", description="职业方向依据：逐字复制岗位 title 或 description 中的一段。只在 intent_fit=unclear 时允许为空。")


class ReviewPoint(DomainModel):
    """AI 只能选择已核验的证据，解释由程序引用原文呈现。"""

    evidence_index: int = Field(ge=0)
    aspect: Literal["core", "transferable", "gap", "learning"]


class DeepReview(DomainModel):
    """对前几名做第二轮审阅；不让模型自由补写候选人经历。"""

    points: list[ReviewPoint] = Field(default_factory=list, max_length=5)
    cautions: list[str] = Field(default_factory=list, max_length=3)
    # 顾虑只能摘录岗位原句，不接受生成的新候选人事实。
    questions: list[Literal["schedule", "duration", "education", "experience", "skill_depth"]] = Field(default_factory=list, max_length=5)
