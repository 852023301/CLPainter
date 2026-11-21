# 标的最新行业、概念和地域采集

## 功能边界

- 入口：web/backend/scripts/data_ingestion/update_instrument_classification.py。
- 标的名单只来自本实例 SQLite 的 instrument 表，限定 market=cn、asset_class=stock，排除未上市和已退市记录，停牌股票不排除。
- 指数、ETF、其他市场不会被错误赋予股票行业，也不会根据数据源的额外列创建 instrument。
- 本次新增独立元数据日批，不改行情、复权方式、画线算法、状态计算或前端。

## 结果表

instrument_classification 仅有九列：instrument_id、sw_l1_code、sw_l1_name、sw_l2_code、sw_l2_name、sw_l3_code、sw_l3_name、concepts、regions。

instrument_id 同时是主键和指向 instrument.id 的外键，删除 instrument 时级联删除。一只股票只有一行；重复执行完整替换 JSON 列表，不累积旧概念，也不产生历史版本。

结果不保存抓取日期、更新时间、数据日期、标签有效期或发布时间。代码在内存中使用这些时间完成有效性检查，任务输出只有计数。

concepts 中每项包含 code、name、paths。paths 保留 class_code、class_name、sub_class_code、sub_class_name、concept_name。相同概念代码在不同分类路径下可能使用不同名称，展示名取已发布的最新目录记录，原始名称保留在各路径中；同一最新发布时间仍有冲突时拒绝发布。

regions 是 concepts 中类别代码为 18 的地域投影；concepts 保留全量有效标签，不能将两个列表数量相加统计。

NULL 表示来源没有提供可确认的概念数据，[] 才表示本次确认没有有效概念。未知不会用旧概念填充。行业归属缺失、或目录已过期时，对应代码和名称为空。

## 来源与有效期

1. 批量 fetch_data 读取 sector、industry、subindustry、concept_l3、industry_info；概念固定为 V1，不混用不同版本或其他平台。
2. 最近十四个自然日只用于查找最近可用的源快照，不是结果保存周期。各归属字段的最新可用日期必须一致；不一致或无数据时失败，不按股票单独向前补值。
3. 概念目录通过 query_concept_list 读取。股票归属有效期通过 query_concept_stocks 读取，股票筛选参数严格由 instrument 生成。
4. 行业目录、概念目录及股票归属均按本次查询开始时刻（Asia/Hong_Kong）判断有效。概念目录尚未发布、未来生效、状态终止及已过期的记录不会写入。
5. 当前概念关系接口起止日期都包含边界。2200-01-01 代表未设置终止日期。标的退市日期按项目现有的排他边界处理。
6. industry_info 返回新旧全量目录，不能依赖 fetch_data 的日期参数替代目录有效期检查。
7. 普通概念矩阵不覆盖北交所，北交所行业代码也不能直接关联普通目录。当前 instrument 只有沪深股票；若将北交所股票加入名单，脚本会因覆盖缺失失败，而非声称完整覆盖或保存假空集合。

最新指本次查询时源端已提供的最新完整数据，不表示该数据源具有完整 PIT 能力，也不保证日更之后任意时刻直接读库仍实时最新。

## 发布与故障处理

脚本使用与实例数据库绑定的空文件锁串行化整次采集，防止较早启动的任务覆盖更新结果；锁文件不包含业务数据或时间。先完成全量读取和校验，再开启 SQLite 写事务更新全部结果；异常回滚，不发布半批数据。写入前再次检查 instrument 身份集合，若采集期间名单变化则失败，重新运行即可。已离开有效股票范围的旧结果会清理。

源查询失败、缺少目标股票列、代码无法关联目录、最新日期不一致或元数据存在无法确定的冲突，均返回非零退出码；流水线停止后续步骤。缺失值单独计数，不能据此宣传分类内容零缺失。

## 接入流水线

现有日更流水线变为：

1. meta_info.py 同步 instrument。
2. update_instrument_classification.py 更新本功能结果。
3. data_from_tdata_1day.py 更新日线。
4. 原有四个周期聚合并行运行。
5. dump_stock_caches.py 导出缓存。
6. update_cl_state.py 更新状态，保留部署环境既有的额外参数。

沿用现有每日流水线触发机制，不新增 Web worker 定时器、不安装系统 cron、不改变原有选股归档参数。

## 部署与运行

先备份目标 SQLite，在目标环境运行 Alembic 迁移，再启用新脚本和流水线。迁移 a8e4c1d6f0b3 接在现有 f7d3b0a5c9e2 后，只新增本功能表，降级仅删除该表。

~~~bash
export PYTHONPATH=/home/wjl/TechFinWorkSpace_v2
python -m alembic -c /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/alembic.ini upgrade head

# 只采集和校验，不写入结果表；不要求先创建本功能表。
python /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/data_ingestion/update_instrument_classification.py --dry-run

