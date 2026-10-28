from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from typing import List, Tuple, Union, Optional

import numpy as np
import pandas as pd

from .fenxing import FenXing, FenXingType
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
    start_time: pd.Timestamp = field(init=False, default=pd.NaT)  # 起始时间
    end_time: pd.Timestamp = field(init=False, default=pd.NaT)  # 结束时间
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
        return True

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
    all_klines: Optional[List[MergedKLine]] = field(init=True, default_factory=list, repr=False)


@dataclass
class FakeBiLast(BiBase):
    """Fake last笔数据结构"""
    all_klines: Optional[List[MergedKLine]] = field(init=True, default_factory=list, repr=False)

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

        # 向左延长不能穿过比终点更极端的价格，否则第一笔的极值不在端点分型上。
        if first_kline_index != origin_first_kline_index:
            if first_bi.is_up():
                covered_extreme = float(np.max(high_prices[first_kline_index:origin_first_kline_index + 1]))
                endpoint_extreme = float(first_bi.end_price)
                blocks_extension = covered_extreme > endpoint_extreme + 1e-8
            else:
                covered_extreme = float(np.min(low_prices[first_kline_index:origin_first_kline_index + 1]))
                endpoint_extreme = float(first_bi.end_price)
                blocks_extension = covered_extreme < endpoint_extreme - 1e-8
            if blocks_extension:
                first_kline_index = origin_first_kline_index

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

    def split_fake_front_bi_by_internal_extreme():
        """用首伪笔内部极值替换首笔终点和下一条笔起点。"""
        if not bi_list or not isinstance(bi_list[0], FakeBiFront):
            return False

        front_bi = bi_list[0]
        if len(bi_list) < 2 or not isinstance(bi_list[1], Bi):
            return False

        next_bi = bi_list[1]
        extreme_fx = None
        extreme_value = front_bi.end_price
        for candidate_fx in fenxing_list:
            if candidate_fx.mid_idx >= next_bi.left_fx.mid_idx:
                break
            if candidate_fx.mid_idx <= front_bi.start_idx:
                continue
            candidate_value = candidate_fx.low_price if front_bi.is_down() else candidate_fx.high_price
            if (candidate_value < extreme_value) if front_bi.is_down() else (candidate_value > extreme_value):
                extreme_value = candidate_value
                extreme_fx = candidate_fx

        if (
                extreme_fx is None
                or extreme_fx.mid_idx <= front_bi.start_idx
                or extreme_fx.mid_idx >= next_bi.left_fx.mid_idx
        ):
            return False

        try:
            replaced_next_bi = Bi.from_fenxing(
                extreme_fx,
                next_bi.right_fx,
                all_klines,
                prefix_merged,
                prefix_gap,
            )
        except ValueError:
            return False
        if not replaced_next_bi.is_finished:
            return False

        extreme_idx = extreme_fx.low_idx if front_bi.is_down() else extreme_fx.high_idx
        historic_bi = FakeBiFront(
            end_idx=extreme_idx,
            start_price=front_bi.start_price,
            end_price=extreme_fx.low_price if front_bi.is_down() else extreme_fx.high_price,
            bi_type=front_bi.bi_type,
            all_klines=all_klines,
        )
        historic_bi.start_idx = front_bi.start_idx
        historic_bi.start_time = front_bi.start_time
        historic_bi.end_time = extreme_fx.trade_datetime
        (
            historic_bi.real_merged_kline_count,
            historic_bi.has_gap_count,
        ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            historic_bi.start_idx,
            historic_bi.end_idx,
            all_klines,
            prefix_merged,
            prefix_gap,
        )
        historic_bi.real_origin_kline_count = historic_bi.end_idx - historic_bi.start_idx + 1
        if not historic_bi.is_kline_count_enough() or historic_bi.start_idx >= historic_bi.end_idx:
            return False

        bi_list[0:2] = [historic_bi, replaced_next_bi]
        return True

    def split_fake_front_bi_by_internal_extreme_permissively():
        """宽松处理无法满足严格边界的首伪笔。"""
        if not bi_list or not isinstance(bi_list[0], FakeBiFront):
            return False

        front_bi = bi_list[0]
        if len(bi_list) < 2 or not isinstance(bi_list[1], Bi):
            return False

        next_bi = bi_list[1]
        extreme_fx = None
        extreme_value = front_bi.end_price
        for candidate_fx in fenxing_list:
            if candidate_fx.mid_idx >= next_bi.start_idx:
                break
            if candidate_fx.mid_idx <= front_bi.start_idx:
                continue
            candidate_value = candidate_fx.low_price if front_bi.is_down() else candidate_fx.high_price
            if (candidate_value < extreme_value) if front_bi.is_down() else (candidate_value > extreme_value):
                extreme_value = candidate_value
                extreme_fx = candidate_fx

        if (
                extreme_fx is None
                or extreme_fx.mid_idx >= next_bi.left_fx.mid_idx
        ):
            return False

        try:
            replaced_next_bi = Bi.from_fenxing(
                extreme_fx,
                next_bi.right_fx,
                all_klines,
                prefix_merged,
                prefix_gap,
            )
        except ValueError:
            return False
        if not replaced_next_bi.is_finished or replaced_next_bi.end_idx != next_bi.end_idx:
            return False

        extreme_idx = extreme_fx.low_idx if front_bi.is_down() else extreme_fx.high_idx
        historic_bi = FakeBiFront(
            end_idx=extreme_idx,
            start_price=front_bi.start_price,
            end_price=extreme_fx.low_price if front_bi.is_down() else extreme_fx.high_price,
            bi_type=front_bi.bi_type,
            all_klines=all_klines,
        )
        historic_bi.start_idx = front_bi.start_idx
        historic_bi.start_time = front_bi.start_time
        historic_bi.end_time = extreme_fx.trade_datetime
        (
            historic_bi.real_merged_kline_count,
            historic_bi.has_gap_count,
        ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            historic_bi.start_idx,
            historic_bi.end_idx,
            all_klines,
            prefix_merged,
            prefix_gap,
        )
        historic_bi.real_origin_kline_count = historic_bi.end_idx - historic_bi.start_idx + 1
        if not historic_bi.is_kline_count_enough() or historic_bi.start_idx >= historic_bi.end_idx:
            return False

        bi_list[0:2] = [historic_bi, replaced_next_bi]
        return True

    def split_initial_fake_front_by_internal_extreme():
        """首伪笔后的首正式笔存在更极值端点时，补出首段不完整笔。"""
        if not bi_list or not isinstance(bi_list[0], (Bi, FakeBiFront)):
            return False

        front_bi = bi_list[0]
        if len(bi_list) < 2 or not isinstance(bi_list[1], Bi):
            return False
        next_bi = bi_list[1]
        if front_bi.bi_type == next_bi.bi_type:
            return False
        candidate_fx = None
        candidate_extreme = None
        for fx in fenxing_list:
            if fx.mid_idx >= next_bi.end_idx:
                break
            if fx.mid_idx <= front_bi.end_idx:
                continue
            if front_bi.is_up() and fx.fenxing_type != FenXingType.BOTTOM:
                continue
            if front_bi.is_down() and fx.fenxing_type != FenXingType.TOP:
                continue
            candidate_value = fx.low_price if front_bi.is_up() else fx.high_price
            is_beyond_next_end = (
                candidate_value < next_bi.end_price
                if front_bi.is_up()
                else candidate_value > next_bi.end_price
            )
            if not is_beyond_next_end:
                continue
            if candidate_fx is None or (
                candidate_value < candidate_extreme
                if front_bi.is_up()
                else candidate_value > candidate_extreme
            ):
                candidate_fx = fx
                candidate_extreme = candidate_value

        if candidate_fx is None:
            return False

        start_fx = None
        for fx in fenxing_list:
            if fx.mid_idx >= candidate_fx.mid_idx:
                break
            if fx.fenxing_type == candidate_fx.fenxing_type:
                continue
            start_fx = fx
        if start_fx is None:
            return False

        reverse_bi = None
        reverse_right_fx = None
        for later_fx in fenxing_list[candidate_fx.idx + 1:]:
            if later_fx.idx is None or later_fx.idx >= next_bi.right_fx.idx:
                break
            if later_fx.fenxing_type == candidate_fx.fenxing_type:
                continue
            try:
                candidate_bi = Bi.from_fenxing(candidate_fx, later_fx, all_klines, prefix_merged, prefix_gap)
            except ValueError:
                continue
            if candidate_bi.is_finished and (
                    reverse_bi is None
                    or (candidate_bi.end_price > reverse_bi.end_price if candidate_bi.is_up() else candidate_bi.end_price < reverse_bi.end_price)
            ):
                reverse_bi = candidate_bi
                reverse_right_fx = later_fx
        if reverse_bi is None:
            return False

        extreme_idx = candidate_fx.low_idx if front_bi.is_up() else candidate_fx.high_idx
        start_idx = start_fx.high_idx if front_bi.is_up() else start_fx.low_idx
        first_bi = FakeBiFront(
            end_idx=extreme_idx,
            start_price=start_fx.high_price if front_bi.is_up() else start_fx.low_price,
            end_price=candidate_fx.low_price if front_bi.is_up() else candidate_fx.high_price,
            bi_type=BiDirectionType.DOWN if front_bi.is_up() else BiDirectionType.UP,
            all_klines=all_klines,
        )
        first_bi.start_idx = start_idx
        first_bi.start_time = all_klines[start_idx].trade_datetime
        first_bi.end_time = candidate_fx.trade_datetime
        first_bi.real_origin_kline_count = extreme_idx - start_idx + 1
        (
            first_bi.real_merged_kline_count,
            first_bi.has_gap_count,
        ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            start_idx, extreme_idx, all_klines, prefix_merged, prefix_gap
        )
        remaining_bi = None
        if reverse_right_fx is not next_bi.right_fx:
            try:
                remaining_bi = Bi.from_fenxing(reverse_right_fx, next_bi.right_fx, all_klines, prefix_merged, prefix_gap)
            except ValueError:
                return False
            if not remaining_bi.is_finished:
                return False
        if first_bi.is_kline_count_enough():
            bi_list[0:2] = [first_bi, reverse_bi] if remaining_bi is None else [first_bi, reverse_bi, remaining_bi]
            return True

        # 最近的反向分型凑不够五根K线时，保留已经合格的首笔，只把下一笔拆到这个极值。
        if not front_bi.is_kline_count_enough():
            return False
        end_fx = None
        for fx in fenxing_list:
            if fx.trade_datetime != front_bi.end_time:
                continue
            if front_bi.is_up() != fx.is_top():
                continue
            end_fx = fx
            break
        if end_fx is None:
            return False
        try:
            connector = Bi.from_fenxing(end_fx, candidate_fx, all_klines, prefix_merged, prefix_gap)
        except ValueError:
            return False
        if (
            not connector.is_finished
            or not connector.is_kline_count_enough()
            or connector.end_idx > reverse_bi.start_idx
        ):
            return False
        rebuilt = [front_bi, connector, reverse_bi]
        if remaining_bi is not None:
            rebuilt.append(remaining_bi)
        bi_list[0:2] = rebuilt
        return True

    def split_bi_by_internal_extreme():
        """用相邻两笔区间内的更极值分型重接两笔端点。"""
        for bi_index in range(0, len(bi_list) - 1):
            current_bi = bi_list[bi_index]
            next_bi = bi_list[bi_index + 1]
            if not isinstance(current_bi, Bi) or not isinstance(next_bi, Bi):
                continue

            if current_bi.left_fx is None or next_bi.left_fx is None:
                continue

            extreme_fx = None
            extreme_value = current_bi.end_price
            for candidate_fx in fenxing_list:
                if candidate_fx.mid_idx > next_bi.left_fx.mid_idx:
                    break
                if candidate_fx.mid_idx <= current_bi.left_fx.mid_idx:
                    continue
                candidate_value = candidate_fx.low_price if current_bi.is_down() else candidate_fx.high_price
                if (candidate_value < extreme_value) if current_bi.is_down() else (candidate_value > extreme_value):
                    extreme_value = candidate_value
                    extreme_fx = candidate_fx

            if (
                    extreme_fx is None
                    or extreme_fx.mid_idx <= current_bi.left_fx.mid_idx
                    or extreme_fx.mid_idx >= next_bi.left_fx.mid_idx
            ):
                continue

            try:
                replaced_current_bi = Bi.from_fenxing(
                    current_bi.left_fx,
                    extreme_fx,
                    all_klines,
                    prefix_merged,
                    prefix_gap,
                )
                replaced_next_bi = Bi.from_fenxing(
                    extreme_fx,
                    next_bi.right_fx,
                    all_klines,
                    prefix_merged,
                    prefix_gap,
                )
            except ValueError:
                continue

            if (
                    replaced_current_bi.end_idx > replaced_next_bi.start_idx
                    or not replaced_current_bi.is_finished
                    or not replaced_next_bi.is_finished
            ):
                continue

            bi_list[bi_index:bi_index + 2] = [replaced_current_bi, replaced_next_bi]
            return True

        return False

    def make_fake_last_bi():

        nonlocal bi_lm, bi_mr, all_klines, bi_list
        if len(bi_list) < 1:
            return
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

    def make_fake_last_bi_v2():

        nonlocal all_klines, bi_list
        if len(bi_list) < 1:
            return

        last_bi: BiBase = bi_list[-1]
        bi_is_up = last_bi.is_up()
        origin_kline_index = last_bi.right_fx.high_idx if bi_is_up else last_bi.right_fx.low_idx
        start_kline_idx = origin_kline_index
        end_kline_idx = len(all_klines) - 1

        if start_kline_idx < end_kline_idx:
            sl = slice(start_kline_idx, end_kline_idx + 1)
            fake_type = last_bi.bi_type
            kline_high_prices = high_prices[sl]
            kline_low_prices = low_prices[sl]
            local_max_idx = int(np.argmax(kline_high_prices))
            local_min_idx = int(np.argmin(kline_low_prices))

            if bi_is_up and local_max_idx > 0 and kline_high_prices[local_max_idx] > last_bi.high_price:
                start_kline_idx += local_max_idx
            elif not bi_is_up and local_min_idx > 0 and kline_low_prices[local_min_idx] < last_bi.low_price:
                start_kline_idx += local_min_idx

            last_bi_extend = False
            if start_kline_idx != origin_kline_index:
                last_bi_extend = True

            def _make_fake_last_bi_extend():
                nonlocal last_bi, start_kline_idx
                if isinstance(last_bi, FakeBiFront):
                    if not last_bi_extend:
                        return
                    extend_dest_time = all_klines[start_kline_idx].trade_datetime
                    new_fx = None
                    if last_bi.right_fx is not None:
                        for i in range(last_bi.right_fx.idx + 1, len(fenxing_list)):
                            fx = fenxing_list[i]
                            if fx.trade_datetime == extend_dest_time:
                                new_fx = fx
                                break
                    end_price = float(high_prices[start_kline_idx] if bi_is_up else low_prices[start_kline_idx])
                    new_bi = FakeBiFront(
                        end_idx=start_kline_idx,
                        start_price=last_bi.start_price,
                        end_price=end_price,
                        bi_type=last_bi.bi_type,
                        right_fx=new_fx,
                        all_klines=all_klines,
                    )
                    new_bi.start_idx = last_bi.start_idx
                    new_bi.start_time = last_bi.start_time
                    new_bi.end_time = extend_dest_time
                    new_bi.real_origin_kline_count = start_kline_idx - last_bi.start_idx + 1
                    (
                        new_bi.real_merged_kline_count,
                        new_bi.has_gap_count,
                    ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
                        new_bi.start_idx,
                        new_bi.end_idx,
                        all_klines,
                        prefix_merged,
                        prefix_gap,
                    )
                    if new_bi.is_kline_count_enough():
                        last_bi = new_bi
                    return
                extend_dest_time = all_klines[start_kline_idx].trade_datetime
                new_fx = None
                for i in range(last_bi.right_fx.idx + 1, len(fenxing_list)):
                    fx = fenxing_list[i]
                    if fx.trade_datetime == extend_dest_time:
                        new_fx = fx
                        break

                if last_bi_extend:
                    if new_fx is not None:
                        if last_bi.right_fx.fenxing_type != new_fx.fenxing_type:
                            new_bi = Bi.from_fenxing(last_bi.right_fx, new_fx, all_klines, prefix_merged, prefix_gap)
                        else:
                            new_bi = FakeBiLast.from_fenxing(
                                left_fx=last_bi.left_fx,
                                right_fx_mid_idx=start_kline_idx,
                                start_price=last_bi.start_price,
                                end_price=high_prices[start_kline_idx] if bi_is_up else low_prices[start_kline_idx],
                                bi_type=fake_type,
                                all_klines=all_klines,
                                prefix_merged=prefix_merged,
                                prefix_gap=prefix_gap,
                            )
                    else:
                        new_bi = FakeBiLast.from_fenxing(
                            left_fx=last_bi.left_fx, right_fx_mid_idx=start_kline_idx,
                            start_price=last_bi.start_price,
                            end_price=high_prices[start_kline_idx] if bi_is_up else low_prices[start_kline_idx],
                            bi_type=fake_type, all_klines=all_klines,
                            prefix_merged=prefix_merged, prefix_gap=prefix_gap)
                    if new_bi.is_finished:
                        last_bi = new_bi

            def _make_fake_last_bi():
                nonlocal last_bi, fake_last_bi
                if last_bi.right_fx is None:
                    return
                fake_type = BiDirectionType.DOWN if last_bi.is_up() else BiDirectionType.UP
                origin_kline_index = last_bi.right_fx.high_idx if last_bi.is_up() else last_bi.right_fx.low_idx
                start_kline_idx = origin_kline_index
                end_kline_idx = len(all_klines) - 1
                sl = slice(start_kline_idx, end_kline_idx + 1)

                if start_kline_idx >= end_kline_idx:
                    return

                kline_high_prices = high_prices[sl]
                kline_low_prices = low_prices[sl]
                local_max_idx = int(np.argmax(kline_high_prices))
                local_min_idx = int(np.argmin(kline_low_prices))

                if fake_type == BiDirectionType.UP and local_max_idx > 0:
                    start_kline_idx += local_max_idx
                elif fake_type == BiDirectionType.DOWN and local_min_idx > 0:
                    start_kline_idx += local_min_idx

                if start_kline_idx == origin_kline_index:
                    return

                new_bi = FakeBiLast.from_fenxing(
                    left_fx=last_bi.right_fx, right_fx_mid_idx=start_kline_idx,
                    start_price=last_bi.end_price,
                    end_price=high_prices[start_kline_idx] if fake_type == BiDirectionType.UP else low_prices[
                        start_kline_idx],
                    bi_type=fake_type, all_klines=all_klines,
                    prefix_merged=prefix_merged, prefix_gap=prefix_gap)

                if new_bi.is_finished:
                    fake_last_bi = new_bi

            _make_fake_last_bi_extend()

            if last_bi.is_finished:
                bi_list[-1] = last_bi

            if isinstance(last_bi, FakeBiLast):
                return

            fake_last_bi: Optional[FakeBiLast] = None

            _make_fake_last_bi()

            if fake_last_bi is not None and fake_last_bi.is_finished:
                bi_list.append(fake_last_bi)

    make_fake_front_bi()

    # 最后一笔lm
    if bi_lm.is_finished:
        bi_finish_deque.append(bi_lm)
        if bi_mr is not None and bi_mr.is_finished:
            bi_finish_deque.append(bi_mr)
            bi_lm = bi_mr
            bi_mr = None

    def prepend_initial_extreme_bi():
        """首个正式笔左侧有同向更极值时，沿原方向把起点回延到该极值。"""
        if not bi_list or not isinstance(bi_list[0], Bi):
            return False

        first_bi = bi_list[0]
        prefix_end_idx = first_bi.start_idx - 1
        if prefix_end_idx < 0:
            return False

        if first_bi.is_up():
            extreme_idx = int(np.argmin(low_prices[:prefix_end_idx + 1]))
            extreme_price = float(low_prices[extreme_idx])
            if extreme_idx >= first_bi.start_idx or extreme_price >= first_bi.start_price:
                return False
            covered_high = float(np.max(high_prices[extreme_idx:first_bi.end_idx + 1]))
            if covered_high > float(first_bi.end_price) + 1e-8:
                return False
        else:
            extreme_idx = int(np.argmax(high_prices[:prefix_end_idx + 1]))
            extreme_price = float(high_prices[extreme_idx])
            if extreme_idx >= first_bi.start_idx or extreme_price <= first_bi.start_price:
                return False
            covered_low = float(np.min(low_prices[extreme_idx:first_bi.end_idx + 1]))
            if covered_low < float(first_bi.end_price) - 1e-8:
                return False

        extended_bi = FakeBiFront(
            end_idx=first_bi.end_idx,
            start_price=extreme_price,
            end_price=first_bi.end_price,
            bi_type=first_bi.bi_type,
            right_fx=first_bi.right_fx,
            all_klines=all_klines,
        )
        extended_bi.start_idx = extreme_idx
        extended_bi.start_time = all_klines[extreme_idx].trade_datetime
        extended_bi.end_time = first_bi.end_time
        extended_bi.real_origin_kline_count = first_bi.end_idx - extreme_idx + 1
        (
            extended_bi.real_merged_kline_count,
            extended_bi.has_gap_count,
        ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
            extreme_idx,
            first_bi.end_idx,
            all_klines,
            prefix_merged,
            prefix_gap,
        )
        if not extended_bi.is_kline_count_enough():
            return False
        bi_list[0] = extended_bi
        return True

    bi_list = list(bi_finish_deque)
    prepend_initial_extreme_bi()
    split_fake_front_bi_by_internal_extreme()
    split_fake_front_bi_by_internal_extreme_permissively()
    split_initial_fake_front_by_internal_extreme()
    while split_bi_by_internal_extreme():
        pass


    if not bi_lm.is_finished:
        for i in range(len(bi_list)):
            bi_list[i].idx = i
        return bi_list


    # make_fake_last_bi()
    make_fake_last_bi_v2()

    def supplement_last_fake_bi_with_reverse_bi():
        nonlocal bi_list
        if not bi_list or not isinstance(bi_list[-1], FakeBiLast):
            return

        tail_bi = bi_list[-1]
        if bi_list[:-1]:
            return

        current_fx = tail_bi.left_fx
        if current_fx is None or current_fx.idx is None or current_fx.idx < 2:
            return

        supplemented_bis = []

        def candidate_extremes_are_valid(candidate_bi) -> bool:
            candidate_low = min(low_prices[candidate_bi.start_idx:candidate_bi.end_idx + 1])
            candidate_high = max(high_prices[candidate_bi.start_idx:candidate_bi.end_idx + 1])
            if candidate_bi.is_up():
                return candidate_low >= candidate_bi.start_price and candidate_high <= candidate_bi.end_price
            return candidate_high <= candidate_bi.start_price and candidate_low >= candidate_bi.end_price

        def find_complete_reverse_bi():
            for candidate_idx in range(current_fx.idx - 1, -1, -1):
                candidate_fx = fenxing_list[candidate_idx]
                if candidate_fx.fenxing_type == current_fx.fenxing_type:
                    continue

                try:
                    candidate_bi = Bi.from_fenxing(
                        candidate_fx,
                        current_fx,
                        all_klines,
                        prefix_merged,
                        prefix_gap,
                    )
                except ValueError:
                    continue

                if candidate_bi.is_kline_count_enough() and candidate_extremes_are_valid(candidate_bi):
                    return candidate_bi

                extended_bi = make_extended_front_bi(candidate_bi)
                if extended_bi is not None:
                    return extended_bi

            return None

        def find_reverse_bi_chain():
            reverse_bi = find_complete_reverse_bi()
            if reverse_bi is None:
                return None

            previous_fx = reverse_bi.left_fx
            for candidate_idx in range(previous_fx.idx - 1, -1, -1):
                candidate_fx = fenxing_list[candidate_idx]
                if candidate_fx.fenxing_type == previous_fx.fenxing_type:
                    continue
                previous_bi_is_up = previous_fx.is_top()
                if previous_bi_is_up == reverse_bi.is_up():
                    continue

                try:
                    previous_bi = Bi.from_fenxing(
                        candidate_fx,
                        previous_fx,
                        all_klines,
                        prefix_merged,
                        prefix_gap,
                    )
                except ValueError:
                    continue

                front_bi = make_extended_front_bi(previous_bi)
                if front_bi is not None:
                    return [front_bi, reverse_bi]

            return [reverse_bi]

        def make_front_reverse_bi():
            if current_fx.is_top():
                reverse_bi_type = BiDirectionType.DOWN
                end_idx = current_fx.high_idx
                end_price = current_fx.high_price
                start_idx = int(np.argmax(high_prices[:end_idx]))
                start_price = high_prices[start_idx]
            else:
                reverse_bi_type = BiDirectionType.UP
                end_idx = current_fx.low_idx
                end_price = current_fx.low_price
                start_idx = int(np.argmin(low_prices[:end_idx]))
                start_price = low_prices[start_idx]

            if start_idx >= end_idx:
                return None

            fake_front_bi = FakeBiFront(
                end_idx=end_idx,
                start_price=start_price,
                end_price=end_price,
                bi_type=reverse_bi_type,
                left_fx=current_fx,
                right_fx=current_fx,
                all_klines=all_klines,
            )
            fake_front_bi.start_idx = start_idx
            fake_front_bi.start_time = all_klines[start_idx].trade_datetime
            fake_front_bi.end_time = current_fx.trade_datetime
            fake_front_bi.real_origin_kline_count = end_idx - start_idx + 1
            (
                fake_front_bi.real_merged_kline_count,
                fake_front_bi.has_gap_count,
            ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
                start_idx,
                end_idx,
                all_klines,
                prefix_merged,
                prefix_gap,
            )

            if not fake_front_bi.is_kline_count_enough():
                return None
            if not candidate_extremes_are_valid(fake_front_bi):
                return None
            return fake_front_bi

        def make_extended_front_bi(candidate_bi):
            if candidate_bi.is_down():
                start_idx = int(np.argmax(high_prices[:candidate_bi.start_idx]))
                start_price = high_prices[start_idx]
                if start_price < candidate_bi.start_price:
                    return None
            else:
                start_idx = int(np.argmin(low_prices[:candidate_bi.start_idx]))
                start_price = low_prices[start_idx]
                if start_price > candidate_bi.start_price:
                    return None

            extended_bi = FakeBiFront(
                end_idx=candidate_bi.end_idx,
                start_price=start_price,
                end_price=candidate_bi.end_price,
                bi_type=candidate_bi.bi_type,
                left_fx=candidate_bi.left_fx,
                right_fx=candidate_bi.right_fx,
                all_klines=all_klines,
            )
            extended_bi.start_idx = start_idx
            extended_bi.start_time = all_klines[start_idx].trade_datetime
            extended_bi.end_time = candidate_bi.end_time
            extended_bi.real_origin_kline_count = (
                candidate_bi.real_origin_kline_count + candidate_bi.start_idx - start_idx
            )
            count_end_idx = candidate_bi.left_fx.end_idx_list[0]
            extended_bi.real_merged_kline_count = (
                candidate_bi.real_merged_kline_count
                + prefix_merged[count_end_idx + 1]
                - prefix_merged[candidate_bi.start_idx]
            )
            extended_bi.has_gap_count = (
                candidate_bi.has_gap_count
                + prefix_gap[count_end_idx + 1]
                - prefix_gap[candidate_bi.start_idx + 1]
            )

            if not extended_bi.is_kline_count_enough():
                return None
            if not candidate_extremes_are_valid(extended_bi):
                return None
            return extended_bi

        while current_fx.idx > 0:
            reverse_bis = find_reverse_bi_chain()

            if reverse_bis is None:
                reverse_bi = make_front_reverse_bi()
                reverse_bis = [reverse_bi] if reverse_bi is not None else None

            if reverse_bis is None:
                break

            if len(reverse_bis) > 1:
                supplemented_bis = reverse_bis
            else:
                supplemented_bis = [*reverse_bis, *supplemented_bis]
            if isinstance(reverse_bis[0], FakeBiFront):
                break
            current_fx = reverse_bis[0].left_fx

        if supplemented_bis:
            bi_list = [*supplemented_bis, tail_bi]

        def merge_front_and_tail_into_one_bi():
            nonlocal bi_list
            if len(bi_list) < 3:
                return

            first_bi = bi_list[0]
            last_bi = bi_list[-1]
            if not isinstance(first_bi, FakeBiFront) or not isinstance(last_bi, FakeBiLast):
                return
            if first_bi.bi_type != last_bi.bi_type:
                return

            start_idx = first_bi.start_idx
            end_idx = last_bi.end_idx
            if first_bi.is_down():
                start_price = max(high_prices[:end_idx + 1])
                end_price = min(low_prices[:end_idx + 1])
                if start_idx != int(np.argmax(high_prices[:end_idx + 1])):
                    return
                if end_idx != int(np.argmin(low_prices[start_idx:end_idx + 1])):
                    return
            else:
                start_price = min(low_prices[:end_idx + 1])
                end_price = max(high_prices[:end_idx + 1])
                if start_idx != int(np.argmin(low_prices[:end_idx + 1])):
                    return
                if end_idx != int(np.argmax(high_prices[start_idx:end_idx + 1])):
                    return

            merged_bi = FakeBiFront(
                end_idx=end_idx,
                start_price=start_price,
                end_price=end_price,
                bi_type=first_bi.bi_type,
                left_fx=first_bi.left_fx,
                right_fx=last_bi.left_fx,
                all_klines=all_klines,
            )
            merged_bi.start_idx = start_idx
            merged_bi.start_time = all_klines[start_idx].trade_datetime
            merged_bi.end_time = all_klines[end_idx].trade_datetime
            merged_bi.real_origin_kline_count = end_idx - start_idx + 1
            (
                merged_bi.real_merged_kline_count,
                merged_bi.has_gap_count,
            ) = BiBase.calculate_bi_real_merged_kline_count_and_gap_count(
                start_idx,
                end_idx,
                all_klines,
                prefix_merged,
                prefix_gap,
            )

            if merged_bi.is_kline_count_enough():
                bi_list = [merged_bi]

        merge_front_and_tail_into_one_bi()

    supplement_last_fake_bi_with_reverse_bi()

    ####################### 检查
    # 检查笔的极值在两端
    for bi in bi_list:
        if type(bi) == FakeBiFront or type(bi) == FakeBiLast:
            continue
        init_highest_price = max(bi.left_fx.high_price, bi.right_fx.high_price)
        init_lowest_price = min(bi.left_fx.low_price, bi.right_fx.low_price)
        start_idx = bi.left_fx.right_idx
        end_idx = bi.end_idx
        sl = slice(bi.left_fx.high_idx if bi.is_up() else bi.left_fx.low_idx, end_idx + 1)
        # highest_price, lowest_price, highest_idx, lowest_idx = BiBase.get_highest_lowest_price(init_highest_price,
        #                                                                                        init_lowest_price,
        #                                                                                        start_idx,
        #                                                                                        end_idx, all_klines,
        #                                                                                        high_prices, low_prices)
        temp_high_prices = high_prices[sl]
        temp_low_prices = low_prices[sl]
        _highest_idx = int(np.argmax(temp_high_prices))
        _lowest_idx = int(np.argmin(temp_low_prices))
        highest_price = temp_high_prices[_highest_idx]
        lowest_price = temp_low_prices[_lowest_idx]


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
