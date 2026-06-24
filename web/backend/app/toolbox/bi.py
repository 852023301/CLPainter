from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
from collections import deque
import numpy as np

from .fenxing import FenXing
from .merged_kline import MergedKLine


class BiDirectionType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 上升笔：底→顶
    DOWN = 'down'  # 下降笔：顶→底


@dataclass
class Bi:
    """笔数据结构（优化版）"""
    start_idx: int = field(init=False)  # 笔起始位置索引（分型所在 K 线索引）
    end_idx: int = field(init=False)  # 笔结束位置索引（分型所在 K 线索引）
    start_time: str = field(init=False)  # 起始时间
    end_time: str = field(init=False)  # 结束时间
    start_price: float = field(init=False)  # 起始价格（顶/底分型的极值）
    end_price: float = field(init=False)  # 结束价格（顶/底分型的极值）
    bi_type: BiDirectionType = field(init=False)  # 笔的方向

    # 左右分型
    left_fx: FenXing
    right_fx: FenXing

    real_origin_kline_count: Optional[int] = field(init=False)  # 笔包含的真实原始 K 线数量（一端分型最高点到另一端最低点之间）
    real_merged_kline_count: Optional[int] = None  # 笔包含的真实合并 K 线数量（一端分型最高点到另一端最低点之间）

    # 包含缺口数量
    has_gap_count: Optional[int] = None

    def __post_init__(self):
        self.bi_type = BiDirectionType.UP if self.right_fx.is_top_bottom == 1 else BiDirectionType.DOWN

        # 确定起始和结束索引
        self.start_idx = self.left_fx.low_idx if self.bi_type == BiDirectionType.UP else self.left_fx.high_idx
        self.end_idx = self.right_fx.high_idx if self.bi_type == BiDirectionType.UP else self.right_fx.low_idx
        if self.end_idx <= self.start_idx:
            raise ValueError(f"结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_time = self.left_fx.trade_date
        self.end_time = self.right_fx.trade_date
        self.start_price = self.left_fx.low_price if self.bi_type == BiDirectionType.UP else self.left_fx.high_price
        self.end_price = self.right_fx.high_price if self.bi_type == BiDirectionType.UP else self.right_fx.low_price
        self.real_origin_kline_count = self.end_idx - self.start_idx + 1

    @property
    def is_up(self) -> bool:
        return self.bi_type == BiDirectionType.UP

    @property
    def is_down(self) -> bool:
        return self.bi_type == BiDirectionType.DOWN

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

    @classmethod
    def from_fenxing(self, left_fx: FenXing, right_fx: FenXing, all_klines: List[MergedKLine]):
        """
        从两个分型对象中创建一个笔对象

        Args:
            left_fx: 左侧分型对象
            right_fx: 右侧分型对象
            all_klines: 合并后的K线列表

        Returns:
            Bi: 笔对象
        """
        if left_fx.is_top_bottom == right_fx.is_top_bottom:
            raise ValueError(f"分型方向一致: {left_fx.is_top_bottom=}")

        bi_real_merged_kline_count, bi_has_gap_count = Bi.calculate_bi_real_merged_kline_count_and_gap_count(
            left_fx.mid_idx, right_fx.mid_idx,
            all_klines)

        bi = Bi(
            left_fx=left_fx,
            right_fx=right_fx,
        )

        bi.real_merged_kline_count = bi_real_merged_kline_count
        bi.has_gap_count = bi_has_gap_count

        return bi

    def is_finished(self) -> bool:
        """
        判断笔是否可以完成

        Returns:
            bool: 笔是否可以完成
        """
        # if not self.has_different_Fenxing():
        #     return False

        if not self.is_leaving_interval():
            return False

        if not self.is_kline_count_enough():
            return False

        return True

    def has_different_Fenxing(self) -> bool:
        """
        判断笔是否包含不同的分型

        Returns:
            bool: 笔是否包含不同的分型
        """
        if self.left_fx.is_top_bottom == self.right_fx.is_top_bottom:
            raise ValueError(f"分型方向一致: {self.left_fx.is_top_bottom=}")
        return True

    def is_leaving_interval(self) -> bool:
        """
        判断底分型最低点低于顶分型中间K线的最低点+顶分型最高点高于底分型中间K线的最高点

        Returns:
            bool: 笔是否满足底分型和顶分型拉开距离
        """
        if self.bi_type == BiDirectionType.UP:
            return self.left_fx.low_price < self.right_fx.low_price and self.left_fx.high_price < self.right_fx.high_price
        else:
            return self.left_fx.high_price > self.right_fx.high_price and self.left_fx.low_price > self.right_fx.low_price

    def is_kline_count_enough(self) -> bool:
        """
        一笔中有效K线至少四根，并且顶分型最高点到底分型最低点最低点之间共有五根原始K线，跳空一次算一根


        Returns:
            bool: 笔是否包含指定数量的K线

        """
        return self.origin_kline_count >= 5 and self.merged_kline_count >= 4

    @staticmethod
    def calculate_bi_real_merged_kline_count_and_gap_count(start_kline_idx: int, end_kline_idx: int,
                                                           all_klines: List[MergedKLine]) -> Tuple[
        int, int]:
        """
            计算一笔中的真实合并K线数量和缺口数量

        """
        if start_kline_idx >= end_kline_idx:
            raise ValueError(f"起始索引不能大于等于结束索引:{all_klines[start_kline_idx]=},{all_klines[end_kline_idx]=}")
        bi_real_merged_kline_count = 0
        bi_has_gap_count = 0
        last_idx = start_kline_idx

        while last_idx <= end_kline_idx:
            last_kline = all_klines[last_idx]
            if last_kline.merged_length == 1:
                bi_real_merged_kline_count += 1
                # 检测是否有缺口(排除第一根)
                if last_idx!=start_kline_idx and last_kline.has_gap:
                    bi_has_gap_count += 1

            last_idx += 1


        return bi_real_merged_kline_count, bi_has_gap_count

    @staticmethod
    def get_highest_lowest_price(highest_price, lowest_price,start_kline_idx: int, end_kline_idx: int,
                                 all_klines: List[MergedKLine]) -> Tuple[float, float]:
        """
        获取笔中的最高价和最低价

        Args:
            left_fx: 左侧分型对象
            right_fx: 右侧分型对象

        Returns:
            Tuple[float, float]: 笔中的最高价和最低价
        """
        if start_kline_idx >= end_kline_idx:
            raise ValueError(f"起始索引不能大于等于结束索引:{all_klines[start_kline_idx]=},{all_klines[end_kline_idx]=}")
        last_idx = start_kline_idx

        while last_idx <= end_kline_idx:
            last_kline = all_klines[last_idx]

            # 收集笔中的最高价和最低价
            if last_kline.high_price > highest_price:
                highest_price = last_kline.merged_high
                # if "2015-11-09" <= last_kline.trade_date <= "2015-11-30":
                #     print(last_kline)
                #     print("%"*50)
            if last_kline.low_price < lowest_price:
                lowest_price = last_kline.merged_low
                # if "2023-02-06" <= last_kline.trade_date <= "2023-03-07":
                #     print(last_kline)
                #     print("%"*50)
            last_idx += 1


        # last_kline = all_klines[last_idx]
        # if "2010-03-22" <= last_kline.trade_date <= "2010-04-22":
        #     print(last_kline)
        #     print("%" * 50)
        #
        # # 收集笔中的最高价和最低价
        # if last_kline.high_price > highest_price:
        #     highest_price = last_kline.high_price
        # if last_kline.low_price < lowest_price:
        #     lowest_price = last_kline.low_price

        return highest_price, lowest_price

    def print_klines_info(self, all_klines):
        for i in range(self.start_idx, self.end_idx+1):
            print(all_klines[i])

def identify_bi_from_fenxing(fenxing_list: List[FenXing], all_klines: List[MergedKLine]) -> List[Bi]:
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
    trade_s = "2025-10-17"
    trade_e = "2025-11-24"
    log_switch = True

    def find_first_bi_in_finish_deque():
        """适合在lm未完成但mr已完成的情况下，在已完成的队列中寻找笔"""
        nonlocal bi_lm
        while len(bi_finish_deque) > 0:
            last_bi_finish = bi_finish_deque.popleft()
            if log_switch and trade_e >= last_bi_finish.left_fx.trade_date >= trade_s:
                print("#" * 50, "lm弹出")
                print(last_bi_finish)
            if (last_bi_finish.bi_type == bi_lm.bi_type) and (
                (last_bi_finish.bi_type == BiDirectionType.UP and last_bi_finish.start_price <= bi_lm.start_price) or (
                last_bi_finish.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price >= bi_lm.start_price)):
                bi_lm = Bi.from_fenxing(last_bi_finish.left_fx, bi_lm.right_fx, all_klines)
                if log_switch and trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                    print("#" * 50, "lm被替换")
                    print(f"bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                return True
        return False

    def find_second_bi_in_finish_deque():
        """适合在mr未完成但xy已经能够包含lm的情况， 在已完成的队列中寻找笔"""
        nonlocal bi_lm
        nonlocal bi_mr
        nonlocal bi_xy
        while len(bi_finish_deque) > 0:
            last_bi_finish = bi_finish_deque.popleft()
            if log_switch and  trade_e >= last_bi_finish.left_fx.trade_date >= trade_s:
                print("#" * 50, "mr弹出")
                print(last_bi_finish)
            if (last_bi_finish.bi_type == bi_mr.bi_type):
                if (last_bi_finish.bi_type == BiDirectionType.UP and last_bi_finish.start_price <= bi_mr.start_price) or (
                last_bi_finish.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price >= bi_mr.start_price):
                    bi_mr = Bi.from_fenxing(last_bi_finish.left_fx, bi_mr.right_fx, all_klines)
                    return False
            else:
                if bi_mr.is_finished():
                    if (bi_mr.bi_type == BiDirectionType.UP and last_bi_finish.start_price >= bi_lm.start_price) or (bi_mr.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price <= bi_lm.start_price):
                        bi_lm = Bi.from_fenxing(last_bi_finish.left_fx, bi_lm.right_fx, all_klines)
                        if len(bi_finish_deque) > 0:
                            bi_mr = bi_lm
                            bi_lm = bi_finish_deque.popleft()

                        elif len(fenxing_deque) > 0:
                            x_fx, y_fx = fenxing_deque.popleft()
                            bi_mr = Bi.from_fenxing(x_fx, y_fx, all_klines)
                        else:
                            bi_mr = None
                        return True


                else:
                    if (bi_mr.bi_type == BiDirectionType.UP and last_bi_finish.start_price >= bi_mr.end_price) or (bi_mr.bi_type == BiDirectionType.DOWN and last_bi_finish.start_price <= bi_mr.end_price):
                        bi_mr = Bi.from_fenxing(last_bi_finish.left_fx, bi_xy.right_fx, all_klines)
                        if len(bi_finish_deque) > 0:
                            bi_lm = bi_finish_deque.popleft()

                        elif len(fenxing_deque) > 0:
                            bi_lm = bi_mr
                            x_fx, y_fx = fenxing_deque.popleft()
                            bi_mr = Bi.from_fenxing(x_fx, y_fx, all_klines)
                        else:
                            bi_mr = None
                        return True


            if log_switch and  ((trade_e >= bi_mr.left_fx.trade_date >= trade_s) or (trade_e >= bi_mr.right_fx.trade_date >= trade_s)):
                print("#" * 50, "mr被替换")
                print(f"bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")

        return False

    """调整deque中的前两笔，使其满足：在mr完成之前，尽可能延长lm"""

    if len(fenxing_deque) < 2:
        return bi_list

    l_fx, m_fx = fenxing_deque.popleft()
    m_fx, r_fx = fenxing_deque.popleft()

    bi_lm = Bi.from_fenxing(l_fx, m_fx, all_klines)
    bi_mr = Bi.from_fenxing(m_fx, r_fx, all_klines)

    while len(fenxing_deque) > 0:
        if bi_lm is None or bi_mr is None:
            break
        is_bi_lm_finish = bi_lm.is_finished()
        is_bi_mr_finish = bi_mr.is_finished()
        if bi_mr.left_fx.trade_date == '2025-10-27' and bi_mr.right_fx.trade_date == '2025-11-03':
            print(bi_mr)
            bi_mr.print_klines_info(all_klines)

        if is_bi_lm_finish and is_bi_mr_finish:
            if log_switch and  trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                print("#" * 50, "加入")
                print(f"bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                print(f"bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")
            bi_finish_deque.appendleft(bi_lm)
            bi_lm = bi_mr
            m_fx, r_fx = fenxing_deque.popleft()
            bi_mr = Bi.from_fenxing(m_fx, r_fx, all_klines)
            if log_switch and  trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                print(f"new bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                print(f"new bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")
            continue

        if log_switch and trade_e >= bi_lm.left_fx.trade_date >= trade_s:
            print("lm和mr任一未完成")
            print(f"bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
            print(f"bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")

        if not is_bi_lm_finish and is_bi_mr_finish:
            if not find_first_bi_in_finish_deque():
                bi_lm = bi_mr
                m_fx, r_fx = fenxing_deque.popleft()
                bi_mr = Bi.from_fenxing(m_fx, r_fx, all_klines)
            continue

        x_fx, y_fx = fenxing_deque.popleft()

        bi_xy = Bi.from_fenxing(x_fx, y_fx, all_klines)

        if bi_xy.bi_type == bi_lm.bi_type:
            if log_switch and  trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                print("@" * 50, "和lm同趋势,变更前")
                print(f"bi_xy:{bi_xy.left_fx.trade_date}~{bi_xy.right_fx.trade_date}")
                print(f"bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                print(f"bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")
            bi_xy = Bi.from_fenxing(bi_mr.right_fx, bi_xy.right_fx, all_klines)
            if (bi_xy.bi_type == BiDirectionType.UP and bi_xy.end_price > bi_lm.end_price) or (
                bi_xy.bi_type == BiDirectionType.DOWN and bi_xy.end_price < bi_lm.end_price):
                if (bi_xy.bi_type == BiDirectionType.UP and bi_xy.start_price < bi_lm.start_price) or (
                    bi_xy.bi_type == BiDirectionType.DOWN and bi_xy.start_price > bi_lm.start_price):


                    if not find_second_bi_in_finish_deque():
                        bi_lm = bi_mr
                        bi_mr = Bi.from_fenxing(bi_mr.right_fx, bi_xy.right_fx, all_klines)
                    continue



                bi_lm = Bi.from_fenxing(bi_lm.left_fx, bi_xy.right_fx, all_klines)

                if len(fenxing_deque) == 0:
                    break
                x_fx, y_fx = fenxing_deque.popleft()
                bi_mr = Bi.from_fenxing(x_fx, y_fx, all_klines)
            if log_switch and  trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                print("@" * 50, "和lm同趋势，变更后")
                print(f"new bi_xy:{bi_xy.left_fx.trade_date}~{bi_xy.right_fx.trade_date}")
                print(f"new bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                print(f"new bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")


        elif bi_xy.bi_type == bi_mr.bi_type:
            if (bi_xy.bi_type == BiDirectionType.UP and bi_xy.end_price > bi_mr.end_price) or (
                bi_xy.bi_type == BiDirectionType.DOWN and bi_xy.end_price < bi_mr.end_price):
                bi_mr = Bi.from_fenxing(bi_mr.left_fx, bi_xy.right_fx, all_klines)
            if log_switch and  trade_e >= bi_lm.left_fx.trade_date >= trade_s:
                print("$" * 50, "和mr同趋势")
                print(f"bi_xy:{bi_xy.left_fx.trade_date}~{bi_xy.right_fx.trade_date}")
                print(f"bi_lm:{bi_lm.left_fx.trade_date}~{bi_lm.right_fx.trade_date}")
                print(f"bi_mr:{bi_mr.left_fx.trade_date}~{bi_mr.right_fx.trade_date}")
        else:
            raise ValueError(f"笔类型不符合预期:{bi_xy.bi_type}")


    if bi_lm.is_finished():
        bi_finish_deque.appendleft(bi_lm)
        bi_lm = None
        if bi_mr.is_finished():
            bi_finish_deque.appendleft(bi_mr)
            bi_mr = None
    bi_list = list(bi_finish_deque)[::-1]

    # 检查笔连续性
    for i in range(len(bi_list) - 1):
        if bi_list[i].right_fx.trade_date != bi_list[i + 1].left_fx.trade_date:
            print(bi_list[i].right_fx.trade_date,bi_list[i + 1].left_fx.trade_date)
            # raise RuntimeError("笔连续性检查失败")

    # 检查笔上下交替
    assert np.all(np.diff([bi.bi_type == BiDirectionType.UP for bi in bi_list]) != 0), "不满足笔上下交替的要求"

    # 检查笔的极值在两端
    for bi in bi_list:
        # print(bi)
        # if log_switch and trade_e >= bi.left_fx.trade_date >= trade_s:
        #     print(bi)
        #     print("左分型的信息：")
        #     print(bi.left_fx)
        #     print("左分型内部所有K线信息：")
        #     bi.left_fx.print_klines_info(all_klines = all_klines)



        init_highest_price = max(bi.left_fx.high_price, bi.right_fx.high_price)
        init_lowest_price = min(bi.left_fx.low_price, bi.right_fx.low_price)
        start_idx = bi.left_fx.right_idx
        end_idx = bi.end_idx
        highest_price, lowest_price = bi.get_highest_lowest_price(init_highest_price, init_lowest_price, start_idx, end_idx, all_klines)
        if highest_price > max(bi.left_fx.high_price, bi.right_fx.high_price):
            text = f"顶分型最高价不是一笔中的最高价: {highest_price=}>[{min(bi.left_fx.low_price,bi.right_fx.low_price)},{max(bi.left_fx.high_price,bi.right_fx.high_price)}],{bi.left_fx.trade_date=}~{bi.right_fx.trade_date=}"
            print(text)
            print(bi)
            raise RuntimeError(text)
        if lowest_price < min(bi.left_fx.low_price, bi.right_fx.low_price):
            text = f"底分型最低价不是一笔中的最低价: {lowest_price=}<[{min(bi.left_fx.low_price,bi.right_fx.low_price)},{max(bi.left_fx.high_price,bi.right_fx.high_price)}],{bi.left_fx.trade_date=}~{bi.right_fx.trade_date=}"
            print(text)
            print(bi)
            raise RuntimeError(text)
    print(f"共{len(bi_list)}笔")
    return bi_list
