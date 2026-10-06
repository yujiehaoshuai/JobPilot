# JobPilot

JobPilot 的最终目标是一个有状态的 AI 求职助手：基于候选人的真实资料发现岗位、解释匹配依据、准备沟通内容，并在用户批准后执行招聘平台操作。

**当前已实现 Phase 0–12 的主要离线流程与平台读取接口；Phase 13 未完成。真实模型、招聘平台操作和容器部署仍有验收缺口。默认运行离线。**

最新验证（2026-10-06）：174 项测试通过，1 项 PostgreSQL 测试因未配置专用测试库跳过；简历导入、Dashboard 回归和离线 Evaluation 质量门禁通过。真实发送仍由保护执行器暂停，不能将离线演示当成已完成真实投递。

BOSS：用户确认普通 Edge 可以搜索并查看岗位详情；程序化访问仍在 HTTP 200 后跳到空白页，具体触发机制未确定，已停止继续访问。登录资料保留，无需反复登录。

完整入口：[启动与 Demo](docs/demo.md) · [当前架构](docs/architecture.md) · [目录树与学习路线](docs/file-guide.md) · [阶段验收和提交](docs/phases.md) · [BOSS 登录诊断](docs/browser-login-diagnosis.md) · [续做记录](docs/resume.md)。

原 Phase 1 CLI 仍可独立运行：读取候选人资料与 20 个虚构岗位，执行规则过滤、去重，将通过筛选的岗位和申请记录保存到 SQLite。新工作流在此基础上增加分析、证据匹配、草稿、审批、检查点及 Web 工作台。默认资料全部虚构，通过规则过滤不等于适合投递。

## 已实现与阶段边界

- Python **3.12**、配置、标准库 logging、类型标注和 docstring。
- Pydantic 模型：CandidateProfile、CandidateSkill、JobPosting、FilterResult、Application，以及共享枚举。
- 只读 JobSourceAdapter、MockJobAdapter 和 20 个 JSON 岗位。
- 城市、岗位标题、排除词、空 JD、用工类型、实习时长及到岗天数的确定性过滤。
- 岗位标准化，按 `source + source_job_id` 和规范 URL 去重。
- SQLite 持久化、重复导入、申请状态管理和需要明确确认的本地状态修改。
- CLI 与离线单元、集成测试。

后续模块已加入结构化 JD 分析、证据匹配、沟通草稿、BOSS/牛客只读 Adapter、审批队列、LangGraph、FastAPI、Dashboard、MCP、Evaluation、SQLAlchemy/Alembic 和部署配置。外部发送接口尚未通过平台验收，不开放真实自动发送。

## Python 与安装

项目要求 `3.12.x`，在 `pyproject.toml`、`.python-version` 和 CLI 启动检查中均有声明。运行依赖见 requirements.txt，已验证的锁定版本见 requirements.lock.txt。现有环境直接使用，不需要重复安装。

当前工作区的 `.venv` 已准备好，版本为 Python 3.12.10，直接使用即可，**无需再安装 Python 或重建环境**：

```powershell
cd D:\JobPilot
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest -q
```

需要在另一份干净工作区新建环境时，优先使用电脑上已有的 Python 3.12。例如本机已有 `C:\python312\python.exe`：

```powershell
& 'C:\python312\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

只运行程序可以安装 `requirements.txt`。上面的命令明确指定解释器，不需要激活虚拟环境；如果希望使用文档中的简写，可先执行：

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
python -m pytest -q
```

如果 PowerShell 不允许激活脚本，继续使用 `.\.venv\Scripts\python.exe` 即可。

当前 `.venv` 基于上次已配置的项目内 `.runtime\python312\tools\python.exe`。两者都被 Git 忽略，均保留原状。不要单独移动或删除解释器目录，否则该虚拟环境会失效。本项目当前按源码目录运行，尚未做可分发的安装包。

## 配置

