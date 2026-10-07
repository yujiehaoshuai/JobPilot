# JobPilot

先把一个真实网站跑通：**实习僧岗位 → 规则筛选 → JD 分析 → 候选人证据匹配 → 保存状态 → Web 展示**。当前暂缓其他网站与发送功能，保留已有模块供以后继续。

2026-10-07 已跑通 **真实实习僧岗位 → DeepSeek 分析 → 技能匹配 → 保存结果 → 页面查看**。最初读取 2 条岗位完成真实 AI 分析；修正技能名称提取后，再用 1 条真实岗位完整复验通过。重启后旧结果仍可读，发送和投递动作均为 0。**验收使用明确标注的虚构资料，不是用户本人求职结论。**

## 怎么使用

Windows 双击项目文件夹里的 **start.cmd**，浏览器会自动打开并连接程序。不要关闭启动窗口；用完后按 Ctrl+C 停止。

第一次可以点击 **“先用虚构资料体验一下” → “帮我找岗位”**。这会使用示例资料和示例岗位，不调用 AI，不花模型费用，也不发送消息。

正式使用只需下面几步：

1. **连接 DeepSeek**：在页面左上方打开 DeepSeek 开放平台，创建并复制“API Key”（服务密钥），粘贴到页面，点击“保存密钥”，再点击“测试连接”。不用手填模型名或接口地址，不要把密钥发到聊天里。
2. **告诉程序你会什么**：填写姓名或昵称，粘贴简历或真实经历，也可读取 Word（.docx）或文本文件。每项技能选择真实程度，并从正文复制一句相关经历。核对后点击“确认使用这份资料”。
3. **搜索与比较**：输入岗位关键词，选择“实习僧 · 真实岗位”和“让 AI 分析”，先读 5 条，再点击“帮我找岗位”。在右侧查看匹配项、资料中未提到的要求以及双方原文。

密钥只保存在本机 `.env`。保存设置不调用 AI；测试连接与分析岗位会从你的 DeepSeek 账户计费。当前主流程仅把岗位说明交给 AI，确认的个人资料在本机比较。没有配置时不会把基础演示冒充成 AI 分析。

结果与确认的资料会随任务保存在本机，之后点击“以前的搜索”即可查看；原始简历文件不保存。资料没有提到某项技能，不等于你一定不会，可以核对后补充真实经历。

<details>
<summary>命令行启动、连接设置和旧版资料导入</summary>

沿用 Python 3.12 与已有 `.venv`，不要删除它依赖的 `.runtime`。

```powershell
cd D:\JobPilot
.\.venv\Scripts\python.exe -m app.server --open-browser
```

浏览器没有自动打开时，可以访问 `http://127.0.0.1:8000`，在“高级设置”中手动连接：默认本机连接码位于 `data/agent/api-token.txt`；如果填写过 `JOBPILOT_API_TOKEN` 则使用配置值。连接码与 DeepSeek 服务密钥是两回事。

旧版 Candidate Profile JSON 的导入和原始编辑框保留在“高级设置”，普通使用不需要。刷新页面会保留当前页面会话的本机连接；换浏览器需重新从启动器打开或手动连接。

</details>

## 已保存的本次演示

默认启动后，在“以前的搜索”中点击 **“DeepSeek 验收示例（虚构资料）”**，即可查看已保存的真实 AI 结果，不会再次调用模型。原来的离线分析演示仍保留在独立目录：

```powershell
.\.venv\Scripts\python.exe -m app.server --open-browser --data data/shixiseng-demo --port 8000
```

程序会自动打开页面。点击“刷新记录”，选择实习僧任务。该目录只存在于本机，不随 Git 分发；其中 `candidate-demo.json` 明确标注虚构，`live-report.json` 保存验收结果。

端口被占用时使用 `start.cmd --port 8001`；查看已保存的演示可用 `start.cmd --data data/shixiseng-demo`。

## 命令行与测试

