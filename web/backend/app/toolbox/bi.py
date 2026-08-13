from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from typing import List, Tuple, Union, Optional

import numpy as np

from .fenxing import FenXing
from .merged_kline import MergedKLine


class BiDirectionType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 上升笔：底→顶
    DOWN = 'down'  # 下降笔：顶→底


@dataclass
class BiBase:
    """笔的基类: 字段分三类——
    1) init 参数: 实例化时由调用方传入(或默认值)
    2) init=False + 默认值: 由 __post_init__ 或外部逻辑事后赋值
    3) Optional: 允许为 None 的可空字段
    """
    # === init 参数(可由调用方传入) ===
    end_idx: int = 0  # 笔结束位置索引(分型所在 K 线索引); 默认 0, 子类/FakeBiLast 会显式传入
    start_price: float = 0.0  # 起始价格(顶/底分型的极值)
    end_price: float = 0.0  # 结束价格(顶/底分型的极值)
    bi_type: Optional[BiDirectionType] = None  # 笔的方向; Bi 在 __post_init__ 推导, FakeBiLast 由构造传入
    left_fx: Optional[FenXing] = None  # 左侧分型; 可空(部分子类构造时不一定有)
    right_fx: Optional[FenXing] = None  # 右侧分型; 可空

    # === 由 __post_init__ / 外部事后赋值(init=False) ===
    start_idx: int = field(init=False, default=0)  # 笔起始位置索引(分型所在 K 线索引)
    start_time: str = field(init=False, default='')  # 起始时间
    end_time: str = field(init=False, default='')  # 结束时间
    real_origin_kline_count: int = field(init=False, default=0)  # 笔包含的真实原始 K 线数量(一端分型最高点到另一端最低点之间)
    real_merged_kline_count: int = field(init=False, default=0)  # 笔包含的真实合并 K 线数量(一端分型最高点到另一端最低点之间)
    has_gap_count: int = field(init=False, default=0)  # 包含缺口数量
    idx: int = field(init=False, default=0)  # 本笔在笔列表中的索引

    def is_up(self) -> bool:
        return self.bi_type == BiDirectionType.UP

    def is_down(self) -> bool:
        return self.bi_type == BiDirectionType.DOWN

    @property
    def high_price(self):
        return max(self.start_price, self.end_price)

    @property
    def low_price(self):
        return min(self.start_price, self.end_price)

    @property
    def origin_kline_count(self):
        """笔包含的原始 K 线数量（一端分型最高点到另一端最低点之间）+缺口数量"""
        return self.real_origin_kline_count + self.has_gap_count

    @property
    def merged_kline_count(self):
        """笔包含的合并 K 线数量（一端分型最高点到另一端最低点之间）+缺口数量"""
        return self.real_merged_kline_count + self.has_gap_count

    def to_dict(self) -> dict:
        """
        将 Bi 对象转换为字典格式（兼容原有 identify_bi 的输出格式）

        Returns:
            dict: 包含 start, end, direction, start_price, end_price 的字典
        """
        return {
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "direction": self.bi_type.value,
            "start_price": self.start_price,
            "end_price": self.end_price
        }

    @cached_property
    def is_finished(self) -> bool:
        """
        判断笔是否可以完成

        Returns:
            bool: 笔是否可以完成
        """

        if not self.is_leaving_interval():
            return False

        if not self.is_kline_count_enough():
            return False

        return True

    def is_kline_count_enough(self) -> bool:
        """
        一笔中有效K线至少四根，并且顶分型最高点到底分型最低点最低点之间共有五根原始K线，跳空一次算一根


        Returns:
            bool: 笔是否包含指定数量的K线

        """
        return self.origin_kline_count >= 5 and self.merged_kline_count >= 4 and self.real_merged_kline_count >= 3

    def is_leaving_interval(self) -> bool:
        """
        判断一端分型是否有一部分能够离开另一端分型

        Returns:
            bool: 笔是否满足底分型和顶分型拉开距离
        """
        ...

    @staticmethod
    def calculate_bi_real_merged_kline_count_and_gap_count(start_kline_idx: int, end_kline_idx: int,
                                                           all_klines: List[MergedKLine],
                                                           prefix_merged: Union[List[int], None] = None,
                                                           prefix_gap: Union[List[int], None] = None) -> Tuple[
        int, int]:
        """
            计算一笔中的真实合并K线数量和缺口数量

        """
        if start_kline_idx >= end_kline_idx:
            raise ValueError(
                f"起始索引不能大于等于结束索引:{all_klines[start_kline_idx]=},{all_klines[end_kline_idx]=}")
        if prefix_merged is not None and prefix_gap is not None:
            bi_real_merged_kline_count = prefix_merged[end_kline_idx + 1] - prefix_merged[start_kline_idx]
            bi_has_gap_count = prefix_gap[end_kline_idx + 1] - prefix_gap[start_kline_idx + 1]
        else:
            bi_real_merged_kline_count = 0
            bi_has_gap_count = 0
            last_idx = start_kline_idx

            while last_idx <= end_kline_idx:
                last_kline = all_klines[last_idx]
                if last_kline.merged_length == 1:
                    bi_real_merged_kline_count += 1
                    # 检测是否有缺口(排除第一根)
                    if last_idx != start_kline_idx and last_kline.has_gap:
                        bi_has_gap_count += 1

                last_idx += 1

        return bi_real_merged_kline_count, bi_has_gap_count

    @staticmethod
    def get_highest_lowest_price(highest_price, lowest_price, start_kline_idx: int, end_kline_idx: int,
                                 all_klines: List[MergedKLine],
                                 high_arr: Union['np.ndarray', None] = None,
                                 low_arr: Union['np.ndarray', None] = None) -> Tuple[float, float, int, int]:
        """
        获取笔中的最高价和最低价

        Args:
            highest_price: 初始最高价
            lowest_price: 初始最低价
            start_kline_idx: 起始K线索引
            end_kline_idx: 结束K线索引
            all_klines: 合并后的K线列表
            high_arr: 预计算的high价格numpy数组（O(1)区间查询）
            low_arr: 预计算的low价格numpy数组（O(1)区间查询）

        Returns:
            Tuple[float, float, int, int]: 最高价, 最低价, 最高价索引, 最低价索引
        """
        if start_kline_idx >= end_kline_idx:
            raise ValueError(
                f"起始索引不能大于等于结束索引:{all_klines[start_kline_idx]=},{all_klines[end_kline_idx]=}")
        if high_arr is not None and low_arr is not None:
            sl = slice(start_kline_idx, end_kline_idx + 1)
            local_high_idx = int(np.argmax(high_arr[sl]))
            local_low_idx = int(np.argmin(low_arr[sl]))
            h_price = float(high_arr[start_kline_idx + local_high_idx])
            l_price = float(low_arr[start_kline_idx + local_low_idx])
            if h_price > highest_price:
                highest_price = h_price
                highest_idx = start_kline_idx + local_high_idx
            else:
                highest_idx = start_kline_idx
            if l_price < lowest_price:
                lowest_price = l_price
                lowest_idx = start_kline_idx + local_low_idx
            else:
                lowest_idx = start_kline_idx
        else:
            last_idx = start_kline_idx
            highest_idx, lowest_idx = last_idx, last_idx

            while last_idx <= end_kline_idx:
                last_kline = all_klines[last_idx]

                # 收集笔中的最高价和最低价
                if last_kline.high_price > highest_price:
                    highest_price = last_kline.merged_high
                    highest_idx = last_idx
                if last_kline.low_price < lowest_price:
                    lowest_price = last_kline.merged_low
                    lowest_idx = last_idx
                last_idx += 1

        return highest_price, lowest_price, highest_idx, lowest_idx

    def print_klines_info(self, all_klines):
        for i in range(self.start_idx, self.end_idx + 1):
            print(all_klines[i])


