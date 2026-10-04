# 完整源码目录树与文件职责

这是 Phase 0 + Phase 1 的完整项目源码/测试/文档清单。注释说明每个文件在当前架构中的作用。`__init__.py` 仅声明对应 Python 包与模块说明，不隐藏初始化业务逻辑。

```text
JobPilot/
├── .env.example                       # 本阶段配置变量名，不含凭据
├── .gitignore                         # 忽略个人资料、数据库、环境与缓存
├── .python-version                    # 声明 Python 3.12
├── pyproject.toml                     # 版本边界、项目元数据、pytest 配置
├── requirements.txt                   # Pydantic 与 python-dotenv 运行依赖
├── requirements-dev.txt               # 运行依赖 + pytest
├── README.md                          # 定位、安装、运行、测试、输出与路线图
├── app/
│   ├── __init__.py                    # app 包
│   ├── main.py                        # CLI 参数、可见流水线、错误出口
│   ├── config.py                      # 环境/.env/默认配置及路径解析
│   ├── logging_config.py              # 标准库日志、run_id、stderr 输出
│   ├── enums.py                       # 用工类型、技能等级、申请状态
│   ├── exceptions.py                  # 明确的领域/配置/存储错误类型
│   ├── models/
│   │   ├── __init__.py                # 模型包
│   │   ├── base.py                    # 公共模型配置及非空字符串约束
│   │   ├── candidate.py               # 候选人事实、技能证据与求职条件
│   │   ├── job.py                     # 平台统一岗位与过滤结果
│   │   └── application.py             # 候选人/岗位关联的本地进展
│   ├── adapters/
│   │   ├── __init__.py                # 数据入口包
│   │   ├── base.py                    # 只读搜索/详情抽象接口
│   │   └── mock/
│   │       ├── __init__.py            # Mock 包
│   │       └── adapter.py            # 有序读取并校验 JSON 岗位
│   ├── services/
│   │   ├── __init__.py                # 业务规则包
│   │   ├── normalization_service.py   # 字符串清理及 URL 规范化
│   │   ├── filter_service.py          # 确定性筛选及拒绝原因
│   │   └── deduplication_service.py   # 批次内按平台身份/URL 保序去重
│   └── storage/
│       ├── __init__.py                # 持久化包
│       └── tracker.py                 # SQLite、事务、身份复用、确认及状态流转
├── fixtures/
│   ├── candidate.example.json        # 明确标记为虚构的候选人示例
│   └── jobs/
│       ├── 01_agent_engineer.json     # 通过：Agent 实习
│       ├── 02_llm_application.json    # 通过：LLM 应用实习
│       ├── 03_ai_backend.json         # 通过：AI 后端实习
│       ├── 04_rag.json                # 通过：远程 RAG 实习
│       ├── 05_chinese_llm.json        # 通过：中文大模型标题
│       ├── 06_agent_tools.json        # 通过：Agent 工具实习
│       ├── 07_rag_platform.json       # 通过：RAG 平台实习
│       ├── 08_llm_engineering.json    # 通过：中文远程城市别名
│       ├── 09_agent_workflow.json     # 通过：Agent 工作流实习
│       ├── 10_llm_backend.json        # 通过：LLM 后端实习
│       ├── 11_rag_engineer.json       # 通过：RAG 工程实习
│       ├── 12_agent_id_duplicate.json # 通过过滤后按平台编号去重
│       ├── 13_llm_url_duplicate.json  # 通过过滤后按规范 URL 去重
│       ├── 14_frontend.json           # 拒绝：Agent 相关但属于前端
│       ├── 15_frontend.json           # 拒绝：英文前端标题
│       ├── 16_testing.json            # 拒绝：LLM 相关但属于测试
│       ├── 17_testing.json            # 拒绝：英文测试标题
│       ├── 18_cv_algorithm.json       # 拒绝：CV 算法
│       ├── 19_cv_algorithm.json       # 拒绝：中文计算机视觉
│       └── 20_sales.json              # 拒绝：销售/排除关键词
├── tests/
│   ├── conftest.py                    # 测试候选人及岗位工厂
│   ├── unit/
│   │   ├── test_models.py             # 模型约束、序列化、时间与默认值
│   │   ├── test_config.py             # 配置优先级、路径、错误值
│   │   ├── test_mock_adapter.py       # Mock 查询、详情、损坏文件
│   │   ├── test_filter.py             # 业务筛选及边界条件
│   │   ├── test_deduplication.py      # 规范化、去重与保留身份参数
│   │   └── test_storage.py            # 事务、幂等、状态及候选人隔离
│   └── integration/
│       └── test_workflow.py           # 实际 CLI、重启、批准、URL 别名与错误路径
└── docs/
    ├── architecture.md                # 当前实现、设计理由与阶段边界
    ├── file-guide.md                  # 本文件：完整源码目录与职责
    └── phase-0-1-report.md             # 续做文件清单、验收与未开始工作
```

工作区还有自动生成且不应提交的目录：

| 路径 | 作用 |
| --- | --- |
| `.venv/` | 上次已配置的 Python 3.12.10 虚拟环境与依赖；本次沿用 |
| `.runtime/` | 上次环境依赖的本地 Python 发行包；本次保持不变 |
| `data/jobpilot.db` | 运行演示生成的候选人、11 个岗位、11 个申请记录 |
| `.pytest_cache/`、各层 `__pycache__/` | 测试缓存与 Python 字节码 |

本轮没有修改此前的模型、20 个岗位数据、候选人示例或筛选规则实现。具体续做文件清单见验收记录。尚未初始化 Git，因此这里的“新增/修改”相对于本次续做开始时的磁盘检查，不是提交间差异。
