"""后续阶段专用配置，保持原 Phase 1 的配置兼容。"""

import os
from pathlib import Path
from dotenv import dotenv_values
from app.config import PROJECT_ROOT


def setting(name, default=""):
    """只读配置，环境变量优先；不打印密钥或含密码的 URL。"""
    values = dotenv_values(PROJECT_ROOT / ".env", interpolate=False)
    return (os.environ.get(name, values.get(name)) or default).strip()


def agent_database_url(data_dir: Path | None = None):
    folder = data_dir or PROJECT_ROOT / "data/agent"
    folder.mkdir(parents=True, exist_ok=True)
    return setting("AGENT_DATABASE_URL", "sqlite:///" + str((folder / "agent.db").resolve()).replace("\\", "/"))
