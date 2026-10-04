"""定义 Phase 1 的岗位来源接口，目前只支持读取岗位。"""

from abc import ABC, abstractmethod

from app.models.job import JobPosting


class JobSourceAdapter(ABC):
    """把不同来源的岗位统一为 JobPosting，隔离平台细节。

    业务服务只使用此接口，无需了解数据来自文件还是招聘平台。
    Phase 1 不提供联系准备和发送接口；这些操作留待 Phase 4，
    并与明确的人工审批一同加入。
    """

    @abstractmethod
    def search_jobs(self, queries: list[str] | None = None) -> list[JobPosting]:
        """返回匹配任一查询词的岗位；未提供查询词时返回全部岗位。"""

    @abstractmethod
    def get_job_detail(self, source_job_id: str) -> JobPosting:
        """按来源平台的岗位编号，返回一条完整的岗位信息。"""
