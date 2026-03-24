# SocialHub.AI CLI Technical Design Document

**Version**: 1.2.0
**Updated**: 2026-03
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
9. [Skills Security Subsystem](#9-skills-security-subsystem)
10. [Skills Sandbox Subsystem](#10-skills-sandbox-subsystem)
11. [Security Design](#11-security-design)
12. [Deployment Architecture](#12-deployment-architecture)

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
| **Extensibility** | Feature extension via certified Skills Store plugins |
| **Automation** | Heartbeat scheduled task scheduling with compound command support |
| **Visualization** | Chart generation and HTML reports |
| **Security** | Ed25519 signature verification, sandbox isolation, declarative permissions |

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
| Skill Signing   | Ed25519 (cryptography library)            |
| Skill Hashing   | SHA-256 (hashlib)                         |
| Skill Loading   | importlib.util.spec_from_file_location    |
| Sandbox         | Python monkey-patching (builtins/socket)  |
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
+-------------------------------------------------------------------+
|                                                                   |
|  +-------------------------------------------------------------+  |
|  |                      SocialHub.AI CLI                       |  |
|  |  +-----------+  +-----------+  +-----------+  +---------+   |  |
|  |  | Commands  |  |    MCP    |  |    AI     |  |Heartbeat|   |  |
|  |  |  Module   |  |  Client   |  |  Module   |  |Scheduler|   |  |
|  |  +-----------+  +-----------+  +-----------+  +---------+   |  |
|  |  +-----------+  +-----------+  +-----------+  +---------+   |  |
|  |  |  Output   |  |  Skills   |  |  Config   |  |  Local  |   |  |
|  |  |  Module   |  |  (w/     |  |  Manager  |  |  Reader |   |  |
|  |  |           |  |  Sandbox) |  |           |  |         |   |  |
|  |  +-----------+  +-----------+  +-----------+  +---------+   |  |
|  +-------------------------------------------------------------+  |
|                                                                   |
+-------------------------------------------------------------------+
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
│   ├── config.py                # Configuration management (Pydantic v2)
│   │
│   ├── commands/                # Command modules
│   │   ├── ai.py               # AI natural language + multi-step + insights
│   │   ├── analytics.py        # Data analytics commands (MCP support)
│   │   ├── heartbeat.py        # Scheduled task scheduler (&&-chaining)
│   │   ├── mcp.py              # MCP database commands (loads from config)
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
│   │   ├── client.py           # HTTP client (retry logic)
│   │   ├── mcp_client.py       # MCP client (SSE + threading.Event)
│   │   └── models.py           # API data models
│   │
│   ├── local/                   # Local data processing layer
│   │   ├── reader.py           # Data reader
│   │   └── processor.py        # Data processor
│   │
│   ├── output/                  # Output formatting layer
│   │   ├── table.py            # Table output
│   │   ├── chart.py            # Chart generation
│   │   ├── export.py           # Data export
│   │   └── report.py           # HTML report generation
│   │
│   └── skills/                  # Skills subsystem
│       ├── models.py           # SkillManifest, InstalledSkill (Pydantic v2)
│       ├── registry.py         # Local registry (registry.json)
│       ├── store_client.py     # Store API client + DEMO_SKILLS
│       ├── security.py         # 12-component security subsystem
│       ├── manager.py          # 10-step install pipeline
│       ├── loader.py           # importlib dynamic loading + sandbox exec
│       ├── version_manager.py  # SemVer + VersionManager + changelog
│       ├── sandbox/
│       │   ├── manager.py      # SandboxManager (coordinator)
│       │   ├── filesystem.py   # FileSystemSandbox (builtins.open)
│       │   ├── network.py      # NetworkSandbox (socket.socket)
│       │   └── execute.py      # ExecuteSandbox (subprocess.* + os.system)
│       └── store/
│           └── report-generator/
│               └── skill.yaml  # Built-in skill manifest
│
├── Doc/                         # Generated reports
├── Memory.md                    # Project memory
├── Heartbeat.md                 # Scheduled task config
├── User.md                      # User profile
├── QA.md                        # Quality check log
└── docs/                        # Documentation
    ├── DESIGN.md               # This document
    ├── README.md               # Full product documentation
    ├── skills-technical-spec.md  # Skills subsystem technical spec
    ├── skills-store-design.md  # Skills Store platform design
    ├── SKILLS-DEVELOPMENT-PLAN.md
    ├── SECURITY-GUIDE-DEVELOPERS.md
    └── SECURITY-GUIDE-USERS.md
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
|                         Skills Extension Layer                           |
|  +-----------------------------+  +----------------------------------+  |
|  |     Skills Manager          |  |     Sandbox + Security           |  |
|  |  (Install/Load/Execute)     |  |  (Ed25519/SHA-256/Permissions)   |  |
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
               MCPConfig      threading      JSON-RPC        TSV resp
               from config    .Event sync                        |
                    |              |              |               |
+---------+    +---------+    +---------+    +---------+         |
| Output  |<---|  Format |<---|  Parse  |<---| SSE     |<--------+
| Display |    |  Table  |    |  TSV    |    | Response|
+---------+    +---------+    +---------+    +---------+
```

#### 2.3.2 AI Multi-Step Execution Flow

```
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

#### 2.3.3 Skill Execution Flow

```
+---------+    +---------+    +---------+    +---------+    +---------+
|  User   |--->| Skills  |--->| Loader  |--->| Sandbox |--->|  Skill  |
|  Input  |    | Command |    | (Load)  |    | Activate|    | Execute |
+---------+    +---------+    +---------+    +---------+    +---------+
                    |              |              |               |
                    v              v              v               v
               Verify Sig    importlib     Patch open/     Call skill
               SHA-256 hash  spec_from     socket/        function
               CRL check     file_loc      subprocess     with context
                    |              |              |               |
+---------+    +---------+    +---------+    +---------+         |
| Output  |<---| Format  |<---| Return  |<---| Sandbox |<--------+
|         |    | Result  |    | Output  |    | Restore |
+---------+    +---------+    +---------+    +---------+
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

#### 3.1.2 Smart Routing Logic

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
        handle_single_command(response)
```

#### 3.1.3 Command Registration

```python
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
app.add_typer(mcp.app, name="mcp")
app.add_typer(heartbeat.app, name="heartbeat")
```

### 3.2 Configuration Module (config.py)

Pydantic v2 models for all configuration:

```python
class MCPConfig(BaseModel):
    sse_url: str
    post_url: str
    tenant_id: str

class AIConfig(BaseModel):
    provider: str = "azure"     # "azure" or "openai"
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_deployment: str = "gpt-4o"
    openai_api_key: str = ""

class AppConfig(BaseModel):
    mode: str = "mcp"           # "mcp" or "local"
    mcp: MCPConfig
    ai: AIConfig
    local: LocalConfig

def load_config() -> AppConfig:
    """Load config from ~/.socialhub/config.json with env var overrides."""
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
|  Command  |     |   Client  |     | Listener  |     |    DB     |
+-----------+     +-----------+     +-----------+     +-----------+
                       |                  |
                       v                  v
                  +-----------+     +-----------+
                  | MCPConfig |     | threading |
                  | (from     |     | .Event    |
                  | load_config)|   | sync      |
                  +-----------+     +-----------+
```

### 4.2 MCP Client Implementation

The MCP client uses `threading.Event` for reliable SSE session synchronization, avoiding CPU-spinning busy-wait loops.

```python
class MCPConfig(BaseModel):
    sse_url: str
    post_url: str
    tenant_id: str

    @validator("sse_url", "post_url")
    def _validate_config(cls, v):
        if not v:
            raise ValueError("MCP URL must be configured")
        return v

class MCPClient:
    """MCP (Model Context Protocol) Client using SSE."""

    def __init__(self, config: MCPConfig):
        self.config = config
        self._session_id: Optional[str] = None
        self._session_ready = threading.Event()  # Replaces busy-wait
        self._sse_thread: Optional[threading.Thread] = None

    def connect(self) -> None:
        """Establish SSE connection and wait for session ID."""
        self._session_ready.clear()
        self._sse_thread = threading.Thread(target=self._sse_listener, daemon=True)
        self._sse_thread.start()
        # Block until SSE session is established (up to 10s)
        self._session_ready.wait(timeout=10.0)

    def _handle_sse_event(self, event_type: str, data: str) -> None:
        """Process incoming SSE events."""
        if event_type == "session":
            self._session_id = data
            self._session_ready.set()  # Unblock connect()

    def query(self, sql: str, timeout: int = 60,
              database: Optional[str] = None) -> list[dict]:
        """Execute SQL query via MCP JSON-RPC."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {"sql": sql, "database": database}
            }
        }
        response = self._send_request(request, timeout=timeout)
        return self._parse_tsv_response(response)

    def disconnect(self) -> None:
        self._session_ready.clear()
        # ... close SSE connection
```

All MCP commands load credentials from the application config rather than hardcoded values:

```python
# In every mcp.py command:
app_config = load_config()
config = MCPConfig(
    sse_url=app_config.mcp.sse_url,
    post_url=app_config.mcp.post_url,
    tenant_id=tenant or app_config.mcp.tenant_id,
)
```

### 4.3 MCP Command Reference

```bash
socialhub mcp connect               # Test connection, list available tools
socialhub mcp tables                # List database tables
socialhub mcp schema <table>        # View table schema
socialhub mcp databases             # List available databases
socialhub mcp query "SELECT ..."    # Execute SQL query
socialhub mcp sql                   # Interactive SQL session
socialhub mcp stats                 # Database statistics
```

### 4.4 Common Database Tables

| Table | Description |
|-------|-------------|
| `dwd_v_order` | Order details |
| `dim_customer_info` | Customer info |
| `dim_member_info` | Member info |
| `dwd_v_coupon_record` | Coupon records |
| `dwd_v_points_record` | Points records |

---

## 5. AI Module Design

### 5.1 AI Integration Architecture

```
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

Auto-retries 3 times on network timeout or connection error:

```python
def call_ai_api(user_message: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            response = httpx.post(url, json=payload, timeout=60)
            return response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                time.sleep(wait_time)
    return f"Error: API unavailable after {max_retries} attempts"
```

### 5.3 Multi-Step Plan Extraction

AI response format uses `[PLAN_START]` marker with numbered steps:

```python
def extract_plan_steps(response: str) -> list[dict]:
    if "[PLAN_START]" not in response:
        return []

    # Pattern 1: Steps with ```bash code blocks
    # Pattern 2: Steps with inline sh command
    steps = []  # [{number, description, command}, ...]
    return steps
```

### 5.4 AI Insights Generation

After multi-step execution, auto-generates structured insights:

```python
def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on multi-step execution results."""
    insight_prompt = f"""User query: {query}

Data results:
{results_text}

Provide concise insight analysis:
1. Key findings (2-3 points)
2. Trend analysis
3. Business recommendations (1-2 actionable suggestions)"""

    return call_ai_api(insight_prompt)
```

### 5.5 Scheduled Task Creation from AI

When AI detects a scheduling intent, `ai.py` saves the task to `Heartbeat.md`:

```python
from .heartbeat import HEARTBEAT_FILE  # Shared constant for path consistency

def save_scheduled_task(task: dict) -> None:
    heartbeat_path = HEARTBEAT_FILE  # ~/socialhub/Heartbeat.md
    # Append task section to Heartbeat.md
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
  sh analytics orders --period=today
  ```
- **Description**: Morning business overview data
```

Multi-line code blocks are joined with ` && ` internally, then executed as sequential sub-commands.

### 6.3 Compound Command Execution

The heartbeat engine supports `&&`-chained commands (multi-line bash blocks become compound commands):

```python
HEARTBEAT_FILE = Path.home() / "socialhub" / "Heartbeat.md"

def _execute_single_sh_command(cmd: str) -> tuple[bool, str]:
    """Execute a single 'sh ...' command securely.

    SECURITY: Only allows 'sh' (SocialHub CLI) commands.
    Uses shell=False with argument list to prevent command injection.
    """
    import shlex
    cmd = cmd.strip()

    if not cmd.startswith("sh "):
        return False, "Only 'sh' commands are allowed for security reasons"

    cli_args = cmd[3:].strip()

    # Block dangerous shell characters (note: && is handled at caller level)
    dangerous_chars = [';', '||', '|', '`', '$', '>', '<', '\n', '\r']
    for char in dangerous_chars:
        if char in cli_args:
            return False, f"Invalid command: contains disallowed character '{char}'"

    args = shlex.split(cli_args)
    python_exe = sys.executable
    full_cmd = [python_exe, "-m", "socialhub.cli.main"] + args

    result = subprocess.run(
        full_cmd,
        shell=False,        # SECURITY: Never use shell=True
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="replace"
    )
    return result.returncode == 0, result.stdout + result.stderr


def execute_task(task: dict) -> tuple[bool, str]:
    """Execute a task command, supporting compound '&&'-chained commands."""
    command = task["command"].strip()

    # Split compound commands (multi-line blocks joined with ' && ')
    sub_commands = [c.strip() for c in command.split(" && ") if c.strip()]

    all_output: list[str] = []
    for sub_cmd in sub_commands:
        console.print(f"\n[cyan]Executing: {sub_cmd}[/cyan]")
        success, output = _execute_single_sh_command(sub_cmd)
        if output:
            all_output.append(output)
        if not success:
            return False, "\n".join(all_output)  # Stop on first failure

    return True, "\n".join(all_output)
```

### 6.4 Schedule Parsing

Supported frequency formats:

| Format | Example | Description |
|--------|---------|-------------|
| `Daily HH:MM` | `Daily 09:00` | Run once per day at specified time |
| `Weekly Day HH:MM` | `Weekly Mon 08:00` | Run once per week |
| `Hourly` | `Hourly` | Run at the start of each hour |

### 6.5 Windows Task Scheduler Integration

```powershell
$action = New-ScheduledTaskAction `
    -Execute "socialhub.exe" `
    -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger `
    -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask `
    -TaskName "SocialHub Heartbeat" `
    -Action $action `
    -Trigger $trigger `
    -Description "Hourly heartbeat check"
```

---

## 7. Data Models

### 7.1 Core Data Models

```python
class Customer(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_type: CustomerType
    created_at: datetime
    total_orders: int = 0
    total_spent: float = 0.0

class Order(BaseModel):
    order_id: str
    customer_id: str
    amount: float
    channel: str
    status: OrderStatus
    order_date: datetime

class ScheduledTask(BaseModel):
    id: str
    name: str
    frequency: str
    status: TaskStatus      # pending / running / done / paused / failed
    command: str
    description: Optional[str] = None
    insights: bool = False
```

---

## 8. Skills Store Design

### 8.1 Overview

The Skills Store provides officially certified skill plugins to extend CLI functionality. All skills undergo mandatory security certification before publication.

### 8.2 Skill Lifecycle

```
  +----------+     +----------+     +----------+     +----------+
  | Discover |---->| Download |---->|  Verify  |---->| Install  |
  +----------+     +----------+     +----------+     +----------+
       |               |                |                  |
       v               v                v                  v
  +----------+    SHA-256 hash    Ed25519 sig         importlib
  |  Browse  |    check           verify              dynamic load
  |  Store   |    CRL check       permission          + sandbox
  +----------+                    consent             activation
```

### 8.3 Skill Manifest (skill.yaml)

```yaml
name: "report-generator"
version: "1.0.0"
display_name: "Business Report Generator"
description: "Generate comprehensive business analysis reports"
author: "SocialHub Official"
license: "MIT"

category: "analytics"
tags: [report, analytics, business]

compatibility:
  cli_version: ">=0.1.0"
  python_version: ">=3.10"

dependencies:
  python: []
  skills: []

permissions:
  - file:write      # Write report files
  - network:none    # No network access
  - data:read       # Read customer data

entrypoint: "main.py"
commands:
  - name: "generate-report"
    description: "Generate business analysis report"
    function: "generate_report"

certification:
  certified_at: "2024-03-15T10:00:00Z"
  certified_by: "SocialHub.AI"
  signature: "<base64_ed25519_signature>"
  certificate_id: "CERT-2024-00001"
```

### 8.4 10-Step Install Pipeline (SkillManager)

```
Step 1: Fetch skill metadata from store
Step 2: Check if already installed (version comparison)
Step 3: Download skill package (.zip)
Step 4: Verify SHA-256 file hash
Step 5: Verify Ed25519 digital signature
Step 6: Check CRL (Certificate Revocation List)
Step 7: Present permissions to user, obtain consent
Step 8: Extract package to ~/.socialhub/skills/installed/
Step 9: Install Python dependencies (pip)
Step 10: Register in local registry (registry.json)
```

### 8.5 Skill Data Models (Pydantic v2)

```python
class SkillCategory(str, Enum):
    DATA = "data"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    INTEGRATION = "integration"
    UTILITY = "utility"

class SkillPermission(str, Enum):
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK_LOCAL = "network:local"
    NETWORK_INTERNET = "network:internet"
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    EXECUTE = "execute"

class SkillManifest(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: SkillCategory
    permissions: list[SkillPermission]
    entrypoint: str
    commands: list[SkillCommand]
    certification: Optional[SkillCertification] = None

class InstalledSkill(BaseModel):
    manifest: SkillManifest
    install_path: str
    installed_at: str
    status: SkillStatus        # active / disabled / error
    granted_permissions: list[SkillPermission]
```

---

## 9. Skills Security Subsystem

The security subsystem (`security.py`) contains 12 components handling the full security lifecycle of skills.

### 9.1 Component Overview

| Component | Responsibility |
|-----------|---------------|
| `KeyManager` | Load/cache Ed25519 public key from embedded PEM |
| `HashVerifier` | SHA-256 file integrity verification |
| `SignatureVerifier` | Ed25519 signature verification against manifest payload |
| `RevocationListManager` | Fetch/cache CRL from store; check revoked certificates |
| `PermissionChecker` | Validate permission strings against SkillPermission enum |
| `PermissionStore` | Persist granted permissions to `~/.socialhub/skill_permissions.json` |
| `PermissionPrompter` | Interactive Rich console prompts for user consent |
| `PermissionContext` | Context manager; grants/revokes active permissions per execution |
| `SecurityAuditLogger` | Append-only JSON audit log at `~/.socialhub/security_audit.log` |
| `SecurityEventReporter` | Rich console display of security events |
| `SkillHealthChecker` | Verify installed skill file integrity on demand |
| (module-level) | `verify_skill_installation()` — orchestrates full verification chain |

### 9.2 Verification Chain

```
verify_skill_installation(skill)
    |
    +-- HashVerifier.verify_file(skill_path, expected_hash)
    |       SHA-256(file bytes) == manifest.certification.hash
    |
    +-- SignatureVerifier.verify(manifest_payload, signature)
    |       Ed25519_verify(public_key, payload, sig)
    |
    +-- RevocationListManager.is_revoked(certificate_id)
            Fetch CRL from store API (cached 1h)
            certificate_id in revoked_list?
```

### 9.3 Permission Flow

```
Install time:
  PermissionChecker.validate(permissions)  # Enum validation
  PermissionPrompter.prompt_user(permissions)  # Interactive consent
  PermissionStore.save(skill_name, granted)  # Persist to JSON

Execution time:
  with PermissionContext(skill_name, required_permissions):
      # Granted permissions active
      skill_function()
  # Permissions revoked after context exit
```

### 9.4 Audit Log Format

```json
{
  "timestamp": "2026-03-21T10:30:00",
  "event_type": "skill_installed",
  "skill_name": "report-generator",
  "details": {
    "version": "1.0.0",
    "permissions_granted": ["file:write", "data:read"]
  }
}
```

---

## 10. Skills Sandbox Subsystem

The sandbox subsystem (`sandbox/`) provides runtime isolation for skill execution using Python monkey-patching. No OS-level containers are required.

### 10.1 SandboxManager

Coordinates the three sandbox components:

```python
class SandboxManager:
    def __init__(self, skill_name: str, permissions: list[SkillPermission]):
        self.fs_sandbox = FileSystemSandbox(skill_name, permissions)
        self.net_sandbox = NetworkSandbox(skill_name, permissions)
        self.exec_sandbox = ExecuteSandbox(skill_name, permissions)

    def __enter__(self):
        self.fs_sandbox.activate()
        self.net_sandbox.activate()
        self.exec_sandbox.activate()
        return self

    def __exit__(self, *args):
        self.exec_sandbox.deactivate()
        self.net_sandbox.deactivate()
        self.fs_sandbox.deactivate()
```

### 10.2 FileSystemSandbox

Intercepts `builtins.open` to enforce path restrictions:

```python
class FileSystemSandbox:
    def activate(self):
        self._original_open = builtins.open

        def restricted_open(file, mode='r', *args, **kwargs):
            if self._is_write_mode(mode):
                if not self._has_permission(SkillPermission.FILE_WRITE):
                    raise PermissionError("Skill lacks file:write permission")
                if not self._is_allowed_path(file):
                    raise PermissionError(f"Write outside allowed paths: {file}")
            return self._original_open(file, mode, *args, **kwargs)

        builtins.open = restricted_open

    def deactivate(self):
        builtins.open = self._original_open
```

Allowed write paths: `Doc/`, `~/socialhub/`, `~/.socialhub/skills/`

### 10.3 NetworkSandbox

Intercepts `socket.socket.__init__` to enforce network restrictions:

```python
class NetworkSandbox:
    def activate(self):
        self._original_socket = socket.socket

        class RestrictedSocket(socket.socket):
            def __init__(inner_self, *args, **kwargs):
                if not outer_self._has_permission(SkillPermission.NETWORK_INTERNET):
                    if not outer_self._has_permission(SkillPermission.NETWORK_LOCAL):
                        raise PermissionError("Skill has no network access permission")
                super().__init__(*args, **kwargs)

        socket.socket = RestrictedSocket
```

### 10.4 ExecuteSandbox

Intercepts `subprocess.run`, `subprocess.Popen`, `subprocess.call`, and `os.system`:

```python
class ExecuteSandbox:
    def activate(self):
        if not self._has_permission(SkillPermission.EXECUTE):
            # Replace all subprocess entry points with blocked versions
            subprocess.run = self._blocked_execute
            subprocess.Popen = self._blocked_popen
            subprocess.call = self._blocked_execute
            os.system = self._blocked_system

    def _blocked_execute(self, *args, **kwargs):
        raise PermissionError("Skill lacks 'execute' permission")
```

### 10.5 Skill Execution with Sandbox

```python
# In SkillLoader.run_skill_command():
def run_skill_command(skill: InstalledSkill, command_name: str, args: dict):
    granted = PermissionStore.load(skill.manifest.name)

    with SandboxManager(skill.manifest.name, granted) as sandbox:
        with PermissionContext(skill.manifest.name, granted):
            module = importlib.util.spec_from_file_location(
                skill.manifest.name,
                skill.install_path / skill.manifest.entrypoint
            )
            spec.loader.exec_module(module)
            func = getattr(module, command.function)
            return func(**args)
```

---

## 11. Security Design

### 11.1 Security Layers

| Layer | Measures |
|-------|----------|
| API Security | HTTPS, API Key authentication, timeout retry |
| Data Security | Encrypted sensitive data storage |
| Skill Integrity | SHA-256 hash verification + Ed25519 signature |
| Skill Trust | CRL revocation check against store server |
| Skill Runtime | Sandbox (filesystem/network/execute) isolation |
| Skill Permissions | Declarative manifest + interactive user consent + persistent store |
| Command Injection | `shell=False` + `shlex.split()` in heartbeat execution |
| Audit | Append-only JSON audit log for all security events |

### 11.2 Heartbeat Command Injection Prevention

The heartbeat scheduler uses `shell=False` with argument list construction, preventing shell injection even for user-defined task commands:

```python
# SAFE: shell=False with explicit argument list
full_cmd = [python_exe, "-m", "socialhub.cli.main"] + shlex.split(cli_args)
subprocess.run(full_cmd, shell=False, ...)

# BLOCKED: dangerous characters rejected before reaching subprocess
dangerous_chars = [';', '||', '|', '`', '$', '>', '<', '\n', '\r']
```

### 11.3 Windows Encoding Compatibility

```python
# Avoid Unicode special characters in CLI output
# Replacement scheme:
# ✓ -> [OK]
# ✗ -> [FAIL]
# ¥ -> CNY
# → -> ->
```

---

## 12. Deployment Architecture

### 12.1 Local Installation Structure

```
User Machine
├── Python 3.10+
├── ~/.socialhub/
│   ├── config.json              # Configuration file
│   ├── history.json             # Command history
│   ├── skill_permissions.json   # Granted skill permissions
│   ├── security_audit.log       # Security audit log (JSON lines)
│   └── skills/
│       ├── registry.json        # Installed skills registry
│       ├── cache/               # Download cache
│       └── installed/           # Installed skill packages
│           └── report-generator/
│               ├── skill.yaml
│               └── main.py
├── ~/socialhub/
│   ├── Memory.md                # Project memory
│   ├── Heartbeat.md             # Scheduled tasks
│   ├── User.md                  # User profile
│   ├── QA.md                    # Quality check log
│   └── Doc/                     # Generated reports and charts
└── site-packages/
    └── socialhub/               # CLI package
```

---

## Appendix

### A. Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0.0 | 2024-03 | Initial version |
| 1.1.0 | 2024-03 | Added MCP database, Heartbeat scheduler, AI insights, API retry |
| 1.2.0 | 2026-03 | Fixed MCPClient threading.Event sync; fixed Heartbeat &&-chaining; fixed MCP config loading; fixed analytics NameError; added sandbox subsystem docs; expanded Skills security docs |

### B. Related Documentation

| Document | Location | Description |
|----------|----------|-------------|
| Product Docs | `docs/README.md` | Full command reference and usage guide |
| Skills Technical Spec | `docs/skills-technical-spec.md` | Complete skills subsystem technical spec |
| Skills Store Design | `docs/skills-store-design.md` | Store platform design (backend) |
| Security Guide (Dev) | `docs/SECURITY-GUIDE-DEVELOPERS.md` | Security guide for skill developers |
| Security Guide (User) | `docs/SECURITY-GUIDE-USERS.md` | Security guide for end users |

### C. Glossary

| Term | Description |
|------|-------------|
| CIP | Customer Intelligence Platform |
| MCP | Model Context Protocol |
| SSE | Server-Sent Events |
| Heartbeat | Scheduled task execution system |
| CRL | Certificate Revocation List |
| Sandbox | Python monkey-patch based skill runtime isolation |
| Ed25519 | Elliptic-curve digital signature algorithm used for skill signing |

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform
</p>