@dataclass
class FakeBiFront(BiBase):
    """Fake first笔数据结构"""
    all_klines: Optional[List[MergedKLine]] = None


@dataclass
class FakeBiLast(BiBase):
    """Fake last笔数据结构"""
    all_klines: Optional[List[MergedKLine]] = None

    def __post_init__(self):
        # 确定起始和结束索引
        self.start_idx = self.left_fx.low_idx if self.bi_type == BiDirectionType.UP else self.left_fx.high_idx

        if self.end_idx <= self.start_idx:
            raise ValueError(f"结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_time = self.left_fx.trade_datetime
        self.end_time = self.all_klines[self.end_idx].trade_datetime

        self.real_origin_kline_count = self.end_idx - self.start_idx + 1

    @classmethod
    def from_fenxing(cls, left_fx: FenXing, right_fx_mid_idx: int, start_price, end_price, bi_type: BiDirectionType,
                     all_klines: List[MergedKLine], prefix_merged: Union[List[int], None] = None,
                     prefix_gap: Union[List[int], None] = None):
        """
        从两个分型对象中创建一个笔对象

        Args:
            left_fx: 左侧分型对象
            right_fx: 右侧分型对象
            all_klines: 合并后的K线列表

        Returns:
            Bi: 笔对象
        """

        bi_real_merged_kline_count, bi_has_gap_count = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            left_fx.mid_idx, right_fx_mid_idx,
            all_klines, prefix_merged, prefix_gap)

        bi = FakeBiLast(
            left_fx=left_fx,
            end_idx=right_fx_mid_idx,
            bi_type=bi_type,
            all_klines=all_klines,
            start_price=start_price,
            end_price=end_price,
        )

        bi.real_merged_kline_count = bi_real_merged_kline_count
        bi.has_gap_count = bi_has_gap_count

        return bi

    def is_leaving_interval(self) -> bool:
        """
        判断一端分型是否有一部分能够离开另一端分型

        Returns:
            bool: 笔是否满足底分型和顶分型拉开距离
        """
        end_kline = self.all_klines[self.end_idx]
        if self.bi_type == BiDirectionType.UP:
            return self.left_fx.low_price < end_kline.merged_low and self.left_fx.high_price < self.end_price
        else:
            return self.left_fx.high_price > end_kline.merged_high and self.left_fx.low_price > self.end_price


