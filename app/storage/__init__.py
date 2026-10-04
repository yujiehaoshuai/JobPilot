"""本地存储模块：保存候选人资料、岗位信息和申请进度。"""

from app.storage.tracker import SQLiteTracker

__all__ = ["SQLiteTracker"]
