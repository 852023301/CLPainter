from dataclasses import dataclass
from enum import Enum
from typing import List,Tuple

from .fenxing import FenXing
from .merged_kline import MergedKLine


class BiDirectionType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 上升笔：底→顶
    DOWN = 'down'  # 下降笔：顶→底


@dataclass
class Bi:
    """笔数据结构（优化版）"""
    start_idx: int  # 笔起始位置索引（分型所在 K 线索引）
    end_idx: int  # 笔结束位置索引（分型所在 K 线索引）
    start_time: str  # 起始时间
    end_time: str  # 结束时间
    start_price: float  # 起始价格（顶/底分型的极值）
    end_price: float  # 结束价格（顶/底分型的极值）
    bi_type: BiDirectionType  # 笔的方向


    real_origin_kline_count: int  # 笔包含的真实原始 K 线数量（一端分型最高点到另一端最低点之间）
    real_merged_kline_count: int  # 笔包含的真实合并 K 线数量（一端分型最高点到另一端最低点之间）
    
    # 包含缺口数量
    has_gap_count: int = 0

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
        return self.real_merged_kline_count+ self.has_gap_count
        
    

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


def identify_bi_from_fenxing(fenxing_list: List[FenXing], all_klines: List[MergedKLine] = None) -> List[Bi]:
    """
    根据分型列表划分缠论笔

    Args:
        fenxing_list: 分型对象列表
        all_klines: 合并后的K线列表（可选，用于获取时间信息）

    Returns:
        List[Bi]: Bi 对象列表
    """
    bi_list = []
    last_fractal = None

    for i, fenxing in enumerate(fenxing_list):
        if last_fractal is None:
            last_fractal = (i, fenxing)
            continue

        last_idx, last_fx = last_fractal

        # 规则：同向分型取极值（如果两个都是顶，取更高的那个；两个都是底，取更低的那个）
        if last_fx.is_top_bottom == fenxing.is_top_bottom:
            if fenxing.is_top_bottom == 1 and fenxing.high_price > last_fx.high_price:
                last_fractal = (i, fenxing)
            elif fenxing.is_top_bottom == -1 and fenxing.low_price < last_fx.low_price:
                last_fractal = (i, fenxing)
            continue

        # 规则：顶底之间至少要有1根独立K线 (索引差 >= 4，因为中间要隔一根)
        # 缠论严格定义是顶底分型元素不共用，且中间至少有一根K线。
        # 在合并K线序列中，索引差至少为 3 (例如: 0是底, 1是中间, 2是顶 -> 差2不行，至少要差3或4视具体实现)
        # 通常要求：顶分型最高K线索引 - 底分型最低K线索引 >= 4
        if abs(fenxing.end_idx - last_fx.end_idx) >= 4:
            direction = "up" if fenxing.is_top_bottom == 1 else "down"
            bi_type = BiDirectionType.UP if direction == "up" else BiDirectionType.DOWN

            # 确定起始和结束索引
            start_idx = last_fx.low_idx if direction == "up" else last_fx.high_idx
            end_idx = fenxing.high_idx if direction == "up" else fenxing.low_idx
            if end_idx <= start_idx:
                raise ValueError("结束索引不能小于起始索引")

            # 获取时间信息（如果提供了 all_klines）
            start_time = all_klines[start_idx].trade_date
            end_time = all_klines[end_idx].trade_date

            bi_real_merged_kline_count, bi_has_gap_count = calculate_bi_real_merged_kline_count_and_gap_count(last_fx.get_mid_idx(), fenxing.get_mid_idx(),
                                            all_klines)
            # 创建 Bi 对象
            bi = Bi(
                start_idx=start_idx,
                end_idx=end_idx,
                start_time=start_time,
                end_time=end_time,
                start_price=last_fx.low_price if direction == "up" else last_fx.high_price,
                end_price=fenxing.high_price if direction == "up" else fenxing.low_price,
                bi_type=bi_type,
                real_origin_kline_count=end_idx - start_idx + 1,
                real_merged_kline_count=bi_real_merged_kline_count,
                has_gap_count=bi_has_gap_count
            )
            bi_list.append(bi)
            last_fractal = (i, fenxing)
    # print(bi_list)
    return bi_list


def calculate_bi_real_merged_kline_count_and_gap_count(start_kline_idx: int, end_kline_idx: int, all_klines: List[MergedKLine]) -> Tuple[int,int]:
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

