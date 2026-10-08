"""默认只监听本机；多用户部署前需要额外的身份与权限设计。"""

import uvicorn
import argparse
from pathlib import Path
import threading
import time
import webbrowser
import json
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import URLError, HTTPError


def open_existing_server(url: str, data_dir: Path, token: str) -> bool:
    """同一资料目录的服务已运行时直接打开它，不要求用户复制连接码。"""
    from app.llm.client import NoRedirect
    from app.exceptions import ConfigurationError
    try:
        request = Request(url + "/api/instance", headers={"X-JobPilot-Token": token})
        with build_opener(NoRedirect).open(request, timeout=2) as response:
            value = json.loads(response.read(4096))
    except HTTPError:
        raise ConfigurationError("这个端口已有其他服务或旧版程序，请关闭旧程序，或使用 --port 8001 启动") from None
    except (URLError, TimeoutError):
        return False
    except (ValueError, UnicodeError):
        raise ConfigurationError("这个端口不是可连接的 JobPilot 服务，请换一个端口") from None
    if not isinstance(value, dict) or not isinstance(value.get("data_directory"), str):
        raise ConfigurationError("这个端口不是可连接的 JobPilot 服务，请换一个端口")
    if value.get("service") != "JobPilot" or Path(value["data_directory"]).resolve() != data_dir.resolve():
        raise ConfigurationError("这个端口正在使用另一份数据目录，请使用 --port 8001")
    webbrowser.open(url + "/#" + urlencode({"access": token}))
    return True


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
    if args.open_browser:
        from app.exceptions import ConfigurationError
        try:
            if open_existing_server(url, data_dir, token):
                print("程序已经在运行，已为你重新打开页面。")
                return
        except ConfigurationError as exc:
            parser.error(str(exc))
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