@dataclass
class Bi(BiBase):
    """笔数据结构"""

    # 左右分型
    left_fx: FenXing  # 左侧分型
    right_fx: FenXing  # 右侧分型

    def __post_init__(self):
        self.bi_type = BiDirectionType.UP if self.right_fx.is_top() else BiDirectionType.DOWN

        # 确定起始和结束索引
        self.start_idx = self.left_fx.low_idx if self.bi_type == BiDirectionType.UP else self.left_fx.high_idx
        self.end_idx = self.right_fx.high_idx if self.bi_type == BiDirectionType.UP else self.right_fx.low_idx
        if self.end_idx <= self.start_idx:
            raise ValueError(f"结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_time = self.left_fx.trade_datetime
        self.end_time = self.right_fx.trade_datetime
        self.start_price = self.left_fx.low_price if self.bi_type == BiDirectionType.UP else self.left_fx.high_price
        self.end_price = self.right_fx.high_price if self.bi_type == BiDirectionType.UP else self.right_fx.low_price
        self.real_origin_kline_count = self.end_idx - self.start_idx + 1

    @classmethod
    def from_fenxing(cls, left_fx: FenXing, right_fx: FenXing, all_klines: List[MergedKLine],
                     prefix_merged=None, prefix_gap=None):
        """
        从两个分型对象中创建一个笔对象

        Args:
            left_fx: 左侧分型对象
            right_fx: 右侧分型对象
            all_klines: 合并后的K线列表

        Returns:
            Bi: 笔对象
        """
        if left_fx.fenxing_type == right_fx.fenxing_type:
            raise ValueError(f"分型方向一致: {left_fx.fenxing_type=}")

        bi_real_merged_kline_count, bi_has_gap_count = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            left_fx.mid_idx, right_fx.mid_idx,
            all_klines, prefix_merged, prefix_gap)

        bi = Bi(
            left_fx=left_fx,
            right_fx=right_fx,
        )

        bi.real_merged_kline_count = bi_real_merged_kline_count
        bi.has_gap_count = bi_has_gap_count

        return bi

    def has_different_Fenxing(self) -> bool:
        """
        判断笔是否包含不同的分型

        Returns:
            bool: 笔是否包含不同的分型
        """
        if self.left_fx.fenxing_type == self.right_fx.fenxing_type:
            raise ValueError(f"分型方向一致: {self.left_fx.fenxing_type=}")
        return True

    def is_leaving_interval(self) -> bool:
        """
        判断一端分型是否有一部分能够离开另一端分型

        Returns:
            bool: 笔是否满足底分型和顶分型拉开距离
        """
        if self.bi_type == BiDirectionType.UP:
            return self.left_fx.low_price < self.right_fx.low_price and self.left_fx.high_price < self.right_fx.high_price
        else:
            return self.left_fx.high_price > self.right_fx.high_price and self.left_fx.low_price > self.right_fx.low_price

    def extends_beyond_end(self, price: float) -> bool:
        """判断给定价格是否在本笔方向上超越了本笔终点价格

        UP笔: price > end_price (向上超越顶分型)
        DOWN笔: price < end_price (向下超越底分型)
        """
        if self.is_up():
            return price > self.end_price
        return price < self.end_price

    def extends_beyond_start(self, price: float) -> bool:
        """判断给定价格是否在本笔反方向上超越了本笔起点价格

        UP笔: price < start_price (向下超越底分型)
        DOWN笔: price > start_price (向上超越顶分型)
        """
        if self.is_up():
            return price < self.start_price
        return price > self.start_price


