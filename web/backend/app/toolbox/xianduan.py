import copy
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple, TypedDict, Union
from abc import ABC
import numpy as np
import pandas as pd

from .bi import BiBase
from .geometry import price_is_more_extreme, price_is_same
from .tezhengxulie import TeZhengXuLie


class XianDuanDirectionType(str, Enum):
    """线段的类型"""
    UP = 'up'  # 上升段：底→顶
    DOWN = 'down'  # 下降段：顶→底


class ExtremeBoundary(TypedDict):
    """线段极值修复时的真实边界点"""

    price: float
    time: pd.Timestamp
    kline_idx: int
    prev_end_bi_idx: int
    next_start_bi_idx: int


# 特征序列分界可能存在小偏差；只有起点严重偏离真实极值时才做后置修复。
EXTREMUM_REPAIR_THRESHOLD = 0.20
BoundarySide = Literal["start", "end"]
ExtremeType = Literal["low", "high"]


@dataclass
class XianDuanBase(ABC):
    """线段数据结构基类

    所有字段均为 init=False + 默认值: 由子类的 __post_init__ 或外部构造逻辑
    (如 make_fake_last_xd) 事后填充
    """
    start_idx: int = field(init=False, default=0)  # 线段起始位置索引(特征序列极值点所在 K 线索引)
    end_idx: int = field(init=False, default=0)  # 线段结束位置索引(特征序列极值点所在 K 线索引)
    start_bi_idx: int = field(init=False, default=0)  # 线段起始位置的笔索引(特征序列极值点中间笔索引)
    end_bi_idx: int = field(init=False, default=0)  # 线段真实覆盖到的最后一笔索引（(特征序列中间笔索引-1）
    start_time: pd.Timestamp = field(init=False, default=pd.NaT)  # 起始时间
    end_time: pd.Timestamp = field(init=False, default=pd.NaT)  # 结束时间
    start_price: float = field(init=False, default=0.0)  # 起始价格(顶/底特征序列的极值)
    end_price: float = field(init=False, default=0.0)  # 结束价格(顶/底特征序列的极值)
    xianduan_type: Optional[XianDuanDirectionType] = field(init=False, default=None)  # 线段的方向

    idx: int = field(init=False, default=0)

    _is_finished_cache: Optional[bool] = field(
        init=False,
        default=None,
        repr=False,
    )

    def is_up(self) -> bool:
        """判断当前线段是否为上升线段。"""
        return self.xianduan_type == XianDuanDirectionType.UP

    def is_down(self) -> bool:
        """判断当前线段是否为下降线段。"""
        return self.xianduan_type == XianDuanDirectionType.DOWN

    def extends_beyond_end(self, price: float) -> bool:
        """判断给定价格是否在本线段方向上超越了本线段终点价格

        UP线段: price > end_price (向上超越顶分型)
        DOWN线段: price < end_price (向下超越底分型)
        """
        if self.is_up():
            return price > self.end_price
        return price < self.end_price

    def extends_beyond_start(self, price: float) -> bool:
        """判断给定价格是否在本线段反方向上超越了本线段起点价格

        UP线段: price < start_price (向下超越底分型)
        DOWN线段: price > start_price (向上超越顶分型)
        """
        if self.is_up():
            return price < self.start_price
        return price > self.start_price

    @property
    def bi_count(self) -> int:
        """返回线段覆盖的笔数量。"""
        return self.end_bi_idx - self.start_bi_idx + 1

    def to_dict(self) -> dict:
        """转换成前端画线更容易消费的字典结构。"""
        return {
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "direction": self.xianduan_type.value,
            "start_price": self.start_price,
            "end_price": self.end_price,
        }

    def has_enough_bi(self) -> bool:
        """缠论线段至少由三笔构成。"""
        return self.bi_count >= 3

    def invalidate_cache(self):
        self._is_finished_cache = None


@dataclass
class FakeXianDuanLast(XianDuanBase):
    """最末尾的假线段"""

    # xianduan索引(由 generate_xian_duan 事后填充)
    left_tzxl: Optional[TeZhengXuLie] = field(init=False, default=None)
    # end_bi_idx这个属性是被赋值的


@dataclass
class FakeXianDuanFirst(XianDuanBase):
    """最早的假线段"""

    # 右侧特征序列(由 make_fake_first_xd_extend 事后填充)
    right_tzxl: Optional[TeZhengXuLie] = field(init=False, default=None)

    # end_bi_idx这个属性是被赋值的

    def extend(self, right_tzxl: TeZhengXuLie):
        """向后延长"""
        self.end_bi_idx = right_tzxl.mid_bi_idx - 1
        self.end_idx = right_tzxl.mid_bi.start_idx
        self.end_time = right_tzxl.start_time
        self.end_price = right_tzxl.start_price
        self.right_tzxl = right_tzxl
        self.invalidate_cache()
        return self

    @property
    def is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if self._is_finished_cache is None:
            self._is_finished_cache = self._is_finished()
        return self._is_finished_cache

    def _is_finished(self) -> bool:
        if not self.has_enough_bi():
            return False
        if self.is_fanbao():
            return False

        return True

    def is_fanbao(self) -> bool:
        """若特征序列完成前已经反包原趋势，则前一个特征序列只是中继"""
        if self.is_up() and self.right_tzxl.right_bi.end_price < self.start_price:
            return True
        elif self.is_down() and self.right_tzxl.right_bi.end_price > self.start_price:
            return True
        return False


