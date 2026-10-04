"""从本地文件读取固定的岗位样本，无需浏览器或网络。"""

import json
from pathlib import Path

from pydantic import ValidationError

from app.adapters.base import JobSourceAdapter
from app.exceptions import JobParseError
from app.models.job import JobPosting


class MockJobAdapter(JobSourceAdapter):
    """按文件名顺序读取岗位，每个 JSON 文件对应一个 JobPosting。

    固定读取顺序，让重复运行的筛选和去重结果保持稳定。
    """

    def __init__(self, fixtures_path: Path) -> None:
        """保存岗位样本目录；实际读取和校验在查询时执行。"""
        self.fixtures_path = Path(fixtures_path)

    def _load_jobs(self) -> list[JobPosting]:
        """读取并校验目录中的所有岗位，返回统一的数据模型列表。

        目录无效、没有样本或任一文件解析失败时，抛出 JobParseError。
        错误信息保留文件名和具体原因，方便定位有问题的样本。
        """
        if not self.fixtures_path.is_dir():
            raise JobParseError(f"Job fixture directory does not exist: {self.fixtures_path}")

        paths = sorted(self.fixtures_path.glob("*.json"))
        if not paths:
            raise JobParseError(f"No JSON job fixtures found in: {self.fixtures_path}")

        jobs: list[JobPosting] = []
        for path in paths:
            try:
                # 兼容普通 UTF-8 文件，以及 Windows 编辑器可能保存的 BOM 文件。
                raw_job = json.loads(path.read_text(encoding="utf-8-sig"))
                jobs.append(JobPosting.model_validate(raw_job))
            except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
                raise JobParseError(f"Invalid job fixture {path.name}: {exc}") from exc
        return jobs

    def search_jobs(self, queries: list[str] | None = None) -> list[JobPosting]:
        """在岗位标题和描述中查找查询词，命中任意一个就保留岗位。

        忽略空白查询词和大小写；查询词按普通文本处理，不作为正则表达式。
        清理后没有查询词时返回全部岗位。
        """
        jobs = self._load_jobs()
        terms = [query.strip().casefold() for query in queries or [] if query.strip()]
        if not terms:
            return jobs
        return [
            job
            for job in jobs
            if any(term in f"{job.title}\n{job.description}".casefold() for term in terms)
        ]

    def get_job_detail(self, source_job_id: str) -> JobPosting:
        """返回来源岗位编号一致的首条样本，找不到时抛出 JobParseError。"""
        for job in self._load_jobs():
            if job.source_job_id == source_job_id:
                return job
        raise JobParseError(f"Mock job not found: {source_job_id}")
