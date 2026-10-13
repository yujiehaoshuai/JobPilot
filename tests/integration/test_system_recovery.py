"""通过真实回环 HTTP 与新服务实例验证恢复，而不是复用内存中的图。"""

from scripts.recovery_smoke import main


def test_http_service_restart_preserves_approval_and_completes(monkeypatch):
    # 即使系统代理不可用，回环 API 的审批和恢复也不能经过代理。
    monkeypatch.setattr("urllib.request.getproxies", lambda: {"http": "http://127.0.0.1:1"})
    monkeypatch.setattr("urllib.request.proxy_bypass", lambda host: False)
    result = main()
    assert result["jobs"] == result["decisions"] == 11
