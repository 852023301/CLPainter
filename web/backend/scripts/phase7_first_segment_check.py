"""检查首段 fake/real 修复是否符合预期。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.toolbox.datacube import _DataCache, load_data_cache_pickle  # noqa: E402

OLD_ROOT = Path("/mnt/DataDepartmentTest/home/wjl/data_set/dump/curated")
RAW_ROOT = Path("/mnt/DataDepartmentTest/home/wjl/data_set/pv_data")

ASSET_CLASS = {
    "000750SZ": "asset_class=stock",
    "300265SZ": "asset_class=stock",
    "159663SZ": "asset_class=fund",
    "510560SH": "asset_class=fund",
    "159518SZ": "asset_class=fund",
}

CASES = {
    "000750SZ": [
        ("FakeXianDuanFirst", "1997-07-15", "1997-08-21"),
        ("XianDuan", "1997-08-21", "1998-01-08"),
        ("XianDuan", "1998-01-08", "1999-12-29"),
    ],
    "300265SZ": [
        ("FakeXianDuanFirst", "2011-09-16", "2013-06-25"),
        ("XianDuan", "2013-06-25", "2015-05-27"),
    ],
    "159663SZ": [
        ("FakeXianDuanFirst", "2022-10-31", "2023-02-08"),
        ("XianDuan", "2023-02-08", "2024-02-05"),
    ],
    "510560SH": [
        ("FakeXianDuanFirst", "2015-07-09", "2017-03-21"),
        ("XianDuan", "2017-03-21", "2018-10-19"),
    ],
    "159518SZ": [
        ("FakeXianDuanFirst", "2023-11-15", "2023-12-13"),
        ("XianDuan", "2023-12-13", "2024-07-18"),
        ("XianDuan", "2024-07-18", "2025-04-09"),
    ],
}


def _rows(segments):
    return [
        (
            type(segment).__name__,
            segment.start_time.strftime("%Y-%m-%d"),
            segment.end_time.strftime("%Y-%m-%d"),
        )
        for segment in segments
    ]


def main() -> int:
    failures = 0
    for symbol, expected in CASES.items():
        asset_class = ASSET_CLASS[symbol]
        old = load_data_cache_pickle(
            symbol, "freq=1day", "market=cn", asset_class, OLD_ROOT
        )
        source = RAW_ROOT / "freq=1day" / "market=cn" / asset_class / f"{symbol}.pkl"
        cache = _DataCache(source, reference_xian_duan_list=old.xian_duan_list)
        cache.ensure_loaded()
        actual = _rows(cache.xian_duan_list[: len(expected)])
        ok = actual == expected
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {symbol} actual={actual} expected={expected}")
    print(f"first segment failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
