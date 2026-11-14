# Phase 7 保守模式验收摘要（2026-11-12）

## 数据

- 生产 raw：`/mnt/DataDepartmentTest/home/wjl/data_set`（只读）
- 隔离输出：`/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation_v2`
- 生产 curated 未被覆盖

## 全量结果

```text
导出：成功 38860，失败 0
结构 diff：changed 313
bi_changed：0
xd_changed：313
```

313 个变化：

```text
新增 fake 首段：287
线段数量不变、边界调整：26
线段数量减少：0
```

287 个新增 fake 首段已全部自动校验：

- 至少 3 笔；
- 方向与下一段相反；
- 终点与下一段起点连续；
- 笔索引连续；
- 全部通过。

## 不变量审计

```text
旧：6608
新：6140
减少：468（约 7.1%）
```

没有新增违规类型。

## 用户抽查

12 个抽查项（11 个唯一标的）全部通过：

```text
spot check failures: 0
```

重点确认：

- `600996SH` 保留 `2024-11-08 ~ 2025-04-09`
- `000750SZ` 保留 `2024-10-09 ~ 2025-04-09`
- `600015SH` 保留 `2023-06-26 ~ 2025-07-10`、`2025-07-10 ~ 2026-08-31`
- `000001SZ` 保留 `2025-04-07 ~ 2025-07-10`、`2025-07-10 ~ 2026-07-01`
- `159301SZ` 不再出现 `2026-05-14 ~ 2026-07-09`
- `159577SZ` 补出 `FakeXianDuanFirst 2024-04-22 ~ 2025-01-07`

## 可视化报告

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_spot
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_same_count
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_visual_report_v2_fake_first
```

## 全量变化清单

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_changed_cases_v2.jsonl
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_changed_cases_v2_summary.json
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_same_count_review.csv
```

## 测试

```text
73 passed, 4 skipped
```

## 当前状态（历史记录，最新结果见文末）

- 保守模式已全量跑通；
- 测试环境已切换到新缓存，并完成 API 冒烟；
- 生产默认开关仍关闭，生产 curated 未覆盖；
- 3267 个首段变化已按你的规则推广；
- 336 个 body_changed 案例需要单独复核：
  `http://172.17.1.5:15003/phase7_visual_report_v3_body_changed/`
- 确认后再按 `phase7_production_deploy.md` 协调生产更新。

## 右侧特征序列第 4 笔及以后

已实现 `_right_tzxl_extra_bis`：

- 只扫描当前 `right_tzxl` 的 `left_bi_idx` 到 `right_bi_idx` 区间；
- 只取未进入 3 个组件的同向笔；
- 对下降段检查最高点，对上升段检查最低点；
- 超出左侧极值但未超过 `EXTREMUM_REPAIR_THRESHOLD` 时允许；
- 超出阈值时报告 `right_tzxl_later_exceeds_left`。

1000 样本审计中新增 5 个违规；全量审计新增：

```text
right_tzxl_later_exceeds_left: 201
```

没有跨线段误报。这 201 个需要决定是继续修复还是接受为提示。

## 测试环境切换

### 容器代码

测试容器 `CLPainter` 的代码已同步到当前版本。

切换前备份：

```text
/root/CLPainter_backup_20261112
```

容器内代码已把 `CLPainter.web.backend.app...` 导入改为 `app...`，以匹配容器运行方式。

### 容器内兼容缓存

宿主机生成的 pickle 使用 `CLPainter...` 模块路径，容器无法直接反序列化。
已在容器内重新生成容器兼容缓存：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev_phase7_v2
```

该目录的 `pv_data`、`old_pv_data`、`instrument.db` 软链到生产 `data_set`，只读使用；写入只发生在 `dump/curated` 和 `dump/chart_payload`。

容器内全量导出：

```text
成功 38860，失败 0
```

### 测试服务切换

容器 `settings.py` 的 `DEFAULT_DATA_ROOT` 已改为：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev_phase7_v2
```

gunicorn master 已执行 `kill -HUP` 平滑重启。

### API 冒烟测试

```text
159577SZ 1day fund  200
600996SH 1day stock 200
159301SZ 1day fund  200
```

页面内 `xdData` 已确认：

