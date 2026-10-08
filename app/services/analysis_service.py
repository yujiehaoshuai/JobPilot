"""分析 JD 后核对引用；模型生成的字段不能越过原文边界。"""

from app.llm.base import LLMClient
from app.models.analysis import JobAnalysis
from app.models.job import JobPosting
from app.exceptions import StructuredOutputError


class JobAnalyzer:
    """只把岗位描述发给模型，不发送完整候选人资料。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def analyze(self, job: JobPosting, intent: str | None = None) -> JobAnalysis:
        """校验每个技能的原文依据；没有依据的技能会导致本次分析失败。"""
        from app.models.search import SearchJobAnalysis
        payload = {"description": job.description}
        if intent is not None:
            payload.update(title=job.title, intent=intent)
        # 新排序多了职业方向引用；最多纠正一次格式/引用错误，仍不接受无依据结果。
        attempts = 2 if intent is not None else 1
        for attempt in range(attempts):
            result = self.client.complete("search_analyze" if intent is not None else "analyze", payload,
                                          SearchJobAnalysis if intent is not None else JobAnalysis)
            try:
                self.validate(result, job, intent)
                return result
            except StructuredOutputError as exc:
                if attempt + 1 == attempts:
                    raise
                payload["validation_feedback"] = str(exc) + "。请重新输出完整结构，原文引用须直接复制，禁止留空或改写。"

    @staticmethod
    def validate(result, job, intent):
        """结构合法还不够，每个技能和职业方向都要能回到岗位原文。"""
        if intent is not None and (result.intent_quote not in job.title + "\n" + job.description
                                  or (result.intent_fit != "unclear" and not result.intent_quote)):
            raise StructuredOutputError("岗位方向判断缺少岗位原文依据")
        evidence = {item.skill.casefold(): item.quote for item in result.evidence}
        for item in result.evidence:
            if item.quote not in job.description or item.skill.casefold() not in item.quote.casefold():
                raise StructuredOutputError("技能引用不在 JD 中，已拒绝分析结果")
        for skill in result.required_skills + result.preferred_skills:
            if skill.casefold() not in evidence:
                raise StructuredOutputError("技能缺少可核验的 JD 引用")
