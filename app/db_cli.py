"""显式执行数据库升级；不会自动删除旧 SQLite 或迁移真实资料。"""

import argparse
from alembic import command
from alembic.config import Config
from app.config import PROJECT_ROOT
from app.runtime_config import agent_database_url


def upgrade(url: str):
    """应用业务表迁移，再准备 LangGraph 自己维护的检查点表。"""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        with PostgresSaver.from_conn_string(url.replace("postgresql+psycopg://", "postgresql://", 1)) as saver:
            saver.setup()


def main():
    parser = argparse.ArgumentParser(description="升级 Agent 数据库与检查点结构")
    parser.add_argument("command", choices=["upgrade"])
    parser.parse_args()
    upgrade(agent_database_url())
    print("Agent database migration: OK")


if __name__ == "__main__":
    main()
