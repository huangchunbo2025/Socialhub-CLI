# Emarsys BigQuery → StarRocks 字段映射手册 v2

> 最后更新：2026-04-03
> BQ 字段来源：`docs/emarsys-integration/bigquery-scheme-2.md`
> 目标库：`dts_test`（DTS 表）/ `datanow_test`（t_retailevent）

---

## 全局映射规则

| BigQuery 字段 | StarRocks 字段 | 路径 | 说明 |
|---|---|---|---|
| `customer_id` | `tenant_id` | DTS | Emarsys 账号 ID → 租户 ID |
| `contact_id` | `consumer_code` | DTS | 联系人 ID → 客户编码 |
| `contact_id` | `text1` | DataNow | 联系人 ID → 槽位 |

### DTS id 生成规则（sort key）

| 目标表 | id 生成方式 |
|---|---|
| `vdm_t_message_record` | hash(contact_id \|\| message_id \|\| event_time) |
| `vdm_t_activity` | hash(campaign_id \|\| event_time) |
| `vdm_t_points_account` | hash(contact_id \|\| plan_id) |
| `vdm_t_product` | hash(item_id) |

### DataNow t_retailevent 公共字段

每张表的 DataNow 映射表均须完整列出，不得省略：

| t_retailevent 字段 | 来源 | 说明 |
|---|---|---|
| `event_key` | 每表固定常量 | 如 `$emarsys_email_send` |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | 按业务确认 | 实际事件发生时间，逐表判断 |
| `customer_code` | config `account_id` | 配置层传入，非 BQ 字段 |

### DataNow 槽位规则

| 槽位 | 适用类型 |
|---|---|
| `text1–30` | 长字符串：contact_id、url、user_agent、uid 等 |
| `dimension1–25` | 枚举/分类短字符串：campaign_type、platform、bounce_type 等 |
| `bigint1–15` | 整数 ID：campaign_id、message_id、launch_id 等 |
| `decimal1–5` | 小数：balance、points |
| `datetime1–5` | 时间戳 |
| `date1–5` | 日期 |
| `context` | JSON / 嵌套 RECORD |

---

## Email 数据视图

### 1. email_campaigns

> 已废弃，不同步。

---

### 2. email_campaigns_v2

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `event_time` | `create_time` | 活动创建/修改时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| `is_recurring` | `marketing_type` | false→0（单次），true→1（周期性） |
| *(固定值 "email")* | `activity_channel` | 邮件渠道 |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`campaign_type`、`category_name`、`defined_type`、`language`、`origin_campaign_id`、`program_id`、`program_version_id`、`status`、`subject`、`suite_event`、`suite_type`、`timezone`、`version_name`

---

### 3. email_campaign_categories

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS**：无（纯活动分类配置，无业务事件语义）

---

### 4. email_sends

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 5 发送）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| `customer_id` | `tenant_id` | 全局规则 |
| `event_time` | `send_time` | 发送时间，NOT NULL |
| `loaded_at` | `create_time` | 记录创建时间，NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | 邮箱域名 |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值 2)* | `template_type` | 邮件渠道 |
| *(固定值 5)* | `status` | 5=发送 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time) |

**丢弃**：`launch_id`（vdm_t_message_record 无对应字段）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 5. email_opens

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 6 打开）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | |
| `customer_id` | `tenant_id` | |
| `event_time` | `send_time` | 打开时间，NOT NULL |
| `email_sent_at` | `create_time` | 原始发送时间，NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值 2)* | `template_type` | 邮件 |
| *(固定值 6)* | `status` | 6=打开 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time) |

