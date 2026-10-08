# 安装、运行、演示与已知限制

## 环境和安装

本机沿用 `D:\JobPilot\.venv\Scripts\python.exe`，Python 3.12。不要重建现有环境，也不要删除它依赖的 `.runtime`。PyCharm 选择该解释器，工作目录设为 `D:\JobPilot`，按模块运行入口。

仅在另一份全新工作区安装时执行：

```powershell
& 'C:\python312\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

本机浏览器默认使用已安装的 Edge，不需要重复下载浏览器。配置示例见根目录 `.env.example`；只有不存在 `.env` 时才复制：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

真实模型现在可以在页面的“连接 DeepSeek”里配置。默认使用 `deepseek-flash`、`https://api.deepseek.com` 和 Responses 接口；保存时会同时填写 `.env` 的 LLM_BASE_URL、LLM_MODEL、LLM_API_STYLE、LLM_API_KEY，保留其他配置。其他服务仍可手动配置 `chat_completions`，但必须支持严格 JSON Schema。

## 最快打开求职助手

Windows 双击 `start.cmd`，会自动打开浏览器并连接本机程序，不安装或改动环境。命令行也可以：

```powershell
.\.venv\Scripts\python.exe -m app.server --open-browser
```

1. 首次体验：点击“先用虚构资料体验一下”，然后点击“帮我找岗位”。示例会填入各个输入框，可以修改，不调用真实 AI。
2. 正式使用：在“连接 DeepSeek”中保存服务密钥、测试连接；不要把密钥发到聊天或提交 Git。
3. 在第 1 步填写姓名或昵称、简历或真实经历。每项技能选择真实程度，复制一句正文中的相关经历，再填写工作类型、每周到岗天数和实习月数。
4. 在第 2 步选择“实习僧 · 真实岗位”或已登录的“牛客 · 真实岗位”，以及“让 AI 分析”，输入关键词，先读取 5 条，直接点击“帮我找岗位”。每次都使用输入框当前的内容。
5. 在右侧查看岗位和匹配结果，展开“为什么这样匹配？查看双方原文”。结果自动保存，下次打开后点击“以前的搜索”可重新查看。

正文可直接粘贴，也可读取 TXT、Markdown、DOCX（最多 1 MB）。DOCX 只读取正文段落和表格；PDF、扫描件请先复制并核对文字。程序不推测学历、年限或熟练程度；否定句、岗位要求和别人的经历不能当作自己的经历。原始文件不保存，点击搜索后才保存本次填写的资料。

<details>
<summary>重新打开页面与开发者接口</summary>

默认监听 `http://127.0.0.1:8000`。端口占用时可用 `start.cmd --port 8001`。页面关闭或失去连接后，重新双击 `start.cmd`，启动器会识别已运行的同一份程序并打开它。不要手工填连接码。开发接口说明在 `/docs`，完整 Schema 在 `/openapi.json`，需要本机鉴权。

页面固定用于搜索和匹配，已移除旧 JSON 编辑、重复确认和模拟审批入口。学习审批流程请运行 `python -m scripts.recovery_smoke`；它使用临时虚构资料，不操作真实网站。CLI 的 CandidateProfile 文件入口仍保留。

状态不明时先人工核查，再填写依据；确认未发送会结束该动作，想重试必须重新创建并审批。停止服务再启动后可从旧记录继续，恢复任务本身不能代替批准。

</details>

## CLI 与浏览器

页面支持实习僧和已登录的牛客；BOSS 暂不显示，保留诊断入口。实习僧默认最多 5 条详情，可在页面或工作流 CLI 的 `--limit` 调整至 40 条，每个关键词最多读两页。数量上限包含不可读的详情尝试，跳过时显示原因；全部不可读则失败，验证或限流仍暂停。候选人城市、标题和到岗天数会照常过滤，零匹配时查看排除原因，不要为了得到结果而改写自己的真实条件。

```powershell
# 单独确认真实数据入口，最多读取三条详情
.\.venv\Scripts\python.exe -m app.browser_cli search --source shixiseng --query Python --limit 3
# 用自己的资料只做匹配；offline 是有限词表，配置模型后再换 live
.\.venv\Scripts\python.exe -m app.workflow_cli start --source shixiseng --query Python --candidate data/candidate.json --analysis-only --mode offline --data data/shixiseng-cli
# 查看本次已保存的真实岗位演示；候选人是虚构资料
.\.venv\Scripts\python.exe -m app.server --open-browser --data data/shixiseng-demo --port 8000
```

