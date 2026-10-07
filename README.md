# JobPilot

先把一个真实网站跑通：**实习僧岗位 → 规则筛选 → JD 分析 → 候选人证据匹配 → 保存状态 → Web 展示**。当前暂缓其他网站与发送功能，保留已有模块供以后继续。

2026-10-07 本机实测：读取 5 条真实岗位，按虚构示例条件排除 1 条，匹配并保存 4 条；重启读回和页面展示通过，没有生成发送或投递动作。**匹配目前使用离线词表，真实 LLM 尚未配置；这不是用户本人求职结论。**

## 先运行

沿用已有 Python 3.12 和 `.venv`，不要重建环境，也不要删除它依赖的 `.runtime`。

```powershell
cd D:\JobPilot
.\.venv\Scripts\python.exe -m app.server
```

打开 <http://127.0.0.1:8000>：

1. 输入本机令牌：未配置时保存在 `data/agent/api-token.txt`；配置过则使用 `.env` 的 `JOBPILOT_API_TOKEN`。
2. 导入自己的 Candidate Profile JSON，或先载入明确标注的虚构示例。也可通过页面里的正文/TXT/Markdown/DOCX 入口整理简历，技能和证据由本人确认。
3. 选择“实习僧公开岗位”、填写关键词，保留“只搜索和匹配”。首次熟悉操作也可用 Mock，全程离线。
4. 查看读取数量、排除原因、匹配技能、缺失证据和原文引用。任务与结果自动保存，可刷新或重启后查看。

真实资料保存到被忽略的 `data/candidate.json` 等本机文件，不要覆盖公开 fixtures。默认示例有城市、岗位方向及实习天数限制；搜索到岗位但全部被排除时，先看原因，不要改写真实条件来凑结果。

## 已保存的本次演示

本机已有独立演示库，可以直接查看，无需再次访问招聘网站：

```powershell
.\.venv\Scripts\python.exe -m app.server --data data/shixiseng-demo --port 8000
```

令牌来自 `data/shixiseng-demo/api-token.txt`（配置值优先）。刷新任务列表，选择实习僧任务。该目录只存在于本机，不随 Git 分发；其中 `candidate-demo.json` 明确标注虚构，`live-report.json` 保存验收结果。

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

当前 **212 项测试通过，1 项 PostgreSQL 测试因无专用测试库跳过**；本地 Dashboard 回归、真实岗位页面展示、离线 Evaluation 门禁通过。离线词表的 JD 技能集合准确率为 4/6，证据幻觉为 0/10，仅代表合成样本。配置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 后可改用 `--mode live`；Key 只放本机 `.env`。

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

- 实习僧只读第一页，默认最多 5 条详情；请求至少间隔一秒。遇到 401/403/429 或验证会暂停；不伪装浏览器、不解码保护字体。岗位是否仍在招，要去原页核对。
- BOSS 普通浏览器可用，但 Playwright 跳空白的问题未解决；扩展方案还未完成真实验收。牛客真实读取仍待验证。这两个来源在 Dashboard 暂时禁用。
- 默认只匹配，不生成草稿或动作。已有审批和模拟流程保留；真实发送执行器尚未开放，后续也必须逐条批准。
- Docker Compose 和 PostgreSQL 配置已存在，本机尚未完成真实部署验收。无需为当前单机流程引入 Redis。

[架构](docs/architecture.md) · [安装、Demo、Evaluation、Docker 命令](docs/demo.md) · [阶段与 Git 提交](docs/phases.md) · [验收及待办](docs/verification.md) · [BOSS 诊断](docs/browser-login-diagnosis.md)
