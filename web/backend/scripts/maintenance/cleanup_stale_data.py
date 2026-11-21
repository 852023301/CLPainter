"""Preview, quarantine or restore unregistered runtime data; never delete it."""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR.parent.parent.parent))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="统一预览、隔离与恢复源数据和派生缓存")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="将确认失效的文件移入隔离目录，不物理删除")
    action.add_argument("--restore", type=Path, help="按隔离 manifest.json 恢复，不覆盖现存文件")
    parser.add_argument("--metadata-report", type=Path, default=os.getenv("CLPAINTER_METADATA_REPORT"))
    parser.add_argument("--max-orphan-ratio", type=float, default=0.2, help="单范围允许的隔离比例，默认 0.2")
    args = parser.parse_args(argv)
    if not args.restore and not args.metadata_report:
        parser.error("清理必须提供完整元数据清单 --metadata-report")
    from CLPainter.web.backend.app._config.settings import settings
    from CLPainter.web.backend.app.data_lifecycle import (
        apply_cleanup,
        plan_cleanup,
        restore_cleanup,
    )
    from CLPainter.web.backend.app.db.base import engine

    try:
        if args.restore:
            result = {"mode": "restore", **restore_cleanup(args.restore, settings)}
        else:
            plan = plan_cleanup(settings, engine, args.metadata_report, max_orphan_ratio=args.max_orphan_ratio)
            if args.apply:
                manifest = apply_cleanup(plan, settings, engine)
                result = {
                    "mode": "quarantine",
                    "as_of": plan["as_of"],
                    "moved": len(plan["files"]),
                    "manifest": str(manifest) if manifest else None,
                    "skipped": plan["skipped"],
                }
            else:
                result = {"mode": "dry-run", "count": len(plan["files"]), "plan": plan}
    except (ValueError, KeyError, OSError) as error:
        print(f"统一清理拒绝执行: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
