# 代码导读：先看实习僧搜索与匹配

当前先完成一个网站，阅读时沿下面的主线走。Mock、fixtures 和测试用于验证行为；审批、MCP、PostgreSQL、Docker 等扩展模块可以后读，不需要一开始全部理解。

| 顺序 | 文件 | 要弄明白的问题 |
| --- | --- | --- |
| 1 | app/models/job.py、candidate.py | 一个岗位和一份候选人资料包含什么？ |
| 2 | app/adapters/shixiseng.py、http_reader.py | 怎样从公开页面拿到可靠文本？ |
| 3 | app/browser/selectors.py | 页面结构改变时改哪里？ |
| 4 | app/services/normalization_service.py、filter_service.py、deduplication_service.py | 为什么有些岗位被排除或合并？ |
| 5 | app/services/analysis_service.py、matching_service.py、app/llm/offline.py | 要求如何提取，匹配凭什么有依据？ |
| 6 | app/workflow/graph.py | 跟随 analysis_only 的 discover → analyze → advance → finish 分支。 |
| 7 | app/api/worker.py、server.py、app/web/app.js | 任务怎样存下来，页面怎样显示结果？ |

先运行 README 的实习僧只匹配示例，再读 tests/integration/test_analysis_only.py，对照一次完整的数据流。没有 API Key 时仍能理解流程，但离线词表不能替代真正的模型。

已删去三个重复的早期演示脚本，以及过时的续做文档；现在以 README、demo.md、verification.md 为入口。下面的完整目录和扩展模块默认折叠，按需展开。

<details>
<summary>完整源码目录（不含本地环境、真实数据和浏览器资料）</summary>

