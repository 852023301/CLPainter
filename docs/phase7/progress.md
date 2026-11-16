# Phase 7 不变量驱动修复循环 - 执行记录

## 目标

在不改变默认生产管线的前提下，建立一套可验证的线段修复路径：

- 统一不变量检查
- 原子修复操作
- 新旧结果并行对比
- 全量不变量审计
- 通过 feature flag 灰度启用

默认开关保持关闭。

## 数据路径

早期实验使用：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/curated
```

最终保守模式验证使用生产 raw 的隔离输出：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation_v2/dump/curated
```

## 不变量定义

### 笔

- 方向交替
- 首尾连续
- 确认笔 K 线数量足够
- 区间最高价不超过两端分型最高价
- 区间最低价不低于两端分型最低价

### 线段

- 方向交替
- 首尾连续
- 笔覆盖连续
- 每段至少三笔
- 起点偏离真实极值不超过 `EXTREMUM_REPAIR_THRESHOLD`
- 终点必须是同向笔极值
- 反向笔不能穿透起点

## 初始全量审计

修正不变量定义后，全量 `38850` 个缓存：

```text
bi 违规：0
xd:penetrates_start        2685
xd:end_not_extreme_bi      1971
xd:start_extreme_deviation  511
合计                       5167
```

## 修复操作

### 端点操作

- `move_shared_boundary`
- `move_end_and_next_start`
- `start_extremum_error` 预检查

### 无效段合并

- `merge_invalid_segment_with_next`
- `merge_invalid_segment_with_previous`

### 穿透修复

- `repair_penetrates_start`
- 多笔穿透逐条尝试
- 失败后合并相邻段

### 局部重分段

- `resegment_local_window`
- 窗口半径 1/2/3
- 两段/三段候选
- 候选评分：
  - 窗口外新增违规数
  - 窗口内剩余违规数
  - 新段数
  - 总违规数

## 修复后全量审计

开启修复循环和局部重分段：

```text
xd:penetrates_start         778
xd:end_not_extreme_bi       956
xd:start_extreme_deviation   78
合计                       1812
```

对比初始：

```text
5167 -> 1812
```

整体违规减少约 **65%**。

分项：

- `penetrates_start`：2685 -> 778
- `end_not_extreme_bi`：1971 -> 956
- `start_extreme_deviation`：511 -> 78

没有新增违规类型。

## 新旧并行对比

开启局部重分段后，全量 `38850` 个缓存：

```text
成功 38850，失败 0
bi_changed = 0
xd_changed = 2379
```

## Feature flags

在 `app/_config/settings.py` 中新增：

```python
ENABLE_XIANDUAN_REPAIR_LOOP
ENABLE_XIANDUAN_LOCAL_RESEGMENT
```

默认值均为 `False`。

启用方式：

```bash
export ENABLE_XIANDUAN_REPAIR_LOOP=1
export ENABLE_XIANDUAN_LOCAL_RESEGMENT=1
```

只启用基础修复、不启用局部重分段：

```bash
export ENABLE_XIANDUAN_REPAIR_LOOP=1
export ENABLE_XIANDUAN_LOCAL_RESEGMENT=0
```

回滚：

```bash
unset ENABLE_XIANDUAN_REPAIR_LOOP
unset ENABLE_XIANDUAN_LOCAL_RESEGMENT
```

## 测试

```text
49 passed
```

覆盖：

- 几何工具
- 笔端点工厂
- 不变量检查
- 修复规划器
- S1-S28 回归
- 数据质量占位

## 当前限制

- 默认生产管线未切换，Phase 7 仍为实验路径。
- `end_not_extreme_bi` 仍有 956 个，主要是 `best_at_start` 的无效段。
- 局部重分段成本高于端点修复，建议只在需要时开启。
- 修复后的结果尚未经过人工逐案例确认，建议先灰度。

## 推荐上线方式

1. 先在测试环境设置：

   ```bash
   ENABLE_XIANDUAN_REPAIR_LOOP=1
   ENABLE_XIANDUAN_LOCAL_RESEGMENT=1
   ```

2. 重新生成一批缓存。
3. 用 `phase7_invariant_audit.py` 和 `snapshot_structures.py` 做新旧 diff。
4. 确认目标案例和随机样本无明显异常后，再扩大范围。
5. 生产环境默认保持关闭，直到完成人工验收。


## 灰度验证记录

### 50 个样本，flags 关闭

```text
成功 50，失败 0
bi_changed = 14
xd_changed = 1
old_xd_violations: start=4, penetrates=12, end=12
new_xd_violations: start=4, penetrates=12, end=12
```

说明默认管线行为稳定；`bi_changed=14` 来自 raw 数据与 curated 旧结果的数据漂移，不是 Phase 7 修复导致。

### 50 个样本，flags 开启

```text
成功 50，失败 0
bi_changed = 14
xd_changed = 13
old_xd_violations: start=4, penetrates=12, end=12
new_xd_violations: start=0, penetrates=3, end=9
```

Phase 7 额外改变了 12 个线段结果，整体违规从 28 降到 12。

### 目标案例

