# Phase 7 生产部署交接

> 当前环境是测试环境，本文档只作为生产环境手动部署依据，不在当前环境执行生产操作。

## 1. 当前测试环境状态

- 测试数据：`/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump`
- 测试容器：`CLPainter`
- 容器配置：`/root/CLPainter/web/backend/.env`
- 容器代码备份：`/root/CLPainter_backup_20261114_203111`
- 测试容器当前使用：
  - `APP_ENV=test`
  - `CACHE_DUMP_DIR=/mnt/DataDepartmentTest/home/wjl/data_set_dev/dump/curated`
  - `ENABLE_XIANDUAN_REPAIR_LOOP=0`
  - `ENABLE_XIANDUAN_LOCAL_RESEGMENT=0`
  - `ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1`

## 2. 生产需要同步的代码

```text
web/backend/app/toolbox/bi.py
web/backend/app/toolbox/xianduan.py
web/backend/app/toolbox/datacube.py
web/backend/app/toolbox/phase7_confirmed_splits.py
web/backend/app/toolbox/phase7_legal_splits.py
web/backend/app/_config/settings.py
web/backend/app/db/base.py
web/backend/app/main.py
```

如需保留审计能力，可同步：

```text
web/backend/scripts/phase7_*.py
web/backend/tests/
```

## 3. 生产配置

生产容器应使用：

```text
APP_ENV=production
DEFAULT_DATA_ROOT=/mnt/DataDepartmentTest/home/wjl/data_set
CACHE_DUMP_DIR=/mnt/DataDepartmentTest/home/wjl/data_set/dump/curated
ENABLE_XIANDUAN_REPAIR_LOOP=0
ENABLE_XIANDUAN_LOCAL_RESEGMENT=0
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1
```

注意：`settings.py` 实际读取的是：

```text
/root/CLPainter/web/backend/.env
```

不是项目根目录的 `.env`。

## 4. 生产缓存生成

不要直接复制宿主机生成的 pickle。生产容器内重新生成。

> 如果生产 gunicorn 正在运行，SQLite 在网络文件系统上可能出现
> `sqlite3.OperationalError: locking protocol`。建议先平滑停止服务，
> 或使用 `sqlite3 instrument.db ".backup '/tmp/instrument_dump.db'"` 生成
> 一份一致性副本，并把 `DB_PATH` 指向该副本后再执行全量 dump。

```bash
cd /root/CLPainter
DATA_DIR=/mnt/DataDepartmentTest/home/wjl/data_set/pv_data \
OLD_DATA_DIR=/mnt/DataDepartmentTest/home/wjl/data_set/old_pv_data \
CACHE_DUMP_DIR=/mnt/DataDepartmentTest/home/wjl/data_set/dump/curated \
DB_PATH=/mnt/DataDepartmentTest/home/wjl/data_set/instrument.db \
ENABLE_XIANDUAN_REPAIR_LOOP=0 \
ENABLE_XIANDUAN_LOCAL_RESEGMENT=0 \
ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH=1 \
PYTHONPATH=/root/CLPainter/web/backend \
python web/backend/scripts/dump_stock_caches.py \
  --source-dirs /mnt/DataDepartmentTest/home/wjl/data_set/pv_data
```

要求：

```text
成功 38855，失败 0
```

## 5. 生产验收

至少检查：

```text
300327SZ 1day stock
688611SH 1day stock
300290SZ 1day stock
159577SZ 1day fund
600996SH 1day stock
```

要求：

- HTTP 200；
- `300327SZ` 的 `xdData` 包含：
  `2013-07-08 -> 2016-06-28 -> 2018-10-12 -> 2021-06-30 -> 2024-02-06`
- `688611SH` 的 `xdData` 包含：
  `2021-05-10 -> 2021-11-23 -> 2022-04-26 -> 2022-08-18`
- 随机抽取 10 个变化案例，全部 200。

## 6. 回滚

备份生产代码和缓存：

```bash
cp -a /root/CLPainter /root/CLPainter_backup_$(date +%Y%m%d_%H%M%S)
mv /mnt/DataDepartmentTest/home/wjl/data_set/dump/curated \
   /mnt/DataDepartmentTest/home/wjl/data_set/dump/curated_backup_$(date +%Y%m%d_%H%M%S)
mv /mnt/DataDepartmentTest/home/wjl/data_set/dump/chart_payload \
   /mnt/DataDepartmentTest/home/wjl/data_set/dump/chart_payload_backup_$(date +%Y%m%d_%H%M%S)
```

回滚时恢复代码和缓存目录，并平滑重启 gunicorn。

## 7. 范围说明

以下改动不属于 Phase 7 算法改动，本次不处理：

```text
.env
README.md
docker-compose.yml
deploy/
docker-compose.prod.yml
docker-compose.test.yml
```

这些留给后续通过 docker-compose 做生产和测试的服务级隔离。
