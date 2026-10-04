"""定义本地申请记录；保存状态本身不会向招聘方发送任何内容。"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import AwareDatetime, Field

from app.enums import ApplicationStatus
from app.models.base import DomainModel, NonEmptyStr


class Application(DomainModel):
    """记录一名候选人对一个岗位的申请进度，供多次运行持续跟踪。

    candidate_id 和 job_id 关联候选人与岗位；id 标识申请记录本身。
    状态和操作说明由业务流程维护，数据模型不会执行投递操作。
    """

    id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    candidate_id: NonEmptyStr
    job_id: NonEmptyStr
    status: ApplicationStatus = ApplicationStatus.NEW
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    # 默认时间只在创建对象时生成，后续更新记录时需由业务流程维护。
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    # 未准备联系内容或尚未操作时保留为空，不代表已经联系招聘方。
    greeting_content: str | None = None
    last_action: str | None = None
    notes: str = ""
