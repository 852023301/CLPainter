import os
import pickle

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from enum import Enum
import numpy as np

@dataclass
class MergedKLine:
    """合并后的K线数据类"""

    trade_date: str
    open: float
    close: float
    low: float
    high: float
    volume: float  # 交易量单位为股

    # K线合并状态
    _is_contained: int = field(default=0, repr=False)  # 是否被合并：1=合并，0=未合并
    merged_length: int = 1  # 连续合并的K线数量
    merged_trend: int = 1  # 合并趋势：1=向上，0=向下
    merged_high: float = field(init=False)  # 合并后的最高价
    merged_low: float = field(init=False)  # 合并后的最低价

    # 分型标记：1=顶分型，-1=底分型，0=无分型
    is_top_bottom: int = 0

    def __post_init__(self):
        # 初始化合并后的高低点为当前K线的高低点
        self.merged_high = self.high
        self.merged_low = self.low

    @property
    def is_contained(self) -> int:
        return self._is_contained

    @is_contained.setter
    def is_contained(self, value: int):
        if value not in (0, 1):
            raise ValueError("is_contained must be 0 or 1")
        self._is_contained = value

@dataclass
class FenXing:
    """分型数据结构"""
    # 分型标记：1=顶分型，-1=底分型
    is_top_bottom: int
    # 分型开始位置索引
    idx: int = field(init=False)
    # 分型长度
    length: int = field(init=False)
    # 三根合并后K线各自的长度
    length_list: List[int] = field(init=False)
    # 三根合并后K线各自的开始索引
    idx_list: List[int] = field(init=False)
    # 分型最高价
    high_price: float = field(init=False)
    # 分型最低价
    low_price: float = field(init=False)
    # 分型最高价索引
    high_idx: int = field(init=False)
    # 分型最低价索引
    low_idx: int = field(init=False)



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
    high_price: float  # 笔中的最高价
    low_price: float  # 笔中的最低价


    # 新增字段：笔包含的 K 线索引范围（用于验证至少 5 根）
    kline_count: int = 0  # 笔包含的合并 K 线数量

    @property
    def is_up(self) -> bool:
        return self.bi_type == BiDirectionType.UP

    @property
    def is_down(self) -> bool:
        return self.bi_type == BiDirectionType.DOWN


def merge_klines(origin_klines: List[List]) -> List[MergedKLine]:
    """
    K线合并处理（缠论包含关系处理）

    Args:
        origin_klines: 原始K线数据列表，每个元素为 [date, open, close, low, high, volume]

    Returns:
        合并后的K线列表
    """
    if not origin_klines:
        return []

    all_klines: List[MergedKLine] = []

    for kl in origin_klines:
        merged_kline = MergedKLine(*kl)

        if not all_klines:
            # 第一根K线直接添加
            all_klines.append(merged_kline)
            continue

        last_kline = all_klines[-1]

        # 判断趋势方向
        if last_kline.merged_high < merged_kline.high and last_kline.merged_low < merged_kline.low:
            merged_kline.merged_trend = 1  # 向上趋势
        elif last_kline.merged_high > merged_kline.high and last_kline.merged_low > merged_kline.low:
            merged_kline.merged_trend = 0  # 向下趋势
        else:
            # 存在包含关系，需要合并
            if _has_containment(last_kline, merged_kline):
                _apply_containment(last_kline, merged_kline)
                all_klines.append(merged_kline)
                continue

        all_klines.append(merged_kline)

    return all_klines


def _has_containment(k1: MergedKLine, k2: MergedKLine) -> bool:
    """判断两根K线是否存在包含关系"""
    return (
        (k1.merged_high <= k2.high and k1.merged_low >= k2.low) or
        (k1.high >= k2.high and k1.merged_low <= k2.low)
    )


def _apply_containment(last_kline: MergedKLine, current_kline: MergedKLine) -> None:
    """应用K线包含关系合并规则"""
    current_kline.is_contained = 1
    current_kline.merged_trend = last_kline.merged_trend
    current_kline.merged_length = last_kline.merged_length + 1

    # 根据趋势方向确定合并后的高低点
    if last_kline.merged_high <= current_kline.high and last_kline.merged_low >= current_kline.low:
        # 情况1：当前K线被上一根包含
        if current_kline.merged_trend == 1:  # 向上趋势取高高
            current_kline.merged_high = current_kline.high
            current_kline.merged_low = last_kline.low
        else:  # 向下趋势取低低
            current_kline.merged_high = last_kline.merged_high
            current_kline.merged_low = current_kline.low

    elif last_kline.high >= current_kline.high and last_kline.merged_low <= current_kline.low:
        # 情况2：上一根K线被当前包含
        if current_kline.merged_trend == 1:  # 向上趋势取高高
            current_kline.merged_high = last_kline.high
            current_kline.merged_low = current_kline.low
        else:  # 向下趋势取低低
            current_kline.merged_high = current_kline.high
            current_kline.merged_low = last_kline.merged_low
    else:
        raise ValueError(f"异常的包含关系: {last_kline.trade_date} -> {current_kline.trade_date}")


