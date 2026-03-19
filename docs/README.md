# SocialHub.AI CLI 产品说明文档

<p align="center">
  <img src="../web/skills-store/logo.png" alt="SocialHub.AI" width="120">
</p>

<p align="center">
  <strong>Customer Intelligence Platform</strong><br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  <a href="https://github.com/huangchunbo2025/Socialhub-CLI">GitHub</a> •
  <a href="https://huangchunbo2025.github.io/Socialhub-CLI/">Skills Store</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#命令参考">命令参考</a>
</p>

---

## 目录

- [产品简介](#产品简介)
- [核心功能](#核心功能)
- [系统要求](#系统要求)
- [安装指南](#安装指南)
- [快速开始](#快速开始)
- [命令参考](#命令参考)
- [MCP 数据库](#mcp-数据库)
- [AI 智能助手](#ai-智能助手)
- [定时任务](#定时任务heartbeat)
- [图表与报告](#图表与报告)
- [Skills Store](#skills-store)
- [配置管理](#配置管理)
- [常见问题](#常见问题)

---

## 产品简介

**SocialHub.AI CLI** 是一款面向数据分析师和营销经理的命令行工具，为 SocialHub.AI 客户智能平台（CIP）提供强大的命令行操作能力。

### 适用人群

| 角色 | 使用场景 |
|------|----------|
| **数据分析师** | 数据查询、报表生成、客户分析、留存分析 |
| **营销经理** | 活动管理、客户分群、优惠券管理、消息发送 |
| **运营人员** | 客户管理、标签管理、积分管理 |
| **开发者** | API 集成、自动化脚本、数据导出 |

### 产品特点

- **智能交互** - 支持自然语言输入，AI 自动解析并执行命令
- **MCP 数据库** - 直连 StarRocks 分析数据库，实时查询
- **多步骤执行** - AI 生成执行计划，确认后自动执行所有步骤
- **AI 洞察** - 执行完成后自动生成数据洞察和业务建议
- **定时任务** - Heartbeat 调度器支持定时自动执行任务
- **可视化输出** - 终端表格、图表生成、HTML 报告
- **技能扩展** - 通过 Skills Store 安装官方认证插件

---

## 核心功能

### 1. 数据分析 (Analytics)

| 功能 | 说明 |
|------|------|
| 数据概览 | KPI 指标卡、业务总览 |
| 客户分析 | 新客、活跃客户、客户画像 |
| 订单分析 | 销售额、客单价、渠道分析 |
| 留存分析 | 7/14/30 天留存率 |
| 图表生成 | 柱状图、饼图、折线图、仪表板 |
| 报告生成 | HTML 分析报告，可导出 PDF |

### 2. MCP 数据库

- 直连 StarRocks 分析数据库
- 交互式 SQL 查询
- 表结构查看
- 实时数据分析

### 3. 客户管理 (Customers)

- 客户搜索与查询
- 客户详情查看
- 客户 360° 画像
- 客户数据导出

### 4. 营销工具 (Marketing)

- 营销活动管理
- 客户分群管理
- 标签体系管理
- 优惠券管理
- 积分管理
- 消息管理

### 5. 定时任务 (Heartbeat)

- 定时执行报表生成
- 每日数据概览
- 自动 Memory 归档
- Windows 任务计划集成

### 6. AI 智能助手

- 自然语言命令解析
- 多步骤计划执行
- 自动数据洞察
- API 超时自动重试

---

## 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10+, macOS 10.14+, Linux |
| **Python** | 3.10 或更高版本 |
| **内存** | 建议 4GB+ |
| **网络** | MCP/API 模式需要网络连接 |

### 依赖包

```
typer[all]      # CLI 框架
rich            # 终端美化
httpx           # HTTP 客户端
pandas          # 数据处理
pydantic        # 数据验证
matplotlib      # 图表生成（可选）
```

---

## 安装指南

### 方式一：从源码安装（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/huangchunbo2025/Socialhub-CLI.git
cd Socialhub-CLI

# 2. 安装依赖
pip install -e .

# 3. 安装图表支持（可选）
pip install matplotlib
```

### 验证安装

```bash
socialhub --version
```

运行 `socialhub` 查看欢迎画面：

```
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \  |_ _|
 \___ \ / _ \ / __| |/ _` | | |_| | | | | '_ \  / _ \  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \ | |
 |____/ \___/ \___|_|\__,_|_|_| |_|\__,_|_.__//_/   \_\___|

                v0.1.0 | Customer Intelligence Platform

+------------------------------- Quick Start --------------------------------+
|   socialhub analytics overview    Business overview                        |
|   socialhub analytics orders      Order analysis                           |
|   socialhub mcp sql               Interactive SQL                          |
|   socialhub ai chat "..."         AI assistant                             |
|   socialhub <query>               Smart mode                               |
|   socialhub --help                All commands                             |
+----------------------------------------------------------------------------+
```

### Windows PowerShell 别名配置

```powershell
# 打开 PowerShell 配置文件
notepad $PROFILE

# 添加以下内容
Set-Alias -Name sh -Value "C:\Users\<用户名>\AppData\Local\Python\pythoncore-3.14-64\Scripts\socialhub.exe"

# 保存后重新加载
. $PROFILE
```

---

## 快速开始

### 初始化配置

```bash
# 初始化配置文件
socialhub config init

# 查看当前配置
socialhub config show
```

### 第一个命令

```bash
# 查看数据概览（MCP 模式）
socialhub analytics overview --period=30d

# 使用自然语言
socialhub 查看最近30天的销售数据
```

### 生成报告

```bash
# 生成 HTML 分析报告（保存到 Doc/ 文件夹）
socialhub analytics report --title="月度分析报告"
```

---

## 命令参考

### 数据分析 (analytics)

| 命令 | 说明 | 示例 |
|------|------|------|
| `overview` | 数据概览 | `socialhub analytics overview --period=30d` |
| `customers` | 客户分析 | `socialhub analytics customers --period=30d` |
| `orders` | 订单分析 | `socialhub analytics orders --by=channel` |
| `retention` | 留存分析 | `socialhub analytics retention --days=7,14,30` |
| `chart` | 生成图表 | `socialhub analytics chart pie --data=customers` |
| `report` | 生成报告 | `socialhub analytics report --output=Doc/report.html` |

#### 订单分析选项

```bash
# 按渠道分析
socialhub analytics orders --by=channel

# 按店铺分析
socialhub analytics orders --by=province

# 指定时间周期
socialhub analytics orders --period=7d
socialhub analytics orders --period=30d
socialhub analytics orders --period=90d
```

#### 图表类型

```bash
# 柱状图
socialhub analytics chart bar --data=customers --group=customer_type

# 饼图
socialhub analytics chart pie --data=customers --group=customer_type

# 折线图
socialhub analytics chart line --data=orders

# 综合仪表板
socialhub analytics chart dashboard --output=Doc/dashboard.png
```

---

## MCP 数据库

MCP (Model Context Protocol) 直连 StarRocks 分析数据库，实现实时数据查询。

### 基本命令

```bash
# 查看所有表
socialhub mcp tables --database=das_demoen

# 查看表结构
socialhub mcp schema dwd_v_order --database=das_demoen

# 交互式 SQL
socialhub mcp sql

# 执行查询
socialhub mcp query "SELECT COUNT(*) FROM dwd_v_order" --database=das_demoen
```

### 常用表说明

| 表名 | 说明 |
|------|------|
| `dwd_v_order` | 订单明细表 |
| `dim_customer_info` | 客户信息表 |
| `dim_member_info` | 会员信息表 |
| `dwd_v_coupon_record` | 优惠券记录 |
| `dwd_v_points_record` | 积分记录 |

### dwd_v_order 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | varchar | 订单编号 |
| `order_date` | datetime | 订单日期 |
| `customer_code` | varchar | 客户编码 |
| `store_name` | varchar | 店铺名称 |
| `source_name` | varchar | 渠道名称 |
| `total_amount` | decimal | 订单金额 |
| `qty` | int | 商品数量 |

---

## AI 智能助手

### 自然语言交互（智能模式）

直接输入中文自然语言，系统自动识别并调用 AI：

```bash
socialhub 分析最近30天的销售趋势
socialhub 查看各渠道订单分布
socialhub 目前客户表里有哪些字段
socialhub 帮我设置每天8点生成销售报告的定时任务
```

### 多步骤执行

AI 会生成执行计划，确认后自动执行所有步骤：

```bash
socialhub ai chat "全面分析最近30天的业务情况" --auto
```

执行流程：
1. AI 生成多步骤分析计划
2. 用户确认执行
3. 自动依次执行每个步骤
4. 完成后生成 AI 洞察

### AI 洞察

多步骤执行完成后，自动生成：
- 关键发现（2-3 点）
- 趋势分析
- 业务建议（可执行建议）

### API 超时重试

遇到网络超时自动重试 3 次：

```
API 请求超时，2秒后重试 (1/3)...
API 请求超时，4秒后重试 (2/3)...
```

### AI 配置

```bash
# Azure OpenAI 配置
socialhub config set ai.provider azure
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
socialhub config set ai.azure_deployment gpt-4o

# OpenAI 配置
socialhub config set ai.provider openai
socialhub config set ai.openai_api_key YOUR_API_KEY
```

---

## 定时任务（Heartbeat）

Heartbeat 是内置的定时任务调度系统，支持自动执行定期任务。

### 命令列表

```bash
# 查看所有定时任务
socialhub heartbeat list

# 检查并执行到期任务
socialhub heartbeat check

# 强制执行所有待处理任务
socialhub heartbeat check --force

# 预览将要执行的任务（不实际执行）
socialhub heartbeat check --dry-run

# 手动执行指定任务
socialhub heartbeat run daily-overview

# 查看 Windows 任务计划设置说明
socialhub heartbeat setup
```

### 任务配置文件

任务配置在 `~/socialhub/Heartbeat.md` 文件中：

```markdown
### 1. 每日数据概览
- **ID**: daily-overview
- **频率**: 每天 09:00
- **状态**: `pending`
- **命令**:
  ```bash
  sh analytics overview --period=today
  ```
```

### 设置 Windows 自动执行

在 PowerShell 中运行：

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\<用户名>\AppData\Local\Python\pythoncore-3.14-64\Scripts\socialhub.exe" -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "SocialHub Heartbeat" -Action $action -Trigger $trigger -Description "Hourly heartbeat check"
```

---

## 图表与报告

### 图表生成

支持 5 种图表类型：

| 类型 | 命令 | 说明 |
|------|------|------|
| 柱状图 | `chart bar` | 分类数据对比 |
| 饼图 | `chart pie` | 占比分布 |
| 折线图 | `chart line` | 趋势变化 |
| 漏斗图 | `chart funnel` | 转化分析 |
| 仪表板 | `chart dashboard` | 综合视图 |

### HTML 报告

```bash
# 生成报告（默认保存到 Doc/ 文件夹）
socialhub analytics report --title="月度分析报告"

# 自定义输出路径
socialhub analytics report --output=Doc/monthly_report.html

# 不包含客户列表
socialhub analytics report --no-customers
```

#### 导出 PDF

1. 生成报告后自动在浏览器中打开
2. 按 `Ctrl + P` 打开打印对话框
3. 选择"另存为 PDF"

---

## Skills Store

Skills Store 提供官方认证的技能插件，扩展 CLI 功能。

### 浏览与安装

```bash
# 浏览所有技能
socialhub skills browse

# 安装技能
socialhub skills install data-export-plus

# 查看已安装
socialhub skills list
```

### 在线商店

访问：https://huangchunbo2025.github.io/Socialhub-CLI/

---

## 配置管理

### 配置文件位置

- Windows: `C:\Users\<用户名>\.socialhub\config.json`
- macOS/Linux: `~/.socialhub/config.json`

### 常用配置命令

```bash
# 查看所有配置
socialhub config show

# 设置 MCP 模式（默认）
socialhub config set mode mcp

# 设置本地模式
socialhub config set mode local
socialhub config set local.data_dir ./data

# 设置 AI 配置
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
```

---

## 常见问题

### Q: API 请求超时怎么办？

**A:** 系统会自动重试 3 次。如果仍然失败，请检查网络连接或稍后重试。

### Q: 如何查看客户表的字段？

**A:** 使用 MCP 查询：

```bash
socialhub mcp query "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_NAME = 'dim_customer_info'" --database=das_demoen
```

### Q: 定时任务没有执行？

**A:** 需要设置 Windows 任务计划或手动运行：

```bash
socialhub heartbeat check
socialhub heartbeat setup  # 查看设置说明
```

### Q: 报告保存在哪里？

**A:** 默认保存到项目的 `Doc/` 文件夹。

---

## 技术支持

- **GitHub Issues**: https://github.com/huangchunbo2025/Socialhub-CLI/issues
- **Skills Store**: https://huangchunbo2025.github.io/Socialhub-CLI/

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  © 2024 SocialHub.AI. All rights reserved.
</p>
