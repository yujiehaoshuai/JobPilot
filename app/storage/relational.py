"""新的 Agent 数据使用同一套 SQLAlchemy 表定义，兼容 SQLite 与 PostgreSQL。"""

import json
from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime
from sqlalchemy import (MetaData, Table, Column, String, Text, UniqueConstraint,
                        ForeignKey, create_engine, select, update, delete, event)
from app.exceptions import InvalidTransitionError, ConfirmationRequiredError
from app.models.action import ActionPayload, PendingAction
from app.models.application import Application
from app.models.job import JobPosting
from app.enums import ApplicationStatus
from app.services.normalization_service import canonicalize_url
from app.storage.tracker import _ALLOWED_TRANSITIONS


metadata = MetaData()
action_table = Table("pending_actions", metadata,
    Column("id", String, primary_key=True), Column("run_id", String, nullable=False),
    Column("job_id", String, nullable=False), Column("digest", String, nullable=False),
    Column("status", String, nullable=False), Column("data", Text, nullable=False),
    UniqueConstraint("run_id", "job_id", name="uq_action_run_job"))
candidate_table = Table("agent_candidates", metadata,
    Column("id", String, primary_key=True), Column("data", Text, nullable=False))
job_table = Table("agent_jobs", metadata,
    Column("id", String, primary_key=True), Column("source", String, nullable=False),
    Column("source_job_id", String, nullable=False), Column("canonical_url", Text, nullable=False, unique=True),
    Column("data", Text, nullable=False), UniqueConstraint("source", "source_job_id", name="uq_agent_job_source"))
application_table = Table("agent_applications", metadata,
    Column("id", String, primary_key=True),
    Column("candidate_id", String, ForeignKey("agent_candidates.id"), nullable=False),
    Column("job_id", String, ForeignKey("agent_jobs.id"), nullable=False),
    Column("status", String, nullable=False), Column("data", Text, nullable=False),
    UniqueConstraint("candidate_id", "job_id", name="uq_agent_application"))
run_table = Table("agent_runs", metadata,
    Column("id", String, primary_key=True), Column("status", String, nullable=False),
    Column("data", Text, nullable=False))