开启 flags 后：

- `159577SZ`：违规全部消除
- `159301SZ`：起点偏离消除，穿透仍在
- `159612SZ`：穿透消除，终点极值仍在
- `159843SZ`：起点偏离和穿透消除，终点极值仍在
- `159936SZ`：穿透消除，终点极值仍在
- `000001SZ`：终点极值消除
- `002080SZ`：起点偏离和穿透消除
- `600015SH`：终点极值消除
- `603683SH`：穿透消除

仍有个别案例保留：

- `601116SH`
- `300139SZ`
- `000001SH`

这些属于局部重分段仍未覆盖的复杂案例。

### 灰度期间修复的问题

- 删除状态机重构后遗留的 `repair_xianduan_queue_gaps()` 调用
- 把遗留的 `_adjust_xian_duan(...)` 调用改为 `machine.adjust_pair(...)`
- 修复循环结束后重新分配 `segment.idx`，避免下游线段中枢生成使用旧索引

### 结论

Phase 7 已具备灰度条件：

- 默认关闭时行为稳定
- 开启后目标案例明显改善
- 全量审计违规减少约 65%
- 无新增违规类型
- 50 个样本灰度运行 0 失败


## 扩大灰度：200 和 500 样本

### 200 样本，flags 关闭

```text
成功 200，失败 0
bi_changed = 49
xd_changed = 4
old_xd_violations: start=4, penetrates=20, end=34
new_xd_violations: start=4, penetrates=20, end=34
```

### 200 样本，flags 开启

```text
成功 200，失败 0
bi_changed = 49
xd_changed = 32
old_xd_violations: start=4, penetrates=20, end=34
new_xd_violations: start=0, penetrates=6, end=19
```

违规从 58 降到 25。

### 500 样本，flags 关闭

```text
成功 500，失败 0
bi_changed = 101
xd_changed = 6
old_xd_violations: start=11, penetrates=52, end=63
new_xd_violations: start=11, penetrates=52, end=63
```

### 500 样本，flags 开启

```text
成功 500，失败 0
bi_changed = 101
xd_changed = 69
old_xd_violations: start=11, penetrates=52, end=63
new_xd_violations: start=2, penetrates=16, end=29
```

违规从 126 降到 47，减少约 63%。

`bi_changed` 在 flags 开关前后一致，说明笔结果变化来自 raw 数据与 curated 旧结果的数据漂移，不是 Phase 7 修复导致。

### 灰度结论

200 和 500 样本均 0 失败，目标案例和随机样本表现一致：

- 默认关闭时行为稳定
- 开启后违规显著下降
- 无新增违规类型
- 笔结果不受 Phase 7 影响


## 1000 样本灰度

### flags 关闭

```text
成功 1000，失败 0
bi_changed = 174
xd_changed = 11
old_xd_violations: end=98, start=17, penetrates=92
new_xd_violations: end=98, start=17, penetrates=92
```

### flags 开启

```text
成功 1000，失败 0
bi_changed = 174
xd_changed = 114
old_xd_violations: end=98, start=17, penetrates=92
new_xd_violations: end=47, start=2, penetrates=26
```

违规从 207 降到 75，减少约 64%。

`bi_changed` 在 flags 开关前后完全一致（174），再次确认笔结果不受 Phase 7 影响。

### 1000 样本结论

- 0 失败
- 违规减少约 64%
- 无新增违规类型
- 目标案例和随机样本表现一致
- 笔结果稳定


## 2000 样本灰度

### flags 关闭

```text
成功 2000，失败 0
bi_changed = 370
xd_changed = 26
old_xd_violations: end=174, start=34, penetrates=189
new_xd_violations: end=174, start=34, penetrates=189
```

### flags 开启

```text
成功 2000，失败 0
bi_changed = 370
xd_changed = 220
old_xd_violations: end=174, start=34, penetrates=189
new_xd_violations: end=81, start=6, penetrates=51
```

违规从 397 降到 138，减少约 65%。

`bi_changed` 在 flags 开关前后完全一致（370），笔结果稳定。

### 2000 样本结论

- 0 失败
- 违规减少约 65%
- 无新增违规类型
- 目标案例和随机样本表现一致
- 笔结果不受影响


## 全量重算（隔离目录）

为避免覆盖生产 curated，使用独立数据根：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev_phase7
```

其中：

- `pv_data`、`old_pv_data`、`instrument.db` 软链到 `data_set_dev`
- `dump/curated` 和 `dump/chart_payload` 是独立目录

启用：

```bash
ENABLE_XIANDUAN_REPAIR_LOOP=1
ENABLE_XIANDUAN_LOCAL_RESEGMENT=1
```

全量导出结果：

```text
成功 38855，失败 0
```

## 全量重算后的不变量审计

新目录：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev_phase7/dump/curated
```

结果：

```text
xd:end_not_extreme_bi       956
xd:penetrates_start         775
xd:start_extreme_deviation   77
合计                       1808
```

对比旧基线：

```text
5167 -> 1808
```

整体违规减少约 **65%**。

## 全量快照 diff

旧快照：38850 个缓存  
新快照：38855 个缓存

