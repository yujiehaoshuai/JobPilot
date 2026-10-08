# 独立验收与剩余接手事项

## 当前优先级（2026-10-08）

实习僧已完成真实岗位与 DeepSeek 匹配；牛客现也已完成本人登录后的真实只读流程。页面只保留填写资料、选择网站和搜索结果：示例填入输入框，每次搜索使用当前内容，支持每周到岗天数和实习月数。当前不推进发送与投递，BOSS 仍有浏览器兼容问题。

最新全量 252 项通过、1 项专用 PostgreSQL 跳过；Dashboard、状态流续接和离线 Evaluation 门禁通过。牛客真实读取 5 条，虚构示例排除 2 条、分析保存 3 条，0 个动作；独立数据库连接读回任务及检查点一致。真实报告在被忽略的 data/nowcoder-validation/ 中，不能当作用户本人的求职结论。

继续开发先检查 Git diff，沿用 Python 3.12 与现有 .venv。不要重复安装运行时、要求仍有效的登录重做或重建早期阶段。密钥已由用户在本机配置；API Key、简历、报告和浏览器资料不得提交 Git。

旧 `docs/resume.md` 已合并至本页；历史诊断仍在 browser-login-diagnosis.md 与 pycharm-interpreter-diagnosis.md。三个早期重复演示脚本已删除，使用下面的统一测试和完整恢复脚本。

## 本机可完成的验证

在项目根目录执行；沿用现有 Python 3.12，不重建 `.venv`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.dashboard_smoke
.\.venv\Scripts\python.exe -m scripts.recovery_smoke
.\.venv\Scripts\python.exe -m scripts.stream_smoke
.\.venv\Scripts\python.exe -m app.evaluation.runner --browser
.\.venv\Scripts\python.exe -m scripts.deployment_check
```

恢复脚本会创建临时 SQLite 数据库，启动本机 HTTP 服务，等待审批后关闭服务，再建立新实例。它模拟批准一条草稿、拒绝其余草稿，确认 11 岗位流程完成且 Tracker 没有记录真实 CONTACTED。所有资料来自虚构 fixtures，不使用个人数据库。

2026-10-06 本机结果：176 项测试通过、1 项专用 PostgreSQL 测试跳过；真实 HTTP 重启恢复、Dashboard、SSE 续接和配置预检通过，离线评估门禁通过。恢复请求已修复为先保存 QUEUED 再返回，避免客户端读到上一轮 PAUSED。SSE 正常结束后会续接；连续三次连接失败会停止并提示重新选择任务，重连只发起 GET，不重放任务或审批。

## Docker 完整验收

安装并启动 Docker 后运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.docker_smoke
```

脚本创建随机的 `jobpilot-check-...` Compose 项目，使用随机测试凭据和空 env 文件，不读取个人 `.env`，不复用现有数据卷。流程为：配置检查、构建镜像、等待健康、Mock 任务暂停、重启应用、恢复到完成、重复迁移、本地浏览器读取、离线评估。默认生产端口仍是 8000；验收自动选择空闲回环端口，Compose 通过 JOBPILOT_HTTP_PORT 配置端口。

结束时清理本次项目创建的容器与数据卷，不清理用户的 JobPilot 部署。报告和分步日志保存在 `data/deployment/<随机项目名>/`，不提交 Git。退出码 0 表示完整通过，1 表示某一步失败，2 表示本机未找到 Docker；中断或 Docker 守护进程故障时应查看报告中的清理结果，再按报告的精确项目名处理遗留资源。

