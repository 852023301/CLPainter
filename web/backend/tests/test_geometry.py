"""价格/区间极值工具测试。"""

import pytest

from CLPainter.web.backend.app.toolbox.geometry import (
    price_is_more_extreme,
    price_is_same,
    range_extreme_indices,
)


def test_price_is_more_extreme_up():
    assert price_is_more_extreme(10.0, 9.0, True)
    assert not price_is_more_extreme(9.0, 10.0, True)
    assert not price_is_more_extreme(10.0, 10.0, True)


def test_price_is_more_extreme_down():
    assert price_is_more_extreme(9.0, 10.0, False)
    assert not price_is_more_extreme(10.0, 9.0, False)
    assert not price_is_more_extreme(10.0, 10.0, False)


def test_price_is_same_uses_tolerance():
    assert price_is_same(10.0, 10.0 + 5e-9)
    assert not price_is_same(10.0, 10.0 + 2e-8)


def test_range_extreme_indices():
    high = [1.0, 3.0, 2.0, 5.0, 4.0]
    low = [0.5, 0.2, 0.8, 0.1, 0.3]
    assert range_extreme_indices(high, low, 1, 3) == (3, 3)
    assert range_extreme_indices(high, low, 0, 4) == (3, 3)


def test_range_extreme_indices_rejects_invalid_range():
    with pytest.raises(ValueError):
        range_extreme_indices([1.0], [1.0], 1, 2)
