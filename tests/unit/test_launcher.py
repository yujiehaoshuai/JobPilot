"""启动器只在服务就绪后打开页面，不把本机连接码放入 HTTP 查询参数。"""

from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

from app.server import open_when_ready


def test_launcher_waits_for_server_and_uses_fragment(monkeypatch):
    server = SimpleNamespace(started=False, should_exit=False)
    opened = []
    def become_ready(seconds):
        assert not opened
        server.started = True
    monkeypatch.setattr("app.server.time.sleep", become_ready)
    monkeypatch.setattr("app.server.webbrowser.open", opened.append)
    open_when_ready(server, "http://127.0.0.1:8000", "synthetic-connection")
    assert len(opened) == 1
    parts = urlsplit(opened[0])
    assert not parts.query and parse_qs(parts.fragment) == {"access": ["synthetic-connection"]}


def test_launcher_does_not_open_after_shutdown(monkeypatch):
    opened = []
    monkeypatch.setattr("app.server.webbrowser.open", opened.append)
    open_when_ready(SimpleNamespace(started=False, should_exit=True), "http://127.0.0.1:8000", "test")
    assert opened == []


def test_repeated_launch_reuses_only_the_same_data_directory(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock
    import pytest
    from app.exceptions import ConfigurationError
    from app.server import open_existing_server
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        "service": "JobPilot", "data_directory": str(tmp_path)}).encode()
    opener = MagicMock()
    opener.open.return_value = response
    monkeypatch.setattr("app.server.build_opener", lambda *args: opener)
    opened = []
    monkeypatch.setattr("app.server.webbrowser.open", opened.append)
    assert open_existing_server("http://127.0.0.1:8000", tmp_path, "synthetic-key")
    assert len(opened) == 1 and not urlsplit(opened[0]).query
    with pytest.raises(ConfigurationError, match="另一份数据目录"):
        open_existing_server("http://127.0.0.1:8000", tmp_path / "other", "synthetic-key")
    assert len(opened) == 1
    response.__enter__.return_value.read.return_value = b"[]"
    with pytest.raises(ConfigurationError, match="不是可连接"):
        open_existing_server("http://127.0.0.1:8000", tmp_path, "synthetic-key")
    assert len(opened) == 1
