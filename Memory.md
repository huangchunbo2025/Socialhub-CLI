# SocialHub CLI 项目记忆

> 本文件保存有价值的总结信息，供 AI 快速理解项目上下文。
> 完整对话记录见 `memory/YYYY-MM-DD.md`

---

## 记忆系统架构

```
socialhub/
├── Memory.md          # 有价值信息总结 (本文件)
├── User.md            # 用户画像与偏好
├── Heartbeat.md       # 定时任务调度
├── QA.md              # 质量检查流程与记录
└── memory/
    └── YYYY-MM-DD.md  # 每日完整对话记录
```

## QA Agent 工作流程

```
用户需求 → 执行实现 → QA 检查 → 通过? → 交付
                         ↓ 否
                      修正问题 → 重新检查
```

**每次需求完成后必须执行**:
1. 语法检查 - `python -m py_compile`
2. 功能测试 - 验证核心功能
3. 意图匹配 - 对比用户需求与实现
4. 编码兼容 - 检查 Windows GBK
5. 文档更新 - 同步记忆文件

---

## 项目概述

SocialHub.AI CLI 工具，面向数据分析师和营销经理，支持数据查询、报表生成、营销活动管理等功能。

## 技术栈

- Python + Typer (CLI框架)
- Rich (美化输出)
- MCP (Model Context Protocol) 连接分析数据库
- Azure OpenAI (AI助手)

## 关键配置

- 配置文件: `~/.socialhub/config.json`
- 默认模式: `mcp` (直连数据库)
- 数据库: `das_demoen` (StarRocks)

## 已知问题与解决方案

### 1. Azure OpenAI 内容过滤误判

**问题**: 某些中文短语如"再执行一次"会触发 Azure 内容过滤 (self_harm 误判)

**解决方案**: 已实现命令历史功能，直接重复上次命令，不调用 AI

**支持的重复短语**:
- `再执行一次`, `重新执行`, `再来一次`, `再试一次`
- `重复`, `再跑一次`, `重跑`, `上一个`, `!!`
- `repeat`, `again`, `retry`, `redo`

**实现**:
- 历史文件: `~/.socialhub/history.json`
- 保存: 每次执行命令后自动保存
- 重复: 检测到重复短语时直接执行历史命令，不调用 AI

### 2. Windows GBK 编码错误

**问题**: Unicode 字符如 `✓` `¥` 在 Windows 控制台显示时报 GBK 编码错误

**解决方案**:
- 使用 ASCII 替代: `[OK]` 代替 `✓`, `CNY` 代替 `¥`
- 已修复的文件:
  - `cli/output/table.py`
  - `cli/output/export.py`
  - `cli/commands/analytics.py`
  - `cli/commands/skills.py`

### 3. MCP 数据库列名

**问题**: SQL 查询使用错误的列名导致返回空数据

**正确的列名映射** (dwd_v_order 表):
| 用途 | 正确列名 | 错误列名 |
|------|----------|----------|
| 订单金额 | `total_amount` | `paid_amt` |
| 渠道 | `source_name` | `channel_code` |
| 订单日期 | `order_date` | `date` |
| 店铺 | `store_name` | `province` (省份数据为空) |

### 4. 多步骤计划执行

**问题**: AI 生成的多步骤计划只执行第一步就停止

**解决方案**:
- 已更新 `main.py` 的智能识别功能支持多步骤执行
- AI 响应需要使用 `[PLAN_START]` 和 `[PLAN_END]` 标记
- 系统会询问用户确认后自动执行所有步骤

### 5. AI 洞察分析

**功能**: 多步骤执行完成后自动生成 AI 洞察

**实现**:
- `generate_insights()` 函数收集执行结果
- 调用 AI 分析数据并输出:
  - 关键发现 (2-3点)
  - 趋势分析
  - 业务建议 (可执行建议)
- 结果以紫色面板展示

### 6. 定时任务管理

**功能**: 用户可通过自然语言设置定时任务，自动写入 Heartbeat.md

**实现**:
- AI 响应使用 `[SCHEDULE_TASK]` 标记
- `extract_scheduled_task()` 解析任务配置
- `save_scheduled_task()` 写入 Heartbeat.md
- 支持 AI 洞察选项

**示例**:
```
sh 帮我设置一个定时任务，每天晚上8点生成渠道分析报告
→ 解析任务配置
→ 确认后写入 Heartbeat.md
```

## 常用命令

```bash
# 数据分析
sh analytics overview --period=30d     # 业务概览
sh analytics orders --period=30d       # 订单分析
sh analytics orders --by=channel       # 按渠道分析
sh analytics orders --by=province      # 按店铺分析 (实际使用store_name)
sh analytics customers --period=30d    # 客户分析
sh analytics retention --days=7,14,30  # 留存分析

# MCP 数据库
sh mcp tables                          # 列出所有表
sh mcp schema <table_name>             # 查看表结构
sh mcp sql                             # 交互式SQL

# AI 助手
sh ai chat "分析订单趋势" --auto       # 自动执行多步骤计划
sh <自然语言>                          # 智能识别模式
```

## 数据库表结构参考

### dwd_v_order (订单表)
- `code` - 订单编号
- `order_date` - 订单日期 (datetime)
- `customer_code` - 客户编码
- `store_name` - 店铺名称
- `source_name` - 渠道名称
- `total_amount` - 订单金额
- `qty` - 商品数量

### dim_customer_info (客户表)
- `customer_code` - 客户编码
- `customer_name` - 客户名称 (已加密)
- `create_time` - 创建时间
- `source_name` - 来源渠道

## 数据范围

- 订单数据: 2022-10-31 ~ 2026-03-19 (约10,137条)
- 客户数据: 约25,272人
- 近30天: 约418订单, CNY 969,653 销售额

## 文件结构

```
socialhub/
├── cli/
│   ├── main.py              # 入口 + 智能识别
│   ├── config.py            # 配置管理
│   ├── commands/
│   │   ├── analytics.py     # 数据分析命令 (MCP支持)
│   │   ├── ai.py            # AI助手命令
│   │   ├── mcp.py           # MCP数据库命令
│   │   └── ...
│   ├── api/
│   │   ├── client.py        # API客户端
│   │   └── mcp_client.py    # MCP客户端
│   └── output/
│       ├── table.py         # 表格输出
│       ├── export.py        # 导出功能
│       └── report.py        # HTML报告生成
└── docs/                     # 文档
```

## 注意事项

1. **编码**: 所有输出避免使用非ASCII字符
2. **日期过滤**: MCP查询使用 `DATE(order_date) >= '{date}'` 格式
3. **空值处理**: 使用 `COALESCE(column, 'default')` 处理NULL
4. **表格显示**: 分组数据直接返回 list 而非嵌套 dict
