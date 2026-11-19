# 待用户逐项决定的问题清单（2026-11-18）

> 最新状态：上一轮批量修复已撤销；Q1/Q2 已完成并提交为 21f6754。2026-11-19 用户追加授权 Q6，现已收紧挂载范围；用户明确保留 privileged: true，运行中的旧容器尚未切换。Q3/Q4/Q5 及附加事项仍待讨论。原问题核查基线为 d666dc2。
> Q1 仅作测试数据库维护，Q2 仅修改两份部署环境文件。新增 Q6 仅涉及 Compose 挂载、部署说明和挂载回归测试，保留原 privileged: true；未更改计算逻辑、工具失败策略或运行中的服务。

## 1. 此前已完成的回滚（历史记录，最新 Q1/Q2 状态见文末）

- 恢复我上一轮修改的 27 个已跟踪文件，移出 7 个新增修复/测试文件；不回退 Git 提交、不改暂存区。
- 保留已提交的 v5 算法、脚本分类、公共镜像版本整理，以及用户的 Pydantic 配置修复。
- 状态表按行恢复到修改前备份：38850 条，calculated_at 为 2026-11-08；撤销新增 5 条状态和 1 条 688827SH 元数据。
- 不整库替换文件；其他标的元数据、自选和其他表保持回滚前状态。
- 停止并移除本轮新增 clpainter-test、专用网络及 4.0-v5fix-20261118 标签；旧 CLPainter 和原 4.0/3.0 镜像保留。
- v5 的 curated / chart_payload 未覆盖或删除，生产 data_set 未修改。
- 不重建已经删除的 71G 临时候选缓存；不自动重开失效报告 HTTP 服务。这两项属于临时资源清理，不是源码或业务数据恢复。

撤销前恢复材料存放在项目之外：

```text
/home/wjl/.codex/tmp/clpainter-recent-rollback-20261118-bd7x2zdb
```

其中 recent_changes.patch、working_tree/、verification_evidence/、database_after_optimizations.db 用于必要时恢复或复核。里面包含已撤回的诊断，不能原样视为待应用补丁。

## 2. 证据分级与总览

| 编号 | 事项 | 证据性质 | 当前是否实施 |
| --- | --- | --- | --- |
| Q1 | 状态表与当前缓存不一致，另有缺失元数据 | 已观察到的业务数据一致性差异 | 已授权并完成数据维护；不改工具策略 |
| Q2 | 部署环境没有明确固定 v5 开关 | 配置事实 + 小样本重算差异 | 已授权并完成两份 env 配置 |
| Q3 | 首段依赖参考缓存 | 已观察到的设计依赖，不直接判作算法错误 | 否，待决定 |
| Q4 | 缓存回归不能充分证明生产者逻辑 | 已证实的测试覆盖边界 | 否，待决定 |
| Q5 | 历史 Tushare 路径的异常行情处理 | 原函数合成输入可复现；不是主 tdata 路径全部有问题 | 否，待决定 |
| Q6 | 生产/测试共享根目录可写 | 潜在越界写风险，未发现已发生误写的证据 | 2026-11-19 追加授权；配置已修复，旧服务未切换 |
| A1 | 容器入口脚本异常退出时的清理 | 脚本级临时假进程复现，非生产故障记录 | 否，附加可选项 |
| A2 | 快照多进程挂起 | 观察到一次挂起，精确根因未确认 | 否，附加观察项 |
| A3 | 交接和冻结材料的维护 | 文档完整性与有效性，不是画线错误 | 否，附加可选项 |

## Q1：状态表与当前缓存不一致