```powershell
# 只验证真实岗位读取，最多三条详情
.\.venv\Scripts\python.exe -m app.browser_cli search --source shixiseng --query Python --limit 3
# 用自己的资料搜索、筛选和匹配
.\.venv\Scripts\python.exe -m app.workflow_cli start --source shixiseng --query Python --candidate data/candidate.json --analysis-only --mode offline --data data/shixiseng-cli
# 离线回归与质量门禁，不连接招聘网站
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.evaluation.runner
```

当前 **245 项测试通过，1 项 PostgreSQL 测试因无专用测试库跳过**；本地 Dashboard 回归、真实岗位页面展示、离线 Evaluation 门禁通过。离线词表的 JD 技能集合准确率为 4/6，证据幻觉为 0/10，仅代表合成样本。在页面保存 DeepSeek 设置后，命令行也可使用 `--mode live`。DeepSeek 的真实连接、岗位分析和 6 条合成样本评估已通过现有门槛：提取 5/6、技能匹配 6/6、缺失项 5/6，证据伪造 0/10。样本很小，不代表所有岗位的准确率。

新增真实验收：尝试读取 21 条详情，得到 20 条有效岗位，1 条特殊字体岗位明确跳过；第二页与空搜索结果均通过。页面可选 5/10/20/40 条，CLI 使用 `--limit`。

原 Phase 1 教学入口仍为 `python -m app.main`。CLI 和 Dashboard 的历史数据库入口不同，使用方法见 [Demo](docs/demo.md)，不要手工混用数据库。

## 先读哪些代码

按下面一条主线阅读，不必一开始就看全部工程：

1. `app/models/job.py`、`candidate.py`：岗位和候选人的统一格式。
2. `app/adapters/shixiseng.py`、`http_reader.py`：从真实页面取得岗位。
3. `app/services/filter_service.py`：按明确条件筛选。
4. `app/services/analysis_service.py`、`matching_service.py`：提取要求、核对证据。
5. `app/workflow/graph.py`：顺着 `analysis_only` 分支看整个流程。
6. `app/api/worker.py`、`server.py` 和 `app/web/`：后台运行及页面展示。

需要时再读审批、MCP、PostgreSQL 和部署模块。完整树与面试讲解要点见 [代码导读](docs/file-guide.md)。

## 当前边界

- 实习僧默认最多 5 条详情，每个关键词最多两页，请求至少间隔一秒。数量上限包含不可读的详情尝试；个别特殊字体岗位会跳过并说明原因，全部不可读则报错。遇到 401/403/429 或验证会暂停；不伪装浏览器、不解码保护字体。岗位是否仍在招，要去原页核对。
- BOSS 普通浏览器可用，但 Playwright 跳空白的问题未解决；扩展方案还未完成真实验收。牛客真实读取仍待验证。这两个来源暂不显示在普通页面中。
- 模型提取仍可能漏项或与人工标注不一致；技能名称采用保守比较，同义词不会自动视为相同。
- 默认只匹配，不生成草稿或动作。已有审批和模拟流程保留；真实发送执行器尚未开放，后续也必须逐条批准。
- Docker Compose 和 PostgreSQL 配置已存在，本机尚未完成真实部署验收。无需为当前单机流程引入 Redis。

[架构](docs/architecture.md) · [安装、Demo、Evaluation、Docker 命令](docs/demo.md) · [阶段与 Git 提交](docs/phases.md) · [验收及待办](docs/verification.md) · [BOSS 诊断](docs/browser-login-diagnosis.md)

## DeepSeek 接入说明（开发时阅读）

默认使用 `deepseek-flash` 与 Responses 接口，输出仍由 Pydantic 校验。岗位引用必须真实出现在原文；候选人技能匹配仍使用本机确定性逻辑，不让模型编造经历。其他支持严格结构化输出的兼容服务仍可使用原 Chat Completions 接口。

接口依据：[DeepSeek Responses 文档](https://api-docs.deepseek.com/api/create-response/)；当前模型名依据：[官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)。供应商可能调整接口或模型，真实兼容性以本机连接测试与真实岗位验收为准。
