"""让真正的工作流通过 MCP 子进程读取岗位，然后停在审批节点。"""

from tempfile import TemporaryDirectory
from pathlib import Path
from app.main import load_candidate
from app.config import load_settings
from app.workflow.runtime import open_graph, graph_config


def main():
    candidate = load_candidate(load_settings().candidate_path)
    with TemporaryDirectory() as folder:
        with open_graph(Path(folder), transport="mcp") as (graph, actions):
            config = graph_config("mcp-smoke")
            graph.invoke({"run_id": "mcp-smoke", "source": "mock", "mode": "offline", "transport": "mcp",
                          "queries": [], "candidate": candidate.model_dump(mode="json")}, config)
            assert graph.get_state(config).next == ("review",)
            assert actions.list()[0].status == "PENDING"
            print("MCP handshake -> search -> graph -> approval interrupt: OK")


if __name__ == "__main__":
    main()
