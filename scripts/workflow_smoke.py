"""在临时目录完成一次图中断、关闭、重建和人工拒绝演示。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from langgraph.types import Command
from app.config import load_settings
from app.main import load_candidate
from app.workflow.runtime import open_graph, graph_config


def main():
    profile = load_candidate(load_settings().candidate_path)
    config = graph_config("smoke")
    with TemporaryDirectory() as folder:
        with open_graph(Path(folder)) as (graph, actions):
            graph.invoke({"run_id": "smoke", "candidate": profile.model_dump(mode="json"),
                          "queries": [], "source": "mock", "mode": "offline"}, config)
            assert graph.get_state(config).next == ("review",)
        with open_graph(Path(folder)) as (graph, actions):
            for _ in range(30):
                state = graph.get_state(config)
                if not state.next:
                    assert state.values["status"] == "COMPLETED"
                    print(f"Checkpoint / resume / loop: OK ({len(state.values['results'])} jobs)")
                    return
                action = actions.get(state.values["action_id"])
                actions.decide(action.id, action.digest, False, "offline-demo-human")
                graph.invoke(Command(resume=True), config)
        raise AssertionError("工作流未在预期步数内完成")


if __name__ == "__main__":
    main()