最后一个命令会自动打开独立演示库。点击“刷新记录”，选择已有搜索即可查看结果，无需重新抓取。

2026-10-07 本机真实验收：公开搜索取回 5 条完整岗位，虚构 Python 示例按规则排除 1 条、保留并匹配 4 条；API 任务 COMPLETED、0 个动作，重建服务实例后结果一致。这次早期验收采用离线词表；之后的真实 DeepSeek 验收见本页末尾。虚构资料不能代表用户本人的匹配结果。页面刷新时间不是发布时间，部分 JD 可能陈旧；招聘截止日期及名额应在原页核对。

```powershell
# 保留的 Phase 1 程序：20 个样本 → 13 个通过过滤 → 11 个唯一岗位
.\.venv\Scripts\python.exe -m app.main
# 新的离线结构化分析
.\.venv\Scripts\python.exe -m app.intelligence_demo --mode offline
# 启动持久工作流，保留输出里的 run_id
.\.venv\Scripts\python.exe -m app.workflow_cli start --source mock --mode offline
# 通过真实 MCP 子进程读取同一套离线岗位
.\.venv\Scripts\python.exe -m app.workflow_cli start --source mock --mode offline --transport mcp
# BOSS 普通 Edge 人工登录：本人登录，关闭窗口，再在终端按回车
.\.venv\Scripts\python.exe -m app.browser_cli login --source boss --manual
# 登录验收只读取一条岗位，不发起沟通
.\.venv\Scripts\python.exe -m app.browser_cli search --source boss --query Python --limit 1
# 牛客同样使用独立平台资料目录
.\.venv\Scripts\python.exe -m app.browser_cli login --source nowcoder --manual
```

工作流 CLI 用 `status --id RUN_ID` 或 `resume --id RUN_ID`，保持原任务的 source、mode、transport、limit 和 data 参数。未设置 AGENT_DATABASE_URL 时，CLI 使用 `data/agent/actions.db`、tracker.db、checkpoints.db；早期独立 approval_cli 默认是 `data/actions.db`，查看工作流动作必须指定 `--database data/agent/actions.db`。Dashboard 默认使用新的 `data/agent/agent.db`。不要把这几种历史入口的数据库混用。

设置 AGENT_DATABASE_URL 可使用关系后端；PostgreSQL 先运行 `python -m app.db_cli upgrade`。迁移不自动搬迁旧数据库。SQLite 旧表只有与已知 0001 布局一致才可补记版本。

## 牛客登录与只读搜索

这台机器本次已经完成登录，可以在页面直接选“牛客 · 真实岗位”。换机器或登录失效时，在项目文件夹的终端执行：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli login --source nowcoder --manual
```

在打开的普通 Edge 窗口里本人登录，手动搜索并打开一条岗位，完成可能出现的验证。关闭这次专用窗口，然后回终端按回车。之后在 JobPilot 页面搜索；若是旧任务暂停，则选择那条记录，再点“处理好问题，继续这次搜索”。不要同时运行两份牛客任务或留着登录窗口占用资料目录。

也可以单独验证读取：

```powershell
.\.venv\Scripts\python.exe -m app.browser_cli search --source nowcoder --query Python --limit 3
```

牛客目前读取每个关键词的第一页，不自动翻页。页面数量是上限，不保证满额。2026-10-08 从真实页面提交虚构 Python 资料，最多读取 5 条：2 条要求每周 5 天，被示例的 4 天条件排除；其余 3 条经过真实 DeepSeek 分析，完成技能匹配和页面展示。独立连接读回任务及 LangGraph 检查点一致，未生成任何发送动作。

## 测试和 Evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.browser_smoke
.\.venv\Scripts\python.exe -m scripts.platform_smoke nowcoder
.\.venv\Scripts\python.exe -m scripts.recovery_smoke
.\.venv\Scripts\python.exe -m scripts.dashboard_smoke
.\.venv\Scripts\python.exe -m scripts.stream_smoke
.\.venv\Scripts\python.exe -m scripts.mcp_smoke
.\.venv\Scripts\python.exe -m app.evaluation.runner --browser
```

评估输出在 `data/evaluations/latest.json`。13 项指标均保留统计范围与分母。离线合成样本中，JD 技能提取和缺失技能准确率为 4/6，技能匹配 6/6，候选人证据幻觉率 0/10。2026-10-07 的真实 DeepSeek 评估为提取 5/6、匹配 6/6、缺失项 5/6、证据伪造 0/10；输入 4801、输出 732 个模型计量单位，评估总耗时约 9.7 秒，未配置单价故不估算费用。工具选择指标衡量确定性路由，浏览器指标衡量本地合成页面，不代表真实模型或线上平台成功率。实时模型评估用 `--mode live`，会调用已配置服务并产生费用；未知用量和成本保留 null。

