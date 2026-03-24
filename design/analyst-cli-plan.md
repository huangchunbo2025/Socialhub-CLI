# Data Analyst CLI Extension Plan

## 目标

让数据分析师通过自然语言和业务语义命令完成日常分析工作，无需接触 SQL 或数据库。

---

## 设计原则

1. **分析师只看业务语言**，SQL 全部封装在命令内部
2. **两层互补**：结构化命令覆盖高频场景，`sh ai ask` 覆盖临时需求
3. **复用现有模式**：所有新命令沿用 `_get_mcp_*` + `mcp.query()` 模式，不引入新架构
4. **MCP 是唯一数据通道**，分析师无法绕过

```
分析师输入
    ├── sh <command> [options]    → 内部 SQL → MCP → 数据库
    └── sh ai ask "..."           → LLM 理解 → 内部 SQL → MCP → 数据库
```

---

## 现有基础（可直接复用）

| 已有 | 位置 | 说明 |
|------|------|------|
| MCP 连接 | `cli/api/mcp_client.py` | `query()` / `list_tables()` / `get_table_schema()` |
| analytics 命令 | `cli/commands/analytics.py` | overview / customers / retention / orders / campaigns / points / coupons / report |
| AI 自然语言 | `cli/commands/ai.py` | `sh ai ask` / smart mode |
| 输出/导出 | `cli/output/` | table / json / csv / html / pdf |
| 参数校验 | `analytics.py` | `_validate_period()` / `_validate_group_by()` |

---

## 一、增强现有 analytics 命令

### 当前局限

| 命令 | 当前限制 | 需要改进 |
|------|---------|---------|
| `analytics overview` | 只支持固定 period | 支持自定义 `--from` / `--to` 日期范围 |
| `analytics customers` | 只能按一个维度分组 | 支持多维度组合，增加 identity_type 筛选 |
| `analytics orders` | 分组维度固定 | 增加按 tier_code / loyalty_program 分组 |
| `analytics campaigns` | 列表展示为主 | 增加 `--detail` 深度分析（ROI、节点漏斗） |
| `analytics points` | 总览 | 增加到期预警（`--expiring-days`） |

### 具体改动：`cli/commands/analytics.py`

**1. 增加自定义日期范围参数（所有命令通用）**

```python
# 在所有分析命令上增加
from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD")
to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD")

# --from/--to 优先级高于 --period
# 内部统一用 _resolve_date_range(period, from_date, to_date) 处理
```

**2. `analytics customers` 新增维度**

```python
# 新增筛选
identity: Optional[str] = typer.Option(None, "--identity",
    help="Filter by identity type: member / registered / visitor")

# identity_type 映射：member=1, registered=2, visitor=3
```

**3. `analytics campaigns` 新增深度分析**

```python
@app.command("campaigns")
def analytics_campaigns(
    code: Optional[str] = typer.Option(None, "--code", help="Campaign code for detail view"),
    detail: bool = typer.Option(False, "--detail", help="Show node-level funnel analysis"),
    ...
)
# 当 --code + --detail 时，额外查 vdm_t_activity_process 节点漏斗数据
```

**4. `analytics points` 增加到期预警**

```python
expiring_days: int = typer.Option(0, "--expiring-days",
    help="Show points expiring within N days (0=disabled)")
# 查 vdm_t_points_record.effective_end_time
```

---

## 二、新增 `sh members` 命令组

### 新建文件：`cli/commands/members.py`

这是分析师最常用的模块，独立成组。

#### 命令列表

```bash
sh members overview                          # 会员总览
sh members tier-distribution                 # 等级分布
sh members growth [--from] [--to] [--by]    # 新增趋势
sh members churn [--period] [--tier]        # 流失分析
sh members rfm [--output]                   # RFM 价值分层
sh members at-risk [--days]                 # 预流失预警
sh members top [--by] [--limit]             # 高价值会员
```

#### 内部 SQL 模板

**`members overview`**
```sql
-- 来自 das_demoen（已聚合，查询快）
SELECT
    BITMAP_COUNT(BITMAP_UNION(active_custs_bitnum))  AS active_members,
    SUM(add_custs_num)                               AS new_members,
    BITMAP_COUNT(BITMAP_UNION(buyer_bitnum))          AS buying_members,
    BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))    AS churned_members
FROM das_demoen.ads_das_business_overview_d
WHERE biz_date = {latest_date}
  AND identity_type = 1   -- 会员
```

**`members tier-distribution`**
```sql
SELECT
    tier_name,
    loyalty_program_name,
    SUM(total_custs_num_td) AS member_count
FROM das_demoen.ads_das_custs_tier_distribution_d
WHERE biz_date = {latest_date}
  AND identity_type = 1
GROUP BY tier_name, loyalty_program_name
ORDER BY member_count DESC
```