- `159577SZ` 包含 `2024-04-22 -> 2025-01-07` fake 首段；
- `600996SH` 包含 `2024-11-08 -> 2025-04-09`；
- `159301SZ` 的 `xdData` 不包含 `2026-05-14 -> 2026-07-09`。

### 回滚

恢复容器代码：

```bash
docker exec CLPainter bash -lc 'rm -rf /root/CLPainter && mv /root/CLPainter_backup_20261112 /root/CLPainter'
```

恢复测试数据根：

```bash
docker exec CLPainter bash -lc 'sed -i "s#data_set_dev_phase7_v2#data_set_dev#" /root/CLPainter/web/backend/app/_config/settings.py'
docker exec CLPainter bash -lc 'kill -HUP <gunicorn-master-pid>'
```

### 随机冒烟

从 313 个变化案例中随机抽取 10 个，通过测试服务 API 请求，全部返回 200：

```text
600418SH 1day stock
000750SZ 1day stock
688171SH 1day stock
515700SH 1day fund
000827SH 1day index
300210SZ 1week stock
399037SZ 1day index
603021SH 1day stock
600721SH 1week stock
516190SH 1day fund
```

## 生产部署清单

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_production_deploy.md
```

## 报告访问

静态报告服务：

```text
http://172.17.1.5:15003/phase7_visual_report_v2_spot/
http://172.17.1.5:15003/phase7_visual_report_v2_same_count/
http://172.17.1.5:15003/phase7_visual_report_v2_fake_first/
```

> 注意：当前测试容器的代码和 `settings.py` 改动在容器层。如果容器被删除重建，需要重新同步代码，或把改动构建进镜像。

## 首段 fake/real 修复（2026-11-13）

针对人工抽查指出的首段问题，新增：

- 旧缓存首段参考 `reconcile_first_segments`
- fake 首段递归前置 `_prepend_recursive_fakes`
- fake 起止点合法性校正 `_normalize_first_fake`
- 旧缓存 pickle 模块路径兼容 `_load_pickle_compatible`

### 结果

纯算法对比（同一份旧 bi/tzxl，不混入数据漂移）：

```text
xd_changed: 3603
first_only: 3267
body_changed: 336
```

3267 个变化只发生在首段；336 个案例在首段之后还有线段变化，包含之前人工看过的同数量边界调整。需要单独复核：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_body_changed/
```

### 用户点名的首段

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

所有 fake 首段均已校验：

- 起点是合法的上升笔起点或下降笔终点（下降段反之）；
- 终点合法；
- 至少 3 笔；
- 与下一段连续；
- 笔索引连续。

### 审计

v3 全量审计：

```text
penetrates_start         2678
end_not_extreme_bi       1969
right_tzxl_below_left     869
right_tzxl_exceeds_left   577
start_extreme_deviation   509
合计                     6602
```

旧基线 6608，基本持平；首段修复没有引入新的结构问题。

### 报告

```text
http://172.17.1.5:15003/phase7_visual_report_v3_first_segment/
```

全量首段变化清单：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_first_segment_changes_v3.jsonl
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_first_segment_changes_v3_summary.json
```

### 测试服务最终切换

测试容器已改为直接读取宿主机 v3 结果：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_phase7_validation_v3
```

容器 `load_data_cache_pickle` 已改为使用 `_load_pickle_compatible`，可以反序列化宿主机生成的 `CLPainter...` 模块路径 pickle。

API 冒烟：

```text
000750SZ 200，xdData 首段为 1997-07-15 -> 1997-08-21 -> 1998-01-08 -> 1999-12-29
159663SZ 200，xdData 首段为 2022-10-31 -> 2023-02-08 -> 2024-02-05
300265SZ 200，xdData 首段为 2011-09-16 -> 2013-06-25 -> 2015-05-27
```


