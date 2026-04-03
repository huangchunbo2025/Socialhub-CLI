# Emarsys Open Data - BigQuery 数据视图字段手册

> 来源：SAP Help Portal - Open Data Data Views
> 命名规则：`{view_name}_[customer_ID]`，如 `email_sends_12345`

---

## 通用注意事项

- **重复率**：约 0.001%，需要去重处理
- **禁止 SELECT \***：SAP 可能随时增删字段，必须显式指定字段
- **联系人删除**：联系人删除后，其历史数据同步删除
- **contact_id**：Emarsys 内部 ID，不建议作为外部系统唯一标识符
- **60天限制**：邮件活动发生 60 天后，无法关联到具体联系人

---

## Email 数据视图

> 官方文档：[Email Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf396da74c11014b68bc1fdabe6e2ea.html)

### email_campaigns_v2_[customer_ID]

> 邮件活动元数据（推荐使用 v2，旧版 email_campaigns 即将废弃）
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
| email_sent_at | timestamp | 发送时间（UTC） |
| event_time | timestamp | 退回时间（UTC） |
| launch_id | integer | 批次发送唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | integer | 单封邮件唯一ID |
| dsn_reason | string | SMTP 服务器原始退回响应码 |

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

## SMS 数据视图

> 官方文档：[SMS Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3aa0e74c110149dd0dd5a229aa19f.html)

### sms_campaigns_[customer_ID]

> 短信活动元数据
> 数据范围：2017-09-19 起

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动ID |
| name | string | 活动名称 |
| sender_name | string | 发送方名称 |
| message | string | 短信内容 |
| include_unsubscribe_link | boolean | 是否包含退订链接 |
| trigger_type | string | 触发类型：batch_now / ac / batch_later |
| event_time | timestamp | 活动创建/修改时间（UTC） |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| business_unit | string | 服务商名称（当前始终为 null） |

---

### sms_sends_[customer_ID]

> 短信发送记录
> 数据范围：2017-09-19 起

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | string | 消息唯一ID |
| launch_id | integer | 批次发送唯一ID |
| contact_id | integer | Emarsys 内部联系人ID |
| program_id | integer | 所属程序ID（2020-10-05后为NULL） |
| campaign_id | integer | 活动ID |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| event_time | timestamp | 发送时间（UTC） |
| treatments.rti.id | string | 事件触发自动化程序ID |
| treatments.rti.run_id | string | 自动化程序运行实例ID |
| treatments.ac.id | integer | 受众自动化程序ID |
| treatments.ac.run_id | string | 受众自动化程序运行实例ID |

---

### sms_send_reports_[customer_ID]

> 短信投递状态报告
> 数据范围：2017-09-19 起

| 字段 | 类型 | 说明 |
|------|------|------|
| bounce_type | string | 退回原因 |
| campaign_id | integer | 活动ID |
| contact_id | integer | Emarsys 内部联系人ID |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 发送时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| message_id | string | 消息唯一ID |
| status | string | 短信投递状态（由短信服务商提供） |

---

### sms_clicks_[customer_ID]

> 短信链接点击记录
> 数据范围：2017-09-19 起

| 字段 | 类型 | 说明 |
|------|------|------|
| launch_id | integer | 批次发送唯一ID |
| contact_id | integer | Emarsys 内部联系人ID |
| link_id | integer | 链接ID |
| is_dry_run | boolean | 是否测试用URL |
| user_agent | string | 代表联系人点击的 User Agent |
| campaign_id | integer | 活动ID |
| event_time | timestamp | 点击时间（UTC） |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

### sms_unsubscribes_[customer_ID]

> 短信退订记录
> 数据范围：2017-09-19 起

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | Emarsys 内部联系人ID |
| unsubscribe_type | string | 退订类型 |
| event_time | timestamp | 退订时间（UTC） |
| campaign_id | integer | 活动ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| customer_id | integer | 账号唯一ID |

---

## Web Push 数据视图

> 官方文档：[Web Push Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf39a6174c11014b8b0b3ed179c7ec0.html)

### web_push_campaigns_[customer_ID]

> Web Push 活动信息

