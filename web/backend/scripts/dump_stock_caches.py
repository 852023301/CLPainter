import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
import sys
from pathlib import Path

import urllib.request

WORKER_BNUM = 50
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app._config.settings import settings  # noqa: E402
from CLPainter.web.backend.app.api.api_v1.endpoints import (  # noqa: E402
    CACHE_DUMP_DIR,
    dump_data_cache_to_pickle,
)


logger = logging.getLogger(__name__)

DEFAULT_SOURCE_DIRS = (
    "all_stocks",
    "all_index",
    "all_etf",
)
FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/361adc1b-4da1-451d-b881-14b038f938c3"
FEISHU_FAILURE_BATCH_SIZE = 30
MAX_FAILURE_REASON_LENGTH = 500


def parse_args():
    parser = argparse.ArgumentParser(description="批量导出股票 _DataCache pickle 文件")
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        type=Path,
        default=[Path(settings.DATA_DIR) / name for name in DEFAULT_SOURCE_DIRS],
        help="原始 pickle 文件目录，默认包含 all_stocks、all_index 和 all_etf",
    )
    parser.add_argument("--symbol", help="只导出单一标的，例如 600713SH")
    return parser.parse_args()


def dump_worker(source_file: Path, dump_dir: Path) -> None:
    dump_data_cache_to_pickle(source_file, dump_dir)


def collect_source_files(source_dirs: list[Path]) -> list[Path]:
    source_files_by_stem: dict[str, Path] = {}
    for source_dir in source_dirs:
        for source_file in source_dir.glob("*.pkl"):
            existing_file = source_files_by_stem.setdefault(source_file.stem, source_file)
            if existing_file != source_file:
                raise ValueError(f"输出文件名冲突: {existing_file} 和 {source_file}")

    return sorted(source_files_by_stem.values(), key=lambda item: item.stem)


def send_feishu_text(text: str) -> None:
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    request = urllib.request.Request(
        FEISHU_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("code") not in (None, 0):
        raise RuntimeError(f"Feishu 返回错误: {result}")


def notify_failures_to_feishu(total_count: int, success_count: int, failures: list[str]) -> None:
    summary = f"CLPainter 缓存导出失败汇总\n总数: {total_count}\n成功: {success_count}\n失败: {len(failures)}"
    if not failures:
        send_feishu_text(summary)
        return

    for start_index in range(0, len(failures), FEISHU_FAILURE_BATCH_SIZE):
        batch = failures[start_index:start_index + FEISHU_FAILURE_BATCH_SIZE]
        end_index = start_index + len(batch)
        message = f"{summary}\n失败明细: {start_index + 1}-{end_index}\n" + "\n".join(batch)
        send_feishu_text(message)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()

    invalid_dirs = [source_dir for source_dir in args.source_dirs if not source_dir.exists()]
    if invalid_dirs:
        logger.error("源数据目录不存在: %s", ", ".join(map(str, invalid_dirs)))
        return 1

    try:
        source_files = collect_source_files(args.source_dirs)
    except ValueError as error:
        logger.error(str(error))
        return 1

    if not source_files:
        logger.warning("源数据目录中没有 pickle 文件: %s", ", ".join(map(str, args.source_dirs)))
        return 0

    if args.symbol:
        symbol_stem = Path(args.symbol).stem
        source_files = [item for item in source_files if item.stem == symbol_stem]
        if not source_files:
            logger.error("在指定源目录中找不到标的: %s", args.symbol)
            return 1

    success_count = 0
    failure_count = 0
    failures: list[str] = []
    total_count = len(source_files)
    worker_count = min(WORKER_BNUM, total_count)

    with ProcessPoolExecutor(
        max_workers=worker_count,
    ) as executor:
        futures = {
            executor.submit(dump_worker, source_file, CACHE_DUMP_DIR): source_file
            for source_file in source_files
        }

        for index, future in enumerate(as_completed(futures), start=1):
            source_file = futures[future]
            try:
                future.result()
                success_count += 1
                logger.info("[%d/%d] 导出 %s", index, total_count, source_file.name)
            except Exception as error:
                failure_count += 1
                reason = str(error)
                if len(reason) > MAX_FAILURE_REASON_LENGTH:
                    reason = f"{reason[:MAX_FAILURE_REASON_LENGTH]}..."
                failures.append(f"{source_file.name}: {type(error).__name__}: {reason}")
                logger.exception("[%d/%d] 导出失败: %s", index, total_count, source_file.name)

    logger.info(
        "导出完成: 成功 %d，失败 %d，总计 %d",
        success_count,
        failure_count,
        total_count,
    )

    if failures:
        logger.error("失败明细:\n%s", "\n".join(failures))
        try:
            notify_failures_to_feishu(total_count, success_count, failures)
        except Exception as notify_error:
            logger.exception("发送 Feishu 失败汇总失败: %s", notify_error)

    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
