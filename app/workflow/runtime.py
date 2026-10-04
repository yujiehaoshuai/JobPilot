"""为一次图调用准备资源，退出时关闭浏览器与数据库连接。"""

from contextlib import contextmanager
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import load_settings
from app.adapters.mock.adapter import MockJobAdapter
from app.adapters.boss import BossAdapter
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS
from app.llm.client import create_llm
from app.storage.tracker import SQLiteTracker
from app.storage.actions import ActionStore
from app.services.action_service import ApprovalService, MockActionExecutor
from app.exceptions import BrowserPausedError
from app.workflow.graph import build_graph


class UnverifiedPlatformExecutor:
    """真实发送必须先验证登录界面与收件人契约，未配置时明确暂停。"""

    def preflight(self, payload):
        raise BrowserPausedError("真实发送界面尚未验收，需人工核对平台收件人及发送控件")

    def send(self, payload):
        raise RuntimeError("未经页面验收不能发送")


@contextmanager
def open_graph(data_dir: Path, *, source="mock", mode="offline", adapter=None, client=None, database_url=None,
               transport="direct"):
    """只有真实来源才启动浏览器；默认运行完全离线。"""
    from contextlib import ExitStack
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        if adapter is None:
            if transport == "mcp":
                from app.mcp_client import MCPJobAdapter
                adapter = MCPJobAdapter(source)
            elif transport == "direct":
                from app.adapters.factory import open_adapter
                from app.tools.jobs import ToolCallingAdapter
                adapter = ToolCallingAdapter(stack.enter_context(open_adapter(source)))
            else:
                raise ValueError("工具连接方式必须为 direct 或 mcp")
        from app.runtime_config import setting
        database_url = database_url or setting("AGENT_DATABASE_URL")
        if database_url:
            from app.storage.relational import database_engine, RelationalActionStore, RelationalTracker
            engine = database_engine(database_url, initialize=database_url.startswith("sqlite:"))
            stack.callback(engine.dispose)
            actions, tracker = RelationalActionStore(engine), RelationalTracker(engine)
        else:
            # 保留 Phase 5 已有 SQLite 文件；启用新后端必须明确配置。
            actions = ActionStore(data_dir / "actions.db")
            tracker = stack.enter_context(SQLiteTracker(data_dir / "tracker.db"))
        if database_url and database_url.startswith("postgresql"):
            from langgraph.checkpoint.postgres import PostgresSaver
            uri = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
            saver = stack.enter_context(PostgresSaver.from_conn_string(uri))
        else:
            saver = stack.enter_context(SqliteSaver.from_conn_string(str(data_dir / "checkpoints.db")))
        executor = MockActionExecutor() if source == "mock" else UnverifiedPlatformExecutor()
        yield build_graph(adapter, client or create_llm(mode), actions,
                          ApprovalService(actions, executor), tracker, saver), actions


def graph_config(run_id: str):
    """同一个 run_id 始终使用同一检查点；上限容纳 50 个岗位的循环。"""
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 500}
