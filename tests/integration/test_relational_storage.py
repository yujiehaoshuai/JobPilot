"""验证迁移、并发批准和平台去重；有专用 PG 测试库时再跑真实驱动。"""

import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import inspect, text, create_engine
from langgraph.types import Command
from app.db_cli import upgrade
from app.storage.relational import database_engine, RelationalActionStore, RelationalTracker, RunStore
from app.models.action import ActionPayload
from app.exceptions import InvalidTransitionError
from app.services.action_service import ApprovalService, MockActionExecutor
from app.workflow.runtime import open_graph, graph_config
from app.main import load_candidate
from app.config import load_settings
from app.exceptions import StorageError


@pytest.fixture
def engine(tmp_path):
    url = "sqlite:///" + (tmp_path / "agent.db").as_posix()
    upgrade(url)
    upgrade(url)
    value = database_engine(url)
    yield value
    value.dispose()


def test_migration_and_tracker(engine, candidate, make_job):
    assert "agent_runs" in inspect(engine).get_table_names()
    tracker = RelationalTracker(engine)
    tracker.save_candidate(candidate)
    assert tracker.save_jobs([make_job()]) == 1
    assert tracker.save_jobs([make_job()]) == 0
    first = tracker.track(candidate.id, make_job().id)
    assert tracker.track(candidate.id, make_job().id).id == first.id
    tracker.update_status(first.id, "SHORTLISTED", confirmed=True)
    assert tracker.list_applications(candidate.id)[0].status == "SHORTLISTED"


def test_relational_approval_atomic(engine, candidate, make_job):
    store = RelationalActionStore(engine)
    action = store.prepare("r", ActionPayload(candidate=candidate, job=make_job(), content="测试", evidence_ids=[]))
    store.decide(action.id, action.digest, True, "human")
    def claim():
        try:
            store.transition(action.id, "APPROVED", "EXECUTING")
            return True
        except InvalidTransitionError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(lambda _: claim(), range(2))) == 1


def test_run_registry(engine):
    runs = RunStore(engine)
    runs.create("r", {"source": "mock"})
    runs.update("r", "WAITING_APPROVAL", node="review")
    assert runs.get("r")["node"] == "review"
    assert runs.list()[0]["source"] == "mock"


def test_legacy_schema_adoption_preserves_records(tmp_path, candidate):
    """复现旧工作流先建表、API 后迁移；补版本时已有候选人不能丢失。"""
    from app.storage.relational import metadata
    url = "sqlite:///" + (tmp_path / "legacy.db").as_posix()
    engine = create_engine(url)
    metadata.create_all(engine)
    RelationalTracker(engine).save_candidate(candidate)
    upgrade(url)
    upgrade(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001"
        assert conn.execute(text("SELECT id FROM agent_candidates")).scalar_one() == candidate.id
    engine.dispose()


def test_incompatible_legacy_schema_is_untouched(tmp_path):
    """未知布局不能被直接标记为迁移成功，原始数据必须仍可读取。"""
    url = "sqlite:///" + (tmp_path / "unknown.db").as_posix()
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE agent_candidates (id TEXT PRIMARY KEY, note TEXT)"))
        conn.execute(text("INSERT INTO agent_candidates VALUES ('preserve', 'original')"))
    with pytest.raises(StorageError, match="不完整"):
        upgrade(url)
    assert "alembic_version" not in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT note FROM agent_candidates")).scalar_one() == "original"
    engine.dispose()


def test_automatic_initialization_records_migration(tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    engine = database_engine(url, initialize=True)
    upgrade(url)
    assert "alembic_version" in inspect(engine).get_table_names()
    engine.dispose()


def test_relational_workflow_restart(tmp_path, engine):
    url = str(engine.url)
    config = graph_config("relational")
    profile = load_candidate(load_settings().candidate_path)
    with open_graph(tmp_path, database_url=url) as (graph, actions):
        graph.invoke({"run_id": "relational", "source": "mock", "mode": "offline",
                      "queries": ["Python"], "candidate": profile.model_dump(mode="json")}, config)
    with open_graph(tmp_path, database_url=url) as (graph, actions):
        action = actions.get(graph.get_state(config).values["action_id"])
        actions.decide(action.id, action.digest, False, "human")
        graph.invoke(Command(resume=True), config)
        assert actions.get(action.id).status == "REJECTED"


@pytest.mark.skipif(not os.environ.get("JOBPILOT_TEST_POSTGRES_URL"), reason="未提供专用 PostgreSQL 测试库")
def test_postgres_checkpoint_roundtrip(tmp_path):
    """只对显式提供的专用测试数据库建表，不连接用户未知数据库。"""
    from uuid import uuid4
    url = os.environ["JOBPILOT_TEST_POSTGRES_URL"]
    upgrade(url)
    run_id = str(uuid4())
    config = graph_config(run_id)
    profile = load_candidate(load_settings().candidate_path)
    with open_graph(tmp_path, database_url=url) as (graph, actions):
        graph.invoke({"run_id": run_id, "source": "mock", "mode": "offline", "queries": [],
                      "candidate": profile.model_dump(mode="json")}, config)
    with open_graph(tmp_path, database_url=url) as (graph, actions):
        assert graph.get_state(config).next == ("review",)