真实 PostgreSQL 集成测试需要专用 JOBPILOT_TEST_POSTGRES_URL；不能用生产库代替测试库。

评估现在同时执行质量门禁：默认阈值见 `fixtures/evaluation/thresholds.json`。JD 提取与缺失技能至少达到当前离线基线 4/6，技能匹配、工具分派、任务完成和恢复必须全部通过；候选人证据幻觉必须为零且分母非零。添加 `--browser` 时还要求本地浏览器检查通过。这是六个合成样本的回归门槛，不代表生产准确率目标。

可用 `--thresholds data/my-thresholds.json` 设置指标的 `min`/`max`，例如为 Latency、Token Usage（输入输出总和）、Cost 设置上限。配置成本门槛后，成本未知也会失败；不能通过自定义文件关闭零幻觉约束。报告包含 `status` 和逐项 `quality_gate.checks`；任何未达标或评估异常返回退出码 1，并写入本次失败结果，不沿用上次成功报告。人工审批率不要求趋近零，因为逐条审批是预期行为。

## Docker Compose

在已安装 Docker 的机器中，先在本机 `.env` 填写 POSTGRES_PASSWORD 与 JOBPILOT_API_TOKEN，再执行：

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 app
docker compose down
```

Compose 按 PostgreSQL 健康检查 → Alembic 迁移 → API 的顺序启动，数据使用命名卷。普通停止不要加 `-v`，否则会删除卷。默认仅映射本机 8000 端口。容器用于离线 Demo/API；人工招聘网站登录需有界面的本机环境。本机尚无 Docker，因此镜像构建、容器沙箱兼容性及真实 PostgreSQL 联调未验收，不能宣称已完成部署测试。若主机不支持浏览器沙箱，应修正运行条件，不自动关闭安全保护。

## 当前限制

独立 Docker 全流程和 CI 说明见 [验收与接手文档](verification.md)。可用 `python -m scripts.docker_smoke` 在 Docker 可用时创建隔离测试部署，避免手动混用个人数据库。此脚本仍未在本机完成容器实测。

- BOSS 普通 Edge 登录后可搜索并查看详情，已由用户确认；程序化访问仍在 HTTP 200 后跳到 about:blank。单次导航诊断未记录空白跳转原因，读取尚未验收，停止重复访问；详见 browser-login-diagnosis.md。
- 牛客已经过本人登录后的真实搜索、详情和 AI 匹配验收；仍可能因登录过期或网站验证而暂停，不保证一直可用，也没有实现自动翻页。
- 实习僧 2026-10-07 的公开读取和匹配已通过；此前出现过 403，不能保证网站持续可用。可见空结果、最多两页和重复页停止已验收；特殊字体不解码，详情不可读时明确跳过。
- 真实发送执行器仍明确暂停，必须完成收件人和页面契约验收后才可开放；逐动作批准规则不会取消。
- DeepSeek 的真实连接、少量真实岗位分析、合成质量评估和页面展示已通过。资料仍是虚构示例，用户本人结果需要本人确认资料后运行。金额以 DeepSeek 账户为准；现有样本较少，不能保证所有岗位都提取准确。
- 当前为单机单工作线程、有限队列与文件锁。暂不需要 Redis，不支持多主机同时使用同一浏览器资料。
- 日志只记录白名单字段；真实候选人资料、检查点、令牌、Cookie、浏览器 Profile 均保存在 Git 忽略范围内。

## 查看最新的真实 AI 验收结果

正常启动后，点击“刷新记录”，选择“牛客验收示例（虚构资料）”或“DeepSeek 验收示例（虚构资料）”。这条记录已完成真实岗位读取、DeepSeek 分析、Python 证据匹配和保存；查看记录只读取本机数据，不会再次付费调用模型。前一次包含两条岗位的联调记录也保留，便于对照修正前后的技能提取。

本机报告在 `data/deepseek-validation/`：`report.json` 为最初两条岗位，`extraction-recheck.json` 为技能名称修正复查，`corrected-workflow.json` 为修正后完整任务，`evaluation-live.json` 为真实模型的合成样本评估，`dashboard-live.png` 为只读页面验收截图。这些文件不提交 Git。
