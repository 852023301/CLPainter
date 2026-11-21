# 选股周期结果留档

## 已确认范围
DDP get_trade_calendar 为唯一交易日历来源；周期最后一个交易日为 version_date；历史结果只增加 stock_screener_run 一张表，且仅有 id、preset_id、frequency、version_date、results 五列。禁止新增 filters_snapshot、status、error_message、executed_at、name_snapshot，也不将这些信息塞入 results。失败只写日志，成功空名单保存 []，成功记录不可被重跑覆盖。

## 能力与依赖
| 模块 | 职责 | 依赖 |
|---|---|---|
| screener-history-storage | 单表迁移、交易日历、成功快照和集合差异 | 当前方案表 |
| screener-history-runner | 完整状态更新结束后归档到期方案 | storage、现有流水线 |
| screener-history-page | 只读分页列表、固定版本页面、增减展示 | storage |
顺序：storage → runner → page。用户已确认开始实现，不自动部署、迁移实际数据库或提交 Git。

## 语义与安全边界
- 唯一键为 preset_id + frequency + version_date；只支持日/周/月/季/年自动归档，不限和分钟周期暂不自动执行。
- 对日历获取日期 D 及下一交易日 N，比较所属自然周（月/季/年）；跨期时归档，日线每交易日归档。周以周一为起点。日历无下一交易日时失败，不猜测休市。
- 归档消费本次完整状态更新产生的内存记录，而非可能已被下一批覆盖的状态表。D 从本批日线数据日期确定，不使用任务运行日期。完整流水线在采集前记录开始时间，必须不早于数据交易日中国市场时区 16:00，才允许正式留档；缺少流水线上下文的单独状态命令拒绝自动归档。D 为当天时还会校验当前时间不早于 16:00。这是保守的数据就绪门槛，不是市场交易时刻定义。
- 全量状态更新有失败、跳过、缺少标的，或使用 --symbol/--frequency 等部分更新时不得归档。按方案检查当前有效标的覆盖、目标周期记录和日期；日期不一致时保守拒绝，不将缺数据/停牌误判为移出。第一版未接入停牌豁免数据，合法停牌但数据日期落后的方案可能延后归档，日志明确原因。
- 只存完整标的名单，差异按 market + asset_class + code 计算。首次无对比基准；若中间缺期，显示真实对比版本日期。不同条件的历史参数不保留，差异只能解释为名单变化。
- 已有归档的方案禁止直接删除并返回 409，防止历史随方案消失；无历史方案的删除保持不变。名称按当前方案显示。
- 不更改 toolbox 算法和数据，不在 Web worker 启动时启动调度器，不配置机器 cron。接在现有每日更新流水线末尾；部署者须保证盘后定期触发流水线，单独开网页不会自动归档。

## 命令与验证
源代码沿用 UTF-8 无 BOM、原文件换行和原生 Jinja2/FastAPI/SQLAlchemy 风格，不引入依赖。
测试：cd /home/wjl/TechFinWorkSpace_v2/CLPainter && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q web/backend/tests
前端硬门禁：cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend && python -m unittest tests.test_frontend_template
临时 SQLite 验证五字段、唯一性、升级降级、成功空结果、重试不覆盖、日期/状态 0/无基准、页面转义分页和真实 HTTP。
DDP 单元测试使用注入的确定日历；另做一次真实接口只读校验，得到 2026-11-20、2026-11-23。在状态脚本的模拟 worker 上验证成功/失败分支，不运行真实行情采集和批量计算。未经用户要求不启动浏览器。

## 页面与接口
主图选股方案区域增加“历史结果”入口。历史页面为 /api/v1/test_api/stock_screener/history，支持方案/周期筛选、版本分页、固定 run_id 地址和本期/新增/移出/保留视图。点击标的打开当前图表，不是历史行情回放。页面只读，不触发归档或 DDP 请求。
只读 JSON 接口为 GET /api/v1/test_api/stock_screener/runs（limit 1–100、offset 分页）和 GET /api/v1/test_api/stock_screener/runs/{id}。不开放 Web 写入历史接口。

## 上线顺序
当前迁移头为 f7d3b0a5c9e2，上一个版本为 e6c2a9f4b8d1。先备份目标环境配置的 SQLite，将新迁移同步到对应环境，再执行 PYTHONPATH=/root /root/mambaforge/envs/echarts/bin/python -m alembic -c /root/CLPainter/web/backend/alembic.ini upgrade head；确认迁移成功后发布模型、screener 包、API、两个模板、状态脚本和流水线，再重启服务。迁移前不要启用新归档流水线。
不配置新的系统 cron。现有调度器应在盘后定期运行 scripts/pipelines/run_update_pipeline.sh，流水线会自动携带归档标志和开始时间；仅打开网页或单独运行无标志的 update_cl_state.py 不会产生历史。不限、分钟周期不会归档。
代码回滚可保留新增表；降级到 e6c2a9f4b8d1 会删除全部历史结果，必须单独确认，不能自动执行。

## 本次结果（2026-11-20）
- 前端硬门禁：12 tests OK；新增历史页通过真实 HTTP 渲染、转义、空状态和分页检查。
- 最终全量 pytest：350 passed，0 failed，0 skipped；29 条第三方兼容警告。
- 新模块 Ruff 检查、Python AST、Shell 语法、git diff --check 通过；UTF-8 无 BOM、原换行风格保持。
- DDP 实际日历只读样例验证通过；全套归档测试使用确定性离线批次与临时数据库。
- 未修改 toolbox，未执行真实行情流水线，未迁移实际数据库，未部署或提交。README 原有修改字节保持。

## 孤立缓存归档修复（2026-11-21）
- 原流水线在 2026-11-21 00:03:36 以退出码 1 结束；取数、聚合、缓存导出均完成，状态计算无失败，但 3 个未登记旧标的的 15 份缓存触发了归档门禁。原失败日志保留，不改写成成功。
- 修复为：仅在自动归档模式下，先通过独立 SQLite 只读连接读取 instrument 的 market/asset_class/code，匹配完整身份后再计算。未登记缓存只告警、不删除；元数据变化导致的落库缺失、有效标的缺缓存、计算失败和数据日期不一致仍拦截。普通不归档的状态命令保持原行为。
- 相关测试 34 passed；全量为 380 passed / 1 failed。独立失败为 S25（603683SH）线段结构与回归期望不一致，已在未打补丁的原容器复现，未改算法或放宽断言。
- 只部署状态脚本，不带入工作区其他行业分类改动。无新增数据库迁移，结果表仍只有五列。
- 使用原真实取数批次开始时间 2026-11-20T23:42:05+08:00，仅补跑状态更新及归档；不重采行情、不重聚合、不重导出缓存。
- 补跑于 2026-11-21 10:36:26 成功结束，退出码 0。已登记缓存 38,860，未登记 15 份保留；状态成功 38,860、跳过 0、失败 0、找不到 instrument 0；归档成功 2、失败 0。
- 2026-11-20：日三买 14 个，相比 2026-11-19 新增 2、移出 7、保留 12；日二三合买 0 个，新增 0、移出 3、保留 0（成功空结果，不是漏保存）。旧版本、自选和方案内容及 15 份孤立文件均已校验保留。
- 补跑日志：/mnt/DataDepartmentTest/home/wjl/data_set_dev/logs/pipelines/recover-orphans-20261121-101916/replay.log。部署备份与校验：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-orphan-fix-20261121-101916。
