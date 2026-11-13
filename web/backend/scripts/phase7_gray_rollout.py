"""Phase 7 灰度验证：用原始数据重新计算，和 curated 旧结果对比。

不写入 curated，只输出报告。
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

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app._config.settings import settings  # noqa: E402
from CLPainter.web.backend.app.toolbox.bi import (  # noqa: E402
    BiContext,
    BiInvariants,
)
from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    SUPPORTED_CHART_FREQUENCIES,
    _DataCache,
    load_data_cache_pickle,
)
from CLPainter.web.backend.app.toolbox.xianduan import (  # noqa: E402
    XianDuanContext,
    XianDuanInvariants,
)

logger = logging.getLogger(__name__)

TARGET_SYMBOLS = {
    "600015SH",
    "000001SH",
    "000001SZ",
    "603683SH",
    "159870SZ",
    "688549SH",
    "560100SH",
    "300139SZ",
    "002080SZ",
    "600127SH",
    "600113SH",
    "600312SH",
    "159612SZ",
    "601116SH",
    "159843SZ",
    "159936SZ",
    "159301SZ",
    "159577SZ",
}


def _default_worker_count() -> int:
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 灰度验证")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--per-group", type=int, default=20)
    parser.add_argument("--workers", type=int, default=_default_worker_count())
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


def select_cache_files(sample_size: int, per_group: int) -> list[Path]:
    dump_dir = Path(settings.CACHE_DUMP_DIR)
    all_files = sorted(dump_dir.glob("freq=*/market=*/asset_class=*/*.pkl"))
    groups = defaultdict(list)
    for path in all_files:
        frequency, market_dir, asset_class_dir = cache_metadata(path)
        groups[(frequency, market_dir, asset_class_dir)].append(path)

    selected = []
    for key in sorted(groups):
        selected.extend(groups[key][:per_group])

    existing = {path.stem for path in selected}
    for path in all_files:
        if path.stem in TARGET_SYMBOLS and path.stem not in existing:
            selected.append(path)
            existing.add(path.stem)

    selected = sorted(set(selected))[:sample_size]
    return selected


def _canonical_bi(bi) -> list:
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


def _canonical_xd(segment) -> list:
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


def _prefix_counts(klines):
    prefix_merged = [0] * (len(klines) + 1)
    prefix_gap = [0] * (len(klines) + 1)
    for index, kline in enumerate(klines):
        prefix_merged[index + 1] = prefix_merged[index] + (
            1 if kline.merged_length == 1 else 0
        )
        prefix_gap[index + 1] = prefix_gap[index] + (1 if kline.has_gap else 0)
    return prefix_merged, prefix_gap


def _violations_for(cache, bi_list, xd_list):
    klines = cache.merged_klines or []
    fenxing_list = cache.fenxing_list or []
    tzxl_list = cache.te_zheng_xu_lie_list or []
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
    return bi_violations, xd_violations


def check_cache(cache_file: Path) -> dict:
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    symbol = cache_file.stem

    old_cache = load_data_cache_pickle(
        symbol,
        frequency,
        market_dir,
        asset_class_dir,
        Path(settings.CACHE_DUMP_DIR),
    )
    old_bis = list(old_cache.bi_list or [])
    old_xds = list(old_cache.xian_duan_list or [])
    old_bi_canon = [_canonical_bi(bi) for bi in old_bis]
    old_xd_canon = [_canonical_xd(segment) for segment in old_xds]

    source = (
        Path(settings.DATA_DIR)
        / frequency
        / market_dir
        / asset_class_dir
        / f"{symbol}.pkl"
    )
    new_cache = _DataCache(source)
    new_cache.ensure_loaded()
    new_bis = list(new_cache.bi_list or [])
    new_xds = list(new_cache.xian_duan_list or [])
    new_bi_canon = [_canonical_bi(bi) for bi in new_bis]
    new_xd_canon = [_canonical_xd(segment) for segment in new_xds]

    old_bi_v, old_xd_v = _violations_for(old_cache, old_bis, old_xds)
    new_bi_v, new_xd_v = _violations_for(new_cache, new_bis, new_xds)

    return {
        "path": str(cache_file.relative_to(Path(settings.CACHE_DUMP_DIR))),
        "symbol": symbol,
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "bi_changed": old_bi_canon != new_bi_canon,
        "xd_changed": old_xd_canon != new_xd_canon,
        "old_bi_count": len(old_bis),
        "new_bi_count": len(new_bis),
        "old_xd_count": len(old_xds),
        "new_xd_count": len(new_xds),
        "old_bi_violations": [item.code for item in old_bi_v],
        "new_bi_violations": [item.code for item in new_bi_v],
        "old_xd_violations": [item.code for item in old_xd_v],
        "new_xd_violations": [item.code for item in new_xd_v],
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    cache_files = select_cache_files(args.sample_size, args.per_group)
    if not cache_files:
        logger.warning("没有选中任何缓存")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    worker_count = min(max(1, args.workers), len(cache_files))
    results = []
    failed = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(check_cache, path): path for path in cache_files}
        for future in as_completed(futures):
            path = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                failed += 1
                logger.exception("检查失败: %s: %s", path, error)

    results.sort(key=lambda item: item["path"])
    with args.output.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "dump_dir": settings.CACHE_DUMP_DIR,
        "data_dir": settings.DATA_DIR,
        "checked": len(results),
        "failed": failed,
        "bi_changed": sum(1 for item in results if item["bi_changed"]),
        "xd_changed": sum(1 for item in results if item["xd_changed"]),
        "old_bi_violations": dict(Counter(
            code for item in results for code in item["old_bi_violations"]
        )),
        "new_bi_violations": dict(Counter(
            code for item in results for code in item["new_bi_violations"]
        )),
        "old_xd_violations": dict(Counter(
            code for item in results for code in item["old_xd_violations"]
        )),
        "new_xd_violations": dict(Counter(
            code for item in results for code in item["new_xd_violations"]
        )),
    }
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info("灰度验证完成: 成功 %d，失败 %d", len(results), failed)
    logger.info("bi_changed=%d xd_changed=%d", summary["bi_changed"], summary["xd_changed"])
    logger.info("old_xd_violations=%s", summary["old_xd_violations"])
    logger.info("new_xd_violations=%s", summary["new_xd_violations"])
    logger.info("明细: %s", args.output)
    logger.info("汇总: %s", args.summary)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
