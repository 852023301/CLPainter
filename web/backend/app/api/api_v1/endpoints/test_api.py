import logging
import requests
import os
from typing import List, Union
import pandas as pd
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Candlestick, Grid, Line
from pyecharts.commons.utils import JsCode

from pyecharts import options as opts

from ...._config.logging_config import setup_logger
from ..endpoints import get_data_init_set, trade_date_list, merge_data_list, merge_kline_data, origin_kline_data

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

def calculate_ma(day_count: int):
    result: List[Union[float, str]] = []

    for i in range(len(trade_date_list)):
        if i < day_count:
            result.append("-")
            continue
        sum_total = 0.0
        for j in range(day_count):
            sum_total += float(origin_kline_data[i - j][1])
        result.append(abs(float("%.2f" % (sum_total / day_count))))
    return result


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
    kline_origin = (
        Kline(init_opts=opts.InitOpts(width='100%', height='100%'))
        .add_xaxis(trade_date_list)
        .add_yaxis("Price", origin_kline_data)
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(type_="category",
                                     is_scale=True,
                                     min_="dataMin",
                                     max_="dataMax",
                                     ),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross",
                background_color="rgba(245, 245, 245, 0.8)",
                border_width=1,
                border_color="#ccc",
                textstyle_opts=opts.TextStyleOpts(color="#000"),
            ),  # 提示框
            title_opts=opts.TitleOpts(title="Kline-merged"),
            datazoom_opts=[
                opts.DataZoomOpts(
                    is_show=False,
                    type_="inside",
                    xaxis_index=[0, 0],
                    range_end=100
                ),
                opts.DataZoomOpts(
                    is_show=True,
                    xaxis_index=[0, 1],
                    pos_top="65%",
                    # pos_bottom="95%",
                    type_="slider",
                    range_end=100
                ),
                opts.DataZoomOpts(is_show=False, xaxis_index=[0, 2], range_end=100),
            ],
        )
    )

    kline_merged = (
        Kline()
        .add_xaxis(trade_date_list)
        .add_yaxis("Merged_Price", merge_kline_data,
                   xaxis_index=1,
                   yaxis_index=1,
                   )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True,
                                     type_="category",
                                     axislabel_opts=opts.LabelOpts(is_show=False),
                                     ),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
            ),
            legend_opts=opts.LegendOpts(is_show=False),


        )
    )

    kline_ma= (
        Line()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(
            series_name="MA5",
            y_axis=calculate_ma(day_count=5),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(opacity=0.5),
            label_opts=opts.LabelOpts(is_show=False),
        )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axislabel_opts=opts.LabelOpts(is_show=False),
            ),
            yaxis_opts=opts.AxisOpts(
                split_number=3,
                axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                axistick_opts=opts.AxisTickOpts(is_show=False),
                splitline_opts=opts.SplitLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(is_show=True),
            ),
        )
    )

    # Overlap Kline + Line
    overlap_kline_line = kline_origin.overlap(kline_ma)

    bar_volume = (
        Bar()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(
            series_name="volume",
            y_axis=[data.volume for data in merge_data_list],
            xaxis_index=1,
            yaxis_index=1,
            label_opts=opts.LabelOpts(is_show=False),
            # 根据 echarts demo 的原版是这么写的
            # itemstyle_opts=opts.ItemStyleOpts(
            #     color=JsCode("""
            #     function(params) {
            #         var colorList;
            #         if (data.datas[params.dataIndex][1]>data.datas[params.dataIndex][0]) {
            #           colorList = '#ef232a';
            #         } else {
            #           colorList = '#14b143';
            #         }
            #         return colorList;
            #     }
            #     """)
            # )
            # 改进后在 grid 中 add_js_funcs 后变成如下
            itemstyle_opts=opts.ItemStyleOpts(
                color=JsCode(
                    """
                function(params) {
                    var colorList;
                    if (barData[params.dataIndex][1] > barData[params.dataIndex][0]) {
                        colorList = '#ef232a';
                    } else {
                        colorList = '#14b143';
                    }
                    return colorList;
                }
                """
                )
            ),
        )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axislabel_opts=opts.LabelOpts(is_show=False),
            ),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )

    grid_chart = Grid(
        init_opts=opts.InitOpts(
            width="100%",
            height="100%",
            animation_opts=opts.AnimationOpts(animation=False),
        )
    )

    # 这个是为了把 volume 这个数据写入到 html 中,还没想到怎么跨 series 传值
    # demo 中的代码也是用全局变量传的
    grid_chart.add_js_funcs("var barData = {}".format(origin_kline_data))

    grid_chart.add(overlap_kline_line,
                   grid_opts=opts.GridOpts(pos_left="3%", pos_right="1%", height="60%"),)

    # volume 柱状图
    grid_chart.add(bar_volume,
                   grid_opts=opts.GridOpts(
                       pos_left="3%", pos_right="1%", pos_top="71%", height="5%"
                   ),
                   )

    grid_chart.add(
        kline_merged,
        grid_opts=opts.GridOpts(
            pos_left="3%", pos_right="1%", pos_top="77%", height="14%"
        ),)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": grid_chart.render_embed()}
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
