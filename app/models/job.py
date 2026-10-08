"""定义各招聘来源共用的岗位数据，以及规则筛选结果。

允许岗位描述为空，由筛选服务记录明确的淘汰原因。
"""

from datetime import UTC, datetime, date
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, field_validator

from app.enums import EmploymentType
from app.models.base import DomainModel, NonEmptyStr


class JobPosting(DomainModel):
    """用统一字段保存岗位，不依赖浏览器或候选人信息。

    可选字段缺失时保留为 None，表示未知，不擅自补全。
    时间字段必须带时区，避免不同来源的时间含义不一致。
    """

    # id 是本系统的岗位编号；来源名称和来源岗位编号一起用于去重。
    id: NonEmptyStr
    source: NonEmptyStr
    source_job_id: NonEmptyStr
    title: NonEmptyStr
    company: NonEmptyStr
    city: str | None = None
    salary: str | None = None
    description: str
    url: NonEmptyStr
    publish_time: AwareDatetime | None = None
    hr_activity: str | None = None
    deadline: date | None = None
    closed_reason: str | None = None
    # 默认记录当前 UTC 时间，表示本次获取岗位的时间。
    fetched_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    employment_type: EmploymentType = EmploymentType.ANY
    # 以下是岗位对实习时长和每周到岗天数的要求，不是候选人的可用时间。
    # strict=True 要求输入整数，防止字符串或布尔值被自动转换。
    internship_duration_months: int | None = Field(default=None, ge=1, le=120, strict=True)
    required_days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)

    @field_validator("url")
    @classmethod
    def validate_job_url(cls, value: str) -> str:
        """校验岗位链接，成功时返回原字符串，格式不正确时抛出异常。

        只接受带主机名的 HTTP 或 HTTPS 链接，并拒绝含空白的地址。
        这里只检查格式，不访问网页，也不判断岗位是否仍然有效。
        """
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme.lower() in {"http", "https"} and parsed.hostname
            # 读取端口会触发格式校验，可发现 :abc 这类无效端口。
            parsed.port
        except ValueError as exc:
            raise ValueError("Job URL must be a valid HTTP(S) URL") from exc
        if not valid or any(character.isspace() for character in value):
            raise ValueError("Job URL must be a valid HTTP(S) URL")
        return value


class FilterResult(DomainModel):
    """保存规则筛选是否通过，以及未通过的具体原因。

    reasons 可以同时记录多条原因，便于用户了解岗位为何被排除。
    """

    passed: bool
    reasons: list[str] = Field(default_factory=list)
