import json

import pytest

from CLPainter.web.backend.app.toolbox.beichi import macd_divergence
from CLPainter.web.backend.app.toolbox.bi import BiBase, BiDirectionType
from CLPainter.web.backend.app.toolbox.xianduan import XianDuanBase, XianDuanDirectionType


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


@pytest.fixture(params=["bi", "xianduan"])
def make_stroke(request):
    def create(start_idx, end_idx, end_price, upward):
        if request.param == "bi":
            stroke = BiBase(bi_type=BiDirectionType.UP if upward else BiDirectionType.DOWN)
        else:
            stroke = XianDuanBase()
            stroke.xianduan_type = XianDuanDirectionType.UP if upward else XianDuanDirectionType.DOWN
        stroke.start_idx = start_idx
        stroke.end_idx = end_idx
        stroke.end_price = end_price
        return stroke

    return create


def test_down_strokes_diverge_when_new_low_has_smaller_area(make_stroke):
    result = macd_divergence(
        make_stroke(0, 2, 10.0, False),
        make_stroke(3, 5, 9.0, False),
        _chart(DAILY_TIMES, DAILY_MACD),
    )

    assert result.diverged
    assert result.earlier_area == 4.0
    assert result.later_area == 1.5


def test_up_strokes_diverge_when_new_high_has_smaller_area(make_stroke):
    result = macd_divergence(
        make_stroke(0, 2, 10.0, True),
        make_stroke(3, 5, 11.0, True),
        _chart(DAILY_TIMES, [0.0, 4.0, 2.0, -1.0, 1.0, 0.5]),
    )

    assert result.diverged
    assert result.earlier_area == 6.0
    assert result.later_area == 1.5
    assert result.macd_turned


@pytest.mark.parametrize("payload_type", ["mapping", "json", "chart_payload"])
def test_instances_work_with_intraday_subplot_formats(make_stroke, payload_type):
    base = 1_700_000_000
    times = [base + index * 60 for index in range(6)]
    chart = _chart(times, DAILY_MACD)
    if payload_type == "json":
        chart = json.dumps(chart)
    elif payload_type == "chart_payload":
        chart = {"macd_data": json.dumps(chart)}

    result = macd_divergence(
        earlier=make_stroke(0, 2, 10.0, False),
        later=make_stroke(3, 5, 9.0, False),
        macd_data=chart,
    )

    assert result.diverged
    assert result.earlier_area == 4.0
    assert result.later_area == 1.5


@pytest.mark.parametrize(
    "histogram,earlier_price,later_price",
    [
        ([0.0, -1.0, 1.0, -3.0], 10.0, 9.0),
        ([0.0, -3.0, 1.0, -1.0], 9.0, 9.5),
        ([0.0, -3.0, 1.0, -1.0], 9.0, 9.0),
        ([0.0, -3.0, -0.2, -1.0], 10.0, 9.0),
        ([0.0, -1.0, 1.0, -1.0], 10.0, 9.0),
        ([0.0, 0.0, 1.0, -1.0], 10.0, 9.0),
    ],
)
def test_area_extreme_and_opposite_bar_requirements_are_unchanged(
    make_stroke, histogram, earlier_price, later_price
):
    result = macd_divergence(
        make_stroke(0, 1, earlier_price, False),
        make_stroke(2, 3, later_price, False),
        _chart(DAILY_TIMES, histogram),
    )

    assert not result.diverged


def test_opposite_bars_and_dif_do_not_change_area_judgment(make_stroke):
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
        make_stroke(0, 2, 10.0, False),
        make_stroke(3, 5, 9.0, False),
        chart,
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


def test_lower_peak_or_dif_alone_is_not_divergence(make_stroke):
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
        make_stroke(0, 1, 10.0, False),
        make_stroke(2, 3, 9.0, False),
        chart,
    )

    assert not result.diverged
    assert result.peak_lower is False
    assert result.dif_lower


def test_missing_dif_does_not_prevent_area_comparison(make_stroke):
    result = macd_divergence(
        make_stroke(0, 2, 10.0, False),
        make_stroke(3, 5, 9.0, False),
        _chart(DAILY_TIMES, DAILY_MACD),
    )

    assert result.diverged
    assert result.earlier_dif is None
    assert result.later_dif is None
    assert result.dif_lower is False


def test_opposite_directions_are_rejected(make_stroke):
    with pytest.raises(ValueError, match="方向"):
        macd_divergence(
            make_stroke(0, 2, 10.0, True),
            make_stroke(3, 5, 9.0, False),
            _chart(DAILY_TIMES, DAILY_MACD),
        )


def test_out_of_range_endpoint_is_rejected(make_stroke):
    with pytest.raises(ValueError, match="走势索引无效"):
        macd_divergence(
            make_stroke(0, 2, 10.0, False),
            make_stroke(3, 6, 9.0, False),
            _chart(DAILY_TIMES, DAILY_MACD),
        )
