import json

import pandas as pd

from CLPainter.web.backend.app.toolbox.beichi import macd_divergence


DAILY_TIMES = [
    "2024-01-01",
    "2024-01-02",
    "2024-01-03",
    "2024-01-04",
    "2024-01-05",
    "2024-01-06",
]
DAILY_MACD = [0.0, -3.0, -1.0, 1.0, -1.0, -0.5]


def _chart(times, values):
    return {"stats": [{"time": time, "macd": value} for time, value in zip(times, values)]}


def test_daily_times_locate_both_strokes():
    result = macd_divergence(
        _chart(DAILY_TIMES, DAILY_MACD),
        pd.Timestamp("2024-01-01"),
        "2024-01-03",
        "2024-01-04",
        pd.Timestamp("2024-01-06"),
        upward=False,
        earlier_end_price=10.0,
        later_end_price=9.0,
    )

    assert result.diverged
    assert result.earlier_area == 4.0
    assert result.later_area == 1.5


def test_indexes_locate_both_strokes():
    result = macd_divergence(
        _chart(DAILY_TIMES, [0.0, 4.0, 2.0, -1.0, 1.0]),
        0,
        2,
        3,
        4,
        upward=True,
        earlier_end_price=10.0,
        later_end_price=11.0,
    )

    assert result.diverged
    assert result.earlier_area == 6.0
    assert result.later_area == 1.0


def test_intraday_timestamps_match_subplot_seconds():
    base = 1_700_000_000
    times = [base + index * 60 for index in range(6)]
    result = macd_divergence(
        {"macd_data": json.dumps(_chart(times, DAILY_MACD))},
        pd.Timestamp("2023-11-14 22:13:20"),
        base + 120,
        str(base + 180),
        pd.Timestamp(base + 300, unit="s"),
        upward=False,
        earlier_end_price=10.0,
        later_end_price=9.0,
    )

    assert result.diverged
    assert result.earlier_area == 4.0
    assert result.later_area == 1.5


def test_larger_area_new_extreme_and_missing_gap_do_not_diverge():
    chart = _chart(DAILY_TIMES, [0.0, -1.0, 1.0, -3.0, -0.2, -1.0])

    assert not macd_divergence(
        chart, 0, 1, 2, 3, upward=False, earlier_end_price=10.0, later_end_price=9.0
    ).diverged
    assert not macd_divergence(
        chart, 0, 1, 2, 3, upward=False, earlier_end_price=9.0, later_end_price=9.5
    ).diverged
    assert not macd_divergence(
        _chart(DAILY_TIMES, [0.0, -3.0, -0.2, -1.0, 0.0, 0.0]),
        0,
        1,
        2,
        3,
        upward=False,
        earlier_end_price=10.0,
        later_end_price=9.0,
    ).diverged


def test_opposite_bars_and_dif_do_not_change_area_judgment():
    chart = {
        "stats": [
            {"time": "2024-01-01", "macd": 0.0, "dif": -0.2},
            {"time": "2024-01-02", "macd": -3.0, "dif": -1.2},
            {"time": "2024-01-03", "macd": 5.0, "dif": 0.8},
            {"time": "2024-01-04", "macd": 1.0, "dif": 0.4},
            {"time": "2024-01-05", "macd": -1.0, "dif": -0.4},
            {"time": "2024-01-06", "macd": 4.0, "dif": -0.9},
        ]
    }

    result = macd_divergence(
        chart,
        0,
        2,
        3,
        5,
        upward=False,
        earlier_end_price=10.0,
        later_end_price=9.0,
    )

    assert result.diverged
    assert result.earlier_area == 3.0
    assert result.later_area == 1.0
    assert result.earlier_peak == 3.0
    assert result.later_peak == 1.0
    assert result.peak_lower
    assert result.earlier_dif == 1.2
    assert result.later_dif == 0.9
    assert result.dif_lower


def test_lower_peak_or_dif_alone_is_not_divergence():
    chart = {
        "stats": [
            {"time": time, "macd": macd, "dif": dif}
            for time, macd, dif in zip(
                DAILY_TIMES,
                [0.0, -1.0, 1.0, -3.0, 0.0, 0.0],
                [-2.0, -2.0, 0.2, -0.5, 0.0, 0.0],
            )
        ]
    }

    result = macd_divergence(
        chart, 0, 1, 2, 3, upward=False, earlier_end_price=10.0, later_end_price=9.0
    )

    assert not result.diverged
    assert result.peak_lower is False
    assert result.dif_lower


def test_missing_time_reports_the_subplot():
    try:
        macd_divergence(
            _chart(DAILY_TIMES, DAILY_MACD),
            "2024-01-01",
            "2024-02-01",
            "2024-01-04",
            "2024-01-06",
            upward=False,
            earlier_end_price=10.0,
            later_end_price=9.0,
        )
    except ValueError as error:
        assert "副图中找不到时间" in str(error)
    else:
        raise AssertionError("副图中不存在的时间应该报错")
