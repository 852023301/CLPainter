# 前端第 1 项：错误页转义与异常信息保护（2026-11-21）

## 状态与范围

已完成本地实现与验收，并已根据后续用户授权部署到测试服务；尚未提交 Git。仅修改图表 HTML 入口的错误边界及相应测试；不改计算核心、行情缓存、数据库表、选股/历史业务规则、正常页面模板或全局 JSON 接口错误策略。

基线记录继续保留在 docs/review/2026-11-21-frontend-baseline.md；原有冻结副本及当时 14 RED / 4 对照的结果未修改。本轮证据：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-frontend-error-pages-20261121-182421-side`。

## 风险与处理

- 不可信查询参数通过 ValueError 进入 HTML：400 响应现在使用标准库 html.escape 转义，保留可读校验提示，不能生成输入中的 HTML 元素。
- 内部异常泄露：500 响应统一返回“图表暂时不可用，请稍后重试。”，不包含路径、异常文本或合成探针内容；logger.error 的 exc_info=True 保留完整服务端异常栈。
- 异常分类边界：参数及标的路径校验与数据库/分类/序列化/渲染处理分开。内部 ValueError 不再被误当成客户端 400 并回显。前置缓存版本读取的非校验异常也返回通用 500 并记录日志。
- 400/500 响应添加 Cache-Control: no-store，不带 ETag。正常成功页面的 private, no-cache、gzip、ETag/304 行为保持。
- 历史模式缺图时仍保留原有 200 降级工作台；内部初始化失败不得被误判为普通缺图。

## RED → GREEN 与默认门禁

1. 原隔离安全契约：修复前 3 failed / 1 passed；修复后 4 passed，未放宽原断言。
2. 新 HTTP 安全回归：修复前 14 failed / 4 passed；修复后 18 passed。RED 阶段临时独立执行，转绿后接入默认测试集。
3. 新默认用例：web/backend/tests/test_frontend_error_pages.py。使用真实 FastAPI 路由、HTTP 测试客户端、内存 SQLite 与临时模板元数据，不访问真实数据库、缓存或运行中的服务。
4. 18 项覆盖 frequency/market/asset_class/symbol 转义、旧目录参数 400、版本读取/数据库（含 ValueError）/分类/JSON/模板元数据/渲染异常、日志 traceback、错误缓存策略、成功 HTML/gzip/ETag、历史缺图降级与内部故障边界。
5. 前端硬门禁 16 tests OK；默认全量 445 passed、0 failed、0 skipped，pytest 进程退出码 0。比此前默认集增加 18 项安全回归，无新增依赖、无 skip/xfail。
6. 全部旧隔离契约当前为 11 failed / 7 passed：安全相关断言均为 GREEN，其他已知问题仍隔离，未在本任务中修复。

## 复查与边界

- 运行代码仅修改 web/backend/app/api/api_v1/endpoints/test_api.py；源码原有 LF 保持，新测试和本记录为 UTF-8 无 BOM、CRLF。
- 没有编辑 toolbox 计算代码，因此不触发全量 dump；已运行默认全量测试。
- 不修改共享 tasks/plan.md、tasks/todo.md 或两份 README 的其他任务改动。
- 本地实现阶段未部署；后续用户明确授权后的测试服务发布记录见下节。没有 Git 写操作、真实数据流水线或浏览器人工验收。
- 本次不是全站安全审计；JSON 接口、认证、CSP 等不在本项范围内。

## 重跑命令

```bash
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests/test_frontend_error_pages.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests/repros/frontend_contracts.py -k 'error_response or valid_chart'
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_frontend_template
```

日志：red-contracts.log、red-default.log、green-contracts.log、green-http.log、frontend.log、pytest.log、pytest.exit、remaining-contracts.log。保留 API 修改前副本及本轮 diff，方便审查和后续经授权部署。

## 已授权部署到测试（2026-11-21）
- 完成时间：2026-11-21T18:53:14+08:00；容器 clpainter-test，HTTP 15001。
- 仅发布 API 错误处理文件，镜像 4.0 已固化；实际镜像 sha256:4bb23e8ecc66785f6f234c9399328ce354bfb02f95c66bfee7f65848e07e6b13，发布标签 harbor.techfin.ai/wjl-toolkit/cl_painter:frontend-errors-20261121-184411-side。其余运行源码、前端交互及分类独立环境保留。
- 部署前复跑：安全 HTTP 18 passed、前端 16 tests OK、默认全量 445 passed（0 failed / 0 skipped），pytest 退出码 0。
- 真实 HTTP 检查：四种参数的 400 已转义、不缓存；一次受控只读缺图 500 隐藏内部详情、不缓存，服务端保留完整异常栈。该验证产生一条预期错误日志，不是未处理故障；无非预期服务错误。
- 正常页面、历史链接、指标和实际返回脚本交互检查通过。数据库全部表部署前后的行数及 SHA-256 内容指纹不变；生产服务状态未变，没有运行数据流水线或全量 dump。
- 备份、校验和代码回滚命令：/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-error-pages-deploy-20261121-184411-side。未提交 Git，未推送镜像仓库，未进行浏览器人工验收。
