"""Phase 7 人工抽查案例的自动复核。

检查旧/新 curated 中是否保留了用户确认过的标准线段，并确认
159577SZ 的反向延长 fake 段已经恢复。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.toolbox.datacube import load_data_cache_pickle  # noqa: E402

CASES = [
    {
        "symbol": "600996SH",
        "asset_class": "asset_class=stock",
        "expect": [("2024-11-08", "2025-04-09", "XianDuan")],
    },
    {
        "symbol": "300353SZ",
        "asset_class": "asset_class=stock",
        "expect": [],
    },
    {
        "symbol": "000750SZ",
        "asset_class": "asset_class=stock",
        "expect": [("2024-10-09", "2025-04-09", "XianDuan")],
    },
    {
        "symbol": "600015SH",
        "asset_class": "asset_class=stock",
        "expect": [
            ("2023-06-26", "2025-07-10", "XianDuan"),
            ("2025-07-10", "2026-08-31", "XianDuan"),
        ],
    },
    {
        "symbol": "600713SH",
        "asset_class": "asset_class=stock",
        "expect": [("2024-12-16", "2025-04-09", "XianDuan")],
    },
    {
        "symbol": "000001SZ",
        "asset_class": "asset_class=stock",
        "expect": [
            ("2025-04-07", "2025-07-10", "XianDuan"),
            ("2025-07-10", "2026-07-01", "XianDuan"),
        ],
    },
    {
        "symbol": "603683SH",
        "asset_class": "asset_class=stock",
        "expect": [("2024-02-08", "2025-09-25", "XianDuan")],
    },
    {
        "symbol": "159577SZ",
        "asset_class": "asset_class=fund",
        "expect": [("2024-04-22", "2025-01-07", "FakeXianDuanFirst")],
    },
    {
        "symbol": "159301SZ",
        "asset_class": "asset_class=fund",
        "forbid": [("2026-05-14", "2026-07-09", "XianDuan")],
    },
    {
        "symbol": "159612SZ",
        "asset_class": "asset_class=fund",
        "expect": [("2023-01-06", "2025-03-24", "XianDuan")],
    },
    {
        "symbol": "159843SZ",
        "asset_class": "asset_class=fund",
        "expect": [("2025-08-26", "2026-06-29", "XianDuan")],
    },
]


def _rows(cache) -> list[tuple[str, str, str]]:
    return [
        (
            segment.start_time.strftime("%Y-%m-%d"),
            segment.end_time.strftime("%Y-%m-%d"),
            type(segment).__name__,
        )
        for segment in (cache.xian_duan_list or [])
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 抽查案例复核")
    parser.add_argument("--dump-dir", type=Path, required=True)
    parser.add_argument("--frequency", default="freq=1day")
    parser.add_argument("--market", default="market=cn")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures = 0
    for case in CASES:
        cache = load_data_cache_pickle(
            case["symbol"],
            args.frequency,
            args.market,
            case["asset_class"],
            args.dump_dir,
        )
        rows = _rows(cache)
        for expected in case.get("expect", []):
            ok = expected in rows
            failures += 0 if ok else 1
            print(
                f"{'PASS' if ok else 'FAIL'} {case['symbol']} expect {expected} "
                f"rows={rows}"
            )
        for forbidden in case.get("forbid", []):
            ok = forbidden not in rows
            failures += 0 if ok else 1
            print(
                f"{'PASS' if ok else 'FAIL'} {case['symbol']} forbid {forbidden} "
                f"rows={rows}"
            )
    print(f"spot check failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
