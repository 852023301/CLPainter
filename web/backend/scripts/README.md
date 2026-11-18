# 后端脚本分类与运行说明

本目录按功能分类。只保留一份脚本实现；旧的平铺路径不再保留包装入口。
宿主机继续使用 `CLPainter.web.backend.app...` 导入，本次没有统一或改写包命名空间。

## 功能目录

| 目录 | 用途 | 脚本 |
| --- | --- | --- |
| `data_ingestion/` | 标的元数据与行情采集 | `meta_info.py`、`data_from_tdata_1day.py`、`data_from_tushare_old.py` |
| `aggregation/` | 日线聚合为周/月/季/年线 | `from_1day_to_1week.py`、`from_1day_to_1month.py`、`from_1day_to_1quarter.py`、`from_1day_to_1year.py` |
| `cache/` | 完整计算缓存与图表 payload 导出 | `dump_stock_caches.py` |
| `state/` | 从缓存更新缠论状态快照 | `update_cl_state.py` |
| `validation/` | 不变量校验、结构快照、快照对比 | `check_xianduan_invariants.py`、`snapshot_structures.py`、`compare_structures.py` |
| `maintenance/` | 数据目录初始化与项目进程管理 | `_mkdir.py`、`stop_project.py` |
| `pipelines/` | 完整更新流程编排 | `run_update_pipeline.sh` |
| `archive/phase7/` | Phase 7 历史验收工具 | 原归档位置不变，详见该目录 README |

## 宿主机运行环境

以下命令以 `CLPainter/web/backend` 为工作目录。`PYTHONPATH` 需包含 `CLPainter` 的父目录：

```bash
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
export PYTHONPATH="$(cd ../../.. && pwd)${PYTHONPATH:+:${PYTHONPATH}}"
```

如果本地日志目录不可写，可单独设置 `LOG_FILE=/tmp/clpainter_app.log`。
数据路径由应用设置/环境变量决定；运行写入型脚本前检查 `APP_ENV`、`DATA_DIR`、`OLD_DATA_DIR`、`CACHE_DUMP_DIR` 和 `DB_PATH`。

## 完整更新流水线

```bash
bash scripts/pipelines/run_update_pipeline.sh
```

流水线自动定位工作区根目录并补充 `PYTHONPATH`，支持用 `PYTHON_BIN` 指定解释器。
执行顺序保持为：

1. `data_ingestion/meta_info.py`：同步有效标的元数据。
2. `data_ingestion/data_from_tdata_1day.py`：更新日线。
3. 并行执行 `aggregation/` 中的四个周期转换脚本。
4. `cache/dump_stock_caches.py`：导出缓存。
5. `state/update_cl_state.py`：更新状态快照。

任一步骤失败会阻止后续步骤；聚合阶段会等待全部并行任务结束，任一失败都不会导出缓存。
`data_from_tushare_old.py` 用于补充历史数据，不属于常规日更流水线。

## 单独运行示例

```bash
# 下列 --help 命令只查看参数，不执行导出或状态写库。
python3 scripts/cache/dump_stock_caches.py --help
python3 scripts/state/update_cl_state.py --help
python3 scripts/validation/check_xianduan_invariants.py --help

# 生成/比较结构快照；将占位路径替换为实际目录。
python3 scripts/validation/snapshot_structures.py --dump-dir /path/to/curated --output /tmp/structures.jsonl
python3 scripts/validation/compare_structures.py /tmp/old.jsonl /tmp/new.jsonl

# 仅列出项目进程，不停止。
python3 scripts/maintenance/stop_project.py --list-only
```

## 安全执行注意事项

- `data_ingestion/meta_info.py`、`data_from_tdata_1day.py` 以及四个聚合脚本没有 `--help` 参数；直接运行会进入真实更新流程，不能用它们做无副作用的 CLI 冒烟。
- `maintenance/_mkdir.py` 在执行时会创建数据目录，并递归设置权限；不要把它作为普通导入模块或测试探针。
- `maintenance/stop_project.py` 不带 `--list-only` 会停止匹配的项目进程。
- 不要仅为了验证分类而执行完整流水线或真实采集、全量导出、状态写库。

## 旧路径迁移

原 `scripts/<文件名>` 改为上表中的 `scripts/<功能目录>/<文件名>`。
项目内流水线、开发规范和生产交接命令已同步更新；仓库外的 cron、Airflow、IDE 运行配置或手工命令需要同步到新路径。
