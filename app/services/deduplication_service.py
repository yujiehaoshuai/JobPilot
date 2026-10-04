"""按来源岗位编号和整理后的岗位链接去重，无需数据库或外部服务。"""

from app.models.job import JobPosting
from app.services.normalization_service import canonicalize_url


def deduplicate_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    """按输入顺序保留首次出现的岗位，返回去重后的列表。

    来源与岗位编号相同，或整理后的链接相同，都视为重复。
    被丢弃记录的编号和链接也要登记，避免它的另一种链接在后面再次出现。
    保留首条岗位的原有字段，不推测或合并后续记录的内容。
    """
    seen_source_ids: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    unique_jobs: list[JobPosting] = []
    for job in jobs:
        source_id = (job.source.strip().casefold(), job.source_job_id.strip())
        url = canonicalize_url(job.url)
        duplicate = source_id in seen_source_ids or bool(url and url in seen_urls)
        # 先登记所有见过的身份，再决定是否保留，才能识别连续关联的重复记录。
        seen_source_ids.add(source_id)
        if url:
            seen_urls.add(url)
        if not duplicate:
            unique_jobs.append(job)
    return unique_jobs
