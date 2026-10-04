"""默认只监听本机；多用户部署前需要额外的身份与权限设计。"""

import uvicorn


def main():
    """只启动一个服务进程，避免多个进程同时占用同一浏览器资料。"""
    print("Dashboard: http://127.0.0.1:8000")
    print("访问令牌：JOBPILOT_API_TOKEN 或 data/agent/api-token.txt")
    uvicorn.run("app.api.server:create_app", factory=True, host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()
