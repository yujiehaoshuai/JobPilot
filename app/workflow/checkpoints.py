"""搜索图与联系图共用检查点后端，按 thread_id 区分各自的恢复位置。"""

from contextlib import contextmanager
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def open_checkpointer(data_dir: Path, database_url: str | None = None):
    """沿用既有 SQLite 文件；启用 PostgreSQL 时也沿用已有检查点表。"""
    if database_url and database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        uri = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with PostgresSaver.from_conn_string(uri) as saver:
            yield saver
    else:
        with SqliteSaver.from_conn_string(str(Path(data_dir) / "checkpoints.db")) as saver:
            yield saver
