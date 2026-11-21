# 脚本按功能分类计划

## 范围
仅整理 scripts 目录、修正路径与流水线引用、同步说明；不改变计算与采集算法。
保留宿主机 CLPainter.web.backend.app 导入方式和已有 Phase 7 归档。
不执行真实采集、缓存导出、状态写库、权限修改、停止服务或容器部署。

## 顺序
1. 补脚本布局与流水线回归测试，先验证缺少新路径时失败。
2. 移动脚本至 data_ingestion / aggregation / cache / state / validation / maintenance / pipelines。
3. 更新 BACKEND_DIR、PROJECT_ROOT、流水线目标及有效文档命令。
4. 检查 Python AST 除路径外零差异、无副作用入口验证、全量 pytest。

## 验收
- 所有 15 个活跃脚本各有唯一的新位置，7 个 Phase 7 归档脚本不移动。
- 流水线步骤顺序、聚合并行及失败短路保持不变。
- 工作区已有 README 和 WORKERS 修改保持不变。
- 工具核心代码与数据目录不修改；不自动提交 Git。

## 验证结果
- 原测试基线：87 passed。
- 最终测试：121 passed、0 skipped（含 34 项脚本布局/流水线检查）。
- 14 个 Python 活跃脚本与迁移前 AST 一致，仅允许必要的父目录层级变化。
- Shell 语法、七个安全 CLI 的 --help、流水线六种成功/失败场景通过。
- 原 README / prod.env / test.env 字节保持不变；Git 未暂存或提交。

---

# 选股方案持久化计划（2026-11-20）

用户已确认 docs/screener-presets.md 的功能范围。
1. 风险优先：先写真实临时数据库/HTTP 回归，再添加模型、可逆迁移和 CRUD 接口。
2. 接入原选股面板：保存、应用、更新、删除；显式保留不限和 0，处理加载/失败/互斥。
3. 用 Node 执行真实交互回归；运行前端硬门禁和全量 pytest，复查 diff 与 README 原修改保留。

无新的工具依赖，不动计算逻辑、真实数据库、容器与 Git；后端方案沿用当前实例共享边界。详细上线迁移见功能文档。

## 本轮结果
后端 22 passed，前端 12 tests OK；初轮全量 230 passed / 6 failed（同基线）。并行日期回归测试更新后复跑为 315 passed，0 failed，0 skipped；本任务没有修改那组测试或计算代码。迁移只在临时数据库执行，README 原修改保留。新接口/模型/模板上线前必须先对目标数据库备份并运行 Alembic；本轮未部署或提交。
