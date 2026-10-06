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

真实模型需要 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY，服务必须支持严格 JSON Schema。API Key 仅写本机文件。离线演示不需要密钥。

## 最快启动 Dashboard

```powershell
.\.venv\Scripts\python.exe -m app.server
```

打开 `http://127.0.0.1:8000`。页面令牌使用 `.env` 中的 JOBPILOT_API_TOKEN；未配置时，由服务生成到 `data/agent/api-token.txt`，仅在自己的本机页面输入。接口说明位于 `/docs`，完整 Schema 位于 `/openapi.json`。

1. 填入访问令牌，点击“载入虚构示例”；真实资料应从自己的 Candidate Profile JSON 导入。
2. 选择 Mock 与 offline，填写 Python 查询，开始搜索与分析。
3. 查看通过规则过滤的岗位、匹配项、学习中技能、缺失证据和风险。
4. 展开 JD 引用和候选人原文，核对草稿全文与审批摘要。
5. 拒绝一条草稿，观察流程继续到下一岗位；批准一条模拟草稿，观察模拟回执。两者都不向招聘方发送消息。
6. 停止服务再启动，刷新任务列表，选择原任务并恢复；Resume 本身不能代替 Approve。
7. 对 EXECUTING/UNCERTAIN 结果，先在平台人工核对再填写依据。确认未发送会结束该动作；想重试须创建新任务并重新审批。

也可展开“从简历原文整理资料”，导入 UTF-8 TXT、Markdown 或 DOCX（最多 1 MB），或直接粘贴正文。填写姓名和目标条件，添加技能名称、真实程度和逐字原文证据，核对后勾选确认，点击“生成新资料 JSON”。程序检查引用确实存在且包含完整技能名称；不从简历自动推断熟练程度、学历或年限。生成后核对上方 JSON，再开始任务。不要把否定句、岗位要求或别人的经历当作自己的技能。

上传原始文件仅在内存处理；生成资料不会自动建任务，开始任务后才持久化确认的 CandidateProfile。DOCX 只读取正文段落和表格，不读取图片、页眉页脚和批注；PDF、扫描件和旧版 .doc 暂需手动复制或转换文字。未知信息保留未知，示例经历不可当作真实经历使用。

## CLI 与浏览器

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

工作流 CLI 用 `status --id RUN_ID` 或 `resume --id RUN_ID`，保持原任务的 source、mode、transport 和 data 参数。未设置 AGENT_DATABASE_URL 时，CLI 使用 `data/agent/actions.db`、tracker.db、checkpoints.db；早期独立 approval_cli 默认是 `data/actions.db`，查看工作流动作必须指定 `--database data/agent/actions.db`。Dashboard 默认使用新的 `data/agent/agent.db`。不要把这几种历史入口的数据库混用。

设置 AGENT_DATABASE_URL 可使用关系后端；PostgreSQL 先运行 `python -m app.db_cli upgrade`。迁移不自动搬迁旧数据库。SQLite 旧表只有与已知 0001 布局一致才可补记版本。

## 测试和 Evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.browser_smoke
.\.venv\Scripts\python.exe -m scripts.platform_smoke nowcoder
.\.venv\Scripts\python.exe -m scripts.workflow_smoke
.\.venv\Scripts\python.exe -m scripts.recovery_smoke
.\.venv\Scripts\python.exe -m scripts.dashboard_smoke
.\.venv\Scripts\python.exe -m scripts.stream_smoke
.\.venv\Scripts\python.exe -m scripts.mcp_smoke
.\.venv\Scripts\python.exe -m app.evaluation.runner --browser
```

评估输出在 `data/evaluations/latest.json`。13 项指标均保留统计范围与分母。当前合成样本中，JD 技能提取和缺失技能准确率为 4/6，技能匹配 6/6，候选人证据幻觉率 0/10。工具选择指标衡量确定性路由，浏览器指标衡量本地合成页面，不代表真实模型或线上平台成功率。实时模型评估用 `--mode live`，会调用已配置服务并产生费用；未知用量和成本保留 null。

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
- 牛客真实搜索要求登录或验证，本地 fixtures 验证不等于线上成功。
- 实习僧公开请求返回 403，已停止访问；Phase 13 尚未实现并验收。
- 真实发送执行器仍明确暂停，必须完成收件人和页面契约验收后才可开放；逐动作批准规则不会取消。
- LLM 配置未提供；真实供应商兼容性、质量、延迟和费用尚未验证。
- 当前为单机单工作线程、有限队列与文件锁。暂不需要 Redis，不支持多主机同时使用同一浏览器资料。
- 日志只记录白名单字段；真实候选人资料、检查点、令牌、Cookie、浏览器 Profile 均保存在 Git 忽略范围内。