**丢弃**：`geo.*`（进 context）、`ip`、`is_anonymized`（已废弃）、`is_mobile`、`launch_id`、`md5`、`platform`、`uid`、`user_agent`、`generated_from`

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_open` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 打开时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `ip` | 设备 IP |
| `text3` | `md5` | user_agent MD5 |
| `text4` | `uid` | 联系人随机标识符 |
| `text5` | `user_agent` | 设备浏览器信息 |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `dimension3` | `generated_from` | 无打开信息标记 |
| `dimension4` | `geo_country_iso_code` | 国家代码 |
| `dimension5` | `platform` | 设备平台枚举 |
| `dimension6` | `is_mobile` | boolean→"true"/"false" |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `email_sent_at` | 原始发送时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |
| `context` | `geo`（JSON） | 嵌套地理信息子字段 |

**丢弃**：`is_anonymized`（已废弃）

---

### 6. email_clicks

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 7 点击）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| `customer_id` | `tenant_id` | 全局规则 |
| `event_time` | `send_time` | 点击时间，NOT NULL |
| `email_sent_at` | `create_time` | 原始发送时间，NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | 邮箱域名 |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值 2)* | `template_type` | 邮件渠道 |
| *(固定值 7)* | `status` | 7=点击 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time) |

**丢弃**：`category_id`、`category_name`、`geo.*`（进 context）、`ip`、`is_anonymized`（废弃）、`is_img`、`is_mobile`、`launch_id`、`link_id`、`link_name`、`md5`、`platform`、`section_id`、`uid`、`user_agent`

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_click` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 点击时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `ip` | 设备 IP |
| `text3` | `md5` | user_agent MD5 |
| `text4` | `uid` | 联系人随机标识符 |
| `text5` | `user_agent` | 设备浏览器信息 |
| `text6` | `link_name` | 链接名称 |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `dimension3` | `platform` | 设备平台枚举 |
| `dimension4` | `is_mobile` | boolean→"true"/"false" |
| `dimension5` | `is_img` | 是否图片点击，boolean→"true"/"false" |
| `dimension6` | `geo_country_iso_code` | 国家代码 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `bigint4` | `link_id` | 链接 ID |
| `bigint5` | `category_id` | 链接分类 ID |
| `datetime1` | `email_sent_at` | 原始发送时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |
| `context` | `geo`（JSON） | 嵌套地理信息子字段 |

**丢弃**：`is_anonymized`（废弃）、`section_id`（旧版 VCMS）、`category_name`

---

### 7. email_bounces

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 8 退回）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| `customer_id` | `tenant_id` | 全局规则 |
| `event_time` | `send_time` | 退回时间，NOT NULL |
| `email_sent_at` | `create_time` | 原始发送时间，NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | 邮箱域名 |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值 2)* | `template_type` | 邮件渠道 |
| *(固定值 8)* | `status` | 8=退回 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time) |

**丢弃**：`bounce_type`（进 DataNow）、`dsn_reason`（进 DataNow）、`launch_id`

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_bounce` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 退回时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `dsn_reason` | SMTP 退回响应码（长字符串） |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `dimension3` | `bounce_type` | 枚举：block / soft / hard |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `email_sent_at` | 原始发送时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |

---

### 8. email_cancels

**contact_id**：✅

**Sink 1 — DTS**：无（vdm_t_message_record 无对应 status 枚举值）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_cancel` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 取消时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `reason` | 取消原因枚举 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 9. email_complaints

**contact_id**：✅

**Sink 1 — DTS**：无（vdm_t_message_record 无投诉对应 status 枚举值）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_complaint` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 投诉时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `email_sent_at` | 原始发送时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |

---

### 10. email_unsubscribes

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 9 退订）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| `customer_id` | `tenant_id` | 全局规则 |
| `event_time` | `send_time` | 退订时间，NOT NULL |
| `email_sent_at` | `create_time` | 原始发送时间，NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | 邮箱域名 |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值 2)* | `template_type` | 邮件渠道 |
| *(固定值 9)* | `status` | 9=退订 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time) |

**丢弃**：`launch_id`、`source`（进 DataNow）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_email_unsubscribe` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 退订时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `campaign_type` | 枚举：batch / transactional |
| `dimension2` | `domain` | 邮箱域名 |
| `dimension3` | `source` | 退订来源枚举 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `message_id` | 邮件 ID |
| `bigint3` | `launch_id` | 批次 ID |
| `datetime1` | `email_sent_at` | 原始发送时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |

