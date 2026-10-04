"""验证批准绑定内容、幂等领取以及不确定结果的保守处理。"""

from concurrent.futures import ThreadPoolExecutor
import pytest
from app.exceptions import ConfirmationRequiredError, InvalidTransitionError, BrowserPausedError
from app.models.action import ActionPayload
from app.storage.actions import ActionStore
from app.services.action_service import ApprovalService, MockActionExecutor


@pytest.fixture
def action_setup(tmp_path, candidate, make_job):
    store = ActionStore(tmp_path / "actions.db")
    action = store.prepare("run1", ActionPayload(candidate=candidate, job=make_job(),
                                                 content="您好，这是测试消息", evidence_ids=[]))
    return store, action


def test_unapproved_cannot_send(action_setup):
    store, action = action_setup
    with pytest.raises(InvalidTransitionError):
        ApprovalService(store, MockActionExecutor()).execute(action.id)
    assert store.get(action.id).status == "PENDING"


def test_digest_and_rejection(action_setup):
    store, action = action_setup
    with pytest.raises(ConfirmationRequiredError):
        store.decide(action.id, "old-digest", True, "user")
    store.decide(action.id, action.digest, False, "user")
    assert ApprovalService(store, MockActionExecutor()).execute(action.id).status == "REJECTED"


def test_approved_action_sent_once_and_restored(action_setup):
    store, action = action_setup
    store.decide(action.id, action.digest, True, "user")
    service = ApprovalService(store, MockActionExecutor())
    first = service.execute(action.id)
    assert first.status == "SUCCEEDED"
    assert service.execute(action.id).receipt == first.receipt
    assert ActionStore(store.path).get(action.id).status == "SUCCEEDED"
    assert store.prepare("run1", action.payload).id == action.id
    with pytest.raises(InvalidTransitionError):
        store.prepare("run1", action.payload.model_copy(update={"content": "不同消息"}))


def test_timeout_does_not_retry_write(action_setup):
    store, action = action_setup
    store.decide(action.id, action.digest, True, "user")
    class Uncertain(MockActionExecutor):
        calls = 0
        def send(self, payload):
            self.calls += 1
            raise TimeoutError
    executor = Uncertain()
    service = ApprovalService(store, executor)
    assert service.execute(action.id).status == "UNCERTAIN"
    assert service.execute(action.id).status == "UNCERTAIN"
    assert executor.calls == 1


def test_claim_is_atomic(action_setup):
    store, action = action_setup
    store.decide(action.id, action.digest, True, "user")
    def claim():
        try:
            store.transition(action.id, "APPROVED", "EXECUTING")
            return True
        except InvalidTransitionError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: claim(), range(2))) == 1


def test_preflight_pause_preserves_approval(action_setup):
    store, action = action_setup
    store.decide(action.id, action.digest, True, "user")
    class Paused(MockActionExecutor):
        def preflight(self, payload):
            raise BrowserPausedError("需要登录")
    with pytest.raises(BrowserPausedError):
        ApprovalService(store, Paused()).execute(action.id)
    assert store.get(action.id).status == "APPROVED"
