# Skills Store Web Design Language

本文件用于约束 `skills_store_web/` 下后续原型页面的设计方向，确保不同 AI 继续扩展时不会把站点做成多套风格。

## 1. 设计目标

- 这是一个统一站点，不是“商店站点 + 后台模板 + 管理系统”三套产品。
- 所有页面都必须看起来属于同一个 `SocialHub.AI Skills Store` 体系。
- 后台页可以提高信息密度，但不能脱离公开商店页的颜色、圆角、阴影、间距和气质。
- 页面要“企业级、精致、可信”，不是通用 SaaS 模板感。

## 2. 视觉基因

### 2.1 颜色

以 [`styles.css`](C:\Users\86185\Socialhub-CLI\skills_store_web\styles.css) 中变量为准，不要重新定义一套主色。

- `--primary: #121C3D`
- `--accent: #00C9A7`
- `--accent-gradient: linear-gradient(135deg, #00C9A7 0%, #4ADE80 50%, #A3E635 100%)`
- `--success: #10b981`
- `--warning: #f59e0b`
- `--error: #ef4444`
- `--text: #1f2937`
- `--text-secondary: #6b7280`
- `--bg-secondary: #f9fafb`
- `--border: #e5e7eb`

使用规则：

- 顶部导航、Hero 主背景、关键标题强调统一使用 `--primary`
- 主按钮统一使用 `--accent-gradient`
- 成功/警告/错误只用于状态，不拿来做大面积主视觉
- 页面背景优先使用浅色渐变或白底，不做重暗黑风

### 2.2 字体

- 统一使用 `Inter`
- 标题要紧凑、偏强势，正文保持克制
- 不要混入新的字体族

### 2.3 形状

- 全站倾向大圆角，不用尖锐矩形
- 卡片常用圆角：`20px` 到 `28px`
- 小控件和胶囊标签常用圆角：`999px`

### 2.4 阴影

- 页面主卡片用柔和阴影，强调“悬浮但不厚重”
- 优先复用 `styles.css` 的 `--shadow / --shadow-lg / --shadow-xl`
- 不要用很黑、很重的投影

## 3. 页面骨架

当前站点有两种骨架，只能在这两种里扩展。

### 3.1 商店类页面骨架

适用：

- `index.html`
- `installed.html`

结构：

1. 固定顶部导航
2. 深色 Hero 区
3. 主内容区使用 `.container`
4. 底部 footer

特征：

- Hero 必须有氛围层：径向渐变、淡光斑、轻微空间感
- 主内容区是白底或浅渐变背景
- 更适合搜索、列表、介绍、入口页

### 3.2 工作台类页面骨架

适用：

- 开发者页
- 管理员页

结构：

1. 固定顶部导航
2. 深色 Hero 区
3. Hero 下方悬浮一个白色工作区容器
4. 工作区内部是 `左侧导航 + 右侧主内容`
5. 底部 footer

特征：

- 不要直接从导航后面接一整块后台布局
- 必须保留上方 Hero，保证和商店页属于同一站点
- 工作区容器要有大圆角、大白底、明显悬浮感

## 4. 布局规则

### 4.1 全局宽度

- 使用 `.container`
- 最大宽度跟现有站点一致：`1280px`
- 左右留白不要小于 `24px`

### 4.2 工作区布局

当前工作台页统一用：

- 左栏约 `248px`
- 主内容 `minmax(0, 1fr)`
- 栏间距约 `24px`

不要擅自改成：

- 极窄侧栏图标模式
- 三栏布局
- 满屏无边界后台布局

### 4.3 卡片节奏

常用卡片层级：

1. 页面主容器：大圆角、白底、强阴影
2. 模块卡片：白底、边框、较轻阴影
3. 列表子项：浅灰或白底、小卡片感

一个页面里不要出现太多不同圆角和阴影级别。

## 5. 组件约束

### 5.1 顶部导航

所有页面必须保留统一导航：

- 商店
- 已安装
- 开发者
- 管理员
- 文档或对应动作按钮

要求：

- logo 结构保持一致
- 导航高度保持 `64px`
- 当前页高亮用 `.nav-link.active`

### 5.2 Hero

