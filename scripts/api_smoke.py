"""启动真实应用生命周期，用 HTTP 客户端完成一轮请求和审批暂停。"""

import time
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from app.api.server import create_app


def main():
    with TemporaryDirectory() as folder:
        app = create_app(Path(folder), token="offline-demo-token")
        with TestClient(app, headers={"X-JobPilot-Token": "offline-demo-token"}) as client:
            candidate = client.get("/api/candidate-example").json()
            run_id = client.post("/api/runs", json={"candidate": candidate}).json()["id"]
            for _ in range(100):
                value = client.get("/api/runs/" + run_id).json()
                if value["status"] == "PAUSED":
                    assert client.get("/api/actions").json()[0]["status"] == "PENDING"
                    print("HTTP -> background workflow -> approval pause -> SSE: OK")
                    assert "event: state" in client.get(f"/api/runs/{run_id}/events").text
                    return
                assert value["status"] != "FAILED", value.get("error")
                time.sleep(0.05)
            raise AssertionError("任务没有按预期暂停")


if __name__ == "__main__":
    main()