def generate_bi(fenxing_list: List[FenXing], all_klines: List[MergedKLine]) -> List[Union[Bi, FakeBiLast]]:
    """
    根据分型列表划分缠论笔

    Args:
        fenxing_list: 分型对象列表
        all_klines: 合并后的K线列表（可选，用于获取时间信息）

    Returns:
        List[Bi]: Bi 对象列表
    """

    # 将分型列表中的相邻元素两两组合
    fenxing_deque = deque((fenxing_list[i], fenxing_list[i + 1]) for i in range(len(fenxing_list) - 1))
    bi_finish_deque = deque([])

    # 初始化
    bi_list = []
    trade_s = "2023-03-01"
    trade_e = "2024-04-29"
    log_switch = False

    # 预计算：合并K线数量和缺口数量的前缀和（O(1) 查询）
    n_klines = len(all_klines)
    prefix_merged = [0] * (n_klines + 1)
    prefix_gap = [0] * (n_klines + 1)
    for _i in range(n_klines):
        _kl = all_klines[_i]
        prefix_merged[_i + 1] = prefix_merged[_i] + (1 if _kl.merged_length == 1 else 0)
        prefix_gap[_i + 1] = prefix_gap[_i] + (1 if _kl.has_gap else 0)

    # 预计算：high/low 价格数组（用于 O(1) 区间极值查询）
    high_prices = np.array([kl.merged_high for kl in all_klines])
    low_prices = np.array([kl.merged_low for kl in all_klines])

    def _advance_both():
        """推进 lm 和 mr：lm=mr，从 fenxing_deque 取下一对创建新 mr"""
        nonlocal bi_lm, bi_mr, fenxing_deque
        bi_lm = bi_mr
        if len(fenxing_deque) > 0:
            m_fx, r_fx = fenxing_deque.popleft()
            bi_mr = Bi.from_fenxing(m_fx, r_fx, all_klines, prefix_merged, prefix_gap)
        else:
            bi_mr = None

    def find_first_bi_in_finish_deque():
        """适合在lm未完成但mr已完成的情况下，在已完成的队列中寻找笔"""
        nonlocal bi_lm
        nonlocal bi_mr
        while len(bi_finish_deque) > 0:
            last_bi_finish: Bi = bi_finish_deque.pop()
            if log_switch and trade_e >= last_bi_finish.left_fx.trade_datetime >= trade_s:
                print("#" * 50, "old lm弹出")
                print(last_bi_finish)
            if (last_bi_finish.bi_type == bi_lm.bi_type) and (
                (
                    last_bi_finish.is_up() and last_bi_finish.start_price <= bi_lm.start_price) or (
                    last_bi_finish.is_down() and last_bi_finish.start_price >= bi_lm.start_price)):
                bi_lm = Bi.from_fenxing(last_bi_finish.left_fx, bi_lm.right_fx, all_klines, prefix_merged, prefix_gap)
                if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                    print("#" * 50, "lm被替换后")
                    print(f"bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                return True

            #  这行代码按理来说会触发，但从来没有遇到过触发的情况
            if (last_bi_finish.bi_type == bi_mr.bi_type) and (
                (
                    last_bi_finish.is_up() and last_bi_finish.start_price <= bi_mr.start_price) or (
                    last_bi_finish.is_down() and last_bi_finish.start_price >= bi_mr.start_price)):
                bi_mr = Bi.from_fenxing(last_bi_finish.left_fx, bi_mr.right_fx, all_klines, prefix_merged, prefix_gap)
                raise ValueError(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
        return False

    def find_second_bi_in_finish_deque():
        """适合在mr未完成但xy已经能够包含lm的情况（lm与xy同向）， 在已完成的队列中寻找笔

        返回True指，能在last_bi_finish中找到lm的反向延长
        """
        nonlocal bi_lm
        nonlocal bi_mr
        nonlocal bi_xy
        while len(bi_finish_deque) > 0:
            last_bi_finish = bi_finish_deque.pop()
            if log_switch and trade_e >= last_bi_finish.left_fx.trade_datetime >= trade_s:
                print("#" * 50, "last_bi_finish弹出")
                print(f"{last_bi_finish=}")
            if (last_bi_finish.bi_type == bi_mr.bi_type):
                if (
                    last_bi_finish.bi_type == BiDirectionType.UP and last_bi_finish.start_price <= bi_mr.start_price) or (
                    last_bi_finish.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price >= bi_mr.start_price):
                    bi_mr = Bi.from_fenxing(last_bi_finish.left_fx, bi_mr.right_fx, all_klines, prefix_merged,
                                            prefix_gap)
                    return False
            elif (last_bi_finish.bi_type == bi_lm.bi_type):
                # bi_mr是未完成
                if (bi_mr.bi_type == BiDirectionType.UP and last_bi_finish.start_price >= bi_mr.end_price) or (
                    bi_mr.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price <= bi_mr.end_price):

                    bi_mr = Bi.from_fenxing(last_bi_finish.left_fx, bi_xy.right_fx, all_klines, prefix_merged,
                                            prefix_gap)
                    if len(bi_finish_deque) > 0:
                        bi_lm = bi_finish_deque.pop()

                    elif len(fenxing_deque) > 0:
                        bi_lm = bi_mr
                        x_fx, y_fx = fenxing_deque.popleft()
                        bi_mr = Bi.from_fenxing(x_fx, y_fx, all_klines, prefix_merged, prefix_gap)
                    else:
                        bi_mr = None
                    return True
            else:
                raise ValueError(f"{last_bi_finish=} 是意外的方向")

            if log_switch and (
                (trade_e >= bi_mr.left_fx.trade_datetime >= trade_s) or (
                trade_e >= bi_mr.right_fx.trade_datetime >= trade_s)):
                print("#" * 50, "mr被替换后")
                print(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")

        return False

    """调整deque中的前两笔，使其满足：在mr完成之前，尽可能延长lm"""

    if len(fenxing_deque) < 2:
        return bi_list

    l_fx, m_fx = fenxing_deque.popleft()
    m_fx, r_fx = fenxing_deque.popleft()

    bi_lm = Bi.from_fenxing(l_fx, m_fx, all_klines, prefix_merged, prefix_gap)
    bi_mr = Bi.from_fenxing(m_fx, r_fx, all_klines, prefix_merged, prefix_gap)

    while len(fenxing_deque) > 0:
        if bi_mr is None:
            break
        is_bi_lm_finish = bi_lm.is_finished
        is_bi_mr_finish = bi_mr.is_finished
        # if log_switch and bi_mr.left_fx.trade_datetime == '2025-10-27' and bi_mr.right_fx.trade_datetime == '2025-11-03':
        #     print(bi_mr)
        #     bi_mr.print_klines_info(all_klines)

        if is_bi_lm_finish and is_bi_mr_finish:
            if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                print("#" * 50, "加入")
                print(f"bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                print(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
            bi_finish_deque.append(bi_lm)
            _advance_both()
            if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                print("#" * 50, "加入后")
                print(f"new bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                print(f"new bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
            continue

        # if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
        #     print(f"lm和mr任一未完成：{is_bi_lm_finish=}   {is_bi_mr_finish=}")
        #     print(f"bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
        #     print(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")

        elif not is_bi_lm_finish and is_bi_mr_finish:
            if not find_first_bi_in_finish_deque():
                _advance_both()
            continue
        elif not is_bi_mr_finish:

            x_fx, y_fx = fenxing_deque.popleft()

            bi_xy = Bi.from_fenxing(x_fx, y_fx, all_klines, prefix_merged, prefix_gap)

            if bi_xy.bi_type == bi_lm.bi_type:
                if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                    print("@" * 50, "和lm同趋势,变更前")
                    print(f"bi_xy:{bi_xy.left_fx.trade_datetime}~{bi_xy.right_fx.trade_datetime}")
                    print(f"bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                    print(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
                # 轻量级价格判断，避免创建完整 Bi 对象（O(n) → O(1)）
                xy_end_price = y_fx.high_price if bi_xy.is_up() else y_fx.low_price
                # 必须用bi_mr.right_fx而不是bi_xy.left_fx，因为要保持lm和mr的连贯性
                xy_start_price = bi_mr.right_fx.low_price if bi_xy.is_up() else bi_mr.right_fx.high_price
                if bi_lm.extends_beyond_end(xy_end_price):
                    if bi_lm.extends_beyond_start(xy_start_price):
                        # print(xy_start_price , xy_end_price)
                        if not find_second_bi_in_finish_deque():
                            bi_lm = bi_mr
                            # 必须用bi_mr.right_fx而不是bi_xy.left_fx，因为要保持lm和mr的连贯性
                            bi_mr = Bi.from_fenxing(bi_mr.right_fx, y_fx, all_klines, prefix_merged, prefix_gap)
                        if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                            print("@" * 50, "和lm同趋势，find_second_bi_in_finish_deque后")
                            print(f"new bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                            print(f"new bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
                        continue

                    bi_lm = Bi.from_fenxing(bi_lm.left_fx, y_fx, all_klines, prefix_merged, prefix_gap)

                    if len(fenxing_deque) == 0:
                        # 这里可能会导致lm和mr重叠，后续fake逻辑会处理，最后还会检查
                        if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                            print("@" * 50, "和lm同趋势，fenxing_deque为空，退出")
                        break
                    x_fx, y_fx = fenxing_deque.popleft()
                    bi_mr = Bi.from_fenxing(x_fx, y_fx, all_klines, prefix_merged, prefix_gap)
                    if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                        print("@" * 50, "和lm同趋势，变更后")
                        print(f"new bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                        print(f"new bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")


            elif bi_xy.bi_type == bi_mr.bi_type:
                if bi_mr.extends_beyond_end(bi_xy.end_price):
                    if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                        print("$" * 50, "和mr同趋势，变更前")
                        print(f"bi_xy:{bi_xy.left_fx.trade_datetime}~{bi_xy.right_fx.trade_datetime}")
                        print(f"bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                        print(f"bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
                    bi_mr = Bi.from_fenxing(bi_mr.left_fx, bi_xy.right_fx, all_klines, prefix_merged, prefix_gap)
                    if log_switch and trade_e >= bi_lm.left_fx.trade_datetime >= trade_s:
                        print("$" * 50, "和mr同趋势，变更后")
                        print(f"new bi_lm:{bi_lm.left_fx.trade_datetime}~{bi_lm.right_fx.trade_datetime}")
                        print(f"new bi_mr:{bi_mr.left_fx.trade_datetime}~{bi_mr.right_fx.trade_datetime}")
            else:
                raise ValueError(f"笔类型不符合预期:{bi_xy.bi_type}")
        else:
            raise ValueError(f"{is_bi_lm_finish=}  {is_bi_mr_finish=}  出现意外情况")

    def make_fake_front_bi():
        nonlocal bi_finish_deque, all_klines
        # fake 第一笔
        if len(bi_finish_deque) <= 1:
            return
        first_bi: BiBase = bi_finish_deque.popleft()
        origin_first_kline_index = first_bi.start_idx
        first_kline_index = origin_first_kline_index
        sl = slice(0, origin_first_kline_index + 1)

        local_max_idx = int(np.argmax(high_prices[sl]))
        local_min_idx = int(np.argmin(low_prices[sl]))

        if first_bi.is_down() and local_max_idx < origin_first_kline_index and \
            high_prices[local_max_idx] >= all_klines[origin_first_kline_index].high_price:
            first_kline_index = local_max_idx
        elif first_bi.is_up() and local_min_idx < origin_first_kline_index and \
            low_prices[local_min_idx] <= all_klines[origin_first_kline_index].low_price:
            first_kline_index = local_min_idx

        # 如果能找到更早更极值的笔，则延长
        first_bi_extend = False
        if first_kline_index != origin_first_kline_index:
            first_bi_extend = True

        ##### 考虑fake_earliest_bi存在的可能性
        fake_earliest_bi_exist = False
        # 在fake_first_bi之前，还有可能存在一笔更早的反向笔（如603533SH），这一笔的前提是first_kline_index（含）之前至少有3根k线（考虑跳空两次）
        if first_kline_index < 2:
            fake_earliest_bi_exist = False

        if first_bi.is_up():
            earliest_extrame_index = local_max_idx
        else:
            earliest_extrame_index = local_min_idx

        if earliest_extrame_index >= first_kline_index:
            fake_earliest_bi_exist = False

        real_merged_kline_count = prefix_merged[first_kline_index + 1] - prefix_merged[earliest_extrame_index]
        real_origin_kline_count = first_kline_index - earliest_extrame_index + 1
        has_gap_count = prefix_gap[first_kline_index + 1] - prefix_gap[earliest_extrame_index + 1]
        origin_kline_count = real_origin_kline_count + has_gap_count
        merged_kline_count = real_merged_kline_count + has_gap_count

        if origin_kline_count >= 5 and merged_kline_count >= 4 and real_merged_kline_count >= 3:
            fake_earliest_bi_exist = True

        def _make_first_bi_extend_by_extrema():
            """用极值点来延长比"""
            nonlocal first_bi, first_kline_index, all_klines, prefix_merged, prefix_gap
            first_kline = all_klines[first_kline_index]

            fake_first_bi = FakeBiFront()
            fake_first_bi.start_idx = first_kline_index
            fake_first_bi.end_idx = first_bi.end_idx
            fake_first_bi.start_price = first_kline.low_price if first_bi.is_up() else first_kline.high_price
            fake_first_bi.end_price = first_bi.end_price
            fake_first_bi.right_fx = first_bi.right_fx
            fake_first_bi.start_time = first_kline.trade_datetime
            fake_first_bi.end_time = first_bi.end_time

            fake_first_bi.real_origin_kline_count = (first_bi.real_origin_kline_count + origin_first_kline_index -
                                                     first_kline_index)

            # 计算fake_first_bi 的real_merged_kline_count和has_gap_count
            # 搜索截止到左分型的左边merged_kline末尾
            end_kline_idx = first_bi.left_fx.end_idx_list[0]

            fake_first_bi.real_merged_kline_count = (
                first_bi.real_merged_kline_count + prefix_merged[end_kline_idx + 1] -
                prefix_merged[first_kline_index])
            fake_first_bi.has_gap_count = (first_bi.has_gap_count + prefix_gap[end_kline_idx + 1] -
                                           prefix_gap[first_kline_index + 1])
            fake_first_bi.bi_type = first_bi.bi_type

            first_bi = fake_first_bi

        def _make_fake_earliest_bi():
            nonlocal fake_earliest_bi, first_bi
            fake_earliest_bi = FakeBiFront()
            fake_earliest_bi.start_idx = earliest_extrame_index
            fake_earliest_bi.end_idx = first_kline_index
            fake_earliest_bi.start_price = high_prices[earliest_extrame_index] if first_bi.is_up() \
                else low_prices[earliest_extrame_index]
            fake_earliest_bi.end_price = first_bi.start_price
            if isinstance(first_bi, Bi):
                fake_earliest_bi.right_fx = first_bi.right_fx
            fake_earliest_bi.start_time = all_klines[earliest_extrame_index].trade_datetime
            fake_earliest_bi.end_time = first_bi.start_time
            fake_earliest_bi.real_origin_kline_count = real_origin_kline_count
            fake_earliest_bi.real_merged_kline_count = real_merged_kline_count
            fake_earliest_bi.has_gap_count = has_gap_count
            fake_earliest_bi.bi_type = BiDirectionType.DOWN if first_bi.is_up() else BiDirectionType.UP

        fake_earliest_bi = None

        if first_bi_extend and fake_earliest_bi_exist:
            tx_datetime = all_klines[first_kline_index].trade_datetime
            # first_bi_extend有左分型
            new_fx = None
            for ix in fenxing_list:
                if ix.trade_datetime == tx_datetime:
                    new_fx = ix
                    break
            if new_fx is None:
                raise ValueError(f"没有找到笔的左分型:{tx_datetime}")

            if first_bi.right_fx is None:
                raise ValueError(f"笔的右分型不存在:{first_bi.right_fx}")

            first_bi = Bi.from_fenxing(new_fx, first_bi.right_fx, all_klines, prefix_merged, prefix_gap)

            _make_fake_earliest_bi()
        elif first_bi_extend and not fake_earliest_bi_exist:
            # first_bi_extend无左分型
            _make_first_bi_extend_by_extrema()
        elif not first_bi_extend and fake_earliest_bi_exist:
            _make_fake_earliest_bi()

        bi_finish_deque.appendleft(first_bi)
        if fake_earliest_bi is not None:
            bi_finish_deque.appendleft(fake_earliest_bi)

    make_fake_front_bi()

    # 最后一笔lm
    if bi_lm.is_finished:
        bi_finish_deque.append(bi_lm)
        if bi_mr is not None and bi_mr.is_finished:
            bi_finish_deque.append(bi_mr)
            bi_lm = bi_mr
            bi_mr = None

    bi_list = list(bi_finish_deque)

    # 最后一笔mr
    if not bi_lm.is_finished:
        for i in range(len(bi_list)):
            bi_list[i].idx = i
        return bi_list

    # === 漏网之鱼1号：在最后一笔之后寻找可成立的真实笔，适用于图中最后一根K线没有形成分型结构导致疑似lm后缺失显示两笔（一完成一未完成）的情况 ===
    start_idx = bi_lm.right_fx.right_idx
    end_idx = len(all_klines) - 1
    init_highest_price = bi_lm.right_fx.high_price
    init_lowest_price = bi_lm.right_fx.low_price

    if start_idx < end_idx:
        highest_price, lowest_price, highest_idx, lowest_idx = BiBase.get_highest_lowest_price(
            init_highest_price, init_lowest_price, start_idx, end_idx, all_klines, high_prices, low_prices)

        # 遍历后续分型（避免列表切片拷贝），找到 mid_idx 命中极值点的第一个分型
        new_bi_mr = None
        for i in range(bi_lm.right_fx.idx + 1, len(fenxing_list)):
            fx = fenxing_list[i]
            if fx.mid_idx == highest_idx or fx.mid_idx == lowest_idx:
                new_bi_mr = Bi.from_fenxing(bi_lm.right_fx, fx, all_klines, prefix_merged, prefix_gap)
                break

        if new_bi_mr is not None and new_bi_mr.is_finished and new_bi_mr.bi_type != bi_lm.bi_type:
            bi_list.append(new_bi_mr)

        if new_bi_mr is None:
            new_bi_mr = bi_lm

        # === 漏网之鱼2号：在1号笔之后创建反向 FakeBiLast ===
        # 只需计算反方向极值（UP笔→找最低，DOWN笔→找最高），避免冗余双向扫描
        is_up = new_bi_mr.bi_type == BiDirectionType.UP
        scan_start = new_bi_mr.right_fx.right_idx
        sl = slice(scan_start, end_idx + 1)

        if is_up:
            local_idx = int(np.argmin(low_prices[sl]))
            extreme_idx = scan_start + local_idx
            extreme_price = float(low_prices[extreme_idx])
            fake_type = BiDirectionType.DOWN
        else:
            local_idx = int(np.argmax(high_prices[sl]))
            extreme_idx = scan_start + local_idx
            extreme_price = float(high_prices[extreme_idx])
            fake_type = BiDirectionType.UP

        fake_bi_mr = FakeBiLast.from_fenxing(
            left_fx=new_bi_mr.right_fx, right_fx_mid_idx=extreme_idx,
            start_price=new_bi_mr.end_price, end_price=extreme_price,
            bi_type=fake_type, all_klines=all_klines,
            prefix_merged=prefix_merged, prefix_gap=prefix_gap)

        if fake_bi_mr.is_finished:
            if new_bi_mr.is_finished:
                bi_list.append(fake_bi_mr)
        else:
            if bi_lm.bi_type is not None and fake_bi_mr.bi_type == bi_lm.bi_type and bi_lm.extends_beyond_end(
                fake_bi_mr.end_price):
                fake_bi_mr = FakeBiLast.from_fenxing(
                    left_fx=bi_lm.left_fx, right_fx_mid_idx=fake_bi_mr.end_idx,
                    start_price=bi_lm.start_price, end_price=fake_bi_mr.end_price,
                    bi_type=bi_lm.bi_type, all_klines=all_klines,
                    prefix_merged=prefix_merged, prefix_gap=prefix_gap)

                if bi_list[-1] is bi_lm:
                    bi_list.pop()
                bi_list.append(fake_bi_mr)

    ####################### 检查
    # 检查笔的极值在两端
    for bi in bi_list:
        if type(bi) == FakeBiFront or type(bi) == FakeBiLast:
            continue
        init_highest_price = max(bi.left_fx.high_price, bi.right_fx.high_price)
        init_lowest_price = min(bi.left_fx.low_price, bi.right_fx.low_price)
        start_idx = bi.left_fx.right_idx
        end_idx = bi.end_idx
        # print(init_highest_price, init_lowest_price, start_idx, end_idx)
        highest_price, lowest_price, highest_idx, lowest_idx = BiBase.get_highest_lowest_price(init_highest_price,
                                                                                               init_lowest_price,
                                                                                               start_idx,
                                                                                               end_idx, all_klines,
                                                                                               high_prices, low_prices)
        if highest_price > init_highest_price:
            text = f"顶分型最高价不是一笔中的最高价: {highest_price=}>[{min(bi.left_fx.low_price, bi.right_fx.low_price)},{init_highest_price}],{bi.left_fx.trade_datetime=}~{bi.right_fx.trade_datetime=}"
            print(text)
            print(bi)
            raise RuntimeError(text)
        if lowest_price < init_lowest_price:
            text = f"底分型最低价不是一笔中的最低价: {lowest_price=}<[{init_lowest_price},{max(bi.left_fx.high_price, bi.right_fx.high_price)}],{bi.left_fx.trade_datetime=}~{bi.right_fx.trade_datetime=}"
            print(text)
            print(bi)
            raise RuntimeError(text)
    # 检查笔连续性
    for i in range(len(bi_list) - 1):
        if isinstance(bi_list[i], Bi):
            r_trade_date = bi_list[i].right_fx.trade_datetime
        else:
            r_trade_date = all_klines[bi_list[i].end_idx].trade_datetime

        l_trade_date = bi_list[i + 1].left_fx.trade_datetime

        if r_trade_date != l_trade_date:
            print(r_trade_date, l_trade_date)
            raise RuntimeError("笔连续性检查失败")

    # 检查笔上下交替
    assert np.all(np.diff([bi.bi_type == BiDirectionType.UP for bi in bi_list]) != 0), "不满足笔上下交替的要求"
    ####################### 检查
    print(f"共{len(bi_list)}笔")
    for i in range(len(bi_list)):
        bi_list[i].idx = i
    return bi_list
