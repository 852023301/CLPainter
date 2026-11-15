"""Phase 7：新旧管线并行对比。

默认读取 ``settings.CACHE_DUMP_DIR``，当前指向 data_set_dev 下的 curated 缓存。
对每个缓存，把已存的 bi/xian_duan 作为旧结果，再跑实验性修复循环，
输出差异报告。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app._config.settings import settings  # noqa: E402
from CLPainter.web.backend.app.toolbox.bi import (  # noqa: E402
    generate_bi_with_repair_loop,
)
from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
    postprocess_xian_duan,
)
from CLPainter.web.backend.app.toolbox.xianduan import (  # noqa: E402
    generate_xian_duan_with_repair_loop,
)

logger = logging.getLogger(__name__)


def _default_worker_count() -> int:
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 新旧管线并行对比")
    parser.add_argument("--dump-dir", type=Path, default=Path(settings.CACHE_DUMP_DIR))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frequency", choices=tuple(SUPPORTED_CHART_FREQUENCIES))
    parser.add_argument("--market")
    parser.add_argument("--asset-class")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=_default_worker_count())
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--full", action="store_true", help="报告里写入完整新旧结构")
    parser.add_argument("--use-local-resegment", action="store_true", help="启用局部重分段")
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


def _canonical_bi(bi: Any) -> list[Any]:
    return [
        getattr(getattr(bi, "bi_type", None), "value", str(getattr(bi, "bi_type", None))),
        getattr(bi, "start_time", None).isoformat() if getattr(bi, "start_time", None) is not None else None,
        getattr(bi, "end_time", None).isoformat() if getattr(bi, "end_time", None) is not None else None,
        round(float(getattr(bi, "start_price", 0.0)), 8),
        round(float(getattr(bi, "end_price", 0.0)), 8),
        int(getattr(bi, "start_idx", 0)),
        int(getattr(bi, "end_idx", 0)),
        type(bi).__name__,
    ]


def _canonical_xd(segment: Any) -> list[Any]:
    return [
        getattr(
            getattr(segment, "xianduan_type", None),
            "value",
            str(getattr(segment, "xianduan_type", None)),
        ),
        getattr(segment, "start_time", None).isoformat() if getattr(segment, "start_time", None) is not None else None,
        getattr(segment, "end_time", None).isoformat() if getattr(segment, "end_time", None) is not None else None,
        round(float(getattr(segment, "start_price", 0.0)), 8),
        round(float(getattr(segment, "end_price", 0.0)), 8),
        int(getattr(segment, "start_bi_idx", 0)),
        int(getattr(segment, "end_bi_idx", 0)),
        type(segment).__name__,
    ]


def compare_cache(
    cache_file: Path,
    dump_dir: Path,
    max_iterations: int,
    full: bool,
    use_local_resegment: bool = False,
) -> dict:
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        dump_dir,
    )
    old_bis = list(getattr(cache, "bi_list", None) or [])
    old_xds = list(getattr(cache, "xian_duan_list", None) or [])
    old_bi_canon = [_canonical_bi(bi) for bi in old_bis]
    old_xd_canon = [_canonical_xd(segment) for segment in old_xds]
    new_bis = generate_bi_with_repair_loop(
        cache.fenxing_list,
        cache.merged_klines,
        max_iterations=max_iterations,
        initial_bis=old_bis,
        copy_input=True,
    )
    # 线段对比必须从旧管线重新生成，而不是在旧缓存上原地修复。
    # 否则 fake 首段/尾段等由生成阶段产生的结构不会被重新计算。
    new_xds = generate_xian_duan_with_repair_loop(
        cache.te_zheng_xu_lie_list,
        old_bis,
        max_iterations=max_iterations,
        initial_segments=None,
        use_local_resegment=use_local_resegment,
        allow_count_changing_repairs=False,
    )
    new_xds = postprocess_xian_duan(
        new_xds,
        old_xds,
        cache.te_zheng_xu_lie_list,
        old_bis,
        symbol=cache_file.stem,
        frequency=frequency,
    )

    new_bi_canon = [_canonical_bi(bi) for bi in new_bis]
    new_xd_canon = [_canonical_xd(segment) for segment in new_xds]

    result = {
        "path": str(cache_file.relative_to(dump_dir)),
        "symbol": cache_file.stem,
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "bi_changed": old_bi_canon != new_bi_canon,
        "xd_changed": old_xd_canon != new_xd_canon,
        "old_bi_count": len(old_bis),
        "new_bi_count": len(new_bis),
        "old_xd_count": len(old_xds),
        "new_xd_count": len(new_xds),
    }
    if full:
        result["old_bi"] = old_bi_canon
        result["new_bi"] = new_bi_canon
        result["old_xd"] = old_xd_canon
        result["new_xd"] = new_xd_canon
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if not args.dump_dir.exists():
        logger.error("缓存目录不存在: %s", args.dump_dir)
        return 1

    cache_files = collect_cache_files(args)
    if not cache_files:
        logger.warning("没有找到可对比的缓存: %s", args.dump_dir)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    worker_count = min(max(1, args.workers), len(cache_files))
    results = []
    failed = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                compare_cache,
                cache_file,
                args.dump_dir,
                args.max_iterations,
                args.full,
                args.use_local_resegment,
            ): cache_file
            for cache_file in cache_files
        }
        for future in as_completed(futures):
            cache_file = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                failed += 1
                logger.exception("对比失败: %s: %s", cache_file, error)

    results.sort(key=lambda item: item["path"])
    with args.output.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    bi_changed = sum(1 for item in results if item["bi_changed"])
    xd_changed = sum(1 for item in results if item["xd_changed"])
    logger.info(
        "对比完成: 成功 %d，失败 %d，bi_changed=%d，xd_changed=%d，输出 %s",
        len(results),
        failed,
        bi_changed,
        xd_changed,
        args.output,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
