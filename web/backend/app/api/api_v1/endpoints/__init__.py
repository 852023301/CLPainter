import os
import pickle
from pathlib import Path
from typing import List

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.toolbox.bi import generate_bi, Bi
from CLPainter.web.backend.app.toolbox.fenxing import generate_fenxing, FenXing
from CLPainter.web.backend.app.toolbox.tezhengxulie import generate_te_zheng_xu_lie, TeZhengXuLie
from CLPainter.web.backend.app.toolbox.xianduan import generate_xian_duan, XianDuan
from CLPainter.web.backend.app.toolbox.merged_kline import generate_merge_klines, find_top_bottom, MergedKLine
from CLPainter.web.backend.app.toolbox.origin_kline import OriginKLine, generate_origin_klines
from CLPainter.web.backend.app.toolbox.gap import Gap


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
        data_file = Path(settings.DATA_DIR) / "all_index/000001SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_etf/561980SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_etf/159816SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_etf/159831SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_stocks/000001SZ.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_stocks/600703SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_stocks/000011SZ.pkl"
        data_file = Path(settings.DATA_DIR) / "all_stocks/600499SH.pkl"
        # data_file = Path(settings.DATA_DIR) / "all_stocks/603533SH.pkl"

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

    def __new__(cls, special_path=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls.special_path = special_path
        return cls._instance

    def __init__(self, special_path=None):
        if self._initialized:
            return

        self._raw_data = None
        self._origin_kline_data = None
        self._gaps_list = None
        self._merged_klines = None
        self._fenxing_list = None
        self._trade_dates = None
        self._bi_list = None
        self._te_zheng_xu_lie = None
        self._xianduan_list = None
        self._initialized = True

    def ensure_loaded(self):
        """确保数据已加载"""
        if self._raw_data is not None:
            return

        # 加载原始数据
        self._raw_data = load_raw_data(self.special_path)
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

        self._te_zheng_xu_lie = generate_te_zheng_xu_lie(self._bi_list)

        self._xianduan_list = generate_xian_duan(self._te_zheng_xu_lie, self._bi_list)

        self._trade_dates = [data.trade_datetime for data in merged_klines]

    @property
    def raw_data(self) -> List[List]:
        self.ensure_loaded()
        return self._raw_data

    @property
    def origin_kline_data(self) -> List[OriginKLine]:
        self.ensure_loaded()
        return self._origin_kline_data

    @property
    def gaps_list(self) -> List[Gap]:
        self.ensure_loaded()
        return self._gaps_list

    @property
    def merged_klines(self) -> List[MergedKLine]:
        self.ensure_loaded()
        return self._merged_klines

    @property
    def trade_dates(self) -> List[str]:
        self.ensure_loaded()
        return self._trade_dates

    @property
    def bi_list(self) -> List[Bi]:
        self.ensure_loaded()
        return self._bi_list

    @property
    def te_zheng_xu_lie_list(self) -> List[TeZhengXuLie]:
        self.ensure_loaded()
        return self._te_zheng_xu_lie

    @property
    def xian_duan_list(self) -> List[TeZhengXuLie]:
        self.ensure_loaded()
        return self._xianduan_list

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
            cls._instance._te_zheng_xu_lie = None
            cls._instance._xianduan_list = None
            cls._instance._initialized = False
            cls._instance.special_path = None
            cls._instance = None


# 创建全局数据缓存实例


_data_cache = _DataCache()

# 以下代码用于集体测试
all_stocks = sorted(Path(settings.DATA_DIR, "all_stocks").iterdir(), key=lambda p: p.name)
all_etf = sorted(Path(settings.DATA_DIR, "all_etf").iterdir(), key=lambda p: p.name)
all_index = sorted(Path(settings.DATA_DIR, "all_index").iterdir(), key=lambda p: p.name)

# 测试
# for target in [all_stocks, all_etf, all_index]:
#     # _data_cache = _DataCache(target)
#     for i, stk_p in enumerate(target):
#         if stk_p.name in  ['159816SZ.pkl']:
#             continue
#         print(f"{i}:{stk_p}")
#         _data_cache = _DataCache(stk_p)
#         # 强制加载数据以验证
#         _ = _data_cache.raw_data
#         # 重置单例以便下一个股票使用
#         _DataCache.reset_instance()


# 保持向后兼容的接口
def get_data_init() -> List[List]:
    """获取原始数据（向后兼容）"""
    return _data_cache.raw_data


def get_merge_data_list() -> List[MergedKLine]:
    """获取合并后的K线数据（向后兼容）"""
    return _data_cache.merged_klines


def get_fenxing_list() -> List[FenXing]:
    """获取分型列表"""
    return _data_cache.fenxing_list


# 导出变量（保持向后兼容）
get_data_init_set = _data_cache.raw_data
merge_data_list = _data_cache.merged_klines
fenxing_data_list = _data_cache.fenxing_list
trade_date_list = _data_cache.trade_dates
origin_kline_data = _data_cache.origin_kline_data
bi_data_list = _data_cache.bi_list
te_zheng_xu_lie_list = _data_cache.te_zheng_xu_lie_list
xian_duan_list = _data_cache.xian_duan_list
gaps_list = _data_cache.gaps_list
