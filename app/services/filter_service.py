"""用明确的求职条件筛选岗位，并记录原因；不进行语义分析或能力推测。"""

import re

from app.enums import EmploymentType
from app.models.candidate import CandidateProfile
from app.models.job import FilterResult, JobPosting

# 只统一已知的地点别名，未列出的城市保留原值，避免猜测地点含义。
CITY_ALIASES = {
    "hangzhou": "杭州",
    "shanghai": "上海",
    "shenzhen": "深圳",
    "remote": "remote",
    "远程": "remote",
    "远程办公": "remote",
    "远程工作": "remote",
    "居家办公": "remote",
}


def _city_key(city: str) -> str:
    """整理城市名称，返回可直接比较的值。

    忽略大小写和多余空白，去掉末尾的“市”，再转换已知别名。
    """
    value = " ".join(city.strip().casefold().split())
    if value.endswith("市"):
        value = value[:-1]
    return CITY_ALIASES.get(value, value)


def _contains(text: str, keyword: str) -> bool:
    """检查文本是否包含指定词语，忽略大小写和连续空白的差异。

    关键词按普通文本处理，特殊符号不会被当作正则表达式。
    中文按短语匹配；英文和数字边缘增加边界，减少误匹配。
    """
    term = " ".join(keyword.split()).casefold()
    if not term:
        return False
    normalized = " ".join(text.split()).casefold()
    # 限制英文或数字边界，避免关键词 AI 意外匹配到 retail 中间的字母。
    pattern = re.escape(term)
    if term[0].isascii() and term[0].isalnum():
        pattern = r"(?<![a-z0-9])" + pattern
    if term[-1].isascii() and term[-1].isalnum():
        pattern += r"(?![a-z0-9])"
    return re.search(pattern, normalized) is not None


class RuleFilter:
    """检查候选人明确填写的条件，一次返回全部不符合的原因。

    岗位可选信息缺失表示未知，不会仅因缺失就淘汰岗位。
    标题关键词只做初步筛选，不代表候选人已具备岗位要求的技能。
    """

    def evaluate(self, candidate: CandidateProfile, job: JobPosting) -> FilterResult:
        """根据候选人资料检查一条岗位，并返回 FilterResult。

        依次检查描述、城市、排除项、目标标题、用工类型和实习可用时间。
        各项检查独立进行；只有没有任何淘汰原因时，passed 才为真。
        """
        reasons: list[str] = []
        if not job.description.strip():
            reasons.append("Empty job description")

        if candidate.target_cities and job.city and job.city.strip():
            allowed = {_city_key(city) for city in candidate.target_cities}
            if _city_key(job.city) not in allowed:
                reasons.append(f"City outside target cities: {job.city}")

        # 排除岗位名称只查标题；排除关键词同时检查标题和完整描述。
        for role in candidate.excluded_roles:
            if _contains(job.title, role):
                reasons.append(f"Excluded role in title: {role}")
        for keyword in candidate.excluded_keywords:
            if _contains(f"{job.title}\n{job.description}", keyword):
                reasons.append(f"Excluded keyword: {keyword}")

        # 目标岗位与偏好关键词共用“任一命中”规则；未填写时不限制标题。
        title_terms = candidate.target_roles + candidate.preferred_keywords
        if title_terms and not any(_contains(job.title, term) for term in title_terms):
            reasons.append("Title does not contain a target role or preferred keyword")

        # 只有双方都明确填写用工类型时才比较；ANY 表示不限制或未明确。
        if (
            candidate.employment_type != EmploymentType.ANY
            and job.employment_type != EmploymentType.ANY
            and candidate.employment_type != job.employment_type
        ):
            reasons.append(f"Employment type mismatch: {job.employment_type.value}")

        # 实习时间仅在岗位为实习、且双方都填写了相应数值时比较。
        if job.employment_type == EmploymentType.INTERN:
            if (
                candidate.internship_duration_months is not None
                and job.internship_duration_months is not None
                and candidate.internship_duration_months < job.internship_duration_months
            ):
                reasons.append(
                    f"Internship requires {job.internship_duration_months} months; "
                    f"candidate available for {candidate.internship_duration_months}"
                )
            if (
                candidate.available_days_per_week is not None
                and job.required_days_per_week is not None
                and candidate.available_days_per_week < job.required_days_per_week
            ):
                reasons.append(
                    f"Internship requires {job.required_days_per_week} days/week; "
                    f"candidate available for {candidate.available_days_per_week}"
                )

        return FilterResult(passed=not reasons, reasons=reasons)
