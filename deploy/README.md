# CLPainter 生产/测试服务隔离

生产与测试使用同一镜像，通过不同的 compose override 和环境文件区分。

## 构建镜像

首次启动或代码更新后，先构建镜像：

```bash
./deploy/build.sh
```

生产与测试使用同一个镜像 tag，只需要构建一次。镜像版本统一在项目根目录的 `.env` 中配置：

```dotenv
IMAGE_TAG=3.0
```

构建脚本只读取公共 `.env` 和 `docker-compose.yml`，不依赖 `prod.env` 或 `test.env`：

```bash
docker compose -p clpainter-build \
  --env-file .env \
  -f docker-compose.yml build
```

生产和测试启动时仍分别加载 `.env + prod.env`、`.env + test.env`，两个环境文件不再重复定义 `IMAGE_TAG`。

## 测试环境

```bash
./deploy/up-test.sh
```

等价于：

```bash
docker compose -p clpainter-test \
  --env-file .env --env-file deploy/env/test.env \
  -f docker-compose.yml -f docker-compose.test.yml up -d
```

## 生产环境

```bash
./deploy/up-prod.sh
```

等价于：

```bash
docker compose -p clpainter-prod \
  --env-file .env --env-file deploy/env/prod.env \
  -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 数据挂载与权限

所有 bind mount 均使用 `宿主机路径:容器路径:ro/rw` 短语法。

公共 Compose 只保留 tdata/ddp 使用的只读数据源；按用户确认的部署取舍保留 `privileged: true`，本次不修改特权模式：

```yaml
volumes:
  - "/DataDepartment/SourceData:/DataDepartment/SourceData:ro"
```

生产 override 只允许写生产数据：

```yaml
volumes:
  - "/mnt/DataDepartmentTest/home/wjl/data_set:/mnt/DataDepartmentTest/home/wjl/data_set:rw"
```

测试 override 只允许写测试数据：

```yaml
volumes:
  - "/mnt/DataDepartmentTest/home/wjl/data_set_dev:/mnt/DataDepartmentTest/home/wjl/data_set_dev:rw"
```

不再挂载整个 `/DataDepartment`、`/DataDepartmentTest` 或 `/mnt/DataDepartmentTest`。
容器不负责挂载 Ceph/NFS：宿主机先完成挂载，再把指定子目录 bind 进去。
以后如需额外公共数据源，应单独添加必要的只读子目录，不恢复可写整根挂载。
修改数据根时，需要同时更新对应 override 和环境文件中的数据路径。
本次验收只覆盖声明的挂载范围与常规路径可见性，不将结果表述为对容器内任意进程的强安全隔离证明。

启动前确认宿主机公共数据源及本环境数据目录已经存在且内容正确；短语法可能创建不存在的宿主机目录，不能把空目录误当成已准备好的数据。
可以先检查最终合并结果，再由操作者决定是否重建容器：

```bash
docker compose -p clpainter-test \
  --env-file .env --env-file deploy/env/test.env \
  -f docker-compose.yml -f docker-compose.test.yml config
```

挂载变更需要重建容器才能生效；仅修改文件或重启旧容器，不代表旧服务已经采用新挂载。

## 停止

```bash
./deploy/down-test.sh
./deploy/down-prod.sh
```

## 端口

```text
生产：SSH 36602，HTTP 15000
测试：SSH 36603，HTTP 15001
```

## 从旧容器迁移

当前旧容器 `CLPainter` 使用 15000/36602，并且代码是手工同步的，不是当前镜像内容。

迁移前先确认镜像中的代码就是待运行版本。新测试服务使用独立端口，可以先与旧容器并行启动、验收，不需要预先停止或删除旧容器：

```bash
# 需要更新镜像代码时才重新构建
./deploy/build.sh
./deploy/up-test.sh
```

确认新服务的数据路径、图表、筛选结果及采集依赖后，再单独决定是否停用旧容器。
本次配置修复不会自动运行上面的命令，也不会自动切换或删除旧服务。

新测试环境使用：

```text
容器名：clpainter-test
SSH：36603
HTTP：15001
```

## 注意

- 启动新的生产容器前，必须确保 15000/36602 没有被旧 `CLPainter` 占用。
- 当前机器建议只启动测试容器；生产容器应在生产服务器上启动。
- 两个环境使用同一个镜像 tag，避免生产与测试代码不一致。
- 新容器使用镜像内代码，不再依赖手工同步容器文件。
