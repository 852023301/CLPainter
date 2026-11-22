# 前端第 4 项：切换指标保留可视时间范围（2026-11-21）

## 状态与范围

已完成优化并按用户授权部署到 clpainter-test（15001），完成时间 2026-11-21T23:17:09+08:00。未提交 Git。
本项只处理同一页面内指标切换时的时间轴逻辑范围、同步生命周期及相关布局重绘通知，不实现跨股票/周期导航或整页刷新后的视窗/绘图持久化。

证据：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-viewport-20261121-224219-side`；部署、切换前数据备份及代码回滚命令：`/home/wjl/TechFinWorkSpace_v2/temp_dir/clpainter-viewport-20261121-224219-side/deployment`。

## 修复规则

- 默认近 50 根 K 线范围仅由页面启动时的 applyInitialLogicalRange 调用一次；指标完成、失败或全副图就绪时不再重复套用默认范围。
- 在新数据就绪并确认仍为最新构建后，读取主图当时的最新窗口，而非请求开始时的旧窗口。范围按 from/to 数值复制，不持有可被布局修改的引用，不取整、不夹紧负数或小数逻辑坐标。
- 主图暂无范围时使用该副图已有范围；两者均未知时不调用 fitContent 或强制默认窗口。
- 仅在同步的系列替换和布局修改阶段持有范围同步保护，避免临时自动缩放传播到主图。finally 释放本次保护，再恢复主图和当前副图，使现有同步器对齐其他副图。
- 加载失败时不修改窗口；同步渲染失败也走范围恢复。即使恢复接口抛错，同步标志也不会卡死，之后的拖动仍可继续。
- 同步器忽略与来源当前 getter 不一致的过期事件；主图已有有效窗口后，其他初始化数据尚未就绪也允许用户从副图拖动同步。
- 核对了项目实际打包的 v4 图表库：逻辑范围通知使用当前 getVisibleLogicalRange，新增过滤与其语义一致；部署时还校验该库字节保持不变。
- 指标改变高度后，在下一帧发出独立 chartlayoutchange 通知，保留区间框、测量、矩形、趋势线和黄金尺的几何更新，不再依赖错误地重置时间轴来触发重绘。

原指标构建代码块只为 try/finally 保护增加必要缩进，去掉这部分缩进后与修复前逐行相同，见 render-block-equivalence.json；未修改指标数值、颜色、MACD 自动缩放公式或价格轴交互。

## RED → GREEN 与覆盖

最终范围分组修复前模板重放：16 failed / 1 passed；修复后 17 场景全部通过，无 harness_error。原 indicator_preserves_range 断言未放宽，已转绿。

覆盖主图为准、等待期间主图/副图继续拖动、初始化未完成时拖动、请求失败、渲染失败、恢复接口异常后继续同步、过期事件、可变引用与负数小数范围、空范围回退、首次默认仅一次、主图重排自动缩放、已有保护标志，以及布局通知不重置窗口；另有正常主副图同步对照。

既有竞态场景中原“最后一个面板完成就重新套用默认范围”的断言，与本次用户口径冲突，已明确改为“就绪标志正确完成，但不得重置范围”；旧请求不得提前就绪的断言保留，并新增原始启动控制器执行来证明默认窗口确实应用一次，不是删除初始化。

## 验收

- 范围专项 17 场景、原竞态 13 场景、失败重试 18 场景全部通过。
- 默认前端硬门禁 19 tests OK；当前工作区全量 473 passed、0 failed、0 skipped，pytest 进程退出码 0。
- 本项默认新增一个门禁方法；全量总数包含并行任务已有测试，不能把与前轮的数量差异全算作本项新增。
- 原 18 个隔离契约当前为 7 failed / 11 passed，仅剩存储/键盘事项；未用 skip/xfail 隐藏失败。
- 默认完整脚本回归的 DOM 夹具只补齐标准 Event 和 dispatchEvent，以测试新布局通知；原有开关和绘图断言均保留。

## 发布与数据保护

- 仅替换主模板；镜像 4.0 已固化，实际镜像 sha256:ca65c0032f0a91e5a7d84edd9d7d4bb714149046b95928335da18e439a01a385，发布标签 harbor.techfin.ai/wjl-toolkit/cl_painter:viewport-20261121-224219-side。
- 对实际返回页面的指标/范围/重试函数、初始化和订阅代码段、布局通知绑定与可信发布源码逐字比对后，再执行 17 + 13 + 18 场景，全部通过；旧版本脚本会被检查器拒绝。
- 图表、指标、选股、历史、自动应用查询、折叠新增和五期限制正常；原安全 API 哈希及真实 400 转义保持，服务日志无非预期异常。
- 以切换前最新一致性备份为基线，发布后全部数据库表行数及 SHA-256 内容指纹一致；分类独立环境及生产状态保持。
- 工作区另有并行背驰算法和测试改动，本项没有编辑或发布它们；运行中的算法文件与切换前一致，也没有替其执行全量 dump 或声称算法画线已经确认。
- 没有数据库迁移、真实数据写入、行情流水线、生产服务修改、Git 写操作或镜像推送；没有浏览器人工验收，不把 Node 场景耗时当成浏览器性能。

## 重跑

```bash
node /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/repros/frontend_contracts.js --group viewport_preservation --check
cd /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_frontend_template
cd /home/wjl/TechFinWorkSpace_v2/CLPainter
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider web/backend/tests
```
