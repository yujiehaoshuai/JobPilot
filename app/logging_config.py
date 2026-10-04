"""配置标准库日志，供命令行入口记录运行编号、步骤、结果和耗时。"""

import logging


def configure_logging(level: str, run_id: str) -> logging.LoggerAdapter:
    """设置 JobPilot 专用日志，返回带有运行编号的日志适配器。

    level 控制详细程度，run_id 用于关联同一轮运行。
    调用方应只记录必要信息，避免把完整简历或岗位正文写入日志。
    """
    logger = logging.getLogger("jobpilot")
    # 入口会配置日志两次。先移除旧处理器，避免同一条消息重复输出。
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler()
    # 默认写到 stderr；命令行中的正常结果仍由 main.py 输出到 stdout。
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(level)
    # 不再传给根日志器，避免其他库的日志配置造成重复输出。
    logger.propagate = False
    # 适配器保存 run_id；当前入口会在日志正文中明确写出这个编号。
    return logging.LoggerAdapter(logger, {"run_id": run_id})
