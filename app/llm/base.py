"""只约定结构化调用，不让业务服务依赖具体模型供应商。"""

from typing import Any, Protocol, TypeVar
from pydantic import BaseModel
from app.models.analysis import Usage

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """所有客户端都必须返回经过 Pydantic 校验的对象。"""

    usage: list[Usage]

    def complete(self, task: str, payload: dict[str, Any], schema: type[T]) -> T:
        """按指定任务调用模型，并校验返回结构。"""
        ...
