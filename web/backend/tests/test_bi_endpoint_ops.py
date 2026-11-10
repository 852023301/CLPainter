"""笔端点工厂测试。"""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from CLPainter.web.backend.app.toolbox.bi import BiContext, BiDirectionType, BiEndpointOps


def _klines():
    return [
        SimpleNamespace(
            trade_datetime=pd.Timestamp(f"2024-01-0{i + 1}"),
            merged_high=10.0 + i,
            merged_low=8.0 + i,
            merged_length=1,
            has_gap=False,
        )
        for i in range(5)
    ]


def _ops():
    klines = _klines()
    prefix_merged = [0, 1, 2, 3, 4, 5]
    prefix_gap = [0, 0, 0, 0, 0, 0]
    high = np.array([k.merged_high for k in klines])
    low = np.array([k.merged_low for k in klines])
    ctx = BiContext(
        fenxing_list=[],
        all_klines=klines,
        prefix_merged=prefix_merged,
        prefix_gap=prefix_gap,
        high_prices=high,
        low_prices=low,
        fenxing_by_time={},
    )
    return BiEndpointOps(ctx)


def test_make_fake_front_sets_range_and_counts():
    ops = _ops()
    bi = ops.make_fake_front(
        start_idx=0,
        end_idx=4,
        bi_type=BiDirectionType.UP,
        start_price=8.0,
        end_price=14.0,
    )
    assert bi.start_idx == 0
    assert bi.end_idx == 4
    assert bi.start_time == pd.Timestamp("2024-01-01")
    assert bi.end_time == pd.Timestamp("2024-01-05")
    assert bi.real_origin_kline_count == 5
    assert bi.real_merged_kline_count == 5
    assert bi.has_gap_count == 0


def test_make_fake_front_respects_explicit_counts_and_end_time():
    ops = _ops()
    bi = ops.make_fake_front(
        start_idx=0,
        end_idx=4,
        bi_type=BiDirectionType.DOWN,
        start_price=14.0,
        end_price=8.0,
        end_time=pd.Timestamp("2024-01-06"),
        real_origin_kline_count=6,
        real_merged_kline_count=4,
        has_gap_count=1,
    )
    assert bi.end_time == pd.Timestamp("2024-01-06")
    assert bi.real_origin_kline_count == 6
    assert bi.real_merged_kline_count == 4
    assert bi.has_gap_count == 1
