"""通过真实回环 HTTP 与新服务实例验证恢复，而不是复用内存中的图。"""

from scripts.recovery_smoke import main


def test_http_service_restart_preserves_approval_and_completes():
    result = main()
    assert result["jobs"] == result["decisions"] == 11
