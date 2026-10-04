"""审批使用完整快照，避免用户批准 A 内容后程序却发送 B 内容。"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from pydantic import Field
from app.models.base import DomainModel
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting


class ActionPayload(DomainModel):
    """审批界面必须展示的发送对象和正文；所有字段都参与摘要。"""

    kind: Literal["send_message"] = "send_message"
    candidate: CandidateProfile
    job: JobPosting
    content: str = Field(min_length=1, max_length=5000)
    evidence_ids: list[str]
    simulated: bool = True

    def digest(self) -> str:
        """固定 JSON 排序，使摘要在进程重启后仍保持一致。"""
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PendingAction(DomainModel):
    """不确定状态必须人工核查，不能简单当作失败后重试。"""

    id: str
    run_id: str
    payload: ActionPayload
    digest: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXECUTING", "SUCCEEDED", "UNCERTAIN"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_by: str | None = None
    receipt: str | None = None
