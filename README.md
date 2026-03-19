# SocialHub.AI CLI

<p align="center">
  <img src="docs/logo.png" alt="SocialHub.AI" width="100">
</p>

<p align="center">
  <strong>Customer Intelligence Platform CLI</strong><br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#快速安装">快速安装</a> •
  <a href="#使用示例">使用示例</a> •
  <a href="docs/README.md">完整文档</a>
</p>

---

## 功能特性

- **智能交互** - 支持自然语言输入，AI 自动解析并执行命令
- **MCP 数据库** - 直连 StarRocks 分析数据库，实时查询
- **数据分析** - 概览、客户分析、订单分析、留存分析、渠道分析
- **客户管理** - 查询、搜索、画像、分群、标签
- **营销工具** - 活动管理、优惠券、积分、消息
- **可视化** - 图表生成（柱状图、饼图、折线图、仪表板）
- **报告生成** - HTML 分析报告，可打印为 PDF
- **定时任务** - Heartbeat 调度器，自动执行定期任务
- **技能扩展** - Skills Store 官方认证插件
- **AI 洞察** - 多步骤执行后自动生成数据洞察

## 快速安装

```bash
# 克隆仓库
git clone https://github.com/huangchunbo2025/Socialhub-CLI.git
cd Socialhub-CLI

# 安装
pip install -e .

# 安装图表支持（可选）
pip install matplotlib
```

安装后运行 `socialhub` 查看欢迎画面：

```
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \  |_ _|
 \___ \ / _ \ / __| |/ _` | | |_| | | | | '_ \  / _ \  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \ | |
 |____/ \___/ \___|_|\__,_|_|_| |_|\__,_|_.__//_/   \_\___|

                v0.1.0 | Customer Intelligence Platform
```

## 使用示例

### 自然语言交互（智能模式）

```bash
socialhub 分析最近30天的销售趋势
socialhub 查看各渠道订单分布
socialhub 帮我设置每天8点生成销售报告的定时任务
socialhub 目前客户表里有哪些字段
```

### MCP 数据库查询

```bash
socialhub mcp tables                    # 查看所有表
socialhub mcp schema dwd_v_order        # 查看表结构
socialhub mcp sql                       # 交互式 SQL
socialhub mcp query "SELECT COUNT(*) FROM dwd_v_order"
```

### 数据分析

```bash
socialhub analytics overview --period=30d
socialhub analytics orders --period=30d
socialhub analytics orders --by=channel     # 按渠道分析
socialhub analytics orders --by=province    # 按店铺分析
socialhub analytics customers --period=30d
socialhub analytics retention --days=7,14,30
```

### 图表生成

```bash
socialhub analytics chart bar --data=customers --group=customer_type
socialhub analytics chart pie --data=customers --group=customer_type
socialhub analytics chart dashboard --output=Doc/dashboard.png
```

### 报告生成

```bash
socialhub analytics report --title="月度分析报告"
# 报告默认保存到 Doc/ 文件夹
```

### 定时任务（Heartbeat）

```bash
socialhub heartbeat list                # 查看所有定时任务
socialhub heartbeat check               # 检查并执行到期任务
socialhub heartbeat check --force       # 强制执行所有待处理任务
socialhub heartbeat run daily-overview  # 手动执行指定任务
socialhub heartbeat setup               # Windows 任务计划设置说明
```

### 客户管理

```bash
socialhub customers list --type=member
socialhub customers get C001
socialhub customers search --phone=138
socialhub customers export --output=Doc/customers.csv
```

### AI 助手

```bash
socialhub ai chat "分析订单趋势" --auto  # 自动执行多步骤计划
```

### Skills Store

```bash
socialhub skills browse
socialhub skills install wechat-analytics
socialhub skills list
```

## 配置

```bash
# 初始化配置
socialhub config init

# 查看当前配置
socialhub config show

# 设置 MCP 模式（默认）
socialhub config set mode mcp

# 设置本地模式
socialhub config set mode local
socialhub config set local.data_dir ./data

# 配置 AI (Azure OpenAI)
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
```

## 项目结构

```
socialhub/
├── cli/
│   ├── main.py              # 入口 + 智能识别 + 欢迎画面
│   ├── config.py            # 配置管理
│   ├── commands/
│   │   ├── analytics.py     # 数据分析命令 (MCP)
│   │   ├── ai.py            # AI 助手 + 多步骤执行
│   │   ├── heartbeat.py     # 定时任务调度
│   │   ├── mcp.py           # MCP 数据库命令
│   │   └── ...
│   ├── api/
│   │   ├── client.py        # API 客户端
│   │   └── mcp_client.py    # MCP 客户端 (SSE)
│   └── output/
│       ├── table.py         # 表格输出
│       ├── chart.py         # 图表生成
│       ├── export.py        # 导出功能
│       └── report.py        # HTML 报告
├── Doc/                      # 生成的报告和图表
├── Memory.md                 # 项目记忆
├── Heartbeat.md              # 定时任务配置
└── docs/                     # 文档
```

## 文档

- [完整产品文档](docs/README.md) - 详细命令参考和使用指南
- [技术设计文档](docs/DESIGN.md) - 架构设计和实现细节
- [Skills Store](https://huangchunbo2025.github.io/Socialhub-CLI/) - 在线技能商店

## 技术栈

| 组件 | 技术 |
|------|------|
| CLI 框架 | Typer |
| 终端美化 | Rich |
| 数据处理 | Pandas |
| 图表生成 | Matplotlib |
| HTTP 客户端 | httpx |
| AI 助手 | Azure OpenAI |
| 数据库 | StarRocks (MCP) |

## License

MIT License

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>
