# 分阶段实施与验收

Phase 0 + 1 基线：原有 88 项测试通过，原 CLI 为 20 → 13 → 11。已初始化 Git，保留原代码与环境。

## Phase 2

新增 LLMClient、OpenAI 兼容 JSON Schema 客户端、离线替身、JobAnalysis、MatchResult、GreetingPlan 和 GreetingDraft。增加 JD 引用验证和候选人原文证据约束。

检查命令：`python -m pytest -q`；关键功能：`python -m app.intelligence_demo --mode offline`。

验收：97 项测试通过；离线分析演示完成，11 个岗位均经过证据检查。

真实模型需要用户在 .env 配置服务与密钥，目前尚未联网验收。匹配采用保守的显式技能核对；同义词和简历隐含技能不会被自动当成既有经验。

## Phase 3

新增 Playwright 持久会话、BOSS 搜索和详情 Adapter、集中选择器、可信平台 URL 校验与人工验证暂停。运行 `python -m app.browser_cli login` 人工登录；`python -m app.browser_cli search --query Python` 只读搜索。

103 项测试通过；`python -m scripts.browser_smoke` 使用 Edge 和本地虚构 HTML 响应验证读取与验证码暂停。没有下载其他浏览器。平台真实 DOM、登录与风控行为尚需本人登录验收；选择器失效会明确报错，不伪装成空结果。持久会话依据 [Playwright 文档](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)。

## Phase 4

实现完整快照摘要、PendingAction、批准/拒绝、事务领取、模拟执行和回执。`python -m app.approval_cli list` 查看；approve/reject 需要 --id 和看到的 --digest。发送超时保留 UNCERTAIN，不能自动重发；EXECUTING 表示执行中或进程中断待人工核查。

109 项测试通过；`python -m scripts.approval_smoke` 完成临时库审批演示。真实网站发送接口尚未在已登录页面验收，暂不开放真实自动发送；审批和工作流可以独立完成离线演示。

## Phase 5

实现 AgentState、读取/分析/草稿/审批/执行节点、条件边、逐岗位循环、Interrupt、Resume 和 SQLite Checkpoint。原 Phase 1 CLI 与测试保持不变。Resume 不等于 Approve；模型失败保留失败节点，浏览器验证需要人工恢复。

113 项测试通过，覆盖重新创建图后的恢复、拒绝/批准循环、验证暂停和模型错误恢复。`python -m scripts.workflow_smoke` 完成 11 岗位的离线流程。真实来源发送暂停在尚未验收的界面契约处。

使用 `python -m app.workflow_cli start` 启动，记下 run_id；`status --id RUN_ID` 查看，`resume --id RUN_ID` 恢复。对应审批数据库默认是 `data/agent/actions.db`。设计依据：[LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## Phase 6

新增 SQLAlchemy 关系存储、独立 Agent 表、Alembic 0001 和 PostgreSQL Checkpoint。`AGENT_DATABASE_URL` 指定新后端；`python -m app.db_cli upgrade` 显式升级。旧 SQLite 文件不删除、不自动搬迁。迁移定义固定，不从未来可能改变的模型动态生成。

117 项测试通过，1 项真实 PostgreSQL 测试因未提供服务跳过；本机未找到 docker/psql。SQLite 迁移重复执行、关系存储、原子审批及图恢复已验收；`python -m scripts.workflow_smoke` 再次通过。真实 PG 测试命令：配置专用测试库 `JOBPILOT_TEST_POSTGRES_URL` 后运行 `python -m pytest tests/integration/test_relational_storage.py -q`。

## Phase 7

新增 FastAPI、持久任务索引、单工作线程、候选人输入、状态查询、逐动作审批和 SSE 快照流。接口需要本机令牌，校验 Host/Origin，不提供跨域授权。重启后由用户恢复任务，不自动重放未知发送。

120 项测试通过，1 项 PG 测试跳过；`python -m scripts.api_smoke` 完成 HTTP → 工作线程 → 审批暂停 → SSE。启动命令 `python -m app.server`，默认 127.0.0.1:8000；接口文档 `/docs`，令牌在 `.env` 或 `data/agent/api-token.txt`。

## Phase 8

新增无需前端构建工具的中文 Dashboard：导入 JSON、虚构示例、来源/模型选择、任务记录、恢复、技能证据、全文草稿和逐条批准/拒绝。页面用 textContent 显示外部资料，令牌不写入网页或浏览器持久存储。

120 项测试通过，1 项 PG 测试跳过；`python -m scripts.dashboard_smoke` 在本机 Edge 完成载入、搜索、证据展示、拒绝、模拟批准，控制台无页面错误。人工查看 `data/dashboard-smoke.png`，布局和中文可读。该截图和浏览器测试均使用虚构数据。

## Phase 9

新增普通 JobTools 分派器、Pydantic 工具参数、官方 MCP v1 SDK stdio Server/Client。两条路径都使用相同 Adapter；MCP 增加握手、结构化结果和子进程传输，不替代工作流，也不提供权限隔离沙箱。只暴露 search_jobs/get_job_detail，不开放发送、任意脚本或任意 URL。

122 项测试通过，1 项 PG 测试跳过；真实子进程协议测试返回与普通调用相同岗位。`python -m scripts.mcp_smoke` 验证图通过 MCP 读取岗位并停在人工审批。CLI 增加 `--transport mcp`，API 接受 `transport: mcp`。本阶段安装 SDK 1.30.0，明确限定 `<2`，避免混用 v2 接口。

## Phase 10

实现 13 项指标、人工标注的六个虚构 JD 样本、独立评分器、故障注入恢复场景和本地浏览器评估。未知 Token/成本保留 null；单价由本机配置，不硬编码供应商价格。修复跨检查点恢复时用量累计被覆盖的问题。

125 项测试通过，1 项 PG 测试跳过；`python -m app.evaluation.runner --browser` 生成 `data/evaluations/latest.json`。本次离线 JD 技能提取与缺失技能准确率均为 4/6，匹配为 6/6，候选人证据幻觉为 0/10。词表外 Go 和否定句揭示了离线替身的局限；这些结果不代表真实模型或线上平台质量。工具指标是确定性路由准确率，浏览器指标来自本地合成页面。完整任务和恢复场景各通过 1/1，人工审批为 11/11，是安全流程的预期行为。

## Phase 11

新增 Python 3.12 Dockerfile、Compose 数据库健康检查与迁移顺序、依赖锁定、日志字段白名单及轮转、进程内指标、单机任务互斥、浏览器 Profile 互斥、API 令牌桶、导航间隔和有限模型重试。同步图放在受限工作线程，SSE 使用异步等待；外部发送不使用重试。当前单机工作台无需 Redis；不宣称支持多主机横向扩容。

128 项测试通过，1 项 PG 测试跳过；真实 Edge Dashboard 回归、部署静态预检和 pip check 通过。严格 CSP 保留，浏览器测试改用 DOM 断言；接口文档不依赖外部 CDN。本机仍没有 Docker，镜像构建、容器启动和真实 PostgreSQL 联调未验收。Compose 需在 .env 设置 POSTGRES_PASSWORD 和 JOBPILOT_API_TOKEN；运行 `docker compose up --build -d`，不用删除任何现有数据库。
