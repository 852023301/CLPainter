import os
import pickle
import re
import json
import math
from pathlib import Path
from typing import List
from datetime import timezone

import pandas as pd

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.toolbox.bi import generate_bi, Bi
from CLPainter.web.backend.app.toolbox.fenxing import generate_fenxing, FenXing
from CLPainter.web.backend.app.toolbox.tezhengxulie import generate_te_zheng_xu_lie, TeZhengXuLie
from CLPainter.web.backend.app.toolbox.xianduan import generate_xian_duan, XianDuan
from CLPainter.web.backend.app.toolbox.merged_kline import generate_merge_klines, find_top_bottom, MergedKLine
from CLPainter.web.backend.app.toolbox.origin_kline import OriginKLine, generate_origin_klines
from CLPainter.web.backend.app.toolbox.zhongshu import ZhongShuBase, generate_zhongshu_from_bi, \
    generate_zhongshu_in_xianduan_from_bi, remove_bi_zhongshu_duplicates
from CLPainter.web.backend.app.toolbox.xianduan_zhongshu import (
    XianDuanZhongShu,
    generate_xianduan_zhongshu_another,
    generate_zhongshu_from_xianduan,
)
from CLPainter.web.backend.app.toolbox.xianduan_tezhengxulie import (
    XianduanTeZhengXuLie,
    generate_xianduan_tezheng_xu_lie,
)
from CLPainter.web.backend.app.toolbox.gap import Gap
from CLPainter.web.backend.app.toolbox.calculate import (
    calculate_boll_list,
    calculate_macd_indicator,
    calculate_ma_colors,
    calculate_ma_list,
    calculate_rsi_list,
)


def _create_detached_data_cache(cls):
    """创建不调用__init__的空_DataCache实例，供pickle重建使用。"""
    return object.__new__(cls)


DEFAULT_MA_PERIODS = [5, 8, 10, 13, 21, 34, 55, 60, 89, 120, 144, 233, 250]
INDICATOR_PARAMS = {
    "ma": {"periods": DEFAULT_MA_PERIODS},
    "boll": {"n": 26, "k": 2},
    "rsi": {"periods": [6, 12, 24]},
    "macd": {"short": 12, "long": 26, "mid": 9},
}
DEFAULT_MARKET_DIR = "market=cn"
DEFAULT_ASSET_CLASS_DIR = "asset_class=stock"
CHART_PAYLOAD_DIR = Path(settings.CACHE_DUMP_DIR).parent / "chart_payload"
SUPPORTED_CHART_FREQUENCIES = {
    "freq=1day": "日K",
    "freq=1week": "周K",
    "freq=1month": "月K",
    "freq=1quarter": "季K",
    "freq=1year": "年K",
    "freq=1min": "1分",
    "freq=5min": "5分",
    "freq=15min": "15分",
    "freq=30min": "30分",
    "freq=60min": "60分",
    "freq=120min": "120分",
    "freq=240min": "240分",
}


def _chart_time(value):
    """将日内时间转为UTC秒，日级时间保持字符串格式。"""
    if value == value.normalize():
        return value.strftime("%Y-%m-%d")
    return int(value.replace(tzinfo=timezone.utc).timestamp())


