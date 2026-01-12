import logging
import os
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Candlestick

from pyecharts import options as opts
from ...._config.logging_config import setup_logger

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
        Kline()
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