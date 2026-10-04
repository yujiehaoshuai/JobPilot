"""保守地核对已提供的技能，避免把模型推测写成候选人事实。"""

from app.enums import SkillLevel
from app.models.analysis import JobAnalysis, MatchResult, MatchEvidence
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting


class CandidateMatcher:
    """当前只接受名称一致的显式技能；同义词和未结构化经历由用户补充确认。"""

    def match(self, candidate: CandidateProfile, job: JobPosting, analysis: JobAnalysis) -> MatchResult:
        """学习中的技能标记为部分匹配，资料中不存在的技能标记为缺失。"""
        skills = {item.skill.casefold(): (index, item) for index, item in enumerate(candidate.skills)}
        quotes = {item.skill.casefold(): item.quote for item in analysis.evidence}
        evidence: list[MatchEvidence] = []
        for requirement in dict.fromkeys(analysis.required_skills + analysis.preferred_skills):
            found = skills.get(requirement.casefold())
            if found:
                index, item = found
                evidence.append(MatchEvidence(requirement=requirement,
                    jd_quote=quotes.get(requirement.casefold(), ""), candidate_evidence=item.evidence,
                    candidate_evidence_id=f"skills/{index}",
                    status="partial" if item.level == SkillLevel.LEARNING else "matched"))
            else:
                evidence.append(MatchEvidence(requirement=requirement,
                    jd_quote=quotes.get(requirement.casefold(), ""), status="missing"))
        matched = [item.requirement for item in evidence if item.status == "matched"]
        partial = [item.requirement for item in evidence if item.status == "partial"]
        missing = [item.requirement for item in evidence if item.status == "missing"]
        shortlisted = bool(matched or partial)
        return MatchResult(job_id=job.id, matched_skills=matched, partial_skills=partial,
            missing_skills=missing, evidence=evidence,
            candidate_strengths=[item.candidate_evidence for item in evidence if item.status == "matched"],
            risks=analysis.risks + (["存在未满足的要求，请人工查看 JD"] if missing else []),
            shortlisted=shortlisted,
            recommendation_reason="存在可核验的技能交集，建议人工审阅" if shortlisted else "缺少可核验的技能交集")
