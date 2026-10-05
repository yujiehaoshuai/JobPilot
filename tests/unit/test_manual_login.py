"""人工登录只打开指定网站和项目资料目录，不接入自动化控制。"""

from unittest.mock import Mock
from filelock import FileLock
import pytest
from app.browser.manual_login import manual_login
from app.browser.selectors import BOSS
from app.exceptions import BrowserPausedError


def test_manual_login_uses_normal_browser_arguments(tmp_path, monkeypatch):
    executable = tmp_path / "Edge Application" / "msedge.exe"
    monkeypatch.setattr("app.browser.manual_login.edge_executable", lambda: executable)
    launch = Mock(return_value=Mock(wait=lambda: 0))
    monkeypatch.setattr("app.browser.manual_login.subprocess.Popen", launch)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    profile = tmp_path / "profile with spaces"
    manual_login(BOSS, profile)
    assert launch.call_args.args[0] == [str(executable), f"--user-data-dir={profile.resolve()}", "--new-window", BOSS.home]
    with FileLock(str(profile / "jobpilot-session.lock"), timeout=0):
        pass


def test_manual_login_respects_profile_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("app.browser.manual_login.edge_executable", lambda: tmp_path / "msedge.exe")
    launch = Mock()
    monkeypatch.setattr("app.browser.manual_login.subprocess.Popen", launch)
    with FileLock(str(tmp_path / "jobpilot-session.lock"), timeout=0):
        with pytest.raises(BrowserPausedError, match="正在使用"):
            manual_login(BOSS, tmp_path)
    launch.assert_not_called()
