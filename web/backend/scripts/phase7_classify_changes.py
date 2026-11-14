"""Phase 7：按首段变化 / 首段之后变化分类新旧缓存。

只读两个 curated 目录，输出 JSONL 清单和汇总，不修改缓存。
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
)
from CLPainter.web.backend.app.toolbox.xianduan import (  # noqa: E402
    FakeXianDuanFirst,
    XianDuan,
)

logger = logging.getLogger(__name__)


def _default_worker_count() -> int:
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 新旧缓存分类")
    parser.add_argument("--old-dump-dir", type=Path, required=True)
    parser.add_argument("--new-dump-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=_default_worker_count())
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def cache_metadata(cache_file: Path) -> tuple[str, str, str]:
    asset_class_dir = cache_file.parent.name
    market_dir = cache_file.parent.parent.name
    frequency = cache_file.parent.parent.parent.name
    if frequency not in SUPPORTED_CHART_FREQUENCIES:
        raise ValueError(f"不支持的缓存周期: {frequency}: {cache_file}")
    if not market_dir.startswith("market="):
        raise ValueError(f"缓存目录缺少 market=...: {cache_file}")
    if not asset_class_dir.startswith("asset_class="):
        raise ValueError(f"缓存目录缺少 asset_class=...: {cache_file}")
    return frequency, market_dir, asset_class_dir


def _canonical(segment: Any) -> list[Any]:
    return [
        getattr(getattr(segment, "xianduan_type", None), "value", str(getattr(segment, "xianduan_type", None))),
        getattr(segment, "start_time", None).isoformat() if getattr(segment, "start_time", None) is not None else None,
        getattr(segment, "end_time", None).isoformat() if getattr(segment, "end_time", None) is not None else None,
        round(float(getattr(segment, "start_price", 0.0)), 8),
        round(float(getattr(segment, "end_price", 0.0)), 8),
        int(getattr(segment, "start_bi_idx", 0)),
        int(getattr(segment, "end_bi_idx", 0)),
        type(segment).__name__,
    ]


def _first_real_index(segments: list[Any]) -> int | None:
    for index, segment in enumerate(segments):
        if isinstance(segment, XianDuan):
            return index
    return None


def _is_suffix(short: list[Any], long: list[Any]) -> bool:
    if not short or len(short) > len(long):
        return False
    return long[-len(short) :] == short


def _tail_equal(old_segments: list[Any], new_segments: list[Any]) -> bool:
    """首段变化：旧序列是新序列的后缀，或新序列是旧序列的后缀。"""
    old_canonical = [_canonical(item) for item in old_segments]
    new_canonical = [_canonical(item) for item in new_segments]
    return _is_suffix(old_canonical, new_canonical) or _is_suffix(
        new_canonical, old_canonical
    )


def classify_cache(old_dump: Path, new_dump: Path, cache_file: Path) -> dict | None:
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    old_path = old_dump / cache_file.relative_to(new_dump)
    if not old_path.exists():
        return None
    old_cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        old_dump,
    )
    new_cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        new_dump,
    )
    old_segments = list(old_cache.xian_duan_list or [])
    new_segments = list(new_cache.xian_duan_list or [])
    old_canonical = [_canonical(item) for item in old_segments]
    new_canonical = [_canonical(item) for item in new_segments]
    if old_canonical == new_canonical:
        return None

    group = "first_only" if _tail_equal(old_segments, new_segments) else "body_changed"
    fake_count = sum(isinstance(item, FakeXianDuanFirst) for item in new_segments)
    return {
        "symbol": cache_file.stem,
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "path": str(cache_file.relative_to(new_dump)),
        "group": group,
        "fake_first_count": fake_count,
        "old_count": len(old_segments),
        "new_count": len(new_segments),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if not args.old_dump_dir.exists() or not args.new_dump_dir.exists():
        logger.error("新旧缓存目录必须存在")
        return 1

    cache_files = sorted(args.new_dump_dir.glob("freq=*/market=*/asset_class=*/*.pkl"))
    if args.limit is not None:
        cache_files = cache_files[: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    worker_count = min(max(1, args.workers), len(cache_files))
    results: list[dict] = []
    failed = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(classify_cache, args.old_dump_dir, args.new_dump_dir, path): path
            for path in cache_files
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                result = future.result()
            except Exception as error:
                failed += 1
                logger.exception("分类失败: %s: %s", path, error)
                continue
            if result is not None:
                results.append(result)

    results.sort(key=lambda item: item["path"])
    groups = {
        "first_only": [item for item in results if item["group"] == "first_only"],
        "body_changed": [item for item in results if item["group"] == "body_changed"],
        "multi_fake": [item for item in results if item["fake_first_count"] > 1],
    }
    for name, rows in groups.items():
        with (args.output_dir / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "checked": len(cache_files),
        "failed": failed,
        "changed": len(results),
        "groups": {name: len(rows) for name, rows in groups.items()},
        "by_frequency": dict(Counter(item["frequency"] for item in results).most_common()),
        "by_asset_class": dict(Counter(item["asset_class"] for item in results).most_common()),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info("分类完成: checked=%d changed=%d failed=%d", len(cache_files), len(results), failed)
    logger.info("分组: %s", summary["groups"])
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
