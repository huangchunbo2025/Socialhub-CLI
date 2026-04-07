# Emarsys Open Data - BigQuery 数据视图字段手册（v2）

> 来源：SAP Help Portal - Open Data Data Views（官方 PDF，`lib/bigquery_schema.pdf`，生成日期：2026-04-03）
> 官方文档：https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3

---

## 一、产品概述

**Open Data** 是 SAP Emarsys 提供的 Google Cloud Platform 插件，允许用户查询和导出账户中的全量数据，涵盖 Email、Web Push、SMS、Mobile App、Conversational、Product 等多个渠道，可对接 Tableau、Data Studio 等第三方 BI 工具。

---

## 二、命名规则

### GCP 项目名

| 创建时间 | 项目命名格式 |
|---------|-------------|
| 2021-04-30 之后（新项目） | `sap-od-<customer>` |
| 2021-04-30 之前（旧项目） | `ems-od-<customer>` |

> ⚠️ 若查询报错 `Access Denied: Table ems-data-platform:<customer>`，需改用 `ems-od-<customer>` 或 `sap-od-<customer>` 项目名。

### Dataset 名

```
emarsys_<customer>_<suite_account_ID>
```

一个 Open Data 项目可关联多个 SAP Emarsys 账户，每个账户对应独立 dataset。

### 数据视图（View）名

```
{view_name}_[customer_ID]
```

例如：`email_sends_12345`、`email_opens_12345`

### Cloud Storage Bucket 名

```
client_bucket_<customer>
```

---

## 三、访问与权限

- 需要 Google 账户（含个人 Gmail）加入 Open Data Access Group 才能访问 BigQuery 数据视图
- **Service Account Key** 须每 90 天轮换一次，系统会在 Notification Center 提醒
- 数据**仅存储在 EU 区域**，外部工具的 BigQuery region 也必须设置为 EU
- 只有底层表有数据时，对应视图才会在 GCP 项目中可见（例如未集成 Mobile Push，则 push 相关视图不显示）

---

## 四、SQL 查询规范

### 4.1 仅支持 Standard SQL

Open Data 数据视图只支持 **Standard SQL 方言**，不支持 Legacy SQL。

### 4.2 禁止 SELECT *

SAP 可能随时增删字段，`SELECT *` 会导致查询或导出任务失败。**必须显式指定所需字段。**

### 4.3 分区时间（partitiontime）过滤——必须使用

不过滤 `partitiontime` 会全表扫描，快速耗尽配额。建议格式：

```sql
-- 查询某天的数据（推荐加前后一天的 buffer）
WHERE DATE(partitiontime) >= "2019-04-19"
  AND DATE(partitiontime) <= "2019-04-21"
  AND EXTRACT(DATE FROM event_time) = "2019-04-20"
```

查询当天数据（含 Streaming Buffer）：

```sql
WHERE DATE(partitiontime) = CURRENT_DATE()
   OR DATE(partitiontime) = DATE(NULL)
-- DATE(NULL) 用于扫描 Streaming Buffer 中尚未分区的数据
```

### 4.4 获取最新记录（去除历史版本）

Open Data 表存储全量历史记录（如活动名称修改会生成新行），如只需当前最新值，使用 `QUALIFY`：

```sql
SELECT campaign_id, name
FROM `sap-od-[customer_ID].emarsys_[customer_ID].email_campaigns_v2_[customer_ID]`
QUALIFY ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY event_time DESC, loaded_at DESC) = 1;
```

### 4.5 物化视图（Materialized Views）

对频繁读取、不频繁变化的数据子集，可在 `editable_dataset` 中创建物化视图以提升性能：

```sql
CREATE MATERIALIZED VIEW `sap-od-<customer>.editable_dataset.<view_name>` AS
SELECT campaign_id, name, event_time
FROM `sap-od-<customer>.editable_dataset.<source_table>`
GROUP BY 1, 2, 3
```

---

## 五、重要注意事项

### 5.1 重复数据

BigQuery 表为 **raw 表，不保证唯一性**，重复率约 **0.001%**。如需唯一数据，需手动过滤去重。

### 5.2 contact_id 使用风险

`contact_id` 是 SAP Emarsys 内部标识符，**不建议在外部系统中用作唯一标识**。如需对应联系人，须通过 Contacts Data Export API 导出并映射。

### 5.3 联系人删除传播

联系人删除后，其**所有历史行为数据同步删除**，并同步反映在 Open Data 数据视图中。

### 5.4 email 数据中 contact_id / campaign_id 为 null 的情况

| 场景 | 说明 |
|------|------|
| `contact_id` 为 null | 该事件属于测试活动（Test Campaign） |
| `campaign_id` 为 null（在 Sends 视图） | 测试活动的发送事件不写入 Sends 视图 |
| `contact_id` 为 null（超时） | 邮件活动发生在发送后 **60 天以上**，无法关联到具体联系人 |
| `contact_id` 存在但行为数据缺失 | 联系人删除不足 30 天，部分行为数据尚未完全清除 |

### 5.5 字段结构变更通知

SAP 保留随时增删字段的权利，变更前会提前通知。接入方须监控 SAP 变更通知并及时调整查询和导出配置。

---

## Email 数据视图

> 官方文档：[Email Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf396da74c11014b68bc1fdabe6e2ea.html)
> 共 **11 张表**（含 1 张废弃表）

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `email_campaigns` | 否 | ❌ 已废弃 |
| 2 | `email_campaigns_v2` | 否 | ✅ → vdm_t_activity |
| 3 | `email_campaign_categories` | 否 | ❌ 无 contact_id |
| 4 | `email_sends` | ✅ | ✅ → vdm_t_message_record + t_retailevent |
| 5 | `email_opens` | ✅ | ✅ → vdm_t_message_record + t_retailevent |
| 6 | `email_clicks` | ✅ | ✅ → vdm_t_message_record + t_retailevent |
| 7 | `email_bounces` | ✅ | ✅ → vdm_t_message_record + t_retailevent |
| 8 | `email_cancels` | ✅ | ✅ → t_retailevent（dts_ 无枚举值） |
| 9 | `email_complaints` | ✅ | ✅ → t_retailevent（dts_ 无枚举值） |
| 10 | `email_unsubscribes` | ✅ | ✅ → vdm_t_message_record + t_retailevent |
| 11 | `contents` | 否 | ❌ 60天TTL，无 contact_id |

---

### email_campaigns_[customer_ID]

> **已废弃**，请使用 `email_campaigns_v2`，不同步

---

### email_campaigns_v2_[customer_ID]

> 邮件活动元数据（推荐使用 v2）
> 数据范围：2017-08-01 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | 活动类型：test / batch / transactional |
| category_name | string | 自定义分类名称 |
| customer_id | integer | 账号唯一ID |
| defined_type | string | 类型组合值（见下方枚举） |
| event_time | timestamp | 活动创建/修改时间（UTC） |
| is_recurring | boolean | 是否为循环活动 |
| language | string | 两位语言代码 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| name | string | 活动名称 |
| origin_campaign_id | integer | 父活动ID（循环活动或A/B测试） |
| program_id | integer | 所属自动化程序ID |
| program_version_id | integer | 所属自动化程序版本ID |
| status | string | 活动状态（2024-01-26起有效） |
| subject | string | 未个性化的主题行 |
| suite_event | string | 活动子类型 |
| suite_type | string | 活动类型 |
| timezone | string | 活动时区 |
| version_name | string | 活动版本名称 |

**defined_type 枚举值**：newsletter / testmail / on_import / adhoc / recurring / event / multi_language / abtest / virtual_contact / unknown

---

### email_campaign_categories_[customer_ID]

> 包含所有活动分类数据
> 数据范围：2016-01-01 起
> **注意：无 contact_id，无法关联到具体联系人，不同步到 StarRocks**

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 分类创建时间（UTC） |
| id | integer | 活动分类ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| name | string | 活动分类名称 |

---

### email_sends_[customer_ID]

> 邮件发送记录
> 数据范围：2016-01-01 起；测试活动不记录在此表

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| event_time | timestamp | 发送时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |

---

### email_opens_[customer_ID]

> 邮件打开记录（含地理、设备信息）
> 数据范围：2016-01-01 起；可能含重复条目

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 打开时间（UTC） |
| generated_from | string | 无打开信息（追踪像素未下载） |
| geo | record | 地理信息记录体 |
| geo_country_iso_code | string | 国家/地区 ISO 代码 |
| geo.accuracy_radius | integer | 地理位置精度半径（公里） |
| geo.city_name | string | 城市名称 |
| geo.continent_code | string | 大洲代码 |
| geo.latitude | float | 纬度 |
| geo.longitude | float | 经度 |
| geo.postal_code | string | 邮政编码 |
| geo.time_zone | string | 时区 |
| ip | string | 打开设备IP地址 |
| is_anonymized | boolean | 是否已匿名化（已废弃功能） |
| is_mobile | boolean | 是否移动设备打开 |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| md5 | string | user_agent 的 MD5 哈希 |
| message_id | integer | 单封邮件唯一ID |
| platform | string | 设备平台（如 iPhone / Windows 等） |
| uid | string | 联系人随机唯一标识符 |
| user_agent | string | 设备和浏览器信息 |

---

### email_clicks_[customer_ID]