本机实际检查仍为“未找到 Docker”，因此不能宣称镜像或容器已通过。浏览器沙箱不会因验收失败而被关闭。Compose 的健康等待使用官方 [`up --wait`](https://docs.docker.com/reference/cli/docker/compose/up/) 能力。

## CI 配置

`.github/workflows/verify.yml` 包含三个任务：Windows/Linux 的 Python 3.12 离线回归和浏览器检查、临时 PostgreSQL 16 的迁移/批准/跨实例检查点、独立 Compose 全流程。只保存虚构评估报告、测试报告和界面截图，不上传全部 data 或浏览器 Profile。

CI 使用 [GitHub 服务容器](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers) 创建专用 PostgreSQL 测试库；Python 版本由官方 [setup-python](https://github.com/actions/setup-python) 固定为 3.12。本地 YAML 和结构检查已通过，但仓库尚未配置远端，本次没有推送或实际运行 GitHub Actions；CI 运行结果仍待确认。

## 需要本人或外部环境接手的内容

| 项目 | 当前阻塞 | 下一步与完成依据 |
| --- | --- | --- |
| BOSS | 普通 Edge 正常，程序化访问跳空白，原因未确定 | 先解决访问兼容问题，再核对真实搜索、详情和收件人页面；见 browser-login-diagnosis.md |
| 牛客 | 5 条真实读取、3 条 AI 匹配和保存展示已通过 | 当前只读取第一页；登录失效或验证会暂停，后续再按需求扩展 |
| 实习僧 Phase 13 | 已通过公开搜索、详情、匹配保存和页面展示；曾遇到 403，可用性会变 | 默认 5 条、可设上限，每个关键词最多两页；空结果/重复页停止已验收；特殊字体不解码，跳过时展示原因，招聘有效期需人工核对 |
| 真实 LLM | DeepSeek 连接、岗位分析及现有评估门槛已通过 | 扩充真实人工标注样本，核对同义词和泛化技能等边界；不得把小样本结果当成线上准确率 |
| 真实平台发送 | 页面和收件人契约未验收 | 实现并核对平台操作后逐条 Approve，不能用 Resume 或测试审批代替本人批准 |
| PostgreSQL / Docker | 本机服务不可用 | 用专用测试库或上述隔离部署脚本完成真实验收 |
| PDF / 扫描简历 | 当前只支持正文、TXT/Markdown/DOCX | 先人工转文字；复杂排版和 OCR 质量不在已验证范围内 |

浏览器无法访问不影响简历整理、Mock 工作流、审批恢复、MCP 和离线 Evaluation；后续从独立模块继续，不反复登录或重建环境。

## 新手页面与 DeepSeek（2026-10-07）

245 项测试通过、1 项专用 PostgreSQL 跳过；Edge 页面回归包含自动连接、刷新、临时密钥保存、模拟连接测试、个人资料表单、只匹配、旧模拟审批及人工恢复。状态流断线回归通过。上述自动化回归使用临时合成密钥；后续经用户在本机配置，另行完成了下面的真实验收。

用户手动保存密钥并确认连接测试通过后，真实实习僧读取 2 条岗位、真实 DeepSeek 分析、匹配保存通过，0 个发送动作。发现模型将 Python 提取成“Python 编程基础”导致保守匹配漏项，已改进提示：技能名称简短、并列技术拆开，每项仍需原文引用。针对同一岗位复查通过，重启服务后用 1 条岗位再次完整运行，Python 匹配正确，旧两条结果可读。页面只读展示原文及匹配结果，浏览器请求全部为 GET，没有脚本错误。

真实 DeepSeek 在现有 6 条合成标签样本上通过质量门槛：提取 5/6、匹配 6/6、缺失项 5/6、证据伪造 0/10；工作流完成及恢复部分仍是 Mock 验证，不是平台发送成功率。1 条差异为模型额外提取原文中的“并发编程”，而旧标签仅列 Go；未为提高分数修改标签或放宽门槛。输入 4801、输出 732，耗时约 9.7 秒，费用未配置单价而保留未知。报告在被忽略的 data/deepseek-validation/ 中。

这些验收使用虚构候选人。尚未替用户本人生成求职结论；需要本人确认个人资料。真实发送、其他平台和部署限制仍按上表保留。

## 2026-10-08：精简表单验收

252 项测试通过，1 项专用 PostgreSQL 跳过。页面回归已改为示例填框、当前表单提交、实习时间筛选、文件读取、虚构证据拒绝和零动作结果；删除过时的高级设置及模拟审批点击步骤。后端审批和恢复仍由独立测试覆盖。新启动器会复用同一资料目录的已运行服务，用户无需查找或填写连接码。

## 2026-10-08：牛客真实只读全流程

用户完成专用 Edge 登录并关闭窗口后，先验证 2 条岗位读取，再在本机 Dashboard 填写明确虚构的 Python 经历，选择牛客、AI 分析、最多 5 条。共读取 5 条，2 条因每周要求 5 天而被示例的 4 天条件排除，其余 3 条完成 DeepSeek 分析并显示 Python 匹配项及缺失项。任务 COMPLETED，无页面脚本错误，无 PendingAction。独立连接读取业务记录和 LangGraph 检查点，3 条结果逐项一致。

复用原有 NowcoderAdapter、集中选择器和 BrowserSession，未添加绕过检测代码，没有更改平台解析逻辑。新页面开放牛客选项并说明需要已有登录、会打开专用窗口且只读取第一页。未把牛客成功推断成 BOSS 也可用。

报告：data/nowcoder-validation/ 下的 jobs.json（初始两条读取）、workflow.json、summary.json、persistence.json、dashboard-live.png，均被 Git 忽略。新增功能后全量仍为 252 通过、1 跳过，页面回归与离线质量门禁通过。发送、牛客翻页、Docker 与 PostgreSQL 实机验收仍未完成。