```text
added:   5
removed: 0
changed: 10572
```

注意：这个 diff 同时包含：

- raw 数据相对旧 curated 的数据漂移
- 笔结果变化
- Phase 7 线段修复

不是纯 Phase 7 差异。  
纯 Phase 7 影响以 2000 样本灰度对比为准：

```text
flags off: xd_changed=26
flags on:  xd_changed=220
```

## 全量重算结论

- 全量 38855 个缓存导出 0 失败
- 新结果不变量违规 1808，较旧基线减少约 65%
- 生产 curated 未被覆盖
- Phase 7 已具备进入人工验收的条件


## 生产 data_set 隔离验证

使用生产 raw 数据：

```text
/mnt/DataDepartmentTest/home/wjl/data_set
```

隔离输出：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation
```

全量导出：

```text
成功 38860，失败 0
```

### 生产基线审计

```text
xd:penetrates_start        2685
xd:end_not_extreme_bi      1968
xd:start_extreme_deviation  511
合计                       5164
```

### 生产验证结果审计

```text
xd:end_not_extreme_bi       956
xd:penetrates_start         775
xd:start_extreme_deviation   77
合计                       1808
```

违规减少约 65%。

### 生产快照 diff

```text
old: 38860  new: 38860
added: 0  removed: 0  changed: 3180
```

## 可视化验收报告

生成脚本：

```text
CLPainter/web/backend/scripts/phase7_visual_report.py
```

报告目录：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report
```

访问地址：

```text
http://172.17.1.5:15002/
```

报告包含：

- S1-S28 目标案例
- 灰度中变化的目标案例
- 3180 个变化案例中的分层抽样
- 未变化控制样本

每个案例包含：

- Old / New 两张并排图
- 笔和线段
- 线段端点表
- 变化行高亮
- 旧/新不变量违规列表


## 可视化报告更新：变化笔/线段高亮

- 变化笔：紫色 `#9c27b0`
- 变化线段：橙色 `#ff9800`
- Old 线段：红色
- New 线段：绿色
- 笔：蓝色

主报告仍包含未变化控制样本：

```text
http://172.17.1.5:15002/
```

只看变化案例的报告：

```text
http://172.17.1.5:15002/changed/
```


## AGENTS.md 更新

已将“大规模修改的可视化人工审核”流程写入：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/AGENTS.md
```

内容包括：

- 新旧快照与 diff
- 可视化报告生成
- 颜色约定
- 分层案例集
- 人工审核步骤
- 隔离数据目录
- 验收通过后的推进顺序


## 可视化抽查后的修正

抽查发现 Phase 7 修复循环没有严格遵循旧版特征序列定义，已做以下修正：

### 新增特征序列不变量

- `right_tzxl_exceeds_left`：下降段右侧特征序列第 2、3 笔最高点不能超过左侧特征序列最高点
- `right_tzxl_below_left`：上升段右侧特征序列第 2、3 笔最低点不能低于左侧特征序列最低点

第一笔允许超过；后续笔的阈值规则暂未自动修复。

### 新增 tzxl 一致性检查

- `segment_tzxl_consistent`：线段的 `start_bi_idx` / `end_bi_idx` 必须与 `left_tzxl` / `right_tzxl` 一致
- `right_tzxl_rule_ok`：移动端点后必须仍满足右侧特征序列规则
- 任何移动如果导致 tzxl 不一致或违反特征序列规则，都会回滚

### 关闭改变线段总数的修复

默认：

```python
allow_count_changing_repairs = False
use_local_resegment = False
```

即默认不允许：

- 合并相邻标准段
- 删除标准段
- 局部重分段

只允许保持线段总数不变的端点调整。

### 12 个抽查案例复跑结果

使用修正后的保守修复循环：

```text
600996SH  未变化
300353SZ  未变化
000750SZ  未变化
600015SH  未变化
600713SH  未变化
000001SZ  未变化
603683SH  未变化
159577SZ  未变化
159301SZ  未变化
159612SZ  未变化
159843SZ  未变化
```

所有旧版标准段都被保留，没有引入新的 `right_tzxl_exceeds_left` / `right_tzxl_below_left`。

### 仍存在的问题

- `159577SZ` 仍缺反向延长 fake 段 `20240422 ~ 20250107`，属于 fake 段逻辑，不是标准段修复循环。
- 之前生成的 `data_set_phase7_validation` 结果基于激进修复循环，已不再作为验收结果。
- 需要在保守修复循环下重新生成验证数据。

## 保守模式复核与 159577SZ 修复

### 代码修正

1. `phase7_parallel_compare.py` 和 `phase7_invariant_audit.py` 不再在旧缓存线段上原地修复，改为从旧管线重新生成线段。这样 fake 首段/尾段等生成阶段结构会被重新计算。
2. `XianDuanInvariants` 增加右侧特征序列第 2、3 笔检查的单元测试：
   - 第一笔允许超过左侧极值；
   - 第二、第三笔超过左侧极值时报 `right_tzxl_exceeds_left` / `right_tzxl_below_left`。
3. 第四笔及以后暂不做跨线段扫描。当前 `TeZhengXuLie` 只保留合并后的 3 个组件；跨到下一个同向线段会把后续趋势误判为违规（1000 样本中误报 462 个），因此保留为后续扩展 `TeZhengXuLie` 全量组件后再实现。

### 生产数据抽查

使用生产 raw 数据只读、隔离输出：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation_v2
```

