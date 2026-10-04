"""在临时数据库演示人工批准及一次模拟执行，不读取用户数据库。"""

from tempfile import TemporaryDirectory
from pathlib import Path
from app.config import load_settings
from app.main import load_candidate
from app.adapters.mock.adapter import MockJobAdapter
from app.models.action import ActionPayload
from app.storage.actions import ActionStore
from app.services.action_service import ApprovalService, MockActionExecutor


def main():
    settings = load_settings()
    with TemporaryDirectory() as folder:
        store = ActionStore(Path(folder) / "actions.db")
        payload = ActionPayload(candidate=load_candidate(settings.candidate_path),
                                job=MockJobAdapter(settings.jobs_path).search_jobs()[0],
                                content="离线审批演示，不会发送", evidence_ids=[])
        action = store.prepare("smoke", payload)
        store.decide(action.id, action.digest, True, "offline-test-human")
        assert ApprovalService(store, MockActionExecutor()).execute(action.id).status == "SUCCEEDED"
        print("Approval -> simulated execution -> receipt: OK")


if __name__ == "__main__":
    main()
