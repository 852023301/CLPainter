import json
import logging

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..endpoints import load_data_cache_pickle
from ....toolbox.calculate import calculate_boll_list, calculate_macd_indicator, calculate_ma_colors, calculate_ma_list, \
    calculate_rsi_list

# 默认显示的 MA 窗口期(均线种类由这个全局变量完全控制)
DEFAULT_MA_PERIODS = [5, 8, 10, 13, 21, 34, 55, 60, 89, 120, 144, 233, 250]

from ...._config.logging_config import setup_logger
from ...._config.settings import settings

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()

# 调试：打印模板目录路径
template_dir = f"{settings.APP_DIR}/templates"

templates = Jinja2Templates(directory=template_dir)
# 禁用模板缓存以避免 unhashable type 错误
templates.env.cache = None


@router.get("/lightweight_charts_demo", response_class=HTMLResponse)
async def lightweight_charts_demo(request: Request, symbol: str = "600713SH", precision: int = 2):
    """
    Lightweight Charts 优化版：显示K线与缠论笔
    
    Args:
        request: FastAPI 请求对象
        precision: 价格显示精度（小数位数），默认2位，范围0-6
    """
    # 限制精度范围
    precision = max(0, min(6, precision))

    periods = list(DEFAULT_MA_PERIODS)
    ma_colors = calculate_ma_colors(periods)

    try:
        # 1. 准备 K 线数据
        cache = load_data_cache_pickle(symbol)
        sample_dates = cache.trade_dates
        sample_data = cache.origin_kline_data
        sample_gaps = cache.gaps_list

        candle_data = []
        for kline in sample_data:
            candle = {
                "time": kline.trade_datetime,
                "open": float(kline.open),
                "high": float(kline.high),
                "low": float(kline.low),
                "close": float(kline.close)
            }
            candle_data.append(candle)

        # 2. 准备笔（Bi）数据 - 转换为折线图格式
        # 笔的数据点通常是顶底分型的坐标
        bi_line_data = []
        for bi in cache.bi_list:
            # 如果 bi 是 Bi 对象，使用 to_dict() 方法转换
            bi_dict = bi.to_dict()
            # 起点
            bi_line_data.append({
                "time": sample_dates[bi_dict['start_idx']],
                "value": bi_dict['start_price']
            })
            # 终点
            bi_line_data.append({
                "time": sample_dates[bi_dict['end_idx']],
                "value": bi_dict['end_price']
            })

        # 2.5 准备线段（XianDuan）数据 - 转换为折线图格式
        xd_line_data = []
        for xd in cache.xian_duan_list:
            xd_dict = xd.to_dict()
            xd_line_data.append({
                "time": sample_dates[xd_dict['start_idx']],
                "value": xd_dict['start_price']
            })
            xd_line_data.append({
                "time": sample_dates[xd_dict['end_idx']],
                "value": xd_dict['end_price']
            })

        zhongshu_data = [
            {
                "start_time": zhongshu.start_time,
                "end_time": zhongshu.end_time,
                "high_price": float(zhongshu.high_price),
                "low_price": float(zhongshu.low_price),
            }
            for zhongshu in cache.bi_zhongshu_list
        ]

        zhongshu_in_xianduan_data = [
            {
                "start_time": zhongshu.start_time,
                "end_time": zhongshu.end_time,
                "high_price": float(zhongshu.high_price),
                "low_price": float(zhongshu.low_price),
            }
            for zhongshu in cache.bi_zhongshu_in_xianduan_list
        ]

        xianduan_zhongshu_data = [
            {
                "start_time": zhongshu.start_time,
                "end_time": zhongshu.end_time,
                "high_price": float(zhongshu.high_price),
                "low_price": float(zhongshu.low_price),
            }
            for zhongshu in cache.xianduan_zhongshu_list
        ]

        xianduan_zhongshu_another_data = [
            {
                "start_time": zhongshu.start_time,
                "end_time": zhongshu.end_time,
                "high_price": float(zhongshu.high_price),
                "low_price": float(zhongshu.low_price),
            }
            for zhongshu in cache.xianduan_zhongshu_another_list
        ]

        # 3.成交量数据
        volume_data = [
            {
                'time': kline.trade_datetime,
                'value': kline.volume,
                'color': '#ef5350' if kline.is_up() else '#26a69a'
            }
            for kline in sample_data
        ]

        logger.info(f"生成Lightweight Charts数据: {len(candle_data)}根K线, {len(cache.bi_list)}笔")

        # 调试：检查模板名称类型
        # 计算多条 MA 线(后端 pandas, 支撑万根 K 线)
        close_series = pd.Series(
            [kline.close for kline in sample_data],
            index=[kline.trade_datetime for kline in sample_data],
        )
        ma_list_raw = calculate_ma_list(close_series, periods)
        ma_list = [
            {"key": f"MA{item['period']}", "label": f"MA{item['period']}", "color": ma_colors[i],
             "values": item["values"]}
            for i, item in enumerate(ma_list_raw)
        ]
        boll_list_raw = calculate_boll_list(close_series)
        # BOLL 固定配色: 青/紫/深青 —— 与 MACD(橙+蓝)、RSI(粉/绿/棕) 互不冲突
        boll_colors = ["#26A69A", "#AB47BC", "#00796B"]
        boll_list = [
            {"key": item["key"], "label": item["key"], "color": boll_colors[i], "values": item["values"]}
            for i, item in enumerate(boll_list_raw)
        ]
        rsi_list_raw = calculate_rsi_list(close_series)
        # RSI 固定配色: 粉/绿/棕 —— 三色高区分度, 不与 MACD/BOLL 撞色
        rsi_colors = ["#E91E63", "#4CAF50", "#795548"]
        rsi_list = [
            {"key": item["key"], "label": item["key"], "color": rsi_colors[i], "values": item["values"]}
            for i, item in enumerate(rsi_list_raw)
        ]
        macd_indicator = calculate_macd_indicator(close_series, precision=precision)
        template_name = "lightweight_charts_demo.html"

        # 尝试直接渲染模板
        try:
            template = templates.env.get_template(template_name)
            html_content = template.render(
                request=request,
                candle_data=json.dumps(candle_data, ensure_ascii=False),
                bi_data=json.dumps(bi_line_data, ensure_ascii=False),
                xd_data=json.dumps(xd_line_data, ensure_ascii=False),
                zhongshu_data=json.dumps(zhongshu_data, ensure_ascii=False),
                zhongshu_in_xianduan_data=json.dumps(zhongshu_in_xianduan_data, ensure_ascii=False),
                xianduan_zhongshu_data=json.dumps(xianduan_zhongshu_data, ensure_ascii=False),
                xianduan_zhongshu_another_data=json.dumps(
                    xianduan_zhongshu_another_data, ensure_ascii=False
                ),
                candle_count=len(candle_data),
                gaps_data=json.dumps([i.to_kwargs() for i in sample_gaps], ensure_ascii=False),
                volume_data=json.dumps(volume_data, ensure_ascii=False),
                precision=precision,
                ma_data=json.dumps(ma_list, ensure_ascii=False),  # 传递精度参数到模板
                boll_data=json.dumps(boll_list, ensure_ascii=False),
                rsi_data=json.dumps(rsi_list, ensure_ascii=False),
                macd_data=json.dumps(macd_indicator, ensure_ascii=False),
            )
            return HTMLResponse(content=html_content)
        except Exception as render_error:
            logger.error(f"Template rendering error: {str(render_error)}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"生成Lightweight Charts数据失败: {str(e)}", exc_info=True)
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(e)}</p>", status_code=500)