### 已确认的事实
- 修改前快照共 38850 条，计算时间全部停留在 2026-11-08。当前 v5 缓存为 38855 个。
- 以当前缓存和现有 cl_state 规则复算后，与备份表全量比较：4256 条已有记录至少一个字段不同，另缺 5 条；不是 4256 个字段，也不是单凭时间戳判断。
- 例：300327SZ 的 second_point_type 为数据库 1 / 当前缓存复算 0；603138SH 为 0 / 2。
- 缺的 5 条对应 688827SH 五个周期；该标的原 instrument 表没有记录。只读 stock_info 查询能取得其元数据，但写入仍需要用户决定。
- 回滚时曾恢复旧表；本次 Q1 授权后已重新同步，最新结果见文末，不再把回滚时状态当作当前状态。

### 影响与边界
- 图表读取缓存，筛选接口读取 cl_state_snapshot，可能展示不同版本的结果。
- 尚未把全部差异分解成 raw 更新、画线变化或历史计算规则变化；不能一概归因于某次线段重构。
- 一致性核对不等于证明买卖点业务定义唯一正确。

### 请分别决定
- [ ] Q1a 是否先只导出差异，保持数据库不动？
- [x] Q1b 已按 Q1 授权，重新查询只读数据源并补录缺失标的元数据。
- [x] Q1c 已复用现有计算和持久化函数进行全量数据维护；没有修改计算规则或状态更新工具。
- [ ] Q1d 更新工具的部分成功/缺标的跳过/无任务返回策略未改；若要调整，仍需单独确认。

相关代码：
- /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/state/update_cl_state.py
- /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/cl_state/snapshot.py
- /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/api/api_v1/endpoints/test_api.py（stock_screener/query）

## Q2：v5 算法开关未明确写入部署环境

### 已确认的事实
- 已验收 v5 使用 REPAIR_LOOP=0、LOCAL_RESEGMENT=0、LEGAL_SPLIT_SEARCH=1。
- 回滚基线中的 prod.env / test.env 未声明这三个字段，Settings 的默认值均为 0。旧手工容器 backend/.env 则另有开关配置。
- 相同 raw、相同参考缓存下，000068SZ 日线关闭合法搜索为 20 段，开启为 22 段，后者与 v5 一致。

### 影响与边界
- 影响以后重算；仅浏览已经生成好的 v5 图表缓存，不能判断运行时开关是否正确。
- 这不意味着当前所有缓存或图表都已出错。

### 请决定
- [x] Q2a 已在 prod.env / test.env 显式固定 0/0/1。
- [ ] Q2b 保持搜索关闭，并把由此带来的行为变化作为另一版本重新验收？
- [x] Q2c 本次只修改两份环境文件，没有修改 Settings 默认值或流水线脚本。

相关代码：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/_config/settings.py；deploy/env/prod.env；deploy/env/test.env。

## Q3：首段结果依赖参考缓存

### 已确认的事实
- reconcile_first_segments 的设计本来就是使用旧缓存作为迁移锚点。
- 相同 raw 且笔结果相同、开关一致时，159038SZ / 159136SZ 无参考为 1 段，有参考为 2 段并与 v5 一致。
- 原导出默认从输出目录已有缓存取参考；若先移走旧缓存，再向空目录重建，参考输入会变化。

### 正确定位
- 这是可复现条件与迁移依赖，不直接证明线段定义或生成算法错误。
- 不能把“以参考缓存重建相同”说成“仅凭 raw 能独立重建相同”。

### 请决定
- [ ] Q3a 只补文档与明确 --reference-dir 的操作步骤，接受这项设计依赖？
- [ ] Q3b 添加独立的严格重建模式，并保留显式首次初始化入口？
- [ ] Q3c 重新设计为无参考可复现？这会改变行为，需要全量差异和人工验收，不应当作普通整理顺手做。

若选择 Q3b，必须覆盖空源目录、源缺失、参考缺失/损坏、同路径、局部增量及新增标的。上一轮新增严格模式在空源目录时仍提前返回 0，属于那一版实现漏项；现在该模式已撤销，不把它冒充当前项目新增缺陷。普通模式“无任务算成功”是否保留应由用户决定。