> 邮件链接点击记录（含重复点击）
> 数据范围：2018-08-01 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| category_id | integer | 链接分类ID |
| category_name | string | 链接分类名称 |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 点击时间（UTC） |
| geo | record | 地理信息记录体 |
| geo_country_iso_code | string | 国家/地区 ISO 代码 |
| geo.accuracy_radius | integer | 精度半径（公里） |
| geo.city_name | string | 城市名称 |
| geo.continent_code | string | 大洲代码 |
| geo.latitude | float | 纬度 |
| geo.longitude | float | 经度 |
| geo.postal_code | string | 邮政编码 |
| geo.time_zone | string | 时区 |
| ip | string | 点击设备IP地址 |
| is_anonymized | boolean | 是否已匿名化（已废弃功能） |
| is_img | boolean | 是否点击图片（仅旧版 VCMS 编辑器有效） |
| is_mobile | boolean | 是否移动设备 |
| launch_id | integer | 批次发送唯一ID |
| link_id | integer | 链接ID |
| link_name | string | 在邮件编辑器中定义的链接名称 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| md5 | string | user_agent 的 MD5 哈希 |
| message_id | integer | 单封邮件唯一ID |
| platform | string | 设备平台 |
| section_id | integer | 邮件段落ID（仅旧版 VCMS 模板） |
| uid | string | 联系人随机唯一标识符 |
| user_agent | string | 设备和浏览器信息 |

---

### email_bounces_[customer_ID]

> 邮件退回记录
> 数据范围：2016-01-01 起

| 字段 | 类型 | 说明 |
|------|------|------|
| bounce_type | string | 退回类型：block / soft / hard |
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| dsn_reason | string | SMTP 服务器原始退回响应码 |
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 退回时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |

---

### email_cancels_[customer_ID]

> 邮件取消发送记录
> 数据范围：2017-11-20 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 取消时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |
| reason | string | 取消原因（见下方枚举） |
| suite_event | string | 活动子类型 |
| suite_type | string | 活动类型 |

**reason 枚举值**：opted_out / frequency_cap_blocked / invalid_email_address_error / empty_address_error / spamcomplaint_blocked / user_blocked / system_blocked / triggered_email_blocked / pers_error / html_error / text_error / empty_mail / encoding_conversion_error / email_duplication 等

---

### email_complaints_[customer_ID]

> 邮件投诉（标记垃圾邮件）记录
> 数据范围：2017-11-20 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 投诉时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |

---

### email_unsubscribes_[customer_ID]

> 邮件退订记录（不含通过导入或UI操作的退订）
> 数据范围：2017-01-01 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| campaign_type | string | batch 或 transactional |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| domain | string | 收件人邮箱域名 |
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 退订时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |
| source | string | 退订来源（见下方枚举） |

**source 枚举值**：
- `unsubscribe`：通过邮件中的退订链接退订
- `list_unsubscribe`：通过邮件客户端退订按钮退订
- `unsubscribe_from_campaign`：通过 API 退订特定活动

---

### contents_[customer_ID]

> 邮件在线版本中解析出的图片、链接和文本内容
> 数据范围：2023-05-15 起
> **注意：仅在邮件有在线版本时填充；分区有 60 天过期限制；无 contact_id，不同步到 StarRocks**

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer, nullable | 账号唯一ID（从 HTML 文件名解析） |
| campaign_id | integer, nullable | 活动ID（从 HTML 文件名解析） |
| message_id | integer, nullable | 活动内消息唯一ID（从 HTML 文件名解析） |
| uid | string, nullable | 联系人随机唯一标识符（从 HTML 文件名解析） |
| locale | string, nullable | 多语言 VCE 活动的语言版本 IETF 标签 |
| is_multilanguage | boolean, nullable | VCE 活动是否含多语言版本 |
| contents | record, repeated | 邮件中解析出的内容列表 |
| contents.content_type | string, nullable | 内容类型：image_link / image / link / text_link / text |
| contents.src | string, nullable | 图片来源 URL（image / image_link 类型） |
| contents.relative_link_id | integer, nullable | 被追踪链接的相对链接ID |
| contents.content_index | integer, nullable | 内容在邮件中的索引（从 0 开始） |
| contents.is_open_time_content | boolean, nullable | 是否为 Predict / Kickdynamic 开启时内容 |
| contents.is_tracking_pixel | boolean, nullable | 是否为追踪像素图片 |
| contents.e_editable | string, nullable | VCE 活动中可编辑元素的ID |
| contents.e_block_id | string, nullable | VCE 活动中所属 block 的ID |
| contents.external_id | string, nullable | 带 external-id 属性标记的内容ID |
| loaded_at | timestamp, nullable | 邮件解析完成时的时间戳 |
| batch_filename | string, nullable | OVCS 上批次文件的名称和路径 |
| html_filename | string, nullable | 批次中 HTML 文件的名称 |

---

## Web Push 数据视图

> 共 **5 张表**

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `web_push_campaigns` | 否 | ❌ 无 contact_id |
| 2 | `web_push_sends` | ✅ | ✅ → t_retailevent |
| 3 | `web_push_not_sends` | ✅ | ✅ → t_retailevent |
| 4 | `web_push_clicks` | ✅ | ✅ → t_retailevent |
| 5 | `web_push_custom_events` | ✅ | ❌ 未映射 |

---

### web_push_campaigns_[customer_ID]

> 所有 Web Push 活动数据，含所有语言版本

| 字段 | 类型 | 说明 |
|------|------|------|
| internal_campaign_id | integer | 内部活动唯一标识符 |
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | 每个账号内的活动唯一标识符 |
| name | string | 活动名称 |
| source | record | 活动来源记录 |
| source.type | string | 来源类型 |
| source.id | integer | 来源唯一标识符 |
| message | record | 活动消息记录 |
| message.language | string | 消息语言 |
| message.title | string | 消息标题 |
| message.body | string | 消息正文 |
| domain_code | string | 域的唯一代码 |
| domain | string | 域名 |
| settings | record | 活动设置记录 |
| settings.k | string | 设置键 |
| settings.v | string | 设置值 |
| segment_id | integer | 分段唯一标识符 |
| recipient_source_id | integer | 收件人来源数字ID（如分段ID、联系人列表ID） |
| data | string | 活动自定义数据（JSON字符串） |
| launched_at | timestamp | 活动启动时间 |
| scheduled_at | timestamp | 活动计划发送时间 |
| created_at | timestamp | 活动创建时间 |
| deleted_at | timestamp | 活动删除时间 |
| event_time | timestamp | 活动触发时间 |
| loaded_at | timestamp | 数据加载到系统的时间 |
| action_buttons | record | 活动操作按钮记录 |
| action_buttons.k | string | 操作按钮键 |
| action_buttons.v | string | 操作按钮值 |
| sending_limit | record | 发送限制记录 |
| sending_limit.amount | integer | 每时间单位发送消息数量 |
| sending_limit.unit | string | 时间单位（分钟） |
| recipient_source_type | string | 收件人来源类型 |
| status | string | 活动状态 |

---

### web_push_sends_[customer_ID]

> Web Push 发送记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | 每个账号内的活动唯一标识符 |
| contact_id | integer | 联系人唯一标识符 |
| domain_code | string | 域的唯一代码 |
| domain | string | 域名 |
| platform | string | 平台类型（浏览器类型） |
| push_token | string | 收件人推送令牌 |
| client_id | string | 客户端唯一标识符 |
| event_time | timestamp | 事件触发时间 |
| loaded_at | timestamp | 事件加载到系统的时间 |
| treatments | record | 处理记录 |
| treatments.ui | record | UI 处理记录 |
| treatments.ui.id | integer | Web Push 活动唯一标识符 |
| treatments.ui.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.ui_test | record | UI 测试处理记录 |
| treatments.ui_test.id | integer | Web Push 活动唯一标识符 |
| treatments.ui_test.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.rti | record | 基于事件的自动化程序处理记录 |
| treatments.rti.id | string | 基于事件的自动化程序唯一标识符 |
| treatments.rti.run_id | string | 基于事件的自动化程序运行实例标识符 |
| treatments.ac | record | 基于受众的自动化程序处理记录 |
| treatments.ac.id | integer | 基于受众的自动化程序唯一标识符 |
| treatments.ac.run_id | string | 基于受众的自动化程序运行实例标识符 |

---

### web_push_not_sends_[customer_ID]

> Web Push 发送失败记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | 每个账号内的活动唯一标识符 |
| contact_id | integer | 联系人唯一标识符 |
| domain_code | string | 域的唯一代码 |
| domain | string | 域名 |
| platform | string | 平台类型（浏览器类型） |
| push_token | string | 收件人推送令牌 |
| client_id | string | 客户端唯一标识符 |
| error | record | 错误记录 |
| error.reason | string | 错误原因 |
| error.code | string | 错误代码（通常为 HTTP 响应状态码） |
| event_time | timestamp | 事件触发时间 |
| loaded_at | timestamp | 事件加载到系统的时间 |
| treatments | record | 处理记录 |
| treatments.ui | record | UI 处理记录 |
| treatments.ui.id | integer | Web Push 活动唯一标识符 |
| treatments.ui.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.ui_test | record | UI 测试处理记录 |
| treatments.ui_test.id | integer | Web Push 活动唯一标识符 |
| treatments.ui_test.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.rti | record | 基于事件的自动化程序处理记录 |
| treatments.rti.id | string | 基于事件的自动化程序唯一标识符 |
| treatments.rti.run_id | string | 基于事件的自动化程序运行实例标识符 |
| treatments.ac | record | 基于受众的自动化程序处理记录 |
| treatments.ac.id | integer | 基于受众的自动化程序唯一标识符 |
| treatments.ac.run_id | string | 基于受众的自动化程序运行实例标识符 |

