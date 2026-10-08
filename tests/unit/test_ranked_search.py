"""验证软时间条件、可解释评分与模型引用边界，不调用真实模型。"""

from datetime import date
import pytest
from app.enums import SkillLevel
from app.exceptions import StructuredOutputError
from app.llm.offline import OfflineLLMClient
from app.models.candidate import CandidateProfile
from app.models.search import ResumeSearch, ResumeExtraction, SearchJobAnalysis, DeepReview
from app.services.resume_service import analyze_resume
from app.services.ranking_service import search_filter, score_match, review_match
from app.services.matching_service import CandidateMatcher


def profile():
    return CandidateProfile(id="fiction", name="虚构同学", target_cities=["上海"],
        available_days_per_week=3, internship_duration_months=3,
        skills=[dict(skill="Python", level="project_experience", evidence="在课程项目中使用 Python。")])


class FixedClient:
    usage = []
    def __init__(self, output):
        self.output = output
    def complete(self, task, payload, schema):
        return schema.model_validate(self.output)


def test_ai_resume_preserves_quotes_without_inventing_experience():
    body=ResumeSearch(text="在课程项目中使用 Python 编写工具。", intent="后端", source="mock", mode="offline")
    candidate, queries, warnings=analyze_resume(OfflineLLMClient(),body,"resume-id")
    assert candidate.id == "resume-id" and candidate.skills[0].evidence == body.text
    assert candidate.skills[0].level == SkillLevel.PROJECT_EXPERIENCE
    assert candidate.experience == [] and queries == ["后端"]
    assert not warnings


@pytest.mark.parametrize("update", [
    {"skills":[dict(skill="Python",quote="五年 Python 工作经验",level="professional")]},
    {"projects":["在大厂开发五年"]},
    {"name":"原文不存在的人"},
    {"available_days_per_week":5,"days_quote":"每周可到岗3天"},
])
def test_resume_rejects_fabricated_quote_or_time(update):
    raw=dict(search_queries=["Python"],**update)
    with pytest.raises(StructuredOutputError):
        analyze_resume(FixedClient(raw),ResumeSearch(text="使用 Python。每周可到岗3天",intent="Python"),"id")


def test_cutting_a_word_out_of_a_negation_cannot_create_skill():
    raw=dict(search_queries=["Python"],skills=[dict(skill="Python",quote="Python",level="professional")])
    candidate,_,warnings=analyze_resume(FixedClient(raw),ResumeSearch(text="我不会 Python。",intent="后端"),"id")
    assert candidate.skills == [] and warnings


def test_days_are_soft_but_city_deadline_and_closed_status_are_hard(make_job):
    candidate=profile()
    job=make_job(city="上海市/徐汇区",title="智能体研发",employment_type="internship",
                 required_days_per_week=5,internship_duration_months=6)
    assert search_filter(candidate,job).passed
    assert not search_filter(candidate,job.model_copy(update={"city":"北京"})).passed
    assert not search_filter(candidate,job.model_copy(update={"city":None})).passed
    assert not search_filter(candidate,job.model_copy(update={"deadline":date(2000,1,1)})).passed
    assert not search_filter(candidate,job.model_copy(update={"closed_reason":"职位已下线"})).passed


def test_score_keeps_four_and_five_day_jobs_but_explains_difference(make_job):
    candidate=profile()
    analysis=SearchJobAnalysis(required_skills=["Python"],preferred_skills=["SQL"],intent_fit="related",
        intent_quote="Python",evidence=[dict(skill="Python",quote="Python"),dict(skill="SQL",quote="SQL")])
    scores=[]
    for days in [4,5]:
        job=make_job(city="上海",employment_type="internship",required_days_per_week=days,internship_duration_months=3)
        match=score_match(candidate,job,analysis,CandidateMatcher().match(candidate,job,analysis))
        assert search_filter(candidate,job).passed
        assert match.score == sum(match.score_breakdown.values())
        assert "保留机会" in match.availability_notes[0]
        scores.append(match.score)
    assert scores[0]>scores[1]


@pytest.mark.parametrize("points,cautions", [
    ([dict(evidence_index=99,aspect="core")],[]),
    ([dict(evidence_index=0,aspect="core")],[]),
    ([],["不存在的岗位要求"]),
])
def test_deep_review_cannot_promote_missing_skills_or_invent_quotes(points,cautions):
    row={"job":{"title":"测试", "description":"需要 Python"},"match":{"score":10,"availability_notes":[],
        "evidence":[dict(requirement="Python",jd_quote="需要 Python",candidate_evidence=None,status="missing")]}}
    with pytest.raises(StructuredOutputError):
        review_match(FixedClient(dict(points=points,cautions=cautions)),row)


def test_explicit_alias_uses_the_original_resume_evidence(make_job):
    candidate=CandidateProfile(id="alias",name="虚构",skills=[dict(skill="JS",level="project_experience",evidence="使用 JS 编写课程页面")])
    analysis=SearchJobAnalysis(required_skills=["JavaScript"],evidence=[dict(skill="JavaScript",quote="JavaScript")])
    match=CandidateMatcher().match(candidate,make_job(),analysis)
    assert match.matched_skills==["JavaScript"]
    assert match.evidence[0].candidate_evidence==candidate.skills[0].evidence


def test_direction_quote_repair_is_bounded_and_revalidated(make_job):
    from app.services.analysis_service import JobAnalyzer
    class RepairClient:
        def __init__(self,repair):self.calls=0;self.repair=repair
        def complete(self,task,payload,schema):
            self.calls+=1
            if self.calls==2:assert "validation_feedback" in payload
            return schema.model_validate(dict(intent_fit="related",intent_quote="需要 Python" if self.calls==2 and self.repair else ""))
    fixed=RepairClient(True)
    assert JobAnalyzer(fixed).analyze(make_job(description="需要 Python"),intent="后端").intent_quote=="需要 Python"
    assert fixed.calls==2
    invalid=RepairClient(False)
    with pytest.raises(StructuredOutputError):JobAnalyzer(invalid).analyze(make_job(),intent="后端")
    assert invalid.calls==2
