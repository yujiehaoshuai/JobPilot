# Phase 0 + Phase 1 续做与验收记录

## 续做前检查

目录已包含数据模型、配置、日志、CLI、Mock Adapter、20 个模拟岗位、筛选/标准化/去重、SQLiteTracker 和单元测试。现有 **72 项测试通过**；默认 CLI 已能跑通 20 → 13 → 11。缺少 README、架构/交付说明、配置单元测试和端到端测试。

目录没有 `.git`，未重建或覆盖已有实现。已有 `.venv` 是 Python **3.12.10**；本次继续使用，没有新增下载、重装或切换到其他解释器。

## 本次新增的文件

| 文件 | 内容 |
| --- | --- |
| `README.md` | 当前阶段、安装与已有环境用法、命令、配置、输出、测试、阅读顺序、路线图 |
| `docs/architecture.md` | 模型、Adapter、规则、去重、SQLite 和人工确认的设计理由 |
| `docs/file-guide.md` | 完整源码目录树及每个文件职责 |
| `docs/phase-0-1-report.md` | 本次续做范围与验收报告 |
| `app/services/__init__.py` | 明确声明业务服务包 |
| `tests/unit/test_config.py` | 配置默认值、环境优先级、空值、路径、非法配置测试 |
| `tests/integration/test_workflow.py` | 实际子进程 CLI、重复运行、状态确认、中文输出、错误及 URL 别名回归测试 |

## 本次修改的文件

| 文件 | 修改与原因 |
| --- | --- |
| `app/main.py` | 修复 Windows 重定向中文编码；候选人文件无法读取时给出路径和异常类型；补充明确的岗位列表类型与工具日志；使用存储层解析已存在岗位 ID，保留跨次导入的申请进度 |
| `app/storage/tracker.py` | 在事务中同时按平台身份/规范 URL 找到已有岗位；加入 resolve_job_id；URL 相同但编号改变时沿用原身份与状态 |
| `tests/unit/test_storage.py` | “不同平台同编号应独立”测试改用不同平台 URL，使其准确覆盖平台编号隔离，而不与 URL 去重规则冲突 |

运行产生的 `data/jobpilot.db` 是被忽略的本地演示数据，不属于源码；测试数据库使用临时目录。既有环境、候选人示例及 20 个岗位文件均保持原状。

## 验收命令与预期

从项目根目录执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest -q
```

版本为 `Python 3.12.10`。默认演示为：加载 20、拒绝 7、剩余 13、去重 2、最终 11；首次空库新增 11，再次运行新增 0；申请记录始终为 11。

2026-09-28 最终验收：**88 passed in 4.10s**；`python -m pip check` 返回 `No broken requirements found.`。测试环境使用 Pydantic 2.13.5、python-dotenv 1.2.3、pytest 9.1.1。相对于续做前增加 16 项通过的测试。

已验证的关键行为：

- 用户未确认时状态修改失败，数据库状态不变。
- 确认修改后重新启动 CLI，状态与记录 ID 保留。
- 同一 URL 使用不同平台编号分两次导入，不会为已忽略岗位另建 NEW 申请。
- 错误的候选人输入不泄露资料正文，也不创建数据库；错误岗位批次不保存部分记录。
- UTF-8 中文输出在 Windows 子进程管道中可正常解码。

## 当前数据流与设计理由

`main.py → CandidateProfile → MockJobAdapter → JobPosting → normalize_job → RuleFilter → deduplicate_jobs → SQLiteTracker`。

模型校验输入，Adapter 隔离来源，服务只处理统一领域模型，SQLite 持久保存候选人和岗位之间的进展。这些都是普通 Python 调用，不需要先引入 Agent 框架。详细解释见 architecture.md；推荐优先阅读的 5 个文件与后续顺序见 README。

## 未完成项与停止边界

Phase 0 + Phase 1 所要求的功能已完成，验收通过后停止。没有开始 Phase 2。

后续未实现的功能：LLM Client、结构化 JD 分析、候选人语义匹配、GreetingDraft、BOSS 浏览器、外部动作批准/执行、LangGraph、Checkpoint、API、Web UI、PostgreSQL、MCP、Redis、Docker 及其他平台。下一阶段只计划实现 Phase 2 的结构化分析、基于真实证据的匹配和沟通草稿，须等待用户的新指令。

当前限制：规则是字面匹配；缺失字段按未知保留；薪资未解析；数据库暂无迁移；URL 查重是小规模扫描且不保存完整别名历史。没有真实网站验证，也不宣称具备求职发送能力。目录尚未初始化 Git，未创建提交。
