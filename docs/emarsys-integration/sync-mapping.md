# Emarsys BigQuery → StarRocks 字段映射手册

> 状态：讨论中，逐表确认
> 凭证来源：`mcp_server.tenant_bigquery_credentials`（Fernet 解密）

---

## 全局映射规则

| BigQuery 字段 | StarRocks 字段 | 说明 |
|---|---|---|
| `customer_id` | `tenant_id` | Emarsys 账号ID → 我方租户ID（如 `uat`） |
| `contact_id` | `consumer_code` | Emarsys 联系人ID → 客户编码 |

### Sort Key 生成规则

各目标表均有 `id`（bigint, NOT NULL, sort key），BigQuery 无来源，统一用以下规则生成：

| 目标表 | `id` 生成方式 |
|---|---|
| `vdm_t_message_record` | `hash(contact_id \|\| message_id \|\| event_time)` 取正整数 |
| `vdm_t_activity` | `hash(campaign_id \|\| event_time)` 取正整数 |
| `vdm_t_points_account` | `hash(contact_id \|\| plan_id)` 取正整数 |
| `vdm_t_product` | `hash(item_id)` 取正整数 |

---

## email_sends_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | sort key NOT NULL |
| `loaded_at` | `create_time` | NOT NULL |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `launch_id` | *(丢弃)* | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1（营销类），transactional→0（事件类） |
| *(固定值)* | `template_type` | = 2（邮件） |
| *(固定值)* | `status` | = 5（发送成功） |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

---

## email_opens_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 打开时间 |
| `email_sent_at` | `create_time` | 原始发送时间 |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `launch_id` | *(丢弃)* | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值)* | `template_type` | = 2（邮件） |
| *(固定值)* | `operate_status` | = 1（打开） |
| `is_mobile` / `platform` / `ip` / `user_agent` / `uid` / `geo_*` / `md5` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

## email_clicks_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 点击时间 |
| `email_sent_at` | `create_time` | 原始发送时间 |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值)* | `template_type` | = 2（邮件） |
| *(固定值)* | `operate_status` | = 2（点击） |
| `launch_id` / `link_id` / `link_name` / `category_*` / `is_mobile` / `platform` / `ip` / `user_agent` / `uid` / `geo_*` / `md5` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

## email_bounces_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 退回时间 |
| `email_sent_at` | `create_time` | 原始发送时间 |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值)* | `template_type` | = 2（邮件） |
| *(固定值)* | `operate_status` | = 3（退信） |
| `launch_id` / `bounce_type` / `dsn_reason` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

## email_unsubscribes_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 退订时间 |
| `email_sent_at` | `create_time` | 原始发送时间 |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| `domain` | `receiver` | |
| `campaign_type` | `business_type` | batch→1，transactional→0 |
| *(固定值)* | `template_type` | = 2（邮件） |
| *(固定值)* | `operate_status` | = 4（退订） |
| `launch_id` / `source` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

## email_cancels_{cid} → *(跳过，不同步)*

> 原因：目标表 `vdm_t_message_record` 无对应的"取消发送"状态枚举值。

## email_complaints_{cid} → *(跳过，不同步)*

> 原因：目标表 `vdm_t_message_record` 无对应的"投诉/标记垃圾邮件"状态枚举值。

## email_campaigns_v2_{cid} → dts_{tenant_id}.vdm_t_activity

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `event_time` | `create_time` | 创建/修改时间 |
| `is_recurring` | `marketing_type` | false→0（单次），true→1（周期） |
| `status` | `status` | draft/paused→0，scheduled/running→1，done/archived→2 |
| 其余字段 | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time)，sort key |

## sms_sends_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 发送时间 |
| `loaded_at` | `create_time` | |
| `message_id` | `message_id` | |
| `campaign_id` | `activity_code` | |
| *(固定值)* | `template_type` | = 0（国内短信） |
| *(固定值)* | `status` | = 5（发送成功） |
| `launch_id` / `program_id` / `treatments.*` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| message_id \|\| event_time)，sort key |

## sms_send_reports_{cid} → *(跳过，不同步)*

> 原因：`status` 为服务商返回的字符串，无法映射到我方枚举值。

