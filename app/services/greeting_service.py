"""模型选择沟通重点，程序只引用候选人原有证据来组织草稿。"""

from app.llm.base import LLMClient
from app.models.analysis import GreetingDraft, GreetingPlan, MatchResult
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.exceptions import StructuredOutputError


class GreetingGenerator:
    """禁止自由生成经历，用证据编号和原文引用防止事实被夸大。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def generate(self, candidate: CandidateProfile, job: JobPosting, match: MatchResult) -> GreetingDraft:
        """无匹配时拒绝生成；所选证据必须来自当前候选人的相关技能。"""
        allowed = {item.candidate_evidence_id for item in match.evidence
                   if item.status in {"matched", "partial"} and item.candidate_evidence_id}
        facts = {f"skills/{index}": item for index, item in enumerate(candidate.skills)}
        if not match.shortlisted or match.job_id != job.id or not allowed:
            raise StructuredOutputError("缺少相关证据，拒绝生成沟通草稿")
        if not allowed <= facts.keys():
            raise StructuredOutputError("匹配结果引用了不存在的候选人证据")
        plan = self.client.complete("greeting", {"title": job.title,
            "allowed_evidence_ids": sorted(allowed),
            "skills": {key: facts[key].skill for key in sorted(allowed)}}, GreetingPlan)
        ids = list(dict.fromkeys(plan.evidence_ids))
        if not 1 <= len(ids) <= 3 or not set(ids) <= allowed:
            raise StructuredOutputError("草稿使用了未授权或过多的证据")
        quotes = [facts[key].evidence for key in ids]
        content = f"您好，我关注到贵司的「{job.title}」岗位。我的相关经历如下：\n"
        levels = {"learning": "正在学习", "project_experience": "项目中使用过", "professional": "工作中使用过"}
        content += "\n".join(f"- {facts[key].skill}（{levels[facts[key].level.value]}）：{facts[key].evidence}" for key in ids)
        content += "\n希望了解岗位的具体要求，并有机会进一步沟通。"
        return GreetingDraft(job_id=job.id, content=content,
                             used_candidate_evidence=quotes, evidence_ids=ids)