---

### 11. contents

**contact_id**：❌，数据 60 天 TTL → 不同步

**Sink 1 — DTS**：无
**Sink 2 — DataNow**：无

---

## Web Push 数据视图

### 12. web_push_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `created_at` | `create_time` | 活动创建时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| *(固定值 "web_push")* | `activity_channel` | Web Push 渠道 |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`internal_campaign_id`、`source.*`、`message.*`、`domain_code`、`domain`、`settings.*`、`segment_id`、`recipient_source_id`、`data`、`launched_at`、`scheduled_at`、`deleted_at`、`event_time`、`action_buttons.*`、`sending_limit.*`、`recipient_source_type`、`status`

---

### 13. web_push_sends

**contact_id**：✅

**Sink 1 — DTS**：无（DTS 无 Web Push 对应表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_web_push_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `push_token` | 推送令牌 |
| `text3` | `client_id` | 客户端标识符 |
| `dimension1` | `platform` | 浏览器平台枚举 |
| `dimension2` | `domain` | 域名 |
| `dimension3` | `domain_code` | 域唯一代码 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 14. web_push_not_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_web_push_not_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送失败时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `push_token` | 推送令牌 |
| `text3` | `client_id` | 客户端标识符 |
| `dimension1` | `platform` | 浏览器平台枚举 |
| `dimension2` | `domain` | 域名 |
| `dimension3` | `domain_code` | 域唯一代码 |
| `dimension4` | `error.reason` | 错误原因枚举 |
| `dimension5` | `error.code` | HTTP 错误码 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 15. web_push_clicks

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_web_push_click` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 点击时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `client_id` | 客户端标识符 |
| `text3` | `sdk_version` | SDK 版本 |
| `dimension1` | `platform` | 浏览器平台枚举 |
| `dimension2` | `domain` | 域名 |
| `dimension3` | `domain_code` | 域唯一代码 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 16. web_push_custom_events

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_web_push_custom_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件触发时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `client_id` | 客户端标识符 |
| `text3` | `sdk_version` | SDK 版本 |
| `dimension1` | `platform` | 浏览器平台枚举 |
| `dimension2` | `domain` | 域名 |
| `dimension3` | `domain_code` | 域唯一代码 |
| `dimension4` | `event_name` | 自定义事件名称 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `event_attributes`（JSON） | 自定义事件属性 k/v |

---

## Mobile Engage 数据视图

### 17. push_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `created_at` | `create_time` | 活动创建时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| *(固定值 "push")* | `activity_channel` | Mobile Push 渠道 |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`android_settings.*`、`application_id`、`data`、`deleted_at`、`event_time`、`ios_settings.*`、`launched_at`、`message.*`、`push_internal_campaign_id`、`scheduled_at`、`segment_id`、`recipient_source_id`、`source`、`recipient_source_type`、`status`、`target`、`title.*`、`sending_limit`、`created_with`

---

### 18. push_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_push_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `push_token` | 设备推送令牌 |
| `text3` | `hardware_id` | SDK 实例唯一 ID |
| `text4` | `application_code` | 应用唯一代码 |
| `dimension1` | `platform` | 平台枚举：Android / iOS |
| `dimension2` | `target` | 消息目标枚举 |
| `dimension3` | `source.type` | 来源类型枚举：ac / ui |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `application_id` | 应用 ID |
| `bigint3` | `program_id` | 关联程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 19. push_not_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_push_not_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送失败时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `push_token` | 设备推送令牌 |
| `text3` | `hardware_id` | SDK 实例唯一 ID |
| `text4` | `application_code` | 应用唯一代码 |
| `dimension1` | `platform` | 平台枚举：Android / iOS |
| `dimension2` | `reason` | 未发送原因枚举 |
| `dimension3` | `source.type` | 来源类型枚举：ac / ui |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `application_id` | 应用 ID |
| `bigint3` | `program_id` | 关联程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 20. push_opens

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_push_open` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 打开时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `hardware_id` | SDK 实例唯一 ID |
| `text3` | `application_code` | 应用唯一代码 |
| `dimension1` | `source` | 消息显示位置枚举 |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `application_id` | 应用 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 21. push_custom_events

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_push_custom_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件发生时间 |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `hardware_id` | SDK 实例唯一 ID |
| `text3` | `application_code` | 应用唯一代码 |
| `dimension1` | `event_name` | 自定义事件名称 |
| `bigint1` | `application_id` | 应用 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `event_attributes`（JSON） | 自定义事件属性 k/v |