---

### web_push_clicks_[customer_ID]

> Web Push 用户点击记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| contact_id | integer | 联系人唯一标识符 |
| campaign_id | integer | 每个账号内的活动唯一标识符 |
| client_id | string | 客户端唯一标识符 |
| domain_code | string | 域的唯一代码 |
| domain | string | 域名 |
| sdk_version | string | 客户端使用的 SDK 版本 |
| treatments | record | 处理记录 |
| treatments.ui | record | UI 处理记录 |
| treatments.ui.id | integer | Web Push 活动唯一标识符 |
| treatments.ui.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.ui_test | record | UI 测试处理记录 |
| treatments.ui_test.id | integer | Web Push 活动唯一标识符 |
| treatments.ui_test.run_id | string | Web Push 活动运行实例唯一标识符 |
| treatments.rti | record | 基于事件的自动化程序处理记录 |
| treatments.rti.id | string | 基于事件的自动化程序唯一标识符 |
| treatments.rti.run_id | string | 基于事件的自动化程序运行实例标识符 |
| treatments.ac | record | 基于受众的自动化程序处理记录 |
| treatments.ac.id | integer | 基于受众的自动化程序唯一标识符 |
| treatments.ac.run_id | string | 基于受众的自动化程序运行实例标识符 |
| event_time | timestamp | 事件触发时间 |
| loaded_at | timestamp | 事件加载到系统的时间 |
| platform | string | 平台类型（浏览器类型） |

---

### web_push_custom_events_[customer_ID]

> Web Push 自定义事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| contact_id | integer | 联系人唯一标识符 |
| client_id | string | 客户端唯一标识符 |
| domain_code | string | 域的唯一代码 |
| domain | string | 域名 |
| event_name | string | 自定义事件名称 |
| event_attributes | record | 事件附加属性 |
| event_attributes.k | string | 属性键 |
| event_attributes.v | string | 属性值 |
| sdk_version | string | 客户端使用的 SDK 版本 |
| event_time | timestamp | 事件触发时间 |
| loaded_at | timestamp | 事件加载到系统的时间 |
| platform | string | 平台类型（浏览器类型） |

---

## Mobile Engage 数据视图

> 共 **15 张表**

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `push_campaigns` | 否 | ❌ 无 contact_id |
| 2 | `push_sends` | ✅ | ❌ 未映射 |
| 3 | `push_not_sends` | ✅ | ❌ 未映射 |
| 4 | `push_opens` | ✅ | ❌ 未映射 |
| 5 | `push_custom_events` | ✅ | ❌ 未映射 |
| 6 | `inapp_campaigns` | 否 | ❌ 无 contact_id |
| 7 | `inapp_views` | ✅ | ❌ 未映射 |
| 8 | `inapp_clicks` | ✅ | ❌ 未映射 |
| 9 | `inapp_audience_changes` | ✅ | ❌ 未映射 |
| 10 | `inbox_sends` | ✅ | ❌ 未映射 |
| 11 | `inbox_not_sends` | ✅ | ❌ 未映射 |
| 12 | `inbox_tag_changes` | ✅ | ❌ 未映射 |
| 13 | `inbox_campaigns` | 否 | ❌ 无 contact_id |
| 14 | `client_snapshots` | 否（含 identified/anonymous_contact_id） | ❌ 未映射 |
| 15 | `client_updates` | 否 | ❌ 无 contact_id |

---

### push_campaigns_[customer_ID]

> 所有 Mobile Push 活动数据，含所有语言版本
> 数据范围：2017-11-29 起

| 字段 | 类型 | 说明 |
|------|------|------|
| android_settings | record | Android 特定设置 |
| android_settings.k | string | Android 设置键 |
| android_settings.v | string | Android 设置值 |
| application_id | integer | 应用唯一ID |
| campaign_id | integer | 活动唯一ID |
| created_at | timestamp | 活动创建时间（UTC） |
| customer_id | integer | 账号唯一ID |
| data | record | 客户可添加的任意数据 |
| deleted_at | timestamp | 删除时间 |
| event_time | timestamp | 活动最后更新时间 |
| ios_settings | record | iOS 特定设置 |
| ios_settings.k | string | iOS 设置键 |
| ios_settings.v | string | iOS 设置值 |
| launched_at | timestamp | 活动启动时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message | record | 消息正文记录 |
| message.k | string | 消息语言代码 |
| message.v | string | 指定语言的消息正文 |
| name | string | 推送活动名称 |
| push_internal_campaign_id | integer | Push 渠道内部活动ID |
| scheduled_at | timestamp | 计划发送时间 |
| segment_id | integer | 应用的分段ID |
| recipient_source_id | integer | 收件人来源数字ID（如分段ID、联系人列表ID） |
| source | string | 可能来源：ac / broadcast / segment / me_segment |
| recipient_source_type | string | 所选收件人来源类型（AC、分段或联系人列表） |
| status | string | 活动状态 |
| target | string | 可能值：push / deliver / notificationinbox |
| title | record | 始终包含语言代码 |
| title.k | string | 语言代码键 |
| title.v | string | 语言键值 |
| sending_limit | record | 每单位时间（分钟、小时等）发送消息数量 |
| created_with | string | 活动创建来源信息（API含版本或UI） |

---

### push_sends_[customer_ID]

> Mobile Push 发送记录
> 数据范围：2017-05-31 起

| 字段 | 类型 | 说明 |
|------|------|------|
| application_code | string | 应用唯一ID |
| application_id | integer | 应用唯一ID |
| campaign_id | integer | 活动唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 消息发送时间 |
| hardware_id | string | SDK 实例唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| platform | string | 平台名称（Android、iOS 等） |
| program_id | integer | 关联受众自动化程序唯一ID |
| push_token | string | 设备相关令牌 |
| source | record | 事件触发器 |
| source.id | string | 来源唯一ID |
| source.type | string | 来源类型（如 ac 或 ui） |
| target | string | 消息目标，典型值为 push |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |

---

### push_not_sends_[customer_ID]

> Mobile Push 发送失败记录
> 数据范围：2017-05-31 起

| 字段 | 类型 | 说明 |
|------|------|------|
| application_code | string | 应用唯一ID |
| application_id | integer | 应用唯一ID |
| campaign_id | integer | 活动唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 事件发生时间 |
| hardware_id | string | SDK 实例唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| platform | string | 平台名称（Android、iOS 等） |
| program_id | integer | AC 程序唯一ID |
| push_token | string | 设备相关令牌 |
| reason | string | 未发送事件原因 |
| source | record | 事件触发器 |
| source.id | string | 来源唯一ID |
| source.type | string | 来源类型（如 ac 或 ui） |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |

---

### push_opens_[customer_ID]

> Mobile Push 打开记录
> 数据范围：2017-05-31 起

| 字段 | 类型 | 说明 |
|------|------|------|
| application_code | string | 应用唯一ID |
| application_id | integer | 应用唯一ID |
| campaign_id | integer | 活动唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 打开时间 |
| hardware_id | string | SDK 实例唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| source | string | 消息显示位置 |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |

---

### push_custom_events_[customer_ID]

> Mobile Push 自定义事件记录
> 数据范围：2017-05-31 起

| 字段 | 类型 | 说明 |
|------|------|------|
| application_code | string | 应用唯一ID |
| application_id | integer | 应用唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_attributes | record | 任意自定义属性 |
| event_attributes.k | string | 属性键 |
| event_attributes.v | string | 属性值 |
| event_name | string | 事件名称（不唯一） |
| event_time | timestamp | 自定义事件发生时间 |
| hardware_id | string | SDK 实例唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |

---

### inapp_campaigns_[customer_ID]

> 所有 In-app 活动数据，含所有语言版本

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| name | string | 活动 UI 名称 |
| status | string | 状态 |
| source | string | 可能值：broadcast / audience / push |
| application_code | string | 应用代码 |
| event_time | timestamp | 活动最后更新时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### inapp_views_[customer_ID]

> In-app 曝光记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | SAP Emarsys 内部联系人ID |
| application_code | string | 应用唯一ID |
| campaign_id | integer | 活动唯一ID |
| client_id | string | SDK 实例标识符 |
| event_time | timestamp | In-app 曝光时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| audience_change.treatments.rti.program_id | string | 定向联系人的 RTI 程序 |
| audience_change.treatments.contact_segment.segment_id | string | 联系人被添加/移除的联系人分段 |
| audience_change.treatments.push_campaign.campaign_id | string | push 转 In-app 场景下的推送活动 |
| audience_change.treatments.ac.program_id | string | 定向联系人的 AC 程序 |

---

### inapp_clicks_[customer_ID]

