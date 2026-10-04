"""分析、匹配和沟通草稿的数据结构；每个候选人优势必须能追溯到原资料。"""

from typing import Literal
from pydantic import Field
from app.models.base import DomainModel, NonEmptyStr


class RequirementEvidence(DomainModel):
    """技能要求及 JD 原文，不接受模型自行编造的引用。"""

    skill: NonEmptyStr
    quote: NonEmptyStr


class JobAnalysis(DomainModel):
    """模型对 JD 的结构化理解；未知要求保留为空。"""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    education_requirement: str | None = None
    experience_requirement: str | None = None
    internship_requirement: str | None = None
    agent_related: bool = False
    llm_related: bool = False
    backend_related: bool = False
    risks: list[str] = Field(default_factory=list)
    evidence: list[RequirementEvidence] = Field(default_factory=list)


class MatchEvidence(DomainModel):
    """一个要求的匹配结果；候选人证据来自资料中的原文。"""

    requirement: str
    jd_quote: str
    candidate_evidence: str | None = None
    candidate_evidence_id: str | None = None
    status: Literal["matched", "partial", "missing"]


class MatchResult(DomainModel):
    """保守匹配结果，不使用无法解释的综合分数。"""

    job_id: str
    matched_skills: list[str] = Field(default_factory=list)
    partial_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    candidate_strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    recommendation_reason: str
    shortlisted: bool


class GreetingPlan(DomainModel):
    """模型只选择证据编号，不自由生成候选人经历。"""

    evidence_ids: list[str]


class GreetingDraft(DomainModel):
    """待人工审阅的草稿；本模型不能授权发送。"""

    job_id: str
    content: str
    used_candidate_evidence: list[str]
    evidence_ids: list[str]
    status: Literal["DRAFT", "APPROVED", "REJECTED", "SENT"] = "DRAFT"


class Usage(DomainModel):
    """记录真实用量；未知成本保留为空，避免把缺失数据当作免费。"""

    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    cost: float | None = None
    provider: str = "offline"
