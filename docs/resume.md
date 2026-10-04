# JobPilot 续做记录

更新时间：2026-10-05。用户要求选择安全节点停止，今晚不再继续开发。

## 当前检查点

- Phase 0、1 原有结构和测试保留；Phase 2–11 已分别提交。
- Phase 12 的牛客只读 Adapter、统一入口、合成页面与测试已实现。本检查点保存这些改动，真实网站验收仍待完成。
- 最新全量测试：129 通过，1 跳过（没有专用 PostgreSQL 测试库）。牛客本地浏览器搜索/详情验证通过。
- 真实牛客搜索检测到登录或验证界面，已暂停；不绕过验证。BOSS 登录命令已退出，浏览器报告已关闭，登录是否成功尚未确认。
- 没有发送真实消息、投递或修改远端数据。项目环境、数据库、Git 历史和浏览器资料未删除。

## 下次从这里继续

1. 先读本文件、`docs/phases.md` 和 Git 状态，检查已有改动，不重做 Phase 0、1。沿用 `.venv\Scripts\python.exe`，不要重新安装 Python 或重建环境。
2. 完成 Phase 12 的人工登录后只读验收；遇到验证继续暂停，不能把本地合成页面成功当作线上成功。确认阶段稳定后再进入 Phase 13。
3. 实现 ShixisengAdapter，保持集中选择器、统一岗位模型、离线 fixtures、测试和阶段提交。公开搜索入口为 `https://www.shixiseng.com/interns?k=Python`；曾观察到部分字段出现字体混淆字符，需核对真实 DOM，不能绕过平台防护或猜造字段。
4. 补齐端到端验收缺口：真实 OpenAI 兼容模型（用户稍后配置本机 `.env`）、BOSS 登录后的只读解析，以及获得逐动作批准后的平台操作实现。当前真实执行器会暂停，不能宣称已支持真实发送。
5. 验证真实 PostgreSQL、Docker 镜像构建与 Compose 启动；当前仅完成 SQLite、迁移相关测试和部署静态预检，本机未找到 Docker/psql。
6. 汇总更新 README、Architecture、完整目录树、安装/启动/测试/Evaluation/Docker 命令、Demo 流程、已知限制、阶段提交清单、代码学习顺序和 10 个面试技术点。目前 README 和部分架构说明仍偏早期阶段。

## 待核对的工程细节

- 浏览器关闭清理：本次结束旧登录进程时出现 TargetClosedError；需让用户提前关闭窗口的场景也能友好退出。
- 外部操作的 EXECUTING/UNCERTAIN 状态需人工核查，不能自动重发；恢复说明和操作入口仍需完善。
- 真实发送成功后，Tracker 的联系状态应依据真实回执更新；不能把模拟执行当成真实联系。
- 检查先由工作流建立 SQLite 表、之后再运行 Alembic 的迁移衔接，避免已有表冲突。
- Dashboard 当前导入候选人 JSON；直接解析 PDF/Word 简历尚未实现。
- Evaluation 离线结果只代表合成样本和确定性工具路由，不能替代真实模型、平台和模型工具选择评估。

## 常用验证命令

在 `D:\JobPilot` 的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.platform_smoke nowcoder
.\.venv\Scripts\python.exe -m app.browser_cli login --source nowcoder
.\.venv\Scripts\python.exe -m app.browser_cli search --source nowcoder --query Python --limit 1
.\.venv\Scripts\python.exe -m app.evaluation.runner --browser
```

测试以当前 Windows 用户运行，避免受限沙箱账号生成缓存后再次触发 PyCharm 权限问题。Git 使用 `C:\Program Files\Git\bin\git.exe`。密钥、真实简历、Cookie 和浏览器资料保持在 Git 忽略范围内。

阶段提交可用 `git log --oneline` 查看；本检查点的提交主题为 `feat: add phase 12 nowcoder readonly adapter`，提交后应确认工作区干净。