> In-app 用户操作记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | SAP Emarsys 内部联系人ID |
| application_code | string | 应用唯一代码 |
| campaign_id | integer | 活动唯一ID |
| client_id | string | SDK 实例标识符 |
| event_time | timestamp | 事件设备时间 |
| loaded_at | timestamp | 数据库记录的事件时间 |
| button | record | 按钮记录 |
| button.button_id | string | 被按下的按钮ID |
| audience_change.treatments.rti.program_id | string | 定向联系人的 RTI 程序 |
| audience_change.treatments.contact_segment.segment_id | string | 联系人被添加/移除的联系人分段 |
| audience_change.treatments.push_campaign.campaign_id | string | push 转 In-app 场景下的推送活动 |
| audience_change.treatments.ac.program_id | string | 定向联系人的 AC 程序 |

---

### inapp_audience_changes_[customer_ID]

> In-app 受众变更记录（联系人加入/移除受众）
> 数据范围：2020-08-21 起

| 字段 | 类型 | 说明 |
|------|------|------|
| change_type | string | 添加或移除 |
| customer_id | integer | 系统中的客户记录 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| application_code | string | 应用代码 |
| campaign_id | string | 活动唯一ID |
| client_id | string | SDK 实例标识符 |
| event_time | timestamp | 活动最后更新时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| treatment | record | 处理记录 |

---

### inbox_sends_[customer_ID]

> Mobile Inbox 发送记录

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| application_code | string | 应用唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| event_time | timestamp | 设备获取活动的时间 |
| platform | string | 平台名称（Android、iOS 等） |
| source.id | string | 来源唯一ID |
| source.type | string | 来源类型（如 ac 或 ui） |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.ui.id | integer | UI 启动活动的会话ID |
| treatments.ui.run_id | string | UI 启动活动的运行ID |
| treatments.ui_test.id | integer | 测试活动 UI 启动的会话ID |
| treatments.ui_test.run_id | string | 测试活动 UI 启动的运行ID |

---

### inbox_not_sends_[customer_ID]

> Mobile Inbox 发送失败记录

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| application_code | string | 应用唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| event_time | timestamp | inbox 活动发送失败时间 |
| platform | string | 平台名称（Android、iOS 等） |
| reason | string | 未发送事件原因 |
| source.id | string | 来源唯一ID |
| source.type | string | 来源类型（如 ac 或 ui） |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |
| treatments.ui.id | integer | UI 启动活动的会话ID |
| treatments.ui.run_id | string | UI 启动活动的运行ID |
| treatments.ui_test.id | integer | 测试活动 UI 启动的会话ID |
| treatments.ui_test.run_id | string | 测试活动 UI 启动的运行ID |

---

### inbox_tag_changes_[customer_ID]

> Mobile Inbox 标签变更记录

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| application_code | string | 应用唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| event_time | timestamp | 标签更新时间 |
| tag | record | 标签记录 |
| tag.operation | string | 添加/移除标签选项 |
| tag.name | string | 标签名称（high / cancelled / seen / opened / pinned / deleted） |
| platform | string | 平台名称（Android、iOS 等） |
| treatments.rti.id | string | 事件自动化程序ID |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |

---

### inbox_campaigns_[customer_ID]

> 所有 Mobile Inbox 活动数据

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| application_code | string | 应用唯一ID |
| name | string | 活动名称 |
| status | string | 活动状态 |
| source | string | 可能来源：ac / broadcast / segment / me_segment |
| recipient_source_type | string | 所选收件人来源类型（AC、分段或联系人列表） |
| title | record | 活动消息标题 |
| title.key | string | 语言代码键 |
| title.value | string | 语言键值 |
| message | record | 消息正文 |
| message.key | string | 消息语言代码 |
| message.value | string | 指定语言的消息正文 |
| segment_id | integer | 应用的分段ID |
| recipient_source_id | integer | 收件人来源数字ID（分段ID、联系人列表ID） |
| data.key | string | 活动自定义数据ID |
| data.value | string | 活动自定义数据值 |
| target | string | Inbox 活动目标 |
| collapse_id | string | 内部/折叠ID |
| settings.key | string | 设置ID |
| settings.value | string | 设置值 |
| action_buttons.key | string | 操作按钮ID |
| action_buttons.value | string | 操作按钮值 |
| device_filter.key | string | 设备过滤ID |
| device_filter.value | string | 设备过滤值 |
| is_high_priority | boolean | 是否设置高优先级标签 |
| triggerable_by_push | boolean | 是否可由推送活动触发 |
| created_at | timestamp | 活动创建时间（UTC） |
| launched_at | timestamp | 活动启动时间 |
| scheduled_at | timestamp | 计划发送时间 |
| expires_at | timestamp | 消息过期时间 |
| deleted_at | timestamp | 活动删除时间 |
| event_time | timestamp | 活动更新时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### client_snapshots_[customer_ID]

> 移动用户群当前状态快照

| 字段 | 类型 | 说明 |
|------|------|------|
| application_code | string | 应用唯一代码 |
| client_id | string | SDK 实例标识符 |
| model | string | 手机型号 |
| platform | string | Android / iOS |
| language | string | 应用语言 |
| timezone | string | 设备时区 |
| application_version | string | 应用版本 |
| os_version | string | 设备操作系统版本 |
| sdk_version | string | SDK 版本 |
| push_token | string | 推送令牌值（如可用） |
| identified_contact_id | integer | SAP Emarsys 内部联系人ID（已识别联系人） |
| anonymous_contact_id | integer | SAP Emarsys 内部联系人ID（匿名联系人） |
| contact_field_id | string | 用于识别联系人的字段 |
| contact_field_value | string | 联系人字段值 |
| push_token_status | string | 推送令牌状态 |
| first_event_time | timestamp | 用户首次移动活动时间 |
| last_event_time | timestamp | 用户最后移动活动时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### client_updates_[customer_ID]

> 移动客户端更新记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| application_code | string | 应用唯一ID |
| client_id | string | SDK 实例标识符 |
| model | string | 手机型号 |
| platform | string | iOS / Android / Huawei |
| language | string | 应用语言 |
| timezone | string | 设备时区 |
| application_version | string | 应用版本 |
| os_version | string | 设备操作系统版本 |
| sdk_version | string | SDK 版本 |
| event_time | timestamp | 活动更新时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| push_enabled | boolean | 已废弃；推送是否启用请改用：push_token IS NOT NULL AND push_token_status IS NULL |

---

## Mobile Wallet 数据视图

> 共 **2 张表**
> 数据范围：2023-11-08 起

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `wallet_campaigns` | 否 | ❌ 无 contact_id |
| 2 | `wallet_passes` | ✅ | ❌ 未映射 |

---

### wallet_campaigns_[customer_ID]

> Mobile Wallet 活动历史记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | Suite 提供的活动唯一ID |
| internal_campaign_id | UUID | Wallet Service 中的活动唯一ID |
| wallet_config_id | UUID | Wallet 配置唯一ID |
| name | string | 活动名称 |
| status | string | 活动启动状态（IN_DRAFT / READY_TO_LAUNCH） |
| template_type | string | 活动类型（Loyalty / voucher / coupon） |
| created_at | timestamp | 活动创建时间 |
| updated_at | timestamp | 活动修改时间 |
| archived_at | timestamp | 活动归档时间 |
| launched_at | timestamp | 活动启动时间 |
| event_time | timestamp | 影响活动的事件时间 |
| loaded_at | timestamp | 事件加载时间 |

---

### wallet_passes_[customer_ID]

> Mobile Wallet pass 相关事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | UUID | Wallet Service 中 pass 所属活动唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| serial_number | UUID | Mobile Wallet pass 唯一ID |
| platform | string | Mobile Wallet pass 的移动平台（Apple / Google） |
| template_type | string | pass 所属活动类型（Loyalty / voucher / coupon） |
| event | string | 发生的事件（pass_generated / pass_downloaded / pass_updated / pass_removed） |
| event_time | timestamp | 影响 Mobile Wallet 活动的事件时间 |
| loaded_at | timestamp | 事件加载时间 |

---

## SMS 数据视图

> 共 **5 张表**
> 数据范围：2017-09-19 起

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `sms_campaigns` | 否 | ❌ 无 contact_id |
| 2 | `sms_send_reports` | ✅ | ❌ 未映射 |
| 3 | `sms_sends` | ✅ | ✅ → t_retailevent |
| 4 | `sms_clicks` | ✅ | ✅ → t_retailevent |
| 5 | `sms_unsubscribes` | ✅ | ❌ 未映射 |

---

### sms_campaigns_[customer_ID]

> SMS 活动基本信息

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | SMS 活动名称 |
| sender_name | string | 发送者名称 |
| message | string | SMS 消息文本 |
| include_unsubscribe_link | boolean | 是否包含退订链接 |
| trigger_type | string | 触发类型：batch_now / ac / batch_later |
| campaign_id | integer | 包含此消息的活动ID |
| event_time | timestamp | 活动创建或修改时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| business_unit | string | 提供商名称（目前始终为 null） |

---

### sms_send_reports_[customer_ID]

> SMS 投递信息

| 字段 | 类型 | 说明 |
|------|------|------|
| bounce_type | string | 退回原因 |
| campaign_id | integer | 包含此消息的活动ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | SMS 消息发送时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | string | 消息唯一ID |
| status | string | SMS 提供商发送状态 |

