"""定义可以预期的业务异常，交给命令行入口统一显示和处理。

各模块通过抛出明确的异常说明失败原因，避免悄悄跳过错误。
异常消息应只包含排查所需的信息，避免写入完整的个人资料。
"""


class JobPilotError(Exception):
    """所有 JobPilot 业务异常的父类，方便入口统一捕获。"""


class ConfigurationError(JobPilotError):
    """配置或候选人输入无法读取、格式错误，或包含当前不支持的值。"""


class JobParseError(JobPilotError):
    """岗位来源无法提供有效数据，例如 JSON 损坏或找不到指定岗位。"""


class StorageError(JobPilotError):
    """数据库打开、读写或记录校验失败，无法完成当前存储操作。"""


class InvalidTransitionError(JobPilotError):
    """目标状态不存在，或当前状态不允许直接变成目标状态。"""


class ConfirmationRequiredError(JobPilotError):
    """用户尚未明确确认，因此拒绝修改本地申请状态或备注。"""


class LLMError(JobPilotError):
    """模型请求失败；错误消息不包含密钥或完整输入。"""


class StructuredOutputError(LLMError):
    """模型返回格式不符合约定，或引用了不存在的证据。"""
