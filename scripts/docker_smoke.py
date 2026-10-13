"""创建独立 Compose 测试项目，验证部署和重启恢复；不复用用户数据卷。"""

import json
import os
import secrets
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from urllib.request import getproxies
from app.config import PROJECT_ROOT
from scripts.system_smoke import LocalDemoClient


def main():
    """结束时仅清理本次随机项目的容器和卷；报告留在忽略的 data 下。"""
    project = "jobpilot-check-" + uuid4().hex[:16]
    folder = PROJECT_ROOT / "data/deployment" / project
    folder.mkdir(parents=True, exist_ok=False)
    report = {"project": project, "time": datetime.now(UTC).isoformat(), "status": "running", "steps": []}
    docker = shutil.which("docker")
    if not docker:
        report.update(status="blocked", reason="本机未找到 Docker；没有安装或改变现有环境")
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(report["reason"])
        print(f"报告：{folder / 'report.json'}")
        return 2
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # 显式覆盖 Compose 使用的变量，并指定空 env 文件，防止读取个人 .env。
    token = secrets.token_urlsafe(32)
    environment = {**os.environ, "POSTGRES_PASSWORD": secrets.token_hex(24), "JOBPILOT_API_TOKEN": token,
                   "JOBPILOT_HTTP_PORT": str(port), "LLM_BASE_URL": "https://example.invalid/v1",
                   "LLM_MODEL": "", "LLM_API_KEY": "", "LLM_INPUT_PRICE_PER_MILLION": "",
                   "LLM_OUTPUT_PRICE_PER_MILLION": ""}
    # Windows 已配置的系统代理不会自动传给 Docker CLI；仅给本次子进程补上。
    for scheme, proxy in getproxies().items():
        if scheme in {"http", "https"} and proxy:
            environment.setdefault(scheme.upper() + "_PROXY", proxy)
    with TemporaryDirectory(prefix="jobpilot-compose-") as temporary:
        env_file = Path(temporary) / "empty.env"
        env_file.write_text("", encoding="utf-8")
        command = [docker, "compose", "--project-name", project, "--env-file", str(env_file),
                   "--file", str(PROJECT_ROOT / "compose.yaml")]

        def run(label, arguments, timeout=180):
            print(f"部署验收：{label}", flush=True)
            with (folder / f"{label}.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(command + arguments, cwd=PROJECT_ROOT, env=environment,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            report["steps"].append({"name": label, "passed": result.returncode == 0})
            if result.returncode:
                raise RuntimeError(f"{label} 失败")

        try:
            run("configuration", ["config", "--quiet"])
            run("build", ["build"], timeout=1800)
            run("startup", ["up", "--detach", "--wait", "--wait-timeout", "180"], timeout=240)
            client = LocalDemoClient(f"http://127.0.0.1:{port}", token)
            client.wait_ready()
            run_id = client.start_paused()
            run("restart", ["restart", "app"])
            client.wait_ready()
            report["workflow"] = client.complete(run_id)
            report["steps"].append({"name": "checkpoint_resume", "passed": True})
            run("repeat_migration", ["exec", "-T", "app", "python", "-m", "app.db_cli", "upgrade"])
            # 测试目录只读挂载，不进入正式镜像；专用 PG 用本次临时数据库，不能跳过。
            run("postgres", ["run", "--rm", "--no-deps", "--volume",
                f"{PROJECT_ROOT / 'tests'}:/app/tests:ro", "app", "python", "-c",
                "import os, pytest; os.environ['JOBPILOT_TEST_POSTGRES_URL'] = os.environ['AGENT_DATABASE_URL']; "
                "raise SystemExit(pytest.main(['tests/integration/test_relational_storage.py', '-q', '-p', 'no:cacheprovider']))"])
            run("browser", ["exec", "-T", "app", "python", "-m", "scripts.browser_smoke"])
            run("evaluation", ["exec", "-T", "app", "python", "-m", "app.evaluation.runner"])
            report["status"] = "passed"
        except Exception as exc:
            report.update(status="failed", error_type=type(exc).__name__)
            # 清理临时容器前保存故障日志，迁移或健康检查失败后仍能查到原因。
            try:
                run("failure_logs", ["logs", "--no-color", "--tail", "100"], timeout=30)
            except Exception as log_error:
                report["log_error_type"] = type(log_error).__name__
        finally:
            # project 只能由本函数随机生成，不能传入已有项目名或用户数据卷。
            try:
                run("cleanup", ["down", "--volumes", "--remove-orphans"])
            except Exception as exc:
                report.update(status="failed", cleanup_error=type(exc).__name__)
            (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"部署验收：{report['status']}；报告：{folder / 'report.json'}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