相关代码：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/toolbox/datacube.py（dump_data_cache_to_pickle）；/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/app/toolbox/xianduan.py（reconcile_first_segments）。

## Q4：回归测试对生产者的覆盖不充分

### 已确认的事实
- 专门的确认拆分参数化测试是 7 条，规则配置有 17 条；其他回归可能间接覆盖部分情况，不能直接说其余完全无测试。
- 只把这 7 条测试使用的 apply_confirmed_splits 引用替换成原样返回，7 条仍通过；测试读取的输入本来就已经处理好。
- 这证明它们适合做已处理结果的稳定性检查，但不能独立证明拆分生产者真正执行。不能扩大成“全部测试都没有价值”或“拆分算法必然有错”。
- 数据质量旧测试也主要读取已有 raw/cache；不等于异常输入下一次进入转换器仍会正确处理。
- 早期仅重复读取相同缓存的 snapshot 零差异，不能单独证明新生成代码行为未变。后来的实际全量重建提供了更强证据。

### 请决定
- [ ] Q4a 保留现有缓存烟雾/稳定性测试，只新增未拆分输入到预期输出的测试？
- [ ] Q4b 规则是否要求逐条覆盖全部 17 条，并增加 no-op 负控？
- [ ] Q4c 是否加后处理顺序及 raw 到结果的集成测试？与单函数测试分别记录覆盖范围。
- [ ] Q4d 数据缺失时失败还是 skip？这是测试环境策略，应单独确定。

相关代码：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/tests/test_confirmed_splits.py；test_data_quality_regressions.py；test_xianduan_regressions.py；test_bi_regressions.py。

## Q5：历史 Tushare 采集路径的数据质量处理

### 可复现的原函数行为（仅合成数据与临时目录）
- 输入 open/low/high=0、close=1.2，原转换结果仍为 [0,1.2,0,0]。
- 空行情传入 _save_history，会生成内容为 [] 的 pickle。该文件仍有非零文件大小。
- list_date=1800-01-01 的占位标的仍调用历史请求函数。

### 范围限制
- 具体位置是 data_from_tushare_old.py，不是主日更 data_from_tdata_1day.py 全部有同样问题。
- 主 tdata 脚本已有开高低零值填补逻辑，不应因为历史脚本的问题再次无差别改写它。

### 请分开决定
- [ ] Q5a 是否统一历史路径的零 OHLC 填补规则？收盘价异常如何处理需保持既有约束。
- [ ] Q5b 空结果不创建文件；若已有有效旧文件，是保留还是删除？
- [ ] Q5c 日期占位是否只针对 1800-01-01，还是定义更广的无效日期范围？不得未经确认扩大到所有早期合法日期。
- [ ] Q5d 是否只先补合成输入测试，不运行真实采集？

相关代码：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/data_ingestion/data_from_tushare_old.py（_convert_history_to_pv_list、_save_history、_iter_history_for_list）。

## Q6：生产/测试数据挂载边界

> 用户先前决定不处理，2026-11-19 改为授权修复。当前只修改挂载范围并验证；用户明确保留 privileged: true，不执行取消特权项。启动脚本及运行中的旧容器未改，实际服务切换仍需单独确认。

### 修复前已确认的事实
- 原 Compose 已通过项目名、容器名、端口和网络区分服务。
- 但是基础配置把整个 /DataDepartmentTest 和 /mnt/DataDepartmentTest 可写挂给服务，测试进程因此也能到达生产目录。
- 没有证据表明已经发生生产数据误写；这是潜在风险治理，不应描述成既成数据事故。

### 请分别决定
- [x] Q6a 两个 override 各自只挂载自己的可写数据根。
- [x] Q6b 核查 tdata/ddp 依赖后，仅保留公共 /DataDepartment/SourceData 只读挂载，没有挂入另一环境作为基线。
- [x] Q6c 已确认部署取舍：按用户要求保留 privileged: true，不取消特权模式，也不将其继续列为待修复项。
- [ ] Q6d 端口和镜像配置保持原值；未启动常驻新服务或停用旧 CLPainter，切换时间仍由用户决定。

