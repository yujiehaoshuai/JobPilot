"""有状态任务的启动、查看和恢复入口。"""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4
from langgraph.types import Command
from app.config import load_settings
from app.main import load_candidate
from app.workflow.runtime import open_graph, graph_config


def main():
    parser = argparse.ArgumentParser(description="持久化求职工作流")
    parser.add_argument("command", choices=["start", "status", "resume"])
    parser.add_argument("--id")
    parser.add_argument("--source", choices=["mock", "boss", "nowcoder", "shixiseng"], default="mock")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--transport", choices=["direct", "mcp"], default="direct")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--query", action="append")
    parser.add_argument("--limit", type=int, help="最多读取多少条岗位，1 到 40；实习僧默认 5 条")
    parser.add_argument("--analysis-only", action="store_true", help="只搜索、过滤和匹配，不生成草稿或审批动作")
    parser.add_argument("--data", type=Path, default=Path("data/agent"))
    args = parser.parse_args()
    if args.limit is not None and not 1 <= args.limit <= 40:
        parser.error("--limit 必须在 1 到 40 之间")
    run_id = args.id or str(uuid4())
    if args.command != "start" and not args.id:
        parser.error("查看或恢复需要 --id")
    with open_graph(args.data, source=args.source, mode=args.mode, transport=args.transport,
                    search_limit=args.limit) as (graph, actions):
        config = graph_config(run_id)
        existing = graph.get_state(config)
        if args.command == "start":
            if existing.values:
                parser.error("任务编号已存在，请恢复原任务或使用新编号")
            profile = load_candidate(args.candidate or load_settings().candidate_path)
            graph.invoke({"run_id": run_id, "candidate": profile.model_dump(mode="json"),
                          "queries": args.query or [], "source": args.source, "mode": args.mode,
                          "transport": args.transport, "analysis_only": args.analysis_only,
                          "search_limit": args.limit}, config)
        elif not existing.values:
            parser.error("找不到该任务")
        elif (existing.values["source"], existing.values["mode"], existing.values.get("transport", "direct")) != (args.source, args.mode, args.transport):
            parser.error("恢复时必须使用任务原本的 source、mode 和 transport")
        elif args.command == "resume":
            if existing.values.get("search_limit") != args.limit:
                parser.error("恢复时 --limit 必须与原任务一致")
            paused = any(task.interrupts for task in existing.tasks)
            graph.invoke(Command(resume=True) if paused else None, config)
        state = graph.get_state(config)
        print(json.dumps({"run_id": run_id, "next": state.next, "state": state.values,
                          "interrupts": [i.value for t in state.tasks for i in t.interrupts]},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