def load_raw_data() -> List[List]:
    """
    加载原始K线数据

    Returns:
        原始K线数据列表
    """
    app_dir = os.environ.get('appDir')
    if not app_dir:
        raise EnvironmentError("环境变量 'appDir' 未设置")

    data_file = Path(app_dir) / "data_set/data_set.pkl"

    if not data_file.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_file}")

    try:
        with open(data_file, "rb") as f:
            return pickle.load(f)
    except (pickle.PickleError, EOFError) as e:
        raise ValueError(f"数据文件解析失败: {e}")


def find_top_bottom(all_klines: List[MergedKLine]) -> None:
    """
    寻找合并后K线的顶底分型
    """
    if len(all_klines) < 3:
        return

    for idx in range(2, len(all_klines)):
        current_kline = all_klines[idx]

        # 只处理未被合并的K线
        if current_kline.merged_length != 1:
            continue

        # 获取前两根未合并的K线
        prev_offset = current_kline.merged_length
        mid_idx = idx - prev_offset
        left_idx = mid_idx - all_klines[mid_idx].merged_length

        if left_idx < 0:
            continue

        left_kline = all_klines[left_idx]
        mid_kline = all_klines[mid_idx]

        # 判断底分型：左中右形成V型
        if left_kline.merged_low > mid_kline.merged_low < current_kline.merged_low:
            current_kline.is_top_bottom = -1
        # 判断顶分型：左中右形成倒V型
        elif left_kline.merged_high < mid_kline.merged_high > current_kline.merged_high:
            current_kline.is_top_bottom = 1
        else:
            current_kline.is_top_bottom = 0


def extract_fenxing_list(all_klines: List[MergedKLine]) -> List[FenXing]:
    """
    从合并后的K线列表中提取分型集合
    
    Args:
        all_klines: 合并后的K线列表
        
    Returns:
        分型对象列表
    """
    fenxing_list = []
    
    if len(all_klines) < 3:
        return fenxing_list
    
    for idx in range(len(all_klines)):
        kline = all_klines[idx]
        
        # 只处理有分型标记的K线
        if kline.is_top_bottom == 0:
            continue
        
        # 创建分型对象
        fenxing = FenXing(is_top_bottom=kline.is_top_bottom)
        
        # 设置分型索引（当前K线索引）
        fenxing.idx = idx
        
        # 计算分型长度：包含左、中、右三根K线的总长度
        # 左K线
        prev_offset = kline.merged_length
        mid_idx = idx - prev_offset
        
        if mid_idx < 0:
            continue
        
        mid_kline = all_klines[mid_idx]
        left_idx = mid_idx - mid_kline.merged_length
        
        if left_idx < 0:
            continue
        
        left_kline = all_klines[left_idx]
        
        # 分型长度为三根K线各自的 merged_length 之和
        fenxing.length = left_kline.merged_length + mid_kline.merged_length + kline.merged_length
        
        # 记录三根K线各自的长度
        fenxing.length_list = [
            left_kline.merged_length,
            mid_kline.merged_length,
            kline.merged_length
        ]

        # 记录三根K线各自的开始索引
        fenxing.idx_list = [
            left_idx - left_kline.merged_length + 1,
            left_idx + 1,
            mid_idx + 1
        ]

        def get_high_price_idx(mid_klines):
            HHV = -1
            loc = None
            for idx, kline in enumerate(mid_klines):
                if kline.merged_high > HHV:
                    HHV = kline.merged_high
                    loc = idx
            return loc

        def get_low_price_idx(mid_klines):
            LLV = np.inf
            loc = None
            for idx, kline in enumerate(mid_klines):
                if kline.merged_low < LLV:
                    LLV = kline.merged_low
                    loc = idx
            return loc
        
        # 确定分型的最高价和最低价及其索引
        # 顶分型：取中间K线的最高价
        # 底分型：取中间K线的最低价
        if kline.is_top_bottom == 1:  # 顶分型
            fenxing.high_price = mid_kline.merged_high
            fenxing.high_idx = get_high_price_idx(all_klines[left_idx + 1:mid_idx + 1])
            # 底价为三根K线中的最低价
            fenxing.low_price = min(left_kline.merged_low, mid_kline.merged_low, kline.merged_low)

            fenxing.low_idx = min(
                [(left_kline.merged_low, left_idx),
                 (mid_kline.merged_low, mid_idx),
                 (kline.merged_low, idx)],
                key=lambda x: x[0]
            )[1]

        else:  # 底分型
            fenxing.low_price = mid_kline.merged_low
            fenxing.low_idx = get_low_price_idx(all_klines[left_idx + 1:mid_idx + 1])
            # 高价为三根K线中的最高价
            fenxing.high_price = max(left_kline.merged_high, mid_kline.merged_high, kline.merged_high)
            fenxing.high_idx = max(
                [(left_kline.merged_high, left_idx),
                 (mid_kline.merged_high, mid_idx),
                 (kline.merged_high, idx)],
                key=lambda x: x[0]
            )[1]
        
        fenxing_list.append(fenxing)
    
    return fenxing_list


