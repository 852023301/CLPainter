# AGENTS.md - CLPainter 开发指南

本文档为 AI 代理在 CLPainter 项目中工作提供指南。仅保留与本项目相关的部分。

## 项目概述

CLPainter 是一个基于缠论的 K 线画线与指标可视化项目（CL 画线）。

- **后端**: FastAPI (Python 3.9+)，位于 `web/backend/`
- **前端**: 单页 HTML + lightweight-charts v4.1.0，模板位于 `web/backend/app/templates/`
- **计算核心**: 缠论算法（笔、线段、分型、缺口、合并 K 线）位于 `web/backend/app/toolbox/`

### 目录结构

```
CLPainter/
├── web/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/api_v1/endpoints/   # API 端点（test_api.py 含图表 demo）
│   │   │   ├── templates/              # HTML 模板（lightweight_charts_demo.html）
│   │   │   ├── toolbox/                # 核心算法（bi, fenxing, xianduan, gap, calculate）
│   │   │   ├── data_set/               # 数据获取（data_from_tushare.py）
│   │   │   ├── _config/                # 配置
│   │   │   └── main.py                 # 应用入口
│   │   └── run.sh                      # 启动脚本
│   └── deploy/                         # 部署配置
├── docker/
├── docker-compose.yml
├── requirements_pip.txt
└── requirements_conda.txt
```

## 运行

```bash
cd CLPainter/web/backend/
bash run.sh
```

## 远程环境

- **SSH 别名**: `CL` → 172.17.1.5:36602（密码认证）
- **远程项目路径**: `/root/CLPainter/`
- **验证地址**: `http://172.17.1.5:15000/api/v1/test_api/lightweight_charts_demo?precision=3`

### 部署工作流

1. **本地修改优先** — 默认修改本地代码（`C:\Users\wjl\Documents\work\TechFinWorkSpace_v2\CLPainter`）。
2. **远程 HTML 模板可直接部署**（scp 到 CL），无需询问。
3. **修改远程 Python 代码前必须询问用户许可。**
4. **Git 操作（提交、回滚、变更）前必须询问用户许可。**
5. **浏览器验证仅在用户明确要求时进行** — 较为耗时。

### SSH 操作

```bash
# 检查服务
ssh CL "ps aux | grep main.py"

# 部署 HTML 模板
scp CLPainter/web/backend/app/templates/lightweight_charts_demo.html CL:/root/CLPainter/web/backend/app/templates/

# 重启服务（修改 Python 后需要）
ssh CL "cd /root/CLPainter/web/backend && bash run.sh"
```

## 文件编码（关键）

- **所有文件为 UTF-8（无 BOM），换行符为 CRLF。** 编辑后必须保持不变。
- **PowerShell 会损坏中文（默认 GBK）** — 不要用 PowerShell 直接读写包含中文的文件。
- **始终通过 Node REPL (`mcp__node_repl__js`) 编辑文件**，使用 `node:fs`：

```javascript
const fs = await import('node:fs');
// 读取
const text = fs.readFileSync(path, 'utf8');
// 写入（UTF-8 无 BOM）
fs.writeFileSync(path, content, 'utf8');
```

- **编辑后必须验证**：重新读取文件确认无乱码（如 鐢ㄨ、鏁版嵁、U+FFFD）。
- **不要将含中文/非 ASCII 的文件编辑委托给子代理** — 编码处理不可靠，直接在主进程中编辑。

## 代码风格

### Python

- **行宽**: 120 字符
- **格式化**: Black（`black . --line-length 120`）
- **缩进**: 4 空格
- **类型提示**: 函数签名使用类型提示
- **命名**:
  - 变量/函数: `snake_case`
  - 类: `PascalCase`
  - 常量: `UPPER_SNAKE_CASE`
  - 私有: 前缀下划线
- **导入**: 绝对导入，分组排列（标准库 → 第三方 → 本地）

### JavaScript / HTML

- 单页模板，内联 `<style>` 与 `<script>`
- 注释使用中文即可
- lightweight-charts v4.1.0 API（注意版本差异）

## 前端图表技术要点

基于 lightweight-charts v4.1.0，使用时需注意以下关键特性：

- **`autoscaleInfoProvider`** 是**序列级**选项，需保持 `autoScale: true` 才会触发。
- **`IPriceScaleApi`**（v4）仅有 `applyOptions`、`options`、`width`，无 `setVisiblePriceRange`（v5 特性）。
- 共享价格刻度范围 = 所有序列自动缩放范围的**并集**。
- `autoscaleInfoProvider` 返回的 `base` 是**整个序列**的极值，而非可见窗口 — 需通过 `chart.timeScale().getVisibleLogicalRange()` 手动计算可见范围。
- 浏览器 `evaluate` 运行在**隔离环境 (isolated world)**，无法访问页面的 `const`/闭包变量。

### 副图同步（主图与成交量/BOLL/RSI/MACD 副图）

- 所有副图共享同一时间刻度，通过 `subscribeVisibleLogicalRangeChange` 同步缩放与滚动。
- 光标影线通过 `subscribeCrosshairMove` 在所有图之间同步。
- **指标偏移问题**: 副图数据的时间戳必须与主图精确对齐，否则会出现约一个交易日的水平偏移。

## 指标计算

后端通过 `web/backend/app/toolbox/calculate.py` 统一计算指标：

- **均线 (MA)**: `calculate_ma_list`，周期由全局变量 `DEFAULT_MA_PERIODS` 控制
- **均线颜色**: `calculate_ma_colors`，基于周期种子生成确定性颜色
- **BOLL (26, 2)**: `calculate_boll_indicator`
- **RSI (6, 12, 24)**: `calculate_rsi_indicator`
- **MACD (10, 21, 7)**: `calculate_macd_indicator`（含变色柱、面积、连增统计等完整特性）

所有指标在后端计算，前端仅负责渲染。

### MACD 副图缩放注意事项

MACD 副图涉及柱状图与 DIFF/DEA 线的协同缩放，需注意：

- 柱状图与线必须共享同一 `autoscaleInfoProvider`，否则缩放时柱子会反转或变形。
- DIFF/DEA 线允许超出指标框（超出部分不显示），以避免柱子被「压制」。
- MACD 副图高度固定为 180px，其余副图（成交量/BOLL/RSI）为 120px。

## 安全注意事项

- 本项目含 `_config` 配置目录与 `.env` 环境变量，**不要泄露或提交敏感信息**。
- API 端点 `test_api.py` 用于 demo，不要在生产环境中暴露未经验证的参数。

## 常见操作

### 更新远程 HTML 模板

```bash
scp CLPainter/web/backend/app/templates/lightweight_charts_demo.html CL:/root/CLPainter/web/backend/app/templates/
```

### 检查远程服务状态

```bash
ssh CL "ps aux | grep main.py"
```

### 查看远程日志

```bash
ssh CL "tail -50 /root/CLPainter/web/backend/nohup.out"
```

## 注意事项

1. **本地为准**: 默认修改本地代码，远程部署前先本地完成。
2. **远程 Python 改动需许可**: 修改远程 Python 文件前必须询问用户。
3. **Git 操作需许可**: 提交、回滚等变更操作前必须询问用户。
4. **浏览器验证需许可**: 仅在用户明确要求时使用浏览器验证。
5. **Node REPL 编辑**: 含中文的文件始终通过 Node REPL 编辑，避免 PowerShell 编码问题。
6. **Node REPL 持久性**: `const`/`let` 声明在调用间持久；如遇 "Identifier already declared"，使用 `mcp__node_repl__js_reset` 重置后重新声明，或改用 `var`。