开启：

```bash
ENABLE_XIANDUAN_REPAIR_LOOP=1
ENABLE_XIANDUAN_LOCAL_RESEGMENT=0
```

12 个用户抽查项（11 个唯一标的，`600015SH` 同时对应 S9/S24）结果：

```text
600996SH  保留 2024-11-08 ~ 2025-04-09
300353SZ  未变化
000750SZ  保留 2024-10-09 ~ 2025-04-09，并补出 FakeXianDuanFirst
600015SH  保留 2023-06-26 ~ 2025-07-10、2025-07-10 ~ 2026-08-31
600713SH  保留 2024-12-16 ~ 2025-04-09
000001SZ  保留 2025-04-07 ~ 2025-07-10、2025-07-10 ~ 2026-07-01
603683SH  保留 2024-02-08 ~ 2025-09-25
159577SZ  补出 FakeXianDuanFirst 2024-04-22 ~ 2025-01-07
159301SZ  不再出现 2026-05-14 ~ 2026-07-09
159612SZ  保留 2023-01-06 ~ 2025-03-24
159843SZ  保留 2025-08-26 ~ 2026-06-29
```

新增复核脚本：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/phase7_spot_check.py
```

旧生产 curated 上运行结果为 1 个失败（159577SZ 缺 fake 首段）；新隔离目录中该案例已修复。

### 测试

```text
69 passed, 4 skipped
```

## 最终保守模式全量验证（2026-11-12）

### 数据隔离

生产 raw 数据只读，输出隔离目录：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation_v2
```

生产 curated 未覆盖。

### 全量导出

```text
成功 38860，失败 0
```

### 结构 diff

排除内部 `idx` 字段后，真正的结构差异为：

```text
old: 38860  new: 38860
added: 0  removed: 0  changed: 313
bi_changed: 0
xd_changed: 313
```

313 个变化中：

```text
新增 fake 首段：287
线段数量不变、端点/边界调整：26
线段数量减少：0
```

287 个新增 fake 首段已全部自动校验：至少 3 笔、方向与下一段相反、终点与下一段起点连续、笔索引连续，全部通过。

按周期：

```text
freq=1day     213
freq=1week     92
freq=1month     8
```

按资产类别：

```text
stock  236
index   41
fund    36
```

### 全量不变量审计

旧生产 curated：

```text
penetrates_start         2685
end_not_extreme_bi       1968
right_tzxl_below_left     868
right_tzxl_exceeds_left   576
start_extreme_deviation   511
合计                     6608
```

新隔离结果：

```text
penetrates_start         2391
end_not_extreme_bi       1955
right_tzxl_below_left     865
right_tzxl_exceeds_left   574
start_extreme_deviation   355
合计                     6140
```

整体减少 468，约 7.1%。保守模式不再追求激进降低违规数，优先保证旧版标准线段不被破坏。

### 26 个同数量边界调整

- 13 个案例违规减少；
- 13 个案例违规数保持不变；
- 没有新增违规类型；
- 没有线段数量减少。

### 人工抽查

12 个用户抽查项（11 个唯一标的）全部通过：

```text
spot check failures: 0
```

报告目录：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_spot
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_same_count
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_fake_first
```

全量变化清单：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_changed_cases_v2.jsonl
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_changed_cases_v2_summary.json
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_same_count_review.csv
```

### 测试

```text
73 passed, 4 skipped
```

### 当前结论

- 保守模式已经可以在生产 raw 数据上全量跑通；
- 159577SZ 的反向延长 fake 段已恢复；
- 用户指出的 600996SH、000750SZ、600015SH、600713SH、000001SZ、603683SH、159301SZ、159612SZ 等案例均保持旧版标准段；
- 313 个结构变化中，287 个是补 fake 首段，26 个是保持数量的边界调整；
- 生产默认开关仍为关闭，尚未切换生产。

## 测试环境切换（2026-11-12）

- 测试容器：`CLPainter`
- 容器代码备份：`/root/CLPainter_backup_20261112`
- 容器兼容缓存：`/mnt/DataDepartmentTest/home/wjl/data_set_dev_phase7_v2`
- 容器内全量导出：成功 38860，失败 0
- 容器 `DEFAULT_DATA_ROOT` 已切到新缓存目录
- gunicorn 已平滑重启
- API 冒烟：159577SZ、600996SH、159301SZ 均返回 200
- `159577SZ` 页面 `xdData` 已包含 `2024-04-22 -> 2025-01-07`
- `600996SH` 页面 `xdData` 已包含 `2024-11-08 -> 2025-04-09`
- `159301SZ` 页面 `xdData` 不包含 `2026-05-14 -> 2026-07-09`

## 报告访问

