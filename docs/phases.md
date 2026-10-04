# 分阶段实施与验收

Phase 0 + 1 基线：原有 88 项测试通过，原 CLI 为 20 → 13 → 11。已初始化 Git，保留原代码与环境。

## Phase 2

新增 LLMClient、OpenAI 兼容 JSON Schema 客户端、离线替身、JobAnalysis、MatchResult、GreetingPlan 和 GreetingDraft。增加 JD 引用验证和候选人原文证据约束。

检查命令：`python -m pytest -q`；关键功能：`python -m app.intelligence_demo --mode offline`。

验收：97 项测试通过；离线分析演示完成，11 个岗位均经过证据检查。

真实模型需要用户在 .env 配置服务与密钥，目前尚未联网验收。匹配采用保守的显式技能核对；同义词和简历隐含技能不会被自动当成既有经验。
