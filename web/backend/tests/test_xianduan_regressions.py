"""缠论线段端点的代表性数据回归。"""
from pathlib import Path

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.toolbox.datacube import _DataCache

DATA_ROOT = Path(settings.DATA_DIR)


def _load_segments(symbol: str):
    source = DATA_ROOT / "freq=1day/market=cn/asset_class=stock" / f"{symbol}.pkl"
    _DataCache.reset_instance()
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
