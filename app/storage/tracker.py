"""用 SQLite 保存本地数据，并检查用户确认后的申请状态变更。

常见流程如下，具体允许的变更以本模块的状态表为准：
NEW -> ANALYZED -> SHORTLISTED -> CONTACT_READY -> CONTACTED -> REPLIED
-> INTERVIEW -> OFFER 或 REJECTED。

NEW 可以直接进入 SHORTLISTED。记录线下进展时，CONTACTED 也可以直接进入
INTERVIEW、OFFER 或 REJECTED。NEW、ANALYZED、SHORTLISTED、CONTACT_READY
可以进入 IGNORED；IGNORED 可以恢复为 NEW；CONTACT_READY 可以退回 SHORTLISTED。
除 ARCHIVED 外，所有状态都可以归档。ARCHIVED 是终态，不能再转为其他状态。
重复设置当前状态是允许的。

状态变更只记录用户确认的事实。即使改为 CONTACTED，也不会实际发送消息。
Phase 1 只处理本地记录，不执行外部招聘操作。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from pydantic import ValidationError

from app.enums import ApplicationStatus
from app.exceptions import (
    ConfirmationRequiredError,
    InvalidTransitionError,
    StorageError,
)
from app.models.application import Application
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.services.normalization_service import canonicalize_url

# 键是当前状态，值是允许进入的下一状态。空集合表示不能再转为其他状态。
_ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.NEW: frozenset(
        {
            ApplicationStatus.ANALYZED,
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.IGNORED,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.ANALYZED: frozenset(
        {
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.IGNORED,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.SHORTLISTED: frozenset(
        {
            ApplicationStatus.CONTACT_READY,
            ApplicationStatus.IGNORED,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.IGNORED: frozenset(
        {ApplicationStatus.NEW, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.CONTACT_READY: frozenset(
        {
            ApplicationStatus.CONTACTED,
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.IGNORED,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.CONTACTED: frozenset(
        {
            ApplicationStatus.REPLIED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.REPLIED: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.REJECTED: frozenset({ApplicationStatus.ARCHIVED}),
    ApplicationStatus.OFFER: frozenset({ApplicationStatus.ARCHIVED}),
    ApplicationStatus.ARCHIVED: frozenset(),
}


class SQLiteTracker:
    """保存候选人、岗位和申请记录，并限制人工修改申请状态的方式。

    每个实例管理一个数据库连接。建议用 ``with``，也可以显式调用 ``close()``。
    每次写入方法各用一个事务：本次修改要么全部成功，要么全部撤销。
    ``with`` 只负责关闭连接，不会把多个方法调用合并为一个事务。

    岗位通过“来源 + 来源岗位编号”或规范化网址识别。再次导入同一岗位时，
    保留首次保存的身份信息，避免已有申请记录失去关联。
    """

    def __init__(self, database_path: Path) -> None:
        """打开数据库；目录或数据表不存在时，自动创建。"""
        self.database_path = Path(database_path)
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                str(self.database_path), isolation_level=None
            )
            # 让查询结果支持按列名取值；每次写入由 _transaction 显式管理事务。
            self._connection.row_factory = sqlite3.Row
            # SQLite 必须主动开启外键检查，才能阻止申请引用不存在的候选人或岗位。
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._create_schema()
        except (OSError, sqlite3.Error, StorageError) as exc:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise StorageError(f"Cannot open database: {self.database_path}") from exc

    def __enter__(self) -> SQLiteTracker:
        """进入 ``with`` 时返回当前实例，供代码块内读写数据库。"""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出 ``with`` 时关闭连接，无论代码块正常结束还是抛出异常。"""
        self.close()

    def close(self) -> None:
        """关闭数据库连接；重复调用不会产生额外影响。"""
        self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """管理一次完整写入：成功时提交，出现异常时撤销本次全部修改。"""
        try:
            # 先取得写入权限，再查询和修改，避免并发导入都误判为“尚未保存”。
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
        except sqlite3.Error as exc:
            raise StorageError(f"Database write failed: {exc}") from exc

    def _create_schema(self) -> None:
        """建立数据表，用唯一约束和外键保护关联关系。

        候选人和岗位的完整模型保存为 JSON 文本，读取时再由 Pydantic 校验。
        岗位来源、来源编号等字段单独存列，供数据库识别重复岗位。
        申请的状态、备注等经常更新的字段也单独存列。
        """
        with self._transaction():
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )"""
            )
            # 同一来源的同一岗位只能保存一次，避免重复导入产生多条岗位记录。
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_job_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    UNIQUE (source, source_job_id)
                )"""
            )
            # 外键保证关联对象存在；唯一约束保证同一候选人对同一岗位只有一条申请。
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL REFERENCES candidates(id),
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    greeting_content TEXT,
                    last_action TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    UNIQUE (candidate_id, job_id)
                )"""
            )

    def save_candidate(self, profile: CandidateProfile) -> None:
        """新增或更新候选人资料，保留候选人编号及其已有申请关联。"""
        with self._transaction():
            # 已有编号只更新资料，不删除重建记录，避免破坏外键关联。
            self._connection.execute(
                """INSERT INTO candidates (id, data) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data""",
                (profile.id, profile.model_dump_json()),
            )

    def save_jobs(self, jobs: list[JobPosting]) -> int:
        """批量新增或更新岗位，返回本次新增的岗位数；更新不计入数量。

        整批岗位共用一个事务。只要一条写入失败，整批修改都会撤销。
        通过平台编号或网址找到已有岗位时，保留原本的本地编号和平台身份。
        即使输入使用了不同编号，只要网址相同，也继续使用首次保存的身份。
        创建申请前应调用 ``resolve_job_id()``，取得数据库里实际使用的岗位编号。

        若输入的本地编号已被另一个平台岗位占用，则拒绝整批写入。
        """
        inserted = 0
        with self._transaction():
            for job in jobs:
                same_id = self._connection.execute(
                    "SELECT source, source_job_id FROM jobs WHERE id = ?", (job.id,)
                ).fetchone()
                if same_id and (same_id["source"], same_id["source_job_id"]) != (
                    job.source,
                    job.source_job_id,
                ):
                    raise StorageError(
                        f"Job ID {job.id!r} already belongs to a different platform job"
                    )
                existing = self._find_existing_job(job)
                if existing is None:
                    self._connection.execute(
                        "INSERT INTO jobs (id, source, source_job_id, data) VALUES (?, ?, ?, ?)",
                        (job.id, job.source, job.source_job_id, job.model_dump_json()),
                    )
                    inserted += 1
                else:
                    # 只刷新岗位内容，沿用已有身份，确保申请仍关联到原来的岗位。
                    canonical = job.model_copy(update={
                        "id": existing.id,
                        "source": existing.source,
                        "source_job_id": existing.source_job_id,
                    })
                    self._connection.execute(
                        "UPDATE jobs SET data = ? WHERE id = ?",
                        (canonical.model_dump_json(), existing.id),
                    )
        return inserted

    def _find_existing_job(self, job: JobPosting) -> JobPosting | None:
        """先按“来源 + 来源岗位编号”查找，再比较规范化后的网址。

        同一岗位可能以不同编号或带不同参数的网址再次出现。规范化网址后比较，
        可以识别这些别名。本地数据量较小，因此直接遍历已保存的岗位。
        批量保存时，查找和写入在同一个事务内，避免并发导入重复保存同一网址。
        """
        row = self._connection.execute(
            "SELECT data FROM jobs WHERE source = ? AND source_job_id = ?",
            (job.source, job.source_job_id),
        ).fetchone()
        if row is not None:
            return JobPosting.model_validate_json(row["data"])
        url = canonicalize_url(job.url)
        return next((saved for saved in self.list_jobs()
                     if canonicalize_url(saved.url) == url), None)

    def resolve_job_id(self, job: JobPosting) -> str:
        """按平台编号或已知网址别名，返回数据库中实际保存的岗位编号。"""
        try:
            existing = self._find_existing_job(job)
        except (sqlite3.Error, ValidationError) as exc:
            raise StorageError("Cannot resolve saved job identity") from exc
        if existing is None:
            raise StorageError(f"Job has not been saved: {job.id}")
        return existing.id

    def track(self, candidate_id: str, job_id: str) -> Application:
        """为候选人和岗位创建 NEW 申请；已有申请则原样返回，不重置进度。"""
        with self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM applications WHERE candidate_id = ? AND job_id = ?",
                (candidate_id, job_id),
            ).fetchone()
            if existing is not None:
                return self._application_from_row(existing)
            application = Application(candidate_id=candidate_id, job_id=job_id)
            self._connection.execute(
                """INSERT INTO applications (
                    id, candidate_id, job_id, status, created_at, updated_at,
                    greeting_content, last_action, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    application.id,
                    application.candidate_id,
                    application.job_id,
                    application.status.value,
                    application.created_at.isoformat(),
                    application.updated_at.isoformat(),
                    application.greeting_content,
                    application.last_action,
                    application.notes,
                ),
            )
            return application

    def list_jobs(self) -> list[JobPosting]:
        """按编号排序返回已保存岗位，岗位编号均为数据库中保留的正式编号。"""
        try:
            rows = self._connection.execute("SELECT data FROM jobs ORDER BY id").fetchall()
            return [JobPosting.model_validate_json(row["data"]) for row in rows]
        except (sqlite3.Error, ValidationError) as exc:
            raise StorageError(f"Cannot read jobs: {exc}") from exc

    def list_applications(self, candidate_id: str | None = None) -> list[Application]:
        """按创建时间和编号返回申请；传入候选人编号时只返回该候选人的记录。"""
        try:
            if candidate_id is None:
                rows = self._connection.execute(
                    "SELECT * FROM applications ORDER BY created_at, id"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """SELECT * FROM applications WHERE candidate_id = ?
                    ORDER BY created_at, id""",
                    (candidate_id,),
                ).fetchall()
            return [self._application_from_row(row) for row in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read applications: {exc}") from exc

    def get_application(self, application_id: str) -> Application:
        """按编号读取申请；记录不存在时抛出 StorageError。"""
        try:
            row = self._connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read application: {exc}") from exc
        if row is None:
            raise StorageError(f"Application not found: {application_id}")
        return self._application_from_row(row)

    def update_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        *,
        confirmed: bool = False,
        notes: str | None = None,
    ) -> Application:
        """记录已确认且符合状态表的变更，也可以同时替换备注。

        ``confirmed=True`` 表示调用方已取得用户明确确认，本方法不会代替用户确认。
        ``notes=None`` 表示保留原备注；空字符串表示清空备注。
        只修改备注时也必须确认。状态和备注都没变时，直接返回原记录。
        """
        if confirmed is not True:
            raise ConfirmationRequiredError("Changing application status requires confirmation")
        try:
            status = ApplicationStatus(status)
        except ValueError as exc:
            raise InvalidTransitionError(f"Unknown application status: {status}") from exc
        with self._transaction():
            application = self.get_application(application_id)
            # 重复设置当前状态可以继续处理备注；真正切换状态时才检查允许的去向。
            if status != application.status and status not in _ALLOWED_TRANSITIONS[
                application.status
            ]:
                raise InvalidTransitionError(
                    f"Cannot change application from {application.status.value} to {status.value}"
                )
            updated_notes = application.notes if notes is None else notes
            if status == application.status and updated_notes == application.notes:
                return application
            updated = application.model_copy(
                update={
                    "status": status,
                    "notes": updated_notes,
                    "updated_at": datetime.now(UTC),
                    "last_action": f"status:{application.status.value}->{status.value}",
                }
            )
            self._connection.execute(
                """UPDATE applications SET status = ?, notes = ?, updated_at = ?,
                last_action = ? WHERE id = ?""",
                (
                    updated.status.value,
                    updated.notes,
                    updated.updated_at.isoformat(),
                    updated.last_action,
                    application_id,
                ),
            )
            return updated

    @staticmethod
    def _application_from_row(row: sqlite3.Row) -> Application:
        """把数据库行转回申请模型，并重新校验，避免无效数据流入业务代码。"""
        try:
            return Application.model_validate(dict(row))
        except ValidationError as exc:
            raise StorageError(f"Invalid stored application: {exc}") from exc