---

### 22. inapp_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `event_time` | `create_time` | 活动最后更新时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| *(固定值 "inapp")* | `activity_channel` | In-app 渠道 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`status`、`source`、`application_code`

> 注：inapp_campaigns 无 customer_id 字段，tenant_id 暂无来源。

---

### 23. inapp_views

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inapp_view` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 曝光时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `client_id` | SDK 实例标识符 |
| `text3` | `application_code` | 应用唯一代码 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `audience_change.treatments`（JSON） | 受众变更处理记录 |

---

### 24. inapp_clicks



**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inapp_click` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 点击时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `client_id` | SDK 实例标识符 |
| `text3` | `application_code` | 应用唯一代码 |
| `dimension1` | `button.button_id` | 被按下的按钮 ID |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `audience_change.treatments`（JSON） | 受众变更处理记录 |

---

### 25. inapp_audience_changes

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inapp_audience_change` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 受众变更时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `client_id` | SDK 实例标识符 |
| `text3` | `application_code` | 应用唯一代码 |
| `dimension1` | `change_type` | 枚举：添加 / 移除 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatment`（JSON） | 处理记录 |

---

### 26. inbox_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inbox_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 设备获取活动时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `application_code` | 应用唯一代码 |
| `dimension1` | `platform` | 平台枚举：Android / iOS |
| `dimension2` | `source.type` | 来源类型枚举：ac / ui |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 27. inbox_not_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inbox_not_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送失败时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `application_code` | 应用唯一代码 |
| `dimension1` | `platform` | 平台枚举：Android / iOS |
| `dimension2` | `reason` | 未发送原因枚举 |
| `dimension3` | `source.type` | 来源类型枚举：ac / ui |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 28. inbox_tag_changes

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_inbox_tag_change` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 标签更新时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `application_code` | 应用唯一代码 |
| `dimension1` | `platform` | 平台枚举：Android / iOS |
| `dimension2` | `tag.operation` | 枚举：添加 / 移除 |
| `dimension3` | `tag.name` | 标签名称枚举：high / cancelled / seen / opened / pinned / deleted |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 29. inbox_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| *(固定值 "inbox")* | `activity_channel` | Mobile Inbox 渠道 |
| *(生成值)* | `id` | hash(campaign_id) |

> 注：BQ 无 event_time / loaded_at / customer_id，create_time / update_time / tenant_id 暂无来源。

**丢弃**：`status`、`source`、`recipient_source_type`、`title.*`、`message.*`、`segment_id`、`recipient_source_id`、`data.*`、`target`、`collapse_id`、`settings.*`、`action_buttons.*`

---

### 30. client_snapshots

**contact_id**：❌（字段为 identified_contact_id / anonymous_contact_id，非标准 contact_id）→ 不写 DataNow

**Sink 1 — DTS**：无（设备状态快照，非业务事件）

---

### 31. client_updates

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS**：无（设备更新记录，无联系人事件语义）

---

## Mobile Wallet 数据视图

### 32. wallet_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `created_at` | `create_time` | 活动创建时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| *(固定值 "wallet")* | `activity_channel` | Mobile Wallet 渠道 |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`internal_campaign_id`、`wallet_config_id`、`status`、`template_type`、`updated_at`、`archived_at`、`launched_at`、`event_time`

---

### 33. wallet_passes

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_wallet_pass` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件发生时间 |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `serial_number` | Wallet pass 唯一 ID（UUID） |
| `text3` | `campaign_id` | Wallet 活动唯一 ID（UUID） |
| `dimension1` | `platform` | 枚举：Apple / Google |
| `dimension2` | `template_type` | 枚举：Loyalty / voucher / coupon |
| `dimension3` | `event` | 枚举：pass_generated / pass_downloaded / pass_updated / pass_removed |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

