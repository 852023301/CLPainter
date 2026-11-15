"""Phase 7：统计新路径下笔/线段不变量违规。

只读 curated 缓存，不修改任何数据。
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app._config.settings import settings  # noqa: E402
from CLPainter.web.backend.app.toolbox.bi import (  # noqa: E402
    BiContext,
    BiInvariants,
    generate_bi_with_repair_loop,
)
from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
    postprocess_xian_duan,
)
from CLPainter.web.backend.app.toolbox.tezhengxulie import (  # noqa: E402
    generate_te_zheng_xu_lie,
)
from CLPainter.web.backend.app.toolbox.xianduan import (  # noqa: E402
    XianDuanContext,
    XianDuanInvariants,
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
    parser = argparse.ArgumentParser(description="Phase 7 不变量违规统计")
    parser.add_argument("--dump-dir", type=Path, default=Path(settings.CACHE_DUMP_DIR))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--frequency", choices=tuple(SUPPORTED_CHART_FREQUENCIES))
    parser.add_argument("--market")
    parser.add_argument("--asset-class")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=_default_worker_count())
    parser.add_argument("--apply-repair", action="store_true", help="先跑实验性修复循环再检查")
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


def _prefix_counts(klines):
    prefix_merged = [0] * (len(klines) + 1)
    prefix_gap = [0] * (len(klines) + 1)
    for index, kline in enumerate(klines):
        prefix_merged[index + 1] = prefix_merged[index] + (
            1 if kline.merged_length == 1 else 0
        )
        prefix_gap[index + 1] = prefix_gap[index] + (1 if kline.has_gap else 0)
    return prefix_merged, prefix_gap


def audit_cache(
    cache_file: Path,
    dump_dir: Path,
    apply_repair: bool = False,
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
    klines = cache.merged_klines or []
    fenxing_list = cache.fenxing_list or []
    bi_list = list(cache.bi_list or [])
    tzxl_list = cache.te_zheng_xu_lie_list or []
    xd_list = list(cache.xian_duan_list or [])

    if apply_repair:
        # 从原始分型/笔重新生成，而不是在缓存结果上原地修复。
        # 这样才会包含 fake 首段/尾段等生成阶段结构。
        bi_list = generate_bi_with_repair_loop(
            fenxing_list,
            klines,
            initial_bis=None,
        )
        tzxl_list = generate_te_zheng_xu_lie(bi_list)
        xd_list = generate_xian_duan_with_repair_loop(
            tzxl_list,
            bi_list,
            initial_segments=None,
            use_local_resegment=use_local_resegment,
            allow_count_changing_repairs=False,
        )
        xd_list = postprocess_xian_duan(
            xd_list,
            cache.xian_duan_list,
            tzxl_list,
            bi_list,
            symbol=cache_file.stem,
            frequency=frequency,
        )

    prefix_merged, prefix_gap = _prefix_counts(klines)
    high_prices = np.array([kline.merged_high for kline in klines])
    low_prices = np.array([kline.merged_low for kline in klines])
    bi_ctx = BiContext(
        fenxing_list=fenxing_list,
        all_klines=klines,
        prefix_merged=prefix_merged,
        prefix_gap=prefix_gap,
        high_prices=high_prices,
        low_prices=low_prices,
        fenxing_by_time={fx.trade_datetime: fx for fx in fenxing_list},
    )
    bi_violations = BiInvariants(bi_ctx).check(bi_list)

    xd_ctx = XianDuanContext(
        bi_list=bi_list,
        tzxl_list=tzxl_list,
        bi_high_prices=np.array([bi.high_price for bi in bi_list]),
        bi_low_prices=np.array([bi.low_price for bi in bi_list]),
        tzxl_by_time_and_type={
            (tzxl.start_time, tzxl.is_top()): tzxl for tzxl in tzxl_list
        },
    )
    xd_violations = XianDuanInvariants(xd_ctx).check(xd_list)

    return {
        "path": str(cache_file.relative_to(dump_dir)),
        "symbol": cache_file.stem,
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "bi_count": len(bi_list),
        "xd_count": len(xd_list),
        "bi_violations": [
            {"code": item.code, "index": item.index, "detail": item.detail}
            for item in bi_violations
        ],
        "xd_violations": [
            {"code": item.code, "index": item.index, "detail": item.detail}
            for item in xd_violations
        ],
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if not args.dump_dir.exists():
        logger.error("缓存目录不存在: %s", args.dump_dir)
        return 1

    cache_files = collect_cache_files(args)
    if not cache_files:
        logger.warning("没有找到可检查的缓存: %s", args.dump_dir)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    worker_count = min(max(1, args.workers), len(cache_files))
    results = []
    failed = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                audit_cache,
                cache_file,
                args.dump_dir,
                args.apply_repair,
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
                logger.exception("检查失败: %s: %s", cache_file, error)

    results.sort(key=lambda item: item["path"])
    with args.output.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    bi_totals = Counter()
    xd_totals = Counter()
    bi_by_frequency = defaultdict(Counter)
    xd_by_frequency = defaultdict(Counter)
    examples = defaultdict(list)
    for item in results:
        for violation in item["bi_violations"]:
            code = f"bi:{violation['code']}"
            bi_totals[code] += 1
            bi_by_frequency[item["frequency"]][code] += 1
            if len(examples[code]) < 5:
                examples[code].append(
                    f"{item['path']} index={violation['index']} {violation['detail']}"
                )
        for violation in item["xd_violations"]:
            code = f"xd:{violation['code']}"
            xd_totals[code] += 1
            xd_by_frequency[item["frequency"]][code] += 1
            if len(examples[code]) < 5:
                examples[code].append(
                    f"{item['path']} index={violation['index']} {violation['detail']}"
                )

    summary = {
        "dump_dir": str(args.dump_dir),
        "checked": len(results),
        "failed": failed,
        "bi_totals": dict(bi_totals.most_common()),
        "xd_totals": dict(xd_totals.most_common()),
        "bi_by_frequency": {key: dict(value) for key, value in sorted(bi_by_frequency.items())},
        "xd_by_frequency": {key: dict(value) for key, value in sorted(xd_by_frequency.items())},
        "examples": {key: value for key, value in sorted(examples.items())},
    }
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    logger.info("检查完成: 成功 %d，失败 %d", len(results), failed)
    for code, count in bi_totals.most_common():
        logger.info("%s: %d", code, count)
    for code, count in xd_totals.most_common():
        logger.info("%s: %d", code, count)
    logger.info("明细: %s", args.output)
    logger.info("汇总: %s", args.summary)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