## sms_clicks_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 点击时间 |
| `loaded_at` | `create_time` | |
| `campaign_id` | `activity_code` | |
| *(固定值)* | `template_type` | = 0（国内短信） |
| *(固定值)* | `operate_status` | = 2（点击） |
| `launch_id` / `link_id` / `is_dry_run` / `user_agent` | *(丢弃)* | 无对应字段 |
| *(生成值)* | `id` | hash(contact_id \|\| campaign_id \|\| event_time)，sort key |

## sms_unsubscribes_{cid} → dts_{tenant_id}.vdm_t_message_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `customer_id` | `tenant_id` | 全局规则 |
| `contact_id` | `consumer_code` | 全局规则 |
| `event_time` | `send_time` | 退订时间 |
| `loaded_at` | `create_time` | |
| `campaign_id` | `activity_code` | |
| *(固定值)* | `template_type` | = 0（国内短信） |
| *(固定值)* | `operate_status` | = 4（退订） |
| `unsubscribe_type` | *(丢弃)* | |
| *(生成值)* | `id` | hash(contact_id \|\| campaign_id \|\| event_time)，sort key |

## sms_campaigns_{cid} → dts_{tenant_id}.vdm_t_activity

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | 活动编码 |
| `name` | `name` | 活动名称 |
| `event_time` | `create_time` | |
| 其余字段 | *(丢弃)* | |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time)，sort key |

## web_push_campaigns_{cid} → dts_{tenant_id}.vdm_t_activity

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | |
| `name` | `name` | |
| `created_at` | `create_time` | |
| `launched_at` | `start_time` | |
| 其余字段 | *(丢弃)* | |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time)，sort key |

## push_campaigns_{cid} → dts_{tenant_id}.vdm_t_activity

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | |
| `name` | `name` | |
| `created_at` | `create_time` | |
| `launched_at` | `start_time` | |
| 其余字段 | *(丢弃)* | |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time)，sort key |

## wallet_campaigns_{cid} → dts_{tenant_id}.vdm_t_activity

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `campaign_id` | `code` | |
| `name` | `name` | |
| `created_at` | `create_time` | |
| `launched_at` | `start_time` | |
| `status` | `status` | IN_DRAFT→0，READY_TO_LAUNCH→1 |
| 其余字段 | *(丢弃)* | |
| *(生成值)* | `id` | hash(campaign_id \|\| event_time)，sort key |

## wallet_passes_{cid} → *(跳过，不同步)*

> 原因：`vdm_t_message_record.template_type` 无 Mobile Wallet 枚举值，pass 事件类型也无法映射到 `operate_status`。

## webchannel_events_enhanced_{cid} → *(跳过，不同步)*

> 原因：无对应 `template_type` 枚举值（Web Channel），且 show/submit 事件类型无法映射到 `operate_status`。

## session_categories_{cid} → *(dts_ 无对应表，待 t_retailevent 章节确认)*

## session_purchases_{cid} → *(dts_ 无对应表，待 t_retailevent 章节确认)*

## external_events_{cid} → *(dts_ 无对应表，待 t_retailevent 章节确认)*

## custom_events_{cid} → *(dts_ 无对应表，待 t_retailevent 章节确认)*

## automation_node_executions_{cid} → *(跳过，不同步)*

> 原因：Emarsys 内部自动化工作流执行状态，非消息/活动数据，`dts_*` 无对应业务表。

## loyalty_contact_points_state_latest_{cid} → dts_{tenant_id}.vdm_t_points_account

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `member_code` | 全局规则 |
| `balance_points` | `available_points` | 余额积分 |
| `pending_points` | `transit_points` | 待确认积分 |
| `points_to_be_expired` | `expired_points` | 即将过期积分 |
| `event_time` | `create_time` | |
| `external_id` / `plan_id` / `status_points` / `tier` / `tier_entry_time` / `join_time` | *(丢弃)* | 无对应字段 |
| *(无来源)* | `code` / `points_group_code` / `accumulative_points` / `used_points` | 留 NULL |
| *(生成值)* | `id` | hash(contact_id \|\| plan_id)，sort key |

## loyalty_points_earned_redeemed_{cid} → dts_{tenant_id}.vdm_t_points_record

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `contact_id` | `consumer_code` | 全局规则 |
| `contact_id` | `points_account_code` | 联系人ID作为积分账户编码 |
| `event_time` | `create_time` | |
| `abs(points)` | `points_value` | 取绝对值 |
| `points` 正负 | `direction` | 正→1（增），负→2（减） |
| *(生成值)* | `code` | `{contact_id}_{event_time}` 拼接 |
| `external_id` / `contact_state_id` / `loaded_at` / `points_type` | *(丢弃)* | |
| *(无来源)* | `operation_type` / `source` / `order_code` 等 | 留 NULL |

