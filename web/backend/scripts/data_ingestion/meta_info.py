"""从 info 表同步当前有效标的元数据到 SQLite。"""

import argparse
import datetime
import os
import sys
from pathlib import Path

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.data_lifecycle import (
    CODE,
    managed_roots,
    resolve_processing_date,
    write_metadata_report,
)
from CLPainter.web.backend.app.db.base import engine
from CLPainter.web.backend.app.db.models import Instrument
from ddp import MysqlConnection
from sqlalchemy import func, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR.parent.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR.parent.parent))

MARKET = "cn"
ASSET_CLASS_CONFIG = {
    "stock": {
        "table": "stock_info",
        "code_column": "stock_code",
        "name_column": "name",
        "display_name_column": "display_name",
        "asset_class": "stock",
        "precision": 2,
    },
    "index": {
        "table": "index_info",
        "code_column": "index_code",
        "name_column": "name",
        "display_name_column": "display_name",
        "asset_class": "index",
        "precision": 2,
    },
    "etf": {
        "table": "etf_info",
        "code_column": "stock_code",
        "name_column": "name",
        "display_name_column": "display_name",
        "asset_class": "fund",
        "precision": 3,
    },
}


def chart_code(source_code: str) -> str:
    """将 000001.SZ 转成图表使用的 000001SZ。"""
    return source_code.replace(".", "")


def query_active_info(config: dict, as_of: datetime.date | None = None) -> list[Instrument]:
    """按原脚本的日期条件读取当前有效标的。"""
    today = as_of or resolve_processing_date(os.getenv("CLPAINTER_AS_OF"))
    with MysqlConnection() as sql:
        frame = sql.query_pandas(
            f"SELECT {config['code_column']} AS source_code, "
            f"{config['name_column'] or config['code_column']} AS source_name, "
            f"{config['display_name_column'] or config['code_column']} AS source_display_name, "
            "start_date "
            f"FROM {config['table']} "
            f"WHERE start_date <= '{today}' AND end_date > '{today}'"
        )

    instruments = []
    for row in frame.itertuples(index=False):
        source_code = str(row[0])
        source_name = str(row[1]).strip()
        source_display_name = str(row[2]).strip() or source_name
        list_date = row[3].date() if hasattr(row[3], "date") else row[3]
        instruments.append(
            Instrument(
                code=chart_code(source_code),
                name=source_name or source_display_name,
                display_name=source_display_name,
                price_precision=config["precision"],
                market=MARKET,
                asset_class=config["asset_class"],
                list_date=list_date,
                delist_date=None,
            )
        )
    return instruments


def _validate_instruments(
    config: dict, instruments: list[Instrument], previous_count: int, max_drop_ratio: float
) -> None:
    if not 0 <= max_drop_ratio <= 1:
        raise ValueError("max_drop_ratio must be between zero and one")
    codes = [item.code for item in instruments]
    if (
        not codes
        or len(codes) != len(set(codes))
        or any(
            not isinstance(code, str) or code.lower() in {"none", "nan", "nat"} or not CODE.fullmatch(code)
            for code in codes
        )
    ):
        raise ValueError("元数据为空、重复或代码无效，拒绝同步及后续清理")
    if any(item.market != MARKET or item.asset_class != config["asset_class"] for item in instruments):
        raise ValueError("上游元数据返回了错误的市场或资产范围")
    if previous_count and len(codes) < previous_count * (1 - max_drop_ratio):
        raise ValueError("元数据数量骤降超过安全阈值，请人工核对上游后再同步")


def _sync_instruments(session: Session, config: dict, instruments: list[Instrument]) -> tuple[int, int]:
    incoming = {item.code: item for item in instruments}
    current = {
        item.code: item
        for item in session.scalars(
            select(Instrument).where(
                Instrument.market == MARKET,
                Instrument.asset_class == config["asset_class"],
            )
        )
    }
    stale_count = 0
    for code, item in current.items():
        if code not in incoming:
            session.delete(item)
            stale_count += 1
    for code, item in incoming.items():
        existing = current.get(code)
        if existing is None:
            session.add(item)
        else:
            for field in ("name", "display_name", "price_precision", "list_date", "delist_date"):
                setattr(existing, field, getattr(item, field))
    return stale_count, len(incoming)


def sync_asset_class(config: dict, as_of: datetime.date | None = None, max_drop_ratio: float = 0.2) -> tuple[int, int]:
    """兼容单类同步调用；同样先验证，不允许空名单清空元数据。"""
    managed_roots(settings)
    instruments = query_active_info(config, as_of)
    with Session(engine) as session:
        previous = session.scalar(
            select(func.count())
            .select_from(Instrument)
            .where(
                Instrument.market == MARKET,
                Instrument.asset_class == config["asset_class"],
            )
        )
        _validate_instruments(config, instruments, previous, max_drop_ratio)
        result = _sync_instruments(session, config, instruments)
        session.commit()
    return result


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="校验并原子同步完整元数据，供统一清理使用")
    parser.add_argument("--as-of", default=os.getenv("CLPAINTER_AS_OF"), help="本批处理交易日 YYYY-MM-DD")
    parser.add_argument(
        "--report", type=Path, default=os.getenv("CLPAINTER_METADATA_REPORT"), help="完整元数据批次清单"
    )
    parser.add_argument("--max-drop-ratio", type=float, default=0.2, help="允许的元数据数量下降比例，默认 0.2")
    args = parser.parse_args(argv)
    if not 0 <= args.max_drop_ratio <= 1:
        parser.error("--max-drop-ratio 必须在 0 与 1 之间")
    managed_roots(settings)
    as_of = resolve_processing_date(args.as_of)
    # 所有上游查询都完成之后再开始数据库事务，避免部分范围已清空、其他范围却失败。
    prepared = [(label, config, query_active_info(config, as_of)) for label, config in ASSET_CLASS_CONFIG.items()]
    with Session(engine) as session:
        for _, config, instruments in prepared:
            previous = session.scalar(
                select(func.count())
                .select_from(Instrument)
                .where(
                    Instrument.market == MARKET,
                    Instrument.asset_class == config["asset_class"],
                )
            )
            _validate_instruments(config, instruments, previous, args.max_drop_ratio)
        results = [
            (label, config, _sync_instruments(session, config, instruments)) for label, config, instruments in prepared
        ]
        session.commit()
    if args.report:
        write_metadata_report(
            args.report, settings, engine, as_of, [(MARKET, config["asset_class"]) for _, config, _ in prepared]
        )
    print(f"元数据处理日期: {as_of}")
    for label, config, (stale_count, active_count) in results:
        print(f"{label}: 当前有效 {active_count}，清理失效 {stale_count}，asset_class={config['asset_class']}")


if __name__ == "__main__":
    main()
