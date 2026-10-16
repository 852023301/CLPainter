"""从 info 表同步当前有效标的元数据到 SQLite。"""

import datetime
from pathlib import Path
import sys

from ddp import MysqlConnection
from sqlalchemy import select
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.db.base import engine
from CLPainter.web.backend.app.db.models import Instrument

BACKEND_DIR = Path(__file__).resolve().parents[1]
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


def query_active_info(config: dict) -> list[Instrument]:
    """按原脚本的日期条件读取当前有效标的。"""
    today = datetime.date.today()
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


def sync_asset_class(config: dict) -> tuple[int, int]:
    """用当前 info 表结果整体替换同一资产类型的元数据。"""
    instruments = query_active_info(config)
    instruments_by_identity = {
        (instrument.market, instrument.asset_class, instrument.code): instrument
        for instrument in instruments
    }
    active_codes = {instrument.code for instrument in instruments}

    with Session(engine) as session:
        stale_instruments = session.scalars(
            select(Instrument).where(
                Instrument.market == MARKET,
                Instrument.asset_class == config["asset_class"],
                Instrument.code.not_in(active_codes),
            )
        ).all()
        stale_count = len(stale_instruments)
        for instrument in stale_instruments:
            session.delete(instrument)

        existing_map = {
            (instrument.market, instrument.asset_class, instrument.code): instrument
            for instrument in session.scalars(
                select(Instrument).where(
                    Instrument.market == MARKET,
                    Instrument.asset_class == config["asset_class"],
                )
            ).all()
        }
        for identity, instrument in instruments_by_identity.items():
            existing = existing_map.get(identity)
            if existing is None:
                session.add(instrument)
                existing_map[identity] = instrument
                continue
            existing.name = instrument.name
            existing.display_name = instrument.display_name
            existing.price_precision = instrument.price_precision
            existing.list_date = instrument.list_date
            existing.delist_date = instrument.delist_date
        session.commit()

    return stale_count, len(instruments)


def main() -> None:
    for label, config in ASSET_CLASS_CONFIG.items():
        stale_count, active_count = sync_asset_class(config)
        print(
            f"{label}: 当前有效 {active_count}，清理失效 {stale_count}，"
            f"asset_class={config['asset_class']}"
        )


if __name__ == "__main__":
    main()