相关配置：/home/wjl/TechFinWorkSpace_v2/CLPainter/docker-compose.yml；docker-compose.prod.yml；docker-compose.test.yml。

## 3. 附加可选观察，不当作已发生业务事故

### A1 入口脚本异常退出路径
- 原入口使用 set -e 和 wait -n；一个子进程非零退出时，脚本可能在显式清理前退出。
- 用临时假进程重现过脚本未完成伴随进程清理；真实 Docker 最终行为还受 PID 1 / 容器停止机制影响。不能把假进程结果扩大为已经发生生产常驻泄漏。
- 可选：只先补异常路径测试；或单独改清理/等待逻辑；健康检查和启动 --wait 是另一项就绪性增强，不与此捆绑。
- 位置：/home/wjl/TechFinWorkSpace_v2/CLPainter/docker/entrypoint.sh。

### A2 快照多进程挂起
- 观察到一次 fork 工作进程无进展。改 spawn 并限制原生线程后，实际全量快照成功。
- 没有完整线程栈和单因素对照，所以“已经确认 NumPy 锁是精确根因”应撤回。准确结论是：观察到挂起，规避方案跑通，精确根因未确认。
- 可选：先保留源码，只记录运行环境、超时和诊断；或安排可重复试验后再决定进程启动策略。
- 位置：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/validation/snapshot_structures.py。

### A3 交接与冻结材料
- 部分交接字段/部署副本说明不够准确：DEFAULT_DATA_ROOT 不是实际可配置环境字段；环境变量和 backend/.env 的优先级要说明。
- 手工复制几个文件的清单不能代替固定版本的完整交付；容器与宿主机曾有部署副本导入改写，不是 Python 会自动改写源码。
- 报告已按用户要求删除，历史 URL 应标为历史而不是当前验收入口。小体积快照、代码身份、开关及输入来源是否长期保留由用户决定。
- 可选：只整理说明，不改代码、不重新开放报告服务。导入路径统一任务此前已被取消，不自动重启。

## 4. 已撤销的误报：stock_close_dr

- 项目股票采集使用 open_dr / close_dr / low_dr / high_dr / volume_dr；ETF 使用 etf_*_dr。
- stock_close_dr 是我在额外 SDK 探针里手工构造错的字段，并非项目业务脚本实际使用的字段。
- 实际股票/ETF 字段在旧、新容器的字段目录检查均没有无效项；因此“stock_close_dr 未注册导致项目采集阻塞”撤回，不再列作待修外部问题。
- 字段目录检查通过不等于真实完整日更已经执行成功；此次并未做真实全量采集。
- 股票脚本及其字段名没有因为这次误报被修改。

实际调用位置：/home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/data_ingestion/data_from_tdata_1day.py（FIELDS、DR_FIELDS，以及 fetch_data(DR_FIELDS, ...)）。

## 5. 决策与验证规则

- 用户可以只批准某个编号或子项；未批准项继续不动。
- 先明确问题范围，再给最小改动和验收条件；数据维护、风险加固、算法行为变更分开。
- “测试通过”“缓存零差异”“新容器健康”各自只证明其实际覆盖的范围，不扩大成全部环节绝对正确。
- 182 项测试是已撤销版本的历史结果；回滚后已实跑：124 passed、0 skipped。不能把两组成绩混用。
- 宿主机曾做 38855 个全量重建；容器内只做 6 个代表性 raw 重算及接口验收，不把它说成容器内全量重建。
- 回滚后的不一致曾保留为待决事项；本次用户已授权 Q1，现已完成数据维护，不扩大为其他未批准修复。

Q1、Q2 已完成原授权范围；Q6 于 2026-11-19 追加授权，最新处理结果见第 7 节。Q3、Q4、Q5、A1、A2、A3 留待后续讨论。

