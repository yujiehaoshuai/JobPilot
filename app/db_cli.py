"""显式执行数据库升级；不会自动删除旧 SQLite 或迁移真实资料。"""

import argparse
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from app.config import PROJECT_ROOT
from app.runtime_config import agent_database_url
from app.exceptions import StorageError


def adopt_legacy_sqlite(config: Config, url: str) -> None:
    """接管早期直接建表的 Agent 库；结构完全相符才补记版本，不改业务数据。"""
    from app.storage.relational import metadata
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            context = MigrationContext.configure(connection)
            if context.get_current_heads() or not tables.intersection(metadata.tables):
                return
            # 仅接管当前已知的 0001 布局。将来增加迁移后，不能拿新模型替旧库作证。
            if ScriptDirectory.from_config(config).get_current_head() != "0001":
                raise StorageError("发现未记录版本的旧 Agent 数据库，请先核对 0001 结构，不能自动跳过迁移")
            if not set(metadata.tables).issubset(tables):
                raise StorageError("旧 Agent 数据库表不完整，已停止迁移并保留原数据")
            context = MigrationContext.configure(connection, opts={
                "include_object": lambda obj, name, kind, reflected, target:
                    kind != "table" or name in metadata.tables,
                "compare_type": True, "compare_server_default": True,
            })
            differences = compare_metadata(context, metadata)
            for name, table in metadata.tables.items():
                if inspector.get_pk_constraint(name)["constrained_columns"] != [c.name for c in table.primary_key]:
                    differences.append("primary_key")
            if differences:
                raise StorageError("旧 Agent 数据库结构与 0001 不一致，已停止迁移并保留原数据")
        # 校验连接退出后再记录版本，避免 SQLite 读事务阻塞写入。
        command.stamp(config, "0001")
    finally:
        engine.dispose()


def upgrade(url: str):
    """应用业务表迁移，再准备 LangGraph 自己维护的检查点表。"""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["database_url"] = url
    if url.startswith("sqlite:"):
        adopt_legacy_sqlite(config, url)
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
