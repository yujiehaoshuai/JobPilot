# PyCharm 解释器加载故障诊断（2026-09-29）

## 结论

本次 Loading environments 的直接原因是 **项目内 `.pytest_cache` 的 Windows ACL 不允许正常用户读取，导致 PyCharm 的环境发现协程异常退出**。现有 `.venv` 和 `.runtime` 正常，不需要重建。

检查的 IDE 为 PyCharm 2025.3.3，Build PY-253.31033.139。日志反复出现：

```text
java.nio.file.AccessDeniedException: D:\JobPilot\.pytest_cache
VirtualEnvReader.findInterpreter
VirtualEnvReader.findPythonInPythonRoot
UvExistingEnvironmentSelector.detectEnvironments
CustomExistingEnvironmentSelector.onShown
CoroutineName(PythonAddLocalInterpreterDialog launchOnShow)
```

同样的异常还出现在 `detectAssociatedEnvironments` 和 AWT 事件线程中。日志明确指向添加解释器窗口的扫描过程，而不是运行 python.exe 失败。

`.pytest_cache` 原所有者为 `CodexSandboxOffline`，ACL 禁止继承，仅允许 OWNER RIGHTS、SYSTEM、Administrators。PyCharm 实际以普通 `Asus'` 用户运行。修复前，以该用户执行 `Get-ChildItem D:\JobPilot\.pytest_cache` 同样得到访问被拒绝。

这是此前自动化测试留下的缓存权限问题。当前 pytest 的源码通过 `tempfile.mkdtemp` 创建缓存再重命名，解释了为什么缓存权限与项目其他目录不同。不能通过清除 PyCharm 索引、升级 IDE 或重建 SDK 表来修正项目目录的 ACL。

## 逐项检查

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe` | 存在，可正常启动，Python 3.12.10，64 位 |
| `sys.executable` | `D:\JobPilot\.venv\Scripts\python.exe` |
| `sys.prefix` | `D:\JobPilot\.venv` |
| `sys.base_prefix` | `D:\JobPilot\.runtime\python312\tools` |
| `sys._base_executable` | `D:\JobPilot\.runtime\python312\tools\python.exe`，路径有效 |
| `pyvenv.cfg` | home/executable 指向上述有效基础环境；版本 3.12.10；不继承系统包 |
| 基础运行时 | python.exe、python312.dll、Lib/venv 存在，标准库导入正常 |
| 系统 Python 3.12 | `C:\python312\python.exe` 存在且正常，但本次不切换、不重建 |
| 裸 `python --version` | 当前 PATH 下是 Python 3.14.5；验证和配置应使用明确的 `.venv` 路径 |
| pip | 25.0.1；pip check 无依赖冲突 |
| 依赖 | Pydantic 2.13.5、pytest 9.1.1 可正常导入 |
| 项目测试 | 原环境 88 项通过；修复后以 PyCharm 同一用户运行，也为 88 项通过 |

当前 pyvenv.cfg：

```ini
home = D:\JobPilot\.runtime\python312\tools
include-system-site-packages = false
version = 3.12.10
executable = D:\JobPilot\.runtime\python312\tools\python.exe
command = D:\JobPilot\.runtime\python312\tools\python.exe -m venv D:\JobPilot\.venv
```

这是标准 venv 对基础解释器的引用。项目内便携 Python 不一定能像注册安装的系统 Python 一样被自动发现，但该特点并不能证明环境损坏；本次日志已经给出更直接的权限错误。`.venv` 依赖 `.runtime`，因此保留当前环境时仍需保留 `.runtime`。

## .idea 与全局 SDK 配置

检查时未发现 `.idea/misc.xml`，也没有有效的全局 `options/jdk.table.xml`（目录中保留了用户的 backup 文件）。项目尚未持久保存 SDK 绑定，符合此前重置 SDK 配置的现状。

`JobPilot.iml` 使用 inheritedJdk；workspace.xml 的 SDK_HOME 为空、IS_MODULE_SDK=true，表示继承模块解释器，不是失效的绝对路径。未发现指向已经删除 Python 的 SDK 名称或路径。

另有两个独立的项目运行设置值得在恢复解释器后检查：

- `.idea/JobPilot.iml` 的 content URL 是 `file://$MODULE_DIR$`，而 iml 文件位于 `.idea`，应将内容根目录设为 `D:\JobPilot`（对应 `file://$MODULE_DIR$/..`）。
- 临时 main 配置使用脚本 `app/main.py`、工作目录 `app`。推荐使用模块 `app.main`、工作目录 `D:\JobPilot`，与已通过测试的 CLI 相同，避免 `app.*` 导入失败。

这两点不解释本次扫描异常。本次没有在 IDE 正运行时修改 workspace.xml 或 SDK 表，避免与 IDE 保存行为冲突。

## 已执行的最小修复

1. 保存 `.pytest_cache` 原始 ACL，再只给实际用户 `Asus'` 增加该缓存目录及子项的 Modify 权限；其他权限与所有者保持不变。
2. 验证时发现系统临时目录 `C:\Users\Asus'\AppData\Local\Temp\pytest-of-Asus'` 存在相同 ACL 问题。这不会触发本次项目扫描卡死，但会阻止普通用户运行使用 tmp_path 的测试。已备份该测试临时目录的 ACL，并为同一用户补充 Modify 权限。
3. 新增本诊断文档，保存相关日志摘录。

没有重建/移动 `.venv` 或 `.runtime`，没有安装依赖、切换 Python、修改源码、删除数据库或 Git 内容，也没有重置 IDE 全局设置。

备份与证据均在被 Git 忽略的 `data/diagnostics/pycharm-20260929/`：

- `pytest-cache-acl-before-20260929-201357.json`
- `pytest-temp-acl-before.json`
- `environment-discovery-error.log`

## 验证结果与最后一步

以 PyCharm 同一 Windows 用户执行验证：

```text
laptop-jr9kpkg4\asus'
项目根目录各子目录均可读取，包括 .pytest_cache、.runtime、.venv
No broken requirements found.
88 passed in 3.46s
```

文件系统权限与解释器验证已完成。**本次尚未直接确认 PyCharm 窗口中的 Loading environments 已消失**，需要关闭并重新打开该对话框；已异常退出的协程可能需要重启 IDE 才重新执行。

重新添加时选择现有环境：Add Interpreter → Add Local Interpreter → Select existing → Python，然后选择：

```text
D:\JobPilot\.venv\Scripts\python.exe
```

这也是 JetBrains 官方文档给出的现有 Windows venv 选择方式，不需要生成新环境：[Configure a Python interpreter](https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html)。

验证命令（普通 PowerShell，项目根目录）：

```powershell
cd D:\JobPilot
Get-ChildItem -Force .pytest_cache
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

运行应用仍使用 `.\.venv\Scripts\python.exe -m app.main`；它会正常写入本地演示跟踪数据库，因此本次诊断用临时数据库中的集成测试验证应用行为。

如果未来删除测试缓存，再由不同 Windows 账户创建，可能再次产生权限差异。应先检查缓存目录访问权限，避免把相同问题误判为 venv 损坏。JetBrains 的 [PY-83408 讨论](https://youtrack.jetbrains.com/projects/PY/issues/PY-83408/spinning-wheel-while-setting-new-python-interpreter) 也有项目中不可读目录导致环境加载一直等待的同类报告；本次结论以本机日志和访问复现为依据。
