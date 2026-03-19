# SocialHub.AI CLI 产品说明文档

<p align="center">
  <img src="../web/skills-store/logo.png" alt="SocialHub.AI" width="120">
</p>

<p align="center">
  <strong>Stop Adding AI, We Are AI.</strong>
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
- [AI 智能助手](#ai-智能助手)
- [图表与报告](#图表与报告)
- [Skills Store](#skills-store)
- [配置管理](#配置管理)
- [常见问题](#常见问题)

---

## 产品简介

**SocialHub.AI CLI** 是一款面向数据分析师和营销经理的命令行工具，为 SocialHub.AI 客户互动平台（CEP）提供强大的命令行操作能力。

### 适用人群

| 角色 | 使用场景 |
|------|----------|
| **数据分析师** | 数据查询、报表生成、客户分析、留存分析 |
| **营销经理** | 活动管理、客户分群、优惠券管理、消息发送 |
| **运营人员** | 客户管理、标签管理、积分管理 |
| **开发者** | API 集成、自动化脚本、数据导出 |

### 产品特点

- **智能交互** - 支持自然语言输入，AI 自动解析并执行命令
- **双模式支持** - 支持 API 模式和本地数据模式
- **可视化输出** - 终端表格、图表生成、HTML 报告
- **技能扩展** - 通过 Skills Store 安装官方认证插件

---

## 核心功能

### 1. 数据分析 (Analytics)

```
┌─────────────────────────────────────────────────────────┐
│  📊 数据概览    📈 趋势分析    👥 客户分析    📦 订单分析  │
│  🔄 留存分析    🎯 活动分析    🎫 优惠券分析  💰 积分分析  │
└─────────────────────────────────────────────────────────┘
```

### 2. 客户管理 (Customers)

- 客户搜索与查询
- 客户详情查看
- 客户 360° 画像
- 客户数据导出

### 3. 营销工具 (Marketing)

- 营销活动管理
- 客户分群管理
- 标签体系管理
- 优惠券管理
- 积分管理
- 消息管理

### 4. 可视化与报告

- **图表生成**: 柱状图、饼图、折线图、漏斗图、仪表板
- **HTML 报告**: 自动生成可打印为 PDF 的分析报告

### 5. AI 智能助手

- 自然语言命令解析
- 智能命令推荐
- 自动执行功能

---

## 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10+, macOS 10.14+, Linux |
| **Python** | 3.10 或更高版本 |
| **内存** | 建议 4GB+ |
| **网络** | API 模式需要网络连接 |

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

### 方式二：pip 安装

```bash
pip install socialhub-cli
```

### Windows PowerShell 配置

为了方便使用，建议配置 PowerShell 别名：

```powershell
# 打开 PowerShell 配置文件
notepad $PROFILE

# 添加以下内容
function sh { & "python" -m socialhub.cli.main $args }

# 保存后重新加载
. $PROFILE
```

---

## 快速开始

### 初始化配置

```bash
# 初始化配置文件
sh config init

# 设置为本地模式（使用 CSV 数据）
sh config set mode local
sh config set local.data_dir ./data

# 查看当前配置
sh config show
```

### 第一个命令

```bash
# 查看数据概览
sh analytics overview

# 查看客户列表
sh customers list

# 使用自然语言
sh 查看最近30天的销售数据
```

### 生成报告

```bash
# 生成 HTML 分析报告
sh analytics report --output=report.html

# 生成图表
sh analytics chart pie --data=customers --group=customer_type
```

---

## 命令参考

### 数据分析 (analytics)

| 命令 | 说明 | 示例 |
|------|------|------|
| `overview` | 数据概览 | `sh analytics overview --period=30d` |
| `customers` | 客户分析 | `sh analytics customers --period=30d` |
| `orders` | 订单分析 | `sh analytics orders --by=channel` |
| `retention` | 留存分析 | `sh analytics retention --days=7,14,30` |
| `chart` | 生成图表 | `sh analytics chart pie --data=customers` |
| `report` | 生成报告 | `sh analytics report --output=report.html` |

#### 图表类型

```bash
# 柱状图
sh analytics chart bar --data=customers --group=customer_type --output=bar.png

# 饼图
sh analytics chart pie --data=customers --group=customer_type --output=pie.png

# 折线图（需要日期数据）
sh analytics chart line --data=orders --output=trend.png

# 漏斗图
sh analytics chart funnel --output=funnel.png

# 综合仪表板
sh analytics chart dashboard --output=dashboard.png
```

#### 报告生成

```bash
# 基础报告
sh analytics report

# 自定义标题
sh analytics report --title="2024年Q1分析报告"

# 不包含客户列表
sh analytics report --no-customers

# 指定输出路径
sh analytics report --output=C:\Reports\monthly.html
```

### 客户管理 (customers)

| 命令 | 说明 | 示例 |
|------|------|------|
| `list` | 客户列表 | `sh customers list --type=member` |
| `get` | 客户详情 | `sh customers get C001` |
| `search` | 搜索客户 | `sh customers search --phone=138` |
| `portrait` | 客户画像 | `sh customers portrait C001` |
| `export` | 导出客户 | `sh customers export --output=customers.csv` |

### 分群管理 (segments)

| 命令 | 说明 | 示例 |
|------|------|------|
| `list` | 分群列表 | `sh segments list` |
| `get` | 分群详情 | `sh segments get SEG001` |
| `create` | 创建分群 | `sh segments create --name="VIP客户"` |
| `export` | 导出分群 | `sh segments export SEG001 --output=vip.csv` |

### 标签管理 (tags)

| 命令 | 说明 | 示例 |
|------|------|------|
| `list` | 标签列表 | `sh tags list --type=rfm` |
| `get` | 标签详情 | `sh tags get TAG001` |
| `create` | 创建标签 | `sh tags create --name="高价值"` |

### 营销活动 (campaigns)

| 命令 | 说明 | 示例 |
|------|------|------|
| `list` | 活动列表 | `sh campaigns list --status=running` |
| `get` | 活动详情 | `sh campaigns get CAMP001` |
| `analysis` | 活动分析 | `sh campaigns analysis CAMP001 --funnel` |
| `calendar` | 营销日历 | `sh campaigns calendar --month=2024-03` |

### 优惠券 (coupons)

| 命令 | 说明 | 示例 |
|------|------|------|
| `rules list` | 规则列表 | `sh coupons rules list` |
| `list` | 优惠券列表 | `sh coupons list --status=unused` |
| `analysis` | 使用分析 | `sh coupons analysis RULE001` |

### 积分 (points)

| 命令 | 说明 | 示例 |
|------|------|------|
| `rules list` | 规则列表 | `sh points rules list` |
| `balance` | 积分余额 | `sh points balance M001` |
| `history` | 积分历史 | `sh points history M001` |

### 消息 (messages)

| 命令 | 说明 | 示例 |
|------|------|------|
| `templates list` | 模板列表 | `sh messages templates list --channel=sms` |
| `records` | 发送记录 | `sh messages records --status=success` |
| `stats` | 消息统计 | `sh messages stats --period=7d` |

---

## AI 智能助手

### 自然语言交互

SocialHub CLI 支持直接输入中文自然语言，系统会自动识别并调用 AI 进行命令解析：

```bash
# 直接输入自然语言
sh 查看所有VIP会员
sh 分析最近30天的订单数据
sh 生成客户分布饼图
sh 导出高价值客户到Excel
```

### AI 配置

#### Azure OpenAI 配置

```bash
# 设置 Azure OpenAI
sh config set ai.provider azure
sh config set ai.azure_endpoint https://your-resource.openai.azure.com
sh config set ai.azure_api_key YOUR_API_KEY
sh config set ai.azure_deployment gpt-4o
```

#### OpenAI 配置

```bash
# 设置 OpenAI
sh config set ai.provider openai
sh config set ai.openai_api_key YOUR_API_KEY
sh config set ai.openai_model gpt-3.5-turbo
```

### AI 命令模式

```bash
# 使用 AI 聊天模式
sh ai chat "查看客户列表"

# 自动执行生成的命令
sh ai chat "查看VIP会员" -e

# 获取帮助
sh ai help analytics
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

#### 参数说明

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--data` | 数据源 | customers, orders |
| `--group` | 分组字段 | customer_type, channel, province |
| `--metric` | 统计指标 | count, total_spent, orders |
| `--output` | 输出路径 | 支持 .png, .jpg |
| `--title` | 图表标题 | 自定义文本 |

### HTML 报告

生成专业的 HTML 分析报告，支持打印为 PDF：

```bash
sh analytics report --output=report.html --title="月度分析报告"
```

#### 报告内容

- 📊 数据概览（KPI 指标卡）
- 📈 可视化图表（自动嵌入）
- 👥 客户列表（可选）
- 📦 订单列表（可选）

#### 导出 PDF

1. 生成报告后自动在浏览器中打开
2. 按 `Ctrl + P` 打开打印对话框
3. 选择"另存为 PDF"
4. 点击保存

---

## Skills Store

Skills Store 提供官方认证的技能插件，扩展 CLI 功能。

### 浏览技能

```bash
# 浏览所有技能
sh skills browse

# 按分类筛选
sh skills browse --category=analytics

# 搜索技能
sh skills search "数据导出"
```

### 安装技能

```bash
# 安装技能
sh skills install data-export-plus

# 安装指定版本
sh skills install wechat-analytics@2.0.0

# 强制重装
sh skills install report-generator --force
```

### 管理技能

```bash
# 查看已安装
sh skills list

# 启用/禁用技能
sh skills enable data-export-plus
sh skills disable data-export-plus

# 卸载技能
sh skills uninstall data-export-plus

# 更新技能
sh skills update --all
```

### 官方技能列表

| 技能名称 | 说明 | 分类 |
|----------|------|------|
| data-export-plus | 高级数据导出（Parquet, Feather） | 数据处理 |
| wechat-analytics | 微信数据深度分析 | 数据分析 |
| campaign-optimizer | AI 营销活动优化 | 营销工具 |
| customer-rfm | RFM 客户价值分析 | 数据分析 |
| sms-batch-sender | 短信批量发送 | 营销工具 |
| data-sync-tool | CRM/ERP 数据同步 | 系统集成 |
| report-generator | 自动化报表生成 | 实用工具 |
| loyalty-calculator | 会员积分计算器 | 实用工具 |

### Web Skills Store

访问在线技能商店：https://huangchunbo2025.github.io/Socialhub-CLI/

---

## 配置管理

### 配置文件位置

- Windows: `C:\Users\<用户名>\.socialhub\config.json`
- macOS/Linux: `~/.socialhub/config.json`

### 配置项说明

```json
{
  "mode": "local",           // 运行模式: api | local
  "api": {
    "url": "https://api.socialhub.ai",
    "key": "",               // API 密钥
    "timeout": 30
  },
  "local": {
    "data_dir": "./data"     // 本地数据目录
  },
  "ai": {
    "provider": "azure",     // AI 提供商: azure | openai
    "azure_endpoint": "",    // Azure OpenAI 端点
    "azure_api_key": "",     // Azure API 密钥
    "azure_deployment": "gpt-4o",
    "openai_api_key": "",    // OpenAI 密钥
    "openai_model": "gpt-3.5-turbo"
  },
  "default_format": "table", // 默认输出格式
  "page_size": 50            // 默认分页大小
}
```

### 常用配置命令

```bash
# 查看所有配置
sh config show

# 设置配置项
sh config set mode local
sh config set api.key YOUR_API_KEY
sh config set local.data_dir ./data

# 获取配置项
sh config get mode
```

---

## 常见问题

### Q: 提示 "python not found"

**A:** 确保 Python 已安装并添加到 PATH。Windows 用户可以使用完整路径：

```powershell
& "C:\Users\<用户名>\AppData\Local\Python\bin\python.exe" -m socialhub.cli.main --help
```

### Q: 提示 "matplotlib not installed"

**A:** 安装 matplotlib：

```bash
pip install matplotlib
```

### Q: AI 功能报错 "getaddrinfo failed"

**A:** 检查 Azure OpenAI 端点配置是否正确：

```bash
sh config set ai.azure_endpoint https://your-resource.openai.azure.com
```

### Q: 本地模式找不到数据文件

**A:** 确保数据文件在正确的目录：

```bash
# 查看当前数据目录
sh config get local.data_dir

# 设置数据目录
sh config set local.data_dir C:\path\to\data
```

### Q: 如何切换 API 模式

**A:**

```bash
# 切换到 API 模式
sh config set mode api
sh config set api.url https://api.socialhub.ai
sh config set api.key YOUR_API_KEY
```

---

## 技术支持

- **GitHub Issues**: https://github.com/huangchunbo2025/Socialhub-CLI/issues
- **文档中心**: https://docs.socialhub.ai
- **Skills Store**: https://huangchunbo2025.github.io/Socialhub-CLI/

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Stop Adding AI, We Are AI.
</p>

<p align="center">
  © 2024 SocialHub.AI. All rights reserved.
</p>