## SMS 数据视图

### 34. sms_campaigns

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_activity`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `event_time` | `create_time` | 活动创建/修改时间，NOT NULL |
| `loaded_at` | `update_time` | 数据更新时间 |
| *(固定值 "sms")* | `activity_channel` | SMS 渠道 |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time) |

**丢弃**：`sender_name`、`message`、`include_unsubscribe_link`、`trigger_type`、`business_unit`

---

### 35. sms_send_reports

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_sms_send_report` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | SMS 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息唯一 ID |
| `dimension1` | `status` | SMS 提供商发送状态枚举 |
| `dimension2` | `bounce_type` | 退回原因枚举 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 36. sms_sends

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_sms_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | SMS 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息唯一 ID |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `launch_id` | launch 唯一 ID |
| `bigint3` | `program_id` | 程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `treatments`（JSON） | 活动来源处理记录 |

---

### 37. sms_clicks

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_sms_click` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 点击时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_agent` | 用户代理信息 |
| `dimension1` | `is_dry_run` | 是否测试 URL，boolean→"true"/"false" |
| `bigint1` | `campaign_id` | 活动 ID |
| `bigint2` | `launch_id` | launch 唯一 ID |
| `bigint3` | `link_id` | 链接 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 38. sms_unsubscribes

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_sms_unsubscribe` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 退订时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `unsubscribe_type` | 退订类型枚举 |
| `bigint1` | `campaign_id` | 活动 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

## Web Channel 数据视图

### 39. webchannel_events_enhanced

**contact_id**：✅

> 注：BQ 字段 `event_type`（值为 show/submit/click）与 t_retailevent 公共字段同名，写入 dimension1，不覆盖公共字段。

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_webchannel_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_agent` | 设备浏览器信息 |
| `text3` | `md5` | user_agent MD5 |
| `text4` | `campaign_id` | 活动唯一 ID（string） |
| `text5` | `ad_id` | 活动版本 ID（string） |
| `dimension1` | `event_type`（BQ） | 枚举：show / submit / click |
| `dimension2` | `platform` | 设备平台枚举 |
| `dimension3` | `is_mobile` | boolean→"true"/"false" |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

**丢弃**：`is_anonymized`（废弃）

---

## Predict 数据视图

### 40. session_categories

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_session_category` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 浏览分类时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_id` | Predict 用户 ID |
| `dimension1` | `category` | 浏览分类名称 |
| `dimension2` | `user_id_type` | 用户 ID 类型枚举 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

**丢弃**：`user_id_field_id`

---

### 41. session_purchases

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_session_purchase` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 购买时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_id` | Predict 用户 ID |
| `text3` | `order_id` | 订单唯一 ID |
| `dimension1` | `user_id_type` | 用户 ID 类型枚举 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `items`（JSON） | 购买商品列表（item_id/price/quantity） |

**丢弃**：`user_id_field_id`

---

### 42. session_tags

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_session_tag` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件发生时间 |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_id` | Predict 用户 ID |
| `dimension1` | `tag` | 事件类型标签（网站自定义枚举） |
| `dimension2` | `user_id_type` | 用户 ID 类型枚举 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `attributes`（JSON） | 事件属性（name/string_value/number_value/boolean_value） |

**丢弃**：`user_id_field_id`

---