```text
http://172.17.1.5:15003/phase7_visual_report_v2_spot/
http://172.17.1.5:15003/phase7_visual_report_v2_same_count/
http://172.17.1.5:15003/phase7_visual_report_v2_fake_first/
```

## 首段 fake/real 修复（2026-11-13）

人工抽查发现首段存在三类问题：

1. 旧版真实首段被标成 fake；
2. fake 首段前面还可以递归补 fake；
3. fake 上升段起点落在上升笔终点，非法。

已新增：

- `reconcile_first_segments`：用旧缓存首段作为迁移锚点；
- `_prepend_recursive_fakes`：递归补首段 fake；
- `_normalize_first_fake`：校正 fake 起止点到合法笔边界；
- `promote_secondary_fakes`：连续 fake 从第二条开始，满足标准线段定义就转为真实线段；
- `_load_pickle_compatible`：容器兼容宿主机 pickle 模块路径。

纯算法对比：

```text
xd_changed: 3603
first_only: 3267
body_changed: 336
```

所有变化只在首段，首段之后完全一致。

用户点名案例：

```text
000750SZ  Fake down 1997-07-15~1997-08-21
          Real up   1997-08-21~1998-01-08
          Real down 1998-01-08~1999-12-29
300265SZ  Fake down 2011-09-16~2013-06-25
          Real up   2013-06-25~2015-05-27
159663SZ  Fake up   2022-10-31~2023-02-08
          Real down 2023-02-08~2024-02-05
510560SH  Fake up   2015-07-09~2017-03-21
          Real down 2017-03-21~2018-10-19
159518SZ  Fake down 2023-11-15~2023-12-13
          Real up   2023-12-13~2024-07-18
          Real down 2024-07-18~2025-04-09
```

测试服务已切到宿主机 v3 结果，容器通过兼容 loader 直接读取。

报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_first_segment/
```

## 右侧特征序列第 4 笔及以后（2026-11-13）

新增 `_right_tzxl_extra_bis`：

- 只扫描当前 `right_tzxl` 的 `left_bi_idx` 到 `right_bi_idx`；
- 只取未进入 3 个组件的同向笔；
- 下降段检查最高点，上升段检查最低点；
- 超出左侧极值但未超过 `EXTREMUM_REPAIR_THRESHOLD` 时允许；
- 超出阈值报告 `right_tzxl_later_exceeds_left`。

1000 样本审计新增 5 个违规；全量审计 `right_tzxl_later_exceeds_left: 201`，没有跨线段误报。


全量 3267 个仅首段变化报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_first_only/
```

## 连续 FakeXianDuanFirst 收敛（2026-11-13）

规则：首段连续 fake 从后往前尝试转真实；某条不能转真实时，保留这一条，删除它前面的所有 fake。最终首段最多一条 fake。

全量扫描：

```text
consecutive_fake_cases: 0
```

`560690SH` 已收敛为：

```text
Fake down 2024-07-09 ~ 2024-09-09
Real up   2024-09-09 ~ 2025-02-21
```


199 个 `right_tzxl_later_exceeds_left` 缓存（201 个违规）报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_later_exceeds/
```

### `right_tzxl_later_exceeds_left` 有变化案例

199 个唯一缓存：

```text
unchanged_both: 144
changed_both: 55
```

有变化报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_later_exceeds_changed/
```

## 全局 FakeXianDuanFirst 收敛（2026-11-14）

全序列最多一条 FakeXianDuanFirst：从右往左处理，能转真实就转；不能转真实则保留该条并删除左侧所有线段。

全量扫描：`multi_fake_cases: 0`。

可视化报告同步改进：表格只标黄新增线段；图表聚焦最早差异时间点。

## 2026-11-14 续接记录

- 补齐剩余 6 个人工确认拆分：`688611SH`、`300290SZ`、`002045SZ`、`600188SH`、`600502SH`、`600333SH`。
- 新增 `postprocess_xian_duan()`，统一服务、对比脚本和审计脚本的线段后处理顺序。
- 新增实验性通用合法拆分搜索 `legal_splits.py`，通过 `ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1` 启用，默认关闭。
- 修正回归测试基线：S15 数据日期推进；S24/S27 新 fake 首段；S25 尾部 real/fake 归属。
- 测试结果：`82 passed, 4 skipped`。
- 已启动测试环境全量 dump，输出到 `/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/curated`。

## 2026-11-14 全量验证结果

- 测试环境全量 dump：成功 38855，失败 0。
- 清理旧缓存 `561970SH` 五个周期，移动到 `dump/stale_20261114`。
- 测试：`82 passed, 4 skipped`。
- 纯算法对比：`xd_changed=3605`，`first_only=3569`，`body_changed=36`，`bi_changed=0`。
- 全量缓存对比（含数据漂移）：`changed=4141`，`first_only=3382`，`body_changed=759`，`multi_fake=0`。
- 不变量审计：不含 later_exceeds 为 `6603 -> 6613`，含 later_exceeds 为 `6804 -> 6812`，无新增违规类型。
- 新报告：`phase7_visual_report_v4_body_changed`、`phase7_visual_report_v4_later_exceeds_changed`、`phase7_visual_report_v4_first_only`。
- API 冒烟：6 个新增拆分标的均返回 200，`xdData` 已确认。

