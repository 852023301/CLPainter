import logging
import os
import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Grid, Line
from pyecharts.commons.utils import JsCode

from ..endpoints import trade_date_list, merge_data_list, merge_kline_data, origin_kline_data
from ...._config.logging_config import setup_logger
from ....toolbox.calculate import calculate_macd, calculate_ma

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()
appDir = os.environ.get('appDir')
templates = Jinja2Templates(directory=f"{appDir}/templates")




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
            # xaxis_index = [0, 1]的含义是[grip_index，xaxis_index]。不同副图应该对应不同index
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
                opts.DataZoomOpts(is_show=False, xaxis_index=[0, 3], range_end=100),
            ],
        )
    )

    kline_merged = (
        Kline()
        .add_xaxis(trade_date_list)
        .add_yaxis("Merged_Price", merge_kline_data,
                   xaxis_index=1,
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

    close = pd.DataFrame(origin_kline_data).iloc[:, 1]

    line_ma = (
        Line()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(
            series_name="MA5",
            y_axis=calculate_ma(close,day_count=5),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(opacity=0.5),
            label_opts=opts.LabelOpts(is_show=False),
            color="#000000",
            is_symbol_show=False,  # 不显示端点
        )
        .add_yaxis(
            series_name="MA8",
            y_axis=calculate_ma(close, day_count=8),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(opacity=0.5),
            label_opts=opts.LabelOpts(is_show=False),
            color="#FFA500",
            is_symbol_show=False,
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
                # axislabel_opts=opts.LabelOpts(is_show=True),
            ),
            legend_opts=opts.LegendOpts(
                selected_map={
                    "MA8": False,
                }
            ),
        )
    )

    # Overlap Kline + Line
    overlap_kline_line = kline_origin.overlap(line_ma)

    bar_volume = (
        Bar()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(
            series_name="volume",
            y_axis=[data.volume for data in merge_data_list],
            xaxis_index=2,
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

    macd_data = calculate_macd(close)
    bar_macd = (
        Bar()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(
            series_name="MACD",
            y_axis=macd_data["MACD_Hist"],
            xaxis_index=3,
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(
                color=JsCode(
                    """
                        function(params) {
                            var colorList;
                            if (params.data >= 0) {
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
            yaxis_opts=opts.AxisOpts(
                split_number=4,
                axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                axistick_opts=opts.AxisTickOpts(is_show=False),
                splitline_opts=opts.SplitLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(is_show=True),
            ),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )

    line_macd = (
        Line()
        .add_xaxis(xaxis_data=trade_date_list)
        .add_yaxis(  # 这段代码的color设置在add_yaxis的color属性不生效，必须放在LineStyleOpts中，而且不会改变图例的颜色
            series_name="DIF",
            y_axis=macd_data["DIF"],
            xaxis_index=3,
            label_opts=opts.LabelOpts(is_show=False),
            is_symbol_show=False,
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(opacity=1,color="#000000",),
        )
        .add_yaxis(
            series_name="DEA",
            y_axis=macd_data["DEA"],
            xaxis_index=3,
            label_opts=opts.LabelOpts(is_show=False),
            linestyle_opts=opts.LineStyleOpts(opacity=1, color="#FFA500", ),
            is_symbol_show=False,
            is_smooth=True,

        )

        .set_global_opts(legend_opts=opts.LegendOpts(is_show=False))
    )

    # 最下面的MACD
    overlap_bar_line_macd = bar_macd.overlap(line_macd)

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
                   grid_opts=opts.GridOpts(pos_left="3%", pos_right="1%", height="60%"), )

    # volume 柱状图
    grid_chart.add(bar_volume,
                   grid_opts=opts.GridOpts(
                       pos_left="3%", pos_right="1%", pos_top="71%", height="5%"
                   ),
                   )

    grid_chart.add(
        kline_merged,
        grid_opts=opts.GridOpts(
            pos_left="3%", pos_right="1%", pos_top="77%", height="12%"
        ), )

    # MACD DIFS DEAS
    grid_chart.add(
        overlap_bar_line_macd,
        grid_opts=opts.GridOpts(
            pos_left="3%", pos_right="1%", pos_top="90%", height="8%"
        ),
    )

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "chart": grid_chart.render_embed()}
    )
