"""结构化运行事件只记录允许字段，不把密钥、Cookie 或简历正文写入日志。"""

import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import UTC, datetime
from uuid import uuid4


class EventLog:
    """日志按大小轮转；任务详情保存在受控数据库中，不重复复制到日志。"""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("jobpilot.events." + uuid4().hex)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(self.handler)

    def record(self, event, **fields):
        safe = {key: value for key, value in fields.items() if key in {
            "run_id", "status", "elapsed_ms", "error_type", "source", "mode"}}
        self.logger.info(json.dumps({"time": datetime.now(UTC).isoformat(), "event": event, **safe}, ensure_ascii=False))

    def close(self):
        self.logger.removeHandler(self.handler)
        self.handler.close()
