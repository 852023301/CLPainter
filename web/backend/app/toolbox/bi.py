from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
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
        if not self.has_different_Fenxing():
            return False

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
            raise ValueError("起始索引不能大于等于结束索引")
        bi_real_merged_kline_count = 1
        bi_has_gap_count = 0
        last_idx = start_kline_idx
        last_kline = all_klines[start_kline_idx]

        while (last_idx := last_idx + last_kline.merged_length) < end_kline_idx:
            last_kline = all_klines[last_idx]
            bi_real_merged_kline_count += 1
            # 判断是否有缺口
            if last_kline.has_gap:
                bi_has_gap_count += 1

        bi_real_merged_kline_count += 1
        # 判断是否有缺口
        last_kline = all_klines[last_idx]
        if last_kline.has_gap:
            bi_has_gap_count += 1

        return bi_real_merged_kline_count, bi_has_gap_count

    @staticmethod
    def get_highest_lowest_price(start_kline_idx: int, end_kline_idx: int,
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
            raise ValueError("起始索引不能大于等于结束索引")
        last_idx = start_kline_idx
        last_kline = all_klines[start_kline_idx]

        highest_price = last_kline.high_price
        lowest_price = last_kline.low_price

        while (last_idx := last_idx + last_kline.merged_length) < end_kline_idx:
            last_kline = all_klines[last_idx]

            # 收集笔中的最高价和最低价
            if last_kline.merged_high > highest_price:
                highest_price = last_kline.merged_high
            if last_kline.merged_low < lowest_price:
                lowest_price = last_kline.merged_low

        # 判断是否有缺口
        last_kline = all_klines[last_idx]

        # 收集笔中的最高价和最低价
        if last_kline.merged_high > highest_price:
            highest_price = last_kline.merged_high
        if last_kline.merged_low < lowest_price:
            lowest_price = last_kline.merged_low

        return highest_price, lowest_price


def identify_bi_from_fenxing(fenxing_list: List[FenXing], all_klines: List[MergedKLine] = None) -> List[Bi]:
    """
    根据分型列表划分缠论笔

    Args:
        fenxing_list: 分型对象列表
        all_klines: 合并后的K线列表（可选，用于获取时间信息）

    Returns:
        List[Bi]: Bi 对象列表
    """

    # 初始化
    bi_list = []
    L_fractal = None
    M_fractal = None
    R_fractal = None
    N_fractal = None
    lst = [i.is_top_bottom for i in fenxing_list]
    # # print(lst)
    #
    # for i in range(len(fenxing_list) - 1):
    #     if not (lst[i] + lst[i + 1] == 0):
    #         last = fenxing_list[i-1].is_top_bottom
    #         now = fenxing_list[i].is_top_bottom
    #         nextd = fenxing_list[i+1].is_top_bottom
    #         print(f"{fenxing_list[i].trade_date=},{last=},{now=},{nextd=}")
    assert all(lst[i] + lst[i + 1] == 0 for i in range(len(lst) - 1)), "分型不满足交替出现"
    for i, fenxing in enumerate(fenxing_list):
        if L_fractal is None:
            L_fractal = (i, fenxing)
            continue

        L_idx, L_fx = L_fractal

        if L_fractal is not None and M_fractal is None and L_fx.is_top_bottom != fenxing.is_top_bottom:
            M_fractal = (i, fenxing)
            continue

        M_idx, M_fx = M_fractal
        if L_fractal is not None and M_fractal is not None and R_fractal is None:
            if M_fx.is_top_bottom == fenxing.is_top_bottom:
                M_fractal = (i, fenxing)
            else:
                R_fractal = (i, fenxing)

            continue

        R_idx, R_fx = R_fractal

        """
        ############
        开始过滤中继分型
        ############
        """

        """
        若队列为空，LM或MR任一完成后LM Push到队列，然后重置LM和MR
        """
        if not bi_list:
            # 若LM或MR任一完成
            if (first_bi := Bi.from_fenxing(L_fx, M_fx, all_klines)).is_finished() or Bi.from_fenxing(M_fx,
                                                                                                      R_fx,
                                                                                                      all_klines).is_finished():
                bi_list.append(first_bi)
                L_fractal = M_fractal
                M_fractal = R_fractal
                R_fractal = None
                continue

        """
        若队列非空 或 LM或MR无一完成
        """

        # # 若LM未完成
        # if bi_list and  (not (first_bi := Bi.from_fenxing(L_fx, M_fx, all_klines)).is_finished()):

        # 规则：同向分型取极值（如果两个都是顶，取更高的那个；两个都是底，取更低的那个）
        if L_fx.is_top_bottom == fenxing.is_top_bottom:
            if fenxing.is_top_bottom == 1 and fenxing.high_price > L_fx.high_price:
                L_fractal = (i, fenxing)
            elif fenxing.is_top_bottom == -1 and fenxing.low_price < L_fx.low_price:
                L_fractal = (i, fenxing)
            continue

        # 规则：顶底之间至少要有1根独立K线 (索引差 >= 4，因为中间要隔一根)
        # 缠论严格定义是顶底分型元素不共用，且中间至少有一根K线。
        # 在合并K线序列中，索引差至少为 3 (例如: 0是底, 1是中间, 2是顶 -> 差2不行，至少要差3或4视具体实现)
        # 通常要求：顶分型最高K线索引 - 底分型最低K线索引 >= 4
        if abs(fenxing.end_idx - L_fx.end_idx) >= 4:
            # 创建 Bi 对象
            bi = Bi.from_fenxing(L_fx, fenxing, all_klines)

            if bi.merged_kline_count < 4 or bi.origin_kline_count < 5:
                continue

            bi_list.append(bi)
            L_fractal = (i, fenxing)
    # print(bi_list)

    # TODO:笔连续性检查
    # for i in range(len(bi_list) - 1):
    #     if bi_list[i].right_fx.trade_date != bi_list[i + 1].left_fx.trade_date:
    #         print(bi_list[i])

    assert np.all(np.diff([bi.bi_type == BiDirectionType.UP for bi in bi_list]) != 0), "不满足笔上下交替的要求"

    # TODO：极值检查
    # for bi in bi_list:
    #     highest_price, lowest_price = bi.get_highest_lowest_price(bi.start_idx, bi.end_idx, all_klines)
    #     if highest_price > max(bi.left_fx.high_price, bi.right_fx.high_price):
    #         raise ValueError(f"顶分型最高价不是一笔中的最高价: {highest_price=},{bi.left_fx.trade_date=}")
    #     if lowest_price < min(bi.left_fx.low_price, bi.right_fx.low_price):
    #         raise ValueError(f"底分型最低价不是一笔中的最低价: {lowest_price=},{bi.left_fx.trade_date=}")

    return bi_list
