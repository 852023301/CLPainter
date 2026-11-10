"""比较两份 snapshot_structures.py 输出。

退出码：
- 0：完全一致
- 1：存在新增、删除或 hash 变化
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较两份笔/线段/中枢快照")
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--max-details", type=int, default=20)
    parser.add_argument("--full-diff", action="store_true", help="对变化项输出完整 JSON diff")
    return parser.parse_args()


def load_snapshot(path: Path) -> dict[str, dict]:
    data = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            data[item["path"]] = item
    return data


def main() -> int:
    args = parse_args()
    old = load_snapshot(args.old)
    new = load_snapshot(args.new)

    old_paths = set(old)
    new_paths = set(new)
    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed = sorted(
        path for path in old_paths & new_paths if old[path].get("hash") != new[path].get("hash")
    )

    print(f"old: {len(old)}  new: {len(new)}")
    print(f"added: {len(added)}  removed: {len(removed)}  changed: {len(changed)}")

    for label, paths in (("ADDED", added), ("REMOVED", removed), ("CHANGED", changed)):
        for path in paths[: args.max_details]:
            print(f"{label} {path}")

    if args.full_diff:
        for path in changed[: args.max_details]:
            old_item = old[path]
            new_item = new[path]
            old_canonical = old_item.get("canonical")
            new_canonical = new_item.get("canonical")
            if old_canonical is None or new_canonical is None:
                print(f"\n{path}: 快照没有 --full，无法输出结构 diff")
                continue
            old_lines = json.dumps(old_canonical, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
            new_lines = json.dumps(new_canonical, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"old/{path}",
                tofile=f"new/{path}",
                lineterm="",
            )
            print("\n" + "\n".join(diff))

    return 0 if not (added or removed or changed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