没有 `.env` 也可以运行。需要覆盖默认值时，将 `.env.example` 复制为 `.env`，填写以下变量：

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///data/jobpilot.db` | 持久化 SQLite 文件；不支持其他数据库或内存 URL |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `CANDIDATE_PROFILE_PATH` | `fixtures/candidate.example.json` | UTF-8 候选人配置 |
| `MOCK_JOBS_PATH` | `fixtures/jobs` | 一文件一岗位的 JSON 目录 |

读取优先级：进程环境变量 > `.env` > 默认值；空值使用默认值。配置中的相对路径基于项目根目录，CLI 路径参数基于当前终端目录。Windows 绝对数据库路径可写作 `sqlite:///D:/JobPilot/data/custom.db`。

真实候选人资料请保存在被忽略的 `data/` 中，例如 `data/candidate.json`；不要用真实资料替换已公开的示例。API Key 只写入本机 `.env`。

## 运行与本地跟踪

```powershell
# 默认离线演示，重复运行可保留记录
.\.venv\Scripts\python.exe -m app.main

# 自定义候选人、Mock 数据目录和数据库
.\.venv\Scripts\python.exe -m app.main --candidate data/candidate.json --jobs fixtures/jobs --database data/custom.db

# 查看申请记录，获得具体 APPLICATION_ID
.\.venv\Scripts\python.exe -m app.main --list-applications

# 明确确认后才修改本地记录；把 APPLICATION_ID 换成列表里的实际 ID
.\.venv\Scripts\python.exe -m app.main --set-status APPLICATION_ID SHORTLISTED --confirm

# 所有参数
.\.venv\Scripts\python.exe -m app.main --help
```

缺少 `--confirm` 会拒绝修改。状态转移还必须符合 [SQLiteTracker 中的允许列表](app/storage/tracker.py)。记录 `CONTACTED` 等状态只是人工维护本地记录，不会发消息。搜索自动新增 `NEW` 记录属于系统记账，不表示已投递。重复搜索不会重置状态或覆盖备注。

成功退出码为 0；配置、数据、状态或数据库失败为 1；命令行参数错误为 2。CLI 展示写入 stdout，运行日志写入 stderr，重定向输出使用 UTF-8。

## 示例输出

首次运行空数据库的主要输出如下，实际还会逐条显示拒绝原因和最终岗位：

```text
JobPilot | Phase 0 + Phase 1 | MOCK ONLY
当前不会连接真实招聘网站。内置示例候选人与岗位均为虚构。
Candidate: 演示候选人（虚构资料）
Loading jobs from MockJobAdapter...
Jobs loaded: 20
Rejected jobs: 7
Remaining: 13
Duplicates removed: 2
Final: 11
Saving jobs...
New jobs saved: 11
Applications tracked: 11
Done.
```

7 个拒绝岗位为 2 个前端、2 个测试、2 个 CV、1 个销售。一个岗位可能命中多个拒绝原因，因此原因计数总和可以大于 7。再次运行，`New jobs saved` 为 **0**，申请数仍是 **11**。当前工作区已跑过演示，所以默认数据库会显示第二次运行的结果。

## 原 Phase 1 CLI 数据流

```text
main.py
  ├─ load_settings → load_candidate → CandidateProfile
  ├─ JobSourceAdapter → MockJobAdapter → JobPosting × 20
  ├─ normalize_job → RuleFilter → JobPosting × 13
  ├─ deduplicate_jobs → JobPosting × 11
  └─ SQLiteTracker
       ├─ candidates：资料快照
       ├─ jobs：唯一岗位及 JSON 内容
       └─ applications：候选人 + 岗位 + 状态
```

使用 Pydantic 是为了在读取 JSON 时尽早发现字段错误；Adapter 统一数据入口；过滤与去重使用普通 Python；SQLite 使用唯一约束、外键和事务保护持久状态。CLI 明确编排这些步骤，便于从上到下阅读。具体设计取舍与限制见 [架构说明](docs/architecture.md)。

## 原 Phase 1 目录概览

