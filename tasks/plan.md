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
