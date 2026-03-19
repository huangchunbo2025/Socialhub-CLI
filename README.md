# SocialHub.AI CLI

<p align="center">
  <img src="docs/logo.png" alt="SocialHub.AI" width="100">
</p>

<p align="center">
  <strong>客户互动平台命令行工具</strong><br>
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

- **智能交互** - 支持自然语言输入，AI 自动解析命令
- **数据分析** - 概览、客户分析、订单分析、留存分析
- **客户管理** - 查询、搜索、画像、分群、标签
- **营销工具** - 活动管理、优惠券、积分、消息
- **可视化** - 图表生成（柱状图、饼图、折线图、仪表板）
- **报告生成** - HTML 分析报告，可打印为 PDF
- **技能扩展** - Skills Store 官方认证插件

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

### PowerShell 配置（Windows）

```powershell
# 添加别名到 PowerShell 配置
if (!(Test-Path -Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force }
Add-Content -Path $PROFILE -Value 'function sh { & "python" -m socialhub.cli.main $args }'
. $PROFILE
```

## 使用示例

### 自然语言交互

```bash
sh 查看所有VIP会员
sh 分析最近30天的销售数据
sh 生成客户分布饼图
sh 导出高价值客户
```

### 数据分析

```bash
sh analytics overview --period=30d
sh analytics customers --period=30d
sh analytics retention --days=7,14,30
```

### 图表生成

```bash
sh analytics chart bar --data=customers --group=customer_type --output=bar.png
sh analytics chart pie --data=customers --group=customer_type --output=pie.png
sh analytics chart dashboard --output=dashboard.png
```

### 报告生成

```bash
sh analytics report --output=report.html --title="月度分析报告"
```

### 客户管理

```bash
sh customers list --type=member
sh customers get C001
sh customers search --phone=138
sh customers export --output=customers.csv
```

### Skills Store

```bash
sh skills browse
sh skills install wechat-analytics
sh skills list
```

## 配置

```bash
# 初始化配置
sh config init

# 设置本地模式
sh config set mode local
sh config set local.data_dir ./data

# 配置 AI (Azure OpenAI)
sh config set ai.azure_endpoint https://your-resource.openai.azure.com
sh config set ai.azure_api_key YOUR_API_KEY
```

## 文档

- [完整产品文档](docs/README.md) - 详细命令参考和使用指南
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

## License

MIT License

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Stop Adding AI, We Are AI.
</p>