```text
JobPilot/
├─ app/
│  ├─ main.py / config.py / logging_config.py / enums.py / exceptions.py
│  ├─ models/         # 候选人、岗位、申请模型
│  ├─ adapters/       # 统一只读接口和 Mock 实现
│  ├─ services/       # 标准化、过滤、去重
│  └─ storage/        # SQLiteTracker
├─ fixtures/
│  ├─ candidate.example.json
│  └─ jobs/           # 20 个虚构岗位
├─ tests/
│  ├─ unit/
│  └─ integration/
├─ docs/
├─ .env.example / .gitignore / .python-version
├─ pyproject.toml
├─ requirements.txt / requirements-dev.txt
└─ README.md
```

[当前完整源码目录树与主要文件作用](docs/file-guide.md)；[Phase 0、1 历史验收](docs/phase-0-1-report.md)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

默认测试在临时目录建库，覆盖领域模型、过滤、去重、存储、审批、恢复、HTTP、MCP 和评估，不连接招聘网站。真实 PostgreSQL 测试仅在配置专用测试库后启用。浏览器关键演示单独运行 scripts 下的 smoke 命令，使用真实 Edge 和本地合成页面。

## 推荐先读的 5 个文件

1. [app/main.py](app/main.py)：先看 `run_search`，掌握每一步输入输出。
2. [app/models/candidate.py](app/models/candidate.py)：理解资料、技能证据和约束。
3. [app/models/job.py](app/models/job.py)：理解平台统一的数据结构。
4. [app/adapters/mock/adapter.py](app/adapters/mock/adapter.py)：看 JSON 如何变成模型。
5. [app/services/filter_service.py](app/services/filter_service.py)：看普通函数如何给出可解释的筛选结果。

之后读 `deduplication_service.py` 和 `storage/tracker.py`，理解去重、唯一约束与事务。

## 已知限制与 Roadmap

规则与候选人技能匹配采用保守的显式核对，未知信息不能当成已满足。薪资保留原文。原 Phase 1 SQLite 保持兼容，新 Agent 后端使用 Alembic。系统面向单机学习与 Demo，不宣称多租户或多主机高可用。真实平台、模型和容器的待验收事项见续做记录。

阶段顺序保留，各阶段的实现和验收边界见 docs/phases.md；以下为阶段职责：

| Phase | 计划 |
| --- | --- |
| 2 | LLM Client、结构化 JobAnalysis/MatchResult/GreetingDraft、真实证据约束 |
| 3 | BOSS 只读 Adapter、持久浏览器登录、人工处理验证 |
| 4 | PendingAction、批准/拒绝、批准后的外部动作 |
| 5 | 成熟工作流迁移 LangGraph、暂停与恢复 |
| 6 | PostgreSQL、迁移、Checkpoint 持久化 |
| 7–8 | FastAPI 与简洁 Dashboard |
| 9–10 | 部分工具的 MCP 封装、Evaluation Pipeline |
| 11 | 按实际需要加入部署、队列、限流与可观测性 |
| 12–13 | 牛客、实习僧 Adapter，验证平台解耦 |

## Phase 2：结构化分析与证据约束

原命令 `python -m app.main` 保持兼容。新命令：

```powershell
.\.venv\Scripts\python.exe -m app.intelligence_demo --mode offline
# 配好本机 .env 后才运行真实模型；不会自动降级成离线结果。
.\.venv\Scripts\python.exe -m app.intelligence_demo --mode live
```

真实模式读取 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY，接口需支持 Chat Completions 的严格 JSON Schema 输出。协议依据：[官方 Structured Outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs)。模型名称由用户选择，项目不硬编码价格或自动切换供应商。

JobAnalyzer 核对 JD 技能引用；CandidateMatcher 按资料中明确的技能保守匹配，学习中的技能只算部分具备。GreetingGenerator 让模型选择最多三个证据编号，再由程序引用用户原文形成草稿，避免自由生成虚假的项目或熟练程度。非结构化简历中的隐含技能暂不自动判定，需用户补充到 CandidateProfile.skills。

离线客户端是有限词表的演示替身，不代表真实 LLM 质量。API 密钥与真实服务尚需用户配置后验证。