全量 3267 个仅首段变化报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_first_only/
```

## 连续 FakeXianDuanFirst 收敛

已新增规则：

- 首段连续 fake 从后往前尝试转真实；
- 如果某条 fake 不能转真实，则保留这一条，删除它前面的所有 fake；
- 最终首段最多只有一条 `FakeXianDuanFirst`。

全量扫描结果：

```text
consecutive_fake_cases: 0
```

`560690SH` 已从：

```text
Fake up   2024-05-07 ~ 2024-07-09
Fake down 2024-07-09 ~ 2024-09-09
Real up   2024-09-09 ~ 2025-02-21
```

收敛为：

```text
Fake down 2024-07-09 ~ 2024-09-09
Real up   2024-09-09 ~ 2025-02-21
```


199 个 `right_tzxl_later_exceeds_left` 缓存（201 个违规）报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_later_exceeds/
```

### `right_tzxl_later_exceeds_left` 真正有变化的案例

199 个唯一缓存中：

```text
unchanged_both: 144
changed_both: 55
```

真正有变化的只有 55 个，报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_later_exceeds_changed/
```

清单：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_later_exceeds_changed_cases.jsonl
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_later_exceeds_changed_cases_summary.json
```

## 全局 FakeXianDuanFirst 收敛

已从“只处理首段连续 fake”改为“全序列最多一条 FakeXianDuanFirst”：

- 从右往左处理所有 fake；
- 能转真实就转；
- 不能转真实，就保留这一条，删除它左边的所有线段；
- 最终全序列最多一条 fake。

全量扫描：

```text
multi_fake_cases: 0
```

`511660SH`、`513350SH`、`516860SH`、`000992SH` 等案例已收敛为单条 fake。

## 可视化报告改进

- 线段表格只标黄“新增线段”，不再把整体后移的旧线段标黄；
- 图表默认聚焦到最早出现差异的时间点，而不是居中或偏右。

报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v3_first_only/
http://172.17.1.5:15003/phase7_visual_report_v3_body_changed/
```

## 人工确认的 later_exceeds 拆分

已逐段验证 12 个候选拆分：

- 10 个成立并已应用：159852SZ、399991SZ、002025SZ、002054SZ、002073SZ、002099SZ、600038SH、600094SH、600116SH、000789SZ；
- 2 个不成立，保持原样：300284SZ、688611SH。

不成立原因：

- 300284SZ：2015-06-05 之后找不到合法 tzxl 端点，2016-01-27 不是 tzxl 起点，无法构造标准 2/3 段拆分；
- 688611SH：2021-05-10 是 fake 起点，不是 tzxl；2021-09-29~2021-11-23 只有两笔，不能成为标准线段。

实现位置：

```text
web/backend/app/toolbox/phase7_confirmed_splits.py
```

## 2026-11-14 续接：剩余确认拆分与统一后处理

### 已应用剩余人工确认拆分

在 `web/backend/app/toolbox/phase7_confirmed_splits.py` 中新增：

- `688611SH`：fake `2021-05-10 ~ 2021-11-23`，后接两段真实线段；
- `300290SZ`：从 `2013-06-13` 开始四段真实线段，删除前置 fake；
- `002045SZ`：`2006-05-10 -> 2006-08-15 -> 2007-02-16 -> 2008-10-28`；
- `600188SH`：`2005-11-16 -> 2011-04-11 -> 2014-03-11`；
- `600502SH`：`2011-02-09 -> 2013-06-25 -> 2015-06-12 -> 2020-02-04`；
- `600333SH`：`2003-11-19 -> 2004-04-05 -> 2005-07-19 -> 2008-05-09`。

说明：`600188SH`、`600502SH` 使用实际 tzxl 起点日期，和人工描述日期相差 2~4 天。

### 统一后处理管线

新增 `datacube.postprocess_xian_duan()`，统一执行：

```text
reconcile_first_segments
-> apply_confirmed_splits
-> optional legal split search
-> promote_secondary_fakes
-> 重新编号 idx
```

`phase7_parallel_compare.py` 和 `phase7_invariant_audit.py` 已改为调用同一后处理函数。

### 通用合法拆分搜索

新增实验模块：

```text
web/backend/app/toolbox/phase7_legal_splits.py
```

能力：

- 在单个线段的左右 tzxl 之间枚举 2~4 段候选；
- 每段必须 `is_finished=True`、至少三笔、首尾连续；
- 只有整体不变量数量下降时才替换；
- 默认只处理 `right_tzxl_later_exceeds_left` 线段。

开关：

```text
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1
```

默认关闭，当前仍保留人工确认拆分作为验收锚点。

### 测试

```text
82 passed, 4 skipped
```

新增测试：

- `test_phase7_confirmed_splits.py`
- `test_phase7_legal_splits.py`

## 2026-11-14 全量验证结果（最新）

> 本节结果覆盖前面的旧计数。测试环境数据根为 `/mnt/DataDepartmentTest/home/wjl/data_set_dev`。

### 全量 dump

```text
成功 38855，失败 0
```

已清理源目录中不存在的旧缓存 `561970SH` 五个周期，移动到：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/stale_20261114
```

