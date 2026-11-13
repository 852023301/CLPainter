# Phase 7 保守模式验收摘要（2026-11-12）

## 数据

- 生产 raw：`/DataDepartmentTest/home/wjl/data_set`（只读）
- 隔离输出：`/DataDepartmentTest/home/wjl/data_set_phase7_validation_v2`
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

## 当前状态

- 保守模式已全量跑通；
- 测试环境已切换到新缓存，并完成 API 冒烟；
- 生产默认开关仍关闭，生产 curated 未覆盖；
- 3234 个首段变化已按你的规则推广；
- 369 个 body_changed 案例需要单独复核：
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
/DataDepartmentTest/home/wjl/data_set_dev_phase7_v2
```

该目录的 `pv_data`、`old_pv_data`、`instrument.db` 软链到生产 `data_set`，只读使用；写入只发生在 `dump/curated` 和 `dump/chart_payload`。

容器内全量导出：

```text
成功 38860，失败 0
```

### 测试服务切换

容器 `settings.py` 的 `DEFAULT_DATA_ROOT` 已改为：

```text
/DataDepartmentTest/home/wjl/data_set_dev_phase7_v2
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
first_only: 3234
body_changed: 369
```

3234 个变化只发生在首段；369 个案例在首段之后还有线段变化，包含之前人工看过的同数量边界调整。需要单独复核：

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
/DataDepartmentTest/home/wjl/data_set_phase7_validation_v3
```

容器 `load_data_cache_pickle` 已改为使用 `_load_pickle_compatible`，可以反序列化宿主机生成的 `CLPainter...` 模块路径 pickle。

API 冒烟：

```text
000750SZ 200，xdData 首段为 1997-07-15 -> 1997-08-21 -> 1998-01-08 -> 1999-12-29
159663SZ 200，xdData 首段为 2022-10-31 -> 2023-02-08 -> 2024-02-05
300265SZ 200，xdData 首段为 2011-09-16 -> 2013-06-25 -> 2015-05-27
```


全量 3234 个仅首段变化报告：

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
