"""验证重试边界、进程锁和日志白名单，避免可靠性功能引入重复副作用。"""

import json
import pytest
from app.reliability import retry_model, workflow_lock, TokenBucket
from app.observability import EventLog
from app.exceptions import TransientLLMError, StructuredOutputError, InvalidTransitionError


def test_retry_only_transient_errors():
    calls = []
    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise TransientLLMError("暂时失败")
        return "ok"
    assert retry_model(operation, delay=0) == "ok"
    assert len(calls) == 3
    def invalid():
        raise StructuredOutputError("格式错误")
    with pytest.raises(StructuredOutputError):
        retry_model(invalid, delay=0)


def test_lock_prevents_duplicate_worker(tmp_path):
    with workflow_lock(tmp_path):
        with pytest.raises(InvalidTransitionError):
            with workflow_lock(tmp_path):
                pytest.fail("不应获得第二把锁")
    with workflow_lock(tmp_path):
        pass


def test_rate_limit_and_private_log(tmp_path):
    bucket = TokenBucket(capacity=2, per_second=0)
    assert bucket.allow() and bucket.allow() and not bucket.allow()
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.record("test", run_id="1", api_key="secret", resume="private content", status="PAUSED")
    log.close()
    saved = json.loads(path.read_text("utf-8"))
    assert saved["status"] == "PAUSED"
    assert "secret" not in path.read_text("utf-8") and "resume" not in saved