### 43. session_views

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_session_view` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 浏览商品时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_id` | Predict 用户 ID |
| `text3` | `item_id` | 浏览商品唯一 ID |
| `dimension1` | `user_id_type` | 用户 ID 类型枚举 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

**丢弃**：`user_id_field_id`

---

### 44. sessions

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_session` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `start_time` | 会话开始时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `user_id` | Predict 用户 ID |
| `dimension1` | `user_id_type` | 用户 ID 类型枚举 |
| `dimension2` | `currency` | 购买货币枚举 |
| `datetime1` | `start_time` | 会话开始时间 |
| `datetime2` | `end_time` | 会话结束时间 |
| `datetime3` | `loaded_at` | 数据平台加载时间 |
| `context` | `purchases` / `views` / `tags` / `categories` / `last_cart`（JSON） | 全部嵌套子记录 |

**丢弃**：`user_id_field_id`

---

## Event 数据视图

### 45. external_events

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_external_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件发生时间 |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `event_id` | 平台生成的事件唯一标识符 |
| `bigint1` | `event_type_id` | 外部事件类型 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 46. custom_events

**contact_id**：✅

> 注：BQ 字段 `event_type`（boolean）与 t_retailevent 公共字段同名，写入 dimension1，不覆盖公共字段。

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_custom_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件发生时间 |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `event_id` | 事件唯一 ID |
| `dimension1` | `event_type`（BQ） | boolean→"true"/"false" |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

**丢弃**：`partitiontime`（分区字段）

---

## Automation 数据视图

### 47. automation_node_executions

**contact_id**：❌（participants.contact_id 为嵌套字段，批量执行时为 NULL）→ 不写 DataNow

**Sink 1 — DTS**：无

---

## Loyalty 数据视图

### 48. loyalty_contact_points_state_latest

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 100 会员积分状态）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| *(TBD)* | `tenant_id` | 暂无 customer_id 来源 |
| `event_time` | `send_time` | 状态快照时间，NOT NULL |
| `loaded_at` | `create_time` | 数据更新时间，NOT NULL |
| *(固定值 100)* | `status` | 100=会员积分状态 |
| *(生成值)* | `id` | hash(contact_id \|\| event_time) |

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_points_state` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 状态快照时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `dimension1` | `tier_name` | 会员等级名称 |
| `dimension2` | `currency_code` | 积分币种 |
| `bigint1` | `total_points` | 总积分（整数） |
| `bigint2` | `available_points` | 可用积分 |
| `bigint3` | `pending_points` | 待发放积分 |
| `bigint4` | `spent_points` | 已消费积分 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 49. loyalty_points_earned_redeemed

**contact_id**：✅

**Sink 1 — DTS → `dts_test.vdm_t_message_record`**（status = 101 积分收支明细）

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| *(TBD)* | `tenant_id` | 暂无 customer_id 来源 |
| `event_time` | `send_time` | 积分变动时间，NOT NULL |
| `loaded_at` | `create_time` | 数据更新时间，NOT NULL |
| *(固定值 101)* | `status` | 101=积分收支明细 |
| *(生成值)* | `id` | hash(contact_id \|\| event_time) |

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_points_transaction` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 积分变动时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `transaction_id` | 事务唯一 ID |
| `text3` | `source.type_name` | 积分来源（原始类型名称） |
| `dimension1` | `type` | 枚举：earned / redeemed |
| `dimension2` | `source.type` | 枚举：expiration / imported / manual / optin / purchase / refund / registration / voucher |
| `dimension3` | `source.expiration_date` | 积分有效期日期 |
| `dimension4` | `external_source.code` | 外部源代码 |
| `dimension5` | `source.category_name` | 来源分类名称 |
| `bigint1` | `amount` | 积分变动数量 |
| `bigint2` | `balance` | 变动后余额 |
| `bigint3` | `total_points` | 变动时总积分（latest state 快照） |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `labels`（JSON） | 积分标签列表 |

---

### 51. loyalty_vouchers

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_voucher` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 券状态变更时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `voucher_code` | 券唯一代码 |
| `text3` | `voucher_id` | 券 ID |
| `dimension1` | `type` | 枚举：single / combined |
| `dimension2` | `status` | 枚举：active / used / expired / inactive |
| `bigint1` | `amount` | 券金额 |
| `bigint2` | `redeemable_points` | 兑换所需积分 |
| `date1` | `valid_from` | 有效期起始日期 |
| `date2` | `valid_to` | 有效期截止日期 |
| `datetime1` | `used_at` | 使用时间 |
| `datetime2` | `loaded_at` | 数据平台加载时间 |