# 正式更新当前 DB_PATH 对应实例。
python /home/wjl/TechFinWorkSpace_v2/CLPainter/web/backend/scripts/data_ingestion/update_instrument_classification.py
~~~

不要为验证本功能执行真实行情重建或全量画线流水线。单元测试使用临时 SQLite；真实数据验证先 dry-run，再在隔离数据库中验证完整写入和重复执行。不要未经许可修改远程 Python 或迁移生产数据库。


## 本地验证记录

- 分类逻辑与脚本布局专项：62 项通过，包含有效期边界、未知与空集合区分、同代码多路径名称、事务失败保护、instrument 范围变化、重复替换、级联删除、迁移升降级和并发锁。
- 真实源只读验证：5,224 个 instrument 股票，107,962 条有效概念关系、5,233 条地域关系；1 个标的的概念数据未知，保留 NULL。
- 临时 SQLite 迁移后真实写入两次：每次均为 5,224 行，主键无重复，范围外标的为 0，九列结构无时间字段。
- 初次本地验证时未迁移实例 SQLite，未写入本功能表；后续测试容器执行情况见下面的部署记录。未提交 Git，未执行真实行情或画线重算流水线。
- 项目全量回归单独运行；专项与真实数据验证通过不表示已有画线验收用例全部通过。完整结果以本次全量测试日志为准。
- 最终项目全量回归：377 通过、1 失败（test_segment_regression[S25] 的线段尾部与既有验收期望不一致），未跳过或放宽断言；本次没有修改 toolbox、参考缓存或该回归用例，因此整体全量验收尚未通过。日志：/tmp/clpainter-classification-full-tests-delivery.log。


## 测试容器的独立任务环境

测试镜像 4.0 的共享环境包含 pandas 3.1.1，而 tdata 2.63.0 的概念读取仍依赖 pandas 2.x 行为。不能在运行中的共享 Web/计算环境中原地替换依赖。

分类任务使用 /root/CLPainter/.venv-classification，继承原环境的其他依赖，仅在该环境安装 pandas==2.3.3。原 /root/mambaforge/envs/echarts 环境保持不变。

流水线优先使用 CLPAINTER_CLASSIFICATION_PYTHON 显式指定的解释器；未指定且项目 .venv-classification/bin/python 存在时，仅分类步骤使用它；否则沿用 PYTHON_BIN。元数据、行情、聚合、缓存和状态步骤继续使用原解释器。

~~~bash
/root/mambaforge/envs/echarts/bin/python -m venv --system-site-packages /root/CLPainter/.venv-classification
/root/CLPainter/.venv-classification/bin/python -m pip install --no-deps --only-binary=:all: pandas==2.3.3
/root/CLPainter/.venv-classification/bin/python /root/CLPainter/web/backend/scripts/data_ingestion/update_instrument_classification.py --dry-run
~~~

这不修改 tdata 的供应商代码，也不把 V1 概念悄悄改为其他版本。重建测试镜像时需将本功能代码与隔离环境的创建步骤纳入镜像/部署过程；手工同步和环境目录只属于当前容器的可写层。


## 2026-11-21 测试容器执行记录

- 容器 clpainter-test，APP_ENV=test，目标数据库 /mnt/DataDepartmentTest/home/wjl/data_set_dev/instrument.db，未操作生产容器或生产数据库。
- 迁移前已通过 SQLite 在线备份保存到 /mnt/DataDepartmentTest/home/wjl/data_set_dev/backups/instrument-classification-d3t229qt/instrument.db；相同目录保留原模型、原流水线、备份清单及 classification-run.log。
- 已迁移到 a8e4c1d6f0b3，并使用隔离任务环境完成正式采集写入：5,224 行、107,554 条有效概念关系、5,233 条地域关系；1 个标的的概念未知，保存 NULL，行业缺失为 0。
- 写入后检查：每个 instrument 一行、应覆盖标的遗漏为 0、范围外标的为 0、分类外键违规为 0、数据库 integrity_check 为 ok，分类表九列均不包含时间字段。
- 当前测试容器流水线已同步解释器选择逻辑，仅分类步骤使用 .venv-classification；共享环境 pandas 3.1.1 未被卸载或替换，分类环境独立安装 pandas 2.3.3。未重启容器或 Web 服务。
- 本次采用当前容器可写层部署。旧 4.0 镜像不包含新迁移、分类脚本及隔离环境；重建容器前必须构建包含这些内容的新镜像，否则无法识别已经迁移的测试数据库版本。
- 新增解释器隔离与失败短路测试后，分类与脚本布局专项为 69 项通过。
- 兼容解释器接入后的项目全量测试：387 通过、1 失败，剩余仍为既有 S25 线段尾部回归，未修改算法或放宽断言。日志 /tmp/clpainter-classification-runtime-tests.log。
