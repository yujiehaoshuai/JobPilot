"""批量联系的持久恢复图：等批准、等浏览器、等回执，不能代替用户批准。"""

from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from app.exceptions import InvalidTransitionError
from app.workflow.checkpoints import open_checkpointer


class ContactState(TypedDict, total=False):
    """只存操作编号及状态；目标和审批正文仍以 PendingAction 的快照为准。"""

    action_id: str
    run_id: str
    observed: dict
    stage: str


def observed_action(action):
    """状态未变就不新增检查点，也不保存执行许可、个人简历或浏览器资料。"""
    return {
        "status": action.status,
        "digest": action.digest,
        "paused": action.execution_paused,
        "receipt": action.receipt,
        "decided_by": action.decided_by,
        "resolved_by": action.resolved_by,
        "resolution_note": action.resolution_note,
    }


def build_contact_graph(actions, checkpointer):
    """只理解审批状态，不依赖招聘网站；恢复不会改写批准或调用平台操作。"""
    def observe(state):
        action = actions.get(state["action_id"])
        if action.run_id != state["run_id"]:
            raise InvalidTransitionError("联系图与操作所属任务不一致")
        stage = {
            "PENDING": "WAITING_APPROVAL",
            "APPROVED": "WAITING_BROWSER" if action.execution_paused else "READY",
            "EXECUTING": "EXECUTING",
            "UNCERTAIN": "WAITING_REVIEW",
            "SUCCEEDED": "COMPLETED",
            "REJECTED": "COMPLETED",
        }[action.status]
        return {"observed": observed_action(action), "stage": stage}

    def wait_for_event(state):
        kinds = {
            "WAITING_APPROVAL": "approval",
            "WAITING_BROWSER": "browser",
            "READY": "contact_execution",
            "EXECUTING": "contact_receipt",
            "WAITING_REVIEW": "action_recovery",
        }
        interrupt({"kind": kinds[state["stage"]], "action_id": state["action_id"]})
        # Resume 只触发重新读取动作表，不能把 PENDING 自动变成 APPROVED。
        return {}

    graph = StateGraph(ContactState)
    graph.add_node("observe", observe)
    graph.add_node("wait_for_event", wait_for_event)
    graph.add_edge(START, "observe")
    graph.add_conditional_edges("observe", lambda state: END if state["stage"] == "COMPLETED" else "wait_for_event")
    graph.add_edge("wait_for_event", "observe")
    return graph.compile(checkpointer=checkpointer)


def sync_contact_workflows(store, actions, data_dir, database_url=None):
    """调用方持有联系队列锁；数据库先落盘，图失败后可由下次查询补齐。

    每个动作有独立 thread_id，并关联原搜索 run_id。这样后续追加选择岗位时，
    不必重放整个搜索，也不会重放已经完成的联系。
    """
    if not actions:
        return {}
    views = {}
    with open_checkpointer(data_dir, database_url) as saver:
        graph = build_contact_graph(store, saver)
        for action in actions:
            config = {"configurable": {"thread_id": "action:" + action.id}, "recursion_limit": 20}
            for _ in range(3):
                state = graph.get_state(config)
                waiting = any(task.interrupts for task in state.tasks)
                changed = state.values.get("observed") != observed_action(action)
                if not changed and (waiting or not state.next):
                    break
                if state.values and not state.next and not waiting:
                    raise InvalidTransitionError("联系图的终态与动作记录不一致，请人工核查")
                # 崩溃可能发生在 observe 与 wait 之间。先走完旧节点，再重新观察。
                incoming = {"action_id": action.id, "run_id": action.run_id} if not state.values else (
                    Command(resume=True) if waiting else None)
                graph.invoke(incoming, config)
                state = graph.get_state(config)
            if state.values.get("observed") != observed_action(action):
                raise InvalidTransitionError("联系检查点尚未与操作记录一致，暂不允许执行")
            views[action.id] = {
                **state.values,
                "interrupts": [item.value for task in state.tasks for item in task.interrupts],
                "checkpoint_id": state.config["configurable"].get("checkpoint_id"),
            }
    return views
