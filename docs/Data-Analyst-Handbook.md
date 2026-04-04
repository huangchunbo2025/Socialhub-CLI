# SocialHub.AI CLI 数据分析师业务指导手册

## 从数据查询到 AI 驱动洞察的完整实战指南

---

**文档版本：** v1.0
**适用对象：** 数据分析师、运营分析师、BI 工程师
**更新日期：** 2026 年 4 月
**前置要求：** 具备基本的命令行使用经验，了解电商核心指标体系

---

## 目录

1. [写在前面：这本手册能帮你做什么](#1-写在前面这本手册能帮你做什么)
2. [快速上手：10 分钟跑通第一个分析](#2-快速上手10-分钟跑通第一个分析)
3. [核心概念：理解 CLI 的工作方式](#3-核心概念理解-cli-的工作方式)
4. [日常分析场景实战](#4-日常分析场景实战)
5. [深度分析：组合命令的艺术](#5-深度分析组合命令的艺术)
6. [自然语言模式：让 AI 替你想命令](#6-自然语言模式让-ai-替你想命令)
7. [多轮对话：像问同事一样问 AI](#7-多轮对话像问同事一样问-ai)
8. [定时任务：让分析自动跑起来](#8-定时任务让分析自动跑起来)
9. [Skills 插件：扩展你的分析能力](#9-skills-插件扩展你的分析能力)
10. [数据导出与报告生成](#10-数据导出与报告生成)
11. [MCP 数据库直连：写 SQL 的进阶玩法](#11-mcp-数据库直连写-sql-的进阶玩法)
12. [常见问题排查](#12-常见问题排查)
13. [分析场景速查手册](#13-分析场景速查手册)
14. [附录：指标定义与口径说明](#14-附录指标定义与口径说明)

---

## 1. 写在前面：这本手册能帮你做什么

### 你现在可能在经历这些

- 每天早上花 30-60 分钟从 BI 系统拉数据、整理 Excel、发日报
- 运营同学突然问"上周三各渠道的复购率是多少"，你要在 StarRocks 里写 SQL、等查询、复制结果
- 做活动复盘要同时打开 5 个报表，手动对数、做透视表
- 老板问"为什么这周 GMV 下降了"，你要翻好几个维度才能找到原因

### 用了这个工具之后

```bash
# 30 秒拿到日报核心数据
sh analytics overview --period=today --compare

# 直接回答运营的问题
sh analytics retention --days=7 --period=last_week

# 一键活动复盘
sh analytics campaigns --campaign-id=C2026031 --include-roi

# 让 AI 帮你找下降原因
sh "这周 GMV 比上周低了 15%，帮我分析原因，从渠道、商品、客群三个维度"
```

这本手册会告诉你：
- 如何高效使用 22 个分析命令
- 如何用自然语言让 AI 帮你写分析计划
- 如何设置定时任务，让日报自动生成
- 如何通过 Skills 插件扩展分析能力
- 如何直连数据库执行自定义 SQL

---

## 2. 快速上手：10 分钟跑通第一个分析

### 2.1 安装

```bash
# 安装 CLI
pip install socialhub-cli

# 验证安装
sh --version
# 输出：SocialHub CLI v2.x.x
```

### 2.2 配置

```bash
# 查看当前配置
sh config show

# 设置 MCP 连接（向你的数据工程师获取这两个地址）
sh config set mcp.sse_url "https://your-mcp-server/sse"
sh config set mcp.post_url "https://your-mcp-server/messages"
sh config set mcp.tenant_id "your-tenant-id"

# 登录（如果公司启用了 OAuth 认证）
sh auth login
# 按提示输入用户名和密码
```

### 2.3 跑通第一个查询

```bash
# 看看最近 7 天的整体情况
sh analytics overview --period=7d

# 期望输出示例：
# ┌─────────────────────────────────────────────────────────┐
# │  SocialHub Analytics Overview  │  Period: Last 7 Days  │
# ├─────────────────┬───────────────┬───────────────────────┤
# │  Metric         │  Value        │  vs Previous Period   │
# ├─────────────────┼───────────────┼───────────────────────┤
# │  GMV            │  ¥ 2,847,320  │  ▲ 12.3%             │
# │  Orders         │  18,432       │  ▲ 8.7%              │
# │  AOV            │  ¥ 154.5      │  ▲ 3.3%              │
# │  New Customers  │  3,219        │  ▼ 2.1%              │
# │  Active Buyers  │  12,847       │  ▲ 15.2%             │
# │  Coupon Rate    │  38.2%        │  ▲ 2.4pp             │
# └─────────────────┴───────────────┴───────────────────────┘
```

**恭喜，你已经成功运行了第一个分析！**

接下来我们系统地学习每一个分析场景。

---

## 3. 核心概念：理解 CLI 的工作方式

### 3.1 两种使用模式

CLI 支持两种模式，根据你的习惯和需求灵活选择：

**模式一：直接命令（Command Mode）**

```bash
sh analytics orders --period=30d --group=channel
```

适合：知道要看什么指标、需要精确控制参数、想要稳定可重复的查询。

**模式二：自然语言（Smart Mode）**

```bash
sh "分析最近 30 天各渠道订单趋势"
```

适合：探索性分析、不确定用哪个命令、需要多步组合分析。

**智能路由机制：**

CLI 会自动判断你输入的是命令还是自然语言：
- 如果以 `analytics`、`mcp`、`customers` 等关键词开头 → 直接命令模式
- 如果是描述性语言 → 自动进入 AI 解析模式

```bash
sh analytics overview    # → 直接命令
sh "看看概览"            # → AI 解析后执行相同命令
```

**Smart Mode 支持前置全局选项：**

自然语言查询前可以加 `--output-format` 等全局选项，CLI 会正确识别并应用：

```bash
sh --output-format json "分析留存"    # 正确工作，输出 JSON 格式
sh --output-format csv "各渠道订单"   # 同样支持
```

**重复/重放只做精确匹配：**

`again`、`retry`、`!!` 等重放触发词必须是完整查询才会触发重放。如果包含其他内容，则被当作新请求处理：

```bash
sh "again"                         # → 重放上一次查询
sh "!!"                            # → 重放上一次查询
sh "分析留存 again by channel"      # → 当作新请求处理，不会触发重放
```

### 3.2 通用参数说明

几乎所有分析命令都支持以下通用参数：

| 参数 | 含义 | 可选值 | 默认值 |
|------|------|--------|--------|
| `--period` | 时间范围 | `today` `7d` `30d` `90d` `365d` `ytd` `last_week` `last_month` | `30d` |
| `--compare` | 是否对比上期 | `flag`（加上即开启） | 关闭 |
| `--output-format` | 输出格式 | `text` `json` `csv` | `text` |
| `--export` | 导出文件路径 | 文件路径 | 不导出 |

**时间范围说明：**

| 值 | 含义 | 示例 |
|----|------|------|
| `today` | 今日截至当前时间 | 查看今天实时数据 |
| `7d` | 过去 7 天（含今天） | 周度分析 |
| `30d` | 过去 30 天 | 月度分析 |
| `90d` | 过去 90 天 | 季度分析 |
| `365d` | 过去 365 天 | 年度分析 |
| `ytd` | 年初至今 | YTD 累计 |
| `last_week` | 上周完整 7 天（周一到周日） | 周报对比 |
| `last_month` | 上月完整自然月 | 月报对比 |

### 3.3 输出格式选择

```bash
# 默认：终端友好的 Rich 表格
sh analytics overview

# JSON 格式：适合程序处理或存档
sh analytics overview --output-format=json

# 将 JSON 输出保存到文件
sh analytics overview --output-format=json --export=./data/overview_20260402.json
```

### 3.4 查看命令帮助

每个命令都有详细帮助文档：

```bash
sh analytics --help           # 查看所有分析子命令
sh analytics orders --help    # 查看订单分析的所有参数
sh customers --help           # 查看客户管理命令
```

---

## 4. 日常分析场景实战

### 4.1 整体经营概览（analytics overview）

**适用场景：** 日报、周报、月报核心数据，快速了解业务大盘。

```bash
# 基础用法：看 30 天概览
sh analytics overview

# 今日实时数据
sh analytics overview --period=today

# 带环比对比
sh analytics overview --period=7d --compare

# 年初至今（YTD）
sh analytics overview --period=ytd --compare
```

**输出包含的指标：**
- GMV（总交易额）及环比
- 订单量及环比
- 客单价（AOV）及环比
- 新增客户数及环比
- 活跃买家数及环比
- 积分挣取/核销量
- 优惠券核销率

**分析师常见用法：**

```bash
# 大促日当天实时监控
sh analytics overview --period=today

# 大促后复盘（对比大促前 30 天）
sh analytics overview --period=30d --compare

# 月度管理报告
sh analytics overview --period=last_month --compare --export=./report/monthly_overview.json
```

---

### 4.2 订单与销售分析（analytics orders）

**适用场景：** 渠道对比、省份分布、商品销售、退货分析。

```bash
# 基础用法
sh analytics orders

# 按渠道分组（微信、抖音、天猫、自营 App 等）
sh analytics orders --period=30d --group=channel

# 按省份分组（地区分布分析）
sh analytics orders --period=30d --group=province

# 按商品分组（商品销售排行）
sh analytics orders --period=30d --group=product

# 包含退货分析
sh analytics orders --period=30d --include-returns

# 完整分析（渠道 + 退货 + 对比）
sh analytics orders --period=30d --group=channel --include-returns --compare
```

**典型分析输出（渠道维度）：**

```
┌──────────────┬───────────┬──────────┬──────────┬──────────────┐
│  Channel     │  GMV      │  Orders  │  AOV     │  vs. Prev    │
├──────────────┼───────────┼──────────┼──────────┼──────────────┤
│  微信小程序   │  ¥1.2M    │  8,234   │  ¥145.7  │  ▲ 18.3%    │
│  抖音直播     │  ¥0.8M    │  5,102   │  ¥156.8  │  ▲ 34.2%    │
│  天猫旗舰店   │  ¥0.6M    │  3,847   │  ¥155.9  │  ▼ 3.1%     │
│  自营 APP    │  ¥0.2M    │  1,249   │  ¥160.1  │  ▲ 5.6%     │
└──────────────┴───────────┴──────────┴──────────┴──────────────┘
```

**实战技巧：** 当 GMV 环比下降时，先用 `--group=channel` 找到下降最多的渠道，再缩小时间范围（`--period=7d`）看近期趋势，快速定位问题。

---

### 4.3 客户留存分析（analytics retention）

**适用场景：** 复购率监测、客户健康度评估、留存周期分析。

```bash
# 标准留存分析（7天、30天、90天留存率）
sh analytics retention

# 指定留存周期
sh analytics retention --days=30

# 多周期同时分析
sh analytics retention --days=7,30,90

# 带同期对比
sh analytics retention --days=30 --comparison-period=90d

# 按时间范围分析
sh analytics retention --period=last_month --days=30,90
```

**输出示例：**

```
Customer Retention Analysis  │  Period: Last 30 Days

  30-Day Retention Rate:   43.2%  ▲ 2.8pp vs. Previous Period
  90-Day Retention Rate:   28.7%  ▼ 1.2pp vs. Previous Period
  180-Day Retention Rate:  18.4%  ▲ 0.5pp vs. Previous Period

  Cohort Analysis (30-day):
  ┌───────────────┬──────────┬──────────┬──────────┬──────────┐
  │  Cohort Month │  Size    │  Month 1 │  Month 2 │  Month 3 │
  ├───────────────┼──────────┼──────────┼──────────┼──────────┤
  │  2026-01      │  3,241   │  45.2%   │  31.8%   │  22.4%   │
  │  2026-02      │  2,987   │  43.7%   │  29.6%   │  —       │
  │  2026-03      │  3,102   │  42.1%   │  —       │  —       │
  └───────────────┴──────────┴──────────┴──────────┴──────────┘
```

**留存率健康阈值参考（电商行业）：**

| 周期 | 优秀 | 良好 | 需关注 | 需干预 |
|------|------|------|-------|-------|
| 30 天 | > 45% | 35-45% | 25-35% | < 25% |
| 90 天 | > 30% | 20-30% | 12-20% | < 12% |
| 180 天 | > 20% | 12-20% | 8-12% | < 8% |

---

### 4.4 RFM 客户分层（analytics rfm）

**适用场景：** 客群精细化运营，识别 VIP、沉睡客户、流失预警。

```bash
# 查看全量 RFM 分层分布
sh analytics rfm

# 只看高风险流失客群（at-risk）
sh analytics rfm --segment-filter=at-risk

# 看 VIP 客群，取前 200 名
sh analytics rfm --segment-filter=vip --top-limit=200

# 导出 at-risk 客群名单（供运营发召回活动）
sh analytics rfm --segment-filter=at-risk --top-limit=500 --export=./data/at_risk_customers.csv
```

**RFM 分层定义：**

| 分层标签 | Recency（近度） | Frequency（频次） | Monetary（金额） | 运营策略 |
|---------|--------------|----------------|----------------|---------|
| `vip` | 近期购买 | 高频购买 | 高消费 | 专属服务、优先体验 |
| `loyal` | 近期购买 | 中高频 | 中高消费 | 会员升级、积分激励 |
| `potential` | 近期购买 | 低频 | 低消费 | 引导复购、品类推荐 |
| `new` | 首次购买 | 1次 | 不限 | 新客培育、复购激励 |
| `at-risk` | 较长未购买 | 历史高频 | 历史高消费 | 流失预警、召回活动 |
| `sleeping` | 长期未购买 | 历史低频 | 历史低消费 | 低成本激活或放弃 |
| `lost` | 超长未购买 | — | — | 放弃或低价激活 |

**实战案例：大促前客群准备**

```bash
# 步骤 1：了解各分层规模
sh analytics rfm

# 步骤 2：导出高价值且近期未活跃的客群（at-risk），准备召回
sh analytics rfm --segment-filter=at-risk --top-limit=1000 \
  --export=./campaign/pre_promo_atrisk.csv

# 步骤 3：导出 VIP 客群，准备专属优先权益
sh analytics rfm --segment-filter=vip \
  --export=./campaign/pre_promo_vip.csv
```

---

### 4.5 营销活动分析（analytics campaigns）

**适用场景：** 活动效果评估、ROI 计算、活动归因分析。

```bash
# 查看最近 30 天所有活动概览
sh analytics campaigns

# 查看特定活动详情
sh analytics campaigns --campaign-id=C2026031

# 按活动名称模糊搜索
sh analytics campaigns --name-filter="双十一"

# 包含 ROI 分析
sh analytics campaigns --period=30d --include-roi

# 指定 GMV 归因窗口（默认 7 天）
sh analytics campaigns --campaign-id=C2026031 --attribution-window-days=14
```

**输出包含：**
- 触达人数 / 触达率
- 点击人数 / 点击率（CTR）
- 购买人数 / 转化率（CVR）
- 活动 GMV（归因窗口内）
- 奖励发放总量（积分/优惠券）
- ROI（活动 GMV ÷ 活动成本）

**活动 ROI 计算口径说明：**

```
ROI = 活动窗口期内参与用户的新增 GMV ÷ 活动总成本
活动总成本 = 优惠券面值 × 核销数量 + 积分兑换价值 + 活动运营人力成本（可选）
归因窗口：默认最后一次点击后 7 天内的购买行为算作活动贡献
```

---

### 4.6 异常检测（analytics anomaly）

**适用场景：** 数据异常快速定位，大促监控，日常巡检。

```bash
# 检测所有核心指标异常
sh analytics anomaly

# 只检测 GMV 异常
sh analytics anomaly --metric=gmv

# 调整灵敏度（1=低灵敏，3=高灵敏，默认 2）
sh analytics anomaly --metric=orders --sensitivity=3

# 短期异常检测（近 7 天）
sh analytics anomaly --period=7d --metric=gmv
```

**检测原理（3σ 法则）：**

系统以过去 90 天历史数据为基线，计算均值（μ）和标准差（σ）：
- 数值在 μ ± σ 内：正常
- 数值在 μ ± 2σ 内：轻微异常（黄色预警）
- 数值超过 μ ± 3σ：严重异常（红色告警）

```
示例输出：

⚠️  ANOMALY DETECTED

  Metric: GMV
  Date:   2026-04-01
  Value:  ¥ 189,432  (↓ 42% vs. baseline)
  Z-Score: -3.7σ  ← 超过 3σ，触发告警

  Possible Causes:
  ✗ Payment gateway timeout reported at 14:32
  ✗ Inventory shortage on top 3 products
```

**建议设置定时巡检（每日自动运行）：**

```bash
# 在 heartbeat 中添加每日异常检测
sh heartbeat add --name=daily-anomaly \
  --cron="0 8 * * *" \
  --command="sh analytics anomaly --sensitivity=2" \
  --notify-on-error
```

---

### 4.7 客户生命周期分析（analytics funnel）

**适用场景：** 找到客户流失的关键节点，优化运营策略。

```bash
# 查看完整生命周期漏斗
sh analytics funnel

# 指定时间范围
sh analytics funnel --period=90d
```

**漏斗阶段定义：**

```
New（新注册）
    ↓ 首购转化率（目标: > 30%）
First Purchase（首购）
    ↓ 复购转化率（目标: > 45%）
Repeat（复购用户）
    ↓ 忠诚培育率（目标: > 60%）
Loyal（忠诚用户）
    ↓ 流失风险率（监控: < 15%）
At-Risk（流失风险）
    ↓ 流失率（监控: < 10%）
Churned（已流失）
```

**如何利用漏斗数据：**

```bash
# 发现首购转化率低 → 找新客运营问题
sh analytics funnel  # 找到问题节点

# 深入分析新客来源
sh analytics customers --period=30d --include-source

# 再配合活动分析找原因
sh analytics campaigns --name-filter="新客" --include-roi
```

---

### 4.8 客户 LTV 分析（analytics ltv）

**适用场景：** 获客渠道 ROI 评估、用户价值预测、预算分配。

```bash
# 标准 LTV 队列分析（12 个月，跟踪 6 个月）
sh analytics ltv

# 自定义队列窗口
sh analytics ltv --cohort-months=6 --follow-months=12

# 最近 24 个月新客，跟踪 3 个月 LTV
sh analytics ltv --cohort-months=24 --follow-months=3
```

**输出解读：**

```
Customer LTV Analysis  │  Cohort Period: 12 months  │  Follow Period: 6 months

┌────────────────┬─────────┬──────────────────────────────────────┐
│  Cohort        │  Size   │  Cumulative GMV per Customer (months) │
│                │         │  M1      M2      M3      M4      M6   │
├────────────────┼─────────┼──────────────────────────────────────┤
│  2025-04       │  4,231  │  ¥180   ¥264   ¥331   ¥389   ¥482   │
│  2025-05       │  3,987  │  ¥175   ¥258   ¥318   ¥372   ¥461   │
│  2025-10（双十一）│  8,102│  ¥210   ¥272   ¥315   ¥348   ¥401   │  ← 大促获客 LTV 更低
│  2025-11       │  3,641  │  ¥182   ¥270   ¥338   ¥397   ¥495   │
└────────────────┴─────────┴──────────────────────────────────────┘

洞察：双十一获客的 6 个月 LTV（¥401）低于日常获客（平均 ¥470）
建议：评估大促获客成本，优化大促后的客户培育策略
```

---

## 5. 深度分析：组合命令的艺术

单个命令能回答"是什么"，组合命令才能回答"为什么"。以下是几个高频深度分析场景。

### 5.1 场景：大促复盘完整分析

**目标：** 全面评估一次大促活动的效果，包括 GMV、新客、留存、ROI。

```bash
# 步骤 1：整体 GMV 表现
sh analytics overview --period=7d --compare

# 步骤 2：渠道销售分布
sh analytics orders --period=7d --group=channel --compare

# 步骤 3：活动带来的新客质量（近 30 天留存）
sh analytics retention --period=last_month --days=30

# 步骤 4：活动本身的 ROI
sh analytics campaigns --name-filter="大促" --include-roi --attribution-window-days=14

# 步骤 5：大促客群 RFM 分析（识别大促客群的质量）
sh analytics rfm --period=last_month

# 步骤 6：异常检测（确认数据无问题）
sh analytics anomaly --period=7d
```

**或者直接用 AI 帮你规划：**

```bash
sh "帮我做一份上周大促的完整复盘分析，包括 GMV、渠道、新客质量、活动 ROI，输出多步计划"
```

AI 会自动生成并执行完整的多步分析计划。

---

### 5.2 场景：GMV 下降根因分析

**目标：** 快速定位 GMV 下降的原因，给出可操作的建议。

```bash
# 第一步：确认下降幅度
sh analytics overview --period=7d --compare

# 第二步：渠道维度拆解（哪个渠道降了？）
sh analytics orders --period=7d --group=channel --compare

# 假设发现微信渠道下降最多：

# 第三步：查看微信渠道客群留存（是老客流失？）
sh analytics retention --period=7d --days=30

# 第四步：看商品维度（是特定商品断货/下架？）
sh analytics orders --period=7d --group=product

# 第五步：看异常（是否有支付失败、系统故障？）
sh analytics anomaly --period=7d --metric=orders --sensitivity=3

# 第六步：看营销活动（是否上周没有活动拉动？）
sh analytics campaigns --period=14d --compare
```

**模板化根因分析（用 AI 一步搞定）：**

```bash
sh "本周 GMV 比上周下降 18%，帮我从渠道、商品、客群、营销活动四个维度分析根因"
```

---

### 5.3 场景：新品上线效果追踪

**目标：** 追踪新品上线后的销售数据、客群特征、带动效果。

```bash
# 新品销售占比（商品维度）
sh analytics orders --period=30d --group=product

# 购买新品的客群特征（通过 SQL 直连做定制分析）
sh mcp sql
# 在交互式 SQL 中执行：
# SELECT rfm_segment, COUNT(*), AVG(order_value)
# FROM customer_orders
# WHERE product_id = 'NEW_PRODUCT_001'
# AND order_date >= CURRENT_DATE - 30
# GROUP BY rfm_segment

# 新品购买客群的留存质量
sh analytics retention --period=30d

# 关联活动（是否有新品推介活动）
sh analytics campaigns --name-filter="新品"
```

---

### 5.4 场景：会员体系健康度评估

**目标：** 评估会员分层健康度、积分负债、升降级趋势。

```bash
# 会员等级分布
sh analytics loyalty

# 积分计划健康度（挣取/核销/过期比例）
sh analytics points --period=30d --include-breakdown

# 即将过期积分预警（可触发召回活动）
sh analytics points --expiring-within-days=30 --at-risk-limit=100

# 高价值会员流失风险（VIP at-risk）
sh analytics rfm --segment-filter=at-risk

# 完整复购分析
sh analytics repurchase --period=90d
```

---

## 6. 自然语言模式：让 AI 替你想命令

### 6.1 什么时候用自然语言模式

| 场景 | 推荐模式 |
|------|---------|
| 知道要看哪个指标、哪个维度 | 直接命令 |
| 探索性分析，不确定从哪里入手 | 自然语言 |
| 需要多步骤组合分析 | 自然语言（AI 生成计划） |
| 要回答一个开放性问题 | 自然语言 |
| 重复性固定报表 | 直接命令 + heartbeat |

### 6.2 有效的提问技巧

**技巧一：说清楚分析目的，而不只是要什么数据**

```bash
# 效果一般（只说要什么）
sh "给我渠道数据"

# 效果更好（说明目的）
sh "我想了解哪个渠道的客户质量最好，从复购率、客单价、LTV 角度分析"
```

**技巧二：给出时间范围和对比维度**

```bash
# 模糊
sh "分析留存"

# 具体
sh "分析最近 30 天的 30 日留存率，跟上个月同期对比，看是否有改善"
```

**技巧三：指定输出形式**

```bash
# 让 AI 输出多步执行计划
sh "帮我规划一个完整的月度经营分析，输出步骤计划"

# 让 AI 直接回答（单步）
sh "今天的 GMV 大概是多少"
```

**技巧四：在查询中带上业务背景**

```bash
# 带背景
sh "我们上个月做了一个针对沉睡客户的召回活动，想评估效果，
   活动期间是 3 月 15-25 日，活动 ID 是 C2026031"

# AI 会据此调用正确的时间范围和 campaign_id
```

### 6.3 AI 多步计划的工作方式

当 AI 判断需要多个步骤时，会生成执行计划并请求确认：

```
AI Analysis Plan:
  Query: "分析最近 30 天各渠道销售趋势和客户留存"

  Proposed Plan:
  ┌─────────────────────────────────────────────────────────┐
  │ Step 1: 获取整体经营概览                                  │
  │         sh analytics overview --period=30d --compare    │
  ├─────────────────────────────────────────────────────────┤
  │ Step 2: 分析渠道销售趋势                                  │
  │         sh analytics orders --period=30d --group=channel │
  ├─────────────────────────────────────────────────────────┤
  │ Step 3: 计算 30 天客户留存率                              │
  │         sh analytics retention --period=30d --days=30   │
  └─────────────────────────────────────────────────────────┘

  Proceed? [y/N]: y
```

输入 `y` 确认后，系统自动逐步执行，完成后生成 AI 洞察摘要。

### 6.4 常用自然语言提示词模板

**日报场景：**
```bash
sh "给我今天的业务日报，包括 GMV、订单量、新客数，并和昨天对比"
```

**周报场景：**
```bash
sh "生成上周的周报，需要包含整体数据、渠道对比、活动效果，以及和前周的环比"
```

**问题诊断：**
```bash
sh "今天的转化率比昨天低了 30%，帮我从订单、渠道、活动三个维度找原因"
```

**客群洞察：**
```bash
sh "找出我们高价值但近期没有购买的客户，给出他们的特征画像和建议的召回策略"
```

**趋势预判：**
```bash
sh "分析过去 90 天的复购率趋势，判断是否在改善，并找出改善最明显的渠道"
```

---

## 7. 多轮对话：像问同事一样问 AI

### 7.1 开启一个会话

多轮对话让你可以像和同事讨论一样，在一个上下文中连续追问。

```bash
# 开始第一轮（系统自动创建 session）
sh "分析最近 30 天的整体业务情况"

# 输出结果后，查看 session ID
# Session ID: sess_20260402_abc123

# 继续这个会话追问
sh -c sess_20260402_abc123 "微信渠道的情况怎么样？"
sh -c sess_20260402_abc123 "微信渠道里哪些商品卖得最好？"
sh -c sess_20260402_abc123 "这些商品的复购率是什么水平？"
```

**每次追问时，AI 都记得上文说的是"微信渠道"**，不需要每次重复背景。

### 7.2 管理你的会话

```bash
# 列出所有活跃会话
sh session list

# 输出示例：
# ┌─────────────────────────┬────────────────────────────────────┬──────────────┐
# │  Session ID             │  Last Query                        │  Created     │
# ├─────────────────────────┼────────────────────────────────────┼──────────────┤
# │  sess_20260402_abc123   │  "微信渠道里哪些商品卖得最好？"      │  2h ago      │
# │  sess_20260401_def456   │  "分析上周的大促复盘"               │  1d ago      │
# └─────────────────────────┴────────────────────────────────────┴──────────────┘

# 恢复一个会话
sh session resume sess_20260401_def456

# 删除会话（会话默认 24h 后自动过期）
sh session delete sess_20260401_def456
```

### 7.3 记忆系统增强

**单轮查询也能积累记忆：**

即使不使用 `--session` 显式开启会话，CLI 也会创建临时会话来提取洞察和摘要。你不需要刻意开启会话就能获得个性化上下文——系统会自动记住之前分析中的关键发现。

**记忆系统识别业务上下文：**

如果你通过 `sh memory set` 配置了行业、旺季、KPI 基准等业务上下文信息，这些现在会被注入 AI 上下文中，让分析建议更贴合你的业务实际：

```bash
# 设置业务上下文（这些信息会被 AI 在分析时参考）
sh memory set business.industry "美妆护肤"
sh memory set business.peak_season "双十一、618、38节"
sh memory set business.kpi_benchmark.retention_30d "40%"
sh memory set business.kpi_benchmark.aov "¥180"
```

> **说明：** 之前只有分析偏好（如默认时间范围、输出格式）会被注入 AI 上下文，现在行业、旺季、KPI 基准等业务上下文也会被一并注入。

### 7.4 多轮对话的最佳实践

**适合多轮对话的场景：**
- 探索性分析（不确定结论，需要逐步深入）
- 问题排查（每一步结论决定下一步看什么）
- 报告撰写（边分析边整理叙述逻辑）

**每轮问题建议：**
1. **第一轮：宽**——先看大盘，了解整体
2. **第二轮：缩**——聚焦到异常维度
3. **第三轮：深**——在异常维度里找根因
4. **第四轮：建议**——让 AI 给出运营建议

**示例完整会话：**

```bash
轮次 1：sh "分析最近 7 天的整体业务"
         → 发现 GMV 下降 12%，但订单量正常，说明客单价下降

轮次 2：sh -c <session> "为什么客单价会下降？从渠道和商品角度看"
         → 发现抖音渠道客单价从 ¥180 降到 ¥142

轮次 3：sh -c <session> "抖音渠道近 7 天的商品销售结构有变化吗？"
         → 发现低客单价商品比例从 30% 升到 55%

轮次 4：sh -c <session> "这个变化和活动有关系吗？上周抖音有没有做低价引流活动？"
         → 关联到一个"9.9 元拼手气"活动，定位根因

轮次 5：sh -c <session> "给我总结一下这次分析，并给出针对性建议"
         → AI 生成完整分析摘要和运营建议
```

---

## 8. 定时任务：让分析自动跑起来

### 8.1 Heartbeat 调度器简介

`heartbeat` 是 CLI 内置的定时任务调度器，支持 cron 表达式，可以将任何分析命令设置为定时自动执行。

**典型用途：**
- 每天早 9 点自动生成日报
- 每周一自动生成周报
- 每小时监控大促期间的实时数据
- 每日自动检测数据异常

**重要行为变更：**

- **周期任务现在真正重复执行：** Daily 和 Weekly 任务执行完成后会自动重置为 pending 状态，下次到点会再次执行。之前的行为是执行一次后就不再调度。
- **手动执行加锁保护：** `sh heartbeat run <id>` 现在会加锁，防止和定时检查（`sh heartbeat check`）并发执行同一任务，避免重复运行。
- **检查历史可审计：** 每次 `sh heartbeat check` 都会在检查记录表中追加一条记录，方便回溯调度历史。

### 8.2 基础用法

```bash
# 添加每日 8:30 自动日报（使用 --schedule 自然语言描述周期）
sh heartbeat add --name="每日概览" --schedule="每天 08:30" --command="sh analytics overview --period=today --compare"

# 添加每周五下午 3 点周报
sh heartbeat add --name="周报分析" --schedule="每周五 15:00" --command="sh analytics overview --period=7d"

# 也可以继续使用 cron 表达式（适合高级调度需求）
sh heartbeat add \
  --name="daily-anomaly-check" \
  --cron="0 8,14,20 * * *" \
  --command="sh analytics anomaly --sensitivity=2"

# 查看所有任务
sh heartbeat list

# 手动触发任务
sh heartbeat run daily-overview

# 暂停任务
sh heartbeat pause daily-overview

# 删除任务
sh heartbeat remove daily-overview
```

### 8.3 Cron 表达式速查

```
格式：分钟 小时 日 月 星期

0 9 * * *        每天早 9 点
0 8 * * 1        每周一早 8 点
0 9,18 * * *     每天早 9 点和下午 6 点
*/30 * * * *     每 30 分钟
0 9 1 * *        每月 1 日早 9 点
0 9 * * 1-5      工作日（周一到周五）早 9 点
```

### 8.4 自然语言创建定时任务

你也可以直接用自然语言让 AI 帮你创建定时任务：

```bash
sh "帮我每天早上 9 点自动生成业务日报，包括 GMV、订单、新客"
```

AI 会解析你的意图，生成类似以下的调度计划：

```
[SCHEDULE_TASK]
- Name: morning-daily-report
- Frequency: 0 9 * * *
- Command: sh analytics overview --period=today --compare
- Insights: true
[/SCHEDULE_TASK]

已为你创建定时任务：morning-daily-report
下次执行时间：明天 09:00
```

### 8.5 大促期间实时监控方案

```bash
# 大促期间每 30 分钟检查一次核心数据
sh heartbeat add \
  --name="promo-realtime" \
  --cron="*/30 * * * *" \
  --command="sh analytics overview --period=today"

# 每 10 分钟异常检测（高灵敏度）
sh heartbeat add \
  --name="promo-anomaly" \
  --cron="*/10 * * * *" \
  --command="sh analytics anomaly --period=today --sensitivity=3"

# 大促结束后记得关闭高频任务
sh heartbeat pause promo-realtime
sh heartbeat pause promo-anomaly
```

---

## 9. Skills 插件：扩展你的分析能力

### 9.1 什么是 Skills

Skills 是 SocialHub CLI 的插件系统，允许安装第三方或内部开发的分析工具，在安全沙箱中运行。

**典型 Skills 类型：**
- **报告生成**：将分析数据转换为 Word/PDF/PPT 格式
- **数据可视化**：生成复杂图表（热力图、桑基图等）
- **外部集成**：将分析结果同步到飞书、企业微信、邮件
- **定制分析**：特定行业或品类的专属分析模型

### 9.2 发现和安装 Skills

```bash
# 浏览 Skills 商店
sh skills browse

# 按分类浏览
sh skills browse --category=analytics
sh skills browse --category=reporting

# 搜索特定 Skill
sh skills search "报告"

# 查看 Skill 详情（安装前了解权限要求）
sh skills info report-generator

# 安装 Skill
sh skills install report-generator
# 安装过程中会显示权限请求，需要你确认

# 查看已安装的 Skills
sh skills list
```

### 9.3 使用 Skills

```bash
# 基本用法
sh skills run <skill-name> <skill-command> [参数]

# 示例：用报告生成 Skill 生成月报 PDF
sh skills run report-generator create-monthly-report \
  --period=last_month \
  --output=./reports/monthly_report.pdf

# 示例：发送到飞书
sh skills run lark-reporter send-report \
  --chat-id=oc_xxxx \
  --period=last_week
```

### 9.4 Skills 的安全保证

作为数据分析师，你需要了解以下安全机制，以便在被询问时给出合理解释：

**安装时的保护：**
1. 每个 Skill 都有 Ed25519 数字签名，确保来自官方来源
2. SHA-256 哈希校验文件完整性（防止被篡改）
3. CRL 吊销列表检查（已发现问题的 Skill 会被拦截）

**运行时的保护：**
- Skill 只能访问指定目录（`~/.socialhub/skills/<name>/` 和工作目录）
- 需要网络访问的 Skill 必须在安装时明确声明并获得授权
- 任何超出权限的行为都会被拦截并记录

**权限审批：**
```
安装 report-generator 时的权限提示：

  report-generator 请求以下权限：
  ✓ [file:read]   读取分析数据文件
  ✓ [file:write]  保存报告到指定目录
  ✗ [network:internet]  发送数据到外部服务器 ← 需要谨慎！

  是否授权？[y/N]:
```

**建议：** 对 `network:internet` 权限要特别谨慎，只授权给你信任来源的 Skill。

---

## 10. 数据导出与报告生成

### 10.1 内置导出功能

```bash
# 导出为 CSV（适合进一步 Excel 分析）
sh analytics orders --period=30d --group=channel \
  --output-format=csv --export=./data/channel_orders.csv

# 导出为 JSON（适合程序处理或数据存档）
sh analytics rfm --segment-filter=at-risk \
  --output-format=json --export=./data/at_risk_customers.json

# 批量导出（结合 shell 脚本）
for period in 7d 30d 90d; do
  sh analytics overview --period=$period \
    --output-format=json \
    --export=./data/overview_${period}.json
done
```

### 10.2 生成 HTML 报告

CLI 内置 HTML 报告生成能力：

```bash
# 生成可视化 HTML 报告
sh analytics overview --period=30d --report --report-output=./reports/overview.html

# 包含图表的订单分析报告
sh analytics orders --period=30d --group=channel --report \
  --report-output=./reports/channel_analysis.html
```

生成的 HTML 报告包含：
- 响应式布局，可在浏览器直接查看
- 交互式图表（折线图、柱状图、饼图）
- 核心数据高亮展示
- 可直接通过链接分享

### 10.3 图表生成

```bash
# 生成 GMV 趋势图（PNG 格式）
sh analytics orders --period=90d --chart --chart-output=./charts/gmv_trend.png

# 生成渠道分布饼图
sh analytics orders --period=30d --group=channel \
  --chart-type=pie --chart-output=./charts/channel_pie.png
```

### 10.4 定期自动报告方案

**方案：结合 heartbeat + 导出 + Skill（飞书/邮件发送）**

```bash
# 步骤 1：创建每周报告任务
sh heartbeat add \
  --name="weekly-export" \
  --cron="0 8 * * 1" \
  --command="sh analytics overview --period=last_week --compare --output-format=json --export=/tmp/weekly_overview.json"

# 步骤 2：安装飞书报告 Skill（如果有）
sh skills install lark-reporter

# 步骤 3：创建完整的周报自动化任务（自然语言）
sh "帮我设置一个每周一早 8 点的自动周报，分析上周整体数据、渠道对比、
   活动效果，生成 HTML 报告并发送到飞书群 oc_xxxx"
```

---

## 11. MCP 数据库直连：写 SQL 的进阶玩法

### 11.1 什么时候需要直连 MCP

内置分析命令已经覆盖了 90% 的日常需求。以下情况需要用 MCP 直连写 SQL：
- 内置命令没有覆盖的定制维度（如特定 SKU 的历史价格变化）
- 需要关联多张业务表
- 临时性的探索分析，结果不需要复用
- 数据质量问题排查

### 11.2 探索数据库结构

```bash
# 查看所有可用的数据库表
sh mcp tables

# 查看特定表的字段结构
sh mcp schema dwd_v_order

# 输出示例：
# Table: dwd_v_order
# ┌─────────────────────┬────────────┬─────────────────────────────────┐
# │  Column             │  Type      │  Description                    │
# ├─────────────────────┼────────────┼─────────────────────────────────┤
# │  order_id           │  VARCHAR   │  订单 ID                         │
# │  customer_id        │  VARCHAR   │  客户 ID                         │
# │  channel            │  VARCHAR   │  渠道（weixin/douyin/taobao）    │
# │  order_value        │  DECIMAL   │  订单金额                         │
# │  order_date         │  DATE      │  下单日期                         │
# │  status             │  VARCHAR   │  订单状态                         │
# └─────────────────────┴────────────┴─────────────────────────────────┘

# 搜索包含特定字段的表
sh mcp search --keyword="customer_id"
```

### 11.3 执行 SQL 查询

```bash
# 交互式 SQL 模式
sh mcp sql

# 进入交互式界面后输入 SQL：
> SELECT channel, COUNT(*) as orders, SUM(order_value) as gmv
  FROM dwd_v_order
  WHERE order_date >= CURRENT_DATE - 30
  GROUP BY channel
  ORDER BY gmv DESC;

# 单次查询（非交互式）
sh mcp query "SELECT COUNT(*) FROM dwd_v_customer WHERE register_date >= '2026-01-01'"
```

### 11.4 常用 SQL 分析模板

**渠道转化漏斗（自定义版）：**

```sql
-- 近 30 天各渠道的访问→购买漏斗
SELECT
    channel,
    COUNT(DISTINCT visitor_id) AS visitors,
    COUNT(DISTINCT CASE WHEN add_to_cart = 1 THEN visitor_id END) AS cart_adds,
    COUNT(DISTINCT customer_id) AS buyers,
    ROUND(COUNT(DISTINCT customer_id) * 100.0 / COUNT(DISTINCT visitor_id), 2) AS cvr
FROM dwd_v_user_behavior
WHERE event_date >= CURRENT_DATE - 30
GROUP BY channel
ORDER BY cvr DESC;
```

**自定义 RFM 分层：**

```sql
-- 基于过去 180 天数据的 RFM 打分
WITH rfm_base AS (
    SELECT
        customer_id,
        DATEDIFF(CURRENT_DATE, MAX(order_date)) AS recency,
        COUNT(DISTINCT order_id) AS frequency,
        SUM(order_value) AS monetary
    FROM dwd_v_order
    WHERE order_date >= CURRENT_DATE - 180
      AND status = 'completed'
    GROUP BY customer_id
)
SELECT
    customer_id,
    recency, frequency, monetary,
    CASE
        WHEN recency <= 30 AND frequency >= 3 AND monetary >= 500 THEN 'VIP'
        WHEN recency <= 60 AND frequency >= 2 THEN 'Loyal'
        WHEN recency > 90 AND frequency >= 3 THEN 'At-Risk'
        ELSE 'Others'
    END AS rfm_segment
FROM rfm_base;
```

**同期群留存率（精确计算）：**

```sql
-- 按首购月份分析次月留存
WITH first_purchase AS (
    SELECT customer_id, DATE_TRUNC('month', MIN(order_date)) AS cohort_month
    FROM dwd_v_order
    WHERE status = 'completed'
    GROUP BY customer_id
),
repeat_purchase AS (
    SELECT o.customer_id, DATE_TRUNC('month', o.order_date) AS purchase_month
    FROM dwd_v_order o
    JOIN first_purchase fp ON o.customer_id = fp.customer_id
    WHERE o.order_date > fp.cohort_month
      AND o.status = 'completed'
)
SELECT
    fp.cohort_month,
    COUNT(DISTINCT fp.customer_id) AS cohort_size,
    COUNT(DISTINCT rp.customer_id) AS retained,
    ROUND(COUNT(DISTINCT rp.customer_id) * 100.0 / COUNT(DISTINCT fp.customer_id), 2) AS retention_rate
FROM first_purchase fp
LEFT JOIN repeat_purchase rp
    ON fp.customer_id = rp.customer_id
    AND rp.purchase_month = fp.cohort_month + INTERVAL '1 month'
GROUP BY fp.cohort_month
ORDER BY fp.cohort_month;
```

---

## 12. 常见问题排查

### 12.1 连接问题

**问题：`Error: MCP connection failed`**

```bash
# 检查配置
sh config show

# 确认 MCP 地址是否正确
sh config get mcp.sse_url

# 测试连接
sh mcp tables

# 如果是代理问题，设置代理
sh config set network.http_proxy "http://proxy.company.com:8080"
```

**问题：`Auth: token expired`**

```bash
# 重新登录
sh auth login

# 查看 token 状态
sh auth status
```

> **Token 宽限期：** 认证服务短暂中断（< 5 分钟）不会立即锁定用户，已有 token 在宽限期内仍然有效。

**问题：登录时密码输入不可见 / 无法粘贴**

部分终端（如 PowerShell）的密码输入可能不可靠。可以使用显示密码模式：

```bash
# 方式一：命令行参数
sh auth login --show-password

# 方式二：环境变量
export SOCIALHUB_SHOW_PASSWORD=1
sh auth login
```

---

### 12.2 数据问题

**问题：查询结果比 BI 系统少**

常见原因：
1. 时间范围口径不同（CLI 默认 `30d` = 过去 30 天，部分 BI 按自然月）
2. 订单状态过滤（CLI 默认只统计 `completed` 状态）
3. 多租户数据隔离（检查 `tenant_id` 配置）

```bash
# 确认当前 tenant_id
sh config get mcp.tenant_id

# 查看数据口径（使用 SQL 直连验证）
sh mcp query "SELECT status, COUNT(*) FROM dwd_v_order WHERE order_date >= '2026-03-01' GROUP BY status"
```

**问题："今天"查询的数据差一天**

分析层统一使用 UTC 时区进行日期计算。如果你所在时区为 UTC+8，在北京时间凌晨 0:00-8:00 之间查询"今天"的数据时，分析层的"今天"仍然是 UTC 的前一天。这是预期行为，不是数据缺失。

**问题：某天数据为空**

```bash
# 使用异常检测确认
sh analytics anomaly --period=7d --metric=orders

# 直连数据库检查原始数据
sh mcp query "SELECT order_date, COUNT(*) FROM dwd_v_order WHERE order_date BETWEEN '2026-04-01' AND '2026-04-02' GROUP BY order_date"
```

---

### 12.3 AI 模式问题

**问题：AI 给出的命令执行失败**

```bash
# 查看最近的 AI 决策 trace
sh trace list --date=today

# 查看具体 trace 内容
sh trace view <trace-id>

# 重新用直接命令尝试
sh analytics overview --period=30d
```

**问题：AI 的分析计划不符合预期**

在自然语言提问时，加入更多约束：

```bash
# 添加明确的限制
sh "分析订单趋势，只看微信渠道，只分析近 7 天，不要看其他维度"

# 或者先用直接命令，再追问洞察
sh analytics orders --period=7d --group=channel
sh "基于上面的数据，微信渠道下降的主要原因可能是什么？"
```

**问题：多步计划执行到一半失败**

```bash
# 查看历史记录
sh history list

# 查看失败的执行记录
sh history view <history-id>

# 手动执行剩余步骤
sh analytics retention --period=30d --days=30  # 从失败步骤开始
```

---

### 12.4 技巧与快捷方式

```bash
# 重复上一次查询
sh repeat

# 查看命令历史
sh history list

# 从历史重播某次查询
sh history replay <history-id>

# 清除会话历史
sh session delete --all-expired
```

---

## 13. 分析场景速查手册

### 场景 A：日常巡检（每天花 5 分钟）

```bash
sh analytics overview --period=today        # 今日实时大盘
sh analytics anomaly --period=today         # 今日异常检测
```

---

### 场景 B：日报生成（每天早 9 点）

```bash
sh analytics overview --period=yesterday --compare   # 昨日 vs 前日
sh analytics orders --period=7d --group=channel      # 渠道趋势
sh analytics retention --period=7d --days=7          # 近 7 日留存
```

---

### 场景 C：周报生成（每周一）

```bash
sh analytics overview --period=last_week --compare
sh analytics orders --period=last_week --group=channel --compare
sh analytics campaigns --period=last_week --include-roi
sh analytics retention --period=last_month --days=30
```

---

### 场景 D：月报生成（每月 1 日）

```bash
sh analytics overview --period=last_month --compare
sh analytics orders --period=last_month --group=channel
sh analytics customers --period=last_month --include-source
sh analytics rfm
sh analytics loyalty
sh analytics ltv --cohort-months=12 --follow-months=6
sh analytics points --period=last_month --include-breakdown
```

---

### 场景 E：大促前准备

```bash
sh analytics rfm --segment-filter=vip              # 导出 VIP 客群
sh analytics rfm --segment-filter=at-risk          # 导出 at-risk 客群
sh analytics coupons --period=30d                  # 现有优惠券核销率
sh analytics retention --days=30,90               # 留存基线
```

---

### 场景 F：大促期间实时监控

```bash
sh analytics overview --period=today               # 每小时看一次
sh analytics anomaly --sensitivity=3               # 每 30 分钟异常检测
sh analytics orders --period=today --group=channel # 渠道实时对比
```

---

### 场景 G：大促复盘

```bash
sh analytics overview --period=7d --compare
sh analytics orders --period=7d --group=channel --include-returns
sh analytics campaigns --name-filter="大促" --include-roi --attribution-window-days=14
sh analytics customers --period=7d --include-source
sh analytics retention --period=7d --days=30
```

---

### 场景 H：流失预警与召回

```bash
sh analytics rfm --segment-filter=at-risk --export=./at_risk.csv
sh analytics points --expiring-within-days=30      # 积分即将过期客户
sh analytics repurchase --period=90d              # 复购周期参考
```

---

### 场景 I：营销活动评估

```bash
sh analytics campaigns --campaign-id=<id> --include-roi
sh analytics retention --period=30d               # 活动后留存
sh analytics funnel --period=30d                  # 生命周期漏斗变化
```

---

### 场景 J：商品分析

```bash
sh analytics products --period=30d               # 商品销售排行
sh analytics orders --period=30d --group=product # 商品订单分布
sh mcp sql  # 定制 SQL 分析特定 SKU
```

---

## 14. 附录：指标定义与口径说明

### A. 核心指标定义

| 指标 | 定义 | 口径说明 |
|------|------|---------|
| **GMV** | 总交易金额 | 只统计 `status=completed` 的订单，不含已取消、退款中 |
| **AOV** | 平均客单价 | GMV ÷ 有效订单数 |
| **新客数** | 统计期内首次购买的客户数 | 以历史上第一笔完成订单日期为首购日期 |
| **活跃买家** | 统计期内有购买行为的客户数 | 去重客户 ID，不限购买次数 |
| **30 日留存率** | 某批次客户在 30 天后仍有购买的比例 | 分母为批次客户总数，分子为 30 天内有再购的客户数 |
| **RFM - Recency** | 客户最近一次购买距今天数 | 取最近一笔完成订单的日期计算 |
| **RFM - Frequency** | 客户历史购买次数 | 计算期内有效订单数（不含退款） |
| **RFM - Monetary** | 客户历史消费总金额 | 计算期内完成订单的 GMV 之和 |
| **LTV** | 客户生命周期价值 | 按首购月份分组后，跟踪累计 GMV |
| **优惠券核销率** | 已核销优惠券 ÷ 已发放优惠券 | 以面值统计（非数量） |
| **活动 ROI** | 活动期内新增 GMV ÷ 活动总成本 | 归因窗口默认 7 天，可调整 |

---

### B. 时间口径说明

| 参数值 | 计算方式 | 示例（今日为 2026-04-02） |
|-------|---------|------------------------|
| `today` | `[今日 00:00, 当前时间]` | 2026-04-02 00:00 ~ 现在 |
| `7d` | `[今日-6天 00:00, 今日 23:59]` | 2026-03-27 ~ 2026-04-02 |
| `30d` | `[今日-29天 00:00, 今日 23:59]` | 2026-03-04 ~ 2026-04-02 |
| `last_week` | 上周完整自然周（周一到周日） | 2026-03-23 ~ 2026-03-29 |
| `last_month` | 上月完整自然月 | 2026-03-01 ~ 2026-03-31 |
| `ytd` | `[今年 1 月 1 日, 今日 23:59]` | 2026-01-01 ~ 2026-04-02 |

---

### C. 渠道标准编码

| 渠道编码 | 渠道名称 |
|---------|---------|
| `weixin` | 微信小程序 |
| `douyin` | 抖音/TikTok |
| `taobao` | 淘宝/天猫 |
| `app` | 自营 APP |
| `h5` | 微信 H5 |
| `offline` | 线下门店 |
| `other` | 其他渠道 |

---

### D. 快速命令参考卡

```
日常分析
  sh analytics overview [--period=30d] [--compare]
  sh analytics orders [--group=channel|province|product] [--include-returns]
  sh analytics retention [--days=7,30,90] [--comparison-period=90d]
  sh analytics anomaly [--metric=gmv|orders|aov] [--sensitivity=1-3]

深度分析
  sh analytics rfm [--segment-filter=vip|at-risk|loyal|sleeping]
  sh analytics ltv [--cohort-months=12] [--follow-months=6]
  sh analytics funnel [--period=90d]
  sh analytics campaigns [--campaign-id=X] [--include-roi]
  sh analytics loyalty
  sh analytics points [--expiring-within-days=30]

AI 模式
  sh "<自然语言描述>"
  sh -c <session-id> "<追问>"

定时任务
  sh heartbeat add --name=X --cron="0 9 * * *" --command="..."
  sh heartbeat list
  sh heartbeat run <name>

数据库直连
  sh mcp tables
  sh mcp schema <table-name>
  sh mcp sql

历史与会话
  sh history list
  sh history replay <id>
  sh session list
  sh trace list --date=today
```

---

## 结语

SocialHub CLI 的核心设计理念是：**让数据分析师从"取数工具"升级为"洞察生产者"**。

传统工作流中，数据分析师的大量时间花在取数、清洗、格式化上，真正用于思考和洞察的时间反而很少。CLI 通过以下方式改变这一现状：

- **命令化**取数流程，从 30 分钟压缩到 30 秒
- **AI 驱动**探索性分析，降低对 SQL 的依赖
- **自动化**日常报告，释放重复性工作时间
- **标准化**指标口径，消除部门间数据争议

随着你对这套工具的熟悉，你会发现分析工作的重心会自然地从"怎么取数"转移到"怎么解读和决策"——这才是数据分析师最核心的价值所在。

---

*文档版本：v1.0 | 2026 年 4 月*
*反馈与建议：请联系数据平台团队*
*下次更新：2026 年 7 月（新功能发布后同步更新）*
