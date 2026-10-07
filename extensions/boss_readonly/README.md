# JobPilot 普通浏览器只读实验

这是独立的 Manifest V3 扩展，不依赖 Playwright、CDP、油猴、Node 构建工具或第三方脚本。不改变现有 BOSS Adapter。本阶段验证浏览器读取路径，不代表已经实现完整扩展桥接。

## 加载

1. 在正常使用的 Edge 或 Chrome 中打开扩展管理页：`edge://extensions` 或 `chrome://extensions`。
2. 由你打开“开发者模式”，选择“加载解压缩的扩展”，目录选 `D:\JobPilot\extensions\boss_readonly`。
3. 点击工具栏的扩展图标“JobPilot 只读采集实验”，会打开独立面板。
4. 使用普通浏览器里已有的 BOSS 登录状态。此前项目专用 `profiles/boss` 与普通浏览器的用户资料可能不同；如果当前浏览器未登录，需要你手动登录，扩展不复制 Cookie。

不需要重装 Python 或下载浏览器。不要用 Playwright 启动本次浏览器，不要接入 CDP，不要同时启用其他会投递或发消息的脚本。

## 实验顺序

1. 点击“打开 example.com 并观察”，等待约 12 秒，回到面板导出 JSON。
2. 点击“打开 BOSS 首页并观察”，等待并导出。页面稳定不代表已经登录。
3. 如出现登录或验证码，在网页中手动完成；回面板刷新列表，选择页面，点击“读取并观察，不导航”。
4. 输入关键词，点击“搜索并读取岗位”。成功时结果包含 `listings`。
5. 点击“打开首个岗位并读取”。只有标题、公司、JD 都存在时，结果才包含可交给 `JobPosting` 校验的 `jobs`；否则记录缺失，不伪造。

每次主动导航都新开标签页，通过 `chrome.tabs.update` 访问一次。读取使用 `chrome.scripting.executeScript` 的 `ISOLATED` 环境。面板必须保持打开；关闭或刷新面板会停止观察并丢失本次内存结果。生成的 JSON 默认保存到浏览器下载目录。后端尚未接入，文件不会自动导入数据库。

## 怎么判断结果

- `page_observed`：本次观察期间能读取页面，不保证账户、搜索、详情或长期运行已经全部验收。
- `blank`：曾访问非空白页面，随后该标签页变空白；继续观察至少两秒。
- `manual_verification_required`：需要你本人处理登录或验证，扩展不重试。
- `tab_closed` / `tab_replaced` / `tab_discarded`：分别对应关闭、替换和浏览器丢弃页面，不能一律称作 crash。
- `page_not_ready` / `observation_error`：加载或读取未完成，不当成“零岗位”。

记录标签页编号、脱敏 URL、状态和读取时间。扩展 API 没有等价于 Playwright 所有 frame/crash 事件的能力，本报告不猜测根因。原有 Playwright 诊断仍保留。

## 范围与资料处理

没有发消息、投递、修改简历、请求网站隐藏接口或上传服务端的代码。API Key 和候选人简历不需要填入扩展。遇到验证就暂停。不修改浏览器指纹、页面计时器或原生函数。

`tabs` 权限用于读取被选标签页的 URL 和生命周期；代码只查询 BOSS/example.com，事件也只记录本次选中标签页。`scripting` 的站点权限仅限 manifest 列出的三个域名。没有 debugger、cookies、历史记录、后台远程命令或外部脚本权限。

报告移除 URL 的查询参数和片段，包含公开岗位正文；不要提交个人诊断报告到 Git。原始详情链接可能含本次导航所需参数，只保留在面板内存中，不写入导出的 JSON。面板不保存整个页面正文、用户聊天或浏览器登录资料。

## 开发和验证

选择器由现有 `app/browser/selectors.py` 导出，修改它后运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_browser_probe
node --test tests/browser_probe/*.test.mjs
.\.venv\Scripts\python.exe -m pytest -q
```

当前仅验证单次搜索页和单条详情的读取，不实现自动翻页。现有平台选择器仍需要真实页面验收；可见 DOM 中没有详情链接时会返回空列表，不转向隐藏接口。后续只有本机验证通过，才接入带认证的本地后端接口及原有业务流程。

参考浏览器 API：[Tabs](https://developer.chrome.com/docs/extensions/reference/api/tabs)、[Scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting)。路线依据：[公开对照实验](https://github.com/openai/codex/issues/35700)，它并非本项目真实网站验证结果。所有实现为本项目编写，未复制第三方自动投递脚本。
