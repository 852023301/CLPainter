import os
import pickle
from pathlib import Path
from typing import List


class MergedKLine:
    def __init__(self, trade_date, open_, close, low, high, volume):
        self.trade_date = trade_date
        self.open = open_
        self.close = close
        self.low = low
        self.high = high
        self.volume = volume  # 交易量单位为股

        # 根据上一根k线的状态决定下一根k线的参数
        self._is_contained = 0  # 是否合并,is_contained=1是合并,is_contained=0是未合并，用于显示颜色
        self.merged_length = 1  # 连续合并的K线长度
        self.merged_trend = 1  # 合并结果,trend=1是向上,trend=0是向下，用于显示颜色
        self.merged_high = high  # 合并后的最高价
        self.merged_low = low  # 合并后的最低价

        # 定义顶分型和底分型  1为顶分型，-1为底分型
        self.is_top_bottom = 0

    @property
    def is_contained(self):
        return self._is_contained

    @is_contained.setter
    def is_contained(self, value):
        self._is_contained = value


def find_top_bottom(all_klines: List[MergedKLine]):
    """
    寻找合并后K线的顶底分型
    :param all_klines:
    :return:
    """
    if len(all_klines) < 2:
        return

    # 寻找每一根K线的前一根未包含K线的位置

    for idx, merged_kline in enumerate(all_klines):
        if idx < 2:
            continue

        mid_merged_kline = all_klines[idx - merged_kline.merged_length]
        left_merged_kline = all_klines[idx - merged_kline.merged_length - mid_merged_kline.merged_length]

        if merged_kline.merged_length != 1:
            continue

        # 顶底分型完成信号不会同时出现在一根K线上
        if (left_merged_kline.merged_low > mid_merged_kline.merged_low) and (
            mid_merged_kline.merged_low < merged_kline.merged_low):
            merged_kline.is_top_bottom = -1

        elif (left_merged_kline.merged_high < mid_merged_kline.merged_high) and (
            mid_merged_kline.merged_high > merged_kline.merged_high):
            merged_kline.is_top_bottom = 1

        else:
            merged_kline.is_top_bottom = 0


def merge_data():
    """
    K线合并
    :return:
    """
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    origin_klines = get_data_init_set
    all_klines = []

    for idx, kl in enumerate(origin_klines):
        merged_kline = MergedKLine(*kl)

        if len(all_klines) == 0:
            # 第一根k线不处理
            all_klines.append(merged_kline)
            continue

        # 根据上一根k线的状态决定下一根k线的参数
        last_merged_kline = all_klines[-1]
        if last_merged_kline.merged_high < merged_kline.high and last_merged_kline.merged_low < merged_kline.low:
            merged_kline.merged_trend = 1
        elif last_merged_kline.merged_high > merged_kline.high and last_merged_kline.merged_low > merged_kline.low:
            merged_kline.merged_trend = 0
        else:

            # 判断合并
            if (last_merged_kline.merged_high <= merged_kline.high
                and last_merged_kline.merged_low >= merged_kline.low) or (
                last_merged_kline.high >= merged_kline.high and last_merged_kline.merged_low <= merged_kline.low
            ):
                merged_kline.is_contained = 1
                merged_kline.merged_trend = last_merged_kline.merged_trend
                merged_kline.merged_length = last_merged_kline.merged_length + 1

                if (
                    last_merged_kline.merged_high <= merged_kline.high and
                    last_merged_kline.merged_low >= merged_kline.low):
                    merged_kline.merged_high = merged_kline.high if merged_kline.merged_trend == 1 \
                        else last_merged_kline.merged_high
                    merged_kline.merged_low = last_merged_kline.low if merged_kline.merged_trend == 1 \
                        else merged_kline.merged_low

                elif (
                    last_merged_kline.high >= merged_kline.high and
                    last_merged_kline.merged_low <= merged_kline.low):
                    merged_kline.merged_high = last_merged_kline.high if merged_kline.merged_trend == 1 \
                        else merged_kline.high
                    merged_kline.merged_low = merged_kline.low if merged_kline.merged_trend == 1 \
                        else last_merged_kline.merged_low
                else:
                    raise Exception("异常包含关系")

        all_klines.append(merged_kline)

    return all_klines


from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class BiType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 上升笔：底→顶
    DOWN = 'down'  # 下降笔：顶→底