@dataclass
class XianDuan(XianDuanBase):
    # 左右分型
    left_tzxl: TeZhengXuLie
    right_tzxl: TeZhengXuLie

    # 完整的笔列表引用（用于第二种特征序列判断等场景）
    bi_list: List[BiBase] = field(default_factory=list, repr=False)

    def __post_init__(self):
        """根据左右两个特征序列分型初始化线段端点、方向和价格。"""
        if self.left_tzxl.type == self.right_tzxl.type:
            raise ValueError(f"特征序列分型方向一致: {self.left_tzxl.type=}")

        self.xianduan_type = (
            XianDuanDirectionType.UP if self.right_tzxl.is_top() else XianDuanDirectionType.DOWN
        )

        self.start_idx = self.left_tzxl.start_idx
        self.end_idx = self.right_tzxl.start_idx
        if self.end_idx <= self.start_idx:
            raise ValueError(f"线段结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_bi_idx = self.left_tzxl.mid_bi_idx
        self.end_bi_idx = self.right_tzxl.mid_bi_idx - 1
        self.start_time = self.left_tzxl.start_time
        self.end_time = self.right_tzxl.start_time
        self.start_price = self.left_tzxl.start_price
        self.end_price = self.right_tzxl.start_price

        if self.start_time >= self.end_time:
            raise ValueError(f"线段起始时间不能大于结束时间:{self.start_time=}>={self.end_time=}")

    @classmethod
    def from_tzxl(cls, left_tzxl: TeZhengXuLie, right_tzxl: TeZhengXuLie,
                  bi_list: Optional[List[BiBase]] = None) -> "XianDuan":
        """从一左一右两个特征序列分型构造候选线段。"""
        if bi_list is None:
            bi_list = []
        return cls(left_tzxl=left_tzxl, right_tzxl=right_tzxl, bi_list=bi_list)

    @property
    def is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if self._is_finished_cache is None:
            self._is_finished_cache = self._is_finished()
        return self._is_finished_cache

    def _is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if not self.has_enough_bi():
            return False
        if self.is_fanbao():
            return False

        # 判断第二种特征序列时，要考虑第一笔和第二笔的包含关系
        if self.left_tzxl.is_second_category() and self.is_second_bi_contain_first_bi():
            return False
        return True

    def print_is_finished(self):
        return f"{self.has_enough_bi()=}  {self.is_fanbao()=}  {self.left_tzxl.is_second_category()=}   {self.is_second_bi_contain_first_bi()=}"


    def is_fanbao(self) -> bool:
        """若特征序列完成前已经反包原趋势，则前一个特征序列只是中继"""
        if self.is_up() and self.right_tzxl.right_bi.end_price < self.left_tzxl.low_price:
            return True
        elif self.is_down() and self.right_tzxl.right_bi.end_price > self.left_tzxl.high_price:
            return True
        return False

    def is_second_bi_contain_first_bi(self) -> bool:
        """判断在第二种特征序列中，第二条线段的结束特征序列中，第二笔是否包含第一笔（以此来判断第二段是否无效）"""
        # 使用完整的 bi_list，如果未提供则回退到 right_tzxl.bi_list
        target_bi_list = self.bi_list
        if not target_bi_list:
            target_bi_list = self.right_tzxl.bi_list
            if not target_bi_list:
                target_bi_list = self.left_tzxl.bi_list
                if not target_bi_list:
                    raise ValueError("无法获取特征序列的笔列表")

        start_bi_idx = self.start_bi_idx + 1
        end_bi_idx = self.right_tzxl.mid_bi_idx
        merged_deque = deque([])
        bi = target_bi_list[start_bi_idx]
        # print(f"{bi.start_time=}")
        merged_low = bi.low_price
        merged_high = bi.high_price

        # 第二段线段向上的情况
        if self.xianduan_type == XianDuanDirectionType.UP:
            forward_up = True
            # 笔向下
            assert bi.is_down(), "判断第二种特征序列是否成立时发生笔方向错误的情况"

            for idx in range(start_bi_idx + 2, end_bi_idx + 1, 2):
                bi = target_bi_list[idx]
                if (bi.start_price > merged_high and bi.end_price > merged_low):
                    merged_deque.append((merged_low, merged_high))
                    merged_high = bi.start_price
                    merged_low = bi.end_price
                    forward_up = True
                    continue
                elif (bi.start_price < merged_high and bi.end_price < merged_low):
                    merged_deque.append((merged_low, merged_high))
                    merged_high = bi.start_price
                    merged_low = bi.end_price
                    forward_up = False
                    continue
                elif (bi.end_price >= merged_low and bi.start_price <= merged_high) or (
                    bi.end_price <= merged_low and bi.start_price >= merged_high):
                    # 合并
                    if forward_up:
                        func = max
                    else:
                        func = min
                    merged_high = func(merged_high, bi.start_price)
                    merged_low = func(merged_low, bi.end_price)
                else:
                    raise ValueError(f"判断第二种特征序列是否成立时发现意外的笔")

            # 寻找是否存在不被合并的笔，能够完成第二种特征序列
            for ml, mh in merged_deque:
                if ml < merged_low and mh < merged_high:
                    return False

        # 第二段线段向下的情况
        else:
            forward_up = False
            # 笔向上
            assert bi.is_up(), "判断第二种特征序列是否成立时发生笔方向错误的情况"
            # print(f"{list(range(start_bi_idx + 2, end_bi_idx + 1, 2))=}")
            for idx in range(start_bi_idx + 2, end_bi_idx + 1, 2):
                bi = target_bi_list[idx]
                if (bi.start_price > merged_low and bi.end_price > merged_high):
                    merged_deque.append((merged_low, merged_high))
                    merged_low = bi.start_price
                    merged_high = bi.end_price
                    forward_up = True
                    continue
                elif (bi.start_price < merged_low and bi.end_price < merged_high):
                    merged_deque.append((merged_low, merged_high))
                    merged_low = bi.start_price
                    merged_high = bi.end_price
                    forward_up = False
                    continue
                elif (bi.start_price >= merged_low and bi.end_price <= merged_high) or (
                    bi.start_price <= merged_low and bi.end_price >= merged_high):
                    # 合并
                    if forward_up:
                        func = max
                    else:
                        func = min
                    merged_high = func(merged_high, bi.end_price)
                    merged_low = func(merged_low, bi.start_price)
                else:
                    raise ValueError(f"判断第二种特征序列是否成立时发现意外的笔")

            # 寻找是否存在不被合并的笔，能够完成第二种特征序列
            for ml, mh in merged_deque:
                if ml > merged_low and mh > merged_high:
                    return False

        return True


class XianDuanEndpointOps:
    """线段端点操作的独立实现。

    这里刻意不抽取成笔/线段共用基类：笔和线段的端点规则不同，共用抽象
    反而会把两套规则耦合在一起。本类只服务 ``xianduan.py``。
    """

    def __init__(self, bi_list: List[BiBase], tzxl_list: List[TeZhengXuLie]):
        self.bi_list = bi_list
        self.tzxl_list = tzxl_list

    def find_extreme_boundary(
        self,
        segment: XianDuanBase,
        extreme_type: ExtremeType,
    ) -> ExtremeBoundary:
        """在线段覆盖范围内找到可作为相邻线段分界的真实极值点。"""
        best_boundary: Optional[ExtremeBoundary] = None
        best_key: Optional[Tuple[float, pd.Timestamp]] = None
        for bi_idx in range(segment.start_bi_idx, segment.end_bi_idx + 1):
            bi = self.bi_list[bi_idx]
            start_boundary: ExtremeBoundary = {
                "price": bi.start_price,
                "time": bi.start_time,
                "kline_idx": bi.start_idx,
                "prev_end_bi_idx": bi_idx - 1,
                "next_start_bi_idx": bi_idx,
            }
            end_boundary: ExtremeBoundary = {
                "price": bi.end_price,
                "time": bi.end_time,
                "kline_idx": bi.end_idx,
                "prev_end_bi_idx": bi_idx,
                "next_start_bi_idx": bi_idx + 1,
            }
            for boundary in (start_boundary, end_boundary):
                key = (boundary["price"], boundary["time"])
                if (
                    best_key is None
                    or (extreme_type == "low" and key < best_key)
                    or (extreme_type == "high" and key > best_key)
                ):
                    best_boundary = boundary
                    best_key = key

        if best_boundary is None:
            raise ValueError("线段覆盖的笔为空，无法寻找极值边界")
        return best_boundary

    def extreme_end_bi_idx(
        self,
        start_bi_idx: int,
        end_bi_idx: int,
        is_up: bool,
    ) -> Optional[int]:
        """返回区间内同向笔终点的最极值笔；同价时取更晚的笔。"""
        best_idx = None
        best_price = None
        for bi_idx in range(start_bi_idx, end_bi_idx + 1):
            bi = self.bi_list[bi_idx]
            if bi.is_up() != is_up:
                continue
            price = float(bi.end_price)
            if best_idx is None or price_is_more_extreme(price, best_price, is_up) or (
                price_is_same(price, best_price) and bi_idx > best_idx
            ):
                best_idx = bi_idx
                best_price = price
        if best_idx is None or best_idx < start_bi_idx + 2:
            return None
        return best_idx

    def make_bi_range_segment(
        self,
        start_bi_idx: int,
        end_bi_idx: int,
        is_up: bool,
    ) -> FakeXianDuanLast:
        start_bi = self.bi_list[start_bi_idx]
        end_bi = self.bi_list[end_bi_idx]
        segment = FakeXianDuanLast()
        segment.xianduan_type = XianDuanDirectionType.UP if is_up else XianDuanDirectionType.DOWN
        segment.start_bi_idx = start_bi_idx
        segment.end_bi_idx = end_bi_idx
        segment.start_idx = start_bi.start_idx
        segment.end_idx = end_bi.end_idx
        segment.start_time = start_bi.start_time
        segment.end_time = end_bi.end_time
        segment.start_price = start_bi.start_price
        segment.end_price = end_bi.end_price
        segment.invalidate_cache()
        return segment

    def move_start(self, segment: XianDuanBase, start_bi_idx: int) -> None:
        start_bi = self.bi_list[start_bi_idx]
        segment.start_bi_idx = start_bi_idx
        segment.start_idx = start_bi.start_idx
        segment.start_time = start_bi.start_time
        segment.start_price = start_bi.start_price
        segment.invalidate_cache()
        if not isinstance(segment, (XianDuan, FakeXianDuanLast)):
            return
        for tzxl in self.tzxl_list:
            if tzxl.start_time != start_bi.start_time:
                continue
            if abs(float(tzxl.start_price) - float(start_bi.start_price)) > 1e-6:
                continue
            if segment.is_up() and not tzxl.is_bottom():
                continue
            if segment.is_down() and not tzxl.is_top():
                continue
            segment.left_tzxl = tzxl
            break

    def move_end(self, segment: XianDuanBase, end_bi_idx: int) -> None:
        end_bi = self.bi_list[end_bi_idx]
        segment.end_bi_idx = end_bi_idx
        segment.end_idx = end_bi.end_idx
        segment.end_time = end_bi.end_time
        segment.end_price = end_bi.end_price
        segment.invalidate_cache()
        if not isinstance(segment, (XianDuan, FakeXianDuanFirst)):
            return
        for tzxl in self.tzxl_list:
            if tzxl.start_time != end_bi.end_time:
                continue
            if abs(float(tzxl.start_price) - float(end_bi.end_price)) > 1e-6:
                continue
            if segment.is_up() and not tzxl.is_top():
                continue
            if segment.is_down() and not tzxl.is_bottom():
                continue
            segment.right_tzxl = tzxl
            break

    def set_boundary(
        self,
        segment: XianDuanBase,
        boundary: ExtremeBoundary,
        boundary_side: BoundarySide,
    ) -> None:
        boundary_bi_idx = (
            boundary["next_start_bi_idx"] if boundary_side == "start" else boundary["prev_end_bi_idx"]
        )
        bi = self.bi_list[boundary_bi_idx]
        if boundary_side == "start":
            segment.start_bi_idx = boundary["next_start_bi_idx"]
            segment.start_idx = bi.start_idx
            segment.start_time = bi.start_time
            segment.start_price = bi.start_price
        else:
            segment.end_bi_idx = boundary["prev_end_bi_idx"]
            segment.end_idx = bi.end_idx
            segment.end_time = bi.end_time
            segment.end_price = bi.end_price
        segment.invalidate_cache()


class XianDuanRepairOps:
    """线段修复的原子操作，只服务 xianduan.py。"""

    def __init__(self, ctx: "XianDuanContext", endpoint_ops: XianDuanEndpointOps):
        self.ctx = ctx
        self.endpoint_ops = endpoint_ops

    def range_breaks_start(self, start_bi_idx: int, end_bi_idx: int, is_up: bool) -> bool:
        """反向笔终点突破线段起点时，这条线段不能成立。"""
        bi_list = self.ctx.bi_list
        start_price = float(bi_list[start_bi_idx].start_price)
        for bi_idx in range(start_bi_idx, end_bi_idx + 1):
            bi = bi_list[bi_idx]
            if bi.is_up() == is_up:
                continue
            price = float(bi.end_price)
            if is_up and price < start_price - 1e-8:
                return True
            if not is_up and price > start_price + 1e-8:
                return True
        return False

    def absorb_tail_into_next_segment(
        self,
        segments: List[XianDuanBase],
        index: int,
        extreme_idx: int,
    ) -> bool:
        """把切不开的尾部并入下一条反向线段，且不破坏该线段终点极值。"""
        if index + 1 >= len(segments):
            return False
        segment = segments[index]
        next_segment = segments[index + 1]
        if next_segment.is_up() == segment.is_up():
            return False
        if next_segment.start_bi_idx != segment.end_bi_idx + 1:
            return False
        new_start_bi_idx = extreme_idx + 1
        if new_start_bi_idx > segment.end_bi_idx:
            return False
        if self.ctx.bi_list[new_start_bi_idx].is_up() != next_segment.is_up():
            return False
        new_end_bi_idx = next_segment.end_bi_idx
        if self.endpoint_ops.extreme_end_bi_idx(
            new_start_bi_idx, new_end_bi_idx, next_segment.is_up()
        ) != new_end_bi_idx:
            return False
        if self.range_breaks_start(new_start_bi_idx, new_end_bi_idx, next_segment.is_up()):
            return False
        self.endpoint_ops.move_end(segment, extreme_idx)
        self.endpoint_ops.move_start(next_segment, new_start_bi_idx)
        return True

    def segment_tzxl_consistent(self, segment: XianDuanBase) -> bool:
        if not isinstance(segment, XianDuan):
            return True
        left = getattr(segment, "left_tzxl", None)
        right = getattr(segment, "right_tzxl", None)
        if left is None or right is None:
            return False
        if left.mid_bi_idx != segment.start_bi_idx:
            return False
        if right.mid_bi_idx - 1 != segment.end_bi_idx:
            return False
        start_bi = self.ctx.bi_list[segment.start_bi_idx]
        end_bi = self.ctx.bi_list[segment.end_bi_idx]
        if left.start_time != start_bi.start_time:
            return False
        if abs(float(left.start_price) - float(start_bi.start_price)) > 1e-6:
            return False
        if right.start_time != end_bi.end_time:
            return False
        if abs(float(right.start_price) - float(end_bi.end_price)) > 1e-6:
            return False
        return True

    def right_tzxl_rule_ok(self, segment: XianDuanBase) -> bool:
        if not isinstance(segment, XianDuan):
            return True
        left = getattr(segment, "left_tzxl", None)
        right = getattr(segment, "right_tzxl", None)
        if left is None or right is None:
            return True
        right_bis = right.bi_list[1:]
        if not right_bis:
            return True
        if segment.is_down():
            return max(float(bi.high_price) for bi in right_bis) <= float(left.high_price) + 1e-8
        return min(float(bi.low_price) for bi in right_bis) >= float(left.low_price) - 1e-8

    def _snapshot_segment(self, segment: XianDuanBase):
        return (
            segment.start_bi_idx,
            segment.end_bi_idx,
            segment.start_idx,
            segment.end_idx,
            segment.start_time,
            segment.end_time,
            segment.start_price,
            segment.end_price,
            getattr(segment, "left_tzxl", None),
            getattr(segment, "right_tzxl", None),
        )

    def _restore_segment(self, segment: XianDuanBase, snapshot) -> None:
        (
            segment.start_bi_idx,
            segment.end_bi_idx,
            segment.start_idx,
            segment.end_idx,
            segment.start_time,
            segment.end_time,
            segment.start_price,
            segment.end_price,
            left_tzxl,
            right_tzxl,
        ) = snapshot
        if hasattr(segment, "left_tzxl"):
            segment.left_tzxl = left_tzxl
        if hasattr(segment, "right_tzxl"):
            segment.right_tzxl = right_tzxl
        segment.invalidate_cache()

    def start_extremum_error(
        self,
        start_bi_idx: int,
        end_bi_idx: int,
        is_up: bool,
        start_price: float,
    ) -> float:
        covered = self.ctx.bi_list[start_bi_idx:end_bi_idx + 1]
        if not covered:
            return 0.0
        true_high = max(float(bi.high_price) for bi in covered)
        true_low = min(float(bi.low_price) for bi in covered)
        true_range = true_high - true_low
        if true_range <= 0:
            return 0.0
        deviation = start_price - true_low if is_up else true_high - start_price
        return max(0.0, deviation / true_range)

    def move_shared_boundary(
        self,
        segments: List[XianDuanBase],
        index: int,
        boundary: ExtremeBoundary,
        side: BoundarySide,
    ) -> bool:
        """移动相邻线段共享的边界，保持首尾连续。

        返回 False 表示移动后某条线段不足三笔，调用方应放弃这次修复。
        """
        segment = segments[index]
        if side == "start":
            # 第一段没有前一段可以接管头部区间；向前移动起点会留下未覆盖的头部。
            if index == 0:
                return False
            new_start_bi_idx = boundary["next_start_bi_idx"]
            if segment.end_bi_idx - new_start_bi_idx + 1 < 3:
                return False
            previous = segments[index - 1] if index > 0 else None
            previous_snapshot = self._snapshot_segment(previous) if previous is not None else None
            segment_snapshot = self._snapshot_segment(segment)
            if previous is not None:
                new_prev_end_bi_idx = boundary["prev_end_bi_idx"]
                if new_prev_end_bi_idx - previous.start_bi_idx + 1 < 3:
                    return False
                if self.start_extremum_error(
                    previous.start_bi_idx,
                    new_prev_end_bi_idx,
                    previous.is_up(),
                    previous.start_price,
                ) > EXTREMUM_REPAIR_THRESHOLD:
                    return False
                self.endpoint_ops.set_boundary(previous, boundary, "end")
            self.endpoint_ops.set_boundary(segment, boundary, "start")
            if (previous is not None and not self.right_tzxl_rule_ok(previous)) or not self.right_tzxl_rule_ok(segment):
                if previous is not None:
                    self._restore_segment(previous, previous_snapshot)
                self._restore_segment(segment, segment_snapshot)
                return False
            if (previous is not None and not self.segment_tzxl_consistent(previous)) or not self.segment_tzxl_consistent(segment):
                if previous is not None:
                    self._restore_segment(previous, previous_snapshot)
                self._restore_segment(segment, segment_snapshot)
                return False
            return True

        new_end_bi_idx = boundary["prev_end_bi_idx"]
        if new_end_bi_idx - segment.start_bi_idx + 1 < 3:
            return False
        # 最后一段没有下一段可以接管尾部区间；向前移动终点会留下未覆盖的尾部。
        if index + 1 >= len(segments):
            return False
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        segment_snapshot = self._snapshot_segment(segment)
        next_snapshot = self._snapshot_segment(next_segment) if next_segment is not None else None
        if next_segment is not None:
            new_next_start_bi_idx = boundary["next_start_bi_idx"]
            if next_segment.end_bi_idx - new_next_start_bi_idx + 1 < 3:
                return False
            new_next_start_price = self.ctx.bi_list[new_next_start_bi_idx].start_price
            if self.start_extremum_error(
                new_next_start_bi_idx,
                next_segment.end_bi_idx,
                next_segment.is_up(),
                new_next_start_price,
            ) > EXTREMUM_REPAIR_THRESHOLD:
                return False
            self.endpoint_ops.set_boundary(next_segment, boundary, "start")
        self.endpoint_ops.set_boundary(segment, boundary, "end")
        if not self.right_tzxl_rule_ok(segment) or (
            next_segment is not None and not self.right_tzxl_rule_ok(next_segment)
        ):
            self._restore_segment(segment, segment_snapshot)
            if next_segment is not None:
                self._restore_segment(next_segment, next_snapshot)
            return False
        if not self.segment_tzxl_consistent(segment) or (
            next_segment is not None and not self.segment_tzxl_consistent(next_segment)
        ):
            self._restore_segment(segment, segment_snapshot)
            if next_segment is not None:
                self._restore_segment(next_segment, next_snapshot)
            return False
        return True

    def merge_invalid_segment_with_next(
        self,
        segments: List[XianDuanBase],
        index: int,
    ) -> bool:
        """删除无效段，并把下一段的起点前移到无效段起点。

        适用于 ``end_not_extreme_bi`` 且同向极值落在段首的情况：
        当前段方向本身不可信，保留它只会制造穿透；把它的区间并入下一段，
        再检查下一段是否仍是合法线段。
        """
        if index + 1 >= len(segments):
            return False
        segment = segments[index]
        next_segment = segments[index + 1]
        if segment.is_up() == next_segment.is_up():
            return False

        new_start_bi_idx = segment.start_bi_idx
        if next_segment.end_bi_idx - new_start_bi_idx + 1 < 3:
            return False

        old_start_bi_idx = next_segment.start_bi_idx
        new_start_price = self.ctx.bi_list[new_start_bi_idx].start_price
        if self.start_extremum_error(
            new_start_bi_idx,
            next_segment.end_bi_idx,
            next_segment.is_up(),
            new_start_price,
        ) > EXTREMUM_REPAIR_THRESHOLD:
            return False
        self.endpoint_ops.move_start(next_segment, new_start_bi_idx)
        left_tzxl = getattr(next_segment, "left_tzxl", None)
        start_bi = self.ctx.bi_list[new_start_bi_idx]
        left_tzxl_ok = (
            left_tzxl is not None
            and left_tzxl.start_time == start_bi.start_time
            and abs(float(left_tzxl.start_price) - float(start_bi.start_price)) <= 1e-6
        )
        endpoint_ok = (
            self.endpoint_ops.extreme_end_bi_idx(
                new_start_bi_idx,
                next_segment.end_bi_idx,
                next_segment.is_up(),
            )
            == next_segment.end_bi_idx
        )
        penetration_ok = not self.range_breaks_start(
            new_start_bi_idx,
            next_segment.end_bi_idx,
            next_segment.is_up(),
        )
        if not (left_tzxl_ok and endpoint_ok and penetration_ok):
            self.endpoint_ops.move_start(next_segment, old_start_bi_idx)
            return False

        del segments[index]
        return True

    def _candidate_score(
        self,
        original: List[XianDuanBase],
        candidate: List[XianDuanBase],
        start_index: int,
        old_window_count: int,
        new_window_count: int,
    ):
        invariants = XianDuanInvariants(self.ctx)
        before = invariants.check(original)
        after = invariants.check(candidate)

        before_window = [
            item for item in before
            if start_index <= item.index < start_index + old_window_count
        ]
        after_window = [
            item for item in after
            if start_index <= item.index < start_index + new_window_count
        ]
        if len(after_window) >= len(before_window):
            return None

        before_outside = [
            item for item in before
            if item.index < start_index or item.index >= start_index + old_window_count
        ]
        after_outside = [
            item for item in after
            if item.index < start_index or item.index >= start_index + new_window_count
        ]
        before_outside_codes = Counter(item.code for item in before_outside)
        after_outside_codes = Counter(item.code for item in after_outside)
        if any(
            after_outside_codes[code] > before_outside_codes[code]
            for code in after_outside_codes
        ):
            return None

        return (
            len(after_outside),
            len(after_window),
            new_window_count,
            len(after),
        )

    def resegment_local_window(
        self,
        segments: List[XianDuanBase],
        index: int,
        window_radius: int = 1,
        max_candidates: int = 200,
    ) -> bool:
        """在局部窗口内用 tzxl 重新组合线段，选择评分最优的候选。"""
        start_index = max(0, index - window_radius)
        end_index = min(len(segments) - 1, index + window_radius)
        if start_index >= end_index:
            return False

        start_seg = segments[start_index]
        end_seg = segments[end_index]
        start_tzxl = getattr(start_seg, "left_tzxl", None)
        end_tzxl = getattr(end_seg, "right_tzxl", None)
        if start_tzxl is None or end_tzxl is None:
            return False
        if start_tzxl.idx is None or end_tzxl.idx is None:
            return False
        if start_tzxl.idx >= end_tzxl.idx:
            return False

        tzxl_list = self.ctx.tzxl_list
        old_window_count = end_index - start_index + 1
        original = list(segments)
        best = None
        best_score = None
        tried = 0

        def consider(candidates: List[XianDuanBase]) -> None:
            nonlocal best, best_score, tried
            tried += 1
            if tried > max_candidates:
                return
            if not candidates:
                return
            if candidates[0].start_bi_idx != original[start_index].start_bi_idx:
                return
            if candidates[-1].end_bi_idx != original[end_index].end_bi_idx:
                return
            for left, right in zip(candidates, candidates[1:]):
                if left.end_bi_idx + 1 != right.start_bi_idx:
                    return
            candidate = (
                original[:start_index]
                + candidates
                + original[end_index + 1:]
            )
            score = self._candidate_score(
                original,
                candidate,
                start_index,
                old_window_count,
                len(candidates),
            )
            if score is None:
                return
            if best_score is None or score < best_score:
                best_score = score
                best = candidate

        # 两段替换
        for mid_idx in range(start_tzxl.idx + 1, end_tzxl.idx):
            if tried > max_candidates:
                break
            mid_tzxl = tzxl_list[mid_idx]
            try:
                first = XianDuan.from_tzxl(start_tzxl, mid_tzxl, self.ctx.bi_list)
                second = XianDuan.from_tzxl(mid_tzxl, end_tzxl, self.ctx.bi_list)
            except ValueError:
                continue
            if not first.is_finished or not second.is_finished:
                continue
            if not first.has_enough_bi() or not second.has_enough_bi():
                continue
            consider([first, second])

        # 三段替换
        for mid1_idx in range(start_tzxl.idx + 1, end_tzxl.idx - 1):
            if tried > max_candidates:
                break
            mid1_tzxl = tzxl_list[mid1_idx]
            for mid2_idx in range(mid1_idx + 1, end_tzxl.idx):
                if tried > max_candidates:
                    break
                mid2_tzxl = tzxl_list[mid2_idx]
                try:
                    first = XianDuan.from_tzxl(start_tzxl, mid1_tzxl, self.ctx.bi_list)
                    second = XianDuan.from_tzxl(mid1_tzxl, mid2_tzxl, self.ctx.bi_list)
                    third = XianDuan.from_tzxl(mid2_tzxl, end_tzxl, self.ctx.bi_list)
                except ValueError:
                    continue
                if not (first.is_finished and second.is_finished and third.is_finished):
                    continue
                if not (first.has_enough_bi() and second.has_enough_bi() and third.has_enough_bi()):
                    continue
                consider([first, second, third])

        if best is None:
            return False
        segments[:] = best
        return True

    def resegment_invalid_segment(
        self,
        segments: List[XianDuanBase],
        index: int,
        max_candidates: int = 100,
    ) -> bool:
        for radius in (1, 2, 3):
            if self.resegment_local_window(
                segments,
                index,
                window_radius=radius,
                max_candidates=max_candidates,
            ):
                return True
        return False

    def merge_invalid_segment_with_previous(
        self,
        segments: List[XianDuanBase],
        index: int,
    ) -> bool:
        """删除无效段，并把上一段的终点后移到无效段终点。"""
        if index <= 0:
            return False
        segment = segments[index]
        previous = segments[index - 1]
        if segment.is_up() == previous.is_up():
            return False

        new_end_bi_idx = segment.end_bi_idx
        if new_end_bi_idx - previous.start_bi_idx + 1 < 3:
            return False

        old_end_bi_idx = previous.end_bi_idx
        self.endpoint_ops.move_end(previous, new_end_bi_idx)
        right_tzxl = getattr(previous, "right_tzxl", None)
        end_bi = self.ctx.bi_list[new_end_bi_idx]
        right_tzxl_ok = (
            right_tzxl is not None
            and right_tzxl.start_time == end_bi.end_time
            and abs(float(right_tzxl.start_price) - float(end_bi.end_price)) <= 1e-6
        )
        endpoint_ok = (
            self.endpoint_ops.extreme_end_bi_idx(
                previous.start_bi_idx,
                new_end_bi_idx,
                previous.is_up(),
            )
            == new_end_bi_idx
        )
        penetration_ok = not self.range_breaks_start(
            previous.start_bi_idx,
            new_end_bi_idx,
            previous.is_up(),
        )
        if not (right_tzxl_ok and endpoint_ok and penetration_ok):
            self.endpoint_ops.move_end(previous, old_end_bi_idx)
            return False

        del segments[index]
        return True

    def repair_penetrates_start(
        self,
        segments: List[XianDuanBase],
        index: int,
    ) -> bool:
        """把穿透起点的反向笔并入上一段，局部重切共享边界。"""
        if index <= 0:
            return False
        segment = segments[index]
        for bi_idx in range(segment.start_bi_idx, segment.end_bi_idx + 1):
            bi = self.ctx.bi_list[bi_idx]
            if bi.is_up() == segment.is_up():
                continue
            price = float(bi.end_price)
            penetrated = (
                segment.is_up() and price < float(segment.start_price) - 1e-8
            ) or (
                not segment.is_up() and price > float(segment.start_price) + 1e-8
            )
            if not penetrated:
                continue
            new_start_bi_idx = bi_idx + 1
            if new_start_bi_idx > segment.end_bi_idx:
                continue
            new_start_price = self.ctx.bi_list[new_start_bi_idx].start_price
            if self.start_extremum_error(
                new_start_bi_idx,
                segment.end_bi_idx,
                segment.is_up(),
                new_start_price,
            ) > EXTREMUM_REPAIR_THRESHOLD:
                continue
            boundary = {
                "price": price,
                "time": bi.end_time,
                "kline_idx": bi.end_idx,
                "prev_end_bi_idx": bi_idx,
                "next_start_bi_idx": new_start_bi_idx,
            }
            if self.move_shared_boundary(segments, index, boundary, "start"):
                return True
            continue
        return False

    def move_end_and_next_start(
        self,
        segments: List[XianDuanBase],
        index: int,
        new_end_bi_idx: int,
    ) -> bool:
        """把当前段终点和下一段起点一起移动到 new_end_bi_idx。"""
        segment = segments[index]
        if new_end_bi_idx - segment.start_bi_idx + 1 < 3:
            return False
        # 最后一段不能单独前移终点，否则尾部区间没有线段覆盖。
        if index + 1 >= len(segments):
            return False
        segment_snapshot = self._snapshot_segment(segment)
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        next_snapshot = self._snapshot_segment(next_segment) if next_segment is not None else None
        if next_segment is not None:
            new_next_start_bi_idx = new_end_bi_idx + 1
            if next_segment.end_bi_idx - new_next_start_bi_idx + 1 < 3:
                return False
            new_next_start_price = self.ctx.bi_list[new_next_start_bi_idx].start_price
            if self.start_extremum_error(
                new_next_start_bi_idx,
                next_segment.end_bi_idx,
                next_segment.is_up(),
                new_next_start_price,
            ) > EXTREMUM_REPAIR_THRESHOLD:
                return False
            self.endpoint_ops.move_start(next_segment, new_next_start_bi_idx)
        self.endpoint_ops.move_end(segment, new_end_bi_idx)
        if not self.right_tzxl_rule_ok(segment) or (
            next_segment is not None and not self.right_tzxl_rule_ok(next_segment)
        ):
            self._restore_segment(segment, segment_snapshot)
            if next_segment is not None:
                self._restore_segment(next_segment, next_snapshot)
            return False
        if not self.segment_tzxl_consistent(segment) or (
            next_segment is not None and not self.segment_tzxl_consistent(next_segment)
        ):
            self._restore_segment(segment, segment_snapshot)
            if next_segment is not None:
                self._restore_segment(next_segment, next_snapshot)
            return False
        return True

    def merge_same_direction(self, segments: List[XianDuanBase]) -> List[XianDuanBase]:
        """合并状态机遗留的同向相邻线段。"""
        bi_list = self.ctx.bi_list
        merged_segments = []
        for segment in segments:
            if not merged_segments:
                merged_segments.append(segment)
                continue

            previous_segment = merged_segments[-1]
            if previous_segment.end_time < segment.start_time:
                previous_segment.end_bi_idx = segment.start_bi_idx - 1
                boundary_bi = bi_list[segment.start_bi_idx - 1]
                previous_segment.end_idx = boundary_bi.end_idx
                previous_segment.end_time = boundary_bi.end_time
                previous_segment.end_price = boundary_bi.end_price
                previous_segment.invalidate_cache()

            if previous_segment.is_up() != segment.is_up():
                merged_segments.append(segment)
                continue

            previous_segment.end_bi_idx = segment.end_bi_idx
            previous_segment.end_idx = segment.end_idx
            previous_segment.end_time = segment.end_time
            previous_segment.end_price = segment.end_price
            if isinstance(segment, (XianDuan, FakeXianDuanFirst)):
                previous_segment.right_tzxl = segment.right_tzxl
                if isinstance(previous_segment, FakeXianDuanLast):
                    previous_segment.left_tzxl = None
            previous_segment.invalidate_cache()

        return merged_segments


@dataclass
class XianDuanContext:
    """线段构建上下文，只服务 xianduan.py。"""

    bi_list: List[BiBase]
    tzxl_list: List[TeZhengXuLie]
    bi_high_prices: np.ndarray
    bi_low_prices: np.ndarray
    tzxl_by_time_and_type: Dict[Tuple[pd.Timestamp, bool], TeZhengXuLie]


@dataclass(frozen=True)
class XianDuanInvariantViolation:
    code: str
    index: int
    detail: str = ""


def _right_tzxl_extra_bis(
    segment: XianDuan,
    bi_list: List[BiBase],
) -> List[BiBase]:
    """返回右侧特征序列区间内、未进入 3 组件的同向笔。"""
    right = segment.right_tzxl
    if right is None or not right.bi_list:
        return []
    first_bi = right.bi_list[0]
    if hasattr(first_bi, "is_up"):
        direction_is_up = first_bi.is_up()
    else:
        direction_is_up = not getattr(right, "is_top", lambda: False)()
    stored = set(right.bi_idx_list)
    extras: List[BiBase] = []
    for index in range(right.left_bi_idx, right.right_bi_idx + 1):
        bi = bi_list[index]
        if bi.is_up() == direction_is_up and index not in stored:
            extras.append(bi)
    return extras


class XianDuanInvariants:
    """线段结构不变量检查，只服务 xianduan.py。"""

    def __init__(self, ctx: XianDuanContext):
        self.ctx = ctx

    def check(self, segments: List[XianDuanBase]) -> List[XianDuanInvariantViolation]:
        violations: List[XianDuanInvariantViolation] = []
        bi_list = self.ctx.bi_list
        for index, segment in enumerate(segments):
            if segment.start_bi_idx < 0 or segment.end_bi_idx >= len(bi_list):
                violations.append(
                    XianDuanInvariantViolation("index_bounds", index, "笔索引越界")
                )
                continue
            if segment.start_bi_idx > segment.end_bi_idx:
                violations.append(
                    XianDuanInvariantViolation("index_order", index, "起点笔索引大于终点")
                )
                continue
            if not segment.has_enough_bi():
                violations.append(
                    XianDuanInvariantViolation("min_bi_count", index, "少于三笔")
                )

            if isinstance(segment, (FakeXianDuanFirst, FakeXianDuanLast)):
                continue

            covered = bi_list[segment.start_bi_idx:segment.end_bi_idx + 1]
            true_high = max(float(bi.high_price) for bi in covered)
            true_low = min(float(bi.low_price) for bi in covered)
            true_range = true_high - true_low
            if true_range > 0:
                if segment.is_up():
                    deviation = float(segment.start_price) - true_low
                else:
                    deviation = true_high - float(segment.start_price)
                start_error = max(0.0, deviation / true_range)
                if start_error > EXTREMUM_REPAIR_THRESHOLD:
                    violations.append(
                        XianDuanInvariantViolation(
                            "start_extreme_deviation",
                            index,
                            f"起点偏离真实极值 {start_error:.2%}",
                        )
                    )

            best_idx = None
            best_price = None
            for bi_idx in range(segment.start_bi_idx, segment.end_bi_idx + 1):
                bi = bi_list[bi_idx]
                if bi.is_up() != segment.is_up():
                    continue
                price = float(bi.end_price)
                if (
                    best_idx is None
                    or price_is_more_extreme(price, best_price, segment.is_up())
                    or (price_is_same(price, best_price) and bi_idx > best_idx)
                ):
                    best_idx = bi_idx
                    best_price = price
            if best_idx is not None and best_idx != segment.end_bi_idx:
                violations.append(
                    XianDuanInvariantViolation(
                        "end_not_extreme_bi",
                        index,
                        "终点不是同向笔极值",
                    )
                )

            start_price = float(bi_list[segment.start_bi_idx].start_price)
            for bi_idx in range(segment.start_bi_idx, segment.end_bi_idx + 1):
                bi = bi_list[bi_idx]
                if bi.is_up() == segment.is_up():
                    continue
                price = float(bi.end_price)
                if segment.is_up() and price < start_price - 1e-8:
                    violations.append(
                        XianDuanInvariantViolation(
                            "penetrates_start", index, "反向笔穿透起点"
                        )
                    )
                    break
                if not segment.is_up() and price > start_price + 1e-8:
                    violations.append(
                        XianDuanInvariantViolation(
                            "penetrates_start", index, "反向笔穿透起点"
                        )
                    )
                    break

            if segment.left_tzxl is not None and segment.right_tzxl is not None:
                # 当前 TeZhengXuLie 只保留合并后的 3 个组件；第 4 笔及以后
                # 不在该结构内。跨线段扫描会把后续趋势误判为违规，因此这里
                # 只严格检查右侧特征序列的第 2、3 笔。
                right_bis = segment.right_tzxl.bi_list[1:]
                if right_bis:
                    if segment.is_down():
                        right_high = max(float(bi.high_price) for bi in right_bis)
                        if right_high > float(segment.left_tzxl.high_price) + 1e-8:
                            violations.append(
                                XianDuanInvariantViolation(
                                    "right_tzxl_exceeds_left",
                                    index,
                                    "右侧特征序列第二/三笔最高点超过左侧特征序列最高点",
                                )
                            )
                    else:
                        right_low = min(float(bi.low_price) for bi in right_bis)
                        if right_low < float(segment.left_tzxl.low_price) - 1e-8:
                            violations.append(
                                XianDuanInvariantViolation(
                                    "right_tzxl_below_left",
                                    index,
                                    "右侧特征序列第二/三笔最低点低于左侧特征序列最低点",
                                )
                            )

                extras = _right_tzxl_extra_bis(segment, bi_list)
                if extras:
                    left_high = float(segment.left_tzxl.high_price)
                    left_low = float(segment.left_tzxl.low_price)
                    left_range = abs(left_high - left_low)
                    if left_range <= 1e-8:
                        left_range = abs(
                            float(segment.start_price) - float(segment.end_price)
                        )
                    tolerance = left_range * EXTREMUM_REPAIR_THRESHOLD
                    if segment.is_down():
                        worst = max(float(bi.high_price) for bi in extras)
                        excess = worst - left_high
                    else:
                        worst = min(float(bi.low_price) for bi in extras)
                        excess = left_low - worst
                    if excess > tolerance + 1e-8:
                        violations.append(
                            XianDuanInvariantViolation(
                                "right_tzxl_later_exceeds_left",
                                index,
                                f"右侧特征序列后续笔超出左侧极值 {excess:.4f}，"
                                f"超过阈值 {tolerance:.4f}",
                            )
                        )

        for index in range(1, len(segments)):
            previous = segments[index - 1]
            current = segments[index]
            if previous.is_up() == current.is_up():
                violations.append(
                    XianDuanInvariantViolation(
                        "direction_not_alternating", index, "相邻线段方向相同"
                    )
                )
            if previous.end_time != current.start_time:
                violations.append(
                    XianDuanInvariantViolation(
                        "not_continuous", index, "相邻线段时间不连续"
                    )
                )
            if previous.end_bi_idx + 1 != current.start_bi_idx:
                violations.append(
                    XianDuanInvariantViolation(
                        "bi_coverage_gap", index, "相邻线段笔覆盖不连续"
                    )
                )
        return violations


@dataclass(frozen=True)
class XianDuanRepair:
    action: str
    index: int
    detail: str = ""


class XianDuanRepairLoop:
    """不变量驱动的线段修复规划器。

    当前只做 ``plan``，不直接替换默认管线。真正应用修复需要单独 feature flag
    和全量 diff 验证。
    """

    def __init__(
        self,
        ctx: XianDuanContext,
        endpoint_ops: XianDuanEndpointOps,
        repair_ops: XianDuanRepairOps,
        invariants: XianDuanInvariants,
    ):
        self.ctx = ctx
        self.endpoint_ops = endpoint_ops
        self.repair_ops = repair_ops
        self.invariants = invariants

    def plan(self, segments: List[XianDuanBase]) -> List[XianDuanRepair]:
        repairs: List[XianDuanRepair] = []
        for violation in self.invariants.check(segments):
            if violation.code == "direction_not_alternating":
                repairs.append(XianDuanRepair("merge_same_direction", violation.index))
            elif violation.code in ("not_continuous", "bi_coverage_gap"):
                repairs.append(XianDuanRepair("fill_gap", violation.index))
            elif violation.code == "min_bi_count":
                repairs.append(XianDuanRepair("merge_neighbor", violation.index))
            elif violation.code == "start_extreme_deviation":
                repairs.append(XianDuanRepair("move_start_to_extreme", violation.index))
            elif violation.code == "end_not_extreme_bi":
                repairs.append(XianDuanRepair("move_end_to_extreme", violation.index))
            elif violation.code == "penetrates_start":
                repairs.append(XianDuanRepair("split_or_merge_penetrated", violation.index))
            elif violation.code in ("index_bounds", "index_order"):
                repairs.append(XianDuanRepair("drop_invalid_segment", violation.index))
        return repairs

    def run(self, segments: List[XianDuanBase], max_iterations: int = 10):
        """返回 (当前线段, 修复计划)。

        目前不应用修复，避免在未完成全量验证前改变默认结果。
        """
        current = list(segments)
        repairs: List[XianDuanRepair] = []
        for _ in range(max_iterations):
            repairs = self.plan(current)
            if not repairs:
                break
            break
        return current, repairs


class XianDuanStateMachine:
    """线段双候选状态机，只服务 xianduan.py。

    把 lm/mr/finish_deque 的推进逻辑从 ``generate_xian_duan`` 中独立出来，
    但仍然是线段专用实现，不与笔共用。
    """

    def __init__(
        self,
        ctx: XianDuanContext,
        endpoint_ops: XianDuanEndpointOps,
        repair_ops: XianDuanRepairOps,
    ):
        self.ctx = ctx
        self.endpoint_ops = endpoint_ops
        self.repair_ops = repair_ops
        self.tzxl_deque = deque(
            (ctx.tzxl_list[i], ctx.tzxl_list[i + 1])
            for i in range(len(ctx.tzxl_list) - 1)
        )
        self.finish_deque = deque()
        self.xd_lm: Optional[XianDuanBase] = None
        self.xd_mr: Optional[XianDuanBase] = None
        self.xd_xy: Optional[XianDuanBase] = None

    def adjust_pair(self, xd_lm, xd_mr):
        """在 lm 和 mr 都完成的前提下，追寻 lm 延伸到更极值的价格。"""
        if xd_lm is None or xd_mr is None:
            return xd_lm, xd_mr
        origin_tzxl = xd_mr.left_tzxl
        origin_type = origin_tzxl.type
        old_tzxl = origin_tzxl
        start_idx = -1 if isinstance(xd_lm, FakeXianDuanFirst) else xd_lm.left_tzxl.idx
        end_idx = xd_mr.right_tzxl.idx
        for i in range(start_idx + 1, end_idx):
            new_tzxl = self.ctx.tzxl_list[i]
            if new_tzxl.type == origin_type and (
                (new_tzxl.is_top() and new_tzxl.high_price > old_tzxl.high_price)
                or (new_tzxl.is_bottom() and new_tzxl.low_price < old_tzxl.low_price)
            ):
                if isinstance(xd_lm, FakeXianDuanFirst):
                    import copy
                    new_xd_lm = copy.copy(xd_lm)
                    new_xd_lm.invalidate_cache()
                    new_xd_lm.right_tzxl = new_tzxl
                    if new_xd_lm.right_tzxl is xd_lm.right_tzxl:
                        raise ValueError("new_xd_lm的right_tzxl和xd_lm不可能相等")
                    new_xd_lm.end_bi_idx = new_tzxl.mid_bi_idx - 1
                    new_xd_lm.end_idx = new_tzxl.mid_bi.start_idx
                    new_xd_lm.end_time = new_tzxl.start_time
                    new_xd_lm.end_price = new_tzxl.start_price
                else:
                    new_xd_lm = XianDuan.from_tzxl(xd_lm.left_tzxl, new_tzxl, self.ctx.bi_list)
                new_xd_mr = XianDuan.from_tzxl(new_tzxl, xd_mr.right_tzxl, self.ctx.bi_list)

                if new_xd_lm.is_finished and new_xd_mr.is_finished:
                    xd_lm = new_xd_lm
                    xd_mr = new_xd_mr
                    old_tzxl = new_tzxl

        return xd_lm, xd_mr

    def advance_both(self):
        """推进 lm 和 mr：lm=mr，从 tzxl_deque 取下一对创建新 mr。"""
        self.xd_lm = self.xd_mr
        if self.tzxl_deque:
            x_tzxl, y_tzxl = self.tzxl_deque.popleft()
            self.xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl, self.ctx.bi_list)
        else:
            self.xd_mr = None

    def find_first(self) -> bool:
        """lm 未完成但 mr 已完成时，在已完成队列中寻找 lm。"""
        while self.finish_deque:
            last_xd_finish = self.finish_deque.pop()
            if last_xd_finish.xianduan_type == self.xd_lm.xianduan_type:
                self.xd_lm = last_xd_finish
                self.xd_mr = XianDuan.from_tzxl(
                    self.xd_lm.right_tzxl,
                    self.xd_mr.right_tzxl,
                    self.ctx.bi_list,
                )
                self.xd_lm, self.xd_mr = self.adjust_pair(self.xd_lm, self.xd_mr)
                if self.xd_lm.is_finished and self.xd_mr.is_finished:
                    return True
                continue

            if last_xd_finish.xianduan_type == self.xd_mr.xianduan_type:
                self.xd_mr = XianDuan.from_tzxl(
                    last_xd_finish.left_tzxl,
                    self.xd_mr.right_tzxl,
                    self.ctx.bi_list,
                )
                if self.xd_mr.is_finished:
                    return False
                continue

        return False

    def find_second(self) -> bool:
        """mr 未完成但 xy 已能包含 lm 时，在已完成队列中寻找 lm 的反向延长。"""
        while self.finish_deque:
            last_xd_finish = self.finish_deque.pop()
            if last_xd_finish.xianduan_type == self.xd_mr.xianduan_type:
                tmp_xd_mr = XianDuan.from_tzxl(
                    last_xd_finish.left_tzxl,
                    self.xd_mr.right_tzxl,
                    self.ctx.bi_list,
                )
                if tmp_xd_mr.is_finished:
                    self.xd_mr = tmp_xd_mr
                    return False

            elif last_xd_finish.xianduan_type == self.xd_lm.xianduan_type:
                tmp_xd_mr = XianDuan.from_tzxl(
                    last_xd_finish.left_tzxl,
                    self.xd_xy.right_tzxl,
                    self.ctx.bi_list,
                )
                if tmp_xd_mr.is_finished:
                    if self.finish_deque:
                        self.xd_mr = tmp_xd_mr
                        self.xd_lm = self.finish_deque.pop()
                    elif self.tzxl_deque:
                        self.xd_lm = tmp_xd_mr
                        x_tzxl, y_tzxl = self.tzxl_deque.popleft()
                        self.xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl, self.ctx.bi_list)
                    else:
                        self.xd_lm = tmp_xd_mr
                        self.xd_mr = None
                    return True

            else:
                raise ValueError("find_second_xd_in_finish_deque 发现意外的线段")

        return False

    def run(self):
        """执行主状态机循环。"""
        if len(self.tzxl_deque) < 2:
            return

        l_tzxl, m_tzxl = self.tzxl_deque.popleft()
        m_tzxl, r_tzxl = self.tzxl_deque.popleft()
        self.xd_lm = XianDuan.from_tzxl(l_tzxl, m_tzxl, self.ctx.bi_list)
        self.xd_mr = XianDuan.from_tzxl(m_tzxl, r_tzxl, self.ctx.bi_list)

        while self.tzxl_deque:
            if self.xd_lm is None or self.xd_mr is None:
                break
            is_xd_lm_finished = self.xd_lm.is_finished
            is_xd_mr_finished = self.xd_mr.is_finished

            if is_xd_lm_finished and is_xd_mr_finished:
                self.xd_lm, self.xd_mr = self.adjust_pair(self.xd_lm, self.xd_mr)
                self.finish_deque.append(self.xd_lm)
                self.advance_both()
                continue

            elif not is_xd_lm_finished and is_xd_mr_finished:
                if not self.find_first():
                    self.advance_both()
                continue

            elif not is_xd_mr_finished:
                x_tzxl, y_tzxl = self.tzxl_deque.popleft()
                self.xd_xy = XianDuan.from_tzxl(x_tzxl, y_tzxl, self.ctx.bi_list)
                if self.xd_xy.xianduan_type == self.xd_lm.xianduan_type:
                    if self.xd_lm.extends_beyond_end(self.xd_xy.end_price):
                        if self.xd_lm.extends_beyond_start(self.xd_xy.start_price):
                            if not self.find_second():
                                self.xd_lm = self.xd_mr
                                self.xd_mr = XianDuan.from_tzxl(
                                    self.xd_mr.right_tzxl,
                                    y_tzxl,
                                    self.ctx.bi_list,
                                )
                            continue

                        temp_xd_lm = XianDuan.from_tzxl(
                            self.xd_lm.left_tzxl,
                            self.xd_xy.right_tzxl,
                            self.ctx.bi_list,
                        )

                        if not self.tzxl_deque:
                            self.xd_lm = temp_xd_lm
                            self.xd_mr = None
                            break

                        x_tzxl, y_tzxl = self.tzxl_deque.popleft()
                        temp_xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl, self.ctx.bi_list)

                        if temp_xd_lm.is_finished and temp_xd_mr.is_finished:
                            self.xd_lm = temp_xd_lm
                            self.xd_mr = temp_xd_mr
                        else:
                            temp_xd_lm2 = self.xd_lm
                            temp_xd_mr2 = XianDuan.from_tzxl(
                                temp_xd_lm2.right_tzxl,
                                temp_xd_mr.right_tzxl,
                                self.ctx.bi_list,
                            )
                            if temp_xd_lm2.is_finished and temp_xd_mr2.is_finished:
                                self.xd_lm = temp_xd_lm2
                                self.xd_mr = temp_xd_mr2
                            else:
                                self.xd_lm = temp_xd_lm
                                self.xd_mr = temp_xd_mr
                        continue

                elif self.xd_xy.xianduan_type == self.xd_mr.xianduan_type:
                    new_xd_mr = XianDuan.from_tzxl(
                        self.xd_mr.left_tzxl,
                        self.xd_xy.right_tzxl,
                        self.ctx.bi_list,
                    )
                    if new_xd_mr.is_finished or (
                        (self.xd_xy.is_up() and self.xd_xy.end_price >= self.xd_mr.end_price)
                        or (self.xd_xy.is_down() and self.xd_xy.end_price <= self.xd_mr.end_price)
                    ):
                        self.xd_mr = new_xd_mr
                    continue
                else:
                    raise RuntimeError("不应该存在其他情况")

            else:
                raise RuntimeError("不应该存在其他情况")

    def merge_last_unfinished(self) -> bool:
        """末端候选未确认时，回溯合并为最后一条已确认大线段。"""
        if (
            self.xd_lm is None
            or self.xd_mr is None
            or not self.xd_lm.is_finished
            or self.xd_mr.is_finished
        ):
            return False
        if not self.finish_deque:
            return False

        previous_xd = self.finish_deque[-1]
        if not isinstance(previous_xd, XianDuan):
            return False
        if previous_xd.right_tzxl.idx != self.xd_lm.left_tzxl.idx:
            return False

        merged_xd = XianDuan.from_tzxl(
            previous_xd.left_tzxl,
            self.xd_mr.right_tzxl,
            self.ctx.bi_list,
        )
        if not merged_xd.is_finished:
            return False

        self.finish_deque.pop()
        self.finish_deque.append(merged_xd)
        self.xd_lm = None
        self.xd_mr = None
        return True

    def repair_queue_gaps(self):
        """补齐状态机跳过的未确认区间，保证完成队列首尾相接。"""
        repaired_queue = deque([])
        for segment in self.finish_deque:
            if repaired_queue:
                previous = repaired_queue[-1]
                if previous.end_time < segment.start_time:
                    start_idx = previous.right_tzxl.idx
                    end_idx = segment.left_tzxl.idx
                    if start_idx > end_idx or any(
                        self.ctx.tzxl_list[cursor].type == self.ctx.tzxl_list[cursor - 1].type
                        for cursor in range(start_idx + 1, end_idx + 1)
                    ):
                        raise RuntimeError("补齐线段间隔时，特征序列方向不连续")
                    connector = None
                    fallback_connector = None
                    for cursor in range(start_idx + 1, end_idx + 1):
                        candidate = XianDuan.from_tzxl(
                            self.ctx.tzxl_list[cursor - 1],
                            self.ctx.tzxl_list[cursor],
                            self.ctx.bi_list,
                        )
                        if candidate.start_time == previous.end_time and candidate.is_finished:
                            connector = candidate
                            break
                        if fallback_connector is None and candidate.has_enough_bi():
                            fallback_connector = candidate

                    if connector is None:
                        connector = fallback_connector

                    if connector is None:
                        raise RuntimeError("补齐线段间隔时，无法构造连续连接段")
                    repaired_queue.append(connector)
            repaired_queue.append(segment)

        self.finish_deque = repaired_queue


