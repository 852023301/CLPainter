import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    CACHE_DUMP_DIR,
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
)
from CLPainter.web.backend.app.toolbox.xianduan import (  # noqa: E402
    FakeXianDuanFirst,
    FakeXianDuanLast,
)

logger = logging.getLogger(__name__)


def _default_worker_count() -> int:
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


WORKER_BNUM = _default_worker_count()


def parse_args():
    parser = argparse.ArgumentParser(description="检查线段结构不变量")
    parser.add_argument("--dump-dir", type=Path, default=CACHE_DUMP_DIR)
    parser.add_argument("--frequency", choices=tuple(SUPPORTED_CHART_FREQUENCIES))
    parser.add_argument("--market")
    parser.add_argument("--asset-class")
    parser.add_argument("--symbol")
    parser.add_argument("--fail-on-violation", action="store_true")
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


def collect_cache_files(dump_dir: Path) -> list[Path]:
    return sorted(dump_dir.glob("freq=*/market=*/asset_class=*/*.pkl"))


def _check_segment_bounds(segment, bi_count: int) -> list[str]:
    errors = []
    if segment.start_bi_idx < 0 or segment.end_bi_idx >= bi_count:
        errors.append("index_bounds")
    elif segment.start_bi_idx > segment.end_bi_idx:
        errors.append("index_order")
    if segment.bi_count < 3:
        errors.append("min_bi_count")
    return errors


def _check_segment_extremes(segment, bi_list) -> list[str]:
    if segment.start_bi_idx < 0 or segment.end_bi_idx >= len(bi_list):
        return []
    covered = bi_list[segment.start_bi_idx:segment.end_bi_idx + 1]
    if not covered:
        return []
    errors = []
    true_high = max(float(bi.high_price) for bi in covered)
    true_low = min(float(bi.low_price) for bi in covered)
    if segment.is_up():
        if abs(float(segment.start_price) - true_low) > 1e-8:
            errors.append("start_not_low")
        if abs(float(segment.end_price) - true_high) > 1e-8:
            errors.append("end_not_high")
        if any(float(bi.end_price) < float(segment.start_price) - 1e-8 for bi in covered if bi.is_down()):
            errors.append("down_penetrates_start")
    else:
        if abs(float(segment.start_price) - true_high) > 1e-8:
            errors.append("start_not_high")
        if abs(float(segment.end_price) - true_low) > 1e-8:
            errors.append("end_not_low")
        if any(float(bi.end_price) > float(segment.start_price) + 1e-8 for bi in covered if bi.is_up()):
            errors.append("up_penetrates_start")
    return errors


def check_cache(cache_file: Path, dump_dir: Path) -> dict:
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        dump_dir,
    )
    segments = cache.xian_duan_list or []
    bi_list = cache.bi_list or []
    errors = []
    for index, segment in enumerate(segments):
        for error in _check_segment_bounds(segment, len(bi_list)):
            errors.append((error, index))
        is_fake = isinstance(segment, (FakeXianDuanFirst, FakeXianDuanLast))
        if not is_fake:
            for error in _check_segment_extremes(segment, bi_list):
                errors.append((error, index))
        if index and segments[index - 1].is_up() == segment.is_up():
            errors.append(("direction_not_alternating", index))
        if index and segments[index - 1].end_time != segment.start_time:
            errors.append(("not_continuous", index))
        if index and segments[index - 1].end_bi_idx + 1 != segment.start_bi_idx:
            errors.append(("bi_coverage_gap", index))
    return {
        "frequency": frequency,
        "market": market_dir,
        "asset_class": asset_class_dir,
        "code": cache_file.stem,
        "segments": len(segments),
        "errors": errors,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if not args.dump_dir.exists():
        logger.error("缓存目录不存在: %s", args.dump_dir)
        return 1

    cache_files = collect_cache_files(args.dump_dir)
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

    if not cache_files:
        logger.warning("没有找到可检查的缓存: %s", args.dump_dir)
        return 0

    totals = Counter()
    by_frequency = defaultdict(Counter)
    examples = defaultdict(list)
    checked = 0
    failed = 0
    worker_count = min(WORKER_BNUM, len(cache_files))

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(check_cache, cache_file, args.dump_dir): cache_file
            for cache_file in cache_files
        }
        for future in as_completed(futures):
            cache_file = futures[future]
            try:
                result = future.result()
            except Exception as error:
                failed += 1
                logger.exception("检查失败: %s: %s", cache_file, error)
                continue
            checked += 1
            if not result["errors"]:
                continue
            for error, index in result["errors"]:
                totals[error] += 1
                by_frequency[result["frequency"]][error] += 1
                if len(examples[error]) < 5:
                    examples[error].append(
                        f"{result['frequency']}/{result['market']}/{result['asset_class']}/"
                        f"{result['code']} segment={index}"
                    )

    logger.info("检查完成: 标的 %d，失败 %d", checked, failed)
    for error, count in totals.most_common():
        logger.info("%s: %d", error, count)
        for example in examples[error]:
            logger.info("  %s", example)
    for frequency, counts in sorted(by_frequency.items()):
        logger.info("%s: %s", frequency, dict(counts))

    if args.fail_on_violation and totals:
        return 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