@dataclass
class Bi:
    """笔数据结构（优化版）"""
    start_idx: int  # 笔起始位置索引（分型所在 K 线索引）
    end_idx: int  # 笔结束位置索引（分型所在 K 线索引）
    start_date: str  # 起始日期
    end_date: str  # 结束日期
    start_price: float  # 起始价格（顶/底分型的极值）
    end_price: float  # 结束价格（顶/底分型的极值）
    bi_type: BiType  # 笔的方向
    high_price: float  # 笔中的最高价
    low_price: float  # 笔中的最低价
    start_is_top: bool  # 笔起点是否为顶分型

    # 新增字段：用于验证条件 3
    start_fx_low: float = field(default=0.0)  # 起点分型三根 K 线的最低点
    start_fx_high: float = field(default=0.0)  # 起点分型三根 K 线的最高点
    end_fx_low: float = field(default=0.0)  # 终点分型三根 K 线的最低点
    end_fx_high: float = field(default=0.0)  # 终点分型三根 K 线的最高点

    # 新增字段：笔包含的 K 线索引范围（用于验证至少 5 根）
    kline_count: int = 0  # 笔包含的合并 K 线数量

    @property
    def is_up(self) -> bool:
        return self.bi_type == BiType.UP

    @property
    def is_down(self) -> bool:
        return self.bi_type == BiType.DOWN

    def validate_min_klines(self, min_klines: int = 5) -> bool:
        """验证笔是否满足最少 K 线数"""
        return self.kline_count >= min_klines

    def validate_extreme_points(self) -> bool:
        """
        验证条件 2：
        - 底分型最低点=笔最低点，其他 K 线最低价>底分型最低点
        - 顶分型最高点=笔最高点，其他 K 线最高价<顶分型最高点
        """
        # 这个验证需要在生成笔时传入 K 线数据进行
        return True

    def validate_cross_condition(self) -> bool:
        """
        验证条件 3：端点交叉条件
        - 底分型最低点 < 顶分型三根 K 线的最低点
        - 顶分型最高点 > 底分型三根 K 线的最高点
        """
        if self.is_up:
            # 上升笔：起点是底，终点是顶
            # 底分型最低点 < 顶分型三根 K 线最低点
            if self.start_fx_low < self.end_fx_low:
                return False
            # 顶分型最高点 > 底分型三根 K 线最高点
            if self. start_fx_high < self.end_fx_high:
                return False
        else:
            # 下降笔：起点是顶，终点是底
            # 底分型最低点 < 顶分型三根 K 线最低点
            if self.start_fx_low > self.start_fx_low:
                return False
            # 顶分型最高点 > 底分型三根 K 线最高点
            if self.start_fx_high > self.end_fx_high:
                return False
        return True


