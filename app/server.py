"""默认只监听本机；多用户部署前需要额外的身份与权限设计。"""

import uvicorn
import argparse
from pathlib import Path


def main():
    """只启动一个服务进程，避免多个进程同时占用同一浏览器资料。"""
    parser = argparse.ArgumentParser(description="JobPilot 本地工作台")
    parser.add_argument("--data", type=Path, help="独立的数据目录，默认 data/agent")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    from app.api.server import create_app
    print(f"Dashboard: http://127.0.0.1:{args.port}")
    print(f"访问令牌：JOBPILOT_API_TOKEN 或 {args.data or Path('data/agent')}/api-token.txt")
    uvicorn.run(create_app(data_dir=args.data), host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
