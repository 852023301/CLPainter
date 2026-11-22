# CLPainter 前端修复前基线（2026-11-21）

## 范围与完成定义

本记录只完成修复顺序的第 0 步：冻结代码身份、运行镜像和测试结果，补齐可重复执行的缺陷复现。不修改运行源码、不修复业务行为、不部署、不重启、不写真实数据库、不进行 Git 变更，也不复用或继续主对话的未完成操作。
新红色用例与默认测试集隔离，避免影响主对话的工作。未修改现有测试或共享 tasks/plan.md、tasks/todo.md。

## 基线身份

- 采样开始：2026-11-21T17:59:16+08:00；记录完成：2026-11-21T18:05:29+08:00（UTC+8）。
- 分支：tradingview_dev。
- HEAD：`f31dc8ce06668701a9a368b203220924469e6b2c`。工作区并非干净，因此 HEAD 不能单独代表运行代码。
- 已保存已有前端改动 patch、97 个应用/测试源文件的冻结副本与 SHA-256；采样后 97 个原有源文件的内容均未改变。
- 测试容器：clpainter-test；镜像标签：`harbor.techfin.ai/wjl-toolkit/cl_painter:4.0`。
- 实际镜像：`sha256:65c675a1d9a2d157d6a00723f65a05852ef0c1439273efe5a6cee41d038df80f`。
- 镜像发布标签：`preset-autoquery-20261121-175131`。
- 容器启动：2026-11-21T09:54:28.159247161Z；采样期间容器身份未变化。
- 关键三个运行文件的容器内容与本地采样内容逐字节一致；本记录不把可变的 4.0 标签当作唯一版本标识。
- Python：Python 3.10.13；Node：v20.18.1。依赖版本见 baseline.json。

| 关键文件 | SHA-256 |
|---|---|
| web/backend/app/api/api_v1/endpoints/test_api.py | ff20ac78fedd9694fdbf47422b12ade07144f0b0a037aa4eb2f8f19cbd10e287 |
| web/backend/app/templates/lightweight_charts_demo.html | 6fd434447c8cbecfd12e6e9197ae708d93b1a60c4dd938457545346d9d591d7a |
| web/backend/app/static/js/screener-history.js | e453e9dc53d1263b6c0e0103de2181ce0c27132245962dc2ae11fc7a99bad0e0 |

## 已实跑结果

| 项目 | 结果 | 解释 |
|---|---|---|
| 前端硬门禁 | 16 项通过，退出码 0 | 原有语法、开关、方案及历史交互门禁 |
| 默认全量 pytest | 427 passed，0 failed，0 skipped，退出码 0 | 禁用 pytest cache，并把临时测试目录放入独立证据目录 |
| 默认收集检查 | 427 tests collected | 未收集新隔离复现文件 |
| 显式缺陷契约 | 14 failed，4 passed，0 errors，0 skipped，退出码 1 | 14 个 RED 是已知问题的目标行为未满足，不是默认测试回归 |
| JavaScript 观测 | 9 个红断言、3 个正向对照、1 个缓存观测 | 没有 harness_error |
| 语法及 lint | Node --check、Python Ruff F/E9 通过 | 未修改现有断言、未添加依赖 |

默认全量有 48 条既有兼容警告。这里的通过不代表真实浏览器视觉、布局或性能已经验收。

## 已固定的缺陷与复现

| ID | 问题 | 复现证据 | 严格红断言数 |
|---|---|---|---:|
| F01 | 错误页安全 | 非法 frequency、market 中的无害 span 成为 HTML 元素；500 暴露合成内部诊断 | 3 |
| F02 | 副图乱序 | 慢 BOLL → 快成交量 → BOLL 晚返回，最终 displayed=boll，序列残留 histogram + candlestick | 1 |
| F03 | 请求失败后无法重试 | 模块 Promise 和额外 gapPromise 各自缓存失败；第二次调用实际请求数仍为 1 | 2 |
| F04 | 指标切换重置视窗 | 已有 100–150 范围变成默认 900–949 | 1 |
| F05 | 存储异常中断 | bool/string 的 get/set 四个辅助函数均向外传播 SecurityError | 4 |
| F08 | 键盘交互不足 | 实时选股行仅绑定 click 的 DIV；均线/图层入口没有可聚焦语义 | 3 |

正向对照同时证明：正常成交量可构建、同一成功请求仍能共享、可用存储能正常读写、有效图表请求返回 200。测试不是因缺依赖或夹具崩溃而假红。

## 观测基线与尚未确定的验收口径

- F06 实时结果缓存：观测到恢复 FROM_EARLIER_SESSION，初始化仅请求 /stock_screener/options，fresh_query_calls=0，缓存只有 count/results，未见新鲜度元数据。尚未决定数据版本协议或失效时限，不凭空添加 TTL 断言，也不把所有恢复缓存都判成已发生的过期事故。
- F07 绘图/视窗恢复：源码中 rectState.boxes、trendState.lines、fibState.items 是页面内存状态，周期切换仍通过整页导航。持久化按标的/周期、保存位置和恢复边界尚待明确，本轮没有用简化 VM 重载冒充浏览器持久化测试。
- F09 工程体量：主模板 4622 行、193349 字节；内联 CSS 1300 行、内联 JS 3137 行、DOM 事件绑定 80 处。不擅自设定行数阈值或先行重构。
- F10 性能候选：光标路径存在两处 candleData.find，可视范围变化存在 candleData.filter。这里只记录源码热点，没有真实浏览器首屏、长任务或拖动帧率基准；后续优化必须先测量，不用 Node 单测耗时代替浏览器性能。
- 无浏览器人工验收授权，因此未打开浏览器。键盘焦点契约不等同于完整无障碍审计。

## 证据与重放

证据目录：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-frontend-baseline-20261121-175916-side`。

- baseline.json：代码/镜像/环境、源码稳定性、统计与逐用例结果。
- source-before.json、source-after.json：97 个原有源文件的校验。
- deployed-source-before.json：容器三个关键文件的只读哈希。
- frontend-before.patch、frozen/CLPainter/：已有前端改动与冻结代码、复现用例副本。
- frontend.log、pytest.log、pytest.exit：默认门禁结果。
- contracts.log、contracts.xml、contracts.exit：显式 RED 和正向对照结果。
- javascript-observations.json：具体请求次数、错图、视窗、存储异常与缓存恢复轨迹。
- collection.log：默认收集隔离证明。

执行命令与后续 RED → GREEN 接入方法见 /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/README.md。仅新增本记录及 tests/repros 下的独立文件；默认测试和运行源码保持原样。
