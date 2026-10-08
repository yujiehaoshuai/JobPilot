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


class TransientLLMError(LLMError):
    """限流、暂时服务故障或网络错误，可有限重试模型生成。"""


class StructuredOutputError(LLMError):
    """模型返回格式不符合约定，或引用了不存在的证据。"""


class BrowserPausedError(JobPilotError):
    """网站要求人工登录或验证；完成后才能继续读取。"""


class SelectorChangedError(JobParseError):
    """页面未出现约定字段；暂停并检查页面结构，不能当作零个岗位。"""


class UnreadableJobError(JobParseError):
    """单条岗位正文含无法可靠解释的字符；搜索可跳过，但必须说明原因。"""


class UnavailableJobError(JobParseError):
    """岗位详情明确返回 404/410；记录下线原因后可继续其他岗位。"""