当前 `curated` 和 `chart_payload` 均为 38855 个文件。

### 测试

```text
82 passed, 4 skipped
```

### 纯算法对比（旧缓存 + 新代码）

```text
成功 38860，失败 0
bi_changed: 0
xd_changed: 3605
first_only: 3569
body_changed: 36
```

说明：纯算法对比使用生产旧缓存中的旧笔/旧特征序列重新生成，不混入 raw 数据漂移。

### 全量缓存对比（旧生产 vs 新测试环境）

```text
changed: 4141
first_only: 3382
body_changed: 759
multi_fake: 0
```

该结果包含 raw 数据漂移，不能全部归因于 Phase 7 算法变化。

### 不变量审计

旧生产：

```text
penetrates_start         2682
end_not_extreme_bi       1967
right_tzxl_below_left     868
right_tzxl_exceeds_left   576
start_extreme_deviation   510
right_tzxl_later_exceeds_left 201
```

新测试环境：

```text
penetrates_start         2677
end_not_extreme_bi       1984
right_tzxl_below_left     871
right_tzxl_exceeds_left   575
start_extreme_deviation   506
right_tzxl_later_exceeds_left 199
```

不含 `later_exceeds` 的总数：`6603 -> 6613`。
含 `later_exceeds` 的总数：`6804 -> 6812`。
没有新增违规类型。

### 可视化报告

36 个纯算法 body_changed：

```text
http://172.17.1.5:15003/phase7_visual_report_v4_body_changed/
```

其中 16 个是已人工确认拆分，剩余 20 个也已人工确认无问题：

```text
http://172.17.1.5:15003/phase7_visual_report_v4_body_changed_other/
```

53 个 later_exceeds_changed：

```text
http://172.17.1.5:15003/phase7_visual_report_v4_later_exceeds_changed/
```

3569 个 first_only：

```text
http://172.17.1.5:15003/phase7_visual_report_v4_first_only/
```

报告目录约 1.3G，index 与 HTML 文件数均为 3569。

### API 冒烟

以下标的均返回 200，且 `xdData` 已确认新拆分：

```text
688611SH
300290SZ
002045SZ
600188SH
600502SH
600333SH
```

### 测试容器代码状态

测试容器当前直接读取新缓存，API 冒烟已通过。但容器内 Python 代码尚未同步本轮新增的：

```text
web/backend/app/toolbox/phase7_legal_splits.py
datacube.postprocess_xian_duan
```

原因是项目规范要求修改远程 Python 代码前先取得许可。若测试服务需要按需重算而不是只读缓存，需要先同步容器代码并平滑重启。

### 剩余 20 个非确认拆分 body_changed

```text
000938SZ 001299SZ 002302SZ 002573SZ 002659SZ
002902SZ 300381SZ 300837SZ 301102SZ 600138SH
600178SH 600299SH 600683SH 600839SH 601005SH
601880SH 601995SH 605178SH 688616SH 300678SZ(1week)
```

这 20 个案例均已人工确认无问题。

### 本轮生成物

```text
phase7_v4_parallel_summary.json
phase7_audit_v4_summary.json
phase7_audit_old_summary.json
phase7_v4_first_only_cases.jsonl
phase7_v4_body_changed_cases.jsonl
phase7_v4_body_changed_other_cases.jsonl
phase7_v4_later_exceeds_cases.jsonl
phase7_v4_later_exceeds_changed_cases.jsonl
phase7_classification_v4/summary.json
```

## 2026-11-14 人工验收通过

用户已确认以下两组报告全部无问题：

```text
http://172.17.1.5:15003/phase7_visual_report_v4_body_changed_other/
http://172.17.1.5:15003/phase7_visual_report_v4_later_exceeds_changed/
```