---

### sms_sends_[customer_ID]

> SMS 发送记录

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | string | 消息唯一ID |
| launch_id | integer | 关联 launch 唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| program_id | integer | 发送此消息的程序ID（2020-10-05 起为 NULL） |
| campaign_id | integer | 包含此消息的活动ID |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| event_time | timestamp | SMS 发送时间（UTC） |
| treatments.rti.id | string | 事件自动化程序ID（2020-10-05 起填充） |
| treatments.rti.run_id | string | 事件自动化程序运行实例ID（2020-10-05 起填充） |
| treatments.ac.id | integer | 受众自动化程序ID（2020-10-05 起填充） |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID（2020-10-05 起填充） |

---

### sms_clicks_[customer_ID]

> SMS 链接点击记录

| 字段 | 类型 | 说明 |
|------|------|------|
| launch_id | integer | launch 唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| link_id | integer | 链接ID |
| is_dry_run | boolean | URL 是否用于测试 |
| user_agent | string | 代表联系人点击的用户代理 |
| campaign_id | integer | 包含此消息的活动ID |
| event_time | timestamp | 事件发生时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 事件加载时间（nullable） |

---

### sms_unsubscribes_[customer_ID]

> SMS 退订记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | SAP Emarsys 内部联系人ID |
| unsubscribe_type | string | 取消订阅类型 |
| event_time | timestamp | 订阅取消发生时间（UTC） |
| campaign_id | integer | 包含此消息的活动ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| customer_id | integer | 账号唯一ID |

---

## Web Channel 数据视图

> 共 **1 张表**
> 数据范围：2018-08 起

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `webchannel_events_enhanced` | ✅ | ❌ 未映射 |

---

### webchannel_events_enhanced_[customer_ID]

> Web 渠道活动事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| platform | string | 平台标识（如 iPhone / Windows 等） |
| md5 | string | user_agent 的 MD5 哈希 |
| is_mobile | boolean | 是否在移动设备上注册 |
| is_anonymized | boolean | user_agent 是否已匿名化 |
| campaign_id | string | 活动唯一ID |
| ad_id | string | 活动版本（Ad）ID |
| customer_id | integer | 账号唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| event_type | string | 注册的事件类型：show / submit / click |
| user_agent | string | 设备和浏览器信息 |
| event_time | timestamp | 事件时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

## Predict 数据视图

> 共 **5 张表**
> 数据范围：2017-11-20 起

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `session_categories` | ✅ | ❌ 未映射 |
| 2 | `session_purchases` | ✅ | ❌ 未映射 |
| 3 | `session_tags` | ✅ | ❌ 未映射 |
| 4 | `session_views` | ✅ | ❌ 未映射 |
| 5 | `sessions` | ✅ | ❌ 未映射 |

---

### session_categories_[customer_ID]

> 用户单次会话中浏览的分类

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | Predict 用户ID（邮件哈希或外部ID） |
| user_id_type | string | 用户ID类型（邮件哈希或外部ID） |
| user_id_field_id | integer | 包含此信息的 SAP Emarsys 平台列 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| category | string | 用户浏览的分类名称 |
| event_time | timestamp | 用户浏览分类的时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### session_purchases_[customer_ID]

> 用户单次会话中购买的商品

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | Predict 用户ID（邮件哈希或外部ID） |
| user_id_type | string | 用户ID类型（邮件哈希或外部ID） |
| user_id_field_id | integer | 包含此信息的 SAP Emarsys 平台列 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| items | record | 购买商品列表（含商品ID、价格、数量） |
| items.item_id | string | 购买商品唯一ID |
| items.price | float | 购买时商品价格 |
| items.quantity | float | 购买商品数量 |
| order_id | string | 订单唯一ID |
| event_time | timestamp | 用户购买时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### session_tags_[customer_ID]

> 单次会话中发生的事件

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | Predict 用户ID（邮件哈希或外部ID） |
| user_id_type | string | 用户ID类型（邮件哈希或外部ID） |
| user_id_field_id | integer | 包含此信息的 SAP Emarsys 平台列 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| tag | string | 网站发送的标签（事件类型） |
| attributes | record | 与事件相关的所有属性 |
| attributes.name | string | 属性名称 |
| attributes.string_value | string | 字符串值 |
| attributes.number_value | float | 数字值 |
| attributes.boolean_value | boolean | 逻辑值 |
| event_time | timestamp | 事件发生时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### session_views_[customer_ID]

> 用户单次会话中浏览的商品

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | Predict 用户ID（邮件哈希或外部ID） |
| user_id_type | string | 用户ID类型（邮件哈希或外部ID） |
| user_id_field_id | integer | 包含此信息的 SAP Emarsys 平台列 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| item_id | string | 用户浏览的商品唯一ID |
| event_time | timestamp | 用户查看商品的时间 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### sessions_[customer_ID]

> 完整会话数据（含购买、浏览、事件、分类、购物车信息）
> **注意：建议使用上方各子视图查询，效率更高**

| 字段 | 类型 | 说明 |
|------|------|------|
| start_time | timestamp | 用户会话开始时间 |
| end_time | timestamp | 用户会话结束时间 |
| purchases | record | 购买记录（含时间、商品、价格、数量、订单ID） |
| purchases.event_time | timestamp | 购买发生时间 |
| purchases.items | record | 购买商品列表 |
| purchases.items.item_id | string | 购买商品唯一ID |
| purchases.items.price | float | 购买时商品价格 |
| purchases.items.quantity | float | 购买商品数量 |
| purchases.order_id | string | 购买的唯一订单ID |
| views | record | 用户会话期间浏览的商品 |
| views.event_time | timestamp | 用户浏览商品的时间 |
| views.item_id | string | 用户会话期间浏览的商品唯一ID |
| tags | record | 自定义事件列表 |
| tags.event_time | timestamp | 此标签事件发生的时间 |
| tags.tag | string | 网站发送的标签 |
| tags.attributes | record | 与事件相关的所有属性 |
| tags.attributes.name | string | 属性名称 |
| tags.attributes.string_value | string | 字符串值 |
| tags.attributes.number_value | float | 数字值 |
| tags.attributes.boolean_value | boolean | 逻辑值 |
| categories | record | 用户会话期间浏览的所有分类 |
| categories.event_time | timestamp | 用户浏览分类的时间 |
| categories.category | string | 浏览的分类名称 |
| last_cart | record | 添加到购物车但未购买的商品（废弃购物车） |
| last_cart.event_time | timestamp | 最后一件商品添加/移除购物车的时间 |
| last_cart.items | record | 会话结束时仍在购物车中的商品列表 |
| last_cart.items.item_id | string | 会话结束时购物车中商品唯一ID |
| last_cart.items.price | float | 会话结束时商品价格 |
| last_cart.items.quantity | float | 会话结束时商品数量 |
| user_id | string | Predict 用户ID（邮件哈希或外部ID） |
| user_id_type | string | 用户ID类型（邮件哈希或外部ID） |
| user_id_field_id | integer | 包含此信息的 SAP Emarsys 平台列 |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| currency | string | 购买货币 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

## Event 数据视图

> 共 **2 张表**

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `external_events` | ✅ | ❌ 未映射 |
| 2 | `custom_events` | ✅ | ❌ 未映射 |

---

### external_events_[customer_ID]

> 通过 External Event API 触发的外部事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | SAP Emarsys 内部联系人ID |
| event_id | string | 平台生成的事件唯一标识符 |
| event_time | timestamp | 事件发生时间 |
| event_type_id | integer | 外部事件ID（管理 > 外部事件） |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### custom_events_[customer_ID]

> 自定义事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | SAP Emarsys 内部联系人ID |
| event_id | string | 事件唯一ID |
| event_time | timestamp | 事件发生时间（UTC） |
| event_type | boolean | 事件类型 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据加载到数据平台的日期（UTC） |
| partitiontime | timestamp | 数据分区字段（UTC） |

---

## Automation 数据视图

> 共 **1 张表**
> 数据范围：2022-11-01 起

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `automation_node_executions` | 否（含 participants.contact_id） | ❌ 未映射 |

---

### automation_node_executions_[customer_ID]

> 自动化程序参与者在节点级别的执行旅程记录

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| ac_program_id | integer | 受众自动化程序ID（事件自动化程序时为 NULL） |
| rti_program_id | string | 事件自动化程序ID（受众自动化程序时为 NULL） |
| node_id | string | 节点ID |
| execution_phase | string | START（节点执行开始）或 END（执行结束） |
| execution_id | string | 节点执行ID |
| testing_mode | boolean | 是否以测试模式进入程序 |
| event_time | timestamp | 执行时间 |
| participants.execution_result | string | 执行结果代码（PASSED 或错误码） |
| participants.route_index | integer | 过滤节点后联系人继续的路由索引（include=0 / exclude=1） |
| participants.child_node_id | string | A/B 分流节点中联系人继续的子节点ID |
| participants.continued_in_program | boolean | 联系人是否继续到下一节点 |
| participants.count | integer | 联系人列表中的联系人数量（单个联系人为 1） |
| participants.contact_list_id | integer | 批量执行的联系人列表ID（单联系人事务为 NULL） |
| participants.contact_id | integer | 联系人ID（联系人列表事务为 NULL） |
| participants.trigger_id | string | 事件自动化程序触发器唯一ID（受众自动化程序时为 NULL） |
| participants.deduplication_id | string | 每个参与者的唯一ID |
| partitiontime | timestamp | 分区日期 |

