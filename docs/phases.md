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

## Phase 12：离线实现检查点，真实平台验收待完成

新增 NowcoderAdapter、集中选择器、合成搜索/详情页面和测试。解析岗位、城市、实习天数与时长；通过原有工厂接入 CLI、API、Dashboard 和 MCP，后续过滤与匹配保持平台无关。修复 Dashboard 来源下拉框原有的 HTML 标签错误。

2026-10-05：129 项测试通过，1 项 PostgreSQL 测试因缺少专用测试库跳过；`python -m scripts.platform_smoke nowcoder` 使用真实 Edge 读取本地合成页面，搜索与详情通过。公开页面的搜索路径及详情 DOM 已核对；真实浏览器搜索触发登录或验证提示，程序按规则暂停，尚未完成线上搜索验收，没有申请或发送消息。

用户要求睡前安全停止，工作保存在本检查点，不进入 Phase 13。BOSS 登录命令已退出；关闭时浏览器报告已关闭，不能据此认定登录成功。后续事项见 [续做记录](resume.md)。

## 恢复开发后的兼容修复（2026-10-05）

浏览器提前关窗时显示可操作提示，确保驱动和会话锁释放。SQLite 自动初始化统一走 Alembic；早期直接建表且结构与 0001 完全一致的库只补记版本，不改业务数据，未知布局明确停止。135 项测试通过，1 项 PG 测试跳过；工作流重启恢复（11 岗位）、BOSS 本地浏览器验证及牛客本地搜索/详情验证通过。

BOSS 专用登录窗口已重新打开，等待本人完成登录后再进行真实只读验证。实习僧公开搜索请求返回 HTTP 403，已停止网络访问；Phase 13 暂不能进行真实页面结构验收，不伪装成已完成。

## 登录与未知结果恢复修复（2026-10-05）

显式开启 Chromium 沙箱，增加普通 Edge 人工登录入口和空白页暂停。进程检查证明 `--no-sandbox` 已移除；自动化 BOSS 主页仍在首次 HTTP 200 后跳空白，具体机制未确定。普通人工窗口没有远程调试参数，等待用户确认登录结果，详见 browser-login-diagnosis.md。

未知发送结果现在会暂停工作流，必须人工核查后记录结果；接口持有工作流锁、核对摘要并记录核查依据，不能抢占发送或替代审批。Tracker 记录分析和草稿进度，模拟发送不记为 CONTACTED。

145 项测试通过，1 项 PG 测试跳过；Dashboard、11 岗位恢复演示和带本地浏览器的 Evaluation 通过。合成样本证据幻觉仍为 0/10；真实服务和网站质量未验收。

## 程序化浏览器诊断与加载修复（2026-10-06）

用户确认同一专用资料的普通 Edge 可以搜索并查看岗位详情。关闭人工窗口后做了一次只读导航诊断：主页返回 HTTP 200，约 3.6 秒后主框架提交到空白页。站内跳转记录为脚本发起，但空白跳转没有原因记录，不能把二者混为一谈，也不能据此确定风控或浏览器故障。已停止继续访问，保留登录资料。

修复导航栏链接误判岗位、隐藏空结果模板提前结束等待以及隐藏验证模板遮住可见弹窗的问题。增加不保存 URL 或认证资料的单次导航诊断，以及延迟加载和脚本跳空白的合成回归样本。150 项测试通过，1 项 PG 测试跳过；本地浏览器读取和导航诊断通过。真实 BOSS 程序化读取仍未验收，Phase 13 未推进。

## 阶段提交

2026-10-06 Phase 10 补齐：增加独立质量门禁、阈值文件和失败报告，证据幻觉必须为零且有实际样本。174 项测试通过，1 项 PG 跳过；完整离线 Evaluation（含本地浏览器）达到当前合成基线。自定义质量门槛不能取消零幻觉检查，真实服务结果仍待配置后评估。

2026-10-06 独立功能补齐：增加简历文本/DOCX 导入、本人逐条确认技能和证据、API 原文校验及 Dashboard 表单，复用 Phase 2 的 CandidateProfile 和 Phase 7/8 入口。165 项测试通过，1 项 PG 跳过；本机 Edge 完成导入、生成资料、审批及恢复回归。没有新增依赖，也未修改现有 Python 环境。

| 阶段 | Git commit | 验收边界 |
| --- | --- | --- |
| 0、1 | a6f80a6 | 原有 88 项测试和 CLI 保留 |
| 2 | 3b346ef | 结构化分析离线通过，真实 API 待配置 |
| 3 | 86c0dc2 | BOSS 合成页面通过，真实登录与 DOM 待验收 |
| 4 | 0ff3123 | 审批和模拟执行通过，真实发送未开放 |
| 5 | a2e2b33 | 图循环、暂停和跨实例恢复通过 |
| 6 | 7b23068 | SQLite 与迁移通过，真实 PG 待验收 |
| 7 | 632a1e7 | API 与 SSE 通过 |
| 8 | 5483199 | 中文 Dashboard 离线通过 |
| 9 | ad808e5 | 真实 MCP stdio 子进程协议通过 |
| 10 | 5e39caa | 13 项指标和合成评估，不代表线上质量 |
| 11 | 0eab62b | 可靠性与部署静态检查通过，Docker 未实际启动 |
| 12 | 4f20695 | 牛客合成页面通过，真实搜索待人工验证 |
| 13 | 尚无 | 实习僧公开请求 403，尚未实现验收 |
| 兼容修复 | 4bf7f9a | 浏览器关闭、SQLite 旧表迁移 |
| 登录修复 | e850f74 | 沙箱与普通 Edge 人工登录 |
| 恢复修复 | 3fa77b2 | 未知发送结果暂停与人工核查 |
| 导航修复 | 4507a3b | 可见岗位等待与只读导航诊断 |
| 简历入口 | c46cda7 | 文本/DOCX 提取与本人证据确认 |
