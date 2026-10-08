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

1. 体验：点“先用虚构资料体验一下”，再点“帮我找岗位”，无需密钥。
2. 正式使用：在左侧底部“连接 DeepSeek”保存一次密钥并测试；已经设置的无需重复填写。
3. 粘贴简历全文，只填一次岗位意向；选填城市和到岗时间，选择实习僧、牛客或 BOSS。
4. 点击“帮我找岗位”，AI 自动提炼简历、扩展搜索词、读取岗位、比较评分，对前 5 名再次复核。
5. 查看右侧原文依据、分数、时间差距和详细理由；其余岗位可展开。点击以前的搜索只读取本地结果，不再次调用模型。

正文支持 TXT、Markdown、DOCX（文件最多 1 MB，AI 正文最多三万字）。PDF、扫描件请先转成文字。真实模式将正文发给本机已配置的模型服务；原始文件不保存，但正文作为任务输入保存在本地数据库和检查点，便于恢复。不要把这份本机数据提交 Git。

城市和已知招聘截止条件用于淘汰；到岗天数和实习时长只影响分数并显示差距。岗位标题无需逐字匹配。AI 提炼的技能、项目和经历必须逐字引用原文；用户仍应核对提炼语义，不能把输入材料中别人的经历当作本人事实。

<details>
<summary>重新打开页面与开发者接口</summary>

默认监听 `http://127.0.0.1:8000`。端口占用时可用 `start.cmd --port 8001`。页面关闭或失去连接后，重新双击 `start.cmd`，启动器会识别已运行的同一份程序并打开它。不要手工填连接码。开发接口说明在 `/docs`，完整 Schema 在 `/openapi.json`，需要本机鉴权。

页面固定用于搜索和匹配，已移除旧 JSON 编辑、重复确认和模拟审批入口。学习审批流程请运行 `python -m scripts.recovery_smoke`；它使用临时虚构资料，不操作真实网站。CLI 的 CandidateProfile 文件入口仍保留。

状态不明时先人工核查，再填写依据；确认未发送会结束该动作，想重试必须重新创建并审批。停止服务再启动后可从旧记录继续，恢复任务本身不能代替批准。

</details>

## CLI 与浏览器

新页面使用 `/api/search`：每次默认最多尝试 100 条详情，每个词最多 20 页；API 可设置 1–200 条。逐页交替搜索最多三个关键词，重复页、末页和上限都有覆盖记录，不能把有限搜索当作全站数据。明确 404/410 的详情跳过，验证或限流暂停；文字全部不可读仍失败。

以下旧 CLI 保留 Phase 0/1 的严格规则，不提供新页面的简历提炼和排名。旧 workflow CLI 的数量上限仍为 40；底层只读 Adapter 和 MCP 支持至 200。新功能用页面或 `/api/search`，不要以旧 CLI 的筛选行为推断新页面。

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
# 以下 BOSS 命令仅保留旧 Playwright 诊断；新日常搜索使用页面中的浏览器助手
.\.venv\Scripts\python.exe -m app.browser_cli login --source boss --manual
# 旧控制路径可能再次 blank，不能用它验收新扩展
.\.venv\Scripts\python.exe -m app.browser_cli search --source boss --query Python --limit 1
# 牛客同样使用独立平台资料目录
.\.venv\Scripts\python.exe -m app.browser_cli login --source nowcoder --manual
```

工作流 CLI 用 `status --id RUN_ID` 或 `resume --id RUN_ID`，保持原任务的 source、mode、transport、limit 和 data 参数。未设置 AGENT_DATABASE_URL 时，CLI 使用 `data/agent/actions.db`、tracker.db、checkpoints.db；早期独立 approval_cli 默认是 `data/actions.db`，查看工作流动作必须指定 `--database data/agent/actions.db`。Dashboard 默认使用新的 `data/agent/agent.db`。不要把这几种历史入口的数据库混用。

设置 AGENT_DATABASE_URL 可使用关系后端；PostgreSQL 先运行 `python -m app.db_cli upgrade`。迁移不自动搬迁旧数据库。SQLite 旧表只有与已知 0001 布局一致才可补记版本。

## BOSS 普通浏览器助手

按 [助手说明](../extensions/boss_readonly/README.md) 加载或更新扩展，再在 JobPilot 选 BOSS，点击“连接 BOSS 助手”。不需要关闭正常浏览器或切换专用资料目录；使用当前普通浏览器的登录状态，保持助手页打开。搜索词来自 AI 提炼，读取完成后自动恢复匹配。

遇到登录或验证由本人处理，再点助手中的继续。页面刷新和服务重启不会删除已回传岗位；模型失败从原检查点恢复，不重新分析简历。默认 100 条详情，每词最多 20 页；重复页、找不到下一页或达到上限均明确标记未覆盖。城市由后端严格筛选，网站搜索范围仍取决于 BOSS 当前城市条件。

这条桥接只接入本机 Dashboard/API 的普通工具调用，不改变已有 MCP 协议，不把它称为 MCP。真实发消息和投递尚未启用。

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

牛客通过页面的“下一页”按钮翻页，并等待页码和岗位列表更新，最多 20 页/关键词；直接重载带 page 的地址曾返回重复首屏，不再作为动态页面翻页依据。真实第二页已核对，有限搜索的结果和 AI 分析也已验收；网站可能因登录过期或验证而暂停。历史记录中“每周 4 天排除要求 5 天”的任务使用的是旧策略，新页面现在保留时间差距并扣分。

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
- 牛客已经过本人登录后的真实搜索、详情和 AI 匹配验收；仍可能因登录过期或网站验证而暂停，不保证一直可用，翻页仍受明确数量和页数上限约束。
- 实习僧 2026-10-07 的公开读取和匹配已通过；此前出现过 403，不能保证网站持续可用。可见空结果、公开分页和重复页停止已有回归；特殊字体不解码，详情不可读时明确跳过。
- 真实发送执行器仍明确暂停，必须完成收件人和页面契约验收后才可开放；逐动作批准规则不会取消。
- DeepSeek 的真实连接、少量真实岗位分析、合成质量评估和页面展示已通过。资料仍是虚构示例，用户本人结果需要本人确认资料后运行。金额以 DeepSeek 账户为准；现有样本较少，不能保证所有岗位都提取准确。
- 当前为单机单工作线程、有限队列与文件锁。暂不需要 Redis，不支持多主机同时使用同一浏览器资料。
- 日志只记录白名单字段；真实候选人资料、检查点、令牌、Cookie、浏览器 Profile 均保存在 Git 忽略范围内。

## 查看最新的真实 AI 验收结果

正常启动后，点击“刷新记录”，选择“牛客验收示例（虚构资料）”或“DeepSeek 验收示例（虚构资料）”。这条记录已完成真实岗位读取、DeepSeek 分析、Python 证据匹配和保存；查看记录只读取本机数据，不会再次付费调用模型。前一次包含两条岗位的联调记录也保留，便于对照修正前后的技能提取。

本机报告在 `data/deepseek-validation/`：`report.json` 为最初两条岗位，`extraction-recheck.json` 为技能名称修正复查，`corrected-workflow.json` 为修正后完整任务，`evaluation-live.json` 为真实模型的合成样本评估，`dashboard-live.png` 为只读页面验收截图。这些文件不提交 Git。

新版真实排名验收：在“以前的搜索”选择“排序验收同学”。虚构简历每周 3 天、上海，要求 4/5 天的两条岗位仍被保留，完成 89/41.2 分排序与详细复核。报告位于 data/ranking-validation/。额外真实翻页验收读取两页 21 条不重复岗位，达到数量上限后明确提示还有未覆盖结果。
