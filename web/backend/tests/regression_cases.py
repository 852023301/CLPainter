"""CLPainter 历史回归用例清单。

按检查级别拆分，避免把笔级别、线段级别和数据质量类问题混在一起：

- ``segment``: 线段端点、方向、fake 段类型
- ``bi``: 笔端点、方向、笔数量
- ``pivot``: 线段中枢存在性
- ``data_quality``: 上游数据清洗/空值处理

用例编号与 ``CLPainter/历史已处理问题汇总.md`` 保持一致。
"""

from dataclasses import dataclass
from typing import Literal

MatchMode = Literal["full", "prefix", "suffix", "contains", "endpoint"]


@dataclass(frozen=True)
class SegmentCase:
    case_id: str
    symbol: str
    frequency: str
    asset_class: str
    match: MatchMode
    expected: tuple
    note: str = ""


@dataclass(frozen=True)
class BiCase:
    case_id: str
    symbol: str
    frequency: str
    asset_class: str
    match: MatchMode
    expected: tuple
    note: str = ""


@dataclass(frozen=True)
class PivotCase:
    case_id: str
    symbol: str
    frequency: str
    asset_class: str
    note: str = ""


@dataclass(frozen=True)
class DataQualityCase:
    case_id: str
    symbol: str
    frequency: str
    asset_class: str
    note: str = ""


