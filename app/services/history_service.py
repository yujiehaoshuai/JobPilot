"""清理已经结束的纯搜索历史；联系凭据和仍在使用的数据始终保留。"""

from app.exceptions import InvalidTransitionError
from app.reliability import workflow_lock
from app.workflow.checkpoints import open_checkpointer


def clear_search_history(worker, contacts, bridge):
    """先阻止恢复，再清理检查点和扩展缓存，最后删除业务记录。

    SQLite 的检查点和业务数据分库存放，不能假装一次事务覆盖所有文件。
    因此使用持久 DELETING 状态：中途失败时再次点清理即可继续，不会重跑岗位。
    不删除任何 PendingAction，也不取消正在运行或等待人工处理的任务。
    """
    with worker.lock, contacts.lock, workflow_lock(worker.data_dir):
        if any(not future.done() for future in worker.futures.values()):
            raise InvalidTransitionError("请等当前搜索结束后再清理历史")
        runs = worker.runs
        protected = {action.run_id for action in contacts.actions.list()}
        tracked_profiles = {item.candidate_id for item in contacts.tracker.list_applications()
                            if item.status not in {"NEW", "ANALYZED", "SHORTLISTED"}}
        deleted = []
        with open_checkpointer(worker.data_dir, worker.database_url) as saver:
            for run in runs.list():
                profile_id = (run.get("snapshot", {}).get("candidate") or
                              run.get("input", {}).get("candidate") or {}).get("id")
                if (run["status"] not in {"COMPLETED", "FAILED", "DELETING"}
                        or run["id"] in protected or profile_id in tracked_profiles
                        or not run.get("input", {}).get("analysis_only")):
                    continue
                if not runs.begin_cleanup(run["id"]):
                    continue
                saver.delete_thread(run["id"])
                bridge.delete_request(run["id"])
                runs.finish_cleanup(run["id"])
                deleted.append(run["id"])
        return {"deleted_ids": deleted, "deleted_count": len(deleted), "kept_count": len(runs.list())}
