# 前端第 2 项：副图异步构建竞态（2026-11-21）

## 状态与范围

已完成本地修复和自动化验收，并经用户后续授权部署到测试服务；未提交 Git、未启动浏览器或数据流水线。运行代码只改主模板中的 buildIndicator，不修改 API、算法、数据库、共享请求缓存或其他任务的源码。既有错误页安全修复保持不变。

证据目录：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-indicator-race-20261121-190518-side`。修复前模板、原回归文件、RED/GREEN 场景输出、前端门禁和全量日志均已保存。

## 构建提交规则

- 每个面板独立递增 buildVersion，不使用全局计数器。每次选择（包括重复选择同一指标）都令更早的构建过期。
- 数据准备完成后、删除旧系列或修改样式/lookup/标签/primarySeries 前，确认本次构建仍然最新。
- 过期请求的成功、失败及 finally 均不得更新面板，也不能误报当前选择失败、提前标记 ready 或触发全局初始化。
- 新数据等待期间保留已显示的图；最新的数据加载失败也保留原图，并保持原有当前失败日志。最新失败不允许较早成功请求复活。
- ready 表示最新构建已结束（成功或失败）；等待中的最新构建不能被旧回调提前标记为结束。
- 不取消共享模块请求。其他面板仍可消费同一模块结果，并保持一次网络请求的共享缓存。

同步渲染器自身的异常仍沿用既有错误处理，本项没有扩展为整套渲染事务回滚或错误提示 UI。

## RED → GREEN 与门禁

新增并发分组使用原始 buildIndicator、alignToCandles、buildSubSeries；共享请求案例还执行原 fetchChartModule、ensureIndicatorData、updateIndicatorLookups。只替换请求时序、DOM 和图表 API 边界，不复制被测构建实现。

| 场景 | 验收内容 |
|---|---|
| 慢 BOLL → 快成交量 | 晚到 BOLL 不覆盖最新成交量、不残留系列 |
| 等待数据 | 已显示图、主序列和标签保持，数据就绪后才替换 |
| 最新加载失败 | 原图保持，不出现空白替换 |
| 过期成功与 finally | 不修改 ready、范围、样式，不提前完成四图初始化 |
| 过期失败 | 不报当前选择错误、不修改状态 |
| 最新失败、较早成功 | 较早请求不能在失败后复活 |
| BOLL → 成交量 → BOLL | 同一共享结果返回时只提交最后一次，不叠加系列 |
| 面板独立对照 | 一个面板的选择不使另一面板构建过期 |
| 跨面板共享模块 | 切走一个面板不取消另一个面板，一次网络请求仍共享 |
| 晚到 MACD | 不能覆盖成交量高度、lookup、标签或主序列 |
| 三连切换、最新先完成 | RSI 最后被选择，即使先返回也保持最终 RSI |
| 三连切换、最新后完成 | 旧请求不能留下系列，最终只有 RSI |
| 四指标正常对照 | 成交量、MACD、BOLL、RSI 都能正常构建和替换 |

- 修复前：13 项中 11 RED、2 个正常对照通过，0 harness_error。
- 修复后：13 项全部通过；原 indicator_latest_wins 断言未删除或放宽，已转 GREEN。
- 该分组已显式接入 tests.test_frontend_template，校验全部 13 个 ID 均执行且通过，不能空跑或静默缺项。
- 前端硬门禁：17 tests OK；默认全量：446 passed、0 failed、0 skipped，pytest 进程退出码 0。
- 原 18 个隔离契约目前为 10 failed / 8 passed，其他已知问题仍隔离，没有用 skip/xfail 放宽门禁。

## 本轮明确不处理

- 第 3 项的失败 Promise 缓存/重试策略未改，相关旧用例仍 RED。
- 第 4 项的正常切换后视窗重置未改，indicator_preserves_range 仍 RED。本轮只阻止过期构建的范围副作用，不宣称所有范围问题已修复。
- 存储、键盘、绘图持久化、模板拆分和性能优化未启动；不改变后端指标计算或数据内容。
- 没有浏览器人工验收，本轮属于确定性原函数行为回归，不以 Node 耗时代替实际浏览器性能或视觉结论。

## 重跑

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group indicator_concurrency --check
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_frontend_template
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests
```

新分组与已知缺陷复现仍共用一个测试入口，但默认门禁只显式执行已转绿的 indicator_concurrency 分组；不会自动执行其他 RED 项。修复前冻结证据保持原样，后续部署和 Git 操作仍需用户明确授权。

## 已授权部署到测试（2026-11-21）
- 完成时间：2026-11-21T21:08:49+08:00；clpainter-test，HTTP 15001。只发布主模板，镜像 4.0 已固化；实际镜像 sha256:21515efdefa1b9a4c946c435f8bf76b2bcecccf2c517359e6cc36cbfec0ab61a，发布标签 harbor.techfin.ai/wjl-toolkit/cl_painter:indicator-race-20261121-210041-side。
- 部署前复跑：前端 17 tests OK、并发 13 场景全通过、默认全量 446 passed（0 failed / 0 skipped），pytest 进程退出码 0。
- 实际返回的六个指标函数及方案代码段先与可信发布源码逐字比对，再对实际页面脚本执行 13 个并发场景，全部通过。旧版本代码会被检查器拒绝，不能因缓存返回旧脚本而假通过。
- 正常图表、指标、历史、自动应用查询、新增折叠和五期限制检查通过；安全 API 文件哈希保持，真实 400 转义检查通过。数据库全部表行数及 SHA-256 内容指纹不变，分类独立环境保留，服务日志无非预期异常。
- 备份、源码/数据校验及代码回滚命令：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-indicator-race-deploy-20261121-210041-side。生产状态未变，未运行行情流水线或全量 dump，未提交 Git，未推送镜像，未进行浏览器人工验收。
