import json
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Candlestick

from ..endpoints import bi_data_list
from ..endpoints import origin_kline_data, trade_date_list
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

@router.get("/Kline_base_test", response_class=HTMLResponse)
async def Kline_base_test(request: Request):
    dates = ["2017/7/{}".format(i + 1) for i in range(31)]

    c = (
    Kline()
    .add_xaxis(dates)
    .add_yaxis(
        "kline",
        data,
        markpoint_opts=opts.MarkPointOpts(data=[
                opts.MarkPointItem(
                    coord=[dates[i], data[i][1]],  # 第i天的收盘价坐标
                    name=f"收盘价 {i+1}",
                    symbol_size=10,
                    itemstyle_opts=opts.ItemStyleOpts(color="#0000FF"),
                    label_opts=opts.LabelOpts(
                        position="top",  # 标签在标记点上方
                        color="#333",
                        font_size=12,
                        formatter=f"{data[i][1]}"  # 显示收盘价数值
                    )
                ) for i in range(10)  # 仅前十根
            ])
    )
    .set_global_opts(
        title_opts=opts.TitleOpts(
            title="股票K线图",
            title_textstyle_opts=opts.TextStyleOpts(font_size=20)
        ),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=12)),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=12)),
        legend_opts=opts.LegendOpts(textstyle_opts=opts.TextStyleOpts(font_size=14))
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


# ========== Lightweight Charts 缺口显示相关API ==========

@router.get("/lightweight-charts-gap-demo", response_class=HTMLResponse)
async def lightweight_charts_gap_demo(request: Request):
    """
    Lightweight Charts 缺口显示演示页面
    """
    template = templates.env.get_template("lightweight_charts_gap_backend.html")
    html_content = template.render(
        name="lightweight_charts_gap_backend.html",
        context={"request": request}
    )
    return HTMLResponse(content=html_content)


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


@router.get("/lightweight_charts_demo", response_class=HTMLResponse)
async def lightweight_charts_demo(request: Request):
    """
    Lightweight Charts 优化版：显示K线与缠论笔
    """
    try:
        # 1. 准备 K 线数据
        sample_dates = trade_date_list
        sample_data = origin_kline_data

        candle_data = []
        for i, (date, kline) in enumerate(zip(sample_dates, sample_data)):
            candle = {
                "time": date,
                "open": float(kline.open),
                "high": float(kline.high),
                "low": float(kline.low),
                "close": float(kline.close)
            }
            candle_data.append(candle)

        # 2. 准备笔（Bi）数据 - 转换为折线图格式
        # 笔的数据点通常是顶底分型的坐标
        bi_line_data = []
        for bi in bi_data_list:
            # 如果 bi 是 Bi 对象，使用 to_dict() 方法转换
            bi_dict = bi.to_dict()
            # 起点
            bi_line_data.append({
                "time": sample_dates[bi_dict['start']],
                "value": bi_dict['start_price']
            })
            # 终点
            bi_line_data.append({
                "time": sample_dates[bi_dict['end']],
                "value": bi_dict['end_price']
            })

        logger.info(f"生成Lightweight Charts数据: {len(candle_data)}根K线, {len(bi_data_list)}笔")

        # 调试：检查模板名称类型
        template_name = "lightweight_charts_demo.html"


        # 尝试直接渲染模板
        try:
            template = templates.env.get_template(template_name)
            html_content = template.render(
                request=request,
                candle_data=json.dumps(candle_data, ensure_ascii=False),
                bi_data=json.dumps(bi_line_data, ensure_ascii=False),
                candle_count=len(candle_data)
            )
            return HTMLResponse(content=html_content)
        except Exception as render_error:
            logger.error(f"Template rendering error: {str(render_error)}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"生成Lightweight Charts数据失败: {str(e)}", exc_info=True)
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(e)}</p>", status_code=500)