## 2026-11-14 人工验收与 shadow 验证

- 用户确认 `phase7_visual_report_v4_body_changed_other` 全部无问题。
- 用户确认 `phase7_visual_report_v4_later_exceeds_changed` 全部无问题。
- v4 冻结为当前候选版本，冻结信息写入 `phase7_v4_freeze.json`。
- 启动独立 shadow 全量 dump，验证 `ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1`：
  - 输出：`/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_shadow`
  - 参考：已验收的 v4 `dump/curated`
  - 不影响 v4 主目录。

## 2026-11-14 通用合法拆分 shadow 结果

- shadow 全量 dump：成功 38855，失败 0。
- 相对 v4 仅变化 9 个案例：1 个 first_only，8 个 body_changed。
- 不变量总数下降：不含 later_exceeds `6613 -> 6596`，含 later_exceeds `6812 -> 6789`。
- 报告：`http://172.17.1.5:15003/phase7_visual_report_shadow_legal_split/`
- 通用搜索仍默认关闭，等待人工确认。

## 2026-11-14 v5 候选版本

- 启用 `ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1`，保留 `300327SZ` 显式拆分。
- v5 全量 dump：成功 38855，失败 0。
- 测试：`83 passed, 4 skipped`。
- v5 相对 v4 仅变化 9 个案例：1 first_only / 8 body_changed。
- 纯算法对比：`xd_changed=3612`，`first_only=3568`，`body_changed=44`，`bi_changed=0`。
- v5 审计：`penetrates=2670, end=1985, below=865, exceeds=575, start=501, later=193`。
- v5 报告已生成，冻结信息写入 `v5_freeze.json`。

## 2026-11-14 测试容器切换到 v5

- 同步容器代码：`datacube.py`、`confirmed_splits.py`、`legal_splits.py`、`settings.py`。
- 容器备份：`/root/CLPainter_backup_20261114_203111`。
- 容器实际配置文件为 `/root/CLPainter/web/backend/.env`，已指向 `dump_v5/curated`。
- gunicorn 平滑重启，启动日志确认 `Environment: test`、`Cache Dir: dump_v5/curated`。
- API 冒烟 9 个标的全部 200，`300327SZ` 和 `688611SH` 的 `xdData` 已确认。

## 2026-11-14 P1 完成

- v5 人工验收通过。
- 测试容器切换到 `dump_v5/curated`。
- 容器代码同步并平滑重启。
- API 冒烟通过。
- 提交：`当前 HEAD：完成 Phase 7 v5 通用拆分与测试环境切换`。

## 2026-11-14 P2 代码整合

- 新增 `_make_fake_last()`，统一 fake 尾段构造。
- fake 首段构造统一复用 `_make_fake_first()`。
- 修复整合中发现的 `FakeXianDuanLast` 兼容问题。
- p2 全量 dump：成功 38855，失败 0。
- 测试：`83 passed, 4 skipped`。
- v5 与 p2 snapshot 完全一致：
  `565d9de47f23ce94458a92f115f291d7ccad38eccc8580af28c931ceaf4823e1`
- 不变量审计与 v5 完全一致。

- P2 重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-14 P2 第二轮

- 新增 `_find_extreme_start_bi_index()`，统一首段极值起点搜索。
- p3 全量 dump：成功 38855，失败 0。
- v5 与 p3 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P2 第二轮重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-14 P2 第三轮

- 合并 `repair_first_segment_reverse_extension()` 的上升/下降重复分支。
- p4 全量 dump：成功 38855，失败 0。
- v5 与 p4 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P2 第三轮重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 P2 第四轮

- 将 `validate_xianduan_structure` 和 `repair_first_segment_reverse_extension` 提升为模块级函数。
- p5 全量 dump：成功 38855，失败 0。
- v5 与 p5 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

## 2026-11-15 P2 第五轮

- 新增 `_find_tzxl_by_start_time()` 和 `_make_earliest_candidate()`。
- 统一首段 fake 候选构造。
- p6 全量 dump：成功 38855，失败 0。
- v5 与 p6 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

## 2026-11-15 P2 第六轮

- 新增 `_find_extreme_end_bi_index()`，统一 fake 尾段极值搜索。
- p7 全量 dump：成功 38855，失败 0。
- v5 与 p7 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P2 第六轮重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 P2 第七轮

- 抽取 `_build_fake_boundaries()`，缩短 `generate_xian_duan()`。
- p8 全量 dump：成功 38855，失败 0。
- v5 与 p8 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P2 第七轮重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 P2 第八轮

