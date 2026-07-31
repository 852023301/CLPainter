"""
使用 tushare 读取行情数据(均为不复权/原始价格), 输出与原 tdata 版本完全一致的 .pkl 数据集.

每个 .pkl 内容为 [[date_str, open, close, low, high, volume], ...]:
  - 个股  : all_stocks/<code>.pkl   精度 2 位
  - 指数  : all_index/<code>.pkl    不四舍五入
  - ETF   : all_etf/<code>.pkl      精度 3 位

需要环境变量:
  - TUSHARE_TOKEN : tushare pro 接口 token

标的清单与起始日期均从 tushare 获取, 不再依赖内网 MySQL.

说明:
  - 全部使用 tushare 的 daily / index_daily / fund_daily 接口, 这些接口返回
    不复权(原始)价格; 如需前/后复权请改用 pro_bar(adj="qfq"/"hfq").
"""
import os
import pickle
from pathlib import Path

import pandas as pd
import tushare as ts

from CLPainter.web.backend.app._config.settings import settings


def _get_pro():
    """初始化并返回 tushare pro 接口 (token 从环境变量 TUSHARE_TOKEN 读取)."""
    token = os.getenv("TUSHARE_TOKEN", "ac46d24be66cf2ed037f517378d67874e8294eaf5908f39af23d04f5")
    if not token:
        raise EnvironmentError("环境变量 'TUSHARE_TOKEN' 未设置")
    ts.set_token(token)
    return ts.pro_api()


# 内部 K 线字段顺序: open, close, low, high, volume (与原 tdata 版本一致)
_KLINE_COLS = ["open", "close", "low", "high", "vol"]


def _to_kline_rows(df: pd.DataFrame, precision=None, validate=True):
    """
    将 tushare 日线 DataFrame 转为 [[date, open, close, low, high, volume], ...].

    - trade_date(YYYYMMDD) -> "YYYY-MM-DD", 按日期升序
    - validate=True 时, 价格(open/close/low/high)存在 NaN 或 0 则跳过该标的(返回 None, 与原个股/ETF 逻辑一致)
    - precision 非 None 时对全部数值字段(含成交量)四舍五入
    """
    if df is None or len(df) == 0:
        return []
    df = df.sort_values("trade_date").reset_index(drop=True)
    if validate:
        prices = df[["open", "close", "low", "high"]]
        if prices.isna().any().any() or (prices == 0).any().any():
            return None
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    out = df[["trade_date", *_KLINE_COLS]]
    if precision is not None:
        out = out.copy()
        for col in _KLINE_COLS:
            out[col] = out[col].astype(float).round(precision)
    return out.values.tolist()


def _save(final_list, file_name, dsc_path, keep):
    """写入单个 .pkl, 并登记到 keep 字典供后续清理."""
    with open(Path(dsc_path, file_name), "wb") as fi:
        pickle.dump(final_list, fi)
    keep[file_name] = 1


def _cleanup_dir(dsc_path, keep):
    """删除 dsc_path 下未被 keep 登记的旧 .pkl."""
    for f in os.listdir(dsc_path):
        if keep.get(f) is None:
            os.remove(os.path.join(dsc_path, f))


def _process_symbols(pro, fetch_fn, info_dict, dsc_path, precision=None, validate=True):
    """
    通用流程: 遍历标的清单, 调用 fetch_fn(pro, code, start_date) 取日线,
    转换后落盘, 最后清理过期文件.

    Args:
        pro: tushare pro 接口
        fetch_fn: (pro, code, start_date) -> DataFrame; start_date 为 "YYYYMMDD" 或 None
        info_dict: {code: start_date("YYYY-MM-DD")}
        dsc_path: 输出目录
        precision: 数值精度, None 表示不四舍五入
        validate: 是否校验价格(个股/ETF 校验, 指数不校验, 与原逻辑一致)
    """
    keep = {}
    for code, start_date in info_dict.items():
        sd = start_date.replace("-", "") if start_date else None
        df = fetch_fn(pro, code, sd)
        rows = _to_kline_rows(df, precision=precision, validate=validate)
        if not rows:
            continue
        file_name = f"{code.replace('.', '')}.pkl"
        _save(rows, file_name, dsc_path, keep)
    _cleanup_dir(dsc_path, keep)


if __name__ == "__main__":
    pro = _get_pro()

    #########################################
    # 个股
    stock_df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,list_date')
    stock_df = stock_df.dropna(subset=['list_date'])
    stock_info_dict = dict(
        zip(stock_df['ts_code'], pd.DatetimeIndex(stock_df['list_date']).strftime("%Y-%m-%d")))

    _process_symbols(pro, lambda p, c, s: p.daily(ts_code=c, start_date=s),  # 不复权
                     stock_info_dict, Path(settings.DATA_DIR, "all_stocks"), precision=2)

    #########################################
    # 指数
    index_map = {
        "hs300": "000300.SH",
        "zz500": "000905.SH",
        "zz1000": "000852.SH",
        "cybz": "399006.SZ",
        "zz985": "000985.SH",
        "kc50": "000688.SH",
        "szzs": "000001.SH",
        "sz50": "000016.SH",
        "szcz": "399001.SZ",
        "gz2000": "399303.SZ",
        "zz2000": "932000.SH",
        "zzhl": "000922.SH",
        "a500": "000510.SH",
        "kczz": "000680.SH",
    }
    index_df = pro.index_basic(fields='ts_code,list_date')
    index_df = index_df.dropna(subset=['list_date'])
    index_info_dict = dict(
        zip(index_df['ts_code'], pd.DatetimeIndex(index_df['list_date']).strftime("%Y-%m-%d")))
    # index_map 的 key 是内部别名, value 才是 tushare ts_code; 用 value 作为索引
    index_dict = {code: index_info_dict.get(code) for code in index_map.values()}

    _process_symbols(pro, lambda p, c, s: p.index_daily(ts_code=c, start_date=s),  # 指数, 不复权
                     index_dict, Path(settings.DATA_DIR, "all_index"), validate=False)

    #########################################
    # etf
    etf_df = pro.fund_basic(market='E', fields='ts_code,list_date')
    etf_df = etf_df.dropna(subset=['list_date'])
    etf_info_dict = dict(
        zip(etf_df['ts_code'], pd.DatetimeIndex(etf_df['list_date']).strftime("%Y-%m-%d")))

    _process_symbols(pro, lambda p, c, s: p.fund_daily(ts_code=c, start_date=s),  # ETF, 不复权
                     etf_info_dict, Path(settings.DATA_DIR, "all_etf"), precision=3)

    # 容器内拷贝示例:
    #   docker cp <local>/all_stocks CLPainter:/root/CLPainter/web/backend/app/data_set/
    #   docker cp <local>/all_index CLPainter:/root/CLPainter/web/backend/app/data_set/
    #   docker cp <local>/all_etf   CLPainter:/root/CLPainter/web/backend/app/data_set/
