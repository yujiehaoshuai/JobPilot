# BOSS 登录窗口诊断（更新于 2026-10-07）

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

旧版报告保存在被 Git 忽略的 `data/diagnostics/boss-navigation-0ee70ad08be24beda7d6bf4366143c69.json`。它只保留来源、时间、状态和导航类别，缺少页面编号和完整生命周期，不能据此还原多个页面创建、关闭的先后关系。下面的第二版诊断补充这些证据；旧报告的时间线不代表第二版已完成真实网站验证。

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

需要调查导航原因时，先关闭占用 `profiles/boss` 的项目专用 Edge 窗口，再依次运行两次诊断。每次等待命令结束后再运行下一条：

```powershell
cd D:\JobPilot
.\.venv\Scripts\python.exe -m app.browser_cli diagnose --source boss --url https://example.com
.\.venv\Scripts\python.exe -m app.browser_cli diagnose --source boss
```

两条命令使用相同的 Edge、Playwright、持久资料目录和启动参数，只改变本次访问地址。`--url` 只用于 `diagnose`，接收无账号密码的 HTTPS 地址，端口为默认值或 443；它不改变 Adapter 的域名限制。每次报告使用不同文件名，写入 `D:\JobPilot\data\diagnostics\boss-navigation-<编号>.json`，终端也会打印完整 JSON 和路径。

正常加载后观察八秒，加载本身另有十五秒超时。首次发现空白后，继续旁观至少两秒：不点击、不重试导航、不读取 DOM、不修改页面，只接收事件及读取 CDP 生命周期元数据。窗口关闭不会自动结束其他页面的观察；如果整个 context 或 browser 已关闭，报告会明确标记两秒观察未完成。登录验证或拒绝访问仍触发暂停。退出码 1 表示本次出现异常或暂停，仍应查看已生成的报告。

## 第二版诊断字段和事件

实现位于 `app/browser/diagnostics.py`，命令入口位于 `app/browser_cli.py`。本次不修改 BrowserSession、Adapter、selector 或浏览器启动参数。

- 每个 Playwright `Page` 对象分配固定的本地编号，例如 `page-1`、`page-2`。编号仅在本次报告内有效；多个页面即使 URL 相同，也不会合并。
- 每条事件包含 `page_id`、`current_url`、`target_url`、`kind`、`elapsed_ms`、`is_main_frame` 和 `pages`。`pages` 保存事件发生时 `context.pages` 中每个页面的编号、URL 和关闭状态。浏览器级事件没有所属页面时使用 `null`，无法确定主框架身份时也使用 `null`。
- Playwright 记录 `page.existing`、`page.created`、`page.close`、`page.crash`、`page.framenavigated`、`page.frameattached`、`page.framedetached`、`context.close`、`browser.disconnected`。
- CDP 记录 `Page.frameRequestedNavigation`、`Page.frameNavigated`、`Page.frameAttached`、`Page.frameDetached`、`Target.targetCreated`、`Target.targetDestroyed`、`Target.targetInfoChanged`。`cdp_capabilities` 表明各个页面和浏览器是否启用成功；不支持时仍保留 Playwright 事件。
- `diagnostic.goto`、`diagnostic.target_bound`、`diagnostic.blank_observed`、`diagnostic.finished` 说明诊断动作和边界；操作失败时还记录对应的 `diagnostic.*_error`，不保存可能包含敏感内容的异常全文。
- `first_blank` 指明首次空白涉及的页面和事件；启动时原本存在的空白页不会直接判为故障。`blank_grace` 保存要求的两秒、实际观察时长及是否完成。`known_pages` 保留所有登记过的页面，包括已关闭页面；`final_pages` 是结束时仍在 context 中的页面。

Target 通知可能先于 Playwright 的新页面通知。代码用 `Target.getTargetInfo` 取得真实对应关系后补齐 `page_id`，并用 `page_id_known_at_event` 标明当时是否已知；不会拿相同 URL 猜对应关系。若短命页面在建立关联前就被销毁，Target 事件仍保留 `target_id`，但 `page_id` 可能为 `null`。当时的 URL 和页面快照不会用后来的状态补写。

