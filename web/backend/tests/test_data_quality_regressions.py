"""上游数据质量回归占位。

S20-S23 属于数据清洗/空值处理，不属于线段算法。当前先保留为显式 skip，
等数据管道测试环境接入后再补真实断言。
"""

import pytest

from CLPainter.web.backend.tests.regression_cases import DATA_QUALITY_CASES


@pytest.mark.parametrize("case", DATA_QUALITY_CASES, ids=lambda case: case.case_id)
@pytest.mark.skip(reason="数据管道测试环境尚未接入；先保留用例清单")
def test_data_quality_regression(case):
    assert case.note, f"{case.case_id}: 缺少说明"
