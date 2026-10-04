"""小规模单机部署的互斥、限流与有限重试，不引入没有必要的 Redis。"""

import time
from contextlib import contextmanager
from threading import Lock
from filelock import FileLock, Timeout
from app.exceptions import InvalidTransitionError, TransientLLMError


@contextmanager
def workflow_lock(data_dir):
    """同一数据目录一次只执行一个图；锁在进程退出后自动释放。"""
    lock = FileLock(str(data_dir / "workflow.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise InvalidTransitionError("此数据目录已有工作流执行中，请稍后恢复") from None
    try:
        yield
    finally:
        lock.release()


def retry_model(operation, attempts=3, delay=0.5):
    """只重试明确的暂时模型错误；格式错误、认证错误和外部发送不使用此函数。"""
    for attempt in range(attempts):
        try:
            return operation()
        except TransientLLMError:
            if attempt + 1 == attempts:
                raise
            time.sleep(min(delay * (2 ** attempt), 4))


class TokenBucket:
    """本机 API 的简单令牌桶；容量控制突发量，速率控制持续请求量。"""

    def __init__(self, capacity=120, per_second=2):
        self.capacity, self.rate = capacity, per_second
        self.tokens, self.updated = float(capacity), time.monotonic()
        self.lock = Lock()

    def allow(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True
