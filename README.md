# SocialHub.AI CLI

命令行工具，用于数据分析师和营销经理进行数据查询、报表生成、营销活动管理等操作。

## 安装

```bash
# 从源码安装
pip install -e .

# 或直接安装依赖
pip install typer[all] rich httpx pandas pydantic python-dotenv openpyxl
```

## 快速开始

```bash
# 查看帮助
sh --help

# 初始化配置
sh config init

# 设置API模式
sh config set api.url https://api.socialhub.ai
sh config set api.key YOUR_API_KEY

# 或使用本地模式（测试用）
sh config set mode local
sh config set local.data_dir ./data
```

## 命令列表

### 数据分析 (analytics)

```bash
# 概览分析
sh analytics overview --period=7d
sh analytics overview --from=2024-01-01 --to=2024-03-01

# 客户分析
sh analytics customers --period=30d
sh analytics retention --days=7,14,30

# 订单分析
sh analytics orders --period=30d
sh analytics orders --by=channel
sh analytics orders --by=province

# 活动分析
sh analytics campaigns --id=CAMP001 --funnel
```

### 客户管理 (customers)

```bash
# 搜索客户
sh customers search --phone=138xxx
sh customers search --email=xxx@example.com

# 查看客户详情
sh customers get C001
sh customers portrait C001

# 客户列表
sh customers list --type=member --limit=50

# 导出客户
sh customers export --type=member --output=members.csv
```

### 分群管理 (segments)

```bash
# 分群列表
sh segments list --status=enabled

# 查看分群
sh segments get SEG001
sh segments preview SEG001

# 创建分群
sh segments create --name="高价值客户" --rules='{"behavior":"high_value"}'
sh segments create-from-file --file=customers.csv --name="导入分群"

# 导出分群
sh segments export SEG001 --output=segment.csv
```

### 标签管理 (tags)

```bash
# 标签列表
sh tags list --type=rfm
sh tags get TAG001
sh tags analysis TAG001

# 创建标签
sh tags create --name="VIP客户" --type=static --values="金卡,银卡,铜卡"
```

### 营销活动 (campaigns)

```bash
# 活动列表
sh campaigns list --status=running

# 查看活动
sh campaigns get CAMP001
sh campaigns analysis CAMP001 --funnel

# 创建活动
sh campaigns create --name="新年促销" --type=single

# 营销日历
sh campaigns calendar --month=2024-03
```

### 优惠券 (coupons)

```bash
# 优惠券规则
sh coupons rules list
sh coupons rules get RULE001

# 优惠券查询
sh coupons list --status=unused
sh coupons analysis RULE001
```

### 积分 (points)

```bash
# 积分规则
sh points rules list
sh points rules get RULE001

# 会员积分
sh points balance M001
sh points history M001 --limit=50
```

### 消息 (messages)

```bash
# 消息模板
sh messages templates list --channel=sms
sh messages templates get TPL001

# 发送记录
sh messages records --status=success
sh messages stats --period=7d
```

### 配置 (config)

```bash
# 初始化
sh config init

# 查看配置
sh config show

# 设置配置
sh config set api.url https://api.socialhub.ai
sh config set mode local

# 获取配置
sh config get api.url
```

## 输出格式

```bash
# 默认表格输出
sh analytics overview

# JSON输出
sh analytics overview --format=json

# 导出到文件
sh analytics overview --output=report.csv
sh customers export --output=customers.xlsx
```

## 配置文件

配置文件位于 `~/.socialhub/config.json`

```json
{
  "mode": "api",
  "api": {
    "url": "https://api.socialhub.ai",
    "key": "your-api-key",
    "timeout": 30
  },
  "local": {
    "data_dir": "./data"
  },
  "default_format": "table",
  "page_size": 50
}
```

## 环境变量

也可以通过环境变量配置：

```bash
export SOCIALHUB_API_URL=https://api.socialhub.ai
export SOCIALHUB_API_KEY=your-api-key
export SOCIALHUB_MODE=api
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式化
black socialhub
ruff check socialhub
```

## License

MIT
