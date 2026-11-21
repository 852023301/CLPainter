# 选股方案

## 目标与边界
用户已确认：将当前筛选条件命名保存到后端数据库，支持列出、应用、更新和删除；刷新或换浏览器后仍能读取。方案只保存条件，不保存查询结果，不提供每日结果留档、账号体系或定时执行。
与当前自选板块一致，方案在同一服务实例内共享，不承诺用户隔离。此次只修改本地代码，不迁移真实数据库、不部署容器、不提交 Git。保留用户已有 README 修改。

## 数据与接口契约
新增 stock_screener_preset 表：id、唯一名称 name（去除首尾空白后 1–64 字符）、JSON filters、created_at、updated_at。
接口前缀 /api/v1/test_api/stock_screener/presets：GET 返回 {presets: [...]}；POST 创建返回 201；PUT /{id} 完整更新名称与条件；DELETE /{id} 返回 204。
写入体为 {name, filters}，filters 只接受现有选股字段；null 表示不限，状态值 0 必须保留。字段缺省规范化为 null，不得恢复成默认日线/股票等条件。禁止把 results 或未知字段写入方案。无效输入 422、同名冲突 409、方案不存在 404。

## 界面行为
在选股条件上方增加方案选择、应用/更新/删除按钮及名称输入/保存为新方案按钮。更新和删除需要确认。应用只恢复条件并清除旧查询结果，不自动查询；确认按钮始终查询最新数据。重置只重置当前条件，不删除已保存方案。
操作期间禁用冲突按钮；失败保留当前条件和方案列表，显示可读错误，加载失败可以重试。方案名称通过 textContent 渲染。当前数据不再提供的非空条件必须拒绝应用，不能静默扩大筛选范围。

## 实现与风格
沿用原生 JS/Jinja2、FastAPI、Pydantic 2、SQLAlchemy 2、SQLite 和 Alembic，不引入依赖。后端使用 stock_screener 现有查询模型作为过滤字段契约，以严格模型和数据库唯一约束校验边界；新增同步路由避免在事件循环中执行同步数据库访问。
源文件位于 web/backend/app/db/models.py、app/api/api_v1/endpoints/test_api.py、app/templates/lightweight_charts_demo.html；迁移位于 app/db/migrations/versions。保持现有 UTF-8 无 BOM 与原文件换行风格。

## 验证
- 临时 SQLite 上执行真实 HTTP 创建、读取、更新、冲突、删除、非法输入测试。
- 临时数据库验证 Alembic 升级、降级、再次升级及已有自选数据不变。
- Node 执行模板中的真实方案交互代码，覆盖不限、0 值、刷新、失败/取消和查询/方案互斥。
- 必跑：cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend && python -m unittest tests.test_frontend_template
- 全量：cd /home/wjl/TechFinWorkSpace_v2/CLPainter && python3 -m pytest -q web/backend/tests
- 不修改 toolbox 计算代码，因此不触发全量 dump；未经要求不启动浏览器。

## 上线前迁移
先备份部署环境配置的 SQLite 数据库，并将新增迁移文件 e6c2a9f4b8d1_create_stock_screener_preset.py 同步到目标环境的迁移目录（暂不重载服务），然后在对应环境执行：

    cd /root/CLPainter/web/backend
    PYTHONPATH=/root python -m alembic -c /root/CLPainter/web/backend/alembic.ini upgrade head

宿主机开发环境使用 /home/wjl/TechFinWorkSpace_v2 作为 PYTHONPATH，并使用绝对 alembic.ini 路径。不要把宿主机数据路径用于容器或更换 DB_PATH。迁移通过后同步模型、接口和模板，并平滑重载 Web 进程。仅同步 HTML 不能交付此功能。
回滚代码可以保留新增表与方案数据；只有明确要求丢弃方案数据时才降级到 b4e1a7d9c3f2，降级会删除方案表。

## 本次验证结果（2026-11-20）
- 后端方案测试：22 passed，覆盖真实 HTTP CRUD、严格校验、冲突回滚、跨客户端读取、null/0 和查询最新数据。
- 前端硬门禁：12 tests OK，包含原缺口/均线/图层行为与新增方案交互。
- 全量 pytest：230 passed、6 failed、0 skipped；修改前为 207 passed、6 failed，失败节点完全一致。
- 既有失败：test_bi_regression[S14-quarter]、test_bi_regression[S15]；test_raw_rebuild_uses_explicit_reference[S28/S15]；test_segment_regression[S25/S28]。涉及既有数据日期期望不匹配，本次未修改这些断言或计算代码。
- 第三方兼容警告：当前 Starlette/httpx 的弃用提醒，未升级依赖。
- UTF-8 无 BOM、Python AST、内联脚本解析和 git diff --check 通过；README 原有修改保持原字节。
- 未进行浏览器人工验收、真实数据库迁移、容器部署或 Git 提交。初轮全项目门禁因上述基线失败未通过，后续复跑见下。

### 当前工作区复跑
验证期间工作区另有日期回归测试更新（非本功能修改）。按更新后的工作区重新执行相同全量命令，结果为 315 passed、0 failed、0 skipped，23 条既有第三方兼容警告。全量日志保存在 /tmp/clpainter-screener-presets-tests-20261120-final.log。上述并行改动没有被本任务编辑、暂存或提交。