---

## Loyalty 数据视图

> 共 **7 张表**
> 数据范围：2019-11-01 起（loyalty_actions 从 2020-11-01 起）

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `loyalty_contact_points_state_latest` | 否（含 external_id） | ✅ → t_retailevent |
| 2 | `loyalty_points_earned_redeemed` | 否（含 external_id） | ✅ → t_retailevent |
| 3 | `loyalty_vouchers` | 否（含 external_id） | ❌ 未映射 |
| 4 | `loyalty_exclusive_access` | 否（含 external_id） | ❌ 未映射 |
| 5 | `loyalty_actions` | 否（含 external_id） | ❌ 未映射 |
| 6 | `loyalty_referral_codes` | 否（含 external_id） | ❌ 未映射 |
| 7 | `loyalty_referral_purchases` | 否（含 external_id） | ❌ 未映射 |

---

### loyalty_contact_points_state_latest_[customer_ID]

> 联系人最新 Loyalty 状态数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 事件发生时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| plan_id | string | 联系人所属方案标识符 |
| join_time | timestamp | 用户加入 Loyalty 程序的时间 |
| tier | string | 联系人当前等级名称 |
| tier_entry_time | timestamp | 联系人进入等级的时间 |
| balance_points | float | 余额积分数量 |
| status_points | float | 状态积分数量 |
| pending_points | float | 待确认状态的积分 |
| points_to_be_expired | float | 将过期的积分 |

---

### loyalty_points_earned_redeemed_[customer_ID]

> 联系人积分获取与兑换明细数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 事件发生时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| points | float | 给予或扣除的积分数量 |
| points_type | string | 余额积分或状态积分 |
| tracking_id | string | 内部追踪ID |
| source_of_points_awarded | string | 用户获得或失去积分的原因（Redemption / Tier_calc / Support / Migration / Order / Reward 等） |
| order_id | string | 积分归因的订单ID |
| attach_id | string | 连接动作附加与完成时间的内部ID |
| action_id | string | 积分来源的动作ID |
| reward_tracking_id | string | 内部ID，供将来使用 |
| redeemed_item | string | 用积分兑换的物品（Voucher / Exclusive access） |
| voucher_pool_id | string | 用积分兑换的优惠券池内部ID |
| voucher_pool_name | string | 用积分兑换的优惠券池名称 |
| exclusive_pool_id | string | 用积分兑换的专属访问池内部ID |
| exclusive_pool_name | string | 用积分兑换的专属访问池名称 |
| points_status | string | 积分当前状态：Pending / Confirmed / Expired / Redeemed / Removed |
| points_expiration_date | timestamp | 积分过期日期（仅确认积分；2020-10-19 后可用） |

---

### loyalty_vouchers_[customer_ID]

> 联系人通过积分获得或兑换的优惠券数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 凭证代码被用户看到的时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| pool_name | string | 凭证所属池名称 |
| pool_id | string | 凭证所属池ID |
| voucher_type | string | 已废弃 |
| voucher_name | string | 凭证名称 |
| voucher_code | string | 凭证代码（仅用户显示代码时填充） |
| source_type | string | 用户获得此凭证的原因：reward / redemption / benefit |
| action_attach_id | string | 内部ID |
| action_id | string | 凭证来源的动作ID |
| action_name | string | 凭证来源的动作名称 |
| reward_tracking_id | string | 连接到动作表的ID |
| fixed_benefit_name | string | 用户获得凭证的固定福利 |
| additional_benefit_name | string | 用户获得凭证的额外福利 |
| redemption_type | string | 凭证获取方式：points / free |
| status | string | 凭证状态：pending / redeemed / removed / used |
| expiration_time | timestamp | 凭证过期日期 |
| remove_time | timestamp | 凭证从会员处移除的日期 |
| remove_source | string | 凭证移除方式：internal / wallet / api / admin |

---

### loyalty_exclusive_access_[customer_ID]

> 联系人通过积分获得或兑换的专属访问数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 专属访问代码被用户看到的时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| exclusive_access_name | string | 专属访问所属池名称 |
| exclusive_access_id | string | 专属访问所属池ID |
| source_type | string | 用户获得专属访问的原因：reward / redemption / benefit |
| action_attach_id | string | 内部ID |
| action_id | string | 专属访问来源的动作ID |
| action_name | string | 专属访问来源的动作名称 |
| reward_tracking_id | string | 连接到动作表的ID |
| fixed_benefit_name | string | 用户获得专属访问的固定福利 |
| redemption_type | string | 专属访问获取方式：points / free |
| status | string | 专属访问状态：new / used |
| additional_benefit_name | string | 用户获得专属访问的额外福利 |
| is_redeemed | boolean | 用户是否点击了凭证（true / false） |

---

### loyalty_actions_[customer_ID]

> Loyalty 动作与联系人完成情况数据
> 数据范围：2020-11-01 起

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 动作附加或完成的时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| attach_id | string | 附加到特定用户的动作唯一内部ID |
| snap_id | string | 供将来使用 |
| action_name | string | 动作名称 |
| action_master_type | string | 动作主类型：Purchase / Engagement / Join / Events / Referral |
| action_type | string | 动作类型：personalised / tier_based / default_join |
| action_status | string | 动作状态：attached / completed / canceled |
| reward_tracking_id | string | 用于连接积分、凭证和专属访问表的ID |
| order_id | string | 已完成购买动作对应的订单ID |
| trigger_id | string | 内部供将来使用 |
| valid_from | timestamp | 用户可以开始完成动作的日期 |
| valid_until | timestamp | 用户可以完成动作的截止日期 |

---

### loyalty_referral_codes_[customer_ID]

> 推荐计划中会员发出的推荐码数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | Smart Insight 也使用的 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 动作附加或完成的时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| action_id | string | 推荐计划ID |
| action_name | string | 推荐计划名称 |
| voucher_code | string | 会员发给朋友的优惠券代码 |
| voucher_value | float | 优惠券价值（如：$5、$10） |

---

### loyalty_referral_purchases_[customer_ID]

> 推荐用户的购买数据

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | 推荐朋友购买的会员 user_id 哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 动作附加到用户或完成的时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态的内部标识符 |
| action_id | string | 推荐计划ID |
| attach_id | string | 附加到特定用户的动作唯一内部ID |
| snap_id | string | 供将来使用 |
| reward_tracking_id | string | 用于连接会员因朋友购买获得的奖励 |
| friends_total_order | float | 被推荐用户的订单价值 |
| voucher_code | string | 会员发给朋友并在此购买中使用的优惠券代码 |
| voucher_value | float | 优惠券价值 |
| friends_order_timestamp | timestamp | 被推荐用户购买的时间 |
| friends_order_status | string | 被推荐用户订单状态：pending / confirmed / canceled |

---

## Analytics 数据视图

> 共 **3 张表**

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `revenue_attribution` | ✅ | ❌ 未映射 |
| 2 | `si_contacts` | ✅ | ❌ 未映射 |
| 3 | `si_purchases` | 否 | ❌ 无 contact_id |

---

### revenue_attribution_[customer_ID]

> 购买收入归因数据，识别营销活动带来的转化
> 数据范围：2023-08-07 起

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| contact_id | integer | SAP Emarsys 内部联系人ID |
| event_time | timestamp | 购买时间 |
| loaded_at | timestamp | 事件加载时间 |
| order_id | integer | 购买唯一ID |
| items | record | 购买商品 |
| items.item_id | string | 购买商品ID |
| items.price | float | 商品总销售价格（单价×数量） |
| items.quantity | float | 购买商品数量 |
| treatments | record | 购买归因的处理记录 |
| treatments.hardware_id | string | SDK 实例唯一ID |
| treatments.campaign_id | integer | 处理的活动ID |
| treatments.channel | string | 处理的渠道（如 email / in-app 等） |
| treatments.id | string | 处理的ID（如邮件消息ID等） |
| treatments.rti | record | 事件自动化程序相关信息 |
| treatments.rti.id | string | 事件自动化程序ID（如适用） |
| treatments.rti.run_id | string | 事件自动化程序运行ID（如适用） |
| treatments.ac | record | 受众自动化程序相关信息 |
| treatments.ac.id | integer | 受众自动化程序ID（如适用） |
| treatments.ac.run_id | string | 受众自动化程序运行ID（如适用） |
| treatments.email | record | 邮件特定元数据 |
| treatments.email.launch_id | integer | 处理的 launch ID |
| treatments.email.event_time | timestamp | 处理时间 |
| treatments.attributed_amount | float | 归因到处理的收入金额 |
| treatments.reason | record | 购买归因到处理的原因 |
| treatments.reason.type | string | 归因原因的事件类型（如 send / click 等） |
| treatments.reason.event_time | timestamp | 归因原因事件的时间（如点击时间等） |

---

### si_contacts_[customer_ID]

> Smart Insight 联系人生命周期计算数据
> 数据范围：2023-11-09 起