- `bi.py` 尾段极值搜索复用 `range_extreme_indices()`。
- 清理 `bi.py`、`xianduan.py` 注释中的具体标的/日期示例。
- p9 全量 dump：成功 38855，失败 0。
- v5 与 p9 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P2 第八轮 `bi.py`、`xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 决策：保留白名单

- 保留 `confirmed_splits.py`，不删除。
- 通用合法拆分搜索继续作为实验能力，默认关闭。
- 原因：多数人工确认案例存在多个合法候选，通用化需要额外评分器，复杂度和回归风险过高。

## 2026-11-15 P4 与收尾

- 抽取 `_build_fake_last_bi()`，缩短 `generate_bi()`。
- p10 全量 dump：成功 38855，失败 0。
- v5 与 p10 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。
- 删除 `dump_shadow`、`dump_p2~p12`、`instrument_p9.db`、`instrument_p11.db`，释放约 780G。
- 非 Phase 7 的 docker-compose / deploy / .env 改动保持不动。
- 生产交接文档：`handoff.md`。

- P4 抽取后的 `bi.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 P4 续

- 抽取 `_build_fake_front_bi()` 和 `_repair_initial_fake_front_bi()`。
- 修复抽取时遗漏的 `make_fake_front_bi()` 调用。
- p11 全量 dump：成功 38855，失败 0。
- v5 与 p11 snapshot 完全一致。
- 测试：`83 passed, 4 skipped`。

- P4 续抽取后的 `bi.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 风险修复、数据质量测试与性能优化

- 风险 2：assert 改为显式 AssertionError。
- 风险 3：参考缓存读取失败记录 warning。
- 风险 4：确认拆分未匹配/不连续记录 warning。
- 风险 5：后处理顺序改为 promote -> confirmed -> legal search。
- 数据质量测试 4 个 skip 改为真实断言，测试 `87 passed, 0 skipped`。
- cProfile 定位 `split_bi_by_internal_extreme` 热点，使用 bisect 优化。
- `generate_bi` 典型提升约 2~12 倍。
- p12 全量 dump：成功 38855，失败 0。
- v5 与 p12 snapshot 完全一致。

## 2026-11-15 风险修复

- 将 `fenxing.py`、`merged_kline.py`、`tezhengxulie.py` 的 assert 改为显式 RuntimeError。
- 确认参考缓存加载失败会记录 warning。
- 确认白名单匹配失败会记录 warning。
- 确认当前后处理顺序为 reconcile -> promote -> apply -> search。
- p12 全量 dump：成功 38855，失败 0。
- 测试：`87 passed, 0 skipped`。
- v5 与 p12 snapshot 完全一致。

- 数据质量测试移除 skipif，数据缺失时改为明确失败。
- 当前测试：`87 passed, 0 skipped`。

## 2026-11-15 P4 继续拆分

- 从 `generate_bi()` 抽取 `_completed_merged_count()`、`_opening_span_is_long_enough()`、`_prepend_opening_up_bi_to_qualifying_top()`、`_prepend_opening_down_bi_to_lowest_bottom()`、`_make_opening_bi()`、`_bis_after_endpoint()`、`_install_opening_bi()`、`_opening_bi_sequence_is_valid()`。
- 从 `generate_bi()` 抽取 `_split_bi_by_internal_extreme()`、`_prepend_initial_extreme_bi()`、`_supplement_last_fake_bi_with_reverse_bi()`。
- 从 `generate_xian_duan()` 抽取 `_start_extremum_error()`、`_find_tzxl_by_time()`、`_get_right_tzxl()`、`_set_left_tzxl()`、`_set_right_tzxl()`、`_repair_xianduan_extremes()`、`_split_bi_range()`、`_repair_uncovered_prefix()`、`_repair_xianduan_endpoint_extremes()`、`_make_local_xianduan()`、`_repair_xianduan_endpoints_and_wraparound()`。
- `generate_bi()`：703 行 -> 238 行。
- `generate_xian_duan()`：855 行 -> 472 行。
- p4final 全量 dump：成功 38855，失败 0。
- v5 与 p4final snapshot：`changed: 0`。
- 测试：`87 passed, 0 skipped`。
- 提交：`73ec610 继续拆分笔与线段生成函数的嵌套辅助逻辑`。
- 重构后的 `bi.py`、`xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 P7 旧备份清理

- 删除 `dump/curated_backup_20261114`、`dump/chart_payload_backup_20261114`，释放约 68G。
- 删除 `dump_p4a`、`dump_p4a2`、`dump_p4bc`、`dump_p4final`、`dump_p4a_sample`、`dump_p4a_debug`、`dump_p4bc_sample`，释放约 213G。
- 删除 `instrument_p4a.db`、`instrument_p11.db*`、`instrument_p12.db*`、`instrument_p9.db*` 残留。
- 保留 `dump/curated`、`dump/chart_payload`（v4 回滚）与 `dump_v5`（当前测试环境）。
- 当前占用：`dump` 71G，`dump_v5` 70G。

## 2026-11-15 P4 续二：线段 fake 边界辅助逻辑

- 从 `generate_xian_duan()` 抽取 `_make_fake_last_after_xianduan()`、`_make_fake_first_before_xianduan()`、`_extend_confirmed_segment_past_penetrated_tail()`、`_make_fake_first_reverse_segment()`、`_merge_penetrated_fake_tail()`、`_merge_penetrated_opposite_segments()`、`_find_confirmed_xianduan_pair()`。
- `generate_xian_duan()`：472 行 -> 222 行，已无嵌套函数。
- p4d 全量 dump：成功 38855，失败 0。
- v5 与 p4d snapshot：`changed: 0`。
- 测试：`87 passed, 0 skipped`。
- 提交：`6ec27d9 继续拆分线段 fake 边界辅助逻辑`。
- 重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟通过。