# 线段级：只放文档明确要求线段端点/方向/类型的案例。
SEGMENT_CASES = (
    SegmentCase(
        "S1",
        "600996SH",
        "freq=1day",
        "asset_class=stock",
        "contains",
        ("2021-10-29", "2023-01-04", "XianDuan", True),
    ),
    SegmentCase(
        "S3",
        "000977SZ",
        "freq=1week",
        "asset_class=stock",
        "contains",
        ("2008-11-07", "2015-04-24", "XianDuan", True),
    ),
    SegmentCase(
        "S4",
        "000977SZ",
        "freq=1month",
        "asset_class=stock",
        "full",
        (
            ("2000-06-30", "2008-11-28", "FakeXianDuanLast", False),
            ("2008-11-28", "2026-07-31", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S5",
        "000001SH",
        "freq=1day",
        "asset_class=index",
        "contains",
        ("2025-04-07", "2026-05-14", "XianDuan", True),
        "后续下降段随数据更新，当前为 2026-10-23；这里只固定上升段。",
    ),
    SegmentCase(
        "S6",
        "000001SH",
        "freq=1day",
        "asset_class=index",
        "contains",
        ("2018-01-29", "2019-01-04", "XianDuan", False),
    ),
    SegmentCase(
        "S7",
        "300353SZ",
        "freq=1day",
        "asset_class=stock",
        "contains",
        ("2024-07-09", "2025-09-17", "XianDuan", True),
    ),
    SegmentCase(
        "S8",
        "000750SZ",
        "freq=1day",
        "asset_class=stock",
        "contains",
        ("2025-04-09", "2025-09-11", "XianDuan", True),
    ),
    SegmentCase(
        "S9",
        "600015SH",
        "freq=1day",
        "asset_class=stock",
        "contains",
        ("2023-06-26", "2025-07-10", "XianDuan", True),
    ),
    SegmentCase(
        "S10",
        "600713SH",
        "freq=1day",
        "asset_class=stock",
        "suffix",
        (("2026-04-13", "2026-10-23", "FakeXianDuanLast", False),),
    ),
    SegmentCase(
        "S11",
        "000001SZ",
        "freq=1day",
        "asset_class=stock",
        "endpoint",
        "1996-01-23",
    ),
    SegmentCase(
        "S13",
        "159307SZ",
        "freq=1day",
        "asset_class=fund",
        "contains",
        ("2024-09-19", "2025-11-12", "XianDuan", True),
    ),
    SegmentCase(
        "S24",
        "600015SH",
        "freq=1day",
        "asset_class=stock",
        "prefix",
        (
            ("2004-02-06", "2005-07-12", "XianDuan", False),
            ("2005-07-12", "2007-10-16", "XianDuan", True),
        ),
    ),
    SegmentCase(
        "S25",
        "603683SH",
        "freq=1day",
        "asset_class=stock",
        "suffix",
        (
            ("2024-02-08", "2025-09-25", "XianDuan", True),
            ("2025-09-25", "2026-10-19", "FakeXianDuanLast", False),
        ),
    ),
    SegmentCase(
        "S26",
        "159870SZ",
        "freq=1week",
        "asset_class=fund",
        "full",
        (
            ("2021-09-17", "2024-02-08", "FakeXianDuanLast", False),
            ("2024-02-08", "2026-03-06", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S27-688549SH",
        "688549SH",
        "freq=1week",
        "asset_class=stock",
        "full",
        (
            ("2023-09-08", "2024-09-20", "FakeXianDuanLast", False),
            ("2024-09-20", "2026-07-03", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S27-560100SH",
        "560100SH",
        "freq=1week",
        "asset_class=fund",
        "full",
        (
            ("2022-03-04", "2024-02-08", "FakeXianDuanLast", False),
            ("2024-02-08", "2026-07-03", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S27-300139SZ",
        "300139SZ",
        "freq=1month",
        "asset_class=stock",
        "full",
        (
            ("2010-11-30", "2018-02-28", "FakeXianDuanLast", False),
            ("2018-02-28", "2026-03-31", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S27-002080SZ",
        "002080SZ",
        "freq=1month",
        "asset_class=stock",
        "full",
        (("2012-12-31", "2026-06-30", "FakeXianDuanLast", True),),
    ),
    SegmentCase(
        "S27-600127SH",
        "600127SH",
        "freq=1week",
        "asset_class=stock",
        "full",
        (
            ("2001-06-08", "2005-07-22", "XianDuan", False),
            ("2005-07-22", "2008-05-16", "XianDuan", True),
            ("2008-05-16", "2018-10-19", "XianDuan", False),
            ("2018-10-19", "2026-09-24", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S27-600113SH",
        "600113SH",
        "freq=1month",
        "asset_class=stock",
        "full",
        (
            ("2001-06-29", "2008-11-28", "FakeXianDuanLast", False),
            ("2008-11-28", "2025-12-31", "FakeXianDuanLast", True),
        ),
    ),
    SegmentCase(
        "S28",
        "600312SH",
        "freq=1day",
        "asset_class=stock",
        "suffix",
        (
            ("2024-10-08", "2025-06-23", "XianDuan", False),
            ("2025-06-23", "2026-03-06", "XianDuan", True),
            ("2026-03-06", "2026-07-09", "FakeXianDuanLast", False),
            ("2026-07-09", "2026-10-26", "FakeXianDuanLast", True),
        ),
    ),
)


# 笔级：文档只要求笔端点/笔数量，不要求线段。
BI_CASES = (
    BiCase(
        "S2",
        "000001SH",
        "freq=1year",
        "asset_class=index",
        "prefix",
        (("up", "1990-12-31", "2001-12-31"),),
    ),
    BiCase(
        "S12",
        "600600SH",
        "freq=1month",
        "asset_class=stock",
        "prefix",
        (
            ("down", "1993-08-31", "1994-07-29"),
            ("up", "1994-07-29", "1996-12-31"),
        ),
    ),
    BiCase(
        "S14-quarter",
        "300663SZ",
        "freq=1quarter",
        "asset_class=stock",
        "full",
        (
            ("up", "2017-06-30", "2019-06-28"),
            ("down", "2019-06-28", "2026-09-30"),
        ),
    ),
    BiCase(
        "S15",
        "300583SZ",
        "freq=1quarter",
        "asset_class=stock",
        "full",
        (("down", "2017-03-31", "2026-11-06"),),
    ),
    BiCase(
        "S16",
        "000500SH",
        "freq=1month",
        "asset_class=index",
        "prefix",
        (
            ("up", "2014-10-31", "2015-06-30"),
            ("down", "2015-06-30", "2016-01-29"),
        ),
    ),
    BiCase(
        "S17",
        "399500SZ",
        "freq=1month",
        "asset_class=index",
        "prefix",
        (
            ("up", "2014-10-31", "2015-06-30"),
            ("down", "2015-06-30", "2016-01-29"),
        ),
    ),
    BiCase(
        "S18",
        "000500SH",
        "freq=1quarter",
        "asset_class=index",
        "prefix",
        (("up", "2014-12-31", "2021-03-31"),),
    ),
    BiCase(
        "S19",
        "159936SZ",
        "freq=1quarter",
        "asset_class=fund",
        "prefix",
        (("down", "2015-06-30", "2018-12-28"),),
    ),
)


# 中枢级：只要求线段中枢存在，不要求端点。
PIVOT_CASES = (
    PivotCase(
        "S14-weekly",
        "300663SZ",
        "freq=1week",
        "asset_class=stock",
        "周线不能缺线段中枢",
    ),
)


# 数据质量级：不应混进线段算法回归。
DATA_QUALITY_CASES = (
    DataQualityCase(
        "S20",
        "159229SZ",
        "freq=1day",
        "asset_class=fund",
        "2026-03-11 开/低/高为 0 时用当日收盘价填充，不能参与缺口计算。",
    ),
    DataQualityCase(
        "S21",
        "512070SH",
        "freq=1day",
        "asset_class=fund",
        "2021-09-10 开/低/高为 0 时用当日收盘价填充，图表缓存要能生成。",
    ),
    DataQualityCase(
        "S22",
        "159002SZ",
        "freq=1day",
        "asset_class=fund",
        "价格全空或窗口内无 K 线时不保存空文件；395xxx 上市日占位为 1800-01-01。",
    ),
    DataQualityCase(
        "S23",
        "158065SZ",
        "freq=1day",
        "asset_class=fund",
        "上市日 1800-01-01 且缺旧文件时只跳过该标的，不中断整批基金/股票。",
    ),
)
