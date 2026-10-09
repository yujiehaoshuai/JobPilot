# JobPilot BOSS 岗位助手

在正常使用的 Edge/Chrome 中读取 BOSS 可见岗位，交给本机 JobPilot 自动评分。沿用已有只读实验的普通扩展 API，不需要 Playwright/CDP，也不复制登录资料。

本机有限验收已通过：早期 2 条完整岗位完成 DeepSeek 评分及详细复核；新增滚动验收连续三屏 15 → 30 → 45 个不重复岗位编号。不同关键词、账号及长期稳定性仍需继续验证。

## 第一次使用

1. 双击项目根目录的 `start.cmd`。
2. 在平时登录 BOSS 的浏览器打开 `edge://extensions` 或 `chrome://extensions`。
3. 打开开发者模式，选择“加载解压缩的扩展”，目录选 `D:\JobPilot\extensions\boss_readonly`。以前装过旧版本的，点“重新加载”。
4. 在同一个浏览器刷新 JobPilot 页面，选择 **BOSS 直聘**，点击 **连接 BOSS 助手**。不用填写连接码、模型密钥或简历。
5. 保持自动打开的助手页面不关闭。在普通 BOSS 网页中本人登录；回 JobPilot 填简历、意向，点击 **帮我找岗位**。

助手会创建搜索页和详情页，自动读取公开岗位。已读结果逐条保存；完成后原搜索任务自动进入 AI 分析。请保持本机服务、浏览器和助手页运行。连接有效期一天，过期后回主页面重新连接即可。

## 登录、验证、暂停与继续

遇到登录、验证码、人机验证、空白或页面结构异常，就停止读取。你在 BOSS 页面手动处理后，点助手里的 **已处理好，继续读取**，或回 JobPilot 选择这条历史任务并点 **处理好问题，继续这次搜索**。不会自动回答验证码，也不会不断重试网站。

刷新助手可恢复本机连接；关闭助手再打开时，从 JobPilot 重新连接。已回传的岗位和完成编号保存在本机 `data/agent/boss-bridge.db`，重新搜索时跳过这些详情。搜索页可能重新读取；不把已经确认的岗位重复入库。一个浏览器只运行一个助手面板。

## 范围和限制

- 搜索阶段只读搜索结果、公开详情，通过下一页按钮或列表滚动续页。不读取聊天、Cookie 或网站隐藏接口。
- 简历和 DeepSeek 密钥不会传给扩展；助手接收搜索条件、已读编号，以及用户已批准的岗位目标。扩展不能自行批准操作。
- 目前城市在后端严格筛选，BOSS 搜索页沿用网站当前城市条件。不同城市未被网站返回时，不会凭空补出岗位；需要在网站设置相应搜索范围。
- 默认最多尝试 100 条详情、每词最多 20 页。找不到续页控件、出现重复页或达到上限都会提示范围未覆盖，不能声称全站搜完。当前网站版本的列表滚动已有限实测，网站改版仍可能影响读取。
- 标题、公司或正文缺失的详情会跳过并提示。没有明确的截止日期就不猜测过期。
- 批量联系只执行已批准的“立即沟通”，可能发送 BOSS 默认招呼并展示在线简历；不上传附件、不发送 AI 草稿、不修改远端资料。首次真实联系待本人选定岗位批准，测试样本通过不能替代真实验收。
- 旧 CLI/MCP 的 BOSS 入口仍是 Playwright 诊断路线；日常使用新的 Dashboard 入口。

## 代码从哪里读

`helper.mjs` 接收本机任务 → `search.mjs` 控制只读循环 → `probe.mjs` 观察页面 → `collector.mjs` 读取可见字段 → `app/api/boss_bridge.py` 校验回传 → `BossExtensionAdapter` 进入原工作流。

批量联系：Dashboard 核对并批准 → `app/services/boss_contact.py` 保存不可变操作摘要 → `contact.mjs` 核对页面上的岗位、公司和按钮 → 后端发放 15 秒单次许可 → 扩展再核对并点击一次。只有原岗位显示“继续沟通/已沟通”才回报成功；否则停止队列并请用户核查。90 秒无回执转入待核查，刷新或重启不会重新点击。同一岗位按本机单账号跨任务防重。

升级助手代码后刷新助手页；扩展信息或权限修改后，在扩展管理页重新加载，再回 JobPilot 连接。升级不更改登录资料。日常使用时先在 BOSS 核对账号、默认招呼和在线简历，再到 JobPilot 勾选实际岗位并批准。

`connect.js` 只在本机首页转交一次连接，主 API 凭据不交给扩展。扩展使用权限更小的独立凭据，不能访问简历、模型设置或批准动作。`tabs` 权限用于管理助手自己的页面和 BOSS 页面；连接时只定位本扩展的助手标签，不上传其他标签页信息。站点权限限 BOSS、example.com 诊断页和本机回环地址。

选择器仍只在 `app/browser/selectors.py` 维护，修改后重新生成扩展配置：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_browser_probe
node --test tests/browser_probe/*.test.mjs
.\.venv\Scripts\python.exe -m pytest -q
```

助手页“读取遇到问题时”可以打开旧只读诊断页。它仍提供 example.com 对照、单次搜索、单条详情和报告导出，保留标签页身份及 blank 后两秒观察。诊断结果不会自动导入任务。

参考官方文档：[普通标签页 API](https://developer.chrome.com/docs/extensions/reference/api/tabs)、[隔离环境中的页面读取](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)、[扩展访问本机服务](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)。原路线参考[公开对照实验](https://github.com/openai/codex/issues/35700)，没有复制第三方自动投递脚本或加入反检测代码。