因此 v4 测试环境结果冻结为当前候选版本：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/curated
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/chart_payload
```

下一步在独立 shadow 目录验证 `ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1`，不影响已验收的 v4。

## 2026-11-14 通用合法拆分 shadow 验证

在独立目录开启：

```bash
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1
```

输出：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_shadow
```

结果：

```text
成功 38855，失败 0
相对 v4 变化 9 个案例
first_only: 1
body_changed: 8
multi_fake: 0
```

变化案例：

```text
605488SH 1week
000068SZ 1day
000713SZ 1day
002083SZ 1day
002347SZ 1day
300327SZ 1day
600777SH 1day
603138SH 1day
600835SH 1week
```

shadow 不变量审计：

```text
penetrates_start         2670
end_not_extreme_bi       1985
right_tzxl_below_left     865
right_tzxl_exceeds_left   575
start_extreme_deviation   501
right_tzxl_later_exceeds_left 193
```

对比 v4：

```text
penetrates_start         2677 -> 2670
end_not_extreme_bi       1984 -> 1985
right_tzxl_below_left     871 -> 865
right_tzxl_exceeds_left   575 -> 575
start_extreme_deviation   506 -> 501
right_tzxl_later_exceeds_left 199 -> 193
```

不含 `later_exceeds`：`6613 -> 6596`。
含 `later_exceeds`：`6812 -> 6789`。

shadow 可视化报告：

```text
http://172.17.1.5:15003/phase7_visual_report_shadow_legal_split/
```

通用搜索仍默认关闭，等待这 9 个案例人工确认后再决定是否启用。

### shadow case_0005 修正

用户指出 `300327SZ` 的 shadow 结果应为：

```text
2013-07-08 -> 2016-06-28 -> 2018-10-12 -> 2021-06-30 -> 2024-02-06
```

已逐段确认：

- 四段均 `is_finished=True`；
- 均至少三笔；
- 首尾连续；
- 笔索引连续。

已在 `phase7_confirmed_splits.py` 中增加 `300327SZ` 的显式拆分，并重新生成 shadow 单标的缓存和报告：

```text
http://172.17.1.5:15003/phase7_visual_report_shadow_legal_split/case_0005.html
```

该案例当前审计无违规。v4 主目录暂未修改，等待该案例人工确认后再决定是否提升为 v5。

## 2026-11-14 v5 候选版本

在独立目录启用通用合法拆分搜索并保留 `300327SZ` 显式拆分：

```text
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1
```

v5 输出：

```text
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_v5/curated
/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_v5/chart_payload
```

全量 dump：

```text
成功 38855，失败 0
```

测试：

```text
83 passed, 4 skipped
```

v5 相对 v4：

```text
changed: 9
first_only: 1
body_changed: 8
multi_fake: 0
```

纯算法对比（旧缓存 + v5 代码）：

```text
xd_changed: 3612
first_only: 3568
body_changed: 44
bi_changed: 0
```

v5 不变量审计：

```text
penetrates_start         2670
end_not_extreme_bi       1985
right_tzxl_below_left     865
right_tzxl_exceeds_left   575
start_extreme_deviation   501
right_tzxl_later_exceeds_left 193
```

v5 报告：

```text
http://172.17.1.5:15003/phase7_visual_report_v5_incremental/
http://172.17.1.5:15003/phase7_visual_report_v5_body_changed/
http://172.17.1.5:15003/phase7_visual_report_v5_later_exceeds_changed/
```

`300327SZ` case_0005 已确认并修正为：

```text
2013-07-08 -> 2016-06-28 -> 2018-10-12 -> 2021-06-30 -> 2024-02-06
```

v5 冻结信息：

```text
/home/wjl/TechFinWorkSpace_v2/CLPainter/phase7_v5_freeze.json
```

## 2026-11-14 测试容器切换到 v5

已同步容器代码：

```text
/root/CLPainter/web/backend/app/toolbox/datacube.py
/root/CLPainter/web/backend/app/toolbox/phase7_confirmed_splits.py
/root/CLPainter/web/backend/app/toolbox/phase7_legal_splits.py
/root/CLPainter/web/backend/app/_config/settings.py
```