def load_raw_data(data_file=None) -> List[List]:
    """
    加载原始K线数据

    Returns:
        原始K线数据列表
    """
    # 优先使用配置类中的路径，如果未设置则尝试环境变量
    app_dir = settings.APP_DIR or os.environ.get('APP_DIR')
    if not app_dir:
        raise EnvironmentError("环境变量 'APP_DIR' 未设置且配置中未提供 APP_DIR")

    if data_file is None:
        data_file = Path(settings.DATA_DIR) / "freq=1day/000001SH.pkl"  #
        # data_file = Path(settings.DATA_DIR) / "1day/561980SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/516700SH.pkl"  # Fix:没有fake最后一条线段？为什么线段没有微调成功？
        # FIX: 0段;
        # FIX: 存在更早的反向段
        # data_file = Path(settings.DATA_DIR) / "1day/159831SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/159326SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/159865SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/512880SH.pkl"

        # data_file = Path(settings.DATA_DIR) / "1day/000001SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/000002SZ.pkl"  # FIX: 第一段顶点有问题,_adjust_xian_duan的原因
        # FIX: 2021年7月线段划分有问题;
        # FIX: 存在更早的反向段
        # data_file = Path(settings.DATA_DIR) / "1day/000008SZ.pkl"
        # FIX: 研究为什么会前面会缺少那么多线段？
        # FIX: 研究为什么2015-12~2017-05中间的两条线段缺少一个顶点没有_adjust_xian_duan的效果
        # data_file = Path(settings.DATA_DIR) / "1day/000605SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/001282SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/000009SZ.pkl"  #
        # data_file = Path(settings.DATA_DIR) / "1day/600703SH.pkl"  # Fix:需要延长
        # data_file = Path(settings.DATA_DIR) / "1day/600713SH.pkl"  # Fix:需要延长
        # data_file = Path(settings.DATA_DIR) / "1day/000011SZ.pkl"  #  Fix:需要延长
        # Fix:需要延长
        # data_file = Path(settings.DATA_DIR) / "1day/600499SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "1day/603533SH.pkl" # Fix:需要增加
        # data_file = Path(settings.DATA_DIR) / "1day/300883SZ.pkl" # Fix:线段划分有问题
        # data_file = Path(settings.DATA_DIR) / "1day//000908SZ.pkl"  # Fix:线段划分有问题
        # data_file = Path(settings.DATA_DIR) / "1day/300889SZ.pkl" # Fix:线段划分有问题

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
    special_path: Path | None = None

    def __new__(cls, special_path=None):
        """保证进程内只保留一个可切换数据源的数据缓存实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance.special_path = special_path
        return cls._instance

    def __init__(self, special_path=None):
        """初始化懒加载字段，避免创建时立即读取和计算数据。"""
        if self._initialized:
            return

        self._raw_data = None
        self._origin_kline_data = None
        self._gaps_list = None
        self._merged_klines = None
        self._fenxing_list = None
        self._trade_dates = None
        self._bi_list = None
        self._bi_zhongshu_list = None
        self._te_zheng_xu_lie = None
        self._xianduan_list = None
        self._xianduan_zhongshu_list = None
        self._xianduan_tezhengxulie_list = None
        self._xianduan_zhongshu_another_list = None
        self._bi_zhongshu_in_xianduan_list = None
        self._chart_payload = None
        self._initialized = True

    def __reduce__(self):
        """定义pickle重建方式，避免反序列化时触发单例构造逻辑。"""
        return _create_detached_data_cache, (self.__class__,), self.__dict__

    def ensure_loaded(self):
        """确保数据已加载"""
        if self._raw_data is not None:
            return

        # 加载原始数据
        self._raw_data = load_raw_data(self.special_path)

        if len(self._raw_data) == 0:
            raise ValueError("数据文件为空")
        # print(self._raw_data)

        # 生成原始K线数据类
        self._origin_kline_data, self._gaps_list = generate_origin_klines(self._raw_data)
        # self._origin_kline_data = self._origin_kline_data[:-5]

        # 合并K线
        merged_klines = generate_merge_klines(self._origin_kline_data)
        self._merged_klines = merged_klines

        # 提取分型列表
        self._fenxing_list = generate_fenxing(merged_klines)

        # 基于分型列表划分笔
        self._bi_list = generate_bi(self._fenxing_list, merged_klines)

        # 笔中枢（含扩张中枢）
        if len(self._bi_list) > 5:
            self._bi_zhongshu_list = generate_zhongshu_from_bi(self._bi_list)

        # self._bi_zhongshu_list = []

        # 特征序列
        self._te_zheng_xu_lie = generate_te_zheng_xu_lie(self._bi_list)

        #  线段
        self._xianduan_list = generate_xian_duan(self._te_zheng_xu_lie, self._bi_list)

        # print([(i.start_bi_idx,i.end_bi_idx,type(i)) for i in self._xianduan_list])

        # 笔中枢（仅限线段内）
        if len(self._bi_list) > 5:
            self._bi_zhongshu_in_xianduan_list = generate_zhongshu_in_xianduan_from_bi(
                self._bi_list, [(j.start_bi_idx + 1, j.end_bi_idx) for j in self._xianduan_list])

            self._bi_zhongshu_list = remove_bi_zhongshu_duplicates(
                self._bi_zhongshu_list,
                self._bi_zhongshu_in_xianduan_list,
            )

        if len(self._xianduan_list) > 5:
            self._xianduan_zhongshu_list = generate_zhongshu_from_xianduan(self._xianduan_list)

        self._xianduan_tezhengxulie_list = generate_xianduan_tezheng_xu_lie(self._xianduan_list)
        self._xianduan_zhongshu_another_list = generate_xianduan_zhongshu_another(
            self._xianduan_list,
            self._xianduan_tezhengxulie_list,
        )

        self._trade_dates = [data.trade_datetime for data in merged_klines]

    def build_chart_payload(self, precision: int = 2) -> dict:
        """构建 Lightweight Charts 所需的全部模板数据。"""
        self.ensure_loaded()
        if self._chart_payload is not None:
            return self._chart_payload

        klines = self._origin_kline_data
        dates = self._trade_dates
        chart_dates = [_chart_time(value) for value in dates]
        candle_data = [
            {
                "time": chart_dates[index],
                "open": float(kline.open),
                "high": float(kline.high),
                "low": float(kline.low),
                "close": float(kline.close),
            }
            for index, kline in enumerate(klines)
        ]
        previous_close = None
        change_data = []
        for kline in klines:
            close = float(kline.close)
            change_pct = 0.0 if previous_close in (None, 0) else (close - previous_close) / previous_close * 100
            change_data.append({
                "time": chart_dates[len(change_data)],
                "change_pct": round(change_pct, 6),
            })
            previous_close = close
        bi_data = []
        for bi in self._bi_list:
            bi_dict = bi.to_dict()
            bi_data.extend((
                {"time": chart_dates[bi_dict["start_idx"]], "value": bi_dict["start_price"]},
                {"time": chart_dates[bi_dict["end_idx"]], "value": bi_dict["end_price"]},
            ))

        xd_data = []
        for xd in self._xianduan_list:
            xd_dict = xd.to_dict()
            xd_data.extend((
                {"time": chart_dates[xd_dict["start_idx"]], "value": xd_dict["start_price"]},
                {"time": chart_dates[xd_dict["end_idx"]], "value": xd_dict["end_price"]},
            ))

        def zhongshu_data(items):
            """将中枢对象转换为前端绘图所需的价格区间字典。"""
            return [
                {
                    "start_time": _chart_time(item.start_time),
                    "end_time": _chart_time(item.end_time),
                    "high_price": float(item.high_price),
                    "low_price": float(item.low_price),
                }
                for item in items
            ]

        close_series = pd.Series([kline.close for kline in klines], index=chart_dates)
        ma_periods = INDICATOR_PARAMS["ma"]["periods"]
        ma_colors = calculate_ma_colors(ma_periods)
        ma_data = [
            {
                "key": f"MA{item['period']}",
                "label": f"MA{item['period']}",
                "color": ma_colors[index],
                "values": item["values"],
            }
            for index, item in enumerate(calculate_ma_list(close_series, ma_periods))
        ]
        boll_colors = ["#26A69A", "#AB47BC", "#00796B"]
        boll_data = [
            {"key": item["key"], "label": item["key"], "color": boll_colors[index], "values": item["values"]}
            for index, item in enumerate(
                calculate_boll_list(
                    close_series,
                    n=INDICATOR_PARAMS["boll"]["n"],
                    k=INDICATOR_PARAMS["boll"]["k"],
                    precision=precision,
                )
            )
        ]
        rsi_colors = ["#E91E63", "#4CAF50", "#795548"]
        rsi_data = [
            {"key": item["key"], "label": item["key"], "color": rsi_colors[index], "values": item["values"]}
            for index, item in enumerate(
                calculate_rsi_list(close_series, periods=INDICATOR_PARAMS["rsi"]["periods"], precision=precision)
            )
        ]
        volume_data = [
            {
                "time": chart_dates[index],
                "value": kline.volume if math.isfinite(kline.volume) else 0.0,
                "color": "#ef5350" if kline.is_up() else "#26a69a",
            }
            for index, kline in enumerate(klines)
        ]

        def serialized(value):
            """将数据序列化为紧凑且禁止NaN的JSON字符串。"""
            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )

        indicator_params = {
            "ma": {"periods": ma_periods},
            "boll": INDICATOR_PARAMS["boll"],
            "rsi": INDICATOR_PARAMS["rsi"],
            "macd": INDICATOR_PARAMS["macd"],
        }
        self._chart_payload = {
            "candle_data": serialized(candle_data),
            "change_data": serialized(change_data),
            "bi_data": serialized(bi_data),
            "xd_data": serialized(xd_data),
            "zhongshu_data": serialized(zhongshu_data(self._bi_zhongshu_list or [])),
            "zhongshu_in_xianduan_data": serialized(zhongshu_data(self._bi_zhongshu_in_xianduan_list or [])),
            "xianduan_zhongshu_data": serialized(zhongshu_data(self._xianduan_zhongshu_list or [])),
            "xianduan_zhongshu_another_data": serialized(zhongshu_data(self._xianduan_zhongshu_another_list or [])),
            "gaps_data": serialized([
                {
                    **gap.to_kwargs(),
                    "trade_datetime": _chart_time(gap.trade_datetime),
                    "time": _chart_time(gap.trade_datetime),
                }
                for gap in self._gaps_list
            ]),
            "volume_data": serialized(volume_data),
            "ma_data": serialized(ma_data),
            "boll_data": serialized(boll_data),
            "rsi_data": serialized(rsi_data),
            "macd_data": serialized(
                calculate_macd_indicator(
                    close_series,
                    short=INDICATOR_PARAMS["macd"]["short"],
                    long=INDICATOR_PARAMS["macd"]["long"],
                    mid=INDICATOR_PARAMS["macd"]["mid"],
                    precision=precision,
                )
            ),
            "indicator_params": indicator_params,
            "candle_count": len(candle_data),
            "precision": precision,
        }
        return self._chart_payload

    @property
    def raw_data(self) -> List[List]:
        """获取原始K线数据。"""
        self.ensure_loaded()
        return self._raw_data

    @property
    def origin_kline_data(self) -> List[OriginKLine]:
        """获取标准化后的原始K线列表。"""
        self.ensure_loaded()
        return self._origin_kline_data

    @property
    def gaps_list(self) -> List[Gap]:
        """获取缺口标注列表。"""
        self.ensure_loaded()
        return self._gaps_list

    @property
    def merged_klines(self) -> List[MergedKLine]:
        """获取合并K线列表。"""
        self.ensure_loaded()
        return self._merged_klines

    @property
    def trade_dates(self) -> List[pd.Timestamp]:
        """获取与合并K线对齐的交易时间列表。"""
        self.ensure_loaded()
        return self._trade_dates

    @property
    def bi_list(self) -> List[Bi]:
        """获取笔列表。"""
        self.ensure_loaded()
        return self._bi_list

    @property
    def bi_zhongshu_list(self) -> List[ZhongShuBase]:
        """获取笔中枢列表。"""
        self.ensure_loaded()
        return self._bi_zhongshu_list

    @property
    def bi_zhongshu_in_xianduan_list(self) -> List[ZhongShuBase]:
        """获取线段内部笔中枢列表。"""
        self.ensure_loaded()
        return self._bi_zhongshu_in_xianduan_list

    @property
    def te_zheng_xu_lie_list(self) -> List[TeZhengXuLie]:
        """获取笔特征序列列表。"""
        self.ensure_loaded()
        return self._te_zheng_xu_lie

    @property
    def xian_duan_list(self) -> List[TeZhengXuLie]:
        """获取线段列表。"""
        self.ensure_loaded()
        return self._xianduan_list

    @property
    def xianduan_tezhengxulie_list(self) -> List[XianduanTeZhengXuLie]:
        """获取线段特征序列列表。"""
        self.ensure_loaded()
        return self._xianduan_tezhengxulie_list or []

    @property
    def xianduan_zhongshu_list(self) -> List[XianDuanZhongShu]:
        """获取线段中枢列表。"""
        self.ensure_loaded()
        return self._xianduan_zhongshu_list or []

    @property
    def xianduan_zhongshu_another_list(self) -> List[XianDuanZhongShu]:
        """获取补充线段中枢列表。"""
        self.ensure_loaded()
        return self._xianduan_zhongshu_another_list or []

    @property
    def fenxing_list(self) -> List[FenXing]:
        """获取分型列表"""
        self.ensure_loaded()
        return self._fenxing_list

    @classmethod
    def reset_instance(cls):
        """重置单例实例，用于切换不同的数据源"""
        if cls._instance is not None:
            # 清理资源（如果需要）
            cls._instance._raw_data = None
            cls._instance._origin_kline_data = None
            cls._instance._gaps_list = None
            cls._instance._merged_klines = None
            cls._instance._fenxing_list = None
            cls._instance._trade_dates = None
            cls._instance._bi_list = None
            cls._instance._bi_zhongshu_list = None
            cls._instance._te_zheng_xu_lie = None
            cls._instance._xianduan_list = None
            cls._instance._xianduan_zhongshu_list = None
            cls._instance._xianduan_tezhengxulie_list = None
            cls._instance._xianduan_zhongshu_another_list = None
            cls._instance._bi_zhongshu_in_xianduan_list = None
            cls._instance._chart_payload = None
            cls._instance._initialized = False
            cls._instance.special_path = None
            cls._instance = None


CACHE_DUMP_DIR = Path(settings.CACHE_DUMP_DIR)
_CHART_PAYLOAD_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_CACHE_DUMP_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def get_cache_dump_path(
    symbol: str,
    frequency: str = "freq=1day",
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
    dump_dir: Path = CACHE_DUMP_DIR,
) -> Path:
    """校验标的编码并返回_DataCache pickle路径。"""
    clean_symbol = Path(symbol).stem
    if not _CACHE_DUMP_SYMBOL_PATTERN.fullmatch(clean_symbol):
        raise ValueError(f"非法的标的数据文件名: {symbol}")

    return dump_dir / frequency / market_dir / asset_class_dir / f"{clean_symbol}.pkl"


def get_chart_payload_path(
    symbol: str,
    frequency: str = "freq=1day",
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
) -> Path:
    """校验周期和标的编码，返回图表payload文件路径。"""
    if frequency not in SUPPORTED_CHART_FREQUENCIES:
        raise ValueError(f"不支持的K线周期: {frequency}")

    clean_symbol = Path(symbol).stem
    if not _CHART_PAYLOAD_SYMBOL_PATTERN.fullmatch(clean_symbol):
        raise ValueError(f"非法的标的数据文件名: {symbol}")

    return (
        CHART_PAYLOAD_DIR
        / frequency
        / market_dir
        / asset_class_dir
        / f"{clean_symbol}.chart.pkl"
    )


def get_chart_payload_versions(
    symbol: str,
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
) -> tuple[int, ...]:
    """获取全部周期payload的修改时间，缺失周期返回0。"""
    return tuple(
        path.stat().st_mtime_ns if path.exists() else 0
        for path in (
            get_chart_payload_path(symbol, frequency, market_dir, asset_class_dir)
            for frequency in SUPPORTED_CHART_FREQUENCIES
        )
    )


def _atomic_pickle_dump(value, destination: Path) -> None:
    """通过临时文件原子写入pickle数据，避免留下半成品文件。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.name}.tmp")
    try:
        with temp_path.open("wb") as file:
            pickle.dump(value, file, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def dump_data_cache_to_pickle(
    source_file: Path,
    dump_dir: Path = CACHE_DUMP_DIR,
    frequency: str | None = None,
    dump_cache: bool = True,
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
    precision: int | None = None,
) -> Path:
    """构建图表payload并可选导出_DataCache，写入过程支持强制覆盖。"""
    source_file = Path(source_file)
    if not source_file.exists():
        raise FileNotFoundError(f"数据文件不存在: {source_file}")

    _DataCache.reset_instance()
    cache = _DataCache(source_file)
    cache.ensure_loaded()
    chart_precision = precision if precision is not None else (
        2 if asset_class_dir == "asset_class=stock" else 3
    )
    chart_payload = cache.build_chart_payload(precision=chart_precision)
    _atomic_pickle_dump(
        chart_payload,
        get_chart_payload_path(
            source_file.stem,
            frequency or source_file.parent.name,
            market_dir,
            asset_class_dir,
        ),
    )

    if not dump_cache:
        _DataCache.reset_instance()
        return get_chart_payload_path(
            source_file.stem,
            frequency or source_file.parent.name,
            market_dir,
            asset_class_dir,
        )

    destination = get_cache_dump_path(
        source_file.stem,
        frequency or "freq=1day",
        market_dir,
        asset_class_dir,
        dump_dir,
    )
    try:
        _atomic_pickle_dump(cache, destination)
    finally:
        _DataCache.reset_instance()

    return destination


def load_data_cache_pickle(
    symbol: str,
    frequency: str = "freq=1day",
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
    dump_dir: Path = CACHE_DUMP_DIR,
) -> _DataCache:
    """读取_DataCache缓存，并兼容旧版endpoints模块生成的pickle。"""
    cache_path = get_cache_dump_path(symbol, frequency, market_dir, asset_class_dir, dump_dir)
    if not cache_path.exists():
        raise FileNotFoundError(f"缓存文件不存在: {cache_path}")

    with cache_path.open("rb") as file:
        cache = pickle.load(file)

    cache_type = type(cache)
    is_legacy_cache = (
        cache_type.__name__ == _DataCache.__name__
        and cache_type.__module__.endswith(".endpoints")
        and callable(getattr(cache, "ensure_loaded", None))
    )
    if not isinstance(cache, _DataCache) and not is_legacy_cache:
        raise TypeError(f"缓存文件类型错误: {cache_type.__module__}.{cache_type.__name__}")

    return cache


def load_chart_payload(
    symbol: str,
    frequency: str = "freq=1day",
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
) -> dict:
    """读取指定标的和周期的预计算图表payload。"""
    payload_path = get_chart_payload_path(symbol, frequency, market_dir, asset_class_dir)
    with payload_path.open("rb") as file:
        payload = pickle.load(file)
    if not isinstance(payload, dict):
        raise TypeError(f"图表缓存类型错误: {type(payload).__module__}.{type(payload).__name__}")
    return payload
