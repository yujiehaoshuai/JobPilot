"""人工查看、批准、拒绝待执行动作；真实动作不会交给模拟执行器。"""

import argparse
import sys
from pathlib import Path
from app.storage.actions import ActionStore
from app.services.action_service import ApprovalService, MockActionExecutor


def main():
    """批准必须带上完整摘要，避免批准用户没有看过的最新内容。"""
    parser = argparse.ArgumentParser(description="审批队列")
    parser.add_argument("command", choices=["list", "approve", "reject", "execute-mock"])
    parser.add_argument("--database", type=Path, default=Path("data/actions.db"))
    parser.add_argument("--id")
    parser.add_argument("--digest")
    args = parser.parse_args()
    store = ActionStore(args.database)
    if args.command == "list":
        for action in store.list():
            print(action.model_dump_json(indent=2))
        return
    if not args.id:
        parser.error("该操作需要 --id")
    if args.command in {"approve", "reject"}:
        if not args.digest:
            parser.error("请先查看动作全文，再提供 --digest")
        result = store.decide(args.id, args.digest, args.command == "approve", "local-cli-user")
    else:
        result = ApprovalService(store, MockActionExecutor()).execute(args.id)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
