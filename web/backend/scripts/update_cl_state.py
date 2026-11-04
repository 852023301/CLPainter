import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.cl_state import build_snapshot_record, persist_snapshots  # noqa: E402
from CLPainter.web.backend.app.toolbox.datacube import (  # noqa: E402
    CACHE_DUMP_DIR,
    SUPPORTED_CHART_FREQUENCIES,
    load_data_cache_pickle,
)

logger = logging.getLogger(__name__)


def _default_worker_count() -> int:
    """按当前可用 CPU 数的一半设置进程数。"""
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


WORKER_BNUM = _default_worker_count()


def parse_args():
    """解析状态更新参数。"""
    parser = argparse.ArgumentParser(description="从完整 _DataCache 更新缠论状态快照")
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=CACHE_DUMP_DIR,
        help="完整 _DataCache 根目录，默认使用 CACHE_DUMP_DIR",
    )
    parser.add_argument(
        "--frequency",
        choices=tuple(SUPPORTED_CHART_FREQUENCIES),
        help="只处理指定周期，例如 freq=1day；默认处理全部周期",
    )
    parser.add_argument("--market", help="只处理指定市场，例如 cn")
    parser.add_argument("--asset-class", help="只处理指定资产类别，例如 stock")
    parser.add_argument("--symbol", help="只处理单一标的，例如 600713SH")
    args = parser.parse_args()
    if args.market:
        args.market = args.market.removeprefix("market=")
    if args.asset_class:
        args.asset_class = args.asset_class.removeprefix("asset_class=")
    if args.symbol and (not args.market or not args.asset_class):
        parser.error("指定 --symbol 时必须同时指定 --market 和 --asset-class")
    return args


def cache_metadata(cache_file: Path) -> tuple[str, str, str]:
    """从缓存路径识别周期、市场和资产类别。"""
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
    """收集完整 _DataCache 文件。"""
    return sorted(dump_dir.glob("freq=*/market=*/asset_class=*/*.pkl"))


def state_worker(cache_file: Path, dump_dir: Path) -> dict:
    """读取单个完整 _DataCache 并构造状态记录。"""
    frequency, market_dir, asset_class_dir = cache_metadata(cache_file)
    cache = load_data_cache_pickle(
        cache_file.stem,
        frequency,
        market_dir,
        asset_class_dir,
        dump_dir,
    )
    if "_bi_zhongshu_raw_list" not in cache.__dict__:
        return None
    return build_snapshot_record(
        cache,
        code=cache_file.stem,
        frequency=frequency.removeprefix("freq="),
        market=market_dir.removeprefix("market="),
        asset_class=asset_class_dir.removeprefix("asset_class="),
    )


def main() -> int:
    """批量更新状态快照。"""
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
        logger.warning("没有找到可处理的状态缓存: %s", args.dump_dir)
        return 0

    records = []
    failures = []
    skipped_count = 0
    total_count = len(cache_files)
    worker_count = min(WORKER_BNUM, total_count)

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(state_worker, cache_file, args.dump_dir): cache_file
            for cache_file in cache_files
        }
        for index, future in enumerate(as_completed(futures), start=1):
            cache_file = futures[future]
            try:
                record = future.result()
                if record is None:
                    skipped_count += 1
                    logger.warning("[%d/%d] 跳过无分析字段的缓存: %s", index, total_count, cache_file)
                    continue
                records.append(record)
                logger.info("[%d/%d] 状态 %s", index, total_count, cache_file.name)
            except Exception as error:
                failures.append(f"{cache_file}: {type(error).__name__}: {error}")
                logger.exception("[%d/%d] 状态失败: %s", index, total_count, cache_file)

    missing_count = persist_snapshots(records)
    logger.info(
        "状态更新完成: 成功 %d，跳过 %d，失败 %d，找不到 instrument %d，总计 %d",
        len(records),
        skipped_count,
        len(failures),
        missing_count,
        total_count,
    )
    if failures:
        logger.error("失败明细:\n%s", "\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