## 2026-11-15 v5 first_only 全量报告

- 使用 `phase7_v5_first_only_cases.jsonl` 生成 v5 `first_only` 全量报告。
- 案例数：3568。
- 报告目录：`phase7_visual_report_v5_first_only`，约 1.3G。
- index 链接数：3568。
- 访问地址：`http://172.17.1.5:15003/phase7_visual_report_v5_first_only/`。

## 2026-11-15 v5 验收通过

- 用户确认 v5 可以验收。
- 验收范围：v5 全量缓存 + v5 `first_only` 全量报告。
- v5 状态更新为 `accepted`。
- 保留 v4 回滚目录：`dump/curated`、`dump/chart_payload`。
- 生产部署仍为手动执行，按 `handoff.md` 进行。

## 2026-11-15 测试目录收尾

- 删除历史验证目录：`data_set_dev_phase7`、`data_set_dev_phase7_v2`、`data_set_dev_phase7_v3`、`data_set_phase7_validation`、`data_set_phase7_validation_v2`。
- 删除 `data_set_dev/data_set_dev` 嵌套副本。
- 删除旧 `data_set_dev/dump`（v4 回滚）。
- 将 `data_set_dev/dump_v5` 改名为 `data_set_dev/dump`。
- 测试容器 `CACHE_DUMP_DIR` 更新为 `/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/curated`。
- 改名后全量 snapshot 与 v5 基线一致：`changed: 0`。
- 当前测试数据：`dump/curated` 38855，`dump/chart_payload` 38855。
- 当前不再保留本地 v4 回滚缓存。

## 2026-11-15 CLPainter 项目内部整理

- 保留运行时与测试：
  `web/backend/app/toolbox/confirmed_splits.py`、
  `web/backend/app/toolbox/legal_splits.py`、
  `web/backend/tests/test_confirmed_splits.py`、
  `web/backend/tests/test_legal_splits.py`。
- 归档维护脚本到 `web/backend/scripts/archive/phase7/`：
  `phase7_classify_changes.py`、`phase7_invariant_audit.py`、
  `phase7_parallel_compare.py`、`phase7_visual_report.py`。
- 删除全部可视化报告、分类目录、cases JSONL、summary JSON、CSV 和
  `run_phase7_after_delay.sh`。
- 保留文档与冻结清单：`acceptance.md`、`handoff.md`、
  `v5_freeze.json`、`CODE_CHANGE_STANDARD.md`、`AGENTS.md`、
  `progress.md`；`phase7_production_deploy.md` 已合并到 `handoff.md` 并删除。
- `v5_freeze.json` 在删除清单中也出现过，但按保留清单处理，未删除。

## 2026-11-15 归档剩余一次性脚本

- `phase7_first_segment_check.py`
- `phase7_gray_rollout.py`
- `phase7_spot_check.py`

以上脚本已归档到 `web/backend/scripts/archive/phase7/`。

## 2026-11-15 合并生产部署文档

- `phase7_production_deploy.md` 的前置条件和导入路径注意事项已合并到 `handoff.md`。
- `phase7_production_deploy.md` 已删除。

## 2026-11-16 运行时去 phase7 前缀与目录整理

- `phase7_confirmed_splits.py` 改名为 `confirmed_splits.py`。
- `phase7_legal_splits.py` 改名为 `legal_splits.py`。
- 对应测试改名为 `test_confirmed_splits.py`、`test_legal_splits.py`。
- `datacube.py` 导入路径同步更新。
- 文档移动到 `docs/phase7/`：`acceptance.md`、`handoff.md`、`progress.md`、`v5_freeze.json`。
- 归档脚本移动到 `web/backend/scripts/archive/phase7/`。
- 全量 dump：成功 38855，失败 0。
- 与 v5 基线 snapshot：`changed: 0`。
- 测试：`87 passed, 0 skipped`。
- 测试容器已同步新模块名并平滑重启，API 冒烟通过。

## 2026-11-16 Docker Compose 生产/测试服务隔离

- 新增 `docker/entrypoint.sh`，同时启动 gunicorn 与 sshd。
- `docker-compose.yml` 作为公共配置。
- `docker-compose.prod.yml`、`docker-compose.test.yml` 分别注入生产/测试环境文件、容器名和端口。
- 新增 `deploy/up-test.sh`、`deploy/up-prod.sh`、`deploy/down-test.sh`、`deploy/down-prod.sh`。
- 生产端口：SSH 36602 / HTTP 15000。
- 测试端口：SSH 36603 / HTTP 15001。
- `docker compose config` 和 `up --dry-run` 均通过。

- 新增 `deploy/build.sh`，统一构建生产/测试共用镜像。
- 旧容器 `CLPainter` 代码是手工同步的，迁移到 compose 前需要重建镜像并重建测试容器。
