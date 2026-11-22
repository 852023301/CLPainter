# 前端第 5 项：统一浏览器存储容错（2026-11-22）

## 状态与范围

已完成优化，并按用户授权部署到 clpainter-test（15001），完成时间 2026-11-22T08:56:59+08:00。未提交 Git。
运行代码只更新主模板和 screener-history.js，不修改 API、算法、数据库或其他任务文件。未新增运行时脚本依赖；公共适配层内联在主页面，历史控制器通过参数接收同一实例。

证据：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-storage-20261122-083640-side`；部署数据备份、源码/镜像校验及代码回滚：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-storage-20261122-083640-side/deployment`。

## 降级规则

- createBrowserStorage 在创建时不访问原生 localStorage，属性 getter 本身抛错、对象缺失或方法抛错都不会阻断启动。
- getItem 正常时读取原生值并更新本页最后已知值；读取失败时使用本页缓存，没有缓存则返回 null，由原辅助函数提供默认值。
- setItem 先记录本页新值，再尝试原生写入。QuotaExceededError 等失败后，该键在本页优先使用内存最新值，不能被原生旧值覆盖；false、0、空字符串和缺失值保持区分。
- removeItem 先删除本页值并记录删除标记。原生删除失败时仍返回缺失，不能复活原生旧滚动位置/最近点击等状态。
- 状态按键隔离：一个键写失败不阻止其他键继续持久化；没有未落盘改动的键仍能观察原生存储的外部更新。
- 不后台重放未落盘内容。原生存储恢复后，只有下一次明确写入/删除成功才清除该键的降级标记，避免悄悄覆盖外部较新内容。
- 主图图层、均线、缺口、副图选择、搜索历史、自选布局、实时选股和历史模式/版本/滚动位置使用同一个容错入口；历史控制器通过 storage 参数注入共享对象，不再自行读写原生存储。
- 所有原生 removeItem 调用都改为 lsRemove；删除语义保留，并由故障启动、应用查询和重置用例验证。新的静态门禁禁止公共适配层之外再次出现直接原生 get/set/remove。

降级仅保证当前页面运行。原生存储不可用时，刷新/关闭页面后不能承诺保留本页设置；后端数据库保存的自选、方案、历史记录不受此能力限制。本项不新增跨页持久化、TTL、后台同步或存储权限提示。

## RED → GREEN

18 个存储场景在修复前为 15 failed / 3 passed，修复后全部通过，无 harness_error。原四个存储失败断言保持不变并转绿，隔离复现目前 3 failed / 15 passed，仅剩键盘事项。

覆盖读取受限、quota、失败写入与原生旧值、false/0/空字符串、删除墓碑、最后已知值、localStorage getter 抛错、对象缺失、单键隔离、恢复后显式写入、主页面/历史共享内存、损坏搜索缓存与导航，以及完整页面 available/denied/quota/delete/getter 五种启动、开关、自动应用查询和重置模拟。

- 前端硬门禁：20 tests OK。
- 当前工作区默认全量：474 passed、0 failed、0 skipped，pytest 进程退出码 0。
- 既有范围 17、竞态 13、重试 18 场景全部保持通过，没有放宽其原断言。
- 原删除静态断言从直接 localStorage.removeItem 更新为 lsRemove，保留“必须删除最近点击状态”的语义，而不是删除断言。
- 原方案/历史夹具改为执行真实公共存储块，不再绕过适配层；完整 DOM 夹具补齐标准 options、textContent、hidden/disabled 行为。模块模拟按 URL 查询参数精确路由，避免 module=macd 被 module=ma 的子串错误匹配并产生假错误；健康网络场景同时要求没有组件错误。

## 发布与验证

- 镜像 4.0 已固化；实际镜像 sha256:0276cb70bc329a4c2817b88dcc7c99ada9a9ac05c4fbc8bb5cf65d56b73700e6，发布标签 harbor.techfin.ai/wjl-toolkit/cl_painter:storage-20261122-083640-side。
- 更新两个运行文件前以实际运行容器制作回滚镜像，保留之前的安全修复、指标准确性修复、分类环境和其他运行代码。
- 实际返回的公共存储块、搜索函数、方案/历史注入代码和其他已修复逻辑先与可信发布源码比对；下载的历史脚本哈希与镜像发布记录一致。
- 18 个存储场景通过；13 个原函数场景使用实际页面与实际历史脚本，5 个完整页面故障启动场景使用相同发布源码的冻结原始模板（将 Jinja 数据替换成固定夹具），未执行真实浏览器或修改浏览器权限/已有键。
- 实际返回页面的范围 17、竞态 13、重试 18 场景及原选股/历史交互检查通过；真实 400 转义和错误页安全 API 哈希保留。
- 发布后数据库全部表的行数及 SHA-256 内容指纹与最新切换前一致；正常图表、指标、选股和历史接口正常，服务日志无非预期异常。
- 只修改这两个前端运行文件，没有发布并行算法改动；未运行数据流水线或全量 dump，未进行数据库迁移、生产服务变更、Git 写操作或镜像推送。

## 重跑

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/frontend_storage_behavior.js /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/templates/lightweight_charts_demo.html
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_frontend_template
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests
```

新增 frontend_storage_harness.js 是测试辅助模块，不是运行时依赖。该任务没有降低已有质量门禁，也没有借存储容错修改方案、行情或图表业务规则。