## revenue_attribution_{cid} → *(跳过，不同步)*

> 原因：仅含营销归因字段（order_id + items），缺少 vdm_t_order 必填字段（code、order_date、customer_code 等），无法有效写入。

## conversation_opens_{cid} → *(跳过，不同步)*

> 原因：对话渠道（WhatsApp 等）无对应 `template_type` 枚举值。

## conversation_deliveries_{cid} → *(跳过 dts_，仅同步 datanow)*

> 原因：无对应 `template_type` 枚举值，跳过 dts_ 写入；但有 `event_time` 和 `contact_id`，同步到 t_retailevent。

## engagement_events → *(dts_ 无对应表，待 t_retailevent 章节确认)*

## products_latest_state_{cid} → dts_{tenant_id}.vdm_t_product

| BigQuery 字段 | StarRocks 字段 | 备注 |
|---|---|---|
| `item_id` | `code` | 商品编码 |
| `title.default` | `name` | 默认语言标题 |
| `image.default` | `img` | 默认图片URL |
| `event_time` | `update_time` | timestamp→bigint epoch毫秒转换 |
| `item_group_id` / `link` / `pause` / `title.locals` / `image.locals` | *(丢弃)* | |
| *(无来源)* | `price` / `brand` 等 | 留 NULL |
| *(生成值)* | `id` | hash(item_id)，sort key |

---

# datanow_{tenant_id}.t_retailevent 映射

## 全局规则

### 固定 key 字段（所有表统一）

| t_retailevent 字段 | 来源 | 说明 |
|---|---|---|
| `event_type` | 固定 = `"trace"` | |
| `event_key` | 各表不同，见下方 | |
| `event_time` | `event_time` | |
| `customer_code` | `contact_id` | |
| `tenant_id` | TenantSyncConfig.tenant_id | 系统值，非 BQ 字段 |
| `event_id` | 各表不同，见下方 | |
| `update_time` | 写入时系统时间 | |

### event_key 列表

| BigQuery 表 | event_key |
|---|---|
| email_sends | `$emarsys_email_send` |
| email_opens | `$emarsys_email_open` |
| email_clicks | `$emarsys_email_click` |
| email_bounces | `$emarsys_email_bounce` |
| email_unsubscribes | `$emarsys_email_unsub` |
| email_cancels | `$emarsys_email_cancel` |
| email_complaints | `$emarsys_email_complaint` |
| sms_sends | `$emarsys_sms_send` |
| sms_clicks | `$emarsys_sms_click` |
| sms_unsubscribes | `$emarsys_sms_unsub` |
| wallet_passes | `$emarsys_wallet_pass` |
| webchannel_events_enhanced | `$emarsys_webchannel_event` |
| session_categories | `$emarsys_browse_category` |
| session_purchases | `$emarsys_purchase` |
| external_events | `$emarsys_external_event` |
| custom_events | `$emarsys_custom_event` |
| loyalty_points_earned_redeemed | `$emarsys_loyalty_points` |
| revenue_attribution | `$emarsys_revenue` |
| conversation_opens | `$emarsys_conversation_open` |
| conversation_deliveries | `$emarsys_conversation_delivery` |
| engagement_events | `$emarsys_engagement` |

### event_id 规则

| 表 | event_id 来源 |
|---|---|
| email_sends/opens/clicks/bounces/unsubscribes/cancels/complaints | `message_id` |
| sms_sends | `message_id` |
| sms_clicks / sms_unsubscribes | `hash(contact_id \|\| campaign_id \|\| event_time)` |
| external_events / custom_events / engagement_events | 原生 `event_id` |
| 其余 | `hash(contact_id \|\| event_time)` |

### slot 类型分配原则

| BigQuery 字段类型 | 目标 slot |
|---|---|
| integer / bigint | `bigint` slot |
| float / decimal | `decimal` slot |
| timestamp | `datetime` slot |
| string（短，枚举/编码类） | `dimension` slot |
| string（长，URL/UA/内容） | `text` slot |
| boolean | `bigint` slot（true=1，false=0） |
| record/array（嵌套） | `text` slot（JSON 序列化） |

