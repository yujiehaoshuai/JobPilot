"""外部操作唯一执行入口；不确定结果保留记录，避免重复发送。"""

from typing import Protocol
from app.exceptions import BrowserPausedError, JobPilotError
from app.models.action import ActionPayload


class ActionExecutor(Protocol):
    """平台实现只接收已获批准的完整操作快照。"""

    def preflight(self, payload: ActionPayload) -> None:
        """执行前只读检查目标和会话；此方法禁止触发外部写入。"""

    def send(self, payload: ActionPayload) -> str:
        """只发送一次，返回平台确认凭据；没有确认应抛出异常。"""


class MockActionExecutor:
    """离线演示执行器，返回模拟凭据，从不连接外部平台。"""

    def preflight(self, payload):
        if not payload.simulated or payload.job.source != "mock":
            raise JobPilotError("模拟执行器只接受明确标记的 mock 动作")

    def send(self, payload):
        return "SIMULATED:" + payload.digest()


class ApprovalService:
    """先原子领取批准，再检查页面，最后至多执行一次发送。"""

    def __init__(self, store, executor: ActionExecutor):
        self.store, self.executor = store, executor

    def execute(self, action_id: str):
        action = self.store.get(action_id)
        if action.status in {"SUCCEEDED", "REJECTED", "UNCERTAIN"}:
            return action
        if action.status == "EXECUTING":
            # 另一个工作线程可能仍在发送，重复调用只查看状态，不能抢占执行。
            return action
        action = self.store.transition(action_id, "APPROVED", "EXECUTING")
        try:
            self.executor.preflight(action.payload)
        except Exception:
            # preflight 契约保证没有写入，因此此处可以恢复批准状态。
            self.store.transition(action_id, "EXECUTING", "APPROVED")
            raise
        try:
            receipt = self.executor.send(action.payload)
            if not receipt:
                raise JobPilotError("平台未返回确认")
        except Exception:
            return self.store.transition(action_id, "EXECUTING", "UNCERTAIN",
                                         receipt="发送阶段未得到可靠确认，请人工核查，禁止自动重发")
        return self.store.transition(action_id, "EXECUTING", "SUCCEEDED", receipt=receipt)
