# 统一运行数据清理

## 已确认目标
在元数据同步并校验成功后、行情采集和聚合之前，统一处理 pv_data、curated、chart_payload 中不属于本批元数据范围的文件。身份为 market + asset_class + code；不以“本轮未生成”为失效依据。采集与聚合不再各自删除缺少产物的有效标的文件。

## 边界
只做本地实现和临时目录/数据库测试，不部署、不清理真实数据、不运行真实采集或导出，不修改主线程的状态更新与归档逻辑，也不提交 Git。当前 README 修改保留。
原始历史目录 OLD_DATA_DIR、SQLite、方案历史、其他市场/资产范围和未识别文件不能清理。默认 dry-run；--apply 只移到当前数据根的 quarantine，不物理删除。保存清单与指纹并支持显式恢复，不覆盖已有文件。当前配置的生产和测试数据根不可混用。

## 数据日期与完整性
元数据同步统一选择本批处理交易日，优先 --as-of/CLPAINTER_AS_OF，否则使用 DDP 日历最近一个盘后完整交易日（中国市场时区，16:00 前不选择当日）。元数据查询、有效日期筛选、行情取数 END_DATE 使用同一日期。元数据全部查询和预检通过后一次事务同步三类标的，再写完整批次清单。
空名单、重复/不合法代码、与上一份元数据相比超过默认 20% 的下降会阻止同步；清理必须验证清单完整、范围明确、数据库和数据根匹配、当前身份集合与清单一致。清理候选比例超过默认 20% 时拒绝应用，需人工检查后显式调整阈值。源文件仍有效但未生成/未更新时，应由数据质量门禁报错，不删除旧缓存掩盖失败。

## 实现顺序
1. 写临时 SQLite/目录安全回归，先红后绿：统一清理模块与 CLI、预览/隔离/恢复、非法清单和路径保护。
2. 元数据先校验后原子同步，输出批次清单；统一日期传给取数。
3. 在流水线元数据后调用清理并 --apply，保留原分类任务顺序；移除采集及四类聚合的分散失效清理。
4. 运行 CLI --help、Shell 语法、Ruff 与全量 pytest，检查主线程文件没有被本任务改动。

## 校验命令
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q web/backend/tests/test_data_lifecycle.py web/backend/tests/test_metadata_cleanup_pipeline.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q web/backend/tests
不修改 toolbox，不要求本轮全量 dump；真实批量清理必须另行授权。隔离目录在三个扫描根之外，不会被再次聚合导出。

## 使用与恢复
新入口：web/backend/scripts/maintenance/cleanup_stale_data.py。默认只预览，不移动文件。需要一份本批元数据同步成功生成的 JSON 清单；不能把任意当前数据库导出当作上游完整性证明。

    python web/backend/scripts/data_ingestion/meta_info.py --report /safe/reports/metadata.json
    python web/backend/scripts/maintenance/cleanup_stale_data.py --metadata-report /safe/reports/metadata.json
    python web/backend/scripts/maintenance/cleanup_stale_data.py --metadata-report /safe/reports/metadata.json --apply
    python web/backend/scripts/maintenance/cleanup_stale_data.py --restore /configured-data-root/quarantine/cleanup-BATCH/manifest.json

上述第一条会同步数据库，不是只读操作，实际运行前应备份目标数据库并检查环境。例子中的路径须替换为对应环境路径；本轮没有执行这些真实操作。
流水线自行创建私有临时批次清单，在成功同步后显式调用 --apply；分类任务仍位于清理之后、取数之前。退出时仅删除本轮自建的临时清单，不删除操作者通过 CLPAINTER_METADATA_REPORT 提供的文件。发生实际隔离时，会另存 metadata.json 和 manifest.json 到隔离批次中，因此临时清单删除后仍可审计和恢复。

## 关键限制
- 只隔离本批清单明确覆盖的市场/资产类型；未知文件名和符号链接保留，记录在 skipped 中。chart_payload 正确去掉 .chart.pkl，不把 .chart 误算成代码。
- 已注册但暂时没有源数据的合法标的，其旧 curated/图表文件不会被清掉，保留计算参考；空取数不删除原有合法文件。数据没有到达本批日期时取数阶段直接失败，不以旧数据冒充目标日期。
- 隔离在同一文件系统内通过重命名完成，不释放磁盘空间，不支持跨文件系统复制后删除。候选比例按各根/市场/资产范围分别检查。
- 单个工具的 apply/restore 互斥，并复查元数据摘要、当前身份集合和文件指纹；但这不是跨数据库和文件系统的事务。运行期间不要与另一个元数据同步、采集、聚合、导出或手工文件写入任务并发。
- 部分移动失败时保留可恢复清单；恢复前检查所有目标，不覆盖新生成文件。恢复只还原文件，不回滚数据库；若元数据源错误，先修正元数据再恢复，避免下一次再次隔离。
- 工具运行于 Linux 宿主机或容器，锁使用 POSIX flock。隔离目录在正常流水线扫描根之外，手工导出不要把整个数据根或隔离目录作为 --source-dirs。
- 这是当前运行数据的维护流程；在同一数据根回放更早日期会改变元数据与行情范围。任意历史回放请使用独立数据根，不应借此清理当前服务数据。

## 本次验证结果（2026-11-21）
- 清理/元数据/流水线相关回归：84 passed，覆盖默认预览、显式隔离、恢复、部分失败、路径/环境/命名空间保护、元数据和文件变化、数据日期传递与各阶段失败短路。
- 修改前全量基线：387 passed、1 failed；失败为 test_segment_regression[S25] 的线段结构不匹配。
- 最终当前工作区全量：450 passed、1 failed；唯一失败仍为同一 S25。期间其他线程新增了前端测试，数量差异不全由本任务产生。没有跳过或放宽原断言，全项目全绿门禁尚未通过。
- 新模块/CLI/元数据脚本和新增测试 Ruff 通过；Shell 语法、Python AST/UTF-8 无 BOM、git diff --check 通过。四个聚合脚本的计算函数 AST 与 HEAD 一致，仅移除分散失效清理。
- 全部隔离/恢复测试使用临时目录和 SQLite；流水线顺序测试在独立假工作区运行，避免误用真实虚拟环境和数据脚本。
- 未修改真实数据、未部署容器、未提交 Git。根 README、状态更新和归档测试文件保持本任务开始时的哈希。其他 API/前端并行改动保留。
- 全量日志：/tmp/clpainter-unified-cleanup-tests-20261121-final.log；专项日志：/tmp/clpainter-unified-cleanup-focused-20261121.log。
