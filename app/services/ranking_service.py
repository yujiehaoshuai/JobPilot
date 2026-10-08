"""保留时间有差距的机会，用公开的分项分数排序，再解释靠前的岗位。"""

from datetime import datetime, timedelta, timezone
import re
from app.enums import EmploymentType
from app.exceptions import StructuredOutputError
from app.models.job import FilterResult
from app.models.search import DeepReview
from app.services.filter_service import RuleFilter, _city_key


def search_filter(candidate, job) -> FilterResult:
    """城市和明确的工作类型仍是硬条件；标题、到岗时间交给后续评分。"""
    relaxed = candidate.model_copy(update={"target_roles": [], "preferred_keywords": [],
        "available_days_per_week": None, "internship_duration_months": None, "target_cities": []})
    decision = RuleFilter().evaluate(relaxed, job)
    if candidate.target_cities and not job.city:
        decision.reasons.append("岗位未注明城市，无法确认符合你选择的城市")
    elif candidate.target_cities:
        places = re.split(r"[/、,，;；\s]+", job.city)
        if not any(_city_key(place) == _city_key(city) or place.startswith(_city_key(city) + "市")
                   for city in candidate.target_cities for place in places):
            decision.reasons.append(f"City outside target cities: {job.city}")
    if job.closed_reason:
        decision.reasons.append("岗位已停止招聘：" + job.closed_reason)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    if job.deadline and job.deadline < today:
        decision.reasons.append(f"岗位已过截止日期：{job.deadline.isoformat()}")
    decision.passed = not decision.reasons
    return decision


def score_match(candidate, job, analysis, match):
    """技能占 70 分、意向占 20 分、时间占 10 分；不是录用概率。"""
    weights = {name.casefold(): 1 for name in analysis.preferred_skills}
    weights.update({name.casefold(): 3 for name in analysis.required_skills})
    credit = {item.requirement.casefold(): {"matched": 1, "partial": 0.5, "missing": 0}[item.status]
              for item in match.evidence}
    skill_points = 70 * sum(weight * credit.get(name, 0) for name, weight in weights.items()) / (sum(weights.values()) or 1)
    intent_points = {"related": 20, "adjacent": 12, "unclear": 5, "unrelated": 0}[analysis.intent_fit]
    notes, time_points = [], 10.0
    if job.employment_type == EmploymentType.INTERN:
        for actual, required, label, unit, weight in [
            (candidate.available_days_per_week, job.required_days_per_week, "每周到岗", "天", 3),
            (candidate.internship_duration_months, job.internship_duration_months, "连续实习", "个月", 1),
        ]:
            if actual is not None and required is not None and actual < required:
                notes.append(f"岗位要求{label} {required} {unit}，你的资料为 {actual} {unit}；保留机会，需沟通确认。")
                time_points -= min(5, (required - actual) * weight)
            elif actual is None or required is None:
                notes.append(f"{label}信息尚不完整，需要向招聘方确认。")
                time_points -= 2
    breakdown = {"技能证据（70）": round(skill_points, 1), "岗位意向（20）": intent_points,
                 "可用时间（10）": max(0, time_points)}
    match.score_breakdown = breakdown
    match.score = round(sum(breakdown.values()), 1)
    match.availability_notes = notes
    if not weights:
        match.risks.append("岗位未提取到可核验技能，技能项计 0 分，不能把信息缺失视为完全匹配。")
    if not job.deadline and not job.closed_reason:
        match.risks.append("页面未给出可核验的截止日期，请到原页确认是否仍在招聘。")
    return match


def review_match(client, row):
    """第二轮 AI 只挑选已核验的重点和 JD 顾虑，程序组织解释。"""
    match, job = row["match"], row["job"]
    value = client.complete("deep_review", {"job_title": job["title"], "description": job["description"],
        "score": match["score"], "evidence": match["evidence"], "availability": match["availability_notes"]}, DeepReview)
    reasons = []
    labels = {"core": "这项经历直接对应岗位要求", "transferable": "这项基础有参考价值，仍需确认实际深度",
              "gap": "这项要求缺少简历依据", "learning": "这项技能还处于学习阶段"}
    seen = set()
    for point in value.points:
        if point.evidence_index >= len(match["evidence"]):
            raise StructuredOutputError("详细分析使用了不存在的证据编号")
        evidence = match["evidence"][point.evidence_index]
        allowed = {"matched": {"core", "transferable"}, "partial": {"learning", "transferable"}, "missing": {"gap"}}
        if point.aspect not in allowed[evidence["status"]]:
            raise StructuredOutputError("详细分析把缺失或学习中的技能说成已掌握，已拒绝保存")
        if point.evidence_index in seen:
            continue
        seen.add(point.evidence_index)
        reasons.append({"reason": labels[point.aspect], **evidence})
    if any(not quote or quote not in job["description"] for quote in value.cautions):
        raise StructuredOutputError("详细分析的顾虑不在岗位原文中")
    questions = {"schedule": "能否协商每周到岗天数？", "duration": "能否协商实习时长？",
                 "education": "学历和毕业时间是否符合岗位要求？", "experience": "岗位要求的经验深度如何衡量？",
                 "skill_depth": "缺少的技能是否可以入职后学习？"}
    return {"reasons": reasons, "cautions": value.cautions,
            "questions": list(dict.fromkeys(questions[key] for key in value.questions))}
