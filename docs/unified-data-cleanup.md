# 统一失效文件清理

脚本：web/backend/scripts/maintenance/cleanup_stale_data.py。流水线在 meta_info.py 成功后、采集与聚合前调用一次。

直接读取 instrument 中的有效身份（market + asset_class + code），统一处理当前源数据目录、curated 和 chart_payload 的各周期文件。当前范围为 cn/stock、cn/fund（ETF）、cn/index；不是按“本轮没有生成”判断失效。

## 运行

    python web/backend/scripts/maintenance/cleanup_stale_data.py
    python web/backend/scripts/maintenance/cleanup_stale_data.py --apply

默认只预览；--apply 才把失效文件移入数据根下 quarantine/批次目录，不物理删除。

## 必要保护与恢复

- 三类元数据任一为空时拒绝清理；执行前仍需确认 instrument 已正确同步。
- 有效标的即使缺少源数据，也保留其旧 curated 和 chart_payload。
- 只扫描配置的三个运行数据目录；目录必须位于同一数据根且不能互相重叠，历史源目录和隔离目录不能进入清理范围。
- 跳过其他市场/资产类型、符号链接和不识别的文件名，不读取 pickle 内容。
- 隔离保留原相对路径；moves.jsonl 在每次移动前记录源、目标。异常中止时，先核对文件实际位置，再手工移回；不要覆盖已经重新生成的文件。
- 不要与采集、聚合或缓存导出并发执行。

## 改动边界

四个聚合脚本和日线采集不再按本轮产物集合清理旧文件，ETF 源目录也交给本脚本。日线中原有的单标的空数据处理不变。
元数据同步逻辑和默认取数截止日期（END_DATE = None）保持原样，不依赖元数据报告，也不增加交易日联动或独立生命周期框架。

回归测试仅使用临时目录、临时 SQLite 和替身流水线，不清理真实数据：

    python3 -m pytest -q web/backend/tests/test_cleanup_stale_data.py web/backend/tests/test_script_layout.py
