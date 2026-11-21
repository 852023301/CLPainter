# 选股方案

## 目标与边界
用户已确认：将当前筛选条件命名保存到后端数据库，支持列出、应用、更新和删除；刷新或换浏览器后仍能读取。方案只保存条件，不保存查询结果，不提供每日结果留档、账号体系或定时执行。
与当前自选板块一致，方案在同一服务实例内共享，不承诺用户隔离。此次只修改本地代码，不迁移真实数据库、不部署容器、不提交 Git。保留用户已有 README 修改。

## 数据与接口契约
新增 stock_screener_preset 表：id、唯一名称 name（去除首尾空白后 1–64 字符）、JSON filters、created_at、updated_at。
接口前缀 /api/v1/test_api/stock_screener/presets：GET 返回 {presets: [...]}；POST 创建返回 201；PUT /{id} 完整更新名称与条件；DELETE /{id} 返回 204。
写入体为 {name, filters}，filters 只接受现有选股字段；null 表示不限，状态值 0 必须保留。字段缺省规范化为 null，不得恢复成默认日线/股票等条件。禁止把 results 或未知字段写入方案。无效输入 422、同名冲突 409、方案不存在 404。

## 界面行为
在选股条件上方提供方案选择及新增/应用/更新/删除按钮。名称输入与保存/取消区域默认隐藏，只在点击新增后展开；更新保留所选方案名称，仅覆盖当前筛选条件，不读取新增草稿名称。更新和删除需要确认。应用恢复并校验方案条件、清除旧查询结果，然后自动执行一次确认查询并展示最新结果；仅切换方案下拉选项不查询，确认按钮仍可手工重新查询。重置只重置当前条件，不删除已保存方案。
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

## 紧凑交互调整（2026-11-21）
- 新增/应用/更新/删除按钮使用深色半粗体，禁用状态仍可辨认且不可操作。
- 点击新增后才显示名称输入区并聚焦；取消或 Esc 清空草稿并收起，不改方案及筛选条件；保存成功后收起，失败保留输入便于重试。Enter 保存，中文输入法组合输入时不触发保存。
- 新增期间暂时禁用方案切换及应用/更新/删除，防止误操作其他方案；查询和保存时继续保持原有互斥与重复点击保护。重置关闭草稿，不删除已存方案。
- 不修改后端 CRUD、表结构或真实数据库，本轮未部署或提交。

本轮验证：前端硬门禁 16 tests OK；全量 pytest 427 passed、0 failed、0 skipped，pytest 进程退出码 0。Node 行为覆盖默认隐藏、聚焦、取消/重置、保存失败保留草稿、Enter/Esc/中文输入法、更新名称隔离、最新五版本及旧链接/缓存绕过边界。JS 语法、Python Ruff F/E9、作用域 diff 和 UTF-8 无 BOM 检查通过。未部署、未提交 Git、未启动浏览器或真实数据流水线。

## 紧凑化前端已授权部署（2026-11-21）
前文“未部署”是本地实现阶段记录。用户随后授权发布，已重建并启动 clpainter-test（15001），两个前端运行文件固化到镜像 4.0，发布标签 screener-ui-20261121-170423。部署前复跑：前端 16 tests OK、全量 427 passed（0 failed / 0 skipped）。HTTP 页面/脚本及实际返回文件的 Node 行为检查通过，覆盖粗体按钮、默认收起的新增区、保存/取消/键盘及五期上限。数据库全部表内容指纹不变，分类独立环境保留，生产容器未启动；未运行数据流水线、未进行浏览器人工验收、未提交 Git。部署备份和回滚命令：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-screener-ui-deploy-20261121-170423。

## 应用后自动查询（2026-11-21）
按用户新要求，原“应用不查询”规则作废：点击应用后，先校验并恢复条件，随后直接调用现有确认查询流程一次并展示结果，不模拟额外按钮点击。仅切换方案选项不查询；查询中禁用应用和确认以防重复；空结果正常显示，失败保留条件、清除旧结果并允许再次应用或确认重试。无效方案不发起查询，不限和状态值 0 保持原义。本轮仅本地修改，未部署或提交。

自动查询验收：前端硬门禁 16 tests OK；全量 pytest 427 passed、0 failed、0 skipped，进程退出码 0。先复现旧版不发查询的失败，再通过自动一次查询、结果渲染、不限/零值、空结果、忙态防重复、失败重试和非法条件不查询的 JS 回归。仅应用函数增加共享查询调用并更新提示；未修改后端、算法或真实数据，未部署或提交 Git。

## 自动查询已授权部署（2026-11-21）
前文“自动查询未部署”是本地实现记录；用户随后授权部署，已重建并启动 clpainter-test（15001），只替换主页面模板并固化到镜像 4.0（发布标签 preset-autoquery-20261121-175131）。前端 16 tests OK、全量 427 passed（0 failed / 0 skipped）；实际返回页面的 Node 行为测试验证自动一次查询、结果显示、互斥、空结果及失败重试，已有方案实测只读查询一次返回 HTTP 200、14 个标的。数据库全部表内容指纹不变，既有界面优化、历史五期上限及分类环境保留；生产未启动，不运行数据流水线、不进行浏览器人工验收、不提交 Git。备份与回滚：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-preset-autoquery-deploy-20261121-175131。

## 本轮提交前验收（2026-11-21）
用户已授权提交按钮文字增强、按需新增方案、最新五期历史显示及应用后自动查询，连同测试和部署记录共九个相关文件。前端硬门禁 16 tests OK，全量 427 passed（0 failed / 0 skipped，进程退出码 0）；两个运行文件与已部署版本一致。两份 README 的其他修改不纳入本次提交；不推送远程，不重复部署或重启服务，不修改后端及真实数据。
