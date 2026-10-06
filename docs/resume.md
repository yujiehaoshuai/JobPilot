# JobPilot 续做记录

更新时间：2026-10-06。用户已确认普通 Edge 中可以搜索并查看 BOSS 岗位；程序化访问仍跳空白。

## 当前检查点

- Phase 0、1 原有结构和测试保留；Phase 2–11 已分别提交。
- Phase 12 的牛客只读 Adapter、统一入口、合成页面与测试已实现。本检查点保存这些改动，真实网站验收仍待完成。
- 最新全量测试：150 通过，1 跳过（没有专用 PostgreSQL 测试库）。本地浏览器读取与导航诊断通过；之前的 Dashboard、工作流恢复和带浏览器的离线评估通过。
- 真实牛客搜索检测到登录或验证界面，已暂停。BOSS 的 no-sandbox 警告已修复；用户确认普通 Edge 可以搜索、查看详情并已关闭窗口。复用同一资料的程序化访问仍约 3.6 秒后变为空白。报告没有给出空白跳转的发起原因，不能断言网站风控或浏览器故障，停止重复请求。
- 实习僧公开请求返回 403，已停止网络请求，Phase 13 尚未实现验收。
- 没有发送真实消息、投递或修改远端数据。项目环境、数据库、Git 历史和浏览器资料未删除。

## 下次从这里继续

1. 先读本文件、`docs/phases.md` 和 Git 状态，检查已有改动，不重做 Phase 0、1。沿用 `.venv\Scripts\python.exe`，不要重新安装 Python 或重建环境。
2. 完成 Phase 12 的人工登录后只读验收；遇到验证继续暂停，不能把本地合成页面成功当作线上成功。确认阶段稳定后再进入 Phase 13。
3. 实现 ShixisengAdapter，保持集中选择器、统一岗位模型、离线 fixtures、测试和阶段提交。公开搜索入口为 `https://www.shixiseng.com/interns?k=Python`；曾观察到部分字段出现字体混淆字符，需核对真实 DOM，不能绕过平台防护或猜造字段。
4. 补齐端到端验收缺口：真实 OpenAI 兼容模型（用户稍后配置本机 `.env`）、BOSS 程序化读取兼容问题，以及获得逐动作批准后的平台操作实现。普通 Edge 登录和人工浏览已由用户确认；不要再次要求重复登录。当前真实执行器会暂停，不能宣称已支持真实发送。
5. 验证真实 PostgreSQL、Docker 镜像构建与 Compose 启动；当前仅完成 SQLite、迁移相关测试和部署静态预检，本机未找到 Docker/psql。
6. README、Architecture、完整源码树、Demo/部署命令、提交清单、学习顺序和面试技术点已更新。后续真实平台验收完成后，还需同步更新当前限制和测试结论。

## 待核对的工程细节

- 已修复提前关窗清理、数据库迁移衔接及 EXECUTING/UNCERTAIN 的暂停核查入口；已提交并测试。
- Tracker 现在只凭非模拟成功结果推进到 CONTACTED；真实发送仍需要平台实现及验收。
- 普通 Edge 启动器可能提前退出；人工登录命令等待用户确认关闭窗口，不能把进程退出视为登录成功。
- 已修复搜索页导航链接和隐藏空结果模板的误判；只有可见结果才表示页面就绪。同名隐藏验证模板不能遮住真正显示的验证弹窗。
- 新增 `browser_cli diagnose` 单次只读诊断。只保存导航类别和已知原因，不记录 URL、Cookie 或页面正文；本地合成脚本跳空白样本能正确记录原因，真实 BOSS 的空白跳转未提供原因。
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

后续已保存修复提交：4bf7f9a、e850f74、3fa77b2。具体阶段哈希与验收范围见 phases.md。
