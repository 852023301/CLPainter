import logging
import requests
import os
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Candlestick

from pyecharts import options as opts

from ...._config.logging_config import setup_logger
from ..endpoints import get_data_init_set

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()
appDir = os.environ.get('appDir')
templates = Jinja2Templates(directory=f"{appDir}/templates")


@router.get("/test1")
def test1() -> str:
    logger.info("test1_info")
    logger.debug("test1_debug")

    return "test1"


# 模拟数据生成
def generate_data():
    return [120, 200, 150, 80, 70, 110, 130]


@router.get("/test2", response_class=HTMLResponse)
async def test2(request: Request):
    bar = (
        Bar()
        .add_xaxis(["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
        .add_yaxis("销量", generate_data())
        .set_global_opts(title_opts=opts.TitleOpts(title="周销售数据"))
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": bar.render_embed()}
    )


data = [
     # 开 收 低 高
    [2320.26, 2320.26, 2287.3, 2362.94],
    [2300, 2291.3, 2288.26, 2308.38],
    [2295.35, 2346.5, 2295.35, 2345.92],
    [2347.22, 2358.98, 2337.35, 2363.8],
    [2360.75, 2382.48, 2347.89, 2383.76],
    [2383.43, 2385.42, 2371.23, 2391.82],
    [2377.41, 2419.02, 2369.57, 2421.15],
    [2425.92, 2428.15, 2417.58, 2440.38],
    [2411, 2433.13, 2403.3, 2437.42],
    [2432.68, 2334.48, 2427.7, 2441.73],
    [2430.69, 2418.53, 2394.22, 2433.89],
    [2416.62, 2432.4, 2414.4, 2443.03],
    [2441.91, 2421.56, 2418.43, 2444.8],
    [2420.26, 2382.91, 2373.53, 2427.07],
    [2383.49, 2397.18, 2370.61, 2397.94],
    [2378.82, 2325.95, 2309.17, 2378.82],
    [2322.94, 2314.16, 2308.76, 2330.88],
    [2320.62, 2325.82, 2315.01, 2338.78],
    [2313.74, 2293.34, 2289.89, 2340.71],
    [2297.77, 2313.22, 2292.03, 2324.63],
    [2322.32, 2365.59, 2308.92, 2366.16],
    [2364.54, 2359.51, 2330.86, 2369.65],
    [2332.08, 2273.4, 2259.25, 2333.54],
    [2274.81, 2326.31, 2270.1, 2328.14],
    [2333.61, 2347.18, 2321.6, 2351.44],
    [2340.44, 2324.29, 2304.27, 2352.02],
    [2326.42, 2318.61, 2314.59, 2333.67],
    [2314.68, 2310.59, 2296.58, 2320.96],
    [2309.16, 2286.6, 2264.83, 2333.29],
    [2282.17, 2263.97, 2253.25, 2286.33],
    [2255.77, 2270.28, 2253.31, 2276.22],
]


@router.get("/Kline_base", response_class=HTMLResponse)
async def Kline_base(request: Request):
    c = (
        Kline(init_opts=opts.InitOpts(width='100%', height='100%'))
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis("kline", data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(is_scale=True),
            title_opts=opts.TitleOpts(title="Kline-基本示例"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )

@router.get("/Kline_base_merged", response_class=HTMLResponse)
async def Kline_base_merged(request: Request):
    def merge_data():
        response = requests.get(
            url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
        )
        origin_klines = json_response = get_data_init_set

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

            @property
            def is_contained(self):
                return self._is_contained

            @is_contained.setter
            def is_contained(self, value):
                self._is_contained = value

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

    merge_data_list = merge_data()
    merge_kline_data = [[data.merged_low if data.close > data.open else data.merged_high,
                         data.merged_high if data.close > data.open else data.merged_low,
                         data.merged_low, data.merged_high] for data in merge_data_list]

    trade_date_list = [data.trade_date for  data in merge_data_list ]

    c = (
        Kline(init_opts=opts.InitOpts(width='100%', height='100%'))
        .add_xaxis(trade_date_list)
        .add_yaxis("kline", merge_kline_data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            title_opts=opts.TitleOpts(title="Kline-merged"),
            datazoom_opts=[
                opts.DataZoomOpts(
                    is_show=False,
                    type_="inside",
                ),
                opts.DataZoomOpts(
                    is_show=True,
                    pos_top="85%",
                    type_="slider",
                ),
            ],
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_split_area", response_class=HTMLResponse)
async def Kline_split_area(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis("kline", data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            title_opts=opts.TitleOpts(title="Kline-显示分割区域"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_datazoom_slider", response_class=HTMLResponse)
async def Kline_datazoom_slider(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis("kline", data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            datazoom_opts=[opts.DataZoomOpts()],
            title_opts=opts.TitleOpts(title="Kline-DataZoom-slider"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_datazoom_inside", response_class=HTMLResponse)
async def Kline_datazoom_inside(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis("kline", data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            datazoom_opts=[opts.DataZoomOpts(type_="inside")],
            title_opts=opts.TitleOpts(title="Kline-DataZoom-inside"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_datazoom_slider_position", response_class=HTMLResponse)
async def Kline_datazoom_slider_position(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis("kline", data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            datazoom_opts=[opts.DataZoomOpts(pos_bottom="-2%")],
            title_opts=opts.TitleOpts(title="Kline-DataZoom-slider-Position"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_itemstyle", response_class=HTMLResponse)
async def Kline_itemstyle(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis(
            "kline",
            data,
            itemstyle_opts=opts.ItemStyleOpts(
                color="#ec0000",
                color0="#00da3c",
                border_color="#8A0000",
                border_color0="#008F28",
            ),
        )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            datazoom_opts=[opts.DataZoomOpts(type_="inside")],
            title_opts=opts.TitleOpts(title="Kline-ItemStyle"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Basic_candlestick", response_class=HTMLResponse)
async def Basic_candlestick(request: Request):
    x_data = ["2017-10-24", "2017-10-25", "2017-10-26", "2017-10-27"]
    y_data = [[20, 30, 10, 35], [40, 35, 30, 55], [33, 38, 33, 40], [40, 40, 32, 42]]
    c = (
        Candlestick()
        .add_xaxis(xaxis_data=x_data)
        .add_yaxis(series_name="", y_axis=y_data)
        .set_series_opts()
        .set_global_opts(
            yaxis_opts=opts.AxisOpts(
                splitline_opts=opts.SplitLineOpts(
                    is_show=True, linestyle_opts=opts.LineStyleOpts(width=1)
                )
            )
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )


@router.get("/Kline_markline", response_class=HTMLResponse)
async def Kline_markline(request: Request):
    c = (
        Kline()
        .add_xaxis(["2017/7/{}".format(i + 1) for i in range(31)])
        .add_yaxis(
            "kline",
            data,
            markline_opts=opts.MarkLineOpts(
                data=[opts.MarkLineItem(type_="max", value_dim="close")]
            ),
        )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            title_opts=opts.TitleOpts(title="Kline-MarkLine"),
        )
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": c.render_embed()}
    )