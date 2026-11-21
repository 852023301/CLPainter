# 历史结果与最新行情同页工作台

## 已确认口径
用户明确否定历史截断：历史版本只选择已保存名单及增减，K 线和 MA/成交量/MACD/BOLL/RSI/缠论图层仍使用现有最新完整图表数据。禁止增加 as_of/end_date、裁剪数据、重算历史指标或修改 toolbox。

## 交互与范围
右侧增加实时选股/历史结果两个可键盘操作的标签，共用现有主图及副图。历史模式包括方案、周期、版本、分页、结果分类、数量及对比版本；名单显示版本日期，同时明确提示图表是最新完整行情。切换模式不修改实时筛选条件。
点击历史标的沿用现有图表页面加载方式，在当前标签页切换股票和方案周期，不打开新窗口；URL 携带独立历史上下文，保留版本、分类、分页和滚动位置。均线/图层/副图设置继续由原逻辑恢复，不新建第二套图表。
原 history 链接默认转换为工作台 URL；standalone=1 保留独立只读列表，兼容导出及旧展示测试。旧链接的 preset_id/frequency/run_id/view/offset 全部保留到独立 history_* 参数，不能与图表 frequency 混淆。空版本显示空态；数据读取失败不显示旧版本名单；失效图表缓存时保留历史面板并提示，允许换标的。
不改数据库表、历史内容、算法、数据流水线、依赖和部署配置，不自动部署或提交 Git。README 用户修改保持。

## 实现顺序与验收
1. 先写旧链接跳转、最新图表不截断和图表缺失的 HTTP 回归，再实现兼容入口。
2. 独立原生 JS 历史控制器 + 主模板标签/面板，离线 Node 证明加载、分类、导航上下文、滚动、空/错/乱序和实时互不干扰。
3. 必跑 cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend && python -m unittest tests.test_frontend_template；全量 python3 -m pytest -q web/backend/tests。
前端以 UTF-8 无 BOM 保持原换行；名称用 textContent 渲染。浏览器人工验证仍遵守项目权限，不替代硬门禁。

## 验证结果（2026-11-21）
- 前端硬门禁 15 tests OK，包含旧缺口/均线/图层和方案管理回归，以及新增同页历史交互测试。
- 历史 HTTP/存储测试 29 passed；实际测试证明查看 2026-11-13 的名单时，K 线及 MA/BOLL/RSI/MACD 仍包含 2026-11-20 后续数据，没有按历史版本截断。
- Node 覆盖同标签页导航、版本/分类/分页/滚动恢复、实时条件隔离、请求乱序、错误重试、空名单、键盘标签和安全文本渲染。
- 全量 pytest：447 passed、1 failed（既有 S25 / 603683SH 线段缓存与回归期望不一致），48 条第三方兼容警告；没有修改算法或放宽断言。日志 /tmp/clpainter-history-workspace-tests-20261121-final.log。
- 新 JS 语法、API F/E9 检查、历史测试 Ruff、UTF-8 无 BOM 和目标文件 git diff --check 通过。
- 未手工启动浏览器，未部署、未提交、未迁移或写入实际数据库，未运行真实数据流水线；README 原有内容保持。并行分类展示和统一数据清理改动不由本任务编辑。

## 后续授权部署记录（2026-11-21）
前文“未部署、未提交”和 447 passed / 1 failed 是初始实现阶段的历史记录，不代表下面的部署验收状态。
- 根据用户明确授权，已将本功能部署到 clpainter-test（HTTP 15001），重建并启动测试容器；生产容器保持停止。
- 部署前复跑：前端硬门禁 15 tests OK，全量 448 passed、0 failed、0 skipped。S25 验收在其他任务中已调整；本功能没有修改缠论算法或 S25 验收断言。
- 四个运行文件已固化到镜像 harbor.techfin.ai/wjl-toolkit/cl_painter:4.0；保留发布标签 history-workspace-20261121-155514 和回滚标签 pre-history-workspace-20261121-155514。
- 真实 HTTP 校验通过：旧链接 303 跳转到同页工作台、四个既有历史版本、成功空结果、增减对比、脚本内容及页面脚本解析、独立列表兼容入口。
- 查看 2026-11-19 的名单时，实测 K 线仍包含 2026-11-20；MA/BOLL/RSI/MACD/缺口接口不因历史上下文截断。
- 数据库全部表部署前后的行数及内容指纹完全一致；原分类展示和独立 Python 环境保留。未迁移数据库、未运行行情流水线、未进行浏览器人工验收。
- 部署证据与回滚命令：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-history-workspace-deploy-20261121-155514。
- 用户后续明确授权提交本轮实现、测试和记录；README.md 与 web/backend/scripts/README.md 的其他修改不纳入本轮提交，不推送远程。

## 本次 Git 提交前复跑（2026-11-21）
- 以其他任务收敛后的当前仓库基线重新验证：前端硬门禁 15 tests OK，历史 HTTP/存储 29 passed，全量 426 passed、0 failed、0 skipped，pytest 进程退出码为 0。
- 426 项与部署前的 448 项属于不同仓库基线；本次没有删减其他任务的测试、调整 S25 规则或修改任何运行代码，四个运行文件仍与已部署版本逐字节一致。
- JavaScript 语法、Python AST、作用域 Ruff F/E9、git diff --check、UTF-8 无 BOM 与凭据模式检查通过。
