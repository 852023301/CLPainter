"""导出笔/线段/中枢的稳定快照，用于重构前后的全量 diff。

默认只写 hash 和计数，体积小；加 ``--full`` 时把完整规范结构也写入 JSONL。
输出按缓存路径排序，保证同一份代码重复运行得到完全相同的文件。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
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
    CACHE_DUMP_DIR,
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
)

logger = logging.getLogger(__name__)


def _default_worker_count() -> int:
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出笔/线段/中枢稳定快照")
    parser.add_argument("--dump-dir", type=Path, default=CACHE_DUMP_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frequency", choices=tuple(SUPPORTED_CHART_FREQUENCIES))
    parser.add_argument("--market")
    parser.add_argument("--asset-class")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=_default_worker_count())
    parser.add_argument("--full", action="store_true", help="写入完整规范结构，而不只是 hash")
    parser.add_argument("--include-pivots", action="store_true", default=True)
    parser.add_argument("--no-pivots", dest="include_pivots", action="store_false")
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


def collect_cache_files(args: argparse.Namespace) -> list[Path]:
    cache_files = sorted(args.dump_dir.glob("freq=*/market=*/asset_class=*/*.pkl"))
    if args.frequency:
        cache_files = [path for path in cache_files if cache_metadata(path)[0] == args.frequency]
    if args.market:
        market_dir = f"market={args.market}"
        cache_files = [path for path in cache_files if cache_metadata(path)[1] == market_dir]
    if args.asset_class:
        asset_class_dir = f"asset_class={args.asset_class}"
        cache_files = [path for path in cache_files if cache_metadata(path)[2] == asset_class_dir]
    if args.symbol:
        symbol = Path(args.symbol).stem
        cache_files = [path for path in cache_files if path.stem == symbol]
    if args.limit is not None:
        cache_files = cache_files[: args.limit]
    return cache_files


def _round_price(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 8)


def _iso_time(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def canonical_bi(bi: Any) -> list[Any]:
    return [
        getattr(getattr(bi, "bi_type", None), "value", str(getattr(bi, "bi_type", None))),
        _iso_time(getattr(bi, "start_time", None)),
        _iso_time(getattr(bi, "end_time", None)),
        _round_price(getattr(bi, "start_price", None)),
        _round_price(getattr(bi, "end_price", None)),
        int(getattr(bi, "start_idx", 0)),
        int(getattr(bi, "end_idx", 0)),
        type(bi).__name__,
    ]


def canonical_xianduan(segment: Any) -> list[Any]:
    return [
        getattr(
            getattr(segment, "xianduan_type", None),
            "value",
            str(getattr(segment, "xianduan_type", None)),
        ),
        _iso_time(getattr(segment, "start_time", None)),
        _iso_time(getattr(segment, "end_time", None)),
        _round_price(getattr(segment, "start_price", None)),
        _round_price(getattr(segment, "end_price", None)),
        int(getattr(segment, "start_bi_idx", 0)),
        int(getattr(segment, "end_bi_idx", 0)),
        type(segment).__name__,
    ]


def canonical_pivot(pivot: Any) -> list[Any]:
    return [
        _iso_time(getattr(pivot, "start_time", None)),
        _iso_time(getattr(pivot, "end_time", None)),
        _round_price(getattr(pivot, "start_price", None)),
        _round_price(getattr(pivot, "end_price", None)),
        _round_price(getattr(pivot, "high_price", None)),
        _round_price(getattr(pivot, "low_price", None)),
        int(getattr(pivot, "start_bi_idx", 0)),
        int(getattr(pivot, "end_bi_idx", 0)),
        type(pivot).__name__,
    ]


def build_snapshot(cache_file: Path, dump_dir: Path, include_pivots: bool, full: bool) -> dict:
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        dump_dir,
    )
    bi_list = [canonical_bi(bi) for bi in (getattr(cache, "bi_list", None) or [])]
    xian_duan_list = [
        canonical_xianduan(segment)
        for segment in (getattr(cache, "xian_duan_list", None) or [])
    ]
    bi_zs_in_xd = []
    xd_zs = []
    if include_pivots:
        bi_zs_in_xd = [
            canonical_pivot(pivot)
            for pivot in (getattr(cache, "bi_zhongshu_in_xianduan_list", None) or [])
        ]
        xd_zs = [
            canonical_pivot(pivot)
            for pivot in (getattr(cache, "xianduan_zhongshu_list", None) or [])
        ]

    canonical = {
        "bi": bi_list,
        "xian_duan": xian_duan_list,
        "bi_zhongshu_in_xianduan": bi_zs_in_xd,
        "xianduan_zhongshu": xd_zs,
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    result = {
        "path": str(cache_file.relative_to(dump_dir)),
        "symbol": cache_file.stem,
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "hash": digest,
        "bi_count": len(bi_list),
        "xd_count": len(xian_duan_list),
        "bi_zs_in_xd_count": len(bi_zs_in_xd),
        "xd_zs_count": len(xd_zs),
    }
    if full:
        result["canonical"] = canonical
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if not args.dump_dir.exists():
        logger.error("缓存目录不存在: %s", args.dump_dir)
        return 1

    cache_files = collect_cache_files(args)
    if not cache_files:
        logger.warning("没有找到可导出的缓存: %s", args.dump_dir)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    worker_count = min(max(1, args.workers), len(cache_files))
    results = []
    failed = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                build_snapshot,
                cache_file,
                args.dump_dir,
                args.include_pivots,
                args.full,
            ): cache_file
            for cache_file in cache_files
        }
        for future in as_completed(futures):
            cache_file = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                failed += 1
                logger.exception("导出失败: %s: %s", cache_file, error)

    results.sort(key=lambda item: item["path"])
    with args.output.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    logger.info("导出完成: 成功 %d，失败 %d，输出 %s", len(results), failed, args.output)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
