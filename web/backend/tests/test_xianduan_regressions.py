"""缠论线段端点的代表性数据回归。"""
from pathlib import Path

from CLPainter.web.backend.app.toolbox.datacube import _DataCache

DATA_ROOT = Path("/DataDepartmentTest/wjl/data_set/pv_data")


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