| 字段 | 类型 | 说明 |
|------|------|------|
| internal_campaign_id | integer | 内部活动唯一标识 |
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | 每个客户的活动唯一标识 |
| name | string | 活动名称 |
| source | record | 活动来源记录体 |
| source.type | string | 来源类型 |
| source.id | integer | 来源唯一标识 |
| message | record | 活动消息记录体 |
| message.language | string | 消息语言 |
| message.title | string | 消息标题 |
| message.body | string | 消息正文 |
| domain_code | string | 域名唯一代码 |
| domain | string | 域名 |
| settings | record | 活动设置记录体 |
| settings.k | string | 设置键 |
| settings.v | string | 设置值 |
| segment_id | integer | 受众分群唯一标识 |
| recipient_source_id | integer | 收件人来源数字ID |
| data | string | 自定义数据（JSON字符串） |
| launched_at | timestamp | 活动启动时间 |
| scheduled_at | timestamp | 活动计划时间 |
| created_at | timestamp | 活动创建时间 |
| deleted_at | timestamp | 活动删除时间 |
| event_time | timestamp | 活动创建/修改时间（UTC），**增量同步 watermark 字段** |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

## Mobile Engage 数据视图

> 官方文档：[Mobile Engage Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf39df074c11014ab76cda4fc072545.html)

### push_campaigns_[customer_ID]

> App 推送活动信息（2017-11-29 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| campaign_id | integer | 活动唯一ID |
| customer_id | integer | 账号唯一ID |
| application_id | integer | 应用唯一ID |
| name | string | 推送活动名称 |
| source | string | 来源：ac/broadcast/segment/me_segment |
| event_time | timestamp | 活动最后更新时间（UTC） |
| created_at | timestamp | 活动创建时间（UTC） |
| launched_at | timestamp | 活动启动时间 |
| scheduled_at | timestamp | 活动计划时间 |
| deleted_at | timestamp | 活动删除时间 |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| segment_id | integer | 应用的分群ID |
| recipient_source_id | integer | 收件人来源数字ID |
| push_internal_campaign_id | integer | Push 渠道内部活动ID |
| message | record | 消息记录体（key=语言代码，value=消息内容） |
| android_settings | record | Android 专属设置 |
| ios_settings | record | iOS 专属设置 |
| data | record | 自定义数据 |

---

## Mobile Wallet 数据视图

> 官方文档：[Mobile Wallet Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3b4fa74c11014bb6ee55bfb9f08f4.html)

### wallet_campaigns_[customer_ID]

> 移动钱包活动（2023-11-08 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | integer | Suite 提供的活动唯一ID |
| internal_campaign_id | UUID | Wallet Service 内部活动ID |
| wallet_config_id | UUID | Wallet 配置唯一ID |
| name | string | 活动名称 |
| status | string | 启动状态：IN_DRAFT / READY_TO_LAUNCH |
| template_type | string | 模板类型 |
| created_at | timestamp | 活动创建时间 |
| updated_at | timestamp | 活动修改时间 |
| archived_at | timestamp | 活动归档时间 |
| launched_at | timestamp | 活动启动时间 |
| event_time | timestamp | 影响活动的事件时间 |
| loaded_at | timestamp | 事件加载时间 |

### wallet_passes_[customer_ID]

> 移动钱包通行证记录（2023-11-08 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| campaign_id | UUID | Wallet Service 中通行证所属活动ID |
| contact_id | integer | Emarsys 内部联系人ID |
| serial_number | UUID | 通行证序列号 |
| platform | string | 平台 |
| template_type | string | 模板类型 |
| event | string | 事件类型 |
| event_time | timestamp | 事件时间 |
| loaded_at | timestamp | 加载时间 |

---

## Web Channel 数据视图

> 官方文档：[Web Channel Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3a1ff74c11014a3f6ab8e2f7f7d3d.html)

### webchannel_events_enhanced_[customer_ID]

> 网页渠道事件（2018-08 起）

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| campaign_id | string | aAaAAa1-Aa | 活动唯一ID |
| ad_id | string | 1 | 活动版本（广告）ID |
| customer_id | integer | 1111111111 | 账号唯一ID |
| contact_id | integer | 1111111111 | Emarsys 内部联系人ID |
| event_type | string | show | 事件类型：show/submit/click |
| event_time | timestamp | | 事件时间（UTC） |
| loaded_at | timestamp | | 数据平台加载时间（UTC） |
| platform | string | Windows | 设备平台 |
| md5 | string | | user_agent 的 MD5 哈希 |
| is_mobile | boolean | False | 是否移动设备 |
| is_anonymized | boolean | False | 是否已匿名化 |
| user_agent | string | | 设备和浏览器信息 |

