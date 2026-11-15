"""Phase 7 通用合法拆分搜索。

当前只作为实验能力使用，默认不接入生产管线，也不替代人工确认白名单。
它会在一个线段的左右特征序列之间枚举 2~4 段候选，只接受每一段都满足
标准线段定义、首尾连续、且整体不变量数量下降的拆分。
"""

from __future__ import annotations

import itertools
from typing import Iterable

import numpy as np

from .bi import BiBase
from .tezhengxulie import TeZhengXuLie
from .xianduan import (
    XianDuan,
    XianDuanBase,
    XianDuanContext,
    XianDuanInvariants,
)


def _tzxl_index(tzxl_list: list[TeZhengXuLie], target: TeZhengXuLie) -> int | None:
    for index, tzxl in enumerate(tzxl_list):
        if tzxl is target:
            return index
    for index, tzxl in enumerate(tzxl_list):
        if tzxl.start_time == target.start_time and tzxl.is_top() == target.is_top():
            return index
    return None


def _context(
    segments: list[XianDuanBase],
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
) -> XianDuanContext:
    return XianDuanContext(
        bi_list=bi_list,
        tzxl_list=tzxl_list,
        bi_high_prices=np.array([bi.high_price for bi in bi_list]),
        bi_low_prices=np.array([bi.low_price for bi in bi_list]),
        tzxl_by_time_and_type={(tzxl.start_time, tzxl.is_top()): tzxl for tzxl in tzxl_list},
    )


def _violations(
    segments: list[XianDuanBase],
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
):
    return XianDuanInvariants(_context(segments, tzxl_list, bi_list)).check(segments)


def _build_candidate(
    segment: XianDuan,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
    indices: tuple[int, ...],
) -> list[XianDuan] | None:
    candidate: list[XianDuan] = []
    for left_index, right_index in zip(indices, indices[1:]):
        try:
            current = XianDuan.from_tzxl(
                tzxl_list[left_index],
                tzxl_list[right_index],
                bi_list,
            )
        except ValueError:
            return None
        if not current.is_finished or not current.has_enough_bi():
            return None
        if candidate and (
            candidate[-1].end_time != current.start_time
            or candidate[-1].end_bi_idx + 1 != current.start_bi_idx
        ):
            return None
        candidate.append(current)
    if not candidate:
        return None
    if candidate[0].start_time != segment.start_time or candidate[-1].end_time != segment.end_time:
        return None
    return candidate


def iter_legal_splits(
    segment: XianDuan,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
    max_segments: int = 4,
) -> Iterable[list[XianDuan]]:
    """枚举一个线段内部的合法拆分，优先返回 3 段、2 段、4 段。"""
    left_index = _tzxl_index(tzxl_list, segment.left_tzxl)
    right_index = _tzxl_index(tzxl_list, segment.right_tzxl)
    if left_index is None or right_index is None or right_index - left_index < 2:
        return

    preferred = [3, 2, 4]
    segment_counts = [count for count in preferred if 2 <= count <= max_segments]
    for count in segment_counts:
        for middle in itertools.combinations(range(left_index + 1, right_index), count - 1):
            candidate = _build_candidate(
                segment,
                tzxl_list,
                bi_list,
                (left_index, *middle, right_index),
            )
            if candidate is not None:
                yield candidate


def find_legal_split(
    segment: XianDuan,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
    max_segments: int = 4,
) -> list[XianDuan] | None:
    """返回第一个合法拆分；没有时返回 None。"""
    return next(iter_legal_splits(segment, tzxl_list, bi_list, max_segments), None)


def search_legal_splits(
    segments: list[XianDuanBase],
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
    target_indices: set[int] | None = None,
    max_segments: int = 4,
) -> list[XianDuanBase]:
    """对指定线段搜索并应用合法拆分。

    默认只处理当前报告为 ``right_tzxl_later_exceeds_left`` 的线段。
    只有候选拆分能让整体不变量数量下降时才会替换，避免“为了拆而拆”。
    """
    if not segments:
        return segments

    current = list(segments)
    current_violations = _violations(current, tzxl_list, bi_list)
    if target_indices is None:
        target_indices = {
            violation.index
            for violation in current_violations
            if violation.code == "right_tzxl_later_exceeds_left"
        }
    if not target_indices:
        return current

    for index in sorted(target_indices, reverse=True):
        if index >= len(current):
            continue
        segment = current[index]
        if not isinstance(segment, XianDuan):
            continue

        best: tuple[tuple[int, int], list[XianDuan], list] | None = None
        for candidate in iter_legal_splits(segment, tzxl_list, bi_list, max_segments):
            new_segments = current[:index] + candidate + current[index + 1 :]
            new_violations = _violations(new_segments, tzxl_list, bi_list)
            score = (len(new_violations), len(candidate))
            if best is None or score < best[0]:
                best = (score, candidate, new_violations)
        if best is None:
            continue

        score, candidate, new_violations = best
        if score[0] >= len(current_violations):
            continue
        current = current[:index] + candidate + current[index + 1 :]
        current_violations = new_violations

    for index, segment in enumerate(current):
        segment.idx = index
    return current