**`members growth`**
```sql
SELECT
    DATE_FORMAT(biz_date, {format}) AS period,   -- 月/周/日
    SUM(add_custs_num)               AS new_members
FROM das_demoen.ads_das_business_overview_d
WHERE identity_type = 1
  AND biz_date BETWEEN {from_date} AND {to_date}
GROUP BY period
ORDER BY period
```

**`members churn`**
```sql
SELECT
    tier_name,
    BITMAP_COUNT(BITMAP_UNION(pre_churn_custs_bitnum)) AS pre_churn,
    BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))      AS churned,
    BITMAP_COUNT(BITMAP_UNION(dead_custs_bitnum))        AS lost
FROM das_demoen.ads_das_custs_tier_distribution_d
WHERE biz_date = {latest_date}
GROUP BY tier_name
```

**`members rfm`**
```sql
-- 直接查 RFM 视图
SELECT *
FROM das_demoen.ads_v_rfm
WHERE identity_type = 1
LIMIT {limit}
```

**`members at-risk`**
```sql
-- Pre-churn 客户列表（需从 dts 关联获取详情）
SELECT
    c.code,
    c.name,
    c.mobilephone,
    m.tier_code,
    m.last_order_time   -- 最近购买时间（推算风险）
FROM dts_demoen.vdm_t_consumer c
JOIN dts_demoen.vdm_t_member m ON m.consumer_code = c.code
WHERE m.status = 1           -- 正常会员
  AND m.delete_flag = 0
  AND c.last_order_time < DATE_SUB(NOW(), INTERVAL {days} DAY)
  AND c.delete_flag = 0
ORDER BY c.last_order_time ASC
LIMIT {limit}
```

**`members top`**

```sql
SELECT
    m.consumer_code,
    c.name,
    m.tier_code,
    pa.accumulative_points,
    pa.available_points
FROM dts_demoen.vdm_t_member m
JOIN dts_demoen.vdm_t_consumer c ON c.code = m.consumer_code
JOIN dts_demoen.vdm_t_points_account pa ON pa.member_code = m.card_no
WHERE m.status = 1 AND m.delete_flag = 0
ORDER BY pa.accumulative_points DESC   -- 或按消费金额：需关联 order
LIMIT {limit}
```

#### 注册到 main.py

```python
# cli/main.py 增加
from .commands import members
app.add_typer(members.app, name="members", help="Member analytics commands")
```

---

## 三、新增 `sh customers profile` 命令

在现有 `cli/commands/customers.py` 增加一个子命令，整合三表数据给出客户完整视图。

```bash
sh customers profile 01000000001
```

**内部逻辑（3 个并行 MCP 查询）：**

```python
# 查询 1：基础信息
SELECT code, name, gender, mobilephone, email, source_code,
       first_order_time, last_order_time
FROM dts_demoen.vdm_t_consumer
WHERE code = {consumer_code} AND delete_flag = 0

# 查询 2：会员信息 + 积分
SELECT m.card_no, m.tier_code, m.register_date, m.status,
       pa.accumulative_points, pa.available_points, pa.transit_points
FROM dts_demoen.vdm_t_member m
LEFT JOIN dts_demoen.vdm_t_points_account pa ON pa.member_code = m.card_no
WHERE m.consumer_code = {consumer_code} AND m.delete_flag = 0

# 查询 3：近5笔订单
SELECT code, order_date, cost_amount/100 AS amount_yuan,
       direction, qty
FROM dts_demoen.vdm_t_order
WHERE customer_code = {consumer_code} AND delete_flag = 0
ORDER BY order_date DESC LIMIT 5
```

