"""迁移连接从 AGENT_DATABASE_URL 读取，不在配置文件提交数据库密码。"""

from alembic import context
from sqlalchemy import create_engine, pool
from app.storage.relational import metadata
from app.runtime_config import agent_database_url

config = context.config
url = config.attributes.get("database_url") or agent_database_url()
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