---

## email_sends_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key，业务唯一ID |
| *(固定)* | `event_key` = `$emarsys_email_send` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | 活动ID |
| `launch_id` | `bigint2` | 批次ID |
| `loaded_at` | `datetime1` | 平台加载时间 |
| `campaign_type` | `dimension1` | batch/transactional |
| `domain` | `dimension2` | 收件人域名 |

## email_opens_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_open` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `is_mobile` | `bigint3` | 1/0 |
| `is_anonymized` | `bigint4` | 1/0 |
| `geo.accuracy_radius` | `bigint5` | 精度半径(km) |
| `geo.latitude` | `decimal1` | |
| `geo.longitude` | `decimal2` | |
| `email_sent_at` | `datetime1` | 原始发送时间 |
| `loaded_at` | `datetime2` | |
| `campaign_type` | `dimension1` | |
| `domain` | `dimension2` | |
| `platform` | `dimension3` | |
| `geo_country_iso_code` | `dimension4` | |
| `geo.city_name` | `dimension5` | |
| `geo.continent_code` | `dimension6` | |
| `geo.postal_code` | `dimension7` | |
| `geo.time_zone` | `dimension8` | |
| `generated_from` | `dimension9` | |
| `ip` | `text1` | |
| `user_agent` | `text2` | |
| `uid` | `text3` | |
| `md5` | `text4` | |

## email_clicks_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_click` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `link_id` | `bigint3` | |
| `category_id` | `bigint4` | |
| `section_id` | `bigint5` | |
| `is_mobile` | `bigint6` | 1/0 |
| `is_anonymized` | `bigint7` | 1/0 |
| `is_img` | `bigint8` | 1/0 |
| `geo.accuracy_radius` | `bigint9` | |
| `geo.latitude` | `decimal1` | |
| `geo.longitude` | `decimal2` | |
| `email_sent_at` | `datetime1` | |
| `loaded_at` | `datetime2` | |
| `campaign_type` | `dimension1` | |
| `domain` | `dimension2` | |
| `platform` | `dimension3` | |
| `geo_country_iso_code` | `dimension4` | |
| `geo.city_name` | `dimension5` | |
| `geo.continent_code` | `dimension6` | |
| `geo.postal_code` | `dimension7` | |
| `geo.time_zone` | `dimension8` | |
| `category_name` | `dimension9` | |
| `ip` | `text1` | |
| `user_agent` | `text2` | |
| `uid` | `text3` | |
| `md5` | `text4` | |
| `link_name` | `text5` | |

## email_bounces_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_bounce` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `email_sent_at` | `datetime1` | |
| `loaded_at` | `datetime2` | |
| `campaign_type` | `dimension1` | |
| `domain` | `dimension2` | |
| `bounce_type` | `dimension3` | block/soft/hard |
| `dsn_reason` | `text1` | SMTP 退回响应码 |

## email_unsubscribes_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_unsub` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `email_sent_at` | `datetime1` | |
| `loaded_at` | `datetime2` | |
| `campaign_type` | `dimension1` | |
| `domain` | `dimension2` | |
| `source` | `dimension3` | unsubscribe/list_unsubscribe/unsubscribe_from_campaign |

## email_cancels_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_cancel` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `loaded_at` | `datetime1` | |
| `campaign_type` | `dimension1` | |
| `reason` | `dimension2` | 取消原因枚举 |
| `suite_event` | `dimension3` | |
| `suite_type` | `dimension4` | |

## email_complaints_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_email_complaint` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `email_sent_at` | `datetime1` | |
| `loaded_at` | `datetime2` | |
| `campaign_type` | `dimension1` | |
| `domain` | `dimension2` | |

## sms_sends_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_sms_send` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `program_id` | `bigint3` | |
| `treatments.ac.id` | `bigint4` | 受众自动化程序ID |
| `loaded_at` | `datetime1` | |
| `treatments.rti.id` | `text1` | 事件触发程序ID |
| `treatments.rti.run_id` | `text2` | |
| `treatments.ac.run_id` | `text3` | |

## sms_clicks_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|campaign_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_sms_click` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `launch_id` | `bigint2` | |
| `link_id` | `bigint3` | |
| `is_dry_run` | `bigint4` | 1/0 |
| `loaded_at` | `datetime1` | |
| `user_agent` | `text1` | |

