"""默认只监听本机；多用户部署前需要额外的身份与权限设计。"""

import uvicorn
import argparse
from pathlib import Path
import threading
import time
import webbrowser
from urllib.parse import urlencode


def open_when_ready(server, url: str, token: str) -> None:
    """等服务能接收请求后再打开浏览器；连接码只放在不会发送到服务器的地址片段中。"""
    for _ in range(300):
        if server.should_exit:
            return
        if server.started:
            webbrowser.open(url + "/#" + urlencode({"access": token}))
            return
        time.sleep(0.1)


def main():
    """只启动一个服务进程，避免多个进程同时占用同一浏览器资料。"""
    parser = argparse.ArgumentParser(description="JobPilot 本地工作台")
    parser.add_argument("--data", type=Path, help="独立的数据目录，默认 data/agent")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open-browser", action="store_true", help="自动打开并连接本机页面")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    from app.api.server import create_app, local_token
    from app.config import PROJECT_ROOT
    data_dir = args.data or PROJECT_ROOT / "data/agent"
    data_dir.mkdir(parents=True, exist_ok=True)
    token = local_token(data_dir)
    url = f"http://127.0.0.1:{args.port}"
    print(f"JobPilot 求职助手：{url}")
    from app.llm.client import create_llm
    from app.exceptions import ConfigurationError
    try:
        create_llm("live")
        print("AI 设置已填写。可在页面点击“测试连接”确认是否可用。")
    except (ConfigurationError, ValueError):
        print("首次使用请在页面连接 DeepSeek，也可以先免费体验示例。")
    print("服务运行时保持此窗口打开，停止请按 Ctrl+C。")
    server = uvicorn.Server(uvicorn.Config(create_app(data_dir=data_dir, token=token),
                                          host="127.0.0.1", port=args.port, workers=1))
    if args.open_browser:
        threading.Thread(target=open_when_ready, args=(server, url, token), daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
