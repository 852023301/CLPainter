"""笔/线段不变量检查器单元测试。"""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from CLPainter.web.backend.app.toolbox.bi import (
    BiContext,
    BiDirectionType,
    BiInvariants,
)
from CLPainter.web.backend.app.toolbox.xianduan import (
    FakeXianDuanLast,
    XianDuanContext,
    XianDuanDirectionType,
    XianDuanEndpointOps,
    XianDuanInvariants,
    XianDuanRepairOps,
    _fake_start_index,
    _right_tzxl_extra_bis,
)


def _bi_ctx():
    return BiContext(
        fenxing_list=[],
        all_klines=[],
        prefix_merged=[],
        prefix_gap=[],
        high_prices=np.array([1.0, 2.0, 3.0]),
        low_prices=np.array([0.0, 1.0, 2.0]),
        fenxing_by_time={},
    )


def _bi(bi_type, start_idx, end_idx, start_time, end_time):
    return SimpleNamespace(
        bi_type=bi_type,
        start_idx=start_idx,
        end_idx=end_idx,
        start_time=pd.Timestamp(start_time),
        end_time=pd.Timestamp(end_time),
    )


def _fake_segment(start_bi_idx, end_bi_idx, is_up, start_time, end_time):
    segment = FakeXianDuanLast()
    segment.start_bi_idx = start_bi_idx
    segment.end_bi_idx = end_bi_idx
    segment.xianduan_type = (
        XianDuanDirectionType.UP if is_up else XianDuanDirectionType.DOWN
    )
    segment.start_idx = start_bi_idx
    segment.end_idx = end_bi_idx
    segment.start_time = pd.Timestamp(start_time)
    segment.end_time = pd.Timestamp(end_time)
    segment.start_price = 1.0
    segment.end_price = 2.0
    return segment


def _xd_ctx():
    bis = [
        SimpleNamespace(
            is_up=lambda index=index: index % 2 == 0,
            end_price=float(index),
            high_price=float(index) + 1.0,
            low_price=float(index) - 1.0,
        )
        for index in range(10)
    ]
    return XianDuanContext(
        bi_list=bis,
        tzxl_list=[],
        bi_high_prices=np.array([bi.high_price for bi in bis]),
        bi_low_prices=np.array([bi.low_price for bi in bis]),
        tzxl_by_time_and_type={},
    )


def test_bi_invariants_detect_direction_not_alternating():
    bis = [
        _bi(BiDirectionType.UP, 0, 1, "2024-01-01", "2024-01-02"),
        _bi(BiDirectionType.UP, 1, 2, "2024-01-02", "2024-01-03"),
    ]
    violations = BiInvariants(_bi_ctx()).check(bis)
    assert any(v.code == "direction_not_alternating" for v in violations)


def test_bi_invariants_detect_not_continuous():
    bis = [
        _bi(BiDirectionType.UP, 0, 1, "2024-01-01", "2024-01-02"),
        _bi(BiDirectionType.DOWN, 1, 2, "2024-01-03", "2024-01-04"),
    ]
    violations = BiInvariants(_bi_ctx()).check(bis)
    assert any(v.code == "not_continuous" for v in violations)


def test_xianduan_invariants_detect_min_bi_count():
    segments = [_fake_segment(0, 1, True, "2024-01-01", "2024-01-02")]
    violations = XianDuanInvariants(_xd_ctx()).check(segments)
    assert any(v.code == "min_bi_count" for v in violations)


def test_xianduan_invariants_detect_direction_not_alternating():
    segments = [
        _fake_segment(0, 2, True, "2024-01-01", "2024-01-03"),
        _fake_segment(3, 5, True, "2024-01-03", "2024-01-05"),
    ]
    violations = XianDuanInvariants(_xd_ctx()).check(segments)
    assert any(v.code == "direction_not_alternating" for v in violations)


def test_xianduan_invariants_detect_coverage_gap():
    segments = [
        _fake_segment(0, 2, True, "2024-01-01", "2024-01-03"),
        _fake_segment(4, 6, False, "2024-01-03", "2024-01-05"),
    ]
    violations = XianDuanInvariants(_xd_ctx()).check(segments)
    assert any(v.code == "bi_coverage_gap" for v in violations)


def _right_tzxl(highs, lows, is_top=False):
    return SimpleNamespace(
        bi_list=[
            SimpleNamespace(high_price=high, low_price=low)
            for high, low in zip(highs, lows)
        ],
        bi_idx_list=[0, 1, 2],
        left_bi_idx=0,
        right_bi_idx=2,
        is_top=lambda: is_top,
        is_bottom=lambda: not is_top,
    )


def _xd_segment(is_up, left_high, left_low, right_highs, right_lows):
    segment = SimpleNamespace(
        start_bi_idx=0,
        end_bi_idx=2,
        start_price=left_high if not is_up else left_low,
        end_price=left_low if not is_up else left_high,
        start_time=pd.Timestamp("2024-01-01"),
        end_time=pd.Timestamp("2024-01-03"),
        left_tzxl=SimpleNamespace(high_price=left_high, low_price=left_low),
        right_tzxl=_right_tzxl(right_highs, right_lows, is_top=is_up),
        has_enough_bi=lambda: True,
        is_up=lambda: is_up,
        is_down=lambda: not is_up,
    )
    return segment


