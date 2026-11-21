import argparse
import logging
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.cl_state import build_snapshot_record, persist_snapshots
from CLPainter.web.backend.app.db.base import engine
from CLPainter.web.backend.app.screener.history import (
    archive_due_presets,
    as_date,
    require_pipeline_ready,
)
from CLPainter.web.backend.app.toolbox.datacube import (
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
    parser.add_argument("--archive-screener", action="store_true", help="完整更新成功后归档到期选股方案")
    args = parser.parse_args()
    if args.archive_screener and any((args.frequency, args.market, args.asset_class, args.symbol)):
        parser.error("自动归档必须使用完整更新，不能与周期/市场/种类/标的筛选组合")
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


def load_instrument_identities() -> set[tuple[str, str, str]]:
    """独立只读连接在启动 worker 前关闭，不将元数据连接带入子进程。"""
    database = Path(settings.DB_PATH).resolve()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=30)) as connection:
        return set(connection.execute("SELECT market, asset_class, code FROM instrument").fetchall())


def filter_registered_caches(cache_files: list[Path], identities: set[tuple[str, str, str]]) -> list[Path]:
    """保留元数据中已登记的缓存；孤立文件只告警，不删除或伪造状态。"""
    registered = []
    for path in cache_files:
        _, market_dir, asset_class_dir = cache_metadata(path)
        key = (market_dir.removeprefix("market="), asset_class_dir.removeprefix("asset_class="), path.stem)
        if key in identities:
            registered.append(path)
        else:
            logger.warning("忽略未登记标的的遗留缓存（保留原文件）: %s", path)
    logger.info("归档缓存范围: 已登记 %d，未登记 %d", len(registered), len(cache_files) - len(registered))
    return registered


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
    record = build_snapshot_record(
        cache,
        code=cache_file.stem,
        frequency=frequency.removeprefix("freq="),
        market=market_dir.removeprefix("market="),
        asset_class=asset_class_dir.removeprefix("asset_class="),
    )
    raw_data = cache.__dict__.get("_raw_data")
    record["data_trade_date"] = as_date(raw_data[-1][0]).isoformat() if raw_data else None
    return record


def main() -> int:
    """批量更新状态快照。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    if args.archive_screener and not os.environ.get("CLPAINTER_PIPELINE_STARTED_AT"):
        logger.error("自动归档只能由完整更新流水线触发，缺少流水线开始时间")
        return 1
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

    if args.archive_screener:
        try:
            cache_files = filter_registered_caches(cache_files, load_instrument_identities())
        except (sqlite3.Error, ValueError):
            logger.exception("无法确认标的元数据或缓存身份，未进行自动归档")
            return 1

    if not cache_files:
        logger.warning("没有找到可处理的状态缓存: %s", args.dump_dir)
        return 1 if args.archive_screener else 0

    records = []
    failures = []
    skipped_count = 0
    total_count = len(cache_files)
    worker_count = min(WORKER_BNUM, total_count)

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(state_worker, cache_file, args.dump_dir): cache_file for cache_file in cache_files}
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
    if args.archive_screener:
        if skipped_count or missing_count:
            logger.error("批次不完整，未归档任何选股结果: 跳过 %d，缺少 instrument %d", skipped_count, missing_count)
            return 1
        try:
            require_pipeline_ready(records, os.environ.get("CLPAINTER_PIPELINE_STARTED_AT"))
            report = archive_due_presets(engine, records)
        except Exception:
            logger.exception("选股结果归档失败，未将失败结果保存为空名单")
            return 1
        if report["failed"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