## 6. 本次 Q1/Q2 完成记录（2026-11-18）

- Q1：备份测试数据库，在副本中全量复算并验证，再使用已有 persist_snapshots 对测试库进行事务更新，没有替换数据库文件。
- 覆盖 38855 条状态：missing / extra / mismatched 均为 0；此前 4256 条不一致与缺失 5 条均已同步。
- 缺失的 688827SH 元数据重新从只读 stock_info 查询核实后补录 1 条；自选和其他标的元数据保持不变。
- 筛选接口验证 4 组条件，返回代码集合与复算记录精确一致，不只检查 HTTP 200。
- Q2：prod.env / test.env 增加 REPAIR_LOOP=0、LOCAL_RESEGMENT=0、LEGAL_SPLIT_SEARCH=1；Compose 与 Settings 实际读取均通过，其他解析配置完全相同。
- 仅固定部署环境；开发态 Settings 默认值未修改，宿主机手工任务仍需显式注入相应环境。缓存更新后仍需执行既有状态更新步骤，未修改自动调度。
- Q6 未处理；生产 data_set 未写入，未构建镜像、未部署/重启容器。其余问题没有恢复已撤销的修复。
- 既有回归：124 passed、0 skipped，没有新增 Q4 测试文件。
- 本次备份及验证证据：/home/wjl/.codex/tmp/clpainter-q1-q2-20261118-jidyow05。
- 最近一次写库前备份：/home/wjl/.codex/tmp/clpainter-q1-q2-20261118-jidyow05/instrument_before_publish.db。
- 代码/配置尚未提交 Git。

## 7. Q6 追加授权与配置修复（2026-11-19）

- 用户改为要求修复 Q6，并要求使用冒号短语法挂载；全部使用明确的 `host:container:ro/rw`。
- 公共 Compose 只挂载 `/DataDepartment/SourceData`，权限为只读；移除三个共享整根挂载；按用户确认保留 `privileged: true`。
- 生产 override 只可写挂载 `/mnt/DataDepartmentTest/home/wjl/data_set`；测试 override 只可写挂载同级 `data_set_dev`。
- Docker Compose v2.34.0 实际解析两套配置通过；与修复前比较，除 volumes 外的全部解析配置一致，包括镜像、端口、环境变量和命令。
- 使用现有 4.0 镜像、保留 privileged: true 分别运行生产/测试一次性挂载探针：只看得到本环境数据根，另一环境数据根和旧 /DataDepartmentTest 别名不可见，公共数据源为 ro，本环境数据根挂载为 rw。
- 探针只检查挂载与读取已有文件，没有启动应用、执行数据库迁移、写入生产或测试业务数据；探针容器已清理，未发布端口。
- 在只挂载公共 SourceData 的一次性容器中，tdata 导入成功；脚本实际使用的股票/ETF 共 10 个字段目录检查均通过，全局证券索引可读。没有执行真实全量采集。
- 新增 8 项挂载契约测试；特权模式断言已根据用户明确决定改为保留 true，数据根和只读挂载断言不变；修复前 6 项失败、2 项通过，修复后全部通过；当前全套测试为 133 passed、0 skipped。
- 测试数量包括工作区已有的前端测试变化，不把这些前端修改归入 Q6；前端模板及其测试均未由本次修改。
- deploy/README.md 已说明短语法、数据源依赖、宿主机目录前置检查及并行验收步骤，不再要求先删除旧容器再验收新服务。
- 旧 CLPainter 没有重建，仍保留原挂载；配置层修复和一次性探针通过，不代表常驻服务已经切换或真实全量日更已经验收。
- 本次未修改 Q1/Q2 配置、缓存生成逻辑或其他待决问题；Git 提交按用户后续明确授权执行，不伴随容器切换。

- 提交前用户再次确认 privileged: true 没有必要取消；本次验收仅覆盖声明的挂载范围与常规路径可见性，不作为强安全隔离证明。