Hero 是站点识别核心，后续页面不能省略。

Hero 应包含：

- 页面身份 badge
- 强标题
- 解释性副标题
- 1 到 3 个 meta chip 或 action button

不要：

- 只放一个小标题就结束
- 用后台面包屑替代 Hero

### 5.3 侧边导航

工作台页左侧导航规则：

- 导航项用白底侧栏内部的浅色 active 态
- active 态是浅绿色/浅青绿色背景，不是深色反白
- 导航链接必须是真实页面链接，不依赖单页切换

### 5.4 卡片

模块卡片标准：

- 白底
- 1px 边框
- 大圆角
- 轻阴影
- 内边距统一在 `22px` 到 `24px`

### 5.5 表格

表格不是传统后台强网格风，而是“卡片式表格”。

要求：

- 表格外层先包一个大卡片
- 表头用浅灰背景
- 行 hover 轻微变色即可
- 操作列优先用文本链接式操作

### 5.6 按钮

按钮统一复用：

- `.btn`
- `.btn-primary`
- `.btn-outline`
- `.btn-sm`
- `.btn-block`

规则：

- 主动作只允许一个最强按钮
- 次要动作用 outline
- 危险动作可用红色自定义，但只限拒绝、吊销这类场景

### 5.7 状态表达

统一使用“圆点 + 文本”或“胶囊标签”。

例如：

- 绿色：已发布 / 有效 / 最新
- 黄色：审核中 / 待处理 / 有更新
- 红色：拒绝 / 错误 / 风险

不要把状态做成五颜六色的大块。

### 5.8 Modal / Drawer / Tab

交互组件规则：

- Modal 延续 `index.html` 的弹层语言
- Drawer 是工作台页的补充面板，不应该压过主内容
- Tab 用圆角胶囊按钮，不用传统下划线 tab

## 6. 内容语气

- 文案偏产品化、企业化、可信
- 不要出现过度营销、俏皮化表达
- 开发者页强调流程、审核、版本、权限
- 管理员页强调审核、证书、统计、追踪
- 所有描述尽量具体，不写空泛占位词

## 7. 页面实现策略

后续新增页面时，优先从现有页面复制，而不是重新发明结构。

推荐基底：

- 商店类新页：从 [`index.html`](C:\Users\86185\Socialhub-CLI\skills_store_web\index.html) 或 [`installed.html`](C:\Users\86185\Socialhub-CLI\skills_store_web\installed.html) 扩展
- 开发者类新页：从 [`developer-portal.html`](C:\Users\86185\Socialhub-CLI\skills_store_web\developer-portal.html) 扩展
- 管理员类新页：从 [`admin-portal.html`](C:\Users\86185\Socialhub-CLI\skills_store_web\admin-portal.html) 扩展

不要：

- 新建一份完全不同的页面骨架
- 引入新的 CSS 文件
- 推翻现有 Hero + Workspace 模式

## 8. 链接和信息架构

当前页面集合：

- `index.html`
- `installed.html`
- `developer-portal.html`
- `developer-skills.html`
- `developer-submit.html`
- `developer-settings.html`
- `admin-portal.html`
- `admin-certificates.html`
- `admin-catalog.html`
- `admin-stats.html`

要求：

- 顶部导航互相可达
- 开发者侧栏页面互相可达
- 管理员侧栏页面互相可达
- 页脚至少保留主要入口，不要出现死链接占位

## 9. AI 扩页清单

后续 AI 新增页面时必须检查：

1. 是否使用了 `styles.css` 里的颜色变量
2. 是否保留统一的顶部导航
3. 是否有 Hero，而不是直接进入内容
4. 是否沿用了商店类或工作台类骨架之一
5. 卡片圆角、边框、阴影是否与现有页一致
6. 页面入口和菜单是否都能点通
7. 是否避免做成通用后台模板风

## 10. 禁止事项

- 不要引入新的视觉主色
- 不要改成纯后台管理系统模板风
- 不要移除 Hero
- 不要做满屏密集表格页面而没有卡片容器
- 不要引入 Bootstrap、Tailwind、jQuery、React 等框架
- 不要新建第二套全局 CSS
- 不要把开发者页和管理员页做成与商店页无关的风格

