# SocialHub.AI CLI 详细设计文档

**版本**: 1.0.0
**更新日期**: 2024-03
**作者**: SocialHub.AI 技术团队

---

## 目录

1. [系统概述](#1-系统概述)
2. [架构设计](#2-架构设计)
3. [模块设计](#3-模块设计)
4. [数据模型](#4-数据模型)
5. [API 设计](#5-api-设计)
6. [AI 模块设计](#6-ai-模块设计)
7. [Skills Store 设计](#7-skills-store-设计)
8. [安全设计](#8-安全设计)
9. [扩展性设计](#9-扩展性设计)
10. [部署架构](#10-部署架构)

---

## 1. 系统概述

### 1.1 项目背景

SocialHub.AI CLI 是 SocialHub.AI 客户互动平台（CEP）的命令行工具，旨在为数据分析师和营销经理提供高效的数据查询、分析和营销管理能力。

### 1.2 设计目标

| 目标 | 描述 |
|------|------|
| **易用性** | 支持自然语言交互，降低使用门槛 |
| **灵活性** | 支持 API 模式和本地模式双模式切换 |
| **可扩展性** | 通过 Skills Store 扩展功能 |
| **安全性** | 技能签名验证，权限控制 |
| **可视化** | 支持图表生成和 HTML 报告 |

### 1.3 技术选型

```
┌─────────────────────────────────────────────────────────────┐
│                      技术栈选型                              │
├─────────────────┬───────────────────────────────────────────┤
│ 开发语言        │ Python 3.10+                              │
│ CLI 框架        │ Typer (基于 Click)                        │
│ 终端美化        │ Rich                                      │
│ HTTP 客户端     │ httpx (支持异步)                          │
│ 数据处理        │ Pandas                                    │
│ 数据验证        │ Pydantic v2                               │
│ 图表生成        │ Matplotlib                                │
│ AI 集成         │ Azure OpenAI / OpenAI                     │
│ 配置管理        │ JSON + 环境变量                           │
└─────────────────┴───────────────────────────────────────────┘
```

### 1.4 系统边界

```
                    ┌─────────────────────────────────────┐
                    │         SocialHub.AI Platform       │
                    │  ┌─────────────────────────────────┐│
                    │  │         REST API                ││
                    │  └─────────────────────────────────┘│
                    └─────────────────────────────────────┘
                                      ▲
                                      │ HTTPS
                                      │
┌─────────────────────────────────────┼─────────────────────────────────────┐
│                                     │                                     │
│  ┌──────────────────────────────────┴──────────────────────────────────┐  │
│  │                      SocialHub.AI CLI                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │  │
│  │  │   Commands  │  │  AI Module  │  │   Output    │  │   Skills   │  │  │
│  │  │   Module    │  │  (NLP)      │  │   Module    │  │   Store    │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                     │                                     │
│                    SocialHub.AI CLI │                                     │
└─────────────────────────────────────┼─────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │         Local Data Files          │
                    │    (CSV, Excel, JSON)             │
                    └───────────────────────────────────┘
```

---

## 2. 架构设计

### 2.1 整体架构

```
socialhub/
├── cli/
│   ├── __init__.py              # 版本信息
│   ├── main.py                  # CLI 入口点（智能路由）
│   ├── config.py                # 配置管理
│   │
│   ├── commands/                # 命令模块
│   │   ├── __init__.py
│   │   ├── ai.py               # AI 自然语言模块
│   │   ├── analytics.py        # 数据分析命令
│   │   ├── customers.py        # 客户管理命令
│   │   ├── segments.py         # 分群管理命令
│   │   ├── tags.py             # 标签管理命令
│   │   ├── campaigns.py        # 营销活动命令
│   │   ├── coupons.py          # 优惠券命令
│   │   ├── points.py           # 积分命令
│   │   ├── messages.py         # 消息命令
│   │   ├── skills.py           # 技能管理命令
│   │   └── config_cmd.py       # 配置命令
│   │
│   ├── api/                     # API 客户端层
│   │   ├── __init__.py
│   │   ├── client.py           # HTTP 客户端
│   │   └── models.py           # API 数据模型
│   │
│   ├── local/                   # 本地数据处理层
│   │   ├── __init__.py
│   │   ├── reader.py           # 数据读取器
│   │   └── processor.py        # 数据处理器
│   │
│   ├── output/                  # 输出格式化层
│   │   ├── __init__.py
│   │   ├── table.py            # 表格输出
│   │   ├── chart.py            # 图表生成
│   │   ├── export.py           # 数据导出
│   │   └── report.py           # HTML 报告生成
│   │
│   └── skills/                  # Skills Store 模块
│       ├── __init__.py
│       ├── models.py           # 技能数据模型
│       ├── registry.py         # 本地注册表
│       ├── store_client.py     # 商店 API 客户端
│       ├── security.py         # 安全验证
│       ├── manager.py          # 技能管理器
│       └── loader.py           # 技能加载器
│
├── data/                        # 示例数据
│   ├── customers.csv
│   └── orders.csv
│
├── docs/                        # 文档
│   ├── README.md               # 产品文档
│   └── DESIGN.md               # 设计文档
│
└── tests/                       # 测试
    ├── __init__.py
    ├── test_commands/
    ├── test_api/
    └── test_skills/
```

### 2.2 分层架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Presentation Layer                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  CLI Commands  │  AI Natural Language  │  Output Formatters       │  │
│  │  (Typer)       │  (Azure OpenAI)       │  (Rich, Matplotlib)      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│                           Business Logic Layer                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Analytics     │  Customer Mgmt  │  Campaign Mgmt  │  Skills Mgmt │  │
│  │  Service       │  Service        │  Service        │  Service     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│                           Data Access Layer                             │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │      API Client             │  │      Local Data Reader          │  │
│  │  (httpx → REST API)         │  │  (Pandas → CSV/Excel)           │  │
│  └─────────────────────────────┘  └─────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│                           Infrastructure Layer                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Configuration  │  Logging  │  Security  │  Error Handling        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 数据流设计

#### 2.3.1 API 模式数据流

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  User   │───▶│   CLI   │───▶│   API   │───▶│ Backend │───▶│Database │
│ Input   │    │ Command │    │ Client  │    │  API    │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                    │              │              │              │
                    │              │              │              │
                    ▼              ▼              ▼              ▼
               Parse Args    HTTP Request    Process      Query Data
                    │              │              │              │
                    │              │              │              │
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│ Output  │◀───│  Format │◀───│ Process │◀───│Response │◀────────┘
│ Display │    │  Output │    │  Data   │    │  JSON   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
```

#### 2.3.2 本地模式数据流

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  User   │───▶│   CLI   │───▶│  Local  │───▶│  CSV/   │
│ Input   │    │ Command │    │ Reader  │    │  Excel  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
                    │              │              │
                    │              │              │
                    ▼              ▼              ▼
               Parse Args    Read File     Load DataFrame
                    │              │              │
                    │              │              │
┌─────────┐    ┌─────────┐    ┌─────────┐         │
│ Output  │◀───│  Format │◀───│ Process │◀────────┘
│ Display │    │  Output │    │  Data   │
└─────────┘    └─────────┘    └─────────┘
```

#### 2.3.3 AI 自然语言处理流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AI Natural Language Flow                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  User   │───▶│  Smart  │───▶│   AI    │───▶│ Command │───▶│ Execute │
│  Input  │    │ Router  │    │ Parser  │    │ Extract │    │ Command │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │              │
     │              │              │              │              │
     ▼              ▼              ▼              ▼              ▼
"查看VIP会员"   Is Valid    Azure OpenAI   Extract:      Run:
                Command?    API Call       "sh customers  customers
                   │                        list          list
                   │                        --type=member" --type=member
                   ▼
              No → AI Route
              Yes → Direct Execute
```

---

## 3. 模块设计

### 3.1 主入口模块 (main.py)

#### 3.1.1 职责

- CLI 应用初始化
- 命令组注册
- 智能路由（识别自然语言 vs 标准命令）

#### 3.1.2 智能路由逻辑

```python
def cli():
    args = sys.argv[1:]

    # 无参数 → 显示帮助
    if not args:
        app()
        return

    first_arg = args[0]

    # 有效命令 → 直接执行
    if first_arg in VALID_COMMANDS:
        app()
        return

    # 否则 → 视为自然语言，调用 AI
    query = " ".join(args)
    response = call_ai_api(query)
    # 解析并执行命令...
```

#### 3.1.3 命令注册

```python
# 命令组注册
app.add_typer(analytics.app, name="analytics")
app.add_typer(customers.app, name="customers")
app.add_typer(segments.app, name="segments")
app.add_typer(tags.app, name="tags")
app.add_typer(campaigns.app, name="campaigns")
app.add_typer(coupons.app, name="coupons")
app.add_typer(points.app, name="points")
app.add_typer(messages.app, name="messages")
app.add_typer(config_cmd.app, name="config")
app.add_typer(ai.app, name="ai")
app.add_typer(skills.app, name="skills")
```

### 3.2 配置模块 (config.py)

#### 3.2.1 配置数据模型

```python
class APIConfig(BaseModel):
    """API 连接配置"""
    url: str = "https://api.socialhub.ai"
    key: str = ""
    timeout: int = 30

class LocalConfig(BaseModel):
    """本地模式配置"""
    data_dir: str = "./data"

class AIConfig(BaseModel):
    """AI 配置"""
    provider: str = "azure"  # azure | openai
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_deployment: str = "gpt-4o"
    azure_api_version: str = "2024-08-01-preview"
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"

class Config(BaseModel):
    """主配置"""
    mode: str = "api"  # api | local
    api: APIConfig
    local: LocalConfig
    ai: AIConfig
    default_format: str = "table"
    page_size: int = 50
```

#### 3.2.2 配置文件位置

```
Windows: C:\Users\<用户名>\.socialhub\config.json
macOS:   ~/.socialhub/config.json
Linux:   ~/.socialhub/config.json
```

#### 3.2.3 配置优先级

```
环境变量 > 配置文件 > 默认值
```

### 3.3 命令模块设计

#### 3.3.1 命令模块结构

每个命令模块遵循统一的结构：

```python
"""模块说明"""

import typer
from rich.console import Console

from ..config import load_config
from ..api.client import SocialHubClient, APIError
from ..local.reader import read_data
from ..output.table import print_dataframe
from ..output.export import export_data

app = typer.Typer(help="模块帮助说明")
console = Console()

@app.command("子命令名")
def command_function(
    # 位置参数
    arg: str = typer.Argument(..., help="参数说明"),
    # 可选参数
    option: str = typer.Option("default", "--option", "-o", help="选项说明"),
) -> None:
    """命令说明"""
    config = load_config()

    if config.mode == "api":
        # API 模式处理
        with SocialHubClient() as client:
            data = client.get_data()
    else:
        # 本地模式处理
        data = read_data()

    # 输出处理
    format_output(data)
```

#### 3.3.2 Analytics 模块设计

```
analytics/
├── overview      # 数据概览
├── customers     # 客户分析
├── orders        # 订单分析
├── retention     # 留存分析
├── campaigns     # 活动分析
├── points        # 积分分析
├── coupons       # 优惠券分析
├── chart         # 图表生成
└── report        # 报告生成
```

**图表生成流程**:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Load Data     │────▶│  Process Data   │────▶│ Generate Chart  │
│   (Pandas)      │     │  (Groupby/Agg)  │     │  (Matplotlib)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │   Save Image    │
                                                │   (.png/.jpg)   │
                                                └─────────────────┘
```

**报告生成流程**:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Load Data     │────▶│ Generate Charts │────▶│  Embed Base64   │
│   (All Sources) │     │  (Matplotlib)   │     │  Images in HTML │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Render HTML    │
                                                │  Template       │
                                                └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Save & Open    │
                                                │  in Browser     │
                                                └─────────────────┘
```

### 3.4 输出模块设计

#### 3.4.1 表格输出 (table.py)

```python
def print_dataframe(df: pd.DataFrame, title: str = None) -> None:
    """使用 Rich 打印 DataFrame 为美化表格"""
    table = Table(title=title)

    # 添加列
    for col in df.columns:
        table.add_column(col)

    # 添加行
    for _, row in df.iterrows():
        table.add_row(*[str(v) for v in row.values])

    console.print(table)
```

#### 3.4.2 图表生成 (chart.py)

支持的图表类型：

| 类型 | 函数 | 用途 |
|------|------|------|
| 柱状图 | `save_bar_chart()` | 分类数据对比 |
| 饼图 | `save_pie_chart()` | 占比分布 |
| 折线图 | `save_line_chart()` | 趋势变化 |
| 漏斗图 | `save_funnel_chart()` | 转化分析 |
| 仪表板 | `generate_dashboard()` | 综合视图 |

#### 3.4.3 HTML 报告 (report.py)

```python
def generate_html_report(
    report_data: dict,
    output_path: str,
    title: str = "数据分析报告"
) -> str:
    """生成 HTML 报告

    report_data 结构:
    {
        'overview': {...},      # 概览数据
        'customer_types': {},   # 客户类型分布
        'channels': {},         # 渠道分布
        'sales_trend': {},      # 销售趋势
        'top_customers': {},    # Top 客户
        'customers': [...],     # 客户列表
        'orders': [...]         # 订单列表
    }
    """
    # 生成图表为 Base64
    charts = generate_charts_base64(report_data)

    # 渲染 HTML 模板
    html = HTML_TEMPLATE.format(
        title=title,
        generated_at=datetime.now(),
        content=render_content(report_data, charts)
    )

    # 保存文件
    Path(output_path).write_text(html, encoding='utf-8')

    return output_path
```

---

## 4. 数据模型

### 4.1 核心数据模型

#### 4.1.1 客户模型

```python
class Customer(BaseModel):
    """客户数据模型"""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_type: CustomerType  # member | registered | visitor
    created_at: datetime
    last_active_at: Optional[datetime] = None
    total_orders: int = 0
    total_spent: float = 0.0
    points_balance: int = 0
    tags: list[str] = []
    channels: list[str] = []

class CustomerType(str, Enum):
    MEMBER = "member"
    REGISTERED = "registered"
    VISITOR = "visitor"
```

#### 4.1.2 订单模型

```python
class Order(BaseModel):
    """订单数据模型"""
    order_id: str
    customer_id: str
    customer_name: Optional[str] = None
    amount: float
    channel: str
    status: OrderStatus
    order_date: datetime
    items: list[OrderItem] = []

class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
```

#### 4.1.3 分群模型

```python
class Segment(BaseModel):
    """客户分群模型"""
    id: str
    name: str
    description: Optional[str] = None
    rules: dict  # 分群规则 JSON
    status: SegmentStatus
    customer_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

class SegmentStatus(str, Enum):
    DRAFT = "draft"
    ENABLED = "enabled"
    DISABLED = "disabled"
```

#### 4.1.4 营销活动模型

```python
class Campaign(BaseModel):
    """营销活动模型"""
    id: str
    name: str
    type: CampaignType
    status: CampaignStatus
    start_date: datetime
    end_date: Optional[datetime] = None
    target_segment_id: Optional[str] = None
    target_count: int = 0
    reached_count: int = 0
    converted_count: int = 0
    budget: float = 0.0
    spent: float = 0.0

class CampaignType(str, Enum):
    SINGLE = "single"
    RECURRING = "recurring"
    TRIGGER = "trigger"

class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
```

### 4.2 技能数据模型

#### 4.2.1 技能清单模型

```python
class SkillManifest(BaseModel):
    """技能清单 (skill.yaml)"""
    name: str                           # 技能唯一标识
    display_name: str                   # 显示名称
    version: str                        # 版本号 (SemVer)
    description: str                    # 描述
    author: str                         # 作者
    license: str = "MIT"                # 许可证
    homepage: Optional[str] = None      # 主页

    category: SkillCategory             # 分类
    tags: list[str] = []                # 标签

    permissions: list[Permission] = []  # 所需权限
    dependencies: SkillDependencies     # 依赖

    commands: list[SkillCommand] = []   # 提供的命令
    hooks: list[SkillHook] = []         # 钩子

    min_cli_version: str = "0.1.0"      # 最低 CLI 版本

class SkillCategory(str, Enum):
    DATA = "data"               # 数据处理
    ANALYTICS = "analytics"     # 数据分析
    MARKETING = "marketing"     # 营销工具
    INTEGRATION = "integration" # 系统集成
    UTILITY = "utility"         # 实用工具

class Permission(str, Enum):
    READ_CUSTOMERS = "read:customers"
    WRITE_CUSTOMERS = "write:customers"
    READ_ORDERS = "read:orders"
    READ_CAMPAIGNS = "read:campaigns"
    WRITE_CAMPAIGNS = "write:campaigns"
    SEND_MESSAGES = "send:messages"
    NETWORK_ACCESS = "network:access"
    FILE_WRITE = "file:write"
```

#### 4.2.2 已安装技能模型

```python
class InstalledSkill(BaseModel):
    """已安装技能"""
    name: str
    version: str
    category: SkillCategory
    install_path: Path
    installed_at: datetime
    enabled: bool = True
    config: dict = {}
```

---

## 5. API 设计

### 5.1 API 客户端设计

```python
class SocialHubClient:
    """SocialHub API 客户端"""

    def __init__(self, base_url: str = None, api_key: str = None):
        config = load_config()
        self.base_url = base_url or config.api.url
        self.api_key = api_key or config.api.key
        self.timeout = config.api.timeout
        self._client: Optional[httpx.Client] = None

    def __enter__(self):
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        return self

    def __exit__(self, *args):
        if self._client:
            self._client.close()

    def get(self, endpoint: str, params: dict = None) -> dict:
        """GET 请求"""
        response = self._client.get(endpoint, params=params)
        return self._handle_response(response)

    def post(self, endpoint: str, data: dict = None) -> dict:
        """POST 请求"""
        response = self._client.post(endpoint, json=data)
        return self._handle_response(response)
```

### 5.2 API 端点设计

| 模块 | 端点 | 方法 | 描述 |
|------|------|------|------|
| **Analytics** | `/api/v1/analytics/overview` | GET | 数据概览 |
| | `/api/v1/analytics/customers` | GET | 客户分析 |
| | `/api/v1/analytics/orders` | GET | 订单分析 |
| | `/api/v1/analytics/retention` | GET | 留存分析 |
| **Customers** | `/api/v1/customers` | GET | 客户列表 |
| | `/api/v1/customers/{id}` | GET | 客户详情 |
| | `/api/v1/customers/search` | POST | 搜索客户 |
| | `/api/v1/customers/{id}/portrait` | GET | 客户画像 |
| **Segments** | `/api/v1/segments` | GET | 分群列表 |
| | `/api/v1/segments/{id}` | GET | 分群详情 |
| | `/api/v1/segments` | POST | 创建分群 |
| **Campaigns** | `/api/v1/campaigns` | GET | 活动列表 |
| | `/api/v1/campaigns/{id}` | GET | 活动详情 |
| | `/api/v1/campaigns/{id}/analytics` | GET | 活动分析 |
| **Skills Store** | `/api/v1/skills` | GET | 技能列表 |
| | `/api/v1/skills/{name}` | GET | 技能详情 |
| | `/api/v1/skills/{name}/download` | GET | 下载技能 |
| | `/api/v1/skills/verify` | POST | 验证签名 |

### 5.3 错误处理

```python
class APIError(Exception):
    """API 错误"""
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

# 错误码定义
ERROR_CODES = {
    400: "Bad Request - 请求参数错误",
    401: "Unauthorized - 未授权，请检查 API Key",
    403: "Forbidden - 无权限访问",
    404: "Not Found - 资源不存在",
    429: "Too Many Requests - 请求过于频繁",
    500: "Internal Server Error - 服务器内部错误",
}
```

---

## 6. AI 模块设计

### 6.1 AI 集成架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AI Module Architecture                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    User     │     │   Smart     │     │     AI      │     │   Command   │
│   Input     │────▶│   Router    │────▶│   Service   │────▶│  Executor   │
│             │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │                   │
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │   Command   │     │   Azure     │
                    │  Validator  │     │   OpenAI    │
                    │             │     │             │
                    └─────────────┘     └─────────────┘
```

### 6.2 System Prompt 设计

```python
SYSTEM_PROMPT = """你是 SocialHub.AI CLI 的智能助手，帮助用户使用命令行工具进行数据分析和营销管理。

所有命令都必须以 "sh " 前缀开头！

可用的命令包括：
1. 数据分析 (analytics)
   - sh analytics overview --period=7d|30d|365d
   - sh analytics chart bar|pie|line|dashboard --output=chart.png
   - sh analytics report --output=report.html
   ...

根据用户的自然语言请求，返回：
1. 对应的 CLI 命令（以 ```bash 代码块格式）
2. 简要说明命令的作用
3. 如果用户的请求不清楚，询问更多信息

重要：所有命令必须以 "sh " 前缀开头！

回复使用中文。
"""
```

### 6.3 AI 调用流程

```python
def call_ai_api(user_message: str, api_key: str = None) -> str:
    """调用 AI API 处理自然语言"""
    ai_config = get_ai_config()

    if ai_config["provider"] == "azure":
        # Azure OpenAI
        url = f"{ai_config['azure_endpoint']}/openai/deployments/{ai_config['azure_deployment']}/chat/completions?api-version={ai_config['azure_api_version']}"

        response = httpx.post(
            url,
            headers={"api-key": ai_config["azure_api_key"]},
            json={
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            timeout=60,
        )
    else:
        # OpenAI
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {ai_config['openai_api_key']}"},
            json={
                "model": ai_config["openai_model"],
                "messages": [...],
            },
            timeout=60,
        )

    return response.json()["choices"][0]["message"]["content"]
```

### 6.4 命令提取与执行

```python
def extract_and_execute_command(ai_response: str) -> None:
    """从 AI 响应中提取并执行命令"""
    import re
    import subprocess

    # 提取 bash 代码块中的命令
    commands = re.findall(r"```bash\n(.*?)\n```", ai_response, re.DOTALL)

    if commands:
        cmd = commands[0].strip()

        # 确认执行
        if typer.confirm(f"执行命令: {cmd}?", default=True):
            # 替换 sh 为完整 Python 路径
            if cmd.startswith("sh "):
                cmd = cmd.replace("sh ", f'"{sys.executable}" -m socialhub.cli.main ', 1)

            subprocess.run(cmd, shell=True)
```

---

## 7. Skills Store 设计

### 7.1 技能生命周期

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Skill Lifecycle                                  │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ Discover │────▶│ Download │────▶│  Verify  │────▶│ Install  │
  │          │     │          │     │          │     │          │
  └──────────┘     └──────────┘     └──────────┘     └──────────┘
       │                                                   │
       │                                                   │
       ▼                                                   ▼
  ┌──────────┐                                       ┌──────────┐
  │  Browse  │                                       │  Enable  │
  │  Store   │                                       │ /Disable │
  └──────────┘                                       └──────────┘
                                                          │
                                                          │
  ┌──────────┐     ┌──────────┐     ┌──────────┐         │
  │  Remove  │◀────│ Uninstall│◀────│  Update  │◀────────┘
  │  Files   │     │          │     │          │
  └──────────┘     └──────────┘     └──────────┘
```

### 7.2 技能安装流程

```python
class SkillManager:
    """技能管理器"""

    def install(self, name: str, version: str = None, force: bool = False) -> InstalledSkill:
        """安装技能

        流程:
        1. 从 Store 获取技能信息
        2. 下载技能包
        3. 验证签名
        4. 解压到安装目录
        5. 验证清单文件
        6. 安装 Python 依赖
        7. 注册到本地注册表
        8. 返回安装信息
        """
        # 1. 获取技能信息
        skill_info = self.store.get_skill(name)

        # 2. 检查是否已安装
        installed = self.registry.get_installed(name)
        if installed and not force:
            if installed.version == (version or skill_info.version):
                raise SkillManagerError(f"Skill {name} already installed")

        # 3. 下载技能包
        package_data = self.store.download(name, version)

        # 4. 验证签名
        download_info = self.store.get_download_info(name, version)
        if not self.security.verify_package(package_data, download_info):
            raise SecurityError("Package verification failed")

        # 5. 解压到安装目录
        install_path = self._extract_package(name, package_data)

        # 6. 验证清单
        manifest = self._load_manifest(install_path)

        # 7. 安装依赖
        self._install_dependencies(manifest.dependencies)

        # 8. 注册
        installed_skill = InstalledSkill(
            name=name,
            version=manifest.version,
            category=manifest.category,
            install_path=install_path,
            installed_at=datetime.now(),
            enabled=True,
        )
        self.registry.register(installed_skill)

        return installed_skill
```

### 7.3 安全验证

```python
class SkillSecurity:
    """技能安全验证"""

    # 官方公钥 (Ed25519)
    OFFICIAL_PUBLIC_KEY = "..."

    def verify_package(self, content: bytes, info: dict) -> bool:
        """验证技能包

        验证项:
        1. SHA-256 哈希匹配
        2. Ed25519 签名验证
        """
        # 验证哈希
        computed_hash = hashlib.sha256(content).hexdigest()
        if computed_hash != info.get("hash"):
            return False

        # 验证签名
        signature = info.get("signature")
        if signature:
            return self._verify_signature(computed_hash, signature)

        return True

    def _verify_signature(self, message: str, signature: str) -> bool:
        """Ed25519 签名验证"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(self.OFFICIAL_PUBLIC_KEY)
            )
            public_key.verify(
                bytes.fromhex(signature),
                message.encode()
            )
            return True
        except Exception:
            return False
```

### 7.4 权限控制

```python
class PermissionChecker:
    """权限检查器"""

    def check_permissions(
        self,
        skill: InstalledSkill,
        required: list[Permission],
        granted: list[Permission]
    ) -> tuple[bool, list[Permission]]:
        """检查技能权限

        Returns:
            (是否通过, 缺失的权限列表)
        """
        missing = []
        for perm in required:
            if perm not in granted:
                missing.append(perm)

        return len(missing) == 0, missing

    def request_permission(self, permission: Permission) -> bool:
        """请求用户授权"""
        console.print(f"[yellow]技能请求权限: {permission.value}[/yellow]")
        return typer.confirm("是否授权?")
```

---

## 8. 安全设计

### 8.1 安全架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Security Architecture                            │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           Security Layers                               │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │    API      │  │   Skills    │  │   Config    │  │    Data     │    │
│  │  Security   │  │  Security   │  │  Security   │  │  Security   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│        │                │                │                │             │
│        ▼                ▼                ▼                ▼             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  API Key    │  │  Signature  │  │  Encrypted  │  │  Sanitized  │    │
│  │  Auth       │  │  Verify     │  │  Storage    │  │  Input      │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 API 安全

| 安全措施 | 描述 |
|----------|------|
| HTTPS 传输 | 所有 API 通信使用 HTTPS |
| API Key 认证 | Bearer Token 认证 |
| 请求签名 | 关键操作需要请求签名 |
| 速率限制 | 防止 API 滥用 |

### 8.3 技能安全

| 安全措施 | 描述 |
|----------|------|
| 官方认证 | 仅允许安装官方 Store 的技能 |
| 签名验证 | Ed25519 数字签名验证 |
| 哈希校验 | SHA-256 完整性校验 |
| 权限控制 | 细粒度权限控制 |
| 沙箱隔离 | 技能运行在隔离环境 |

### 8.4 配置安全

```python
# 敏感配置加密存储
class SecureConfig:
    """安全配置管理"""

    def set_secret(self, key: str, value: str) -> None:
        """加密存储敏感配置"""
        # 使用 Fernet 对称加密
        encrypted = self._encrypt(value)
        self._store(key, encrypted)

    def get_secret(self, key: str) -> str:
        """解密获取敏感配置"""
        encrypted = self._load(key)
        return self._decrypt(encrypted)
```

---

## 9. 扩展性设计

### 9.1 插件架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Plugin Architecture                              │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────┐
                          │   CLI Core      │
                          │                 │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
             ┌──────┴──────┐ ┌────┴────┐ ┌───────┴──────┐
             │   Built-in  │ │  Skills │ │    Custom    │
             │   Commands  │ │  Store  │ │   Plugins    │
             └─────────────┘ └─────────┘ └──────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
             ┌──────┴──────┐ ┌───┴───┐ ┌───────┴──────┐
             │    Data     │ │ Anal- │ │   Marketing  │
             │   Export    │ │ ytics │ │    Tools     │
             └─────────────┘ └───────┘ └──────────────┘
```

### 9.2 技能扩展点

```python
class SkillExtensionPoints:
    """技能扩展点"""

    # 命令扩展
    COMMAND = "command"

    # 数据处理扩展
    DATA_PROCESSOR = "data_processor"

    # 输出格式扩展
    OUTPUT_FORMATTER = "output_formatter"

    # 钩子扩展
    PRE_COMMAND = "pre_command"
    POST_COMMAND = "post_command"
```

### 9.3 自定义输出格式

```python
# 扩展输出格式
class OutputFormatter(ABC):
    """输出格式化器基类"""

    @abstractmethod
    def format(self, data: Any) -> str:
        """格式化数据"""
        pass

    @abstractmethod
    def export(self, data: Any, path: str) -> None:
        """导出数据"""
        pass

# 注册自定义格式
FORMATTERS = {
    "table": TableFormatter,
    "json": JsonFormatter,
    "csv": CsvFormatter,
    "excel": ExcelFormatter,
    "parquet": ParquetFormatter,  # 通过技能扩展
}
```

---

## 10. 部署架构

### 10.1 本地安装

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Local Installation                               │
└─────────────────────────────────────────────────────────────────────────┘

User Machine
├── Python 3.10+
├── ~/.socialhub/
│   ├── config.json          # 配置文件
│   ├── skills/              # 已安装技能
│   │   ├── data-export-plus/
│   │   └── wechat-analytics/
│   └── cache/               # 下载缓存
├── site-packages/
│   └── socialhub/           # CLI 包
└── data/                    # 本地数据
    ├── customers.csv
    └── orders.csv
```

### 10.2 企业部署

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Enterprise Deployment                            │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────┐
                          │   Load Balancer │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
             ┌──────┴──────┐ ┌────┴────┐ ┌───────┴──────┐
             │   API       │ │   API   │ │     API      │
             │  Server 1   │ │ Server 2│ │   Server 3   │
             └─────────────┘ └─────────┘ └──────────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                          ┌────────┴────────┐
                          │    Database     │
                          │   (PostgreSQL)  │
                          └─────────────────┘

             ┌─────────────────────────────────────────────┐
             │              Client Machines                │
             │  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
             │  │  CLI 1  │  │  CLI 2  │  │  CLI 3  │     │
             │  └─────────┘  └─────────┘  └─────────┘     │
             └─────────────────────────────────────────────┘
```

### 10.3 Skills Store 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Skills Store Architecture                        │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────┐
                          │  Skills Store   │
                          │     Web UI      │
                          └────────┬────────┘
                                   │
                          ┌────────┴────────┐
                          │  Skills Store   │
                          │      API        │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
             ┌──────┴──────┐ ┌────┴────┐ ┌───────┴──────┐
             │   Skills    │ │  Skills │ │    Skills    │
             │  Metadata   │ │ Packages│ │   Signatures │
             │    (DB)     │ │ (S3/OSS)│ │    (KMS)     │
             └─────────────┘ └─────────┘ └──────────────┘
```

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| CEP | Customer Engagement Platform - 客户互动平台 |
| CLI | Command Line Interface - 命令行界面 |
| RFM | Recency, Frequency, Monetary - 客户价值模型 |
| AIPL | Awareness, Interest, Purchase, Loyalty - 营销漏斗模型 |

### B. 版本历史

| 版本 | 日期 | 描述 |
|------|------|------|
| 1.0.0 | 2024-03 | 初始版本，包含完整功能 |

### C. 参考文档

- [Typer 文档](https://typer.tiangolo.com/)
- [Rich 文档](https://rich.readthedocs.io/)
- [Azure OpenAI 文档](https://learn.microsoft.com/azure/ai-services/openai/)
- [Pydantic 文档](https://docs.pydantic.dev/)

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Stop Adding AI, We Are AI.
</p>