def database_engine(url: str, *, initialize: bool = False):
    """所有自动初始化都通过 Alembic，避免与 API 的迁移入口产生冲突。"""
    if initialize:
        from app.db_cli import upgrade
        upgrade(url)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def configure(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")
    return engine


def insert_for(engine, table):
    """两种数据库都提供 ON CONFLICT，交给方言生成合法 SQL。"""
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError("只支持 SQLite 和 PostgreSQL")
    return insert(table)


class RelationalActionStore:
    """用条件更新原子消费批准，保持 Phase 4 的审批行为。"""

    def __init__(self, engine):
        self.engine = engine

    def prepare(self, run_id: str, payload: ActionPayload) -> PendingAction:
        action = PendingAction(id=str(uuid4()), run_id=run_id, payload=payload,
                               digest=payload.digest(), status="PENDING")
        with self.engine.begin() as conn:
            statement = insert_for(self.engine, action_table).values(id=action.id, run_id=run_id,
                job_id=payload.job.id, digest=action.digest, status=action.status, data=action.model_dump_json())
            conn.execute(statement.on_conflict_do_nothing(index_elements=["run_id", "job_id"]))
            data = conn.execute(select(action_table.c.data).where(
                action_table.c.run_id == run_id, action_table.c.job_id == payload.job.id)).scalar_one()
        result = PendingAction.model_validate_json(data)
        if result.digest != action.digest:
            raise InvalidTransitionError("草稿内容变化，请新建任务重新审批")
        return result

    def get(self, action_id: str) -> PendingAction:
        with self.engine.connect() as conn:
            data = conn.execute(select(action_table.c.data).where(action_table.c.id == action_id)).scalar_one_or_none()
        if data is None:
            raise KeyError(action_id)
        return PendingAction.model_validate_json(data)

    def list(self, run_id=None):
        query = select(action_table.c.data).order_by(action_table.c.id)
        if run_id is not None:
            query = query.where(action_table.c.run_id == run_id)
        with self.engine.connect() as conn:
            return [PendingAction.model_validate_json(row[0]) for row in conn.execute(query)]

    def transition(self, action_id, expected, target, **updates):
        with self.engine.begin() as conn:
            data = conn.execute(select(action_table.c.data).where(action_table.c.id == action_id)).scalar_one()
            action = PendingAction.model_validate_json(data)
            if action.status != expected or action.digest != action.payload.digest():
                raise InvalidTransitionError("动作状态或内容已变化")
            result = PendingAction.model_validate({**action.model_dump(), "status": target, **updates})
            changed = conn.execute(update(action_table).where(action_table.c.id == action_id,
                action_table.c.status == expected, action_table.c.digest == action.digest).values(
                    status=target, data=result.model_dump_json())).rowcount
            if changed != 1:
                raise InvalidTransitionError("动作已被其他执行器领取")
        return result

    def decide(self, action_id, digest, approve, actor):
        if not actor.strip() or self.get(action_id).digest != digest:
            raise ConfirmationRequiredError("审批人或审批摘要无效")
        return self.transition(action_id, "PENDING", "APPROVED" if approve else "REJECTED", decided_by=actor)

    def decide_many(self, decisions, approve, actor):
        """用户一次核对多条操作后，在一个事务中批准或取消，不能只成功一半。"""
        results = []
        with self.engine.begin() as conn:
            for action_id, digest in decisions:
                data = conn.execute(select(action_table.c.data).where(action_table.c.id == action_id)).scalar_one()
                action = PendingAction.model_validate_json(data)
                allowed = {"PENDING"} if approve else {"PENDING", "APPROVED"}
                if action.status not in allowed or action.digest != digest or action.digest != action.payload.digest():
                    raise InvalidTransitionError("岗位状态或审批内容已变化，请刷新后重新核对")
                result = PendingAction.model_validate({**action.model_dump(),
                    "status":"APPROVED" if approve else "REJECTED", "decided_by":actor})
                count = conn.execute(update(action_table).where(action_table.c.id == action_id,
                    action_table.c.status == action.status, action_table.c.digest == digest).values(
                        status=result.status, data=result.model_dump_json())).rowcount
                if count != 1:
                    raise InvalidTransitionError("操作已被领取或取消，请刷新")
                results.append(result)
        return results


class RelationalTracker:
    """Agent 版跟踪器；沿用相同领域模型，不修改 Phase 1 数据库。"""

    def __init__(self, engine):
        self.engine = engine

    def save_candidate(self, profile):
        with self.engine.begin() as conn:
            statement = insert_for(self.engine, candidate_table).values(id=profile.id, data=profile.model_dump_json())
            conn.execute(statement.on_conflict_do_update(index_elements=["id"], set_={"data": profile.model_dump_json()}))

    def save_jobs(self, jobs):
        count = 0
        with self.engine.begin() as conn:
            for job in jobs:
                url = canonicalize_url(job.url)
                existing = conn.execute(select(job_table).where(
                    ((job_table.c.source == job.source) & (job_table.c.source_job_id == job.source_job_id))
                    | (job_table.c.canonical_url == url))).mappings().first()
                if existing:
                    job = job.model_copy(update={"id": existing["id"], "source": existing["source"],
                                                 "source_job_id": existing["source_job_id"]})
                    conn.execute(update(job_table).where(job_table.c.id == job.id).values(
                        data=job.model_dump_json(), canonical_url=url))
                else:
                    statement = insert_for(self.engine, job_table).values(id=job.id, source=job.source,
                        source_job_id=job.source_job_id, canonical_url=url, data=job.model_dump_json())
                    count += conn.execute(statement.on_conflict_do_nothing()).rowcount
        return count

    def resolve_job_id(self, job):
        with self.engine.connect() as conn:
            return conn.execute(select(job_table.c.id).where(
                ((job_table.c.source == job.source) & (job_table.c.source_job_id == job.source_job_id))
                | (job_table.c.canonical_url == canonicalize_url(job.url)))).scalar_one()

    def track(self, candidate_id, job_id):
        application = Application(candidate_id=candidate_id, job_id=job_id)
        with self.engine.begin() as conn:
            statement = insert_for(self.engine, application_table).values(id=application.id,
                candidate_id=candidate_id, job_id=job_id, status=application.status.value,
                data=application.model_dump_json())
            conn.execute(statement.on_conflict_do_nothing(index_elements=["candidate_id", "job_id"]))
            data = conn.execute(select(application_table.c.data).where(
                application_table.c.candidate_id == candidate_id, application_table.c.job_id == job_id)).scalar_one()
        return Application.model_validate_json(data)

    def list_jobs(self):
        with self.engine.connect() as conn:
            return [JobPosting.model_validate_json(row[0]) for row in conn.execute(select(job_table.c.data))]

    def list_applications(self, candidate_id=None):
        query = select(application_table.c.data)
        if candidate_id:
            query = query.where(application_table.c.candidate_id == candidate_id)
        with self.engine.connect() as conn:
            return [Application.model_validate_json(row[0]) for row in conn.execute(query)]

    def update_status(self, application_id, status, *, confirmed=False, notes=None):
        if not confirmed:
            raise ConfirmationRequiredError("状态修改需要确认")
        status = ApplicationStatus(status)
        with self.engine.begin() as conn:
            data = conn.execute(select(application_table.c.data).where(
                application_table.c.id == application_id)).scalar_one()
            value = Application.model_validate_json(data)
            if value.status != status and status not in _ALLOWED_TRANSITIONS[value.status]:
                raise InvalidTransitionError("不允许的申请状态转移")
            old = value.status
            value.status, value.updated_at = status, datetime.now(UTC)
            if notes is not None:
                value.notes = notes
            changed = conn.execute(update(application_table).where(application_table.c.id == application_id,
                application_table.c.status == old.value).values(status=status.value, data=value.model_dump_json())).rowcount
            if changed != 1:
                raise InvalidTransitionError("申请状态已变化，请刷新")
        return value


class RunStore:
    """保存任务入口参数和可展示状态，完整执行上下文由 Checkpoint 管理。"""

    def __init__(self, engine):
        self.engine = engine

    def create(self, run_id: str, data: dict):
        with self.engine.begin() as conn:
            conn.execute(run_table.insert().values(id=run_id, status="QUEUED", data=json.dumps(data)))

    def get(self, run_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(run_table).where(run_table.c.id == run_id)).mappings().first()
        if row is None:
            raise KeyError(run_id)
        return {"id": row["id"], "status": row["status"], **json.loads(row["data"])}

    def expand_search(self, run_id, expected_limit):
        """仅扩展已完成且触及数量上限的只读搜索，不接受新的简历或筛选条件。"""
        with self.engine.begin() as conn:
            row = conn.execute(select(run_table).where(run_table.c.id == run_id)).mappings().first()
            if row is None:
                raise KeyError(run_id)
            data = json.loads(row["data"])
            incoming, snapshot = data["input"], data.get("snapshot", {})
            limit = incoming.get("search_limit", 100)
            if (row["status"] != "COMPLETED" or not incoming.get("ranking")
                    or not incoming.get("analysis_only") or limit != expected_limit):
                raise InvalidTransitionError("搜索状态或额度已变化，请刷新后再试")
            coverage = snapshot.get("search_coverage", {})
            if not coverage.get("limit_reached"):
                raise InvalidTransitionError("本轮没有触及数量上限；页面或验证问题请先处理，不能直接扩大搜索")
            if limit + 50 > 1000:
                raise InvalidTransitionError("单次任务最多 1000 条，请缩小岗位范围后重新搜索")
            if not incoming.get("resume_search", {}).get("cities"):
                raise InvalidTransitionError("这条旧任务没有填写城市，请填写城市后重新搜索")
            limit += 50
            incoming["search_limit"] = limit
            incoming["resume_search"]["search_limit"] = limit
            data.update(error=None, interrupts=[])
            changed = conn.execute(update(run_table).where(run_table.c.id == run_id,
                run_table.c.status == "COMPLETED", run_table.c.data == row["data"]).values(
                    status="QUEUED", data=json.dumps(data))).rowcount
            if changed != 1:
                raise InvalidTransitionError("这次搜索已被继续，请刷新查看进度")
        return limit

    def list(self):
        with self.engine.connect() as conn:
            rows = conn.execute(select(run_table).order_by(run_table.c.id)).mappings().all()
        return [{"id": row["id"], "status": row["status"], **json.loads(row["data"])} for row in rows]

    def update(self, run_id, status, **changes):
        data = self.get(run_id)
        data.pop("id"); data.pop("status")
        data.update(changes)
        with self.engine.begin() as conn:
            conn.execute(update(run_table).where(run_table.c.id == run_id).values(status=status, data=json.dumps(data)))

    def begin_cleanup(self, run_id):
        """先保存清理标记。跨数据库清理中断后，只能重试清理，不能重跑搜索。"""
        with self.engine.begin() as conn:
            changed = conn.execute(update(run_table).where(run_table.c.id == run_id,
                run_table.c.status.in_(["COMPLETED", "FAILED", "DELETING"]),
                ~select(action_table.c.id).where(action_table.c.run_id == run_id).exists(),
            ).values(status="DELETING")).rowcount
            return changed == 1

    def finish_cleanup(self, run_id):
        """删除搜索快照，并清理不再被其他任务或联系记录使用的资料和岗位。"""
        def references(data):
            candidates, jobs = set(), set()
            for state in [data.get("input", {}), data.get("snapshot", {})]:
                candidate = state.get("candidate") or {}
                if candidate.get("id"):
                    candidates.add(candidate["id"])
                for job in [*state.get("jobs", []), *state.get("discovered_jobs", []),
                            *(row["job"] for row in state.get("results", [])),
                            *(row["job"] for row in state.get("rejected_jobs", []))]:
                    jobs.add(job["id"])
            return candidates, jobs

        with self.engine.begin() as conn:
            row = conn.execute(select(run_table).where(run_table.c.id == run_id)).mappings().one()
            if row["status"] != "DELETING":
                raise InvalidTransitionError("搜索状态已变化，不能清理")
            if conn.execute(select(action_table.c.id).where(action_table.c.run_id == run_id)).first():
                raise InvalidTransitionError("存在联系记录，不能清理这次搜索")
            candidate_ids, job_ids = references(json.loads(row["data"]))
            owned_job_ids = set(job_ids)
            for data in conn.execute(select(run_table.c.data).where(run_table.c.id != run_id)).scalars():
                kept_candidates, kept_jobs = references(json.loads(data))
                candidate_ids -= kept_candidates
                job_ids -= kept_jobs
            for data in conn.execute(select(action_table.c.data)).scalars():
                payload = json.loads(data)["payload"]
                candidate_ids.discard(payload["candidate"]["id"])
                job_ids.discard(payload["job"]["id"])
            # 已联系、面试等跟踪记录不属于可丢弃的搜索缓存。
            conn.execute(delete(application_table).where(application_table.c.candidate_id.in_(candidate_ids),
                application_table.c.job_id.in_(owned_job_ids),
                application_table.c.status.in_(["NEW", "ANALYZED", "SHORTLISTED"])))
            conn.execute(delete(candidate_table).where(candidate_table.c.id.in_(candidate_ids),
                ~select(application_table.c.id).where(application_table.c.candidate_id == candidate_table.c.id).exists()))
            conn.execute(delete(job_table).where(job_table.c.id.in_(job_ids),
                ~select(application_table.c.id).where(application_table.c.job_id == job_table.c.id).exists()))
            conn.execute(delete(run_table).where(run_table.c.id == run_id, run_table.c.status == "DELETING"))