def _first_real_index(segments: List[XianDuanBase]) -> Optional[int]:
    for index, segment in enumerate(segments):
        if isinstance(segment, XianDuan):
            return index
    return None


def _find_tzxl_at(
    tzxl_list: List[TeZhengXuLie],
    time: pd.Timestamp,
    is_top: bool,
) -> Optional[TeZhengXuLie]:
    for tzxl in tzxl_list:
        if tzxl.start_time == time and tzxl.is_top() == is_top:
            return tzxl
    return None


def _fake_start_index(
    bi_list: List[BiBase],
    end_bi_idx: int,
    is_up: bool,
) -> Optional[int]:
    """在 [0, end_bi_idx] 内选择 fake 线段的极值起点。"""
    candidates = []
    for index in range(0, end_bi_idx + 1):
        bi = bi_list[index]
        if is_up:
            if bi.is_up():
                candidates.append((float(bi.start_price), index))
            else:
                candidates.append((float(bi.end_price), index))
        else:
            if bi.is_down():
                candidates.append((float(bi.start_price), index))
            else:
                candidates.append((float(bi.end_price), index))
    if not candidates:
        return None
    price, index = min(candidates) if is_up else max(candidates)
    if is_up and bi_list[index].is_down():
        index += 1
    elif not is_up and bi_list[index].is_up():
        index += 1
    if index > end_bi_idx - 2:
        return None
    return index


