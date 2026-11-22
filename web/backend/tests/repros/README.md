# 前端问题复现与分组回归

## 为什么隔离

未修复问题的目标行为仍以 RED 记录。frontend_contracts.py 不匹配默认 test_*.py；没有新增 conftest、pytest 配置、xfail 或 skip。基线阶段不修改已有测试；修复后只把已转绿的分组显式接入门禁。
基线时默认收集为 427 项。第 1 项加入 18 个安全 HTTP 回归；第 2 项把 13 个并发场景显式接入前端门禁，第 3 项后，前端 18 tests OK、默认全量 447 passed。本目录其他 RED 仍只在明确选择时执行。

## 运行当前代码的严格契约

完整复现（修复前基线 14 failed / 4 passed；当前本地 3 failed / 15 passed，退出码仍为 1）：

```bash
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.py
```

只检查本次要修的问题，例如副图竞态：

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js \
  --case indicator_latest_wins --check
```

错误页安全及正向对照：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.py \
  -k 'error_response or valid_chart'
```

Node 不带 --check 时只输出观测 JSON：退出 0 仅表示探针执行成功，不代表契约通过；验收必须使用 --check 或上面的 pytest 命令。解析失败、依赖缺失或意外夹具异常为退出 2，不算有效的缺陷复现。

## 用例与边界

| 领域 | 用例 | 修复前基线现象 |
|---|---|---|
| 请求重试 | module_retry、gap_retry | 首次失败后第二次仍复用失败 Promise，实际请求次数为 1 |
| 副图竞态 | indicator_latest_wins | 选择成交量后，晚到的 BOLL 覆盖面板，残留两类序列 |
| 可视范围 | indicator_preserves_range | 100–150 被重置为初始的 900–949 |
| 存储容错 | storage_* 四项 | 受限存储异常向调用者传播 |
| 键盘交互 | realtime_result_keyboard、两个 menu trigger | 实时名单是仅点击的 DIV；均线与图层入口没有可聚焦语义 |
| 错误页 | 两个 query_html、internal_diagnostics | 无害 span 参数成为 HTML 元素；500 返回合成内部诊断 |
| 正向对照 | control_* 三项、valid_chart | 正常构建、共享成功请求、正常存储和安全页面均通过 |

JavaScript 用例提取并执行原模板函数，不复制被测业务实现；请求、图表 API、DOM 和 storage 边界使用确定性夹具。错误页用例执行原 Python 端点 AST，替换数据库与数据加载边界，不导入真实应用、不接触真实数据库或服务。
HTML 探针只有无害 span，无脚本或事件处理器。未做浏览器利用验证。

缓存新鲜度提供 cache_freshness_observation：确认无版本缓存被恢复，初始化只请求选项、不重新查询。不擅自决定 TTL 或新增数据版本协议，因此该项是观测，不算严格红色断言。
绘图持久化的保存范围、跨标的/周期规则以及真实浏览器性能尚需后续确认；本阶段不伪造对应验收标准或性能数字。

## 修复时的使用方法

1. 对目标问题运行显式用例，保留修复前 RED 结果。
2. 只修改对应功能，使目标断言转为 GREEN，并保持正向对照通过。
3. 将已修复问题的稳定行为用例接入默认门禁；不要删除或放宽断言，也不要用 xfail/skip 冒充修复。
4. 新函数拆分导致提取上下文变化时，只调整夹具接入方式，保留用户可观察的行为断言。
5. 运行前端硬门禁与全量测试；真实浏览器验证仍需要用户明确授权。

## 固定基线重放

源码、用例副本、哈希、初始 diff、镜像身份和日志保存在：

`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-frontend-baseline-20261121-175916-side`

```bash
CLPAINTER_FRONTEND_BASELINE_ROOT=/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-frontend-baseline-20261121-175916-side/frozen/CLPainter \
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  /home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-frontend-baseline-20261121-175916-side/frozen/CLPainter/web/backend/tests/repros/frontend_contracts.py
```