---

### 52. loyalty_exclusive_access

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_exclusive_access` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 专属权益变更时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `item_id` | 专属权益项唯一 ID |
| `dimension1` | `status` | 枚举：active / inactive |
| `date1` | `valid_from` | 有效期起始日期 |
| `date2` | `valid_to` | 有效期截止日期 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 53. loyalty_actions

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_action` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 动作触发时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `action_id` | 动作唯一 ID |
| `dimension1` | `status` | 枚举：active / inactive / deleted |
| `dimension2` | `type` | 动作类型枚举 |
| `bigint1` | `points` | 动作积分值 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 54. loyalty_referral_codes

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_referral_code` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 推荐码创建/更新时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID（推荐人） |
| `text2` | `referral_code` | 推荐码 |
| `dimension1` | `status` | 枚举：active / inactive |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 55. loyalty_referral_purchases

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_loyalty_referral_purchase` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 推荐购买时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID（被推荐人） |
| `text2` | `referral_code` | 使用的推荐码 |
| `dimension1` | `status` | 枚举：pending / approved / declined |
| `bigint1` | `purchase_value` | 购买金额 |
| `bigint2` | `reward_points` | 奖励积分 |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

---

## Analytics 数据视图

### 56. revenue_attribution

**contact_id**：✅

**Sink 1 — DTS**：无（归因分析数据，无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_revenue_attribution` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 购买时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `order_id` | 订单唯一 ID |
| `bigint1` | `items.item_id` | 商品 ID（如有多个取第一个或拼接） |
| `decimal1` | `items.price` | 商品销售价格 |
| `decimal2` | `items.quantity` | 商品数量 |
| `context` | `treatments`（JSON） | 归因处理记录（含 campaign_id/channel/attributed_amount 等） |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 57. si_contacts

**contact_id**：✅

**Sink 1 — DTS**：无（Smart Insight 分析数据，无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_si_contact` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `load_date` | 数据加载时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | Suite 联系人 ID |
| `text2` | `si_contact_id` | Smart Insight 联系人 ID |
| `text3` | `contact_external_id` | 客户系统联系人标识符 |
| `dimension1` | `contact_source` | 联系人来源枚举 |
| `dimension2` | `customer_lifecycle_status` | 生命周期状态：Lead/First time buyer/Active/Defecting/Inactive |
| `dimension3` | `buyer_status` | 买家状态 |
| `dimension4` | `lead_lifecycle_status` | 潜在客户状态：New Lead/Cold Lead/Inactive Lead |
| `dimension5` | `is_generated` | boolean→"true"/"false" |
| `bigint1` | `number_of_purchases` | 购买次数 |
| `decimal1` | `turnover` | 终身消费总额 |
| `decimal2` | `average_order_value` | 订单平均价值 |
| `decimal3` | `average_future_spend` | 预测未来消费 |
| `date1` | `registered_on` | 注册日期 |
| `date2` | `last_order_date` | 最后下单日期 |
| `date3` | `last_engagement_date` | 最后互动日期 |
| `date4` | `last_response_date` | 最后响应日期 |
| `datetime1` | `load_date` | 数据加载时间 |

---

### 58. si_purchases

**contact_id**：❌（只有 si_contact_id，无标准 contact_id）→ 不写 DataNow

**Sink 1 — DTS**：无