def _find_extreme_start_bi_index(
    bi_list: List[BiBase],
    high_prices: np.ndarray,
    low_prices: np.ndarray,
    origin_bi_idx: int,
    is_up: bool,
    strict: bool = False,
) -> int:
    """在 [0, origin_bi_idx] 内寻找更早的同向极值起点，并校正方向。"""
    sl = slice(0, origin_bi_idx + 1)
    local_max_idx = int(np.argmax(high_prices[sl]))
    local_min_idx = int(np.argmin(low_prices[sl]))
    start_idx = origin_bi_idx
    origin_bi = bi_list[origin_bi_idx]

    if is_up:
        candidate = local_min_idx
        if candidate < origin_bi_idx:
            candidate_price = float(low_prices[candidate])
            origin_price = float(origin_bi.low_price)
            is_more_extreme = (
                candidate_price < origin_price
                if strict
                else candidate_price <= origin_price
            )
            if is_more_extreme:
                start_idx = candidate
    else:
        candidate = local_max_idx
        if candidate < origin_bi_idx:
            candidate_price = float(high_prices[candidate])
            origin_price = float(origin_bi.high_price)
            is_more_extreme = (
                candidate_price > origin_price
                if strict
                else candidate_price >= origin_price
            )
            if is_more_extreme:
                start_idx = candidate

    if bi_list[start_idx].is_up() != is_up:
        start_idx += 1
    return start_idx


def _find_tzxl_by_start_time(
    tzxl_list: List[TeZhengXuLie],
    time: pd.Timestamp,
) -> Optional[TeZhengXuLie]:
    for tzxl in tzxl_list:
        if tzxl.start_time == time:
            return tzxl
    return None


