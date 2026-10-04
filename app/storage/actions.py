"""审批记录的事务存储；独立数据库不影响原有 SQLiteTracker。"""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from app.exceptions import ConfirmationRequiredError, InvalidTransitionError
from app.models.action import ActionPayload, PendingAction


class ActionStore:
    """每次调用短连接，允许 API 工作线程安全读写同一个文件。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL,
                digest TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
                UNIQUE(run_id, job_id))""")

    def connect(self):
        """提交和回滚由调用者的 with 块控制，连接在块结束后关闭。"""
        from contextlib import contextmanager
        @contextmanager
        def connection():
            conn = sqlite3.connect(self.path, timeout=15)
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        return connection()

    def prepare(self, run_id: str, payload: ActionPayload) -> PendingAction:
        """同一任务岗位只能有一份草稿；重放必须保持相同内容。"""
        action = PendingAction(id=str(uuid4()), run_id=run_id, payload=payload,
                               digest=payload.digest(), status="PENDING")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM pending_actions WHERE run_id=? AND job_id=?",
                               (run_id, payload.job.id)).fetchone()
            if row:
                previous = PendingAction.model_validate_json(row[0])
                if previous.digest != action.digest:
                    raise InvalidTransitionError("草稿已存在但内容变化，请创建新任务重新审批")
                return previous
            conn.execute("INSERT INTO pending_actions VALUES(?,?,?,?,?,?)", (
                action.id, run_id, payload.job.id, action.digest, action.status, action.model_dump_json()))
        return action

    def get(self, action_id: str) -> PendingAction:
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM pending_actions WHERE id=?", (action_id,)).fetchone()
        if not row:
            raise KeyError(action_id)
        return PendingAction.model_validate_json(row[0])

    def list(self, run_id: str | None = None) -> list[PendingAction]:
        with self.connect() as conn:
            if run_id is None:
                rows = conn.execute("SELECT data FROM pending_actions ORDER BY rowid").fetchall()
            else:
                rows = conn.execute("SELECT data FROM pending_actions WHERE run_id=? ORDER BY rowid",
                                    (run_id,)).fetchall()
        return [PendingAction.model_validate_json(row[0]) for row in rows]

    def transition(self, action_id: str, expected: str, target: str, **updates) -> PendingAction:
        """在同一个写事务中核对状态与正文摘要，保证只能消费一次批准。"""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM pending_actions WHERE id=?", (action_id,)).fetchone()
            if not row:
                raise KeyError(action_id)
            action = PendingAction.model_validate_json(row[0])
            if action.status != expected or action.digest != action.payload.digest():
                raise InvalidTransitionError("动作状态或正文已变化，不能执行当前操作")
            action = PendingAction.model_validate({**action.model_dump(), "status": target, **updates})
            conn.execute("UPDATE pending_actions SET status=?, data=? WHERE id=?",
                         (target, action.model_dump_json(), action_id))
        return action

    def decide(self, action_id: str, digest: str, approve: bool, actor: str) -> PendingAction:
        """必须提交用户看到的摘要；旧页面不能批准后来改变的动作。"""
        if not actor.strip() or self.get(action_id).digest != digest:
            raise ConfirmationRequiredError("审批人或审批摘要无效")
        return self.transition(action_id, "PENDING", "APPROVED" if approve else "REJECTED",
                               decided_by=actor)