class BiGenerator:
    """笔生成器 - 实现旧笔画法"""

    MIN_KLINES = 5  # 至少 5 根合并 K 线才能构成一笔

    def __init__(self, merge_data_list: List[MergedKLine]):
        self.klines = merge_data_list
        self.n = len(merge_data_list)
        self.bis: List[Bi] = []

        # 预处理：获取所有分型索引
        self.top_indices = []  # 顶分型索引列表
        self.bottom_indices = []  # 底分型索引列表
        self._find_all_fx()

    def _find_all_fx(self):
        """找出所有顶底分型的索引"""
        for i, kl in enumerate(self.klines):
            if kl.is_top_bottom == 1:
                self.top_indices.append(i)
            elif kl.is_top_bottom == -1:
                self.bottom_indices.append(i)

    def _get_fx_three_klines_low(self, fx_idx: int) -> float:
        """
        获取分型三根 K 线的最低点
        分型本身 + 左右各一根 K 线
        """
        if fx_idx <= 0 or fx_idx >= self.n - 1:
            # 边界情况，只有一根 K 线
            return self.klines[fx_idx].merged_low

        left_idx = max(0, fx_idx - 1)
        right_idx = min(self.n - 1, fx_idx + 1)

        return min(
            self.klines[left_idx].merged_low,
            self.klines[fx_idx].merged_low,
            self.klines[right_idx].merged_low
        )

    def _get_fx_three_klines_high(self, fx_idx: int) -> float:
        """
        获取分型三根 K 线的最高点
        分型本身 + 左右各一根 K 线
        """
        if fx_idx <= 0 or fx_idx >= self.n - 1:
            return self.klines[fx_idx].merged_high

        left_idx = max(0, fx_idx - 1)
        right_idx = min(self.n - 1, fx_idx + 1)

        return max(
            self.klines[left_idx].merged_high,
            self.klines[fx_idx].merged_high,
            self.klines[right_idx].merged_high
        )

    def _find_start_point(self) -> Tuple[int, bool]:
        """
        找到起点：全局最高价或全局最低价，哪个时间更早就选哪个
        返回：(起点索引，是否为顶分型)
        """
        if self.n == 0:
            return -1, False

        # 找到全局最高和最低的索引
        max_price = float('-inf')
        min_price = float('inf')
        max_idx = 0
        min_idx = 0

        for i, kl in enumerate(self.klines):
            if kl.merged_high > max_price:
                max_price = kl.merged_high
                max_idx = i
            if kl.merged_low < min_price:
                min_price = kl.merged_low
                min_idx = i

        # 选择时间更早的
        if min_idx < max_idx:
            return min_idx, False  # 底分型起点
        else:
            return max_idx, True  # 顶分型起点

    def _find_nearest_fx(self, start_idx: int, need_top: bool) -> Optional[int]:
        """
        从 start_idx 开始向后找最近的符合条件的分型
        need_top=True 找顶分型，False 找底分型
        """
        candidates = self.top_indices if need_top else self.bottom_indices

        for fx_idx in candidates:
            if fx_idx > start_idx:
                return fx_idx
        return None

    def _validate_bi(self, start_idx: int, end_idx: int,
                     start_is_top: bool) -> Optional[Bi]:
        """
        验证从 start_idx 到 end_idx 是否能构成一笔
        返回 Bi 对象或 None
        """
        if end_idx is None or start_idx is None:
            return None

        # 条件 1：至少 5 根 K 线
        kline_count = end_idx - start_idx + 1
        if kline_count < self.MIN_KLINES:
            return None

        start_kl = self.klines[start_idx]
        end_kl = self.klines[end_idx]

        # 确定笔类型
        if start_is_top:
            bi_type = BiType.DOWN  # 顶→底是下降笔
        else:
            bi_type = BiType.UP  # 底→顶是上升笔

        # 计算笔中的最高价和最低价
        high_price = float('-inf')
        low_price = float('inf')
        for i in range(start_idx, end_idx + 1):
            kl = self.klines[i]
            high_price = max(high_price, kl.merged_high)
            low_price = min(low_price, kl.merged_low)

        # 条件 2：验证极值点
        # 底分型的最低点必须是笔的最低点
        # 顶分型的最高点必须是笔的最高点
        if start_is_top:
            # 起点是顶：起点最高价应该是笔的最高价
            if start_kl.merged_high != high_price:
                return None
            # 终点是底：终点最低价应该是笔的最低价
            if end_kl.merged_low != low_price:
                return None
        else:
            # 起点是底：起点最低价应该是笔的最低价
            if start_kl.merged_low != low_price:
                return None
            # 终点是顶：终点最高价应该是笔的最高价
            if end_kl.merged_high != high_price:
                return None

        # 获取分型三根 K 线的极值
        start_fx_low = self._get_fx_three_klines_low(start_idx)
        start_fx_high = self._get_fx_three_klines_high(start_idx)
        end_fx_low = self._get_fx_three_klines_low(end_idx)
        end_fx_high = self._get_fx_three_klines_high(end_idx)

        # 条件 3：验证端点交叉
        if bi_type == BiType.UP:
            # 上升笔：底→顶
            # 底分型最低点 < 顶分型三根 K 线最低点
            if start_kl.merged_low >= end_fx_low:
                return None
            # 顶分型最高点 > 底分型三根 K 线最高点
            if end_kl.merged_high <= start_fx_high:
                return None
        else:
            # 下降笔：顶→底
            # 底分型最低点 < 顶分型三根 K 线最低点
            if end_kl.merged_low >= start_fx_low:
                return None
            # 顶分型最高点 > 底分型三根 K 线最高点
            if start_kl.merged_high <= end_fx_high:
                return None

        # 所有条件满足，创建 Bi
        bi = Bi(
            start_idx=start_idx,
            end_idx=end_idx,
            start_date=start_kl.trade_date,
            end_date=end_kl.trade_date,
            start_price=start_kl.merged_high if start_is_top else start_kl.merged_low,
            end_price=end_kl.merged_low if start_is_top else end_kl.merged_high,
            bi_type=bi_type,
            high_price=high_price,
            low_price=low_price,
            start_is_top=start_is_top,
            start_fx_low=start_fx_low,
            start_fx_high=start_fx_high,
            end_fx_low=end_fx_low,
            end_fx_high=end_fx_high,
            kline_count=kline_count
        )

        return bi

    def generate(self) -> List[Bi]:
        """
        生成所有笔
        采用笔破坏原则：下一笔确认后才能确定前一笔结束
        """
        if self.n == 0:
            return []

        # 找到起点
        start_idx, start_is_top = self._find_start_point()

        if start_idx == -1:
            return []

        # 检查起点是否真的是分型
        start_kl = self.klines[start_idx]
        if start_is_top and start_kl.is_top_bottom != 1:
            # 全局最高点不是顶分型，找最近的顶分型
            new_idx = self._find_nearest_fx(start_idx, need_top=True)
            if new_idx is None:
                return []
            start_idx = new_idx
            start_is_top = True
        elif not start_is_top and start_kl.is_top_bottom != -1:
            # 全局最低点不是底分型，找最近的底分型
            new_idx = self._find_nearest_fx(start_idx, need_top=False)
            if new_idx is None:
                return []
            start_idx = new_idx
            start_is_top = False

        current_idx = start_idx
        current_is_top = start_is_top
        pending_bi: Optional[Bi] = None  # 当前待确认的笔

        while current_idx < self.n:
            # 寻找下一个分型（交替）
            next_fx_idx = self._find_nearest_fx(current_idx, need_top=not current_is_top)

            if next_fx_idx is None:
                # 没有找到下一个分型，结束
                break

            # 尝试形成一笔
            bi = self._validate_bi(current_idx, next_fx_idx, current_is_top)

            if bi:
                # 如果已有待确认的笔，说明前一笔被破坏，确认前一笔
                if pending_bi:
                    self.bis.append(pending_bi)

                # 创建新的待确认笔
                pending_bi = bi
                current_idx = next_fx_idx
                current_is_top = not current_is_top
            else:
                # 不满足笔的条件，继续向后找
                # 这里采用跳过策略：如果当前分型无法成笔，找下一个同类型分型
                if current_is_top:
                    # 当前是顶，找下一个顶
                    next_same_fx = None
                    for idx in self.top_indices:
                        if idx > current_idx:
                            next_same_fx = idx
                            break
                    if next_same_fx:
                        current_idx = next_same_fx
                    else:
                        break
                else:
                    # 当前是底，找下一个底
                    next_same_fx = None
                    for idx in self.bottom_indices:
                        if idx > current_idx:
                            next_same_fx = idx
                            break
                    if next_same_fx:
                        current_idx = next_same_fx
                    else:
                        break

        # 最后一笔如果是待确认状态，且满足条件，也加入
        if pending_bi:
            self.bis.append(pending_bi)

        return self.bis