def _make_earliest_candidate(
    first_xd: Union[XianDuan, FakeXianDuanFirst],
    start_bi_idx: int,
    end_bi_idx: int,
    fake_is_up: bool,
    right_tzxl: TeZhengXuLie,
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
    allow_real: bool,
) -> Optional[Union[XianDuan, FakeXianDuanFirst]]:
    """优先把更早起点转成真实线段，否则构造合法 fake 首段。"""
    start_bi = bi_list[start_bi_idx]
    if allow_real:
        new_tzxl = _find_tzxl_by_start_time(tzxl_list, start_bi.start_time)
        if new_tzxl is not None:
            return XianDuan.from_tzxl(new_tzxl, right_tzxl, bi_list)
    fake = _make_fake_first(bi_list, start_bi_idx, end_bi_idx, fake_is_up, right_tzxl)
    if fake is not None and fake.is_finished:
        return fake
    return None


def _make_fake_first(
    bi_list: List[BiBase],
    start_bi_idx: int,
    end_bi_idx: int,
    is_up: bool,
    right_tzxl: Optional[TeZhengXuLie],
) -> Optional[FakeXianDuanFirst]:
    if start_bi_idx < 0 or end_bi_idx >= len(bi_list) or end_bi_idx - start_bi_idx + 1 < 3:
        return None
    start_bi = bi_list[start_bi_idx]
    end_bi = bi_list[end_bi_idx]
    fake = FakeXianDuanFirst()
    fake.xianduan_type = XianDuanDirectionType.UP if is_up else XianDuanDirectionType.DOWN
    fake.start_bi_idx = start_bi_idx
    fake.end_bi_idx = end_bi_idx
    fake.start_idx = start_bi.start_idx
    fake.end_idx = end_bi.end_idx
    fake.start_time = start_bi.start_time
    fake.end_time = end_bi.end_time
    fake.start_price = start_bi.start_price
    fake.end_price = end_bi.end_price
    fake.right_tzxl = right_tzxl
    fake.invalidate_cache()
    return fake if fake.has_enough_bi() else None


def _make_fake_last(
    bi_list: List[BiBase],
    start_bi_idx: int,
    end_bi_idx: int,
    is_up: bool,
    left_tzxl: Optional[TeZhengXuLie] = None,
    require_enough_bi: bool = False,
) -> Optional[FakeXianDuanLast]:
    if start_bi_idx < 0 or end_bi_idx >= len(bi_list) or start_bi_idx > end_bi_idx:
        return None
    if require_enough_bi and end_bi_idx - start_bi_idx + 1 < 3:
        return None
    start_bi = bi_list[start_bi_idx]
    end_bi = bi_list[end_bi_idx]
    fake = FakeXianDuanLast()
    fake.xianduan_type = XianDuanDirectionType.UP if is_up else XianDuanDirectionType.DOWN
    fake.start_bi_idx = start_bi_idx
    fake.end_bi_idx = end_bi_idx
    fake.start_idx = start_bi.start_idx
    fake.end_idx = end_bi.end_idx
    fake.start_time = start_bi.start_time
    fake.end_time = end_bi.end_time
    fake.start_price = start_bi.start_price
    fake.end_price = end_bi.end_price
    fake.left_tzxl = left_tzxl
    fake.invalidate_cache()
    if require_enough_bi and not fake.has_enough_bi():
        return None
    return fake


def _should_prepend_fakes(
    first: XianDuan,
    bi_list: List[BiBase],
) -> bool:
    """首段起点与更早极值持平/更弱时，允许在前面继续补 fake。"""
    if first.start_bi_idx <= 2:
        return False
    earlier = bi_list[: first.start_bi_idx]
    if not earlier:
        return False
    if first.is_down():
        return max(float(bi.high_price) for bi in earlier) >= float(first.start_price) - 1e-8
    return min(float(bi.low_price) for bi in earlier) <= float(first.start_price) + 1e-8


def _prepend_recursive_fakes(
    segments: List[XianDuanBase],
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
) -> List[XianDuanBase]:
    """在首个真实线段前递归补 fake 线段，直到无法再满足三笔。"""
    if not segments or not isinstance(segments[0], XianDuan):
        return segments
    result = list(segments)
    while result:
        first = result[0]
        end_bi_idx = first.start_bi_idx - 1
        if end_bi_idx < 2:
            break
        fake_is_up = not first.is_up()
        start_bi_idx = _fake_start_index(bi_list, end_bi_idx, fake_is_up)
        if start_bi_idx is None:
            break
        right_tzxl = (
            first.left_tzxl
            if isinstance(first, XianDuan)
            else getattr(first, "right_tzxl", None)
        )
        fake = _make_fake_first(
            bi_list,
            start_bi_idx,
            end_bi_idx,
            fake_is_up,
            right_tzxl,
        )
        if fake is None:
            break
        if result and result[0].start_time != fake.end_time:
            break
        result.insert(0, fake)
    return result


def _normalize_first_fake(
    segments: List[XianDuanBase],
    bi_list: List[BiBase],
) -> List[XianDuanBase]:
    """把首段 fake 的起止点校正到合法的笔边界。"""
    if not segments or not isinstance(segments[0], FakeXianDuanFirst):
        return segments
    fake = segments[0]
    start_bi_idx = _fake_start_index(bi_list, fake.end_bi_idx, fake.is_up())
    if start_bi_idx is None or start_bi_idx == fake.start_bi_idx:
        return segments
    normalized = _make_fake_first(
        bi_list,
        start_bi_idx,
        fake.end_bi_idx,
        fake.is_up(),
        getattr(fake, "right_tzxl", None),
    )
    if normalized is None:
        return segments
    result = list(segments)
    result[0] = normalized
    return result


def _try_promote_fake(
    segment: FakeXianDuanFirst,
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
) -> Optional[XianDuan]:
    left = _find_tzxl_at(
        tzxl_list,
        segment.start_time,
        is_top=not segment.is_up(),
    )
    right = _find_tzxl_at(
        tzxl_list,
        segment.end_time,
        is_top=segment.is_up(),
    )
    if left is None or right is None:
        return None
    try:
        real = XianDuan.from_tzxl(left, right, bi_list)
    except ValueError:
        return None
    if not real.is_finished:
        return None
    if (
        real.start_time != segment.start_time
        or real.end_time != segment.end_time
        or real.start_bi_idx != segment.start_bi_idx
        or real.end_bi_idx != segment.end_bi_idx
    ):
        return None
    return real


def promote_secondary_fakes(
    segments: List[XianDuanBase],
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
) -> List[XianDuanBase]:
    """保证全序列最多只有一条 FakeXianDuanFirst。

    从右往左处理所有 fake：
    - 能转真实就转；
    - 不能转真实，就保留这一条，删除它左边的所有线段；
    - 如果全部都能转真实，则最终没有 fake。
    """
    if not segments:
        return segments
    fake_indices = [
        index
        for index, segment in enumerate(segments)
        if isinstance(segment, FakeXianDuanFirst)
    ]
    if not fake_indices:
        return segments

    result = list(segments)
    for index in reversed(fake_indices):
        fake = result[index]
        real = _try_promote_fake(fake, tzxl_list, bi_list)
        if real is not None:
            result[index] = real
            continue
        result = result[index:]
        return result
    return result


def reconcile_first_segments(
    segments: List[XianDuanBase],
    reference_segments: Optional[List[XianDuanBase]],
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
) -> List[XianDuanBase]:
    """用旧缓存的首段作为迁移锚点，避免状态机改写首段。"""
    if not segments:
        return segments
    if not reference_segments:
        if not isinstance(segments[0], FakeXianDuanFirst):
            return segments
        return _prepend_recursive_fakes(
            _normalize_first_fake(segments, bi_list),
            tzxl_list,
            bi_list,
        )
    ref_first_real = _first_real_index(reference_segments)
    new_first_real = _first_real_index(segments)
    if ref_first_real is None or new_first_real is None:
        return segments
    if not isinstance(segments[0], FakeXianDuanFirst):
        ref_first = reference_segments[ref_first_real]
        new_first = segments[new_first_real]
        if (
            new_first.start_bi_idx == ref_first.start_bi_idx
            and new_first.end_bi_idx == ref_first.end_bi_idx
        ):
            if _should_prepend_fakes(new_first, bi_list):
                return _prepend_recursive_fakes(segments, tzxl_list, bi_list)
            return segments
    ref_prefix = None
    tail = None
    for ref_index in range(ref_first_real, len(reference_segments)):
        anchor_time = reference_segments[ref_index].end_time
        start_index = next(
            (
                index
                for index, segment in enumerate(segments)
                if segment.start_time == anchor_time
            ),
            None,
        )
        if start_index is not None:
            ref_prefix = list(reference_segments[: ref_index + 1])
            tail = list(segments[start_index:])
            break
        end_index = next(
            (
                index
                for index, segment in enumerate(segments)
                if segment.end_time == anchor_time
            ),
            None,
        )
        if end_index is not None:
            ref_prefix = list(reference_segments[: ref_index + 1])
            tail = list(segments[end_index + 1 :])
            break
    if ref_prefix is None or tail is None:
        return segments
    result = ref_prefix + tail
    if isinstance(result[0], XianDuan):
        result = _prepend_recursive_fakes(result, tzxl_list, bi_list)
    return result


def _validate_xianduan_structure(
    segments: List[XianDuanBase],
    bi_list: List[BiBase],
) -> None:
    if not segments:
        return
    if np.any(np.diff([item.is_up() for item in segments]) == 0):
        raise RuntimeError("线段结构校验失败: 方向不交替")

    for index, item in enumerate(segments):
        if not 0 <= item.start_bi_idx <= item.end_bi_idx < len(bi_list):
            raise RuntimeError(
                f"线段结构校验失败: 笔覆盖越界 {item.start_bi_idx=}, {item.end_bi_idx=}"
            )
        if not item.has_enough_bi():
            raise RuntimeError(
                f"线段结构校验失败: 笔数不足 {item.start_time=} ~ {item.end_time=}"
            )

        start_bi = bi_list[item.start_bi_idx]
        end_bi = bi_list[item.end_bi_idx]
        if (
            item.start_idx != start_bi.start_idx
            or item.start_time != start_bi.start_time
            or item.start_price != start_bi.start_price
            or item.end_idx != end_bi.end_idx
            or item.end_time != end_bi.end_time
            or item.end_price != end_bi.end_price
        ):
            raise RuntimeError(
                f"线段结构校验失败: 端点与覆盖笔不一致 {item.start_time=} ~ {item.end_time=}"
            )

        if index and segments[index - 1].end_bi_idx + 1 != item.start_bi_idx:
            raise RuntimeError(
                f"线段结构校验失败: 笔覆盖不连续 {segments[index - 1].end_time=} -> {item.start_time=}"
            )

    for previous_item, item in zip(segments, segments[1:]):
        if previous_item.end_idx != item.start_idx:
            raise RuntimeError(
                f"线段结构校验失败: K线边界不连续 {previous_item.end_time=} -> {item.start_time=}"
            )


def _repair_first_segment_reverse_extension(
    segments: List[XianDuanBase],
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
) -> List[XianDuanBase]:
    """首段内部出现更极值反向端点时，补出反向 fake 首段。"""
    if not segments:
        return segments
    first = segments[0]
    if not isinstance(first, XianDuan):
        return segments

    def _repair(primary_is_high: bool) -> List[XianDuanBase]:
        if primary_is_high:
            primary_idx = max(
                range(first.start_bi_idx, first.end_bi_idx + 1),
                key=lambda idx: float(bi_list[idx].high_price),
            )
            if primary_idx <= first.start_bi_idx:
                return segments
            if float(bi_list[primary_idx].high_price) <= float(first.start_price) + 1e-8:
                return segments
            secondary_idx = min(
                range(0, primary_idx + 1),
                key=lambda idx: float(bi_list[idx].low_price),
            )
            primary_bi = bi_list[primary_idx]
            primary_tzxl = next(
                (
                    tzxl
                    for tzxl in tzxl_list
                    if tzxl.start_time == primary_bi.end_time
                    and tzxl.is_top()
                    and abs(float(tzxl.start_price) - float(primary_bi.end_price)) <= 1e-6
                ),
                None,
            )
            fake_is_up = True
        else:
            primary_idx = min(
                range(first.start_bi_idx, first.end_bi_idx + 1),
                key=lambda idx: float(bi_list[idx].low_price),
            )
            if primary_idx <= first.start_bi_idx:
                return segments
            if float(bi_list[primary_idx].low_price) >= float(first.start_price) - 1e-8:
                return segments
            secondary_idx = max(
                range(0, primary_idx + 1),
                key=lambda idx: float(bi_list[idx].high_price),
            )
            primary_bi = bi_list[primary_idx]
            primary_tzxl = next(
                (
                    tzxl
                    for tzxl in tzxl_list
                    if tzxl.start_time == primary_bi.end_time
                    and tzxl.is_bottom()
                    and abs(float(tzxl.start_price) - float(primary_bi.end_price)) <= 1e-6
                ),
                None,
            )
            fake_is_up = False

        if primary_idx - secondary_idx < 3:
            return segments
        if primary_tzxl is None:
            return segments
        try:
            new_first = XianDuan.from_tzxl(primary_tzxl, first.right_tzxl, bi_list)
        except ValueError:
            return segments
        if not new_first.is_finished or not new_first.has_enough_bi():
            return segments
        fake = _make_fake_first(
            bi_list,
            secondary_idx + 1,
            primary_idx,
            fake_is_up,
            primary_tzxl,
        )
        if fake is None:
            return segments
        return [fake, new_first, *segments[1:]]

    return _repair(first.is_down())


