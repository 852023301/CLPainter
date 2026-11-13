# Phase 7 生产部署清单

> 生产服务在其他服务器，本清单只作为执行步骤，不在当前机器直接操作生产。

## 0. 前置条件

- 测试环境已完成人工验收；
- 生产 `data_set` 的 raw 数据已更新到目标日期；
- 已确认生产容器内代码导入方式是 `app...` 还是 `CLPainter...`；
- 已准备回滚窗口。

## 1. 备份

在生产服务器备份：

```bash
cp -a /root/CLPainter /root/CLPainter_backup_$(date +%Y%m%d)
mv /DataDepartmentTest/home/wjl/data_set/dump/curated \
   /DataDepartmentTest/home/wjl/data_set/dump/curated_backup_$(date +%Y%m%d)
mv /DataDepartmentTest/home/wjl/data_set/dump/chart_payload \
   /DataDepartmentTest/home/wjl/data_set/dump/chart_payload_backup_$(date +%Y%m%d)
```

## 2. 同步代码

同步以下内容：

```text
web/backend/app/toolbox/
web/backend/app/_config/settings.py
web/backend/scripts/
```

注意：生产容器如果使用 `app...` 导入，需要把代码中的：

```text
CLPainter.web.backend.app...
```

替换为：

```text
app...
```

否则 pickle 模块路径会不一致，容器无法反序列化。

## 3. 生成生产兼容缓存

不要直接使用宿主机生成的 pickle。必须在生产容器内重新生成：

```bash
cd /root/CLPainter
DATA_DIR=/DataDepartmentTest/home/wjl/data_set/pv_data \
OLD_DATA_DIR=/DataDepartmentTest/home/wjl/data_set/old_pv_data \
CACHE_DUMP_DIR=/DataDepartmentTest/home/wjl/data_set/dump/curated \
DB_PATH=/DataDepartmentTest/home/wjl/data_set/instrument.db \
ENABLE_XIANDUAN_REPAIR_LOOP=1 \
ENABLE_XIANDUAN_LOCAL_RESEGMENT=0 \
PYTHONPATH=/root/CLPainter/web/backend \
python web/backend/scripts/dump_stock_caches.py \
  --source-dirs /DataDepartmentTest/home/wjl/data_set/pv_data
```

要求：

```text
成功 38860，失败 0
```

## 4. 切换服务

确认 `settings.py` 的 `DEFAULT_DATA_ROOT` 指向生产 `data_set`，然后平滑重启：

```bash
kill -HUP <gunicorn-master-pid>
```

## 5. 冒烟测试

至少检查：

```text
159577SZ 1day fund
600996SH 1day stock
000750SZ 1day stock
600015SH 1day stock
159301SZ 1day fund
159612SZ 1day fund
```

要求：

- HTTP 200；
- `159577SZ` 的 `xdData` 包含 `2024-04-22 -> 2025-01-07`；
- `600996SH` 的 `xdData` 包含 `2024-11-08 -> 2025-04-09`；
- `159301SZ` 的 `xdData` 不包含 `2026-05-14 -> 2026-07-09`；
- 随机抽取 10 个变化案例，全部 200。

## 6. 回滚

恢复代码：

```bash
rm -rf /root/CLPainter
mv /root/CLPainter_backup_YYYYMMDD /root/CLPainter
```

恢复数据：

```bash
rm -rf /DataDepartmentTest/home/wjl/data_set/dump/curated
rm -rf /DataDepartmentTest/home/wjl/data_set/dump/chart_payload
mv /DataDepartmentTest/home/wjl/data_set/dump/curated_backup_YYYYMMDD \
   /DataDepartmentTest/home/wjl/data_set/dump/curated
mv /DataDepartmentTest/home/wjl/data_set/dump/chart_payload_backup_YYYYMMDD \
   /DataDepartmentTest/home/wjl/data_set/dump/chart_payload
```

重启：

```bash
kill -HUP <gunicorn-master-pid>
```