---

## Predict 数据视图

> 官方文档：[Predict Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3a65b74c1101492aec2ea991e9646.html)

### session_categories_[customer_ID]

> 用户浏览分类记录（2017-11-20 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户标识 |
| user_id_type | string | 用户ID类型（email hash 或 external ID） |
| user_id_field_id | integer | 平台中包含此信息的列 |
| contact_id | integer | Emarsys 内部联系人ID |
| category | string | 用户浏览的分类名称 |
| event_time | timestamp | 浏览时间（UTC） |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

### session_purchases_[customer_ID]

> 用户购买记录（2017-11-20 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户标识 |
| user_id_type | string | 用户ID类型 |
| user_id_field_id | integer | 平台中包含此信息的列 |
| contact_id | integer | Emarsys 内部联系人ID |
| items | record | 购买商品列表 |
| items.item_id | string | 购买商品唯一ID |
| items.price | float | 购买时商品价格 |
| items.quantity | float | 购买数量 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 购买时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

## Event 数据视图

> 官方文档：[Event Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3ada674c1101496b9bf708157b4b7.html)

### external_events_[customer_ID]

> 通过 API 触发的外部事件

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | Emarsys 内部联系人ID |
| event_id | string | 平台生成的事件唯一标识 |
| event_time | timestamp | 事件发生时间（UTC） |
| event_type_id | integer | 外部事件ID |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

### custom_events_[customer_ID]

> 自定义事件记录

| 字段 | 类型 | 说明 |
|------|------|------|
| contact_id | integer | Emarsys 内部联系人ID |
| event_id | string | 事件唯一ID |
| event_time | timestamp | 事件发生时间（UTC） |
| event_type | string | 事件类型 |
| customer_id | integer | 账号唯一ID |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| partitiontime | timestamp | 数据分区时间（UTC） |

---

## Automation 数据视图

> 官方文档：[Automation Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/8c74e855e2e049cba195ca88920d4db9.html)

### automation_node_executions_[customer_ID]

> 自动化程序节点执行记录（2022-11-01 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| ac_program_id | integer | 受众自动化程序ID（事件触发程序时为NULL） |
| rti_program_id | string | 事件触发自动化程序ID（受众程序时为NULL） |
| node_id | string | 节点ID |
| execution_phase | string | 执行阶段：START / END |
| execution_id | string | 节点执行唯一ID |
| testing_mode | boolean | 是否为测试模式进入 |
| event_time | timestamp | 执行时间（UTC） |
| participants.execution_result | string | 执行结果：PASSED 或错误代码 |
| participants.route_index | integer | 过滤节点后联系人继续的路由索引 |
| participants.child_node_id | string | A/B 分流节点中联系人继续的子节点ID |
| participants.continued_in_program | boolean | 联系人是否继续到下一节点 |
| participants.count | integer | 联系人列表中的联系人数或单个联系人为1 |
| participants.contact_list_id | string | 批量执行的联系人列表ID |

---

## Loyalty 数据视图

> 官方文档：[Loyalty Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3b11f74c11014bc7cef60c8df1d9f.html)

### loyalty_contact_points_state_latest_[customer_ID]

> 联系人积分状态最新快照（2019-11-01 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | 用户ID的哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 事件发生时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| plan_id | string | 联系人所属积分计划ID |
| join_time | timestamp | 加入时间 |
| tier | string | 当前积分等级名称 |
| tier_entry_time | timestamp | 进入当前等级的时间 |
| balance_points | float | 余额积分数 |
| status_points | float | 状态积分数 |
| pending_points | float | 待确认积分数 |
| points_to_be_expired | float | 即将过期的积分数 |

### loyalty_points_earned_redeemed_[customer_ID]