**Sink 2 — DataNow**：无

---

---

### 59. conversation_opens

**contact_id**：✅

**Sink 1 — DTS**：无

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_conversation_open` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 打开时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息 ID |
| `text3` | `conversation_id` | 对话标识符 |
| `dimension1` | `program_type` | 程序类型枚举：Audience-based / Event-based |
| `bigint1` | `program_id` | Automation 程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 60. conversation_deliveries

**contact_id**：✅

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_conversation_delivery` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 投递时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息 ID |
| `text3` | `conversation_id` | 对话标识符 |
| `text4` | `error_message` | 投递失败错误描述（长字符串） |
| `dimension1` | `status` | 投递状态枚举：DELIVERED / FAILED |
| `dimension2` | `error_type` | 错误类型枚举：INVALID_LINK / ACCOUNT_ISSUE / TEMPLATE_ISSUE |
| `dimension3` | `program_type` | 程序类型枚举：Audience-based / Event-based |
| `bigint1` | `program_id` | Automation 程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 61. conversation_clicks

**contact_id**：✅

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_conversation_click` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 点击时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息 ID |
| `text3` | `conversation_id` | 对话标识符 |
| `text4` | `user_agent` | 用户代理信息 |
| `dimension1` | `program_type` | 程序类型枚举：Audience-based / Event-based |
| `bigint1` | `program_id` | Automation 程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 62. conversation_sends

**contact_id**：✅

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_conversation_send` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 发送时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `message_id` | 消息 ID |
| `text3` | `conversation_id` | 对话标识符 |
| `dimension1` | `program_type` | 程序类型枚举：Audience-based / Event-based |
| `bigint1` | `program_id` | Automation 程序 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |

---

### 63. conversation_messages

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow**：无

---

---

### 64. reporting_email

**contact_id**：❌（聚合报告数据，无单联系人维度）→ 不写 DataNow

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow**：无

---

## Engagement Events 数据视图

### 65. engagement_events

**contact_id**：✅

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow → `t_retailevent`**

| t_retailevent 字段 | BQ 字段 / 来源 | 说明 |
|---|---|---|
| `event_key` | `$emarsys_engagement_event` | 固定值 |
| `event_type` | `"trace"` | 固定值 |
| `event_time` | `event_time` | 事件摄入时间（事件发生时间） |
| `customer_code` | config `account_id` | 配置层传入 |
| `text1` | `contact_id` | 联系人 ID |
| `text2` | `event_id` | 事件唯一 ID |
| `text3` | `event_type` | 事件类型 ID |
| `bigint1` | `customer_id` | 账号唯一 ID |
| `datetime1` | `loaded_at` | 数据平台加载时间 |
| `context` | `event_data`（JSON） | 事件 JSON payload |

---

## Product Catalog 数据视图

### 66. products_latest_state

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS → `dts_test.vdm_t_product`**

| BQ 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `item_id` | `code` | 产品唯一标识 |
| `title.default` | `name` | 产品名称 |
| `category.default` | `category` | 产品分类 |
| `price.default` | `price` | 产品价格 |
| `currency.default` | `currency` | 价格币种 |
| `brand.default` | `brand` | 品牌 |
| `link.default` | `url` | 产品链接 |
| `image.default` | `image_url` | 产品图片链接 |
| `description.default` | `description` | 产品描述 |
| `availability.default` | `status` | 可用状态枚举 |
| `event_time` | `update_time` | 更新时间，NOT NULL |
| `customer_id` | `tenant_id` | 全局规则 |
| *(生成值)* | `id` | hash(item_id) |

**丢弃**：其余 locals 多语言字段、zoom_image、msrp、pause、customs、available 等

**Sink 2 — DataNow**：无

---

### 67. products_change_history

**contact_id**：❌ → 不写 DataNow

**Sink 1 — DTS**：无（无对应业务表）

**Sink 2 — DataNow**：无

---

*文档完成 - 共 66 张表映射*