# Database Schema Guide

客户数据平台（CDP）三库结构说明，供开发时快速理解数据来源、字段含义和查询方式。

---

## 一、三库总览

这是一套标准的数据仓库分层架构，数据从业务系统流向分析层：

```
dts_demoen          →      datanow_demoen       →      das_demoen
（业务源数据）              （实时处理/运营）              （分析/BI层）
  31 张表                     45 张表                     78 张表
原始业务数据                客群/标签/实时事件           聚合指标/报表数据
```

| 数据库 | 定位 | 表前缀 | 用途 |
|--------|------|--------|------|
| `dts_demoen` | 业务源数据 | `vdm_t_` | 原始交易、会员、积分等核心业务数据 |
| `datanow_demoen` | 实时处理层 | `t_`、`t_ma_`、`ads_rec_` | 客群计算、标签结果、营销自动化状态 |
| `das_demoen` | 分析/BI层 | `ads_`、`dws_`、`dwd_`、`dim_` | 预聚合指标，供报表和看板直接查询 |

---

## 二、核心业务概念

### 客户身份体系

一个人在系统中有三层身份，层层关联：

```
vdm_t_consumer（客户基础档案）
    ↓ consumer_code
vdm_t_consumer_identity（身份类型）
    identity_type: 1=会员 2=注册用户 3=访客 4=员工
    ↓ 当 identity_type=1 时
vdm_t_member（会员卡）
    card_no → loyalty_program_code（忠诚度计划）
              ↓
           tier_code（当前等级）
```

**关键标识符：**
- `consumer_code` — 客户唯一编号，`01` 开头，如 `01000000001`
- `card_no` — 会员卡号（非会员无此字段）
- `loyalty_program_code` — 所属忠诚度计划编码
- `tenant_id` — 租户编号（多租户系统，查询时通常需要带上）

### 积分体系

```
vdm_t_loyalty_program（忠诚度计划）
    ↓
vdm_t_basic_points_rule（基础积分规则：消费赚积分）
vdm_t_promotion_points_rule（促销积分规则：活动多倍积分）
    ↓ 触发条件满足后
vdm_t_points_account（积分账户，一个会员一条）
    accumulative_points  — 累计积分（历史总获得）
    available_points     — 可用积分（当前可用）
    transit_points       — 在途积分（未到账）
    expired_points       — 过期积分
    used_points          — 已使用积分
    ↓ 每次变动
vdm_t_points_record（积分流水明细）
    operation_type: 1=消费基础积分 2=促销积分 3=退货扣积分
                    4=人工加积分 5=人工减积分 6=行为积分
                    8=兑换礼品扣 9=兑换优惠券扣 11=过期扣减
```

### 优惠券体系

```
vdm_t_coupon_rule（优惠券规则：定义折扣、门槛、有效期）
    rule_type: 0=满减 1=折扣 2=兑换
    ↓ 发放后
vdm_t_coupon（客户持有的具体优惠券）
    status: 0=未生成 1=已下发 2=已使用 3=已过期
    par_value — 面值（单位：分，÷100 = 元）
```

### 订单体系

```
vdm_t_order（交易主单）
    direction: 0=正单 1=退单 2=换货单
    type: 0=会员单 1=员工单 2=非会员单
    所有金额字段单位均为「分」，÷100 = 元
    ↓
vdm_t_order_detail（订单商品明细）
    ↔ vdm_t_product（商品信息）
```

### 营销活动体系

```
vdm_t_activity（营销活动）
    marketing_type: 0=单次活动 1=周期性活动
    activity_type: 0=其他 1=客户旅程 2=节日活动
    ↓
vdm_t_activity_process（活动流程节点，Canvas画布中的每个节点）
    type — 节点类型（触发/条件/发积分/发优惠券/发消息等）
    process_config — 节点具体配置（JSON）
```

### 消息通道体系

支持渠道（`channel_type`）：
| 值 | 渠道 |
|----|------|
| 1 | 国内短信 |
| 2 | 国际/港澳台短信 |
| 4 | 邮件 |
| 8 | 微信 |
| 16 | WhatsApp |
| 17 | Line |
| 其他 | Messenger、MMS、App Push、App Inbox |

```
vdm_t_message_channel（渠道配置：密钥、频控规则）
vdm_t_template（消息模板）
vdm_t_message_record（消息发送记录，每条消息一条）
    status: 1=待提交 2=提交中 3=提交成功 4=提交失败 5=发送成功 6=发送失败
    operate_status: 1=打开 2=点击 3=退信 4=退订
vdm_t_message_send_history（发送历史聚合）
```

### 客群与标签（datanow_demoen）

```
t_customer_group（客群定义）
    group_type: 0=静态群组 1=动态群组
    generate_type: 0=规则群组 1=导入群组
    execute_sql — 动态群组的计算SQL
    ↓
t_customer_group_detail（群组成员明细）
t_customer_group_history（群组历史快照，使用 bitmap 存储）

t_customer_tag_result（客户标签结果，每个客户+标签一条）
    tag_value — 标签值（如 RFM等级、消费金额区间等）
```

---

## 三、das_demoen 分析层表前缀说明

| 前缀 | 全称 | 用途 |
|------|------|------|
| `dim_` | Dimension | 维度表，基础信息（客户、会员、模板） |
| `dwd_` | Data Warehouse Detail | 明细层，贴近业务的宽表（通常是视图） |
| `dws_` | Data Warehouse Summary | 汇总层，按天/月/年聚合的指标表 |
| `ads_` | Application Data Store | 应用层，直接供报表和 API 查询 |
| `tmp_` | Temporary | 临时中间计算表 |

