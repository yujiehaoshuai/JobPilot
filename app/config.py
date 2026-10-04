"""读取程序配置，并把文件路径转换成明确的绝对路径。

配置来自进程环境变量、项目 .env 和代码默认值。
读取 .env 只生成字典，不会修改当前进程的环境变量。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from app.exceptions import ConfigurationError

# 从本文件的位置找到项目根目录，避免默认路径随终端所在目录变化。
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """保存一轮运行所需的路径和日志级别。

    frozen=True 表示创建后不能重新赋值，避免运行途中意外改动配置。
    """

    candidate_path: Path  # 候选人资料 JSON 文件。
    jobs_path: Path  # 模拟岗位 JSON 文件所在的目录。
    database_path: Path  # 保存候选人、岗位和申请进度的 SQLite 文件。
    log_level: str  # 控制日志详细程度，例如 INFO 或 DEBUG。


def resolve_path(value: str, project_root: Path) -> Path:
    """把配置中的路径转为绝对路径，并展开代表用户目录的 ~。

    绝对路径保持原位置；相对路径从 project_root 开始查找。
    这里只计算路径，不创建文件，也不要求目标已经存在。
    """
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def load_settings(project_root: Path = PROJECT_ROOT) -> Settings:
    """按环境变量 > .env > 默认值的顺序读取，并校验配置。

    选中的值如果为空，就使用默认值；不会继续读取低优先级的值。
    返回 Settings；数据库格式或日志级别不支持时，抛出配置异常。
    """
    project_root = project_root.resolve()
    local_values = dotenv_values(project_root / ".env", interpolate=False)

    def setting(name: str, default: str) -> str:
        """读取一个配置项，清除首尾空白；缺失或留空时采用默认值。"""
        value = os.environ.get(name, local_values.get(name))
        return value.strip() if value and value.strip() else default

    database_url = setting("DATABASE_URL", "sqlite:///data/jobpilot.db")
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ConfigurationError("DATABASE_URL 目前只支持 sqlite:///文件路径")
    database_file = database_url[len(prefix):]
    # 当前需要文件持久保存数据，因此不接受内存数据库或带查询参数的连接地址。
    if not database_file or database_file == ":memory:" or "?" in database_file:
        raise ConfigurationError("DATABASE_URL 必须指向一个持久化 SQLite 文件")

    log_level = setting("LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("LOG_LEVEL 必须是 DEBUG/INFO/WARNING/ERROR/CRITICAL")

    return Settings(
        candidate_path=resolve_path(
            setting("CANDIDATE_PROFILE_PATH", "fixtures/candidate.example.json"), project_root
        ),
        jobs_path=resolve_path(setting("MOCK_JOBS_PATH", "fixtures/jobs"), project_root),
        database_path=resolve_path(database_file, project_root),
        log_level=log_level,
    )