def _xd_ctx_for_segment(segment):
    bis = [
        SimpleNamespace(
            is_up=lambda index=index: index % 2 == 0,
            start_price=10.0,
            end_price=8.0 if index == 2 else 9.5,
            high_price=10.5 if index == 0 else 9.5,
            low_price=8.0 if index == 2 else 8.5,
        )
        for index in range(3)
    ]
    return XianDuanContext(
        bi_list=bis,
        tzxl_list=[],
        bi_high_prices=np.array([bi.high_price for bi in bis]),
        bi_low_prices=np.array([bi.low_price for bi in bis]),
        tzxl_by_time_and_type={},
    )


def test_xianduan_invariants_detect_right_tzxl_exceeds_left():
    segment = _xd_segment(
        is_up=False,
        left_high=10.0,
        left_low=8.0,
        right_highs=[11.0, 10.5, 9.5],
        right_lows=[8.0, 7.5, 7.0],
    )
    violations = XianDuanInvariants(_xd_ctx_for_segment(segment)).check([segment])
    assert any(v.code == "right_tzxl_exceeds_left" for v in violations)


def test_xianduan_invariants_allow_right_tzxl_first_bi_exceed():
    segment = _xd_segment(
        is_up=False,
        left_high=10.0,
        left_low=8.0,
        right_highs=[11.0, 9.0, 9.5],
        right_lows=[8.0, 7.5, 7.0],
    )
    violations = XianDuanInvariants(_xd_ctx_for_segment(segment)).check([segment])
    assert not any(v.code == "right_tzxl_exceeds_left" for v in violations)


def test_xianduan_invariants_detect_right_tzxl_below_left():
    segment = _xd_segment(
        is_up=True,
        left_high=10.0,
        left_low=8.0,
        right_highs=[9.0, 9.5, 10.0],
        right_lows=[8.0, 7.5, 7.0],
    )
    violations = XianDuanInvariants(_xd_ctx_for_segment(segment)).check([segment])
    assert any(v.code == "right_tzxl_below_left" for v in violations)


def test_repair_ops_do_not_move_first_start_without_previous_segment():
    ctx = _xd_ctx()
    ops = XianDuanRepairOps(ctx, XianDuanEndpointOps(ctx.bi_list, []))
    segment = _fake_segment(0, 2, True, "2024-01-01", "2024-01-03")
    boundary = {
        "price": 1.0,
        "time": pd.Timestamp("2024-01-02"),
        "kline_idx": 1,
        "prev_end_bi_idx": -1,
        "next_start_bi_idx": 1,
    }
    assert not ops.move_shared_boundary([segment], 0, boundary, "start")


def test_repair_ops_do_not_move_last_end_without_next_segment():
    ctx = _xd_ctx()
    ops = XianDuanRepairOps(ctx, XianDuanEndpointOps(ctx.bi_list, []))
    segment = _fake_segment(0, 2, True, "2024-01-01", "2024-01-03")
    boundary = {
        "price": 2.0,
        "time": pd.Timestamp("2024-01-03"),
        "kline_idx": 2,
        "prev_end_bi_idx": 2,
        "next_start_bi_idx": 3,
    }
    assert not ops.move_shared_boundary([segment], 0, boundary, "end")
    assert not ops.move_end_and_next_start([segment], 0, 2)

def _simple_bi(index, is_up, high, low):
    return SimpleNamespace(
        idx=index,
        is_up=lambda: is_up,
        is_down=lambda: not is_up,
        start_price=low if is_up else high,
        end_price=high if is_up else low,
        high_price=high,
        low_price=low,
        start_idx=index * 2,
        end_idx=index * 2 + 1,
    )


def test_fake_start_index_uses_extreme_and_valid_boundary():
    bis = [
        _simple_bi(0, True, 20.8, 14.8),
        _simple_bi(1, False, 20.8, 17.82),
        _simple_bi(2, True, 20.35, 17.82),
        _simple_bi(3, False, 20.35, 14.01),
        _simple_bi(4, True, 16.85, 14.01),
        _simple_bi(5, False, 16.85, 14.6),
        _simple_bi(6, True, 23.4, 14.6),
        _simple_bi(7, False, 23.4, 20.38),
        _simple_bi(8, True, 22.55, 20.38),
        _simple_bi(9, False, 22.55, 18.9),
        _simple_bi(10, True, 24.98, 18.9),
    ]
    assert _fake_start_index(bis, 10, True) == 4
    assert _fake_start_index(bis, 3, False) == 1

def test_right_tzxl_extra_bis_only_returns_unstored_same_direction_bis():
    bis = [
        SimpleNamespace(idx=index, is_up=lambda index=index: index % 2 == 0)
        for index in range(7)
    ]
    right = SimpleNamespace(
        bi_list=[bis[0], bis[4], bis[6]],
        bi_idx_list=[0, 4, 6],
        left_bi_idx=0,
        right_bi_idx=6,
    )
    segment = SimpleNamespace(right_tzxl=right)
    assert [bi.idx for bi in _right_tzxl_extra_bis(segment, bis)] == [2]