**常用分析表：**
- `ads_das_business_overview_d` — 业务总览（客户数、订单数、活动量等）
- `ads_das_activity_analysis_d` — 活动分析（各活动的发券、发积分、消息量）
- `dws_customer_base_metrics` — 客户基础指标（RFM 基础数据）
- `dws_order_base_metrics_d` — 订单基础指标
- `dws_points_base_metrics_d` — 积分基础指标
- `ads_v_rfm` — RFM 分析视图（直接用于客户价值分层）

---

## 四、数据库技术特性（Apache Doris）

### 表类型与查询含义

| 建表关键字 | 语义 | 注意事项 |
|-----------|------|---------|
| `AGGREGATE KEY` | 相同 Key 自动聚合 | bitmap 字段用 `BITMAP_UNION`，数值用 `SUM` |
| `PRIMARY KEY` | 主键唯一，UPSERT | 相同主键新记录覆盖旧记录 |
| `UNIQUE KEY` | 唯一约束，最新覆盖 | 类似 PRIMARY KEY |
| `DUPLICATE KEY` | 无去重，追加写入 | 需在查询时自行去重 |

### bitmap 字段的正确用法

`bitmap` 类型不能直接 COUNT，必须用聚合函数：
```sql
-- 错误
SELECT COUNT(activity_custs_bitnum) FROM ...

-- 正确：获取不重复人数
SELECT BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) FROM ...

-- 正确：计算两个群体的交集人数
SELECT BITMAP_COUNT(BITMAP_AND(a.custs_bitnum, b.custs_bitnum)) FROM ...
```

### 金额字段

**所有金额字段单位均为「分」**，展示时需 ÷ 100：
```python
amount_yuan = amount_fen / 100
```

涉及字段：`total_price`、`cost_amount`、`coupon_amount`、`par_value`、`threshold_amount` 等

### 软删除

所有表都有 `delete_flag`，查询时需过滤：
```sql
WHERE delete_flag = 0
```

### CDC 同步字段

`_update_time`（注意前面有下划线）= 数据从源系统同步过来的时间，不是业务时间。用于判断数据新鲜度，不用于业务逻辑。

---

## 五、常用查询模式

### 查询某客户的完整信息

```sql
-- 基础信息 + 会员信息 + 积分
SELECT
    c.code AS consumer_code,
    c.name,
    c.mobilephone,
    m.card_no,
    m.tier_code,
    pa.available_points,
    pa.accumulative_points
FROM vdm_t_consumer c
LEFT JOIN vdm_t_member m ON m.consumer_code = c.code AND m.delete_flag = 0
LEFT JOIN vdm_t_points_account pa ON pa.member_code = m.card_no AND pa.delete_flag = 0
WHERE c.code = '01000000001'
  AND c.delete_flag = 0
```

### 查询客户最近订单

```sql
SELECT code, order_date, cost_amount / 100 AS amount_yuan, direction
FROM vdm_t_order
WHERE customer_code = '01000000001'
  AND delete_flag = 0
ORDER BY order_date DESC
LIMIT 10
```

### 查询某活动的效果指标

```sql
SELECT
    activity_code,
    activity_name,
    BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) AS 参与人数,
    SUM(activity_Points_Issued) AS 发放积分,
    SUM(activity_coupon_issue_qty) AS 发放优惠券,
    SUM(activity_msg_send_num) AS 消息发送量
FROM das_demoen.ads_das_activity_analysis_d
WHERE biz_date = '2024-12-31'  -- 汇总日期
  AND activity_code = 'ACT001'
GROUP BY activity_code, activity_name
```

### 查询客群成员列表

```sql
SELECT d.customer_code
FROM t_customer_group_detail d
WHERE d.group_id = 12345
  AND d.status = 1       -- 1=生效
  AND d.delete_flag = 0
```

---

## 六、identity_type 枚举值

贯穿三个数据库，多处用到：

| 值 | 含义 |
|----|------|
| 1 | 会员（加入了忠诚度计划，有 card_no） |
| 2 | 注册用户（有账号，未入会） |
| 3 | 访客（无账号） |
| 4 | 员工 |

---

## 七、关键字段跨表对应关系

| 业务场景 | 关联字段 |
|---------|---------|
| 客户 ↔ 会员 | `vdm_t_consumer.code` = `vdm_t_member.consumer_code` |
| 会员 ↔ 积分账户 | `vdm_t_member.card_no` = `vdm_t_points_account.member_code` |
| 订单 ↔ 客户 | `vdm_t_order.customer_code` = `vdm_t_consumer.code` |
| 订单 ↔ 积分流水 | `vdm_t_points_record.order_code` = `vdm_t_order.code` |
| 优惠券 ↔ 规则 | `vdm_t_coupon.coupon_rule_code` = `vdm_t_coupon_rule.code` |
| 优惠券 ↔ 活动 | `vdm_t_coupon.activity_code` = `vdm_t_activity.code` |
| 消息 ↔ 活动 | `vdm_t_message_record.activity_code` = `vdm_t_activity.code` |
| 客群成员 ↔ 客户 | `t_customer_group_detail.customer_code` = `vdm_t_consumer.code` |
| 分析层 ↔ 源数据 | `das_demoen.dim_customer_info.customer_code` = `dts_demoen.vdm_t_consumer.code` |
