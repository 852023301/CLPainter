import json

import numpy as np
import pandas as pd
import pytest

from CLPainter.web.backend.app.toolbox.beichi import macd_divergence
from CLPainter.web.backend.app.toolbox.bi import BiBase, BiDirectionType
from CLPainter.web.backend.app.toolbox.calculate import calculate_macd_indicator
from CLPainter.web.backend.app.toolbox.xianduan import XianDuanBase, XianDuanDirectionType


@pytest.fixture(params=['bi', 'xianduan'])
def strokes(request):
    def create(upward=True):
        result = []
        for start, end, price in [(0, 3, 110 if upward else 90), (5, 8, 112 if upward else 88)]:
            if request.param == 'bi':
                stroke = BiBase(bi_type=BiDirectionType.UP if upward else BiDirectionType.DOWN)
            else:
                stroke = XianDuanBase()
                stroke.xianduan_type = XianDuanDirectionType.UP if upward else XianDuanDirectionType.DOWN
            stroke.start_idx = start
            stroke.end_idx = end
            stroke.end_price = price
            result.append(stroke)
        return result
    return create


def chart(histogram, dif=None, raw=False):
    stats = []
    for index, value in enumerate(histogram):
        bar = {'time': f't{index}', 'macd': round(value, 2) if raw else value}
        if raw:
            bar['macd_raw'] = value
        if dif is not None:
            bar['dif'] = round(dif[index], 2) if raw else dif[index]
            if raw:
                bar['dif_raw'] = dif[index]
        stats.append(bar)
    return {'stats': stats}


@pytest.mark.parametrize('upward', [True, False])
@pytest.mark.parametrize('tail,expected,turned', [
    ([.2, .4, .6], False, False),
    ([.5, 1, .2], True, True),
    ([1, .5, .5], True, True),
    ([1, .5, .6], True, True),
    ([1, .5, 2], True, True),
    ([1, 1, 1], False, False),
    ([-.5, -.2, -.1], True, False),
    ([0, 0, 0], True, False),
    ([-.5, -1, .5], False, False),
    ([.5, .2, -.1], True, True),
])
def test_zero_area_or_any_in_segment_contraction_is_enough(strokes, upward, tail, expected, turned):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, -1, -.5, *tail]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.diverged is expected
    assert result.macd_turned is turned


@pytest.mark.parametrize('upward', [True, False])
@pytest.mark.parametrize('tail', [[-.5, -.2, -.1], [0, 0, 0]])
def test_zero_later_area_still_requires_positive_earlier_area(strokes, upward, tail):
    direction = 1 if upward else -1
    histogram = np.array([0, -.5, -.4, -.3, -1, -.5, *tail]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.earlier_area == result.later_area == 0
    assert not result.diverged
    assert not result.macd_turned


@pytest.mark.parametrize('upward', [True, False])
def test_zero_later_area_still_requires_new_extreme_and_gap_confirmation(strokes, upward):
    direction = 1 if upward else -1
    earlier, later = strokes(upward)
    later.end_price = earlier.end_price
    histogram = np.array([0, 4, 3, 2, -1, -.5, -.3, -.2, -.1]) * direction
    assert not macd_divergence(earlier, later, chart(histogram)).diverged
    histogram = np.array([0, 4, 3, 2, 2.5, 3.0, -.3, -.2, -.1]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.later_area == 0
    assert not result.diverged


@pytest.mark.parametrize('upward', [True, False])
@pytest.mark.parametrize('next_bar', [0.0, -.2, -2.0])
def test_only_same_direction_bar_followed_inside_segment_counts_as_contraction(strokes, upward, next_bar):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, -1, -.5, -.1, .5, next_bar]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.diverged
    assert result.macd_turned


@pytest.mark.parametrize('upward', [True, False])
def test_opposite_bar_immediately_outside_segment_cannot_confirm_contraction(strokes, upward):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, -1, -.5, .2, .4, .6, -.1]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert not result.diverged
    assert not result.macd_turned


@pytest.mark.parametrize('upward', [True, False])
def test_rounded_zero_is_not_an_absent_directional_histogram(strokes, upward):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, -1, -.5, .0001, .0002, .0003]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram, raw=True))
    assert result.later_area == pytest.approx(.0006)
    assert not result.diverged
    assert not result.macd_turned


@pytest.mark.parametrize('upward', [True, False])
def test_single_bar_has_no_confirmed_turn(strokes, upward):
    earlier, later = strokes(upward)
    later.end_idx = 6
    direction = 1 if upward else -1
    result = macd_divergence(earlier, later, chart(np.array([0, 4, 3, 2, -1, -.5, .5]) * direction))
    assert not result.diverged
    assert not result.macd_turned


@pytest.mark.parametrize('upward', [True, False])
def test_opposite_dif_does_not_become_directional_strength(strokes, upward):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, -1, -.5, .5, 1, .2]) * direction
    dif = np.array([2, 1.2, 1.5, 1.8, 2.2, 2.4, .4, .8, .9]) * -direction
    result = macd_divergence(*strokes(upward), chart(histogram, dif))
    assert result.diverged
    assert result.earlier_dif is None
    assert result.later_dif is None
    assert not result.dif_lower


@pytest.mark.parametrize('wrapped', [False, True])
def test_raw_histogram_prevents_rounding_false_negative(strokes, wrapped):
    histogram = [0, -.012, -.012, 0, .006, .006, -.013, -.010, 0]
    payload = chart(histogram, raw=True)
    if wrapped:
        payload = {'macd_data': json.dumps(payload)}
    result = macd_divergence(*strokes(False), payload)
    assert result.diverged
    assert result.earlier_area == pytest.approx(.024)
    assert result.later_area == pytest.approx(.023)