| 字段 | 类型 | 说明 |
|------|------|------|
| si_contact_id | integer | Smart Insight 系统内联系人唯一ID |
| contact_id | integer | Suite 中联系人唯一ID |
| contact_external_id | string | 客户用于用户识别的联系人唯一标识符 |
| load_date | timestamp | 数据在 SAP Emarsys 中的加载日期 |
| registered_on | date | 联系人注册日期 |
| contact_source | string | 联系人来源（如手动录入或注册表单名称） |
| number_of_purchases | integer | 联系人购买次数 |
| turnover | numeric | 联系人终身消费总额（含退款） |
| time_ranged_turnover | numeric | 货币区间时间范围内的联系人消费总额 |
| average_order_value | numeric | 联系人订单平均价值 |
| customer_lifecycle_status | string | 客户生命周期状态：Lead / First time buyer / Active / Defecting / Inactive |
| buyer_status | string | 买家状态（在 eRFM 设置页面配置） |
| lead_lifecycle_status | string | 潜在客户生命周期状态：New Lead / Cold Lead / Inactive Lead |
| last_order_date | date | 联系人最后下单日期 |
| last_engagement_date | date | 联系人最后访问网站/点击链接/购买的日期 |
| last_response_date | date | 联系人最后与客户互动的日期 |
| average_future_spend | numeric | 联系人未来消费的预测值 |
| is_generated | boolean | 是否为未识别联系人 |

---

### si_purchases_[customer_ID]

> Smart Insight 销售数据
> 数据范围：2023-12-04 起

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | string | 订单唯一ID |
| load_date | timestamp | 购买在 SAP Emarsys 中的加载日期 |
| si_contact_id | integer | Smart Insight 中联系人唯一ID |
| si_product_id | integer | Smart Insight 中产品唯一ID |
| product_external_id | string | 客户发送的产品ID |
| product_name | string | 产品名称 |
| purchase_date | date | 购买日期 |
| channel | string | 订单销售渠道：online / offline |
| quantity | numeric | 购买商品数量 |
| sales_amount | numeric | 商品总价格 |

---

## Email Reporting for Live Analytics 数据视图

> 共 **1 张表**
> **注意：此数据集通过 BI 平台（SAP Analytics Cloud / Tableau / Google Looker 等）的实时 BigQuery 连接器消费，不适用于数据提取，缺少可靠增量机制所需字段。目前处于有限客户试用阶段。**

| # | 表名 | 有 contact_id | 同步到 StarRocks |
|---|------|:---:|:---:|
| 1 | `reporting_email` | 否 | ❌ 无 contact_id |

---

### reporting_email

> 邮件活动实时分析报告数据

| 字段 | 类型 | 说明 |
|------|------|------|
| accountId | string | SAP Emarsys 账号标识符 |
| campaignId | string | 活动标识符 |
| campaignName | string | 活动名称 |
| campaignType | string | 活动类型 |
| campaignCategory | string | 活动分类 |
| campaignLanguage | string | 活动语言 |
| programId | integer | 活动的程序标识符 |
| parentCampaignId | string | 父活动标识符 |
| parentCampaignName | string | 父活动名称 |
| launchId | string | launch 标识符 |
| sendDateUtc | date | 邮件在 UTC 时区发送的日期 |
| sendDateMonthUtc | integer | 日历月份 |
| sendDateWeekUtc | integer | 日历周 |
| sendDateYearUtc | integer | 日历年 |
| startDateUtc | date | 活动开始日期 |
| sent | integer | 从 SAP Emarsys 邮件服务器发出的邮件数量 |
| delivered | integer | 已投递的邮件数量 |
| bounced | integer | 无法投递的邮件总数 |
| bouncedSoft | integer | 因临时问题无法投递的邮件数 |
| bouncedHard | integer | 因邮件地址不存在无法投递的邮件数 |
| bouncedBlock | integer | 因被垃圾邮件过滤器拦截无法投递的邮件数 |
| opened | integer | 已打开的邮件数量 |
| openedMobile | integer | 在移动设备上打开的邮件数量 |
| openedPrivacy | integer | 由 Apple 邮件隐私保护生成的打开数（iOS/macOS 设备） |
| clickedTotal | integer | 所有联系人的总点击次数 |
| clicked | integer | 唯一点击数（每个联系人每个活动只计一次） |
| clickedTotalAnonymous | integer | 匿名追踪联系人的总点击次数 |
| clickedAnonymous | integer | 匿名追踪联系人的唯一点击次数 |
| clickedMobile | integer | 使用移动设备的唯一点击数 |
| clickedMobileAnonymous | integer | 匿名追踪联系人的移动设备唯一点击数 |
| unsubscribed | integer | 退订此邮件的收件人数（含 List-unsubscribe 退订） |
| listUnsubscribed | integer | 通过邮件客户端 List-unsubscribe 功能退订的收件人数 |
| complained | integer | 将此邮件标记为垃圾邮件的收件人数 |
| canceled | integer | 因收件人从 launch 列表中移除而未发送的邮件数 |
| purchasedTotal | integer | 归因于活动的总购买次数 |
| revenueInAccountCurrency | numeric | 账号货币收入 |
| accountCurrency | string | 账号货币 |

---

## 12. Conversational Channel Data Views

### conversation_opens

视图名：`conversation_opens_[customer_ID]`

包含 Conversational 消息的打开事件数据。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| message_id | integer | 消息 ID |
| customer_id | integer | 账号唯一 ID |
| contact_id | integer | SAP Emarsys 内部联系人 ID（不可用于个人识别） |
| conversation_id | integer | 消息发送标识符，用于关联发送与打开事件 |
| event_time | timestamp | 打开事件被 Conversational 服务商记录的时间（UTC） |
| loaded_at | timestamp | 加载时间戳（UTC） |
| program_id | string | 发送消息的 Automation 程序 ID |
| program_type | string | Automation 程序类型（Audience-based 或 Event-based） |

**StarRocks 同步状态**：`conversation_opens` ❌ 未映射

---

### conversation_deliveries

视图名：`conversation_deliveries_[customer_ID]`

包含 Conversational 消息的投递信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| message_id | integer | 消息 ID |
| customer_id | integer | 账号唯一 ID |
| contact_id | integer | SAP Emarsys 内部联系人 ID（不可用于个人识别） |
| conversation_id | integer | 消息发送标识符，用于关联发送与打开事件 |
| status | string | 消息投递状态（如 DELIVERED、FAILED 等） |
| error_type | string | 投递失败时的错误类型：'INVALID_LINK'、'ACCOUNT_ISSUE' 或 'TEMPLATE_ISSUE' |
| error_message | string | 投递失败时 Conversational 服务商的详细错误描述 |
| event_time | timestamp | 投递事件被 Conversational 服务商记录的时间（UTC） |
| loaded_at | timestamp | 加载时间戳（UTC） |
| program_id | string | 发送消息的 Automation 程序 ID |
| program_type | string | Automation 程序类型（Audience-based 或 Event-based） |

**StarRocks 同步状态**：`conversation_deliveries` ❌ 未映射

---

### conversation_clicks

视图名：`conversation_clicks_[customer_ID]`

包含 Conversational 消息的追踪链接点击数据。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| message_id | integer | 消息 ID |
| customer_id | integer | 账号唯一 ID |
| contact_id | integer | SAP Emarsys 内部联系人 ID（不可用于个人识别） |
| conversation_id | integer | 消息发送标识符，用于关联发送与打开事件 |
| user_agent | string | 代表联系人点击的 user agent |
| event_time | timestamp | 追踪链接被点击的时间（UTC） |
| loaded_at | timestamp | 加载时间戳（UTC） |
| program_id | string | 发送消息的 Automation 程序 ID |
| program_type | string | Automation 程序类型（Audience-based 或 Event-based） |

**StarRocks 同步状态**：`conversation_clicks` ❌ 未映射

---

### conversation_sends

视图名：`conversation_sends_[customer_ID]`

包含 Conversational 消息发送信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| message_id | integer | 消息 ID |
| customer_id | integer | 账号唯一 ID |
| contact_id | integer | SAP Emarsys 内部联系人 ID（不可用于个人识别） |
| conversation_id | integer | 消息标识符，用于关联联系人的参与事件（打开、链接点击等） |
| event_time | timestamp | 系统将消息发送给 Conversational 服务商的时间（UTC） |
| loaded_at | timestamp | 加载时间戳（UTC） |
| program_id | string | 发送消息的 Automation 程序 ID |
| program_type | string | Automation 程序类型（Audience-based 或 Event-based） |

**StarRocks 同步状态**：`conversation_sends` ❌ 未映射

---

### conversation_messages

视图名：`conversation_messages_[customer_ID]`

包含 Conversational 消息的基本信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| message_id | integer | 消息 ID |
| channel | string | 消息渠道 |
| customer_id | integer | 账号唯一 ID |
| event_time | timestamp | 消息创建或修改的时间（UTC） |
| event_type | string | 触发数据写入的事件类型（create、update 或 delete） |
| loaded_at | timestamp | 加载时间戳（UTC） |
| message_type | string | 消息类型（如 card、text、template 等） |
| name | string | 消息名称 |
| template_id | string | 模板消息的模板标识符，非模板类型为 Null |
| template_type | string | 模板消息的模板类型，非模板类型为 Null |

**StarRocks 同步状态**：`conversation_messages` ❌ 未映射

---