def identify_bi(all_klines: List[MergedKLine]) -> List[dict]:
    """
    根据顶底分型划分缠论笔
    Returns: list of dicts with 'start_idx', 'end_idx', 'direction' ('up' or 'down')
    """
    bi_list = []
    last_fractal = None

    for i, kl in enumerate(all_klines):
        if kl.is_top_bottom != 0:
            if last_fractal is None:
                last_fractal = (i, kl)
                continue

            last_idx, last_kl = last_fractal

            # 规则：同向分型取极值（如果两个都是顶，取更高的那个；两个都是底，取更低的那个）
            if last_kl.is_top_bottom == kl.is_top_bottom:
                if kl.is_top_bottom == 1 and kl.merged_high > last_kl.merged_high:
                    last_fractal = (i, kl)
                elif kl.is_top_bottom == -1 and kl.merged_low < last_kl.merged_low:
                    last_fractal = (i, kl)
                continue

            # 规则：顶底之间至少要有1根独立K线 (索引差 >= 4，因为中间要隔一根)
            # 缠论严格定义是顶底分型元素不共用，且中间至少有一根K线。
            # 在合并K线序列中，索引差至少为 3 (例如: 0是底, 1是中间, 2是顶 -> 差2不行，至少要差3或4视具体实现)
            # 通常要求：顶分型最高K线索引 - 底分型最低K线索引 >= 4
            if abs(i - last_idx) >= 4:
                direction = "up" if kl.is_top_bottom == 1 else "down"
                bi_list.append({
                    "start": last_idx,
                    "end": i,
                    "direction": direction,
                    "start_price": last_kl.merged_low if direction == "up" else last_kl.merged_high,
                    "end_price": kl.merged_high if direction == "up" else kl.merged_low
                })
                last_fractal = (i, kl)

    return bi_list


# 懒加载数据缓存
class _DataCache:
    """数据缓存类，实现懒加载"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._raw_data = None
        self._merged_klines = None
        self._trade_dates = None
        self._origin_kline_data = None
        self._merge_kline_data = None
        self._bi_list = None
        self._initialized = True

    def ensure_loaded(self):
        """确保数据已加载"""
        if self._raw_data is not None:
            return

        # 加载原始数据
        self._raw_data = load_raw_data()

        # 合并K线
        merged_klines = merge_klines(self._raw_data)
        self._merged_klines = merged_klines

        # 查找顶底分型
        find_top_bottom(merged_klines)

        # 划分笔
        self._bi_list = identify_bi(merged_klines)

        # 生成各种格式的数据
        self._merge_kline_data = [
            [
                data.merged_low if data.close > data.open else data.merged_high,
                data.merged_high if data.close > data.open else data.merged_low,
                data.merged_low,
                data.merged_high
            ]
            for data in merged_klines
        ]

        self._origin_kline_data = [
            [data.open, data.close, data.low, data.high]
            for data in merged_klines
        ]

        self._trade_dates = [data.trade_date for data in merged_klines]

    @property
    def raw_data(self) -> List[List]:
        self.ensure_loaded()
        return self._raw_data

    @property
    def merged_klines(self) -> List[MergedKLine]:
        self.ensure_loaded()
        return self._merged_klines

    @property
    def trade_dates(self) -> List[str]:
        self.ensure_loaded()
        return self._trade_dates

    @property
    def origin_kline_data(self) -> List[List[float]]:
        self.ensure_loaded()
        return self._origin_kline_data

    @property
    def merge_kline_data(self) -> List[List[float]]:
        self.ensure_loaded()
        return self._merge_kline_data

    @property
    def bi_list(self) -> List[dict]:
        self.ensure_loaded()
        return self._bi_list


# 创建全局数据缓存实例
_data_cache = _DataCache()


# 保持向后兼容的接口
def get_data_init() -> List[List]:
    """获取原始数据（向后兼容）"""
    return _data_cache.raw_data


def get_merge_data_list() -> List[MergedKLine]:
    """获取合并后的K线数据（向后兼容）"""
    return _data_cache.merged_klines


# 导出变量（保持向后兼容）
get_data_init_set = _data_cache.raw_data
merge_data_list = _data_cache.merged_klines
trade_date_list = _data_cache.trade_dates
origin_kline_data = _data_cache.origin_kline_data
merge_kline_data = _data_cache.merge_kline_data
bi_data_list = _data_cache.bi_list