def test_raw_histogram_prevents_rounding_false_positive(strokes):
    histogram = [0, .016, .016, 0, -.006, -.006, .014, .014, .004]
    result = macd_divergence(*strokes(), chart(histogram, raw=True))
    assert not result.diverged
    assert result.earlier_area == result.later_area == pytest.approx(.032)


def test_generated_chart_precision_only_changes_display(strokes):
    close = pd.Series([100, 104, 107, 110, 105, 108, 111, 113, 112],
                      index=pd.date_range('2026-01-01', periods=9))
    low = calculate_macd_indicator(close, precision=0)
    high = calculate_macd_indicator(close, precision=8)
    assert low['stats'][3]['macd'] != high['stats'][3]['macd']
    assert [bar['macd_raw'] for bar in low['stats']] == [bar['macd_raw'] for bar in high['stats']]
    assert [bar['dif_raw'] for bar in low['stats']] == [bar['dif_raw'] for bar in high['stats']]
    assert macd_divergence(*strokes(), low) == macd_divergence(*strokes(), high)


@pytest.mark.parametrize('field', ['macd', 'dif', 'macd_raw', 'dif_raw'])
@pytest.mark.parametrize('invalid', [np.nan, np.inf, -np.inf, None, 'invalid', [1.0]])
def test_invalid_indicator_values_are_rejected(strokes, field, invalid):
    payload = chart([0, 4, 3, 2, -1, -.5, .5, 1, .2])
    for bar in payload['stats']:
        if field != 'macd':
            bar[field] = .1
    payload['stats'][1][field] = invalid
    with pytest.raises(ValueError, match='有限|数值'):
        macd_divergence(*strokes(), payload)


@pytest.mark.parametrize('field', ['macd_raw', 'dif_raw'])
def test_partial_raw_fields_are_rejected(strokes, field):
    payload = chart([0, 4, 3, 2, -1, -.5, .5, 1, .2])
    payload['stats'][0][field] = 0.0
    with pytest.raises(ValueError, match='不完整'):
        macd_divergence(*strokes(), payload)


def test_turn_does_not_look_beyond_later_endpoint(strokes):
    histogram = [0, 4, 3, 2, -1, -.5, .2, .4, .6]
    before = macd_divergence(*strokes(), chart(histogram))
    after = macd_divergence(*strokes(), chart(histogram + [.1, -.2, -.3]))
    assert before == after
    assert not after.diverged


def test_gap_contraction_can_replace_opposite_gap(strokes):
    result = macd_divergence(*strokes(), chart([0, 4, 3, 2, .1, .1, .5, 1, .2]))
    assert result.macd_turned
    assert result.diverged


@pytest.mark.parametrize('upward', [True, False])
@pytest.mark.parametrize('zero_area', [True, False])
@pytest.mark.parametrize('gap,expected', [
    ([1.0, 1.0], True),
    ([.5, 1.5], True),
    ([2.0, 2.0], False),
    ([2.5, 2.2], True),
    ([2.5, 3.0], False),
    ([0.0, 0.0], True),
    ([-.1, -.2], True),
    ([2.5, 1.9], True),
    ([3.5, 3.0], True),
])
def test_gap_checks_adjacent_bars_starting_at_earlier_last_bar(strokes, upward, zero_area, gap, expected):
    direction = 1 if upward else -1
    tail = [-.2, -.1, -.05] if zero_area else [.5, 1.0, .2]
    histogram = np.array([0, 4, 3, 2, *gap, *tail]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.diverged is expected
    assert result.macd_turned is not zero_area


@pytest.mark.parametrize('upward', [True, False])
@pytest.mark.parametrize('gap,expected', [([.1, .1], False), ([.5, .1], True), ([.1, .5], False)])
def test_gap_does_not_use_absolute_height_of_opposite_earlier_last_bar(strokes, upward, gap, expected):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, -.2, *gap, .2, .4, .1]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.macd_turned
    assert result.diverged is expected


@pytest.mark.parametrize('upward', [True, False])
def test_gap_internal_contraction_survives_reacceleration(strokes, upward):
    direction = 1 if upward else -1
    earlier, later = strokes(upward)
    later.start_idx = 6
    later.end_idx = 9
    histogram = np.array([0, 4, 3, 2, 3, 2.5, 4, .5, 1, .2]) * direction
    result = macd_divergence(earlier, later, chart(histogram))
    assert result.macd_turned
    assert result.diverged


@pytest.mark.parametrize('upward', [True, False])
def test_empty_gap_cannot_confirm_separation(strokes, upward):
    direction = 1 if upward else -1
    earlier, later = strokes(upward)
    later.start_idx = 3
    later.end_idx = 6
    histogram = np.array([0, 4, 3, 2, .5, 1.0, .2]) * direction
    result = macd_divergence(earlier, later, chart(histogram))
    assert result.macd_turned
    assert not result.diverged


@pytest.mark.parametrize('upward', [True, False])
def test_gap_contraction_does_not_replace_later_segment_contraction(strokes, upward):
    direction = 1 if upward else -1
    histogram = np.array([0, 4, 3, 2, 1, .8, .2, .4, .6]) * direction
    result = macd_divergence(*strokes(upward), chart(histogram))
    assert result.later_area > 0
    assert not result.macd_turned
    assert not result.diverged
