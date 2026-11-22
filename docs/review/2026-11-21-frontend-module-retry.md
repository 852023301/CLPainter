# 前端第 3 项：指标、均线、缺口加载失败后的重试（2026-11-21）

## 状态与范围

已完成优化并根据用户明确授权部署到 clpainter-test（15001），完成时间 2026-11-21T22:25:34+08:00。未提交 Git。
运行代码只修改主模板内 fetchChartModule、ensureGapMarkers 和均线隐藏时的请求判断；没有修改后端接口、算法、数据库、现有竞态保护或正常切换的视窗行为。

证据：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-module-retry-20261121-215924-side`；部署、数据备份及代码回滚命令：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-module-retry-20261121-215924-side/deployment`。

## 请求生命周期

- 同一模块的等待中请求仍共享同一个 Promise；失败之后只清理对应模块，下一次用户操作会创建新请求。新一次重试的并发使用者仍共享一次网络请求。
- 清理前比较 Promise 身份，旧失败不能删除较新的成功缓存，也不能清空其他模块缓存。
- 网络拒绝、同步 fetch 异常、HTTP 非成功状态、外层 JSON 失败、内嵌 data JSON 失败或错误容器形状，均进入共享请求的失败清理路径。
- 内嵌 JSON 在共享请求中只解码一次，缓存规范化 data；现有消费者本来支持字符串和对象，HTTP 接口保持原样。该集中解码用于修复失败缓存边界，不宣称浏览器性能提升。
- MACD 缺省或为 null 的可选 lines/stats/markers 字段规范为空数组，避免空对象第一次可显示、下一次切换却抛错；不改变指标公式或有效指标值。
- 缺口额外的 gapPromise 也在失败时清理，并保留身份检查；成功、空结果及既有合法 null 结果不因重试机制被反复请求。
- 隐藏尚未创建的均线不再启动请求；再次勾选时按需加载。等待中用户取消勾选时，晚到数据不能重新打开该图层。
- 不新增后台循环重试、超时策略、成功缓存 TTL 或全局面板重建。通过原来的指标切换、均线/缺口取消再勾选触发重试，无需整页刷新。

## RED → GREEN

最终 18 场景对修复前模板重放为 12 failed / 6 passed；修复后 18 个场景全部通过，0 harness_error。另保留了发现空 MACD 再次切换失败的独立 RED 证据。

覆盖网络/HTTP/两层 JSON/错误形状/同步异常、失败与恢复阶段的共享请求、旧失败不误删新缓存、缺口与均线完整开关链路、晚到结果遵守最新开关、BOLL/RSI/MACD 失败后再切换、空成功缓存、其他模块缓存隔离，以及缺口 Promise 替换保护。

18 场景已显式接入默认前端门禁；原有 13 个竞态场景继续全部通过。原断言未放宽，没有 skip/xfail，没有新增依赖。

## 最终验收与部署

- 前端硬门禁：18 tests OK。
- 默认全量：447 passed、0 failed、0 skipped，pytest 进程退出码 0；包含最终空 MACD 边界。
- 原 18 个隔离契约当前为 8 failed / 10 passed，两个重试断言已转绿；剩余视窗、存储和键盘问题未在本任务修复。
- 仅替换主模板，镜像 4.0 已固化；实际镜像 sha256:e4c4bf4478c3f682e268d822ecc5f7dbb7055a900ed9fdea7432552212e1a304，发布标签 harbor.techfin.ai/wjl-toolkit/cl_painter:module-retry-20261121-215924-side。
- 先比对实际页面的十个命名函数、缺口开关箭头函数及方案代码段与可信发布源码一致，再对实际返回页面脚本执行 18 个重试及 13 个竞态场景，全部通过。
- 正常图表、指标、选股、历史、折叠新增区、五期限制和既有 400 安全转义检查通过；服务日志无非预期异常。
- 准备期间检测到选股方案表有外部更新，切换前重新做一致性备份并采用最新内容。发布后所有数据库表行数和 SHA-256 内容指纹与该切换前基线一致，没有覆盖更新、自选或历史数据。
- 分类独立 Python 环境保留；生产状态未变；未运行行情流水线或全量 dump，没有数据库迁移、Git 写操作、镜像推送或浏览器人工验收。

## 保留边界

本项不重算或修复错误指标记录，不把渲染器自身的异常改造成事务回滚；正常切换指标的视窗重置仍是第 4 项。成功缓存的新鲜度、存储容错和键盘交互继续按后续计划处理。

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group module_retry_lifecycle --check
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group indicator_concurrency --check
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_frontend_template
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests
```