```text
JobPilot/
├── .github/
│   └── workflows/
│       └── verify.yml
├── app/
│   ├── adapters/
│   │   ├── mock/
│   │   │   ├── __init__.py
│   │   │   └── adapter.py
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── boss.py
│   │   ├── browser_adapter.py
│   │   ├── factory.py
│   │   ├── http_reader.py
│   │   ├── nowcoder.py
│   │   └── shixiseng.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── worker.py
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── diagnostics.py
│   │   ├── manual_login.py
│   │   ├── selectors.py
│   │   └── session.py
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── gates.py
│   │   ├── metrics.py
│   │   └── runner.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── client.py
│   │   └── offline.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── action.py
│   │   ├── analysis.py
│   │   ├── application.py
│   │   ├── base.py
│   │   ├── candidate.py
│   │   ├── job.py
│   │   └── resume.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── action_service.py
│   │   ├── analysis_service.py
│   │   ├── deduplication_service.py
│   │   ├── filter_service.py
│   │   ├── greeting_service.py
│   │   ├── matching_service.py
│   │   ├── normalization_service.py
│   │   └── resume_service.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── actions.py
│   │   ├── relational.py
│   │   └── tracker.py
│   ├── tools/
│   │   ├── __init__.py
│   │   └── jobs.py
│   ├── web/
│   │   ├── api.html
│   │   ├── app.js
│   │   ├── index.html
│   │   ├── resume.js
│   │   └── style.css
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   └── runtime.py
│   ├── __init__.py
│   ├── approval_cli.py
│   ├── browser_cli.py
│   ├── config.py
│   ├── db_cli.py
│   ├── enums.py
│   ├── exceptions.py
│   ├── intelligence_demo.py
│   ├── logging_config.py
│   ├── main.py
│   ├── mcp_client.py
│   ├── mcp_server.py
│   ├── observability.py
│   ├── reliability.py
│   ├── runtime_config.py
│   ├── server.py
│   └── workflow_cli.py
├── docs/
│   ├── architecture.md
│   ├── browser-login-diagnosis.md
│   ├── demo.md
│   ├── file-guide.md
│   ├── phase-0-1-report.md
│   ├── phases.md
│   ├── pycharm-interpreter-diagnosis.md
│   └── verification.md
├── extensions/
│   └── boss_readonly/
│       ├── background.js
│       ├── collector.mjs
│       ├── core.mjs
│       ├── manifest.json
│       ├── panel.css
│       ├── panel.html
│       ├── panel.mjs
│       ├── probe.mjs
│       ├── README.md
│       └── selectors.json
├── fixtures/
│   ├── browser/
│   │   ├── boss_detail.html
│   │   ├── boss_search.html
│   │   ├── boss_search_delayed.html
│   │   ├── nowcoder_detail.html
│   │   ├── nowcoder_search.html
│   │   ├── shixiseng_detail.html
│   │   └── shixiseng_search.html
│   ├── evaluation/
│   │   ├── gold.json
│   │   └── thresholds.json
│   ├── jobs/
│   │   ├── 01_agent_engineer.json
│   │   ├── 02_llm_application.json
│   │   ├── 03_ai_backend.json
│   │   ├── 04_rag.json
│   │   ├── 05_chinese_llm.json
│   │   ├── 06_agent_tools.json
│   │   ├── 07_rag_platform.json
│   │   ├── 08_llm_engineering.json
│   │   ├── 09_agent_workflow.json
│   │   ├── 10_llm_backend.json
│   │   ├── 11_rag_engineer.json
│   │   ├── 12_agent_id_duplicate.json
│   │   ├── 13_llm_url_duplicate.json
│   │   ├── 14_frontend.json
│   │   ├── 15_frontend.json
│   │   ├── 16_testing.json
│   │   ├── 17_testing.json
│   │   ├── 18_cv_algorithm.json
│   │   ├── 19_cv_algorithm.json
│   │   └── 20_sales.json
│   └── candidate.example.json
├── migrations/
│   ├── versions/
│   │   └── 0001_agent_state.py
│   └── env.py
├── scripts/
│   ├── browser_smoke.py
│   ├── build_browser_probe.py
│   ├── dashboard_smoke.py
│   ├── deployment_check.py
│   ├── docker_smoke.py
│   ├── lifecycle_smoke.py
│   ├── mcp_smoke.py
│   ├── navigation_smoke.py
│   ├── platform_smoke.py
│   ├── recovery_smoke.py
│   ├── stream_smoke.py
│   └── system_smoke.py
├── tests/
│   ├── browser_probe/
│   │   └── probe.test.mjs
│   ├── integration/
│   │   ├── test_agent_graph.py
│   │   ├── test_analysis_only.py
│   │   ├── test_http_api.py
│   │   ├── test_mcp_protocol.py
│   │   ├── test_relational_storage.py
│   │   ├── test_resume_api.py
│   │   ├── test_system_recovery.py
│   │   └── test_workflow.py
│   ├── unit/
│   │   ├── test_approval.py
│   │   ├── test_browser_adapter.py
│   │   ├── test_browser_diagnostics.py
│   │   ├── test_browser_probe_contract.py
│   │   ├── test_browser_session.py
│   │   ├── test_config.py
│   │   ├── test_deduplication.py
│   │   ├── test_evaluation_gates.py
│   │   ├── test_evaluation_metrics.py
│   │   ├── test_filter.py
│   │   ├── test_intelligence.py
│   │   ├── test_manual_login.py
│   │   ├── test_mock_adapter.py
│   │   ├── test_models.py
│   │   ├── test_nowcoder_adapter.py
│   │   ├── test_reliability.py
│   │   ├── test_resume.py
│   │   ├── test_shixiseng_adapter.py
│   │   ├── test_storage.py
│   │   └── test_worker_queue.py
│   └── conftest.py
├── .gitattributes
├── .dockerignore
├── .env.example
├── .gitignore
├── .python-version
├── alembic.ini
├── compose.yaml
├── Dockerfile
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements.lock.txt
├── start.cmd
└── requirements.txt
```

</details>

<details>
<summary>扩展模块职责与完整学习路线</summary>

## 主要文件职责

