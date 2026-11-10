"""不变量修复规划器测试。"""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from CLPainter.web.backend.app.toolbox.bi import (
    BiContext,
    BiDirectionType,
    BiEndpointOps,
    BiInvariants,
    BiRepairLoop,
    BiRepairOps,
)
from CLPainter.web.backend.app.toolbox.xianduan import (
    FakeXianDuanLast,
    XianDuanContext,
    XianDuanDirectionType,
    XianDuanEndpointOps,
    XianDuanInvariants,
    XianDuanRepairLoop,
    XianDuanRepairOps,
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


def test_bi_repair_loop_plans_merge_for_same_direction():
    ctx = _bi_ctx()
    endpoint_ops = BiEndpointOps(ctx)
    repair_ops = BiRepairOps(ctx, endpoint_ops)
    loop = BiRepairLoop(ctx, endpoint_ops, repair_ops, BiInvariants(ctx))
    bis = [
        _bi(BiDirectionType.UP, 0, 1, "2024-01-01", "2024-01-02"),
        _bi(BiDirectionType.UP, 1, 2, "2024-01-02", "2024-01-03"),
    ]
    current, repairs = loop.run(bis)
    assert current == bis
    assert any(repair.action == "merge_same_direction" for repair in repairs)


def test_xianduan_repair_loop_plans_merge_for_same_direction():
    ctx = _xd_ctx()
    endpoint_ops = XianDuanEndpointOps(ctx.bi_list, ctx.tzxl_list)
    repair_ops = XianDuanRepairOps(ctx, endpoint_ops)
    loop = XianDuanRepairLoop(
        ctx,
        endpoint_ops,
        repair_ops,
        XianDuanInvariants(ctx),
    )
    segments = [
        _fake_segment(0, 2, True, "2024-01-01", "2024-01-03"),
        _fake_segment(3, 5, True, "2024-01-03", "2024-01-05"),
    ]
    current, repairs = loop.run(segments)
    assert current == segments
    assert any(repair.action == "merge_same_direction" for repair in repairs)


def test_xianduan_repair_loop_plans_fill_gap():
    ctx = _xd_ctx()
    endpoint_ops = XianDuanEndpointOps(ctx.bi_list, ctx.tzxl_list)
    repair_ops = XianDuanRepairOps(ctx, endpoint_ops)
    loop = XianDuanRepairLoop(
        ctx,
        endpoint_ops,
        repair_ops,
        XianDuanInvariants(ctx),
    )
    segments = [
        _fake_segment(0, 2, True, "2024-01-01", "2024-01-03"),
        _fake_segment(4, 6, False, "2024-01-03", "2024-01-05"),
    ]
    _, repairs = loop.run(segments)
    assert any(repair.action == "fill_gap" for repair in repairs)
