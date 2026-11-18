# Phase 7 归档脚本

这些脚本是 Phase 7 线段优化阶段的维护与验收工具，不属于运行时依赖。

- `phase7_classify_changes.py`：新旧缓存分类
- `phase7_invariant_audit.py`：不变量审计
- `phase7_parallel_compare.py`：新旧管线并行对比
- `phase7_visual_report.py`：可视化验收报告

运行方式与归档前一致，脚本内部已将 `BACKEND_DIR` 调整为 `parents[3]`。

- `phase7_first_segment_check.py`：首段 fake/real 检查
- `phase7_gray_rollout.py`：灰度抽样对比
- `phase7_spot_check.py`：单标的抽查