def generate_xian_duan(tzxl_list: List[TeZhengXuLie], bi_list: List[BiBase]) -> List[XianDuanBase]:
    """
    根据特征序列分型划分线段。

    实现思路和 generate_bi 保持一致：相邻异类特征序列先形成候选线段，
    在确认前允许同向端点继续延长；满足三笔以上、不出现翻包、第二种
    特征序列缺口被后续确认后，才把候选线段加入结果。
    """

    # 初始化

    xianduan_list = []
    endpoint_ops = XianDuanEndpointOps(bi_list, tzxl_list)
    ctx = XianDuanContext(
        bi_list=bi_list,
        tzxl_list=tzxl_list,
        bi_high_prices=np.array([bi.high_price for bi in bi_list]),
        bi_low_prices=np.array([bi.low_price for bi in bi_list]),
        tzxl_by_time_and_type={
            (tzxl.start_time, tzxl.is_top()): tzxl
            for tzxl in tzxl_list
        },
    )
    repair_ops = XianDuanRepairOps(ctx, endpoint_ops)

    ########################### 辅助函数
    def _start_extremum_error(segment: XianDuanBase) -> float:
        """计算线段起点偏离真实反向极值的比例。"""
        covered_bi_list = bi_list[segment.start_bi_idx:segment.end_bi_idx + 1]
        true_high = max(bi.high_price for bi in covered_bi_list)
        true_low = min(bi.low_price for bi in covered_bi_list)
        true_range = true_high - true_low
        if true_range <= 0:
            return 0.0

        if segment.is_up():
            deviation = segment.start_price - true_low
        else:
            deviation = true_high - segment.start_price
        return max(0.0, deviation / true_range)

    def _find_tzxl_by_time(
        tzxl_by_time_and_type: Dict[Tuple[pd.Timestamp, bool], TeZhengXuLie],
        time: pd.Timestamp,
        is_top: bool,
    ) -> Optional[TeZhengXuLie]:
        return tzxl_by_time_and_type.get((time, is_top))

    def _get_right_tzxl(segment: XianDuanBase) -> Optional[TeZhengXuLie]:
        if isinstance(segment, (XianDuan, FakeXianDuanFirst)):
            return segment.right_tzxl
        return None

    def _set_left_tzxl(segment: XianDuanBase, tzxl: TeZhengXuLie):
        if isinstance(segment, (XianDuan, FakeXianDuanLast)):
            segment.left_tzxl = tzxl

    def _set_right_tzxl(segment: XianDuanBase, tzxl: TeZhengXuLie):
        if isinstance(segment, (XianDuan, FakeXianDuanFirst)):
            segment.right_tzxl = tzxl

    def repair_xianduan_extremes(xianduan_list: List[XianDuanBase]) -> List[XianDuanBase]:
        """修复起点严重偏离真实极值的相邻划分。

        修复时优先保证端点极值和方向交替；随后向后合并最少数量的相邻段，
        使修复后的线段重新满足最少笔数且终点仍是覆盖区间内的真实极值。
        """
        repaired_list = list(xianduan_list)
        tzxl_by_time_and_type: Dict[Tuple[pd.Timestamp, bool], TeZhengXuLie] = {}
        for tzxl in tzxl_list:
            tzxl_by_time_and_type.setdefault((tzxl.start_time, tzxl.is_top()), tzxl)
        index = 1
        while index < len(repaired_list):
            segment = repaired_list[index]
            if _start_extremum_error(segment) <= EXTREMUM_REPAIR_THRESHOLD:
                index += 1
                continue

            extreme_type = "low" if segment.is_up() else "high"
            boundary = endpoint_ops.find_extreme_boundary(segment, extreme_type)
            new_start_bi_idx = boundary["next_start_bi_idx"]
            if new_start_bi_idx <= segment.start_bi_idx or new_start_bi_idx > segment.end_bi_idx:
                index += 1
                continue

            previous = repaired_list[index - 1]
            previous_bi_count = boundary["prev_end_bi_idx"] - previous.start_bi_idx + 1
            if previous_bi_count < 3:
                index += 1
                continue

            absorb_stop = None
            scan_end_bi_idx = new_start_bi_idx - 1
            true_high = float("-inf")
            true_low = float("inf")
            for stop_index in range(index, len(repaired_list), 2):
                if stop_index != index and isinstance(repaired_list[stop_index], FakeXianDuanLast):
                    continue

                candidate_end_bi_idx = repaired_list[stop_index].end_bi_idx
                if candidate_end_bi_idx < new_start_bi_idx + 2:
                    continue

                while scan_end_bi_idx < candidate_end_bi_idx:
                    scan_end_bi_idx += 1
                    scan_bi = bi_list[scan_end_bi_idx]
                    true_high = max(true_high, scan_bi.high_price)
                    true_low = min(true_low, scan_bi.low_price)

                endpoint_bi = bi_list[candidate_end_bi_idx]
                endpoint_extreme = (
                    endpoint_bi.end_price >= true_high if segment.is_up()
                    else endpoint_bi.end_price <= true_low
                )
                boundary_kept_extreme = (
                    boundary["price"] <= true_low if segment.is_up()
                    else boundary["price"] >= true_high
                )
                if endpoint_bi.is_up() == segment.is_up() and boundary_kept_extreme and endpoint_extreme:
                    absorb_stop = stop_index
                    break

            if absorb_stop is None:
                index += 1
                continue

            boundary_tzxl = _find_tzxl_by_time(
                tzxl_by_time_and_type,
                boundary["time"],
                segment.is_down(),
            )
            if boundary_tzxl is None:
                index += 1
                continue

            endpoint_ops.set_boundary(previous, boundary, "end")
            endpoint_ops.set_boundary(segment, boundary, "start")

            final_segment = repaired_list[absorb_stop]
            final_bi = bi_list[final_segment.end_bi_idx]
            final_tzxl = _get_right_tzxl(final_segment)
            if final_tzxl is None and not (
                isinstance(final_segment, FakeXianDuanLast) and final_segment is segment
            ):
                raise RuntimeError("极值修复候选段缺少右侧特征序列")

            final_boundary: ExtremeBoundary = {
                "price": final_bi.end_price,
                "time": final_bi.end_time,
                "kline_idx": final_bi.end_idx,
                "prev_end_bi_idx": final_segment.end_bi_idx,
                "next_start_bi_idx": final_segment.end_bi_idx + 1,
            }
            endpoint_ops.set_boundary(segment, final_boundary, "end")

            _set_left_tzxl(segment, boundary_tzxl)
            _set_right_tzxl(previous, boundary_tzxl)
            if final_tzxl is not None:
                _set_right_tzxl(segment, final_tzxl)

            del repaired_list[index + 1:absorb_stop + 1]
            index += 1

        for segment in repaired_list:
            if not segment.has_enough_bi():
                raise RuntimeError(
                    f"极值修复后线段笔数不足:"
                    f"{segment.start_time} -> {segment.end_time}"
                )

        for index in range(len(repaired_list) - 1):
            if repaired_list[index].end_time != repaired_list[index + 1].start_time:
                raise RuntimeError(
                    f"极值修复后线段连续性检查失败:"
                    f"{repaired_list[index].end_time} -> {repaired_list[index + 1].start_time}"
                )
            if repaired_list[index].is_up() == repaired_list[index + 1].is_up():
                raise RuntimeError("极值修复后线段方向交替检查失败")
        return repaired_list

    def _split_bi_range(start_bi_idx: int, end_bi_idx: int, is_up: bool) -> Optional[List[XianDuanBase]]:
        """按同向终点极值把笔区间完整切成线段；切不完则放弃。"""
        if start_bi_idx > end_bi_idx:
            return []
        segments: List[XianDuanBase] = []
        cursor = start_bi_idx
        direction_up = is_up
        while cursor <= end_bi_idx:
            if bi_list[cursor].is_up() != direction_up:
                return None
            extreme_idx = endpoint_ops.extreme_end_bi_idx(cursor, end_bi_idx, direction_up)
            if extreme_idx is None:
                return None
            segments.append(endpoint_ops.make_bi_range_segment(cursor, extreme_idx, direction_up))
            if extreme_idx == end_bi_idx:
                return segments
            cursor = extreme_idx + 1
            direction_up = not direction_up
        return None

    def _repair_uncovered_prefix(segments: List[XianDuanBase]) -> List[XianDuanBase]:
        """把第一段之前能完整按极值切分、且能反向接上的笔补成线段。"""
        if not segments or not bi_list:
            return segments
        first_start_bi_idx = segments[0].start_bi_idx
        if first_start_bi_idx <= 0:
            return segments
        prefix = _split_bi_range(0, first_start_bi_idx - 1, bi_list[0].is_up())
        if not prefix or prefix[-1].is_up() == segments[0].is_up():
            return segments
        # The first confirmed feature sequence can start later than the first
        # pen. Local extrema alone cannot prove an extra leading segment.
        return segments

    def repair_xianduan_endpoint_extremes(segments: List[XianDuanBase]) -> List[XianDuanBase]:
        """线段终点必须是同向笔极值；尾部能完整反向切分时才截断。

        尾部无法切成完整线段时，若并入下一条反向线段后终点仍是极值，
        且中间没有反向笔突破新起点，则把尾部并入下一条线段。
        """
        repaired = list(segments)
        index = 0
        while index < len(repaired):
            segment = repaired[index]
            extreme_idx = endpoint_ops.extreme_end_bi_idx(segment.start_bi_idx, segment.end_bi_idx, segment.is_up())
            if extreme_idx is None or extreme_idx == segment.end_bi_idx:
                index += 1
                continue
            tail = _split_bi_range(extreme_idx + 1, segment.end_bi_idx, not segment.is_up())
            if tail:
                if index + 1 < len(repaired) and tail[-1].is_up() == repaired[index + 1].is_up():
                    index += 1
                    continue
                endpoint_ops.move_end(segment, extreme_idx)
                repaired[index + 1:index + 1] = tail
                index += 1
                continue
            if repair_ops.absorb_tail_into_next_segment(repaired, index, extreme_idx):
                index += 1
                continue
            index += 1
        return _repair_uncovered_prefix(repaired)

    def _make_local_xianduan(
        direction: XianDuanDirectionType,
        left_tzxl: TeZhengXuLie,
        right_tzxl: TeZhengXuLie,
    ) -> XianDuan:
        segment = XianDuan.from_tzxl(left_tzxl, right_tzxl, bi_list)
        if segment.xianduan_type != direction:
            raise ValueError("局部重切线段方向不一致")
        if not segment.has_enough_bi():
            raise ValueError("局部重切线段笔数不足")
        if not segment.is_finished:
            raise ValueError("局部重切线段未完成")
        return segment

    def repair_xianduan_endpoints_and_wraparound(
        segments: List[XianDuanBase],
    ) -> List[XianDuanBase]:
        """在局部窗口内修复被反向极值穿透的线段端点。

        特征序列只提供候选分界。若下降段内部出现高于起点的顶，或上升段内部出现
        低于起点的底，说明旧分界已经被反向极值穿透。此时仅在后续数段内寻找
        方向极值重切，并保留原有特征序列作为新端点，避免重写全局端点。
        """
        repaired_list = list(segments)
        index = 0
        while index < len(repaired_list) - 1:
            segment = repaired_list[index]
            next_segment = repaired_list[index + 1]
            if isinstance(segment, FakeXianDuanLast) or isinstance(next_segment, FakeXianDuanLast):
                index += 1
                continue
            if isinstance(segment, FakeXianDuanFirst) or segment.left_tzxl is None or segment.right_tzxl is None:
                index += 1
                continue

            window_stop = min(index + 5, len(repaired_list))
            local_segments = [repaired_list[index]]
            for scan_index in range(index + 1, window_stop):
                candidate = repaired_list[scan_index]
                if isinstance(candidate, FakeXianDuanLast):
                    break
                local_segments.append(candidate)
            if len(local_segments) < 2:
                index += 1
                continue

            scan_end_idx = local_segments[-1].end_idx
            scan_tzxl = [
                tzxl for tzxl in tzxl_list
                if segment.start_idx < tzxl.start_idx <= scan_end_idx
            ]
            endpoint_candidates = []
            if segment.is_up():
                endpoint_candidates = [
                    tzxl for tzxl in scan_tzxl
                    if tzxl.is_top()
                    and tzxl.start_price > segment.end_price
                    and (
                        tzxl.start_idx > segment.end_idx
                        or tzxl.start_price > segment.start_price
                    )
                ]
            else:
                endpoint_candidates = [
                    tzxl for tzxl in scan_tzxl
                    if tzxl.is_bottom()
                    and tzxl.start_price < segment.end_price
                    and (
                        tzxl.start_idx > segment.end_idx
                        or tzxl.start_price < segment.start_price
                    )
                ]

            if not endpoint_candidates:
                index += 1
                continue

            if segment.is_up():
                better_endpoint = max(
                    endpoint_candidates,
                    key=lambda tzxl: (tzxl.start_price, tzxl.start_time),
                )
            else:
                better_endpoint = min(
                    endpoint_candidates,
                    key=lambda tzxl: (tzxl.start_price, tzxl.start_time),
                )

            if segment.is_up():
                reverse_candidates = [
                    tzxl for tzxl in scan_tzxl
                    if tzxl.is_bottom() and tzxl.start_idx > better_endpoint.start_idx
                ]
            else:
                reverse_candidates = [
                    tzxl for tzxl in scan_tzxl
                    if tzxl.is_top() and tzxl.start_idx > better_endpoint.start_idx
                ]
            if not reverse_candidates:
                index += 1
                continue

            if segment.is_up():
                reverse_endpoint = min(
                    reverse_candidates,
                    key=lambda tzxl: (tzxl.start_price, tzxl.start_time),
                )
            else:
                reverse_endpoint = max(
                    reverse_candidates,
                    key=lambda tzxl: (tzxl.start_price, tzxl.start_time),
                )

            next_right_candidates = [
                candidate.right_tzxl
                for candidate in local_segments[1:]
                if candidate.is_up() == segment.is_up()
                and candidate.right_tzxl is not None
                and candidate.right_tzxl.start_idx > reverse_endpoint.start_idx
            ]
            if not next_right_candidates:
                index += 1
                continue

            next_right_endpoint = min(
                next_right_candidates,
                key=lambda tzxl: tzxl.start_idx,
            )

            reverse_direction = (
                XianDuanDirectionType.DOWN if segment.is_up() else XianDuanDirectionType.UP
            )
            try:
                extended_segment = _make_local_xianduan(
                    segment.xianduan_type,
                    segment.left_tzxl,
                    better_endpoint,
                )
                reversed_segment = _make_local_xianduan(
                    reverse_direction,
                    better_endpoint,
                    reverse_endpoint,
                )
                shifted_next = _make_local_xianduan(
                    segment.xianduan_type,
                    reverse_endpoint,
                    next_right_endpoint,
                )
            except ValueError:
                index += 1
                continue

            replace_stop = index + 1
            while replace_stop < len(repaired_list):
                if repaired_list[replace_stop].start_idx >= shifted_next.end_idx:
                    break
                replace_stop += 1
            else:
                replace_stop = len(repaired_list)
            if replace_stop <= index + 1:
                index += 1
                continue

            repaired_list[index:replace_stop] = [extended_segment, reversed_segment, shifted_next]

        return repaired_list

    ###########################

    if len(tzxl_list) < 2:
        return xianduan_list
    tzxl_deque = deque((tzxl_list[i], tzxl_list[i + 1]) for i in range(len(tzxl_list) - 1))
    xianduan_finish_deque = deque([])

    if len(tzxl_deque) == 1:
        l_tzxl, r_tzxl = tzxl_deque.popleft()
        xd = XianDuan.from_tzxl(l_tzxl, r_tzxl, bi_list)
        if xd.is_finished:
            xianduan_list.append(xd)
        # 两端都只有少量特征序列时，用真实方向极值补首尾假线段，
        # 避免因状态机缺少后续确认而只画中间一段。
        if xianduan_list:
            confirmed = xianduan_list[0]
            # When the directional tail contains a more extreme endpoint than the
            # sole confirmed candidate, that candidate is only an interior split;
            # keep the direction-level tail and drop it from displayed segments.
            tail_probe_start = confirmed.start_bi_idx
            tail_probe_end = endpoint_ops.extreme_end_bi_idx(
                tail_probe_start,
                len(bi_list) - 1,
                confirmed.is_up(),
            )
            replaced_confirmed = False
            if (
                tail_probe_end is not None
                and price_is_more_extreme(
                    float(bi_list[tail_probe_end].end_price),
                    float(confirmed.end_price),
                    confirmed.is_up(),
                )
            ):
                xianduan_list.clear()
                confirmed = endpoint_ops.make_bi_range_segment(
                    tail_probe_start,
                    tail_probe_end,
                    confirmed.is_up(),
                )
                replaced_confirmed = True
            prefix_direction_up = not confirmed.is_up()
            prefix_start_idx = 0
            if not prefix_direction_up:
                prefix_start_idx = 1
            prefix_end_idx = confirmed.start_bi_idx - 1
            if prefix_end_idx >= prefix_start_idx + 2:
                prefix = endpoint_ops.make_bi_range_segment(
                    prefix_start_idx,
                    prefix_end_idx,
                    prefix_direction_up,
                )
                if prefix.has_enough_bi():
                    xianduan_list.insert(0, prefix)

            suffix_start_idx = confirmed.start_bi_idx
            suffix_end_idx = endpoint_ops.extreme_end_bi_idx(
                suffix_start_idx,
                len(bi_list) - 1,
                confirmed.is_up(),
            )
            if suffix_end_idx is not None:
                suffix = endpoint_ops.make_bi_range_segment(
                    suffix_start_idx,
                    suffix_end_idx,
                    confirmed.is_up(),
                )
                if suffix.has_enough_bi() and replaced_confirmed:
                    xianduan_list.append(suffix)

        return xianduan_list

    # 在此 tzxl_deque至少有两个元素
    machine = XianDuanStateMachine(ctx, endpoint_ops, repair_ops)
    machine.run()
    machine.merge_last_unfinished()

    if (
        machine.xd_lm is not None
        and machine.xd_mr is not None
        and machine.xd_lm.is_finished
        and machine.xd_mr.is_finished
    ):
        machine.xd_lm, machine.xd_mr = machine.adjust_pair(machine.xd_lm, machine.xd_mr)
        machine.finish_deque.append(machine.xd_lm)
        machine.finish_deque.append(machine.xd_mr)
        machine.xd_lm = None
        machine.xd_mr = None
    elif (
        machine.xd_lm is not None
        and machine.xd_lm.is_finished
        and (machine.xd_mr is None or not machine.xd_mr.is_finished)
    ):
        machine.finish_deque.append(machine.xd_lm)
        machine.xd_lm = machine.xd_mr

    machine.repair_queue_gaps()
    xianduan_finish_deque = machine.finish_deque

    def make_fake_last_xd():
        """延长最后一条线段+fake一条线段"""
        nonlocal xianduan_finish_deque, bi_list

        if len(xianduan_finish_deque) == 0:
            return

        last_xd: Union[XianDuan, FakeXianDuanLast, FakeXianDuanFirst] = xianduan_finish_deque.pop()

        if isinstance(last_xd, XianDuan):
            # The tail may still be unconfirmed, but an interior same-direction
            # extreme still bounds this segment. Split there and fake the reverse
            # tail through the current directional low instead of extending
            # through the interior extreme.
            better_endpoint: Optional[TeZhengXuLie] = None
            for tzxl in tzxl_list:
                if last_xd.start_idx >= tzxl.start_idx or tzxl.start_idx >= last_xd.end_idx:
                    continue
                if tzxl.type != last_xd.right_tzxl.type:
                    continue
                if better_endpoint is None or price_is_more_extreme(
                    float(tzxl.start_price),
                    float(better_endpoint.start_price),
                    last_xd.is_up(),
                ):
                    better_endpoint = tzxl

            if (
                better_endpoint is not None
                and price_is_more_extreme(
                    float(better_endpoint.start_price),
                    float(last_xd.end_price),
                    last_xd.is_up(),
                )
            ):
                split_segment = XianDuan.from_tzxl(last_xd.left_tzxl, better_endpoint, bi_list)
                if not split_segment.is_finished:
                    xianduan_finish_deque.append(last_xd)
                    return

                reverse_start_bi_idx = split_segment.end_bi_idx + 1
                reverse_end_bi_idx = endpoint_ops.extreme_end_bi_idx(
                    reverse_start_bi_idx,
                    len(bi_list) - 1,
                    not split_segment.is_up(),
                )
                if reverse_end_bi_idx is None:
                    xianduan_finish_deque.append(last_xd)
                    return

                reverse_tail = endpoint_ops.make_bi_range_segment(
                    reverse_start_bi_idx,
                    reverse_end_bi_idx,
                    not split_segment.is_up(),
                )
                xianduan_finish_deque.extend([split_segment, reverse_tail])

                # The first reverse fake tail may itself need a same-direction
                # extreme tail. Keep processing the new tail instead of stopping
                # after one split.
                next_reverse_start_bi_idx = reverse_tail.end_bi_idx + 1
                next_reverse_end_bi_idx = endpoint_ops.extreme_end_bi_idx(
                    next_reverse_start_bi_idx,
                    len(bi_list) - 1,
                    not reverse_tail.is_up(),
                )
                if (
                    next_reverse_end_bi_idx is not None
                    and next_reverse_end_bi_idx >= next_reverse_start_bi_idx + 2
                ):
                    next_reverse_tail = endpoint_ops.make_bi_range_segment(
                        next_reverse_start_bi_idx,
                        next_reverse_end_bi_idx,
                        not reverse_tail.is_up(),
                    )
                    if next_reverse_tail.has_enough_bi():
                        xianduan_finish_deque.append(next_reverse_tail)
                return

        if isinstance(last_xd, (XianDuan, FakeXianDuanFirst)):
            origin_end_cursor_bi_index = last_xd.right_tzxl.mid_bi_idx
        else:
            # 只有FakeXianDuanLast
            origin_end_cursor_bi_index = last_xd.end_bi_idx
        end_bi_index = origin_end_cursor_bi_index
        sl = slice(end_bi_index, len(bi_list))
        bi_high_prices = ctx.bi_high_prices[sl]
        bi_low_prices = ctx.bi_low_prices[sl]
        local_max_idx = int(np.argmax(bi_high_prices))
        local_min_idx = int(np.argmin(bi_low_prices))

        if last_xd.is_up() and local_max_idx > 0 and bi_high_prices[
            local_max_idx] > \
            bi_list[end_bi_index].high_price:
            end_bi_index = end_bi_index + local_max_idx
        elif last_xd.is_down() and local_min_idx > 0 and bi_low_prices[
            local_min_idx] < bi_list[end_bi_index].low_price:
            end_bi_index = end_bi_index + local_min_idx

        last_xd_extend = False
        if end_bi_index != origin_end_cursor_bi_index:
            # 最后一段能延长
            last_xd_extend = True

        ##### 考虑fake_latest_xd存在的可能性

        fake_latest_xd_exist = False
        last_xd_new_tzxl = None  # 扩展后的新线段是否有新的特征序列

        if not last_xd_extend:
            fake_latest_xd_exist = True
        else:
            extend_dest_time = bi_list[end_bi_index].end_time

            for ix in tzxl_list:
                if isinstance(last_xd, XianDuan) and ix.start_time <= last_xd.left_tzxl.start_time:
                    continue
                if ix.start_time == extend_dest_time:
                    fake_latest_xd_exist = True
                    last_xd_new_tzxl = ix
                    break

        def _make_fake_last_xd_extend_by_extrema():
            """用极值点来延长线段"""
            nonlocal last_xd, end_bi_index, bi_list
            start_bi_idx = last_xd.start_bi_idx
            first_bi = bi_list[start_bi_idx]
            end_bi = bi_list[end_bi_index]
            # end_bi_index+1的逻辑不需要往上移，因为end_bi_index的初值源自右侧特征序列游标，比较起来比较直观
            if first_bi.is_up() != end_bi.is_up():
                end_bi_index += 1
                end_bi = bi_list[end_bi_index]

            fake_last_xd = _make_fake_last(
                bi_list,
                start_bi_idx,
                end_bi_index,
                last_xd.is_up(),
            )
            if fake_last_xd is not None:
                last_xd = fake_last_xd

        def _make_fake_latest_xd():
            """
            制造fake latest xd线段
            """
            nonlocal xianduan_finish_deque, bi_list, fake_latest_xd, last_xd
            # 函数外部将xianduan_finish_deque pop出一个后才进入这个函数，所以xianduan_finish_deque长度可能为0，不需要判断
            if last_xd.is_up():
                fake_last_xd_direction_type = XianDuanDirectionType.DOWN
            else:
                fake_last_xd_direction_type = XianDuanDirectionType.UP

            if isinstance(last_xd, (XianDuan, FakeXianDuanFirst)):
                first_bi_index = last_xd.right_tzxl.mid_bi_idx
            else:
                # 只有FakeXianDuanLast
                first_bi_index = last_xd.end_bi_idx + 1
            end_bi_index = last_xd.right_tzxl.right_bi_idx
            sl = slice(end_bi_index, len(bi_list))

            bi_high_prices = ctx.bi_high_prices[sl]
            bi_low_prices = ctx.bi_low_prices[sl]
            local_max_idx = int(np.argmax(bi_high_prices))
            local_min_idx = int(np.argmin(bi_low_prices))

            if fake_last_xd_direction_type == XianDuanDirectionType.UP and local_max_idx > 0 and bi_high_prices[
                local_max_idx] > \
                bi_list[end_bi_index].high_price:
                end_bi_index = end_bi_index + local_max_idx
            elif fake_last_xd_direction_type == XianDuanDirectionType.DOWN and local_min_idx > 0 and bi_low_prices[
                local_min_idx] < bi_list[end_bi_index].low_price:
                end_bi_index = end_bi_index + local_min_idx

            first_bi = bi_list[first_bi_index]
            end_bi = bi_list[end_bi_index]

            fake_dest_time = end_bi.end_time

            # 有可能出现假线段变真线段的情况，例如all_etf/516700SH  20260611前后线段变真线段
            fake_is_true = False
            new_fx = None

            for idx in tzxl_list:
                if isinstance(last_xd, XianDuan) and idx.start_time <= last_xd.left_tzxl.start_time:
                    continue
                if idx.start_time == fake_dest_time:
                    new_fx = idx
                    fake_is_true = True
                    break

            if fake_is_true and new_fx is not None:
                if not isinstance(last_xd.right_tzxl, TeZhengXuLie):
                    raise ValueError(f"last_xd.right_tzxl不是TeZhengXuLie")
                fake_latest_xd = XianDuan.from_tzxl(last_xd.right_tzxl, new_fx, bi_list)


            else:
                fake_latest_xd = _make_fake_last(
                    bi_list,
                    first_bi_index,
                    end_bi_index,
                    fake_last_xd_direction_type == XianDuanDirectionType.UP,
                )

        fake_latest_xd: Optional[Union[XianDuan, FakeXianDuanLast]] = None

        if last_xd_extend and fake_latest_xd_exist:
            if last_xd_new_tzxl is None:
                raise ValueError(f"last_xd_extend和fake_latest_xd_exist为True时，last_xd_new_tzxl不能为None")
            if isinstance(last_xd, XianDuan):

                last_xd = XianDuan.from_tzxl(last_xd.left_tzxl, last_xd_new_tzxl, bi_list)
            elif isinstance(last_xd, FakeXianDuanFirst):
                last_xd = last_xd.extend(last_xd_new_tzxl)
            else:
                raise ValueError(f"last_xd类型错误")
            _make_fake_latest_xd()
        elif last_xd_extend and not fake_latest_xd_exist:
            _make_fake_last_xd_extend_by_extrema()
        elif not last_xd_extend and fake_latest_xd_exist:
            _make_fake_latest_xd()

        xianduan_finish_deque.append(last_xd)
        if fake_latest_xd is not None:
            xianduan_finish_deque.append(fake_latest_xd)

            while isinstance(fake_latest_xd, XianDuan):
                last_xd = fake_latest_xd
                fake_latest_xd = None
                _make_fake_latest_xd()
                if fake_latest_xd is not None:
                    xianduan_finish_deque.append(fake_latest_xd)

    def make_fake_first_xd_extend():
        """
         fake延长first线段
        """
        nonlocal xianduan_finish_deque, bi_list
        if len(xianduan_finish_deque) == 0:
            return
        first_xd: Union[XianDuan, FakeXianDuanFirst] = xianduan_finish_deque.popleft()

        origin_first_bi_index = first_xd.start_bi_idx
        first_bi_index = _find_extreme_start_bi_index(
            bi_list,
            ctx.bi_high_prices,
            ctx.bi_low_prices,
            origin_first_bi_index,
            first_xd.is_up(),
            strict=False,
        )
        first_bi = bi_list[first_bi_index]

        # 如果没找到更早更极值的笔，则不变
        first_xd_reverse_extend = first_bi_index != origin_first_bi_index

        def _make_fake_earliest_xd():
            """
            制造fake earliest线段
            """
            nonlocal xianduan_finish_deque, bi_list, fake_earliest_xd, first_xd
            # 函数外部将xianduan_finish_deque popleft出一个后才进入这个函数，所以xianduan_finish_deque长度可能为0，不需要判断
            if first_xd.is_up():
                fake_earliest_xd_direction_type = XianDuanDirectionType.DOWN
            else:
                fake_earliest_xd_direction_type = XianDuanDirectionType.UP

            origin_first_bi_index = first_xd.start_bi_idx - 1
            if origin_first_bi_index <= 0:
                return
            first_bi_index = _find_extreme_start_bi_index(
                bi_list,
                ctx.bi_high_prices,
                ctx.bi_low_prices,
                origin_first_bi_index,
                fake_earliest_xd_direction_type == XianDuanDirectionType.UP,
                strict=True,
            )
            first_bi = bi_list[first_bi_index]
            # 如果没变化，或者变化量小于2，则不进行fake线段的制造
            if first_bi_index == origin_first_bi_index or (origin_first_bi_index - first_bi_index) < 2:
                return

            candidate = _make_earliest_candidate(
                first_xd,
                first_bi_index,
                origin_first_bi_index,
                fake_earliest_xd_direction_type == XianDuanDirectionType.UP,
                first_xd.left_tzxl,
                tzxl_list,
                bi_list,
                allow_real=True,
            )
            if candidate is not None:
                fake_earliest_xd = candidate

        if first_xd_reverse_extend:
            candidate = _make_earliest_candidate(
                first_xd,
                first_bi_index,
                first_xd.end_bi_idx,
                first_xd.is_up(),
                first_xd.right_tzxl,
                tzxl_list,
                bi_list,
                allow_real=isinstance(first_xd, XianDuan),
            )
            if candidate is not None:
                first_xd = candidate

        fake_earliest_xd: Optional[Union[XianDuan, FakeXianDuanFirst]] = None

        # 反向延长段完成后，如果始于一个普通分析，那么才能考虑fake_earliest_xd存在的可能性
        if isinstance(first_xd, XianDuan):
            _make_fake_earliest_xd()

        xianduan_finish_deque.appendleft(first_xd)
        # print(f"{first_xd.start_time=},{first_xd.end_time=}")
        if fake_earliest_xd is not None and fake_earliest_xd.is_finished:
            xianduan_finish_deque.appendleft(fake_earliest_xd)
            # print(f"{fake_earliest_xd.start_time=},{fake_earliest_xd.end_time=}")
            while isinstance(fake_earliest_xd, XianDuan):
                first_xd = fake_earliest_xd
                fake_earliest_xd = None
                _make_fake_earliest_xd()
                if fake_earliest_xd is not None and fake_earliest_xd.is_finished:
                    xianduan_finish_deque.appendleft(fake_earliest_xd)

    make_fake_first_xd_extend()

    make_fake_last_xd()

    def make_fake_last_after_xianduan(left_xianduan: XianDuan) -> Optional[FakeXianDuanLast]:
        """以已确认线段末端为起点，用后续真实反向极值构造假线段。"""
        start_bi_idx = left_xianduan.end_bi_idx + 1
        if start_bi_idx >= len(bi_list):
            return None

        fake_direction = XianDuanDirectionType.DOWN if left_xianduan.is_up() else XianDuanDirectionType.UP
        candidate_bi_idx = start_bi_idx
        candidate_price = float("inf") if fake_direction == XianDuanDirectionType.DOWN else float("-inf")
        for bi_idx in range(start_bi_idx, len(bi_list)):
            bi = bi_list[bi_idx]
            price = bi.low_price if fake_direction == XianDuanDirectionType.DOWN else bi.high_price
            if (
                fake_direction == XianDuanDirectionType.DOWN and price < candidate_price
            ) or (
                fake_direction == XianDuanDirectionType.UP and price > candidate_price
            ):
                candidate_bi_idx = bi_idx
                candidate_price = price

        candidate_bi = bi_list[candidate_bi_idx]
        if candidate_bi.is_up() != (fake_direction == XianDuanDirectionType.UP):
            return None

        return _make_fake_last(
            bi_list,
            start_bi_idx,
            candidate_bi_idx,
            fake_direction == XianDuanDirectionType.UP,
            require_enough_bi=True,
        )

    def make_fake_first_before_xianduan(
        left_xianduan: XianDuanBase,
    ) -> Union[XianDuan, FakeXianDuanFirst]:
        """将 fallback 首段左侧延长到更早的真实极值点。"""
        origin_start_bi_idx = left_xianduan.start_bi_idx
        candidate_bi_idx = origin_start_bi_idx
        candidate_price = (
            float("inf") if left_xianduan.is_up() else float("-inf")
        )
        for bi_idx in range(origin_start_bi_idx):
            bi = bi_list[bi_idx]
            price = bi.low_price if left_xianduan.is_up() else bi.high_price
            if (
                left_xianduan.is_up() and price < candidate_price
            ) or (
                not left_xianduan.is_up() and price > candidate_price
            ):
                candidate_bi_idx = bi_idx
                candidate_price = price

        if candidate_bi_idx >= origin_start_bi_idx:
            return left_xianduan

        candidate_bi = bi_list[candidate_bi_idx]
        is_direction_bi = candidate_bi.is_up() == left_xianduan.is_up()
        if not is_direction_bi and candidate_bi_idx + 1 >= origin_start_bi_idx:
            return left_xianduan
        if not is_direction_bi:
            candidate_bi_idx += 1
            candidate_bi = bi_list[candidate_bi_idx]

        right_tzxl = (
            left_xianduan.right_tzxl
            if isinstance(left_xianduan, (XianDuan, FakeXianDuanFirst))
            else None
        )
        fake_xianduan = _make_fake_first(
            bi_list,
            candidate_bi_idx,
            left_xianduan.end_bi_idx,
            left_xianduan.is_up(),
            right_tzxl,
        )
        return fake_xianduan if fake_xianduan is not None else left_xianduan

    def _extend_confirmed_segment_past_penetrated_tail(segment: XianDuan) -> XianDuan:
        """尾段被更极值的同向特征序列穿透时，把已确认线段延到新的极值终点。

        只接受延伸后自身仍然成立、且新尾段不再被反向笔穿透的终点。
        这样不会退回“取最后一个完成分界”而把中间已成立的反向段吞掉。
        """
        current = segment
        while isinstance(current, XianDuan) and current.left_tzxl is not None:
            tail = make_fake_last_after_xianduan(current)
            if tail is None or not repair_ops.range_breaks_start(tail.start_bi_idx, tail.end_bi_idx, tail.is_up()):
                return current

            replacement: Optional[XianDuan] = None
            for tzxl in tzxl_list:
                if tzxl.start_time <= current.end_time or tzxl.start_time > tail.end_time:
                    continue
                if current.is_up():
                    endpoint_is_more_extreme = price_is_more_extreme(
                        float(tzxl.start_price), float(current.end_price), True
                    )
                    if not tzxl.is_top() or not endpoint_is_more_extreme:
                        continue
                elif not tzxl.is_bottom() or not price_is_more_extreme(
                    float(tzxl.start_price), float(current.end_price), False
                ):
                    continue

                extended = XianDuan.from_tzxl(current.left_tzxl, tzxl, bi_list)
                if not extended.is_finished or repair_ops.range_breaks_start(
                    extended.start_bi_idx, extended.end_bi_idx, extended.is_up()
                ):
                    continue
                extended_tail = make_fake_last_after_xianduan(extended)
                if extended_tail is None or not extended_tail.has_enough_bi():
                    continue
                if repair_ops.range_breaks_start(extended_tail.start_bi_idx, extended_tail.end_bi_idx, extended_tail.is_up()):
                    continue
                if replacement is None or price_is_more_extreme(
                    float(extended.end_price), float(replacement.end_price), extended.is_up()
                ):
                    replacement = extended

            if replacement is None:
                return current
            current = replacement
        return current

    def _make_fake_first_reverse_segment(left_xianduan: XianDuanBase) -> Optional[FakeXianDuanLast]:
        """在已确认段左侧按真实反向边界构造 fake 前置段。"""
        if left_xianduan.start_bi_idx <= 1:
            return None
        reverse_up = not left_xianduan.is_up()
        end_bi_idx = left_xianduan.start_bi_idx - 1

        reverse_boundary_idx: Optional[int] = None
        reverse_boundary_price = float("inf") if reverse_up else float("-inf")
        boundary_is_start = False
        for bi_idx in range(0, end_bi_idx + 1):
            bi = bi_list[bi_idx]
            start_price = float(bi.start_price)
            end_price = float(bi.end_price)
            start_is_more_extreme = (
                start_price > reverse_boundary_price
                if not reverse_up
                else start_price < reverse_boundary_price
            )
            if start_is_more_extreme:
                reverse_boundary_price = start_price
                reverse_boundary_idx = bi_idx
                boundary_is_start = True
            end_is_more_extreme = (
                end_price > reverse_boundary_price
                if not reverse_up
                else end_price < reverse_boundary_price
            )
            if end_is_more_extreme:
                reverse_boundary_price = end_price
                reverse_boundary_idx = bi_idx
                boundary_is_start = False
        if reverse_boundary_idx is None:
            return None

        start_bi_idx = reverse_boundary_idx if boundary_is_start else reverse_boundary_idx + 1
        extreme_end_bi_idx = endpoint_ops.extreme_end_bi_idx(start_bi_idx, end_bi_idx, reverse_up)
        if extreme_end_bi_idx is None or extreme_end_bi_idx < start_bi_idx + 2:
            return None
        candidate = endpoint_ops.make_bi_range_segment(start_bi_idx, extreme_end_bi_idx, reverse_up)
        if repair_ops.range_breaks_start(candidate.start_bi_idx, candidate.end_bi_idx, candidate.is_up()):
            return None
        return candidate

    def _merge_penetrated_fake_tail(left_xianduan: XianDuan, right_xianduan: XianDuanBase) -> XianDuan:
        """右侧反向 fake 段中间笔穿透左段终点时，两段应并回同向延伸段。"""
        if right_xianduan.is_up() == left_xianduan.is_up():
            return left_xianduan
        for bi_idx in range(right_xianduan.start_bi_idx, len(bi_list)):
            bi = bi_list[bi_idx]
            if bi.is_up() != left_xianduan.is_up():
                continue
            if price_is_more_extreme(
                float(bi.end_price),
                float(left_xianduan.end_price),
                left_xianduan.is_up(),
            ):
                end_bi_idx = endpoint_ops.extreme_end_bi_idx(
                    left_xianduan.start_bi_idx,
                    len(bi_list) - 1,
                    left_xianduan.is_up(),
                )
                if end_bi_idx is None:
                    return left_xianduan
                return endpoint_ops.make_bi_range_segment(
                    left_xianduan.start_bi_idx,
                    end_bi_idx,
                    left_xianduan.is_up(),
                )
        return left_xianduan

    def _merge_penetrated_opposite_segments(left_xianduan: XianDuanBase, right_xianduan: XianDuanBase) -> XianDuanBase:
        """反向 fake 尾被下一笔同向极值穿透时，按穿透方向重切。"""
        if right_xianduan.is_up() == left_xianduan.is_up():
            return left_xianduan
        check_stop = min(right_xianduan.end_bi_idx + 1, len(bi_list) - 1)
        for bi_idx in range(right_xianduan.end_bi_idx + 1, check_stop + 1):
            bi = bi_list[bi_idx]
            is_left_direction = bi.is_up() == left_xianduan.is_up()
            boundary_price = float(left_xianduan.end_price)
            if is_left_direction:
                penetrated = price_is_more_extreme(
                    float(bi.end_price), boundary_price, left_xianduan.is_up()
                )
                start_bi_idx = left_xianduan.start_bi_idx
                direction_up = left_xianduan.is_up()
            else:
                penetrated = price_is_more_extreme(
                    float(bi.end_price), boundary_price, right_xianduan.is_up()
                )
                start_bi_idx = right_xianduan.start_bi_idx
                direction_up = right_xianduan.is_up()
            if not penetrated:
                continue

            end_bi_idx = endpoint_ops.extreme_end_bi_idx(start_bi_idx, len(bi_list) - 1, direction_up)
            if end_bi_idx is None:
                return left_xianduan
            return endpoint_ops.make_bi_range_segment(start_bi_idx, end_bi_idx, direction_up)
        return left_xianduan

    def find_confirmed_xianduan_pair() -> List[XianDuanBase]:
        """主流程无结果时，寻找最早的已确认线段并补齐末尾假线段。"""
        for left_idx in range(len(tzxl_list)):
            best_split_idx: Optional[int] = None
            best_left_xianduan: Optional[XianDuan] = None
            for split_idx in range(left_idx + 1, len(tzxl_list)):
                if tzxl_list[left_idx].type == tzxl_list[split_idx].type:
                    continue

                left_xianduan = XianDuan.from_tzxl(
                    tzxl_list[left_idx],
                    tzxl_list[split_idx],
                    bi_list,
                )
                if left_xianduan.is_finished and best_left_xianduan is None:
                    best_split_idx = split_idx
                    best_left_xianduan = left_xianduan

            if best_split_idx is None or best_left_xianduan is None:
                continue

            best_left_xianduan = _extend_confirmed_segment_past_penetrated_tail(best_left_xianduan)
            fake_last_xianduan = make_fake_last_after_xianduan(best_left_xianduan)
            if fake_last_xianduan is not None:
                merged_left_xianduan = _merge_penetrated_fake_tail(
                    best_left_xianduan,
                    fake_last_xianduan,
                )
                reverse_first_xianduan = _make_fake_first_reverse_segment(merged_left_xianduan)
                if reverse_first_xianduan is not None and reverse_first_xianduan.has_enough_bi():
                    return [reverse_first_xianduan, merged_left_xianduan]
                fake_first_xianduan = make_fake_first_before_xianduan(merged_left_xianduan)
                return [fake_first_xianduan, merged_left_xianduan]

        return []

    xianduan_list = list(xianduan_finish_deque)
    if xianduan_list:
        repaired_index = 0
        while repaired_index + 1 < len(xianduan_list):
            left_xianduan = xianduan_list[repaired_index]
            right_xianduan = xianduan_list[repaired_index + 1]
            if (
                isinstance(right_xianduan, FakeXianDuanLast)
                and right_xianduan.is_up() != left_xianduan.is_up()
            ):
                merged_xianduan = _merge_penetrated_opposite_segments(
                    left_xianduan,
                    right_xianduan,
                )
                if merged_xianduan is not left_xianduan:
                    replace_stop = repaired_index + 2
                    while (
                        replace_stop < len(xianduan_list)
                        and xianduan_list[replace_stop].start_idx < merged_xianduan.end_idx
                    ):
                        replace_stop += 1
                    del xianduan_list[repaired_index:replace_stop]
                    xianduan_list.insert(repaired_index, merged_xianduan)
                    continue
            repaired_index += 1
    if not xianduan_list:
        xianduan_list = find_confirmed_xianduan_pair()

    if (
        xianduan_list
        and isinstance(xianduan_list[0], FakeXianDuanLast)
        and xianduan_list[0].start_bi_idx > 0
    ):
        reverse_prefix = _make_fake_first_reverse_segment(xianduan_list[0])
        if reverse_prefix is not None and reverse_prefix.has_enough_bi():
            xianduan_list.insert(0, reverse_prefix)
    if len(xianduan_list) >= 3:
        first = xianduan_list[0]
        second = xianduan_list[1]
        third = xianduan_list[2]
        # The state machine may start with an unconfirmed leading candidate.
        # If its high/low is immediately superseded by the following reverse
        # segment and then the third segment renews the original direction,
        # the confirmed segmentation begins from the second candidate.
        if (
            first.is_up() != second.is_up()
            and third.is_up() == first.is_up()
            and second.end_price < first.end_price
            and third.end_price > first.end_price
        ):
            xianduan_list = xianduan_list[1:]
    xianduan_list = repair_ops.merge_same_direction(xianduan_list)
    xianduan_list = repair_xianduan_endpoints_and_wraparound(xianduan_list)

    ####################### 检查
    # 检查笔上下交替
    assert np.all(np.diff([xd.is_up() for xd in xianduan_list]) != 0), "不满足线段上下交替的要求"

    # 检查线段日期连续性
    for i in range(len(xianduan_list) - 1):
        r_trade_date = xianduan_list[i].end_time
        l_trade_date = xianduan_list[i + 1].start_time

        if r_trade_date != l_trade_date:
            print(r_trade_date, l_trade_date)
            raise RuntimeError("线段连续性检查失败")
    ####################### 检查

    # 微调线段
    for i in range(len(xianduan_list) - 1):
        temp_xd_lm = xianduan_list[i]
        temp_xd_mr = xianduan_list[i + 1]

        if isinstance(temp_xd_lm, FakeXianDuanLast) or isinstance(temp_xd_mr, FakeXianDuanLast):
            break
        xianduan_list[i], xianduan_list[i + 1] = machine.adjust_pair(temp_xd_lm, temp_xd_mr)

    # 特征序列只提供候选分界；最终结果必须校准真实极值，避免明显头尾不在极值的线段。
    xianduan_list = repair_xianduan_extremes(xianduan_list)
    xianduan_list = repair_xianduan_endpoint_extremes(xianduan_list)
    xianduan_list = _repair_first_segment_reverse_extension(xianduan_list, tzxl_list, bi_list)
    _validate_xianduan_structure(xianduan_list, bi_list)

    for i in range(len(xianduan_list)):
        xianduan_list[i].idx = i
    return xianduan_list


