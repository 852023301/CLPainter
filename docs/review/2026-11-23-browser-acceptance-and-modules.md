# 真实浏览器验收与前端模块拆分（2026-11-23，侧对话）

## 授权与范围
用户要求继续优化真实浏览器验收空白、模块拆分不完整，并部署到测试。使用隔离 Chromium/Playwright，不接用户日常浏览器；真实方案、自选和归档只读，所有非查询写接口在测试浏览器阻断。不发送主对话消息、不使用子代理、不操作 Git、不改算法、数据或部署配置。

## 分片计划
1. 真实 Chromium 基线：1440/1024/390/320px、焦点、选股/历史、图表交互、跨标签持久化、故障取消、浏览器 trace 与循环稳定性。
2. 独立移动布局修复：390px 标的标题宽度 0、查询结果区仅 9px（16 个结果）。只调整移动媒体查询，再冻结拆分前参考。
3. 原位置 Jinja include 分别提取请求、选股、指标模块；原始 JavaScript 展开后必须逐字节一致，不引入新前端请求、ESM 或框架；同步模板依赖缓存，保留全部回归。
4. 前端硬门禁、全量测试、候选隔离浏览器验收与保护文件检查。以当前测试容器为基底发布，部署后真实浏览器复验、业务数据库指纹不变。

## 基线
Chromium 130.0.6723.31，独立上下文，桌面 1440/1024 和移动模拟 390/320 页面均 HTTP 200，无未捕获页面异常或正常流程控制台错误、无整页横向溢出。手机截图与真实几何发现上述两个布局缺陷。以上为修改前基线，RED 记录保留在本任务证据目录。

## 已完成的独立布局修复
- 手机 390/320px：标题被挤为宽度 0；平板 1024px 也有同类问题。通过标题/搜索换行、标题弹性基准修复，当前案例标题约 179px。
- 真实查询返回 16 个结果，但手机列表仅 9px（内容高度为零）；移动实时面板增加可用高度，筛选区至少 120px、结果区至少 160px，实测结果区约 169px。
- 布局行为修复先建立独立参考，模块拆分相对修复后的参考做零差异验证。原生较短自动化点击间隔曾只留下绘图预览，现按完成提示与跨页恢复断言验收，失败证据保留；菜单首项是全选，焦点断言按真实第一个可用复选框校验。

## 模块拆分与缓存
- 新增 _frontend_requests.js（39 行）、_screener_workspace.js（635 行）、_chart_indicators.js（559 行），原位置 Jinja 组合，不增加浏览器请求、打包依赖、ESM 或全局作用域变化。
- 主模板从 5,171 行/225,593 字节降为 3,958 行/158,543 字节；这是维护性改善，组合后包含相同 JavaScript，不冒称传输大小或运行速度同比降低。
- 每片提取后展开源码逐字节一致；片段不含尾部换行，原分隔换行留主模板。最终参考 pre-split-reference-v2.html 包含明确的平板 CSS 修复，初始参考与失败记录保留。
- Python API 只补三个片段的模板缓存依赖，无其他业务变化；新增回归覆盖片段变动后的 HTML/ETag 失效。三份真实页面在仅归一既有资源版本并应用明确布局修复后，完整 HTML、脚本和数据与拆分前一致。

## 真实浏览器验收与性能边界
- Chromium 130.0.6723.31，独立临时上下文，阻断真实方案/自选/历史写接口，只允许已有方案只读查询；不接日常浏览器，不读取凭据。
- 1440/1024/390/320px 布局、标题/结果高度、无整页横向溢出、按需新增/取消、应用自动一次查询、均线与图层键盘焦点、原生多标签绘图、指标失败/重试、查询取消与晚到响应均通过。桌面可访问树已保存；移动仅 viewport/touch 模拟，不等于真机 Safari、完整读屏或 WCAG 认证。
- 发布后设定 90 秒高频循环，完成 576 次操作，无页面未捕获异常或正常流程控制台错误。额外四宽度正常加载审计无警告，故障场景的预期 503/取消独立归档。
- Trace 有 74 次主线程任务超过 50ms，最长 301.803ms；这仍是后续专项优化依据。本次不宣称零卡顿、60FPS、field INP 或小时级稳定性；duration 含 trace 导出耗时。初次解析使用旧 RunTask 名，现兼容实际 ThreadControllerImpl::RunTask，原 trace 与重分析记录均保留。
- 候选仅在隔离浏览器响应中替换 CSS，正式发布后读取服务实际响应；加载传输条件不同，不用 FCP 差值宣称拆分提速。后续性能修改应单独定位、基准和验收。

## 验证与已授权测试发布
- 冻结发布候选：前端硬门禁 31 tests OK，全量 507 passed、0 failed、0 skipped，进程退出码 0；88 条既有兼容警告。JS/Python 语法、Ruff F/E9、作用域 diff 与 UTF-8 无 BOM 检查通过。
- 运行于 clpainter-test（15001），完成 2026-11-23T14:03:53+08:00；镜像 sha256:3015f42e6bec4b55b76da232f81caceedc9f35220cf2b22c84d47d440f01a49f，标签 harbor.techfin.ai/wjl-toolkit/cl_painter:browser-modules-20261123-131827。仅主模板、三个片段和缓存依赖变化；其余运行源码（含算法、历史控制器、工作台存储、分类环境）完全保留。
- 实际脚本复验四项边界 25、绘图 30、键盘 30、存储 18、缓存 15、性能/行为 14、竞态 13、重试 18、范围 17 和方案/历史专项；三页面渲染快照及 ETag 验证通过。数据库全部表行数和 SHA-256 内容指纹与切换前一致，保留 3 个方案、4 个归档、24 个自选成员。
- 最终记录时发现并行本地更新：web/backend/app/toolbox/beichi.py、web/backend/tests/test_macd_divergence.py。未覆盖或发布这些文件；运行镜像的源码清单比对证明，除既定五个文件外全部保持。507 项结果针对冻结发布候选，不冒称后续本地算法编辑已验收。
- 未运行流水线/全量 dump、修改数据库或生产、推送镜像、写 Git、发送主对话消息或使用子代理。
- 浏览器截图/可访问树/trace：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-browser-modules-20261123-131827-side/browser-live；手机对比：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-browser-modules-20261123-131827-side/mobile-browser-comparison.png；前后副本和全部失败记录：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-browser-modules-20261123-131827-side。
- 数据/代码备份、指纹、发布与回滚命令：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-browser-modules-20261123-131827-side/deployment。本轮未改变浏览器存储协议，回滚不清理浏览器数据。

## 可重复执行
脚本 /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/validation/frontend_browser_acceptance.js，显式指定 --output、--playwright、--chromium、--library-path；--case 支持 all/layout/workspace/faults，--stability-ms 控制循环时长。Playwright 与 Chromium 来自当前已有缓存，无运行时依赖或全局配置变更。