`current_url` 是事件回调当时 Playwright 缓存的页面 URL，CDP 的 `target_url` 可能更早反映导航。URL 保存协议、主机和路径，移除查询参数、片段、账号密码；其他协议隐藏内容。路径本身仍可能包含岗位编号等信息，报告不读取 Cookie、页面正文或截图，也不提交 Git。每份报告最多保存 500 条事件，超过后由 `dropped_events` 计数，因此缺少事件不能证明它没有发生。

`diagnostic.finished` 是观测边界。随后解除监听和 CDP 会话，再由原来的 Session 清理浏览器，所以 `caller_cleanup_included=false`；诊断主动结束后的正常关闭不会被误判为现场故障。可参考 [Playwright CDPSession 文档](https://playwright.dev/python/docs/api/class-cdpsession) 和 [BrowserContext 事件文档](https://playwright.dev/python/docs/api/class-browsercontext)。

判断时先看页面编号，再看事件先后：同一 `page_id` 的主框架跳到空白，与新 `page_id` 出现空白，是两种不同现象。若普通网页也空白，可优先调查 Edge、Playwright、资料目录；若普通网页稳定而 BOSS 异常，可缩小到 BOSS 页面加载后的行为，但两种结果都不能单独证明具体根因。

## 已验证与未完成

第二版诊断更新后，189 项测试通过，1 项因未提供专用 PostgreSQL 测试库跳过。两个本地合成场景通过真实 Edge 验证：原页面脚本跳空白后观察两秒；主页面正常、另建空白窗口并关闭，同时移除子框架。后者能记录两个不同编号、弹窗关闭、frame detach 和 Target 创建/销毁。测试使用临时资料目录，所有网页响应由本地提供，不访问真实招聘网站。

新增单元测试覆盖 URL 参数校验、两个命令的启动设置一致、页面 crash/close、context/browser 关闭、CDP 不可用时保留事件、清理后不再记录事件。已有的搜索、详情、延迟加载、验证码暂停等离线验证继续保留。第二版刚完成时，真实网站对照尚未执行；后来读取的用户报告见下方 2026-10-07 记录。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.browser_smoke
.\.venv\Scripts\python.exe -m scripts.navigation_smoke
.\.venv\Scripts\python.exe -m scripts.lifecycle_smoke
```

BOSS 普通浏览器登录和人工查看详情已由用户确认；程序化真实搜索、详情 DOM 和发送界面仍未验收。没有发送消息或投递，没有修改 Python 环境、数据库、系统安全设置或网站验证机制。

## 2026-10-07 普通浏览器扩展实验

已读取用户在 2026-10-06 晚间生成的第二版报告：`boss-navigation-2efbf0bf728f431e80d78eb0ef8fc660.json` 和 `boss-navigation-e71f113f43c74d18a160fadb3b3930cb.json` 中 example.com 均为 `page_observed`；`boss-navigation-72d7881f758e421baba76d35407a9306.json` 中同一 `page-1` 主框架在 3640ms 变为 `about:blank`，未记录到新页面、关闭或 crash。这支持继续调查控制路径差异，不等于确定了某一段网站脚本就是根因。

新增独立实验目录 `extensions/boss_readonly`，通过普通扩展 API 导航，在 `ISOLATED` 环境读取公开岗位 DOM。它不连接 CDP、不改变现有 Adapter、不调用 LLM，也不包含发送消息、投递或修改远端资料的逻辑。选择器由现有 `app/browser/selectors.py` 导出。

加载和实验步骤见 [扩展说明](../extensions/boss_readonly/README.md)。本阶段验证 example.com 对照、BOSS 首页、单次搜索和单条详情；自动翻页及本地后端接入尚未实现。

离线事件与读取测试通过，不等于真实扩展已在 BOSS 验收。本轮电脑操作工具因无法可靠识别 Windows 上当前浏览器 URL，停止了界面控制；没有改走其他控制通道，也没有安装扩展或操作 BOSS。扩展需要用户在普通浏览器中手动加载，再生成真实页面报告。