## sms_unsubscribes_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|campaign_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_sms_unsub` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `campaign_id` | `bigint1` | |
| `loaded_at` | `datetime1` | |
| `unsubscribe_type` | `dimension1` | |

## wallet_passes_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_wallet_pass` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `loaded_at` | `datetime1` | |
| `platform` | `dimension1` | |
| `template_type` | `dimension2` | |
| `event` | `dimension3` | pass 事件类型 |
| `campaign_id` | `text1` | UUID |
| `serial_number` | `text2` | 通行证序列号 |

## webchannel_events_enhanced_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_webchannel_event` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `is_mobile` | `bigint1` | 1/0 |
| `is_anonymized` | `bigint2` | 1/0 |
| `loaded_at` | `datetime1` | |
| `event_type` | `dimension1` | show/submit/click |
| `platform` | `dimension2` | |
| `ad_id` | `dimension3` | 活动版本ID |
| `campaign_id` | `text1` | |
| `user_agent` | `text2` | |
| `md5` | `text3` | |

## session_categories_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_browse_category` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `user_id_field_id` | `bigint1` | |
| `loaded_at` | `datetime1` | |
| `category` | `dimension1` | 浏览分类 |
| `user_id_type` | `dimension2` | email hash / external ID |
| `user_id` | `text1` | |

## session_purchases_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_purchase` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `user_id_field_id` | `bigint1` | |
| `loaded_at` | `datetime1` | |
| `user_id_type` | `dimension1` | |
| `user_id` | `text1` | |
| `items`（JSON） | `text2` | item_id/price/quantity 序列化 |

## external_events_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `event_id` | `event_id` | key，原生唯一ID |
| *(固定)* | `event_key` = `$emarsys_external_event` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `event_type_id` | `bigint1` | 外部事件类型ID |
| `loaded_at` | `datetime1` | |

## custom_events_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `event_id` | `event_id` | key，原生唯一ID |
| *(固定)* | `event_key` = `$emarsys_custom_event` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `loaded_at` | `datetime1` | |
| `partitiontime` | `datetime2` | 分区时间 |
| `event_type` | `dimension1` | 自定义事件类型 |

## loyalty_points_earned_redeemed_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_loyalty_points` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `points` | `decimal1` | 正=获取，负=兑换 |
| `loaded_at` | `datetime1` | |
| `points_type` | `dimension1` | Balance/Status |
| `external_id` | `text1` | 用户ID哈希 |
| `contact_state_id` | `text2` | 联系人状态内部标识 |

## revenue_attribution_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| hash(contact_id\|\|event_time) | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_revenue` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `order_id` | `bigint1` | 订单ID |
| `loaded_at` | `datetime1` | |
| `items`（JSON） | `text1` | item_id/price/quantity |
| `treatments`（JSON） | `text2` | campaign_id/channel/id/hardware_id |

## conversation_opens_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_conversation_open` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `message_id` | `bigint1` | |
| `conversation_id` | `bigint2` | |
| `loaded_at` | `datetime1` | |
| `program_type` | `dimension1` | |
| `program_id` | `text1` | |

## conversation_deliveries_{cid} → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key，投递时间（UTC） |
| `message_id` | `event_id` | key |
| *(固定)* | `event_key` = `$emarsys_conversation_delivery` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `message_id` | `bigint1` | |
| `conversation_id` | `bigint2` | |
| `status` | `dimension1` | DELIVERED/FAILED |
| `error_type` | `dimension2` | |
| `error_message` | `text1` | |

## engagement_events → datanow_{tenant_id}.t_retailevent

| BigQuery 字段 | t_retailevent 字段 | 说明 |
|---|---|---|
| `contact_id` | `customer_code` | key |
| `event_time` | `event_time` | key |
| `event_id` | `event_id` | key，原生唯一ID |
| *(固定)* | `event_key` = `$emarsys_engagement` | key |
| *(固定)* | `event_type` = `trace` | |
| *(系统)* | `tenant_id` | TenantSyncConfig |
| `loaded_at` | `datetime1` | |
| `partitiontime` | `datetime2` | 分区时间 |
| `event_type` | `dimension1` | 事件类型 |
| `event_data`（JSON） | `context` | 完整 payload |
