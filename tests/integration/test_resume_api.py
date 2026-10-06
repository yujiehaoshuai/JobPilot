"""验证简历入口的权限、真实流式限额和原文证据到审批的完整链路。"""

from fastapi.testclient import TestClient
from app.api.server import create_app
from tests.integration.test_http_api import wait_for_pause


def test_resume_import_build_and_workflow(tmp_path):
    with TestClient(create_app(tmp_path, token="t")) as client:
        path = "/api/resume/extract?format=txt"
        content = "虚构同学\n在课程项目中使用 Python 编写测试。"
        assert client.post(path, content=content.encode()).status_code == 401
        client.headers["X-JobPilot-Token"] = "t"
        response = client.post(path, content=content.encode())
        assert response.status_code == 200 and response.json()["text"] == content
        body = dict(text=content, name="虚构同学", confirmed=True, skills=[dict(
            skill="Python", level="project_experience", quote="在课程项目中使用 Python 编写测试。")])
        candidate = client.post("/api/resume/profile", json=body)
        assert candidate.status_code == 200
        assert client.get("/api/runs").json() == []
        # 只有显式开始任务才持久化确认后的资料；上传和整理本身不启动任务。
        run = client.post("/api/runs", json={"candidate": candidate.json()})
        assert run.status_code == 202
        state = wait_for_pause(client, run.json()["id"])
        assert state["interrupts"][0]["kind"] == "approval"
        action = client.get("/api/actions", params={"run_id": run.json()["id"]}).json()[0]
        assert body["skills"][0]["quote"] in action["payload"]["content"]
        body["skills"][0]["quote"] = "虚构 Python 大厂经历"
        assert client.post("/api/resume/profile", json=body).status_code == 422


def test_resume_stream_limit_without_content_length(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token": "t"}) as client:
        def chunks():
            yield b"a" * 600000
            yield b"a" * 600000
        result = client.post("/api/resume/extract?format=txt", content=chunks())
        assert result.status_code == 413
        assert client.post("/api/resume/extract?format=docx", content=b"broken").status_code == 422
