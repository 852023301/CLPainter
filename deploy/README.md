# CLPainter 生产/测试服务隔离

生产与测试使用同一镜像，通过不同的 compose override 和环境文件区分。

## 构建镜像

首次启动或代码更新后，先构建镜像：

```bash
./deploy/build.sh
```

生产与测试使用同一个镜像 tag，只需要构建一次。

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

迁移测试环境：

```bash
docker stop CLPainter
docker rm CLPainter
./deploy/build.sh
./deploy/up-test.sh
```

迁移后测试环境使用：

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
