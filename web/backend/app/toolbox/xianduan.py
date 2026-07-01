from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import numpy as np
from .tezhengxulie import TeZhengXuLie


class XianDuanDirectionType(str, Enum):
    """线段的类型"""
    UP = 'up'  # 上升段：底→顶
    DOWN = 'down'  # 下降段：顶→底


@dataclass
class XianDuan:
    """线段数据结构"""
    start_idx: int = field(init=False)  # 线段起始位置索引（特征序列所在 K 线索引）
    end_idx: int = field(init=False)  # 线段结束位置索引（特征序列所在 K 线索引）
    start_bi_idx: int = field(init=False)  # 线段起始位置的笔索引（特征序列所在 笔索引）
    end_bi_idx: int = field(init=False)  # 线段结束位置的笔索引（特征序列所在 笔索引）
    start_time: str = field(init=False)  # 起始时间
    end_time: str = field(init=False)  # 结束时间
    start_price: float = field(init=False)  # 起始价格（顶/底特征序列的极值）
    end_price: float = field(init=False)  # 结束价格（顶/底特征序列的极值）
    xianduan_type: XianDuanDirectionType = field(init=False)  # 线段的方向

    # 左右分型
    left_fx_tzxl: TeZhengXuLie
    right_fx_tzxl: TeZhengXuLie

    def __post_init__(self):
        """根据左右两个特征序列分型初始化线段端点、方向和价格。"""
        if self.left_fx_tzxl.type == self.right_fx_tzxl.type:
            raise ValueError(f"特征序列分型方向一致: {self.left_fx_tzxl.type=}")

        self.xianduan_type = (
            XianDuanDirectionType.UP if self.right_fx_tzxl.is_top() else XianDuanDirectionType.DOWN
        )

        self.start_idx = self.left_fx_tzxl.start_idx
        self.end_idx = self.right_fx_tzxl.start_idx
        if self.end_idx <= self.start_idx:
            raise ValueError(f"线段结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_bi_idx = self.left_fx_tzxl.mid_bi_idx
        self.end_bi_idx = self.right_fx_tzxl.mid_bi_idx
        self.start_time = self.left_fx_tzxl.start_time
        self.end_time = self.right_fx_tzxl.start_time
        self.start_price = self.left_fx_tzxl.start_price
        self.end_price = self.right_fx_tzxl.start_price

    def is_up(self) -> bool:
        """判断当前线段是否为上升线段。"""
        return self.xianduan_type == XianDuanDirectionType.UP

    def is_down(self) -> bool:
        """判断当前线段是否为下降线段。"""
        return self.xianduan_type == XianDuanDirectionType.DOWN

    @property
    def bi_count(self) -> int:
        """返回线段覆盖的笔数量。"""
        return self.end_bi_idx - self.start_bi_idx + 1

    def to_dict(self) -> dict:
        """转换成前端画线更容易消费的字典结构。"""
        return {
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_bi_idx": self.start_bi_idx,
            "end_bi_idx": self.end_bi_idx,
            "direction": self.xianduan_type.value,
            "start_price": self.start_price,
            "end_price": self.end_price,
        }

    @classmethod
    def from_tzxl(cls, left_fx_tzxl: TeZhengXuLie, right_fx_tzxl: TeZhengXuLie) -> "XianDuan":
        """从一左一右两个特征序列分型构造候选线段。"""
        return cls(left_fx_tzxl=left_fx_tzxl, right_fx_tzxl=right_fx_tzxl)

    def is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if not self.has_enough_bi():
            return False

        if not self.is_leaving_interval():
            return False

        if not self.is_broken():
            return False

        # TODO 判断第二种特征序列时，线段完成判断具有滞后性

        return True

    def has_enough_bi(self) -> bool:
        """缠论线段至少由三笔构成。"""
        return self.bi_count >= 3

    def is_leaving_interval(self) -> bool:
        """判断右侧特征序列是否相对左侧特征序列完成区间离开。"""
        if self.is_up():
            return (
                self.left_fx_tzxl.low_price < self.right_fx_tzxl.low_price
                and self.left_fx_tzxl.high_price < self.right_fx_tzxl.high_price
            )

        return (
            self.left_fx_tzxl.high_price > self.right_fx_tzxl.high_price
            and self.left_fx_tzxl.low_price > self.right_fx_tzxl.low_price
        )

    def is_broken(self) -> bool:
        """分型完成前是否已经破坏原趋势"""
        if self.is_up() and self.right_fx_tzxl.right_bi.end_price < self.left_fx_tzxl.mid_bi.start_price:
            return False
        elif self.is_down() and self.right_fx_tzxl.right_bi.end_price > self.left_fx_tzxl.mid_bi.start_price:
            return False
        return True


def _is_better_same_type(candidate: TeZhengXuLie, current: TeZhengXuLie) -> bool:
    """同类特征序列里，判断 candidate 是否比 current 更适合做端点。"""
    if candidate.type != current.type:
        return False

    if candidate.is_top():
        return candidate.start_price >= current.start_price

    return candidate.start_price <= current.start_price


def _is_stronger_end(candidate: XianDuan, current: XianDuan) -> bool:
    """同方向候选线段里，判断 candidate 的右端是否更极端。"""
    if candidate.xianduan_type != current.xianduan_type:
        return False

    if candidate.is_up():
        return candidate.end_price >= current.end_price

    return candidate.end_price <= current.end_price


def _has_tzxl_gap(tzxl: TeZhengXuLie) -> bool:
    """判断特征序列是否为第二种类型，即是否存在特征序列缺口。"""
    return tzxl.is_second_category()


def _confirm_break(
    left_tzxl: TeZhengXuLie,
    right_tzxl: TeZhengXuLie,
    tzxl_list: List[TeZhengXuLie],
    right_idx: int,
) -> bool:
    """
    判断特征序列分型是否足以确认线段端点。

    第一种特征序列直接按相反分型确认；第二种特征序列有缺口，
    需要后续同类特征序列继续越过该端点，等价于缺口后的确认。
    """
    if left_tzxl.type == right_tzxl.type:
        return False

    if not _has_tzxl_gap(right_tzxl):
        return True

    for tzxl in tzxl_list[right_idx + 1:]:
        if tzxl.type != right_tzxl.type:
            continue

        if _is_better_same_type(tzxl, right_tzxl):
            return True

        return False

    return False


def _can_build_xianduan(
    left_tzxl: TeZhengXuLie,
    right_tzxl: TeZhengXuLie,
    tzxl_list: List[TeZhengXuLie],
    right_idx: int,
) -> bool:
    """综合缺口确认和线段成立条件，判断两个特征序列能否形成线段。"""
    if not _confirm_break(left_tzxl, right_tzxl, tzxl_list, right_idx):
        return False

    return XianDuan.from_tzxl(left_tzxl, right_tzxl).is_finished()


def _find_next_opposite(
    left_idx: int,
    tzxl_list: List[TeZhengXuLie],
) -> Optional[tuple[int, int]]:
    """从左端点之后寻找可确认线段的第一个异类特征序列端点。"""
    left_tzxl = tzxl_list[left_idx]
    best_idx: Optional[int] = None

    for idx in range(left_idx + 1, len(tzxl_list)):
        tzxl = tzxl_list[idx]

        if tzxl.type == left_tzxl.type:
            if best_idx is None and _is_better_same_type(tzxl, left_tzxl):
                left_tzxl = tzxl
                left_idx = idx
            continue

        if best_idx is None or _is_better_same_type(tzxl, tzxl_list[best_idx]):
            best_idx = idx

        if _can_build_xianduan(left_tzxl, tzxl_list[best_idx], tzxl_list, best_idx):
            return left_idx, best_idx

    if best_idx is None:
        return None

    return left_idx, best_idx


def generate_xian_duan(tzxl_list: List[TeZhengXuLie]) -> List[XianDuan]:
    """
    根据特征序列分型划分线段。

    实现思路和 generate_bi 保持一致：相邻异类特征序列先形成候选线段，
    在确认前允许同向端点继续延长；满足三笔以上、端点离开区间、第二种
    特征序列缺口被后续确认后，才把候选线段加入结果。
    """
    if len(tzxl_list) < 2:
        return []

    xianduan_list: List[XianDuan] = []

    left_idx = 0
    while left_idx < len(tzxl_list) - 1:
        left_tzxl = tzxl_list[left_idx]

        while left_idx + 1 < len(tzxl_list) and _is_better_same_type(tzxl_list[left_idx + 1], left_tzxl):
            left_idx += 1
            left_tzxl = tzxl_list[left_idx]

        next_pair = _find_next_opposite(left_idx, tzxl_list)
        if next_pair is None:
            break

        left_idx, right_idx = next_pair
        left_tzxl = tzxl_list[left_idx]
        right_tzxl = tzxl_list[right_idx]
        if left_tzxl.type == right_tzxl.type:
            left_idx = right_idx
            continue

        candidate = XianDuan.from_tzxl(left_tzxl, right_tzxl)
        if not _can_build_xianduan(left_tzxl, right_tzxl, tzxl_list, right_idx):
            left_idx += 1
            continue

        while right_idx + 1 < len(tzxl_list):
            next_idx = right_idx + 1
            next_tzxl = tzxl_list[next_idx]

            if next_tzxl.type == candidate.right_fx_tzxl.type:
                next_candidate = XianDuan.from_tzxl(candidate.left_fx_tzxl, next_tzxl)
                if _is_stronger_end(next_candidate, candidate):
                    candidate = next_candidate
                    right_idx = next_idx
                    continue

            break

        if xianduan_list and xianduan_list[-1].xianduan_type == candidate.xianduan_type:
            if _is_stronger_end(candidate, xianduan_list[-1]):
                xianduan_list[-1] = XianDuan.from_tzxl(xianduan_list[-1].left_fx_tzxl, candidate.right_fx_tzxl)
        else:
            xianduan_list.append(candidate)

        left_idx = right_idx

    assert np.all(np.diff([xd.is_up() for xd in xianduan_list]) != 0), "不满足线段上下交替的要求"
    return xianduan_list