固定副本用于复现本次前端契约；未复制大行情数据、.env 或容器环境变量，不是完整可迁移容器。冻结源码仍按内部资料保管。默认全量测试依赖现有项目依赖及测试数据环境。

## 第 1 项安全修复后的状态（2026-11-21）
原三个错误页安全断言已转绿；未放宽或删除原契约。web/backend/tests/test_frontend_error_pages.py 的 18 个 HTTP 回归已加入默认门禁，前端 16 tests OK、默认全量 445 passed（0 failed / 0 skipped）。当前隔离用例 11 failed / 7 passed，剩余失败属于副图、重试、存储和键盘等尚未修复事项。
本项安全修复已根据用户授权部署到测试服务（15001），尚未提交 Git；阶段记录见 /home/wjl/TechFinWorkSpace_v2/CLPainter/docs/review/2026-11-21-frontend-error-pages.md。原冻结基线仍保留原始 RED 状态，可独立重放。

## 第 2 项并发修复后的状态（2026-11-21）
原 indicator_latest_wins 已转绿；新增 indicator_concurrency 分组共 13 场景全部通过，并接入前端硬门禁。正常请求失败重试及正常切换视窗重置仍属于后续事项，原断言没有放宽。

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group indicator_concurrency --check
```

当前原始隔离契约仍为 18 项，其中 10 failed / 8 passed；新并发场景由上面分组和前端门禁执行。第 2 项已根据用户授权部署到测试服务（15001），尚未提交 Git；部署及验收记录见 /home/wjl/TechFinWorkSpace_v2/CLPainter/docs/review/2026-11-21-frontend-indicator-race.md。

## 第 3 项重试修复并部署（2026-11-21）
module_retry_lifecycle 分组 18 场景已接入默认门禁并全部转绿；原竞态 13 场景保持通过。前端 18 tests OK、默认全量 447 passed（0 failed / 0 skipped）。当前原始 18 个隔离契约为 8 failed / 10 passed；正常视窗、存储、键盘等剩余 RED 未放宽。

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group module_retry_lifecycle --check
```

第 3 项已按用户授权部署到测试服务（15001），尚未提交 Git。阶段记录见 /home/wjl/TechFinWorkSpace_v2/CLPainter/docs/review/2026-11-21-frontend-module-retry.md。冻结基线保持原样。

## 第 4 项视窗优化并部署（2026-11-21）
viewport_preservation 分组 17 场景已加入门禁并全部通过；原竞态 13、重试 18 场景保持通过。前端门禁 19 tests OK，当前工作区（含并行任务已有测试）全量 473 passed、0 failed、0 skipped。原始 18 个隔离契约现为 7 failed / 11 passed，正常切换视窗断言已转绿；存储与键盘事项未改。

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group viewport_preservation --check
```

该项已按用户授权部署到测试服务（15001），未提交 Git；不包含并行算法改动，也不实现跨股票/周期或整页导航的持久化。记录见 /home/wjl/TechFinWorkSpace_v2/CLPainter/docs/review/2026-11-21-frontend-viewport.md。冻结基线保持原样。

## 第 5 项浏览器存储容错并部署（2026-11-22）
四个原存储断言已转绿，原 18 个隔离契约当前为 3 failed / 15 passed，剩余是键盘交互。新增独立 frontend_storage_behavior.js 的 18 场景已接入默认门禁；前端 20 tests OK，当前工作区全量 474 passed（0 failed / 0 skipped）。范围、竞态和重试分组保持通过。

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/frontend_storage_behavior.js /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/templates/lightweight_charts_demo.html
```

该项已按用户授权部署到测试服务（15001），未提交 Git；故障时仅保证本页内存状态，不承诺刷新后持久。记录见 /home/wjl/TechFinWorkSpace_v2/CLPainter/docs/review/2026-11-22-frontend-storage.md。冻结基线保持原样。
