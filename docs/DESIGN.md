# SocialHub.AI CLI Technical Design Document

**Version**: 1.1.0
**Updated**: 2024-03
**Author**: SocialHub.AI Technical Team

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Design](#2-architecture-design)
3. [Module Design](#3-module-design)
4. [MCP Database Design](#4-mcp-database-design)
5. [AI Module Design](#5-ai-module-design)
6. [Scheduled Tasks Design (Heartbeat)](#6-scheduled-tasks-design-heartbeat)
7. [Data Models](#7-data-models)
8. [Skills Store Design](#8-skills-store-design)
9. [Security Design](#9-security-design)
10. [Deployment Architecture](#10-deployment-architecture)

---

## 1. System Overview

### 1.1 Project Background

SocialHub.AI CLI is the command-line tool for the SocialHub.AI Customer Intelligence Platform (CIP), designed to provide data analysts and marketing managers with efficient data querying, analysis, and marketing management capabilities.

### 1.2 Design Goals

| Goal | Description |
|------|-------------|
| **Usability** | Natural language interaction to lower usage barriers |
| **Real-time** | MCP direct database connection for real-time analysis |
| **Intelligence** | AI multi-step execution with automatic insights |
| **Extensibility** | Feature extension via Skills Store |
| **Automation** | Heartbeat scheduled task scheduling |
| **Visualization** | Chart generation and HTML reports |

### 1.3 Technology Stack

```
+-----------------+-------------------------------------------+
|    Component    |              Technology                   |
+-----------------+-------------------------------------------+
| Language        | Python 3.10+                              |
| CLI Framework   | Typer (based on Click)                    |
| Terminal Styling| Rich                                      |
| HTTP Client     | httpx (async support)                     |
| Data Processing | Pandas                                    |
| Data Validation | Pydantic v2                               |
| Chart Generation| Matplotlib                                |
| AI Integration  | Azure OpenAI / OpenAI                     |
| Database        | MCP (Model Context Protocol) / StarRocks  |
| Configuration   | JSON + Environment Variables              |
+-----------------+-------------------------------------------+
```

### 1.4 System Boundaries

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

## 2. Architecture Design

### 2.1 Overall Architecture

```
socialhub/
├── cli/
│   ├── __init__.py              # Version info
│   ├── main.py                  # CLI entry (smart routing + welcome screen)
│   ├── config.py                # Configuration management
│   │
│   ├── commands/                # Command modules
│   │   ├── __init__.py
│   │   ├── ai.py               # AI natural language + multi-step + insights
│   │   ├── analytics.py        # Data analytics commands (MCP support)
│   │   ├── heartbeat.py        # Scheduled task scheduler [NEW]
│   │   ├── mcp.py              # MCP database commands [NEW]
│   │   ├── customers.py        # Customer management commands
│   │   ├── segments.py         # Segment management commands
│   │   ├── tags.py             # Tag management commands
│   │   ├── campaigns.py        # Marketing campaign commands
│   │   ├── coupons.py          # Coupon commands
│   │   ├── points.py           # Points commands
│   │   ├── messages.py         # Message commands
│   │   ├── skills.py           # Skills management commands
│   │   └── config_cmd.py       # Configuration commands
│   │
│   ├── api/                     # API client layer
│   │   ├── __init__.py
│   │   ├── client.py           # HTTP client
│   │   ├── mcp_client.py       # MCP client (SSE) [NEW]
│   │   └── models.py           # API data models
│   │
│   ├── local/                   # Local data processing layer
│   │   ├── __init__.py
│   │   ├── reader.py           # Data reader
│   │   └── processor.py        # Data processor
│   │
│   ├── output/                  # Output formatting layer
│   │   ├── __init__.py
│   │   ├── table.py            # Table output
│   │   ├── chart.py            # Chart generation
│   │   ├── export.py           # Data export
│   │   └── report.py           # HTML report generation
│   │
│   └── skills/                  # Skills Store module
│       ├── __init__.py
│       ├── models.py           # Skill data models
│       ├── registry.py         # Local registry
│       ├── store_client.py     # Store API client
│       ├── security.py         # Security verification
│       ├── manager.py          # Skill manager
│       └── loader.py           # Skill loader
│
├── Doc/                         # Generated reports [NEW]
├── Memory.md                    # Project memory [NEW]
├── Heartbeat.md                 # Scheduled task config [NEW]
├── docs/                        # Documentation
└── tests/                       # Tests
```

### 2.2 Layered Architecture

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

### 2.3 Data Flow Design

#### 2.3.1 MCP Mode Data Flow

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

#### 2.3.2 AI Multi-Step Execution Flow

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

#### 2.3.3 API Timeout Retry Flow

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

## 3. Module Design

### 3.1 Main Entry Module (main.py)

#### 3.1.1 Responsibilities

- CLI application initialization
- Welcome screen display
- Command group registration
- Smart routing (natural language vs standard commands)
- Command history management
- Multi-step plan execution

#### 3.1.2 Welcome Screen

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

#### 3.1.3 Smart Routing Logic

```python
def cli():
    args = sys.argv[1:]

    # No args -> show welcome screen
    if not args:
        show_welcome()
        return

    first_arg = args[0]

    # Valid command -> execute directly
    if first_arg in VALID_COMMANDS:
        app()
        return

    # Check repeat phrases
    query = " ".join(args)
    if is_repeat_phrase(query):
        execute_last_command()
        return

    # Otherwise -> treat as natural language, call AI
    response = call_ai_api(query)

    # Check for scheduled task
    if scheduled_task := extract_scheduled_task(response):
        handle_scheduled_task(scheduled_task)
        return

    # Check for multi-step plan
    if steps := extract_plan_steps(response):
        execute_plan(steps, original_query=query)
    else:
        # Single command handling
        handle_single_command(response)
```

#### 3.1.4 Command Registration

```python
# Command group registration
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

### 3.2 Command History Module

```python
HISTORY_FILE = Path.home() / ".socialhub" / "history.json"

REPEAT_PHRASES = {
    "repeat", "again", "retry", "redo", "run again",
    "execute again", "one more time", "!!"
}

def load_history() -> dict:
    """Load command history from file."""

def save_history(query: str, commands: list = None) -> None:
    """Save command to history."""
```

---

## 4. MCP Database Design

### 4.1 MCP Client Architecture

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

### 4.2 MCP Client Implementation

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

### 4.3 MCP Command Design

```bash
# List all tables
socialhub mcp tables --database=das_demoen

# View table schema
socialhub mcp schema <table_name> --database=das_demoen

# Interactive SQL
socialhub mcp sql

# Execute query
socialhub mcp query "SELECT * FROM dwd_v_order LIMIT 10"
```

### 4.4 Database Table Schema

#### dwd_v_order (Orders Table)

| Field | Type | Description |
|-------|------|-------------|
| `code` | varchar | Order ID |
| `order_date` | datetime | Order date |
| `customer_code` | varchar | Customer code |
| `store_name` | varchar | Store name |
| `source_name` | varchar | Channel name |
| `total_amount` | decimal | Order amount |
| `qty` | int | Item quantity |

#### dim_customer_info (Customer Table)

| Field | Type | Description |
|-------|------|-------------|
| `customer_code` | varchar | Customer code |
| `create_time` | datetime | Creation time |
| `identity_type` | int | Identity type |
| `customer_name` | varchar | Customer name (encrypted) |
| `source_code` | varchar | Source code |
| `source_name` | varchar | Source channel |
| `gender` | varchar | Gender |
| `bitmap_id` | int | Bitmap ID |

---

## 5. AI Module Design

### 5.1 AI Integration Architecture

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

### 5.2 API Timeout Retry Mechanism

```python
def call_ai_api(user_message: str, api_key: str = None, max_retries: int = 3) -> str:
    """Call AI API with retry mechanism."""
    last_error = None

    for attempt in range(max_retries):
        try:
            response = httpx.post(url, json=payload, timeout=60)
            return response.json()["choices"][0]["message"]["content"]

        except httpx.TimeoutException:
            last_error = "API request timeout"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                console.print(f"[yellow]API request timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        except httpx.ConnectError:
            last_error = "Network connection failed"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]Network connection failed, retrying in {wait_time}s...[/yellow]")
                time.sleep(wait_time)
            continue

    return f"Error: {last_error}, retried {max_retries} times."
```

### 5.3 Multi-Step Plan Execution

```python
def extract_plan_steps(response: str) -> list[dict]:
    """Extract multi-step plan from AI response."""
    if "[PLAN_START]" not in response:
        return []

    steps = []
    # Pattern 1: With ```bash code blocks
    step_pattern1 = r"Step\s*(\d+)[：:]\s*(.+?)\n```bash\n(.+?)\n```"

    # Pattern 2: Command on next line
    step_pattern2 = r"Step\s*(\d+)[：:]\s*(.+?)\n+\s*(sh\s+[^\n]+)"

    # Extract and return steps
    return steps


def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute multi-step plan with progress display."""
    all_results = []

    for step in steps:
        console.print(f"[cyan]Step {step['number']}: {step['description']}[/cyan]")
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

### 5.4 AI Insights Generation

```python
def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on execution results."""
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    insight_prompt = f"""User query: {query}

The following are the data results from the analysis:
{results_text}

Please provide concise insight analysis based on the above data:
1. Key findings (2-3 points)
2. Trend analysis
3. Business recommendations (1-2 actionable suggestions)

Output insights directly, no commands. Be concise and professional."""

    return call_ai_api(insight_prompt)
```

---

## 6. Scheduled Tasks Design (Heartbeat)

### 6.1 Heartbeat Architecture

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

### 6.2 Task Configuration Format (Heartbeat.md)

```markdown
### 1. Daily Data Overview
- **ID**: daily-overview
- **Frequency**: Daily 09:00
- **Status**: `pending`
- **Command**:
  ```bash
  sh analytics overview --period=today
  ```
- **Description**: Morning business overview data
```

### 6.3 Heartbeat Command Design

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

### 6.4 Task Parsing and Execution

```python
def parse_heartbeat_tasks() -> list[dict]:
    """Parse tasks from Heartbeat.md file."""
    content = HEARTBEAT_FILE.read_text(encoding="utf-8")

    # Extract task sections
    task_pattern = r"### \d+\. (.+?)\n- \*\*ID\*\*: (.+?)\n- \*\*Frequency\*\*: (.+?)\n- \*\*Status\*\*: `(.+?)`"

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

### 6.5 Windows Task Scheduler Integration

```powershell
# Auto-setup hourly check
$action = New-ScheduledTaskAction -Execute "socialhub.exe" -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "SocialHub Heartbeat" -Action $action -Trigger $trigger
```

---

## 7. Data Models

### 7.1 Core Data Models

```python
class Customer(BaseModel):
    """Customer data model"""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_type: CustomerType
    created_at: datetime
    total_orders: int = 0
    total_spent: float = 0.0

class Order(BaseModel):
    """Order data model"""
    order_id: str
    customer_id: str
    amount: float
    channel: str
    status: OrderStatus
    order_date: datetime

class ScheduledTask(BaseModel):
    """Scheduled task model"""
    id: str
    name: str
    frequency: str
    status: TaskStatus
    command: str
    description: Optional[str] = None
    insights: bool = False
```

---

## 8. Skills Store Design

### 8.1 Skill Lifecycle

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

### 8.2 Security Verification

- SHA-256 hash verification
- Ed25519 digital signature verification
- Permission control

---

## 9. Security Design

### 9.1 Security Layers

| Layer | Measures |
|-------|----------|
| API Security | HTTPS, API Key, timeout retry |
| Data Security | Encrypted sensitive data storage |
| Skill Security | Signature verification, permission control |
| Encoding Compatibility | Windows GBK compatibility handling |

### 9.2 Windows Encoding Compatibility

```python
# Avoid Unicode special characters
# Replacement scheme:
# ✓ -> [OK]
# ✗ -> [FAIL]
# ¥ -> CNY
# → -> ->
```

---

## 10. Deployment Architecture

### 10.1 Local Installation Structure

```
User Machine
├── Python 3.10+
├── ~/.socialhub/
│   ├── config.json          # Configuration file
│   ├── history.json         # Command history
│   ├── skills/              # Installed skills
│   └── cache/               # Download cache
├── ~/socialhub/
│   ├── Memory.md            # Project memory
│   ├── Heartbeat.md         # Scheduled tasks
│   ├── User.md              # User profile
│   ├── QA.md                # Quality check
│   └── Doc/                 # Generated reports
└── site-packages/
    └── socialhub/           # CLI package
```

---

## Appendix

### A. Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0.0 | 2024-03 | Initial version |
| 1.1.0 | 2024-03 | Added MCP database, Heartbeat scheduler, AI insights, API retry |

### B. Glossary

| Term | Description |
|------|-------------|
| CIP | Customer Intelligence Platform |
| MCP | Model Context Protocol |
| SSE | Server-Sent Events |
| Heartbeat | Heartbeat Scheduler - scheduled task execution system |

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform
</p>