| 入口或模块 | 阅读时关注什么 |
| --- | --- |
| app/main.py | 原 Phase 1 可见流水线，理解一次搜索的输入和输出 |
| app/models | Pydantic 模型、候选人证据、岗位、动作快照与用量 |
| app/services/filter_service.py | 确定性筛选规则与拒绝原因 |
| app/services/analysis_service.py | 结构化 JD 和原文引用校验 |
| app/services/matching_service.py | 明确技能匹配、部分具备与缺失证据 |
| app/services/greeting_service.py | 用真实证据编号组织草稿 |
| app/services/resume_service.py、app/web/resume.js | 简历正文提取、人工确认和逐字引用校验 |
| app/services/action_service.py | 批准消费、未知结果和人工核查 |
| app/adapters | 平台差异留在数据入口，Mock 保留离线能力 |
| app/browser | 集中选择器、可信 URL、沙箱、资料锁与人工登录 |
| app/workflow/graph.py | State、节点、条件边、循环、Interrupt |
| app/workflow/runtime.py | 资源生命周期、Checkpointer 和执行器注入 |
| app/storage | SQLite 兼容入口和新的关系存储 |
| migrations | 固定迁移版本，避免修改模型后旧迁移随之变化 |
| app/api | HTTP 鉴权、单工作线程、状态持久化与 SSE |
| app/web | 无前端构建工具的中文工作台 |
| app/tools、app/mcp_client.py、app/mcp_server.py | 对比进程内函数分派与 MCP 协议传输 |
| app/evaluation | 合成金标数据、指标范围、恢复场景和用量统计 |
| app/evaluation/gates.py | 零幻觉门禁、有效分母和可配置质量阈值 |
| scripts/recovery_smoke.py、scripts/docker_smoke.py | 真实 HTTP 重启恢复和隔离部署验收 |
| scripts | 可单独运行的关键功能演示，不是生产入口 |

## 推荐学习顺序

1. 跑 `app.main`，对照 `main.py`、CandidateProfile 和 JobPosting 看数据如何流动。
2. 读 MockJobAdapter、fixtures 和对应测试，理解输入校验及可重复 Demo。
3. 读 normalization、filter、deduplication，区分确定性规则和语义分析。
4. 读 SQLiteTracker，理解主键、唯一约束、事务、状态迁移和幂等导入。
5. 读 analysis 模型、LLMClient 和 OfflineLLMClient，理解结构化输出与测试替身。
6. 读匹配及草稿服务，追踪一句候选人陈述怎样找到原文证据。
7. 读 PendingAction、ActionStore 和 ApprovalService，先理解审批边界再看执行。
8. 读 graph.py 与 test_agent_graph.py，逐步画出暂停、恢复和按岗位循环的位置。
9. 读 relational.py、Alembic、worker.py、FastAPI，再用 Dashboard 观察持久状态。
10. 最后读浏览器、MCP、Evaluation 和部署文件，思考这些机制分别解决什么真实问题。


</details>

## 最值得面试讲解的 10 个技术点

1. **平台解耦**：多个 Adapter 输出统一 JobPosting，过滤、匹配与图无需包含招聘站点分支。
2. **结构化输出仍要验真**：Pydantic 检查结构，原文引用检查事实来源，两者各管一层。
3. **候选人证据约束**：模型选择已有编号，程序引用原文，避免把学习中技能或未知经历写成事实。
4. **确定性逻辑的边界**：过滤、去重和状态机使用普通 Python，减少成本并提高可测试性。
5. **审批绑定快照**：完整 payload 的摘要绑定候选人、目标、正文，旧页面不能批准新内容。
6. **至少一次恢复与至多一次发送的冲突**：图可以重放，但批准只能原子领取；未知发送结果必须人工核查，不能宣称网络操作天然 exactly-once。
7. **Checkpoint 与业务状态分离**：图保存执行位置，关系表保存岗位、审批和申请事实，两者都需要一致的任务身份。
8. **普通工具与 MCP 的区别**：一个是本进程方法分派，一个增加握手、序列化和进程传输；协议不自动带来权限隔离。
9. **评估分母与范围**：金标样本、工具路由、合成页面和真实网站不能混成一个成功率；无数据时保留未知。
10. **按规模选择可靠性机制**：单机文件锁、有限线程、令牌桶和日志轮转先满足当前需求；需要跨主机队列时才考虑 Redis。

讲解时要主动说明真实模型、平台发送和 Docker 尚未验收，不能把设计能力或离线测试包装成生产结果。