# 使用示例
def generate_bis(merge_data_list: List[MergedKLine]) -> List[Bi]:
    """
    主函数：根据合并后的 K 线数据生成笔

    Args:
        merge_data_list: 已标注顶底分型的合并 K 线列表

    Returns:
        笔列表
    """
    generator = BiGenerator(merge_data_list)
    return generator.generate()



def get_data_init():
    # import requests
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    # get_data_init_set = json_response = response.json()
    with open(Path(os.environ['appDir']) / "data_set/data_set.pkl", "rb", ) as f:
        json_response = pickle.load(f)
    # 解析数据
    return json_response


# 原始文件
get_data_init_set = get_data_init()

# 合并后的数据
merge_data_list = merge_data()
find_top_bottom(merge_data_list)

# for i in merge_data_list:
#     # print(i.trade_date,i.is_contained, i.merged_length)
#     print(i.trade_date, i.is_contained, i.merged_length, i.is_top_bottom)

merge_kline_data = [[data.merged_low if data.close > data.open else data.merged_high,
                     data.merged_high if data.close > data.open else data.merged_low,
                     data.merged_low, data.merged_high] for data in merge_data_list]
origin_kline_data = [[data.open,
                      data.close,
                      data.low, data.high] for data in merge_data_list]

# 交易日
trade_date_list = [data.trade_date for data in merge_data_list]