def generate_xian_duan_with_repair_loop(
    tzxl_list: List[TeZhengXuLie],
    bi_list: List[BiBase],
    max_iterations: int = 10,
    initial_segments: Optional[List[XianDuanBase]] = None,
    copy_input: bool = True,
    use_local_resegment: bool = False,
    allow_count_changing_repairs: bool = False,
) -> List[XianDuanBase]:
    """实验性：先走旧管线，再用不变量修复循环收敛。

    默认管线不调用本函数；它用于 Phase 7 的新旧并行对比。
    """
    if initial_segments is None:
        segments = generate_xian_duan(tzxl_list, bi_list)
    elif copy_input:
        segments = copy.deepcopy(list(initial_segments))
    else:
        segments = list(initial_segments)
    ctx = XianDuanContext(
        bi_list=bi_list,
        tzxl_list=tzxl_list,
        bi_high_prices=np.array([bi.high_price for bi in bi_list]),
        bi_low_prices=np.array([bi.low_price for bi in bi_list]),
        tzxl_by_time_and_type={
            (tzxl.start_time, tzxl.is_top()): tzxl for tzxl in tzxl_list
        },
    )
    endpoint_ops = XianDuanEndpointOps(bi_list, tzxl_list)
    repair_ops = XianDuanRepairOps(ctx, endpoint_ops)
    invariants = XianDuanInvariants(ctx)

    for _ in range(max_iterations):
        violations = invariants.check(segments)
        if not violations:
            break
        changed = False
        for violation in violations:
            index = violation.index
            if index >= len(segments):
                continue
            segment = segments[index]
            if violation.code == "start_extreme_deviation":
                extreme_type = "low" if segment.is_up() else "high"
                boundary = endpoint_ops.find_extreme_boundary(segment, extreme_type)
                if (
                    boundary["next_start_bi_idx"] > segment.start_bi_idx
                    and repair_ops.move_shared_boundary(segments, index, boundary, "start")
                ):
                    changed = True
                    break
            elif violation.code == "end_not_extreme_bi":
                new_end_bi_idx = endpoint_ops.extreme_end_bi_idx(
                    segment.start_bi_idx,
                    segment.end_bi_idx,
                    segment.is_up(),
                )
                if new_end_bi_idx is None:
                    if allow_count_changing_repairs and (
                        repair_ops.merge_invalid_segment_with_next(segments, index)
                        or repair_ops.merge_invalid_segment_with_previous(segments, index)
                        or (use_local_resegment and repair_ops.resegment_invalid_segment(segments, index))
                    ):
                        changed = True
                        break
                elif (
                    new_end_bi_idx != segment.end_bi_idx
                    and repair_ops.move_end_and_next_start(segments, index, new_end_bi_idx)
                ):
                    changed = True
                    break
                elif allow_count_changing_repairs and (
                    repair_ops.merge_invalid_segment_with_next(segments, index)
                    or repair_ops.merge_invalid_segment_with_previous(segments, index)
                    or (use_local_resegment and repair_ops.resegment_invalid_segment(segments, index))
                ):
                    changed = True
                    break
            elif violation.code == "penetrates_start":
                if repair_ops.repair_penetrates_start(segments, index):
                    changed = True
                    break
                if allow_count_changing_repairs and (
                    repair_ops.merge_invalid_segment_with_next(segments, index)
                    or repair_ops.merge_invalid_segment_with_previous(segments, index)
                    or (use_local_resegment and repair_ops.resegment_invalid_segment(segments, index))
                ):
                    changed = True
                    break
            elif violation.code == "direction_not_alternating":
                if allow_count_changing_repairs:
                    segments = repair_ops.merge_same_direction(segments)
                    changed = True
                    break
        if not changed:
            break
    for idx, segment in enumerate(segments):
        segment.idx = idx
    return segments
