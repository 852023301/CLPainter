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
    XianDuanInvariants,
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