## 13. Engagement Events Data Views

### engagement_events

视图名：`engagement_events`（无 customer_ID 后缀）

包含通过 Engagement Events 服务导入 SAP Emarsys 的所有事件数据。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| customer_id | integer | 账号唯一 ID |
| event_type | string | 事件类型的唯一 ID（在系统中配置） |
| event_id | string | 事件发生的唯一 ID |
| event_time | timestamp | 事件摄入时间（UTC） |
| contact_id | integer | SAP Emarsys 内部联系人 ID（不可用于个人识别） |
| event_data | JSON | 摄入事件的 JSON payload |
| loaded_at | timestamp | 加载时间戳（UTC） |
| partitiontime | timestamp | 分区日期 |

**StarRocks 同步状态**：`engagement_events` → `datanow_.t_retailevent`（event_key: `$emarsys_engagement_event`）✅ 已映射

---

## 14. Product Catalog Data Views

> **注意**：此功能目前处于 Pilot 阶段，仅对部分客户开放。需使用 Product Catalog Stream API。

### products_latest_state

视图名：`products_latest_state_[customer_ID]`

包含产品目录的最新状态，提供所有产品的关键属性、可用性、定价及本地化信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| customer_id | integer | 账号唯一 ID |
| item_id | string | 内部唯一产品 ID |
| event_time | timestamp | 商品最后更改时间 |
| loaded_at | timestamp | 事件加载时间 |
| item_group_id | string | 商品所属分组标识符 |
| pause | boolean | 产品是否暂停 |
| title | record | 产品标题 |
| title.default | string | 默认语言的标题 |
| title.locals | record | 包含其他语言标题列表的 record |
| title.locals.k | string | 语言区域的 key |
| title.locals.v | string | 该语言区域的标题 |
| link | record | 产品 URI |
| link.default | string | 默认语言的链接 |
| link.locals | record | 包含其他语言链接列表的 record |
| link.locals.k | string | 语言区域的 key |
| link.locals.v | string | 该语言区域的链接 |
| image | record | 产品图片 URI |
| image.default | string | 默认语言的图片 |
| image.locals | record | 包含其他语言图片列表的 record |
| image.locals.k | string | 语言区域的 key |
| image.locals.v | string | 该语言区域的图片 |
| zoom_image | record | 产品放大图片 URI |
| zoom_image.default | string | 默认语言的放大图片 |
| zoom_image.locals | record | 包含其他语言放大图片列表的 record |
| zoom_image.locals.k | string | 语言区域的 key |
| zoom_image.locals.v | string | 该语言区域的放大图片 |
| category | record | 产品类别 URI |
| category.default | array | 默认语言的类别数组 |
| category.locals | record | 包含其他语言类别列表的 record |
| category.locals.k | string | 语言区域的 key |
| category.locals.v | array | 该语言区域的类别 |
| available | record | 产品是否可用 |
| available.default | boolean | 默认语言的可用状态 |
| available.locals | record | 包含其他语言可用状态列表的 record |
| available.locals.k | string | 语言区域的 key |
| available.locals.v | boolean | 该语言区域的可用状态 |
| description | record | 产品描述 |
| description.default | string | 默认语言的描述 |
| description.locals | record | 包含其他语言描述列表的 record |
| description.locals.k | string | 语言区域的 key |
| description.locals.v | string | 该语言区域的描述 |
| msrp | record | 产品建议零售价 |
| msrp.default | float | 默认语言的建议零售价 |
| msrp.locals | record | 包含其他语言建议零售价列表的 record |
| msrp.locals.k | string | 语言区域的 key |
| msrp.locals.v | float | 该语言区域的建议零售价 |
| price | record | 产品价格 |
| price.default | float | 默认语言的价格 |
| price.locals | record | 包含其他语言价格列表的 record |
| price.locals.k | string | 语言区域的 key |
| price.locals.v | float | 该语言区域的价格 |
| currency | record | 产品价格货币 |
| currency.default | string | 默认语言的货币 |
| currency.locals | record | 包含其他语言货币列表的 record |
| currency.locals.k | string | 语言区域的 key |
| currency.locals.v | string | 该语言区域的货币 |
| availability | record | 产品可用状态（in_stock/out_of_stock/preorder/backorder） |
| availability.default | string | 默认语言的可用状态 |
| availability.locals | record | 包含其他语言可用状态列表的 record |
| availability.locals.k | string | 语言区域的 key |
| availability.locals.v | string | 该语言区域的可用状态 |
| brand | record | 产品品牌 |
| brand.default | array | 默认语言的品牌数组 |
| brand.locals | record | 包含其他语言品牌列表的 record |
| brand.locals.k | string | 语言区域的 key |
| brand.locals.v | array | 该语言区域的品牌 |
| customs | record | 自定义字段（键值对） |
| customs.k | string | 自定义字段的 key |
| customs.v | string | 自定义字段的值 |

**StarRocks 同步状态**：`products_latest_state` → `dts_` ✅ 已映射

---

### products_change_history

视图名：`products_change_history_[customer_ID]`

包含产品目录的历史变更记录，记录每次更新、新增或删除操作，提供产品数据随时间演变的详细时间线。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| customer_id | integer | 账号唯一 ID |
| item_id | string | 内部唯一产品 ID |
| event_time | timestamp | 商品最后更改时间 |
| loaded_at | timestamp | 事件加载时间 |
| delete | boolean | 是否为删除事件（true 表示已删除，否则为 NULL） |
| new_value | record | 变更事件后商品的更新值（字段结构见下表） |
| old_value | record | 变更事件前商品的原有值（字段结构见下表） |

**new_value / old_value 内部字段结构：**

| 字段名 | 类型 | 描述 |
|--------|------|------|
| event_time | timestamp | 商品最后更改时间 |
| item_group_id | string | 商品所属分组标识符 |
| pause | boolean | 产品是否暂停 |
| partitiontime | timestamp | 分区时间 |
| title | record | 产品标题 |
| title.default | string | 默认语言的标题 |
| title.locals | record | 包含其他语言标题列表的 record |
| title.locals.k | string | 语言区域的 key |
| title.locals.v | string | 该语言区域的标题 |
| link | record | 产品 URI |
| link.default | string | 默认语言的链接 |
| link.locals | record | 包含其他语言链接列表的 record |
| link.locals.k | string | 语言区域的 key |
| link.locals.v | string | 该语言区域的链接 |
| image | record | 产品图片 URI |
| image.default | string | 默认语言的图片 |
| image.locals | record | 包含其他语言图片列表的 record |
| image.locals.k | string | 语言区域的 key |
| image.locals.v | string | 该语言区域的图片 |
| zoom_image | record | 产品放大图片 URI |
| zoom_image.default | string | 默认语言的放大图片 |
| zoom_image.locals | record | 包含其他语言放大图片列表的 record |
| zoom_image.locals.k | string | 语言区域的 key |
| zoom_image.locals.v | string | 该语言区域的放大图片 |
| category | record | 产品类别 URI |
| category.default | array | 默认语言的类别数组 |
| category.locals | record | 包含其他语言类别列表的 record |
| category.locals.k | string | 语言区域的 key |
| category.locals.v | array | 该语言区域的类别 |
| available | record | 产品是否可用 |
| available.default | boolean | 默认语言的可用状态 |
| available.locals | record | 包含其他语言可用状态列表的 record |
| available.locals.k | string | 语言区域的 key |
| available.locals.v | boolean | 该语言区域的可用状态 |
| description | record | 产品描述 |
| description.default | string | 默认语言的描述 |
| description.locals | record | 包含其他语言描述列表的 record |
| description.locals.k | string | 语言区域的 key |
| description.locals.v | string | 该语言区域的描述 |
| msrp | record | 产品建议零售价 |
| msrp.default | float | 默认语言的建议零售价 |
| msrp.locals | record | 包含其他语言建议零售价列表的 record |
| msrp.locals.k | string | 语言区域的 key |
| msrp.locals.v | float | 该语言区域的建议零售价 |
| price | record | 产品价格 |
| price.default | float | 默认语言的价格 |
| price.locals | record | 包含其他语言价格列表的 record |
| price.locals.k | string | 语言区域的 key |
| price.locals.v | float | 该语言区域的价格 |
| currency | record | 产品价格货币 |
| currency.default | string | 默认语言的货币 |
| currency.locals | record | 包含其他语言货币列表的 record |
| currency.locals.k | string | 语言区域的 key |
| currency.locals.v | string | 该语言区域的货币 |
| availability | record | 产品可用状态（in_stock/out_of_stock/preorder/backorder） |
| availability.default | string | 默认语言的可用状态 |
| availability.locals | record | 包含其他语言可用状态列表的 record |
| availability.locals.k | string | 语言区域的 key |
| availability.locals.v | string | 该语言区域的可用状态 |
| brand | record | 产品品牌 |
| brand.default | array | 默认语言的品牌数组 |
| brand.locals | record | 包含其他语言品牌列表的 record |
| brand.locals.k | string | 语言区域的 key |
| brand.locals.v | array | 该语言区域的品牌 |
| customs | record | 自定义字段（键值对） |
| customs.k | string | 自定义字段的 key |
| customs.v | string | 自定义字段的值 |

**StarRocks 同步状态**：`products_change_history` ❌ 未映射
