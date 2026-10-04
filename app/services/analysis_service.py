"""分析 JD 后核对引用；模型生成的字段不能越过原文边界。"""

from app.llm.base import LLMClient
from app.models.analysis import JobAnalysis
from app.models.job import JobPosting
from app.exceptions import StructuredOutputError


class JobAnalyzer:
    """只把岗位描述发给模型，不发送完整候选人资料。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def analyze(self, job: JobPosting) -> JobAnalysis:
        """校验每个技能的原文依据；没有依据的技能会导致本次分析失败。"""
        result = self.client.complete("analyze", {"description": job.description}, JobAnalysis)
        evidence = {item.skill.casefold(): item.quote for item in result.evidence}
        for item in result.evidence:
            if item.quote not in job.description or item.skill.casefold() not in item.quote.casefold():
                raise StructuredOutputError("技能引用不在 JD 中，已拒绝分析结果")
        for skill in result.required_skills + result.preferred_skills:
            if skill.casefold() not in evidence:
                raise StructuredOutputError("技能缺少可核验的 JD 引用")
        return result
