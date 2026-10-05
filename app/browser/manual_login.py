"""人工登录入口：启动正常 Edge 窗口，不连接调试接口，也不读取登录表单。"""

import os
import subprocess
from pathlib import Path
from filelock import FileLock, Timeout
from app.exceptions import BrowserPausedError
from app.browser.selectors import SiteSpec


def edge_executable() -> Path:
    """查找本机已安装的 Edge；不下载浏览器，不修改系统设置。"""
    for variable, relative in [
        ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
        ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
        ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
    ]:
        root = os.environ.get(variable)
        if root:
            path = Path(root) / relative
            if path.is_file():
                return path
    raise BrowserPausedError("未找到已安装的 Edge，请在 Windows 本机运行人工登录命令")


def manual_login(site: SiteSpec, profile: Path) -> None:
    """只负责打开专属窗口；用户本人登录，关闭窗口后由只读流程另行验收。"""
    executable = edge_executable()
    profile = Path(profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(profile / "jobpilot-session.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise BrowserPausedError("浏览器资料正在使用，请先关闭其他任务或登录窗口") from None
    try:
        # 普通人工浏览，不传 no-sandbox、远程调试、隐藏自动化等参数。
        # 参数使用列表传递，资料路径中的空格不能变成额外的命令。
        process = subprocess.Popen([str(executable), f"--user-data-dir={profile}",
                                    "--new-window", site.home])
        print("请在新开的 Edge 中手动登录；完成后关闭本次窗口以释放资料目录。", flush=True)
        print("本命令不读取密码、验证码或 Cookie，也不会自动确认登录成功。", flush=True)
        if process.wait() != 0:
            raise BrowserPausedError("Edge 未正常退出，请先检查并关闭本次窗口")
        # Edge 启动器有时会提前退出，而真正的窗口仍在运行。
        # 因此还需用户确认关闭，不能仅凭启动器退出就认定资料目录已释放。
        try:
            input("确认本次 Edge 窗口已关闭后按回车结束：")
        except EOFError:
            raise BrowserPausedError("终端输入已关闭；请先手动关闭本次浏览器窗口，再运行其他任务") from None
    finally:
        lock.release()