> 积分获取与兑换明细（2019-11-01 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| external_id | string | 用户ID的哈希版本 |
| customer_id | integer | 账号唯一ID |
| event_time | timestamp | 事件发生时间（UTC） |
| loaded_at | timestamp | 数据平台加载时间（UTC） |
| contact_state_id | string | 联系人当前状态内部标识 |
| points | float | 给予或扣减的积分数（负值为扣减） |
| points_type | string | 积分类型：Balance 或 Status |

---

## Analytics 数据视图

> 官方文档：[Analytics Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf3b87c74c1101488d898cf917a37a8.html)

### revenue_attribution_[customer_ID]

> 收入归因数据（2023-08-07 起）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| contact_id | integer | Emarsys 内部联系人ID（无联系人信息时为null） |
| event_time | timestamp | 购买时间（UTC） |
| loaded_at | timestamp | 事件加载时间（UTC） |
| order_id | integer | 购买订单ID |
| items | record | 购买商品记录体 |
| items.item_id | string | 购买商品ID |
| items.price | float | 商品总销售价格（单价×数量） |
| items.quantity | float | 购买数量 |
| treatments | record | 购买归因的营销活动记录体 |
| treatments.campaign_id | integer | 归因活动ID |
| treatments.channel | string | 归因渠道（email/in-app 等） |
| treatments.id | string | 归因处理唯一ID |
| treatments.hardware_id | string | SDK 实例唯一ID |

---

## Conversational Channel 数据视图

> 官方文档：[Conversational Channel Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/91765f2992044c2b9849c286097d120e.html)

### conversation_opens_[customer_ID]

> 对话渠道打开记录（WhatsApp 等）

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | integer | 消息ID |
| customer_id | integer | 账号唯一ID |
| contact_id | integer | Emarsys 内部联系人ID |
| conversation_id | integer | 关联发送与打开事件的标识符 |
| event_time | timestamp | 打开事件时间（UTC） |
| loaded_at | timestamp | 加载时间（UTC） |
| program_id | string | 消息发送来源程序ID |
| program_type | string | 程序类型 |

### conversation_deliveries_[customer_ID]

> 对话渠道投递状态记录

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | integer | 消息ID |
| customer_id | integer | 账号唯一ID |
| contact_id | integer | Emarsys 内部联系人ID |
| conversation_id | integer | 关联发送与打开事件的标识符 |
| status | string | 投递状态（DELIVERED/FAILED 等） |
| error_type | string | 投递失败类型：INVALID_LINK/ACCOUNT_ISSUE/TEMPLATE_ISSUE |
| error_message | string | 服务商详细错误描述 |
| event_time | timestamp | 投递时间（UTC），**增量同步 watermark 字段** |
| loaded_at | timestamp | 数据平台加载时间（UTC） |

---

## Engagement Events 数据视图

> 官方文档：[Engagement Events Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/c1d002dee47b44db815e2377abce8668.html)

### engagement_events

> 导入到 Emarsys 的所有事件数据（**注意：查询时必须过滤 partitiontime**）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| event_type | string | 事件类型唯一ID |
| event_id | string | 事件发生唯一ID |
| event_time | timestamp | 事件摄入时间（UTC） |
| contact_id | integer | Emarsys 内部联系人ID |
| event_data | JSON | 事件的 JSON payload |
| loaded_at | timestamp | 加载时间（UTC） |
| partitiontime | timestamp | 分区日期（UTC）**查询必须指定** |

---

## Product Catalog 数据视图

> 官方文档：[Product Catalog Data Views](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/4dfb0564bda6432dab4f3165747b8bb2.html)
> **注意：此功能目前仅对部分客户开放 Pilot 阶段**

### products_latest_state_[customer_ID]

> 商品目录最新状态（需要 Product Catalog Stream API）

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_id | integer | 账号唯一ID |
| item_id | string | 商品内部唯一ID |
| event_time | timestamp | 商品最后修改时间（UTC） |
| loaded_at | timestamp | 事件加载时间 |
| item_group_id | string | 商品所属分组标识 |
| pause | boolean | 商品是否暂停 |
| title.default | string | 默认语言标题 |
| title.locals | record | 多语言标题列表 |
| link.default | string | 默认语言商品链接 |
| link.locals | record | 多语言商品链接列表 |
| image.default | string | 默认语言商品图片URL |
| image.locals | record | 多语言商品图片列表 |
