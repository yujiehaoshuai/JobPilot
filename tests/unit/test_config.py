"""验证配置的默认值、覆盖顺序和路径解析，避免受启动目录或终端环境影响。"""

from pathlib import Path

import pytest

from app.config import load_settings
from app.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """每项测试前临时移除外部配置，防止本机环境变量影响测试结果。"""
    for name in ("DATABASE_URL", "LOG_LEVEL", "CANDIDATE_PROFILE_PATH", "MOCK_JOBS_PATH"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_resolve_against_project_root(tmp_path: Path) -> None:
    """未提供配置时，数据和样例路径应以指定项目根目录为基准。"""
    settings = load_settings(tmp_path)
    assert settings.database_path == tmp_path / "data" / "jobpilot.db"
    assert settings.candidate_path == tmp_path / "fixtures" / "candidate.example.json"
    assert settings.jobs_path == tmp_path / "fixtures" / "jobs"
    assert settings.log_level == "INFO"


def test_environment_overrides_dotenv_without_changing_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """环境变量优先于 .env，读取 .env 时不应改写当前进程的环境变量。"""
    import os

    (tmp_path / ".env").write_text(
        "DATABASE_URL=sqlite:///custom.db\nLOG_LEVEL=debug\n"
        "CANDIDATE_PROFILE_PATH=private/profile.json\n", encoding="utf-8"
    )
    monkeypatch.setenv("LOG_LEVEL", "warning")
    settings = load_settings(tmp_path)
    assert settings.database_path == tmp_path / "custom.db"
    assert settings.candidate_path == tmp_path / "private" / "profile.json"
    assert settings.log_level == "WARNING"
    assert "DATABASE_URL" not in os.environ


def test_blank_example_values_use_defaults(tmp_path: Path) -> None:
    """示例配置中的空值应采用默认配置，避免把空字符串当成有效设置。"""
    (tmp_path / ".env").write_text("DATABASE_URL=\nLOG_LEVEL=\n", encoding="utf-8")
    assert load_settings(tmp_path).log_level == "INFO"
    assert load_settings(tmp_path).database_path == tmp_path / "data" / "jobpilot.db"


@pytest.mark.parametrize("url", ["postgresql://localhost/db", "sqlite:///", "sqlite:///:memory:", "sqlite:///x.db?mode=ro"])
def test_unsupported_database_configuration_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """逐项拒绝不支持的数据库类型、空路径、内存库和附带查询参数的地址。"""
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ConfigurationError):
        load_settings(tmp_path)


def test_invalid_log_level_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """日志级别填写错误时应明确报错，避免静默采用意外配置。"""
    monkeypatch.setenv("LOG_LEVEL", "everything")
    with pytest.raises(ConfigurationError):
        load_settings(tmp_path)


def test_absolute_database_path_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """用户指定绝对数据库路径时，应原样使用，不再拼接项目根目录。"""
    expected = tmp_path / "another" / "tracker.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + expected.as_posix())
    assert load_settings(tmp_path).database_path == expected
