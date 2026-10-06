# BOSS 登录窗口诊断（更新于 2026-10-06）

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

实际打开的普通 Edge 主进程已核对：无 `--no-sandbox`、无 `--remote-debugging-pipe`。2026-10-06 用户确认该窗口中能够正常搜索并查看岗位详情，随后确认关闭窗口。普通浏览器的登录和人工浏览已确认；程序化读取尚未验收，不需要反复重新登录。

## 2026-10-06 单次只读诊断

关闭人工窗口并释放资料锁后，程序使用原来的 `profiles/boss` 启动 Edge，只访问一次 BOSS 主页。通过浏览器调试协议观察主框架导航，不注入脚本，不修改页面响应，也不读取 Cookie。

| 相对时间 | 实际记录 |
| --- | --- |
| 281 毫秒 | 主框架提交到平台页面，主页响应 HTTP 200 |
| 562 毫秒 | 请求跳转到另一个平台页面，原因为 `scriptInitiated` |
| 1562 毫秒 | 主框架提交到平台页面 |
| 3562 毫秒 | 主框架提交到 `about:blank`，没有记录到对应的跳转请求原因 |

结论：问题发生在程序化访问场景；当前证据不能确定空白跳转由哪段脚本、网站策略或浏览器机制触发。不能把前面的站内脚本跳转当作空白跳转原因，也不能断言账号异常或平台封禁。发现空白后已暂停，没有循环重试。

报告保存在被 Git 忽略的 `data/diagnostics/boss-navigation-0ee70ad08be24beda7d6bf4366143c69.json`。报告只保留来源、时间、状态和导航类别，不保存实际 URL、查询参数、岗位编号或页面内容。

同时修复三处本地读取问题：BOSS 导航栏的 `/job_detail/` 入口不再视为岗位链接；等待实际可见的结果，避免隐藏空结果模板提前结束等待；验证检测检查所有可见匹配元素，避免第一个隐藏模板导致漏检。这些修复不等于已经解决真实空白页。

## 用户操作

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli login --source boss --manual
```

在新开的普通 Edge 中手动登录或完成验证。完成后关闭本次窗口，再在运行命令的终端按回车。浏览器资料仍留在 `profiles/boss`，不要删除或提交 Git。

以下是一次只读搜索的命令。当前已经确认程序化访问会变空白，应等访问条件或兼容问题有明确变化后再验证，不要反复运行：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli search --source boss --query Python --limit 1
```

如果只读搜索再次出现空白页、验证码或拒绝访问，应停止并人工检查；不要通过隐藏自动化标识、伪装浏览器或关闭安全功能继续请求。程序退出码为 0 或打开主页均不等于已确认登录。

需要调查导航原因时，可以手动运行一次诊断，报告默认写入 `data/diagnostics/`：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli diagnose --source boss
```

诊断观察最多八秒（主页加载另有十五秒超时），遇到空白、登录验证或拒绝访问即结束。退出码 1 表示本次未完成正常页面观察。某类导航可能没有对应的原因事件；没有记录不能当成没有发生。可参考 [Playwright CDPSession 文档](https://playwright.dev/python/docs/api/class-cdpsession)。

## 已验证与未完成

150 项测试通过，1 项因未提供专用 PostgreSQL 测试库跳过。本地合成页面的搜索、详情、延迟加载、验证码暂停、空白页暂停均已通过真实 Edge 验证；合成脚本跳空白时，诊断能够记录 `scriptInitiated`。单元测试覆盖启用沙箱、窗口提前关闭、资料目录互斥、普通人工启动参数、导航链接误判和诊断 URL 脱敏。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.browser_smoke
.\.venv\Scripts\python.exe -m scripts.navigation_smoke
```

BOSS 普通浏览器登录和人工查看详情已由用户确认；程序化真实搜索、详情 DOM 和发送界面仍未验收。没有发送消息或投递，没有修改 Python 环境、数据库、系统安全设置或网站验证机制。
