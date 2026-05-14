import os
import pickle
from pathlib import Path
from typing import List


class MergedKLine:
    """合并后的K线数据类"""

    def __init__(self, trade_date: str, open_: float, close: float,
                 low: float, high: float, volume: float):
        self.trade_date = trade_date
        self.open = open_
        self.close = close
        self.low = low
        self.high = high
        self.volume = volume  # 交易量单位为股

        # K线合并状态
        self._is_contained = 0  # 是否被合并：1=合并，0=未合并
        self.merged_length = 1  # 连续合并的K线数量
        self.merged_trend = 1  # 合并趋势：1=向上，0=向下
        self.merged_high = high  # 合并后的最高价
        self.merged_low = low  # 合并后的最低价

        # 分型标记：1=顶分型，-1=底分型，0=无分型
        self.is_top_bottom = 0

    @property
    def is_contained(self) -> int:
        return self._is_contained

    @is_contained.setter
    def is_contained(self, value: int):
        if value not in (0, 1):
            raise ValueError("is_contained must be 0 or 1")
        self._is_contained = value


def find_top_bottom(all_klines: List[MergedKLine]) -> None:
    """
    寻找合并后K线的顶底分型

    Args:
        all_klines: 合并后的K线列表
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