容器代码备份：

```text
/root/CLPainter_backup_20261114_203111
```

容器实际读取的配置文件是：

```text
/root/CLPainter/web/backend/.env
```

已设置：

```text
APP_ENV=test
CACHE_DUMP_DIR=/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_v5/curated
ENABLE_XIANDUAN_REPAIR_LOOP=0
ENABLE_XIANDUAN_LOCAL_RESEGMENT=0
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1
```

gunicorn master 已平滑重启，启动日志确认：

```text
Environment: test
Cache Dir: /mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_v5/curated
```

API 冒烟：

```text
300327SZ 200
688611SH 200
300290SZ 200
002045SZ 200
600188SH 200
600502SH 200
600333SH 200
159577SZ 200
600996SH 200
```

`xdData` 已确认：

- `300327SZ` 包含 `2013-07-08 -> 2016-06-28 -> 2018-10-12 -> 2021-06-30 -> 2024-02-06`
- `688611SH` 包含 `2021-05-10 -> 2021-11-23 -> 2022-04-26 -> 2022-08-18`

## 2026-11-14 P1 完成

- v5 已人工验收通过。
- 测试容器已切换到 v5 缓存路径。
- 容器代码已同步并平滑重启。
- API 冒烟全部通过。
- Git 提交：

```text
当前 HEAD：完成 Phase 7 v5 通用拆分与测试环境切换
```

容器代码备份：

```text
/root/CLPainter_backup_20261114_203111
```

## 2026-11-14 P2 代码整合（零 diff）

本轮只做纯重构，不改变 v5 行为：

- 新增 `_make_fake_last()`，统一 `FakeXianDuanLast` 的字段赋值；
- `FakeXianDuanFirst` 的构造统一复用 `_make_fake_first()`；
- 替换 `generate_xian_duan()` 内部重复的 fake 首段/尾段手工构造；
- 修复整合过程中发现的 `FakeXianDuanLast` 传入 `make_fake_first_before_xianduan()` 的兼容问题。

全量验证：

```text
dump_p2：成功 38855，失败 0
测试：83 passed, 4 skipped
```

v5 与 p2 快照：

```text
SNAPSHOT_IDENTICAL
sha256: 565d9de47f23ce94458a92f115f291d7ccad38eccc8580af28c931ceaf4823e1
```

不变量审计与 v5 完全一致：

```text
penetrates_start         2670
end_not_extreme_bi       1985
right_tzxl_below_left     865
right_tzxl_exceeds_left   575
start_extreme_deviation   501
right_tzxl_later_exceeds_left 193
```

结论：本次代码整合为纯重构，行为零差异。v5 测试环境数据保持不变，p2 仅作为验证目录。

### P2 容器同步

重构后的 `xianduan.py` 已同步到测试容器并平滑重启：

```text
/root/CLPainter/web/backend/app/toolbox/xianduan.py
```

API 冒烟：

```text
300327SZ 200
688611SH 200
300290SZ 200
159577SZ 200
```

容器启动日志仍为：

```text
Environment: test
Cache Dir: /mnt/DataDepartmentTest/home/wjl/data_set_dev/dump_v5/curated
```

## 2026-11-14 P2 第二轮：首段极值搜索整合

新增：

```text
_find_extreme_start_bi_index()
```

统一 `make_fake_first_xd_extend()` 和 `_make_fake_earliest_xd()` 中重复的：

- `[0, origin_bi_idx]` 切片；
- `argmax/argmin` 极值搜索；
- `>= / >` 与 `<= / <` 的严格比较；
- 笔方向不一致时的 `+1` 校正。

验证：

```text
p3 全量 dump：成功 38855，失败 0
测试：83 passed, 4 skipped
v5 与 p3 snapshot：SNAPSHOT_IDENTICAL
sha256: 565d9de47f23ce94458a92f115f291d7ccad38eccc8580af28c931ceaf4823e1
```

结论：第二轮仍为纯重构，行为零差异。

### P2 第二轮容器同步

第二轮重构后的 `xianduan.py` 已同步测试容器并平滑重启，API 冒烟：

```text
300327SZ 200
688611SH 200
159577SZ 200
```
