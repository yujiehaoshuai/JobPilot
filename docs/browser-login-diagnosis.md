# BOSS 登录窗口诊断（2026-10-05）

## 已确认的现象

用户看到 BOSS 页面先出现，然后跳到 `about:blank`，同时 Edge 提示 `--no-sandbox` 不受支持。

这是两个需要分别验证的问题：

- 沙箱警告来自 Playwright 默认启动配置。本机依赖源码和官方文档均表明，不显式启用沙箱时会添加 `--no-sandbox`。
- 修复为 `chromium_sandbox=True` 后，系统进程检查确认没有 `--no-sandbox`。但只读复现仍观察到 BOSS 首次响应为 HTTP 200，约两秒后主页面成为 `about:blank`。
- 因此沙箱警告的来源已确认并修复；空白跳转的具体机制尚未确定。不能仅凭此现象断言账号异常、验证码失败或网站封禁。

依据：[Playwright BrowserType 参数说明](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context-option-chromium-sandbox)。本机 Python Playwright 版本为 1.63.0。

## 已做的最小修复

1. BrowserSession 显式启用 Chromium 沙箱。
2. `about:blank` 明确触发暂停，不能当作登录成功；不循环刷新或绕过验证。
3. 增加普通 Edge 人工登录入口，复用 `profiles/boss`，只由用户本人操作。该入口不使用远程调试参数，不读取密码、验证码或 Cookie。
4. 人工窗口和自动读取共用资料目录锁，避免同时占用。Edge 启动器可能比窗口提前退出，所以终端还会要求确认关闭窗口后再结束。

实际打开的普通 Edge 主进程已核对：无 `--no-sandbox`、无 `--remote-debugging-pipe`。是否能够登录以及登录是否有效，仍需人工完成和后续只读验收。

## 用户操作

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli login --source boss --manual
```

在新开的普通 Edge 中手动登录或完成验证。完成后关闭本次窗口，再在运行命令的终端按回车。浏览器资料仍留在 `profiles/boss`，不要删除或提交 Git。

然后才能验证一次只读搜索：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli search --source boss --query Python --limit 1
```

如果只读搜索再次出现空白页、验证码或拒绝访问，应停止并人工检查；不要通过隐藏自动化标识、伪装浏览器或关闭安全功能继续请求。程序退出码为 0 或打开主页均不等于已确认登录。

## 已验证与未完成

本地合成页面的搜索、详情、验证码暂停、空白页暂停均已通过真实 Edge 验证。单元测试覆盖启用沙箱、窗口提前关闭、资料目录互斥及普通人工启动参数。

BOSS 真实登录、真实搜索、详情 DOM 和发送界面仍未验收。没有发送消息或投递，没有修改 Python 环境、数据库、系统安全设置或网站验证机制。
