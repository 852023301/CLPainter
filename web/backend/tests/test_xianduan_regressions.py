"""缠论线段端点的代表性数据回归。"""
from pathlib import Path

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.toolbox.datacube import _DataCache

DATA_ROOT = Path(settings.DATA_DIR)


def _load_segments(symbol: str, frequency: str = "freq=1day", asset_class: str = "asset_class=stock"):
    source = DATA_ROOT / frequency / "market=cn" / asset_class / f"{symbol}.pkl"
    cache = _DataCache(source)
    cache.ensure_loaded()
    return cache.xian_duan_list


def test_600015sh_daily_first_two_segments_use_confirmed_boundaries():
    segments = _load_segments("600015SH")
    actual = [(str(segment.start_time.date()), str(segment.end_time.date())) for segment in segments[:2]]
    assert actual == [
        ("2004-02-06", "2005-07-12"),
        ("2005-07-12", "2007-10-16"),
    ]


def test_603683sh_daily_tail_splits_at_2025_09_25_and_fakes_to_2026_10_19():
    segments = _load_segments("603683SH")
    actual = [
        (str(segment.start_time.date()), str(segment.end_time.date()), type(segment).__name__)
        for segment in segments[-2:]
    ]
    assert actual == [
        ("2024-02-08", "2025-09-25", "XianDuan"),
        ("2025-09-25", "2026-10-19", "FakeXianDuanLast"),
    ]


def test_159870sz_weekly_has_down_and_up_fake_segments():
    segments = _load_segments("159870SZ", "freq=1week", "asset_class=fund")
    actual = [
        (
            str(segment.start_time.date()),
            str(segment.end_time.date()),
            type(segment).__name__,
            segment.is_up(),
        )
        for segment in segments
    ]
    assert actual == [
        ("2021-09-17", "2024-02-08", "FakeXianDuanLast", False),
        ("2024-02-08", "2026-03-06", "FakeXianDuanLast", True),
    ]


def _assert_segments(symbol, frequency, asset_class, expected):
    segments = _load_segments(symbol, frequency, asset_class)
    actual = [
        (str(segment.start_time.date()), str(segment.end_time.date()), type(segment).__name__, segment.is_up())
        for segment in segments
    ]
    assert actual == expected


def test_688549sh_weekly_prefix_and_extended_tail():
    _assert_segments(
        "688549SH",
        "freq=1week",
        "asset_class=stock",
        [
            ("2023-09-08", "2024-09-20", "FakeXianDuanLast", False),
            ("2024-09-20", "2026-07-03", "FakeXianDuanLast", True),
        ],
    )


def test_fallback_tail_penetrated_by_later_same_direction_bi_does_not_split():
    _assert_segments(
        "560100SH",
        "freq=1week",
        "asset_class=fund",
        [("2024-02-08", "2026-07-03", "FakeXianDuanLast", True)],
    )
    _assert_segments(
        "300139SZ",
        "freq=1month",
        "asset_class=stock",
        [("2018-02-28", "2026-03-31", "FakeXianDuanLast", True)],
    )
    _assert_segments(
        "002080SZ",
        "freq=1month",
        "asset_class=stock",
        [("2012-12-31", "2026-06-30", "FakeXianDuanLast", True)],
    )