**输出示例：**
```
┌─ Customer Profile: 01000000001 ─────────────────────┐
│ Name: 张三    Gender: 男    Phone: 138****8888        │
│ Source: 微信  Registered: 2022-03-15                 │
├─ Membership ────────────────────────────────────────┤
│ Card: M0001234   Tier: Gold   Status: 正常            │
│ Points: 12,450 available  (28,900 accumulated)       │
├─ Recent Orders ─────────────────────────────────────┤
│ 2024-03-10  ¥328.00  正单  3件                       │
│ 2024-02-28  ¥156.00  正单  2件                       │
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

---

## 四、增强 `sh ai ask`

### 问题

当前 `sh ai ask` 的 AI system prompt 里没有数据库 schema 上下文，LLM 对业务字段不熟悉，生成的内部查询容易出错。

### 改动：`cli/commands/ai.py`

在 `SYSTEM_PROMPT` 中注入业务上下文：

```python
DB_CONTEXT = """
## Available Databases

### dts_demoen — Core Transactional Data
Key tables:
- vdm_t_consumer: customer master (consumer_code, name, gender, mobilephone, source_code, first_order_time, last_order_time)
- vdm_t_member: membership card (card_no, consumer_code, tier_code, status, register_date, loyalty_program_code)
- vdm_t_points_account: points balance (member_code, accumulative_points, available_points, transit_points, expired_points)
- vdm_t_points_record: points transactions (operation_type, direction, points_value, order_code, effective_end_time)
- vdm_t_order: transactions (code, customer_code, order_date, cost_amount[fen], direction[0=sale,1=return], type[0=member])
- vdm_t_coupon: issued coupons (customer_code, status[1=issued,2=used,3=expired], coupon_rule_code)
- vdm_t_activity: campaigns (code, name, status, start_time, end_time)

### datanow_demoen — Segmentation & Events
Key tables:
- t_customer_group: customer groups (group_id, group_name, group_type[0=static,1=dynamic])
- t_customer_group_detail: group members (customer_code, group_id, status[1=active])
- t_customer_tag_result: customer tags (customer_code, tag_id, tag_value)
- t_member: membership snapshot

### das_demoen — Pre-aggregated Analytics (FAST, use this for metrics)
Key tables:
- ads_das_business_overview_d: daily KPIs (biz_date, identity_type, total_custs_num, add_custs_num, total_transaction_amt)
- ads_das_activity_analysis_d: campaign metrics (activity_code, biz_date, activity_Points_Issued, activity_coupon_issue_qty)
- ads_das_custs_tier_distribution_d: tier distribution (biz_date, tier_code, tier_name, total_custs_num_td)
- ads_v_rfm: RFM segments (ready to query)
- dws_customer_base_metrics: customer behavior metrics

## Rules
- identity_type: 1=member, 2=registered, 3=visitor
- All amounts are in FEN (divide by 100 for yuan display)
- Always filter: delete_flag = 0
- Always filter: tenant_id = {tenant_id}
- For aggregate queries, prefer das_demoen (pre-computed)
- For individual customer queries, use dts_demoen
- NEVER expose SQL to the user; translate results to business language
"""

SYSTEM_PROMPT = SYSTEM_PROMPT + DB_CONTEXT
```

同时，AI 返回结果要翻译回业务语言（不展示 SQL，只展示洞察）：

```
用户: "上个月金卡会员的平均消费金额是多少？"
AI内部: 查 das_demoen 或 dts_demoen，计算结果
AI输出: "上个月（2024年2月）金卡会员平均消费金额为 ¥428.5，
         共有 3,241 名金卡会员产生了消费行为。"
```

---

## 五、新文件清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `cli/commands/members.py` | 新建 | 7 个 members 子命令 |
| `cli/commands/analytics.py` | 修改 | 增加 `--from/--to`，扩展 campaigns/points 参数 |
| `cli/commands/customers.py` | 修改 | 增加 `profile` 子命令 |
| `cli/commands/ai.py` | 修改 | 注入 DB_CONTEXT 到 system prompt |
| `cli/main.py` | 修改 | 注册 members 命令组，更新 VALID_COMMANDS |

---

## 六、实现顺序

### Phase 1：基础增强（改动小，效果快）
1. `ai.py` 注入 DB_CONTEXT → `sh ai ask` 立刻变准
2. `analytics.py` 增加 `--from/--to` 参数 → 现有命令更灵活

### Phase 2：核心新命令
3. `members.py` 新建 → 覆盖分析师最高频需求
4. `customers.py` 增加 `profile` → 360 客户视图

### Phase 3：深度分析
5. `analytics campaigns --code --detail` → 活动漏斗
6. `analytics points --expiring-days` → 积分到期预警
7. 按分析师实际反馈继续补充

---

## 七、验收标准

分析师能用以下自然语言/命令完成工作，**无需知道任何 SQL 或表名**：

```bash
# 日常监控
sh members overview
sh analytics overview --from=2024-01-01 --to=2024-03-31

# 会员分析
sh members tier-distribution
sh members growth --from=2024-01 --to=2024-03 --by=month
sh members churn --period=90d
sh members at-risk --days=60

# 活动效果
sh analytics campaigns --code=ACT001 --detail

# 客户洞察
sh customers profile 01000000001
sh members top --by=points --limit=20

# 临时问题（自然语言）
sh ai ask "哪个等级的会员复购率最高？"
sh ai ask "上个月通过微信渠道注册的新会员有多少？"
sh ai ask "ACT001 活动的积分发放总量和核销率"
sh ai ask "生成一份本季度会员运营分析报告"
```
