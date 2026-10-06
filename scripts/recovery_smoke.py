"""无需 Docker，在本机重启真实 HTTP 服务验证持久审批和完整 Mock 流程。"""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import socket
import threading
import uvicorn
from app.api.server import create_app
from scripts.system_smoke import LocalDemoClient


@contextmanager
def temporary_server(folder):
    """每次使用新端口和服务实例，但数据库目录由调用方保持不变。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    token = "synthetic-recovery-token"
    app = create_app(folder, token=token, database_url="sqlite:///" + (folder / "agent.db").as_posix())
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        client = LocalDemoClient(f"http://127.0.0.1:{port}", token)
        client.wait_ready()
        yield client
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("本机验收服务未能正常结束")


def main():
    with TemporaryDirectory(prefix="jobpilot-recovery-") as folder:
        with temporary_server(Path(folder)) as client:
            run_id = client.start_paused()
        # 旧进程的工作线程和数据库连接已关闭；新服务必须从持久记录恢复。
        with temporary_server(Path(folder)) as client:
            result = client.complete(run_id)
        print(f"HTTP restart / checkpoint / mock approval / tracker: OK ({result['jobs']} jobs)")
        return result


if __name__ == "__main__":
    main()
