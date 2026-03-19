# SocialHub.AI CLI 详细设计文档

**版本**: 1.1.0
**更新日期**: 2024-03
**作者**: SocialHub.AI 技术团队

---

## 目录

1. [系统概述](#1-系统概述)
2. [架构设计](#2-架构设计)
3. [模块设计](#3-模块设计)
4. [MCP 数据库设计](#4-mcp-数据库设计)
5. [AI 模块设计](#5-ai-模块设计)
6. [定时任务设计](#6-定时任务设计heartbeat)
7. [数据模型](#7-数据模型)
8. [Skills Store 设计](#8-skills-store-设计)
9. [安全设计](#9-安全设计)
10. [部署架构](#10-部署架构)

---

## 1. 系统概述

### 1.1 项目背景

SocialHub.AI CLI 是 SocialHub.AI 客户智能平台（CIP）的命令行工具，旨在为数据分析师和营销经理提供高效的数据查询、分析和营销管理能力。

### 1.2 设计目标

| 目标 | 描述 |
|------|------|
| **易用性** | 支持自然语言交互，降低使用门槛 |
| **实时性** | MCP 直连数据库，实时数据分析 |
| **智能化** | AI 多步骤执行、自动洞察生成 |
| **可扩展性** | 通过 Skills Store 扩展功能 |
| **自动化** | Heartbeat 定时任务调度 |
| **可视化** | 支持图表生成和 HTML 报告 |

### 1.3 技术选型

```
+-----------------+-------------------------------------------+
|     组件        |              技术选型                      |
+-----------------+-------------------------------------------+
| 开发语言        | Python 3.10+                              |
| CLI 框架        | Typer (基于 Click)                        |
| 终端美化        | Rich                                      |
| HTTP 客户端     | httpx (支持异步)                          |
| 数据处理        | Pandas                                    |
| 数据验证        | Pydantic v2                               |
| 图表生成        | Matplotlib                                |
| AI 集成         | Azure OpenAI / OpenAI                     |
| 数据库连接      | MCP (Model Context Protocol) / StarRocks  |
| 配置管理        | JSON + 环境变量                           |
+-----------------+-------------------------------------------+
```

### 1.4 系统边界

```
                    +-------------------------------------+
                    |      StarRocks Analytics DB         |
                    |  +-------------------------------+  |
                    |  |           MCP Server          |  |
                    |  +-------------------------------+  |
                    +-------------------------------------+
                                      ^
                                      | SSE (Server-Sent Events)
                                      |
+-------------------------------------+-------------------------------------+
|                                     |                                     |
|  +------------------------------------------------------------------+    |
|  |                      SocialHub.AI CLI                            |    |
|  |  +-----------+  +-----------+  +-----------+  +------------+     |    |
|  |  | Commands  |  |    MCP    |  |    AI     |  | Heartbeat  |     |    |
|  |  |  Module   |  |  Client   |  |  Module   |  | Scheduler  |     |    |
|  |  +-----------+  +-----------+  +-----------+  +------------+     |    |
|  |  +-----------+  +-----------+  +-----------+  +------------+     |    |
|  |  |  Output   |  |   Skills  |  |  Config   |  |   Local    |     |    |
|  |  |  Module   |  |   Store   |  |  Manager  |  |   Reader   |     |    |
|  |  +-----------+  +-----------+  +-----------+  +------------+     |    |
|  +------------------------------------------------------------------+    |
|                                     |                                     |
|                    SocialHub.AI CLI |                                     |
+-------------------------------------+-------------------------------------+
                                      |
                    +-----------------+-----------------+
                    |         Local Data Files          |
                    |       (CSV, Excel, JSON)          |
                    +-----------------------------------+
```

---

## 2. 架构设计

### 2.1 整体架构

```
socialhub/
├── cli/
│   ├── __init__.py              # 版本信息
│   ├── main.py                  # CLI 入口（智能路由 + 欢迎画面）
│   ├── config.py                # 配置管理
│   │
│   ├── commands/                # 命令模块
│   │   ├── __init__.py
│   │   ├── ai.py               # AI 自然语言 + 多步骤执行 + 洞察
│   │   ├── analytics.py        # 数据分析命令 (MCP 支持)
│   │   ├── heartbeat.py        # 定时任务调度 [NEW]
│   │   ├── mcp.py              # MCP 数据库命令 [NEW]
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
│   │   ├── mcp_client.py       # MCP 客户端 (SSE) [NEW]
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
├── Doc/                         # 生成的报告 [NEW]
├── Memory.md                    # 项目记忆 [NEW]
├── Heartbeat.md                 # 定时任务配置 [NEW]
├── docs/                        # 文档
└── tests/                       # 测试
```

### 2.2 分层架构

```
+-------------------------------------------------------------------------+
|                           Presentation Layer                             |
|  +-------------------------------------------------------------------+  |
|  |  CLI Commands  |  Welcome Banner  |  AI NLP  |  Output Formatters |  |
|  |  (Typer)       |  (ASCII Art)     |  (Azure) |  (Rich, Matplotlib)|  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
|                           Business Logic Layer                           |
|  +-------------------------------------------------------------------+  |
|  |  Analytics  |  Customer  |  Campaign  |  Heartbeat  |  AI Insights|  |
|  |  Service    |  Mgmt      |  Mgmt      |  Scheduler  |  Generator  |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
|                           Data Access Layer                              |
|  +-----------------------------+  +----------------------------------+  |
|  |      MCP Client             |  |      API Client / Local Reader   |  |
|  |  (SSE -> StarRocks)         |  |  (httpx -> REST / Pandas -> CSV) |  |
|  +-----------------------------+  +----------------------------------+  |
+-------------------------------------------------------------------------+
|                           Infrastructure Layer                           |
|  +-------------------------------------------------------------------+  |
|  |  Configuration  |  Retry Logic  |  Security  |  Error Handling    |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

### 2.3 数据流设计

#### 2.3.1 MCP 模式数据流

```
+---------+    +---------+    +---------+    +---------+    +-----------+
|  User   |--->|   CLI   |--->|   MCP   |--->|   MCP   |--->| StarRocks |
|  Input  |    | Command |    | Client  |    | Server  |    |    DB     |
+---------+    +---------+    +---------+    +---------+    +-----------+
                    |              |              |               |
                    v              v              v               v
               Parse Args    SSE Connect    Execute SQL     Query Data
                    |              |              |               |
                    |              |              |               |
+---------+    +---------+    +---------+    +---------+         |
| Output  |<---|  Format |<---|  Parse  |<---| SSE     |<--------+
| Display |    |  Table  |    |  TSV    |    | Response|
+---------+    +---------+    +---------+    +---------+
```

#### 2.3.2 AI 多步骤执行流程

```
+-------------------------------------------------------------------------+
|                     AI Multi-Step Execution Flow                         |
+-------------------------------------------------------------------------+

+---------+    +---------+    +---------+    +---------+    +---------+
|  User   |--->|  Smart  |--->|   AI    |--->| Extract |--->| Confirm |
|  Query  |    |  Router |    |  API    |    |  Steps  |    |  Plan   |
+---------+    +---------+    +---------+    +---------+    +---------+
                                                                 |
     +-----------------------------------------------------------+
     |
     v
+---------+    +---------+    +---------+    +---------+    +---------+
| Execute |--->| Execute |--->| Execute |--->| Collect |--->|   AI    |
| Step 1  |    | Step 2  |    | Step N  |    | Results |    | Insight |
+---------+    +---------+    +---------+    +---------+    +---------+
                                                                 |
                                                                 v
                                                          +-----------+
                                                          |  Display  |
                                                          |  Insight  |
                                                          +-----------+
```

#### 2.3.3 API 超时重试流程

```
+---------+    +---------+    +---------+
|   API   |--->| Timeout?|--->|  Yes    |---> Wait 2s ---> Retry 1
|  Call   |    |         |    |         |
+---------+    +---------+    +---------+
                    |              |
                    | No           v
                    |         +---------+
                    |         | Timeout?|---> Wait 4s ---> Retry 2
                    |         |         |
                    |         +---------+
                    |              |
                    v              v
               +---------+   +---------+
               | Success |   | Timeout?|---> Wait 6s ---> Retry 3
               |         |   |         |
               +---------+   +---------+
                                  |
                                  v
                             +---------+
                             |  Fail   |
                             | Message |
                             +---------+
```

---

## 3. 模块设计

### 3.1 主入口模块 (main.py)

#### 3.1.1 职责

- CLI 应用初始化
- 欢迎画面显示
- 命令组注册
- 智能路由（识别自然语言 vs 标准命令）
- 命令历史管理
- 多步骤计划执行

#### 3.1.2 欢迎画面

```python
def show_welcome() -> None:
    """Display welcome banner."""
    logo = """
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \\  |_ _|
 \\___ \\ / _ \\ / __| |/ _` | | |_| | | | | '_ \\  / _ \\  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \\ | |
 |____/ \\___/ \\___|_|\\__,_|_|_| |_|\\__,_|_.__//_/   \\_\\___|
    """
    # Display logo, version, quick start guide
```

#### 3.1.3 智能路由逻辑

```python
def cli():
    args = sys.argv[1:]

    # 无参数 -> 显示欢迎画面
    if not args:
        show_welcome()
        return

    first_arg = args[0]

    # 有效命令 -> 直接执行
    if first_arg in VALID_COMMANDS:
        app()
        return

    # 检查重复执行短语
    query = " ".join(args)
    if is_repeat_phrase(query):
        execute_last_command()
        return

    # 否则 -> 视为自然语言，调用 AI
    response = call_ai_api(query)

    # 检查定时任务
    if scheduled_task := extract_scheduled_task(response):
        handle_scheduled_task(scheduled_task)
        return

    # 检查多步骤计划
    if steps := extract_plan_steps(response):
        execute_plan(steps, original_query=query)
    else:
        # 单命令处理
        handle_single_command(response)
```

#### 3.1.4 命令注册

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
app.add_typer(mcp.app, name="mcp")           # [NEW]
app.add_typer(heartbeat.app, name="heartbeat") # [NEW]
```

### 3.2 命令历史模块

```python
HISTORY_FILE = Path.home() / ".socialhub" / "history.json"

REPEAT_PHRASES = {
    "再执行一次", "重新执行", "再来一次", "再试一次",
    "重复", "再跑一次", "重跑", "上一个", "!!",
    "repeat", "again", "retry", "redo"
}

def load_history() -> dict:
    """Load command history from file."""

def save_history(query: str, commands: list = None) -> None:
    """Save command to history."""
```

---

## 4. MCP 数据库设计

### 4.1 MCP 客户端架构

```
+-------------------------------------------------------------------------+
|                        MCP Client Architecture                           |
+-------------------------------------------------------------------------+

+-----------+     +-----------+     +-----------+     +-----------+
|   CLI     |---->|    MCP    |---->|    SSE    |---->| StarRocks |
|  Command  |     |   Client  |     | Connection|     |    DB     |
+-----------+     +-----------+     +-----------+     +-----------+
                       |                  |
                       v                  v
                  +-----------+     +-----------+
                  |   Query   |     |   Parse   |
                  |  Builder  |     | Response  |
                  +-----------+     +-----------+
```

### 4.2 MCP 客户端实现

```python
class MCPClient:
    """MCP (Model Context Protocol) Client using SSE."""

    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint or MCP_ENDPOINT
        self.session_id = None

    def connect(self) -> str:
        """Establish SSE connection and get session ID."""
        response = httpx.post(
            f"{self.endpoint}/sse",
            json={"jsonrpc": "2.0", "method": "initialize"},
            timeout=30
        )
        # Parse SSE response for session ID
        return self.session_id

    def query(self, sql: str, database: str = "das_demoen") -> list[dict]:
        """Execute SQL query via MCP."""
        # Build JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {"sql": sql, "database": database}
            }
        }

        # Send via SSE and parse TSV response
        response = self._send_request(request)
        return self._parse_tsv_response(response)

    def _parse_tsv_response(self, content: str) -> list[dict]:
        """Parse tab-separated values response."""
        lines = content.strip().split("\n")
        if not lines:
            return []

        headers = lines[0].split("\t")
        results = []
        for line in lines[1:]:
            values = line.split("\t")
            results.append(dict(zip(headers, values)))
        return results
```

### 4.3 MCP 命令设计

```bash
# 查看所有表
socialhub mcp tables --database=das_demoen

# 查看表结构
socialhub mcp schema <table_name> --database=das_demoen

# 交互式 SQL
socialhub mcp sql

# 执行查询
socialhub mcp query "SELECT * FROM dwd_v_order LIMIT 10"
```

### 4.4 数据库表结构

#### dwd_v_order (订单表)

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | varchar | 订单编号 |
| `order_date` | datetime | 订单日期 |
| `customer_code` | varchar | 客户编码 |
| `store_name` | varchar | 店铺名称 |
| `source_name` | varchar | 渠道名称 |
| `total_amount` | decimal | 订单金额 |
| `qty` | int | 商品数量 |

#### dim_customer_info (客户表)

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_code` | varchar | 客户编码 |
| `create_time` | datetime | 创建时间 |
| `identity_type` | int | 身份类型 |
| `customer_name` | varchar | 客户名称 (加密) |
| `source_code` | varchar | 来源编码 |
| `source_name` | varchar | 来源渠道 |
| `gender` | varchar | 性别 |
| `bitmap_id` | int | 位图ID |

---

## 5. AI 模块设计

### 5.1 AI 集成架构

```
+-------------------------------------------------------------------------+
|                          AI Module Architecture                          |
+-------------------------------------------------------------------------+

+-----------+     +-----------+     +-----------+     +-----------+
|   User    |     |   Smart   |     |    AI     |     |  Command  |
|   Input   |---->|   Router  |---->|  Service  |---->|  Executor |
|           |     |           |     |           |     |           |
+-----------+     +-----------+     +-----------+     +-----------+
                       |                 |                 |
                       v                 v                 v
                  +-----------+     +-----------+     +-----------+
                  |  Command  |     |   Azure   |     |  Insight  |
                  | Validator |     |  OpenAI   |     | Generator |
                  +-----------+     +-----------+     +-----------+
```

### 5.2 API 超时重试机制

```python
def call_ai_api(user_message: str, api_key: str = None, max_retries: int = 3) -> str:
    """Call AI API with retry mechanism."""
    last_error = None

    for attempt in range(max_retries):
        try:
            response = httpx.post(url, json=payload, timeout=60)
            return response.json()["choices"][0]["message"]["content"]

        except httpx.TimeoutException:
            last_error = "API 请求超时"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                console.print(f"[yellow]API 请求超时，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        except httpx.ConnectError:
            last_error = "网络连接失败"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]网络连接失败，{wait_time}秒后重试...[/yellow]")
                time.sleep(wait_time)
            continue

    return f"错误：{last_error}，已重试 {max_retries} 次。"
```

### 5.3 多步骤计划执行

```python
def extract_plan_steps(response: str) -> list[dict]:
    """Extract multi-step plan from AI response."""
    if "[PLAN_START]" not in response:
        return []

    steps = []
    # Pattern 1: With ```bash code blocks
    step_pattern1 = r"步骤\s*(\d+)[：:]\s*(.+?)\n```bash\n(.+?)\n```"

    # Pattern 2: Command on next line
    step_pattern2 = r"步骤\s*(\d+)[：:]\s*(.+?)\n+\s*(sh\s+[^\n]+)"

    # Extract and return steps
    return steps


def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute multi-step plan with progress display."""
    all_results = []

    for step in steps:
        console.print(f"[cyan]步骤 {step['number']}: {step['description']}[/cyan]")
        success, output = execute_command(step["command"])
        all_results.append({
            "step": step["number"],
            "description": step["description"],
            "success": success,
            "output": output
        })

    # Generate AI insights
    if all_results:
        insights = generate_insights(original_query, all_results)
        display_insights(insights)
```

### 5.4 AI 洞察生成

```python
def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on execution results."""
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    insight_prompt = f"""用户查询: {query}

以下是执行分析后得到的数据结果:
{results_text}

请基于以上数据，提供简洁的洞察分析:
1. 关键发现 (2-3点)
2. 趋势分析
3. 业务建议 (1-2条可执行建议)

直接输出洞察内容，不要输出命令。用中文回复，简洁专业。"""

    return call_ai_api(insight_prompt)
```

---

## 6. 定时任务设计（Heartbeat）

### 6.1 Heartbeat 架构

```
+-------------------------------------------------------------------------+
|                        Heartbeat Architecture                            |
+-------------------------------------------------------------------------+

+-----------+     +-----------+     +-----------+     +-----------+
| Heartbeat |---->|   Task    |---->|  Schedule |---->|  Execute  |
|    .md    |     |  Parser   |     |  Checker  |     |   Task    |
+-----------+     +-----------+     +-----------+     +-----------+
                       |                 |                 |
                       v                 v                 v
                  +-----------+     +-----------+     +-----------+
                  |   Task    |     |   Time    |     |  Update   |
                  |   List    |     |  Matcher  |     |    Log    |
                  +-----------+     +-----------+     +-----------+
```

### 6.2 任务配置格式 (Heartbeat.md)

```markdown
### 1. 每日数据概览
- **ID**: daily-overview
- **频率**: 每天 09:00
- **状态**: `pending`
- **命令**:
  ```bash
  sh analytics overview --period=today
  ```
- **说明**: 每日早间查看业务概览数据
```

### 6.3 Heartbeat 命令设计

```python
@app.command("check")
def check_tasks(
    force: bool = typer.Option(False, "--force", "-f"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
) -> None:
    """Check and execute due scheduled tasks."""

@app.command("list")
def list_tasks() -> None:
    """List all scheduled tasks."""

@app.command("run")
def run_task(task_id: str) -> None:
    """Manually run a specific task by ID."""

@app.command("setup")
def setup_scheduler() -> None:
    """Show Windows Task Scheduler setup instructions."""
```

### 6.4 任务解析与执行

```python
def parse_heartbeat_tasks() -> list[dict]:
    """Parse tasks from Heartbeat.md file."""
    content = HEARTBEAT_FILE.read_text(encoding="utf-8")

    # Extract task sections
    task_pattern = r"### \d+\. (.+?)\n- \*\*ID\*\*: (.+?)\n- \*\*频率\*\*: (.+?)\n- \*\*状态\*\*: `(.+?)`"

    # Parse command blocks
    command_pattern = r"```bash\r?\n\s*(.+?)\r?\n\s*```"

    return tasks


def should_run_task(task: dict, now: datetime) -> bool:
    """Check if task should run based on current time."""
    schedule = parse_frequency(task["frequency"])

    if schedule["type"] == "daily":
        return now.hour == schedule["hour"] and now.minute >= schedule["minute"]

    elif schedule["type"] == "weekly":
        return now.weekday() == schedule["weekday"] and now.hour == schedule["hour"]

    return False


def execute_task(task: dict) -> tuple[bool, str]:
    """Execute a task command."""
    command = task["command"]

    # Get full path to socialhub executable
    socialhub_exe = Path(sys.executable).parent / "Scripts" / "socialhub.exe"

    # Replace 'sh' with full path
    command = command.replace("sh ", f'"{socialhub_exe}" ')

    result = subprocess.run(command, shell=True, capture_output=True, timeout=300)
    return result.returncode == 0, result.stdout
```

### 6.5 Windows 任务计划集成

```powershell
# 自动设置每小时检查
$action = New-ScheduledTaskAction -Execute "socialhub.exe" -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "SocialHub Heartbeat" -Action $action -Trigger $trigger
```

---

## 7. 数据模型

### 7.1 核心数据模型

```python
class Customer(BaseModel):
    """客户数据模型"""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_type: CustomerType
    created_at: datetime
    total_orders: int = 0
    total_spent: float = 0.0

class Order(BaseModel):
    """订单数据模型"""
    order_id: str
    customer_id: str
    amount: float
    channel: str
    status: OrderStatus
    order_date: datetime

class ScheduledTask(BaseModel):
    """定时任务模型"""
    id: str
    name: str
    frequency: str
    status: TaskStatus
    command: str
    description: Optional[str] = None
    insights: bool = False
```

---

## 8. Skills Store 设计

### 8.1 技能生命周期

```
  +----------+     +----------+     +----------+     +----------+
  | Discover |---->| Download |---->|  Verify  |---->| Install  |
  +----------+     +----------+     +----------+     +----------+
       |                                                   |
       v                                                   v
  +----------+                                       +----------+
  |  Browse  |                                       |  Enable  |
  |  Store   |                                       | /Disable |
  +----------+                                       +----------+
```

### 8.2 安全验证

- SHA-256 哈希校验
- Ed25519 数字签名验证
- 权限控制

---

## 9. 安全设计

### 9.1 安全层级

| 层级 | 措施 |
|------|------|
| API 安全 | HTTPS, API Key, 超时重试 |
| 数据安全 | 敏感数据加密存储 |
| 技能安全 | 签名验证, 权限控制 |
| 编码兼容 | Windows GBK 兼容处理 |

### 9.2 Windows 编码兼容

```python
# 避免使用 Unicode 特殊字符
# 替换方案:
# ✓ -> [OK]
# ✗ -> [FAIL]
# ¥ -> CNY
# → -> ->
```

---

## 10. 部署架构

### 10.1 本地安装结构

```
User Machine
├── Python 3.10+
├── ~/.socialhub/
│   ├── config.json          # 配置文件
│   ├── history.json         # 命令历史
│   ├── skills/              # 已安装技能
│   └── cache/               # 下载缓存
├── ~/socialhub/
│   ├── Memory.md            # 项目记忆
│   ├── Heartbeat.md         # 定时任务
│   ├── User.md              # 用户画像
│   ├── QA.md                # 质量检查
│   └── Doc/                 # 生成的报告
└── site-packages/
    └── socialhub/           # CLI 包
```

---

## 附录

### A. 版本历史

| 版本 | 日期 | 描述 |
|------|------|------|
| 1.0.0 | 2024-03 | 初始版本 |
| 1.1.0 | 2024-03 | 新增 MCP 数据库、Heartbeat 调度器、AI 洞察、API 重试 |

### B. 术语表

| 术语 | 说明 |
|------|------|
| CIP | Customer Intelligence Platform - 客户智能平台 |
| MCP | Model Context Protocol - 模型上下文协议 |
| SSE | Server-Sent Events - 服务器发送事件 |
| Heartbeat | 心跳调度器 - 定时任务执行系统 |

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>
