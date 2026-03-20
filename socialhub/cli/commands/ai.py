"""AI-powered natural language command interface."""

import json
import os
import re
import subprocess
import sys
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import load_config

app = typer.Typer(help="AI assistant for natural language queries")
console = Console()


def get_ai_config() -> dict:
    """Get AI configuration from config file or environment."""
    config = load_config()
    ai_config = config.ai

    return {
        "provider": os.getenv("AI_PROVIDER", ai_config.provider),
        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ai_config.azure_endpoint),
        "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ai_config.azure_api_key),
        "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", ai_config.azure_deployment),
        "azure_api_version": os.getenv("AZURE_OPENAI_API_VERSION", ai_config.azure_api_version),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ai_config.openai_api_key),
        "openai_model": os.getenv("OPENAI_MODEL", ai_config.openai_model),
    }

SYSTEM_PROMPT = """You are the intelligent assistant for SocialHub.AI CLI, helping users with data analysis and marketing management via command line.

All commands must start with "sh " prefix!

Available commands include:
1. Data Analytics (analytics)
   - sh analytics overview --period=7d|30d|365d  # Overview analysis
   - sh analytics customers --period=30d  # Customer analysis
   - sh analytics retention --days=7,14,30  # Retention analysis
   - sh analytics orders --period=30d --by=channel|province  # Order analysis
   - sh analytics chart bar --data=customers --group=customer_type --output=chart.png  # Bar chart
   - sh analytics chart pie --data=customers --group=customer_type --output=pie.png  # Pie chart
   - sh analytics chart dashboard --output=dashboard.png  # Analytics dashboard
   - sh analytics chart funnel --output=funnel.png  # Funnel chart
   - sh analytics report --output=report.html  # HTML analytics report (printable to PDF)
   - sh analytics report --title="Monthly Report" --output=monthly.html  # Custom title report

2. Customer Management (customers)
   - sh customers list --type=member|registered|visitor  # Customer list
   - sh customers search --phone=xxx --email=xxx  # Search customers
   - sh customers get <customer_id>  # Customer details
   - sh customers export --output=file.csv  # Export customers

3. Segment Management (segments)
   - sh segments list  # Segment list
   - sh segments create --name="Name" --rules='{"key":"value"}'  # Create segment
   - sh segments export <segment_id> --output=file.csv  # Export segment

4. Tag Management (tags)
   - sh tags list --type=rfm|aipl|static  # Tag list
   - sh tags create --name="TagName" --type=static --values="val1,val2"  # Create tag

5. Marketing Campaigns (campaigns)
   - sh campaigns list --status=draft|running|finished  # Campaign list
   - sh campaigns analysis <campaign_id> --funnel  # Campaign analysis
   - sh campaigns calendar --month=2024-03  # Marketing calendar

6. Coupons (coupons)
   - sh coupons rules list  # Coupon rules
   - sh coupons list --status=unused|used|expired  # Coupon list
   - sh coupons analysis <rule_id>  # Coupon analysis

7. Points (points)
   - sh points rules list  # Points rules
   - sh points balance <member_id>  # Points balance
   - sh points history <member_id>  # Points history

8. Messages (messages)
   - sh messages templates list --channel=sms|email|wechat  # Message templates
   - sh messages records --status=success|failed  # Send records
   - sh messages stats --period=7d  # Message statistics

## Response Format Rules

When user requests require multiple steps, use the following format:

```
[PLAN_START]
Step 1: <step description>
```bash
<command>
```

Step 2: <step description>
```bash
<command>
```

...more steps...
[PLAN_END]

<insights or analysis recommendations>
```

When user request only needs a single command, output directly:
```bash
<command>
```
with a brief explanation.

## Scheduled Tasks

When user requests scheduling a task, use [SCHEDULE_TASK] marker:

```
[SCHEDULE_TASK]
- ID: <unique task identifier>
- Name: <task name>
- Frequency: <Daily/Weekly/Hourly HH:MM>
- Command: <sh command to execute>
- Description: <task description>
- Insights: <whether to generate AI insights true/false>
[/SCHEDULE_TASK]
```

Example: User says "generate channel analysis report daily at 8pm"
```
[SCHEDULE_TASK]
- ID: daily-channel-report
- Name: Daily Channel Analysis Report
- Frequency: Daily 20:00
- Command: sh analytics orders --by=channel && sh analytics report --title="Channel Analysis Report" --output=channel_report.html
- Description: Auto-generate channel analysis report daily at 8pm
- Insights: true
[/SCHEDULE_TASK]
Task has been added to the schedule and will run daily at 20:00 with AI insights.
```

Important rules:
1. All commands must start with "sh " prefix!
2. Multi-step analysis must be wrapped with [PLAN_START] and [PLAN_END] markers
3. Each step must have a clear description and corresponding command
4. Scheduled tasks must use [SCHEDULE_TASK] marker
5. Reply in English
"""


def call_ai_api(user_message: str, api_key: Optional[str] = None, max_retries: int = 3, show_thinking: bool = True) -> str:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI).

    Args:
        user_message: The user's message to send to the AI
        api_key: Optional API key override
        max_retries: Maximum number of retry attempts for timeout errors (default: 3)
        show_thinking: Whether to show "Thinking..." with elapsed time (default: True)
    """
    import time
    import threading
    from rich.console import Console
    from rich.live import Live
    from rich.text import Text
    console = Console()

    ai_config = get_ai_config()
    provider = ai_config["provider"]

    last_error = None

    def make_api_request(provider: str, ai_config: dict, api_key: Optional[str], result_holder: dict):
        """Make the actual API request in a separate thread."""
        try:
            if provider == "azure":
                key = api_key or ai_config["azure_api_key"]
                if not key:
                    result_holder["error"] = "Error: Azure OpenAI API Key not configured. Run 'sh config set ai.azure_api_key YOUR_KEY' or set AZURE_OPENAI_API_KEY environment variable."
                    return

                endpoint = ai_config["azure_endpoint"]
                deployment = ai_config["azure_deployment"]
                api_version = ai_config["azure_api_version"]
                url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

                response = httpx.post(
                    url,
                    headers={
                        "api-key": key,
                        "Content-Type": "application/json",
                    },
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
                key = api_key or ai_config["openai_api_key"]
                if not key:
                    result_holder["error"] = "Error: OpenAI API Key not configured. Run 'sh config set ai.openai_api_key YOUR_KEY' or set OPENAI_API_KEY environment variable."
                    return

                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": ai_config["openai_model"],
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                    timeout=60,
                )

            result_holder["response"] = response
        except httpx.TimeoutException:
            result_holder["timeout"] = True
        except httpx.ConnectError:
            result_holder["connect_error"] = True
        except Exception as e:
            result_holder["error"] = f"Error: {str(e)}"

    for attempt in range(max_retries):
        result_holder = {}
        start_time = time.time()

        # Start API request in background thread
        api_thread = threading.Thread(
            target=make_api_request,
            args=(provider, ai_config, api_key, result_holder)
        )
        api_thread.start()

        # Show thinking animation with elapsed time
        if show_thinking:
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner_idx = 0

            with Live(console=console, refresh_per_second=10, transient=True) as live:
                while api_thread.is_alive():
                    elapsed = time.time() - start_time
                    spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                    text = Text()
                    text.append(f" {spinner} ", style="cyan")
                    text.append("Thinking", style="cyan bold")
                    text.append(f" ({elapsed:.1f}s)", style="dim")
                    live.update(text)
                    spinner_idx += 1
                    time.sleep(0.1)
        else:
            api_thread.join()

        api_thread.join()
        elapsed_time = time.time() - start_time

        # Check results
        if "error" in result_holder:
            return result_holder["error"]

        if "timeout" in result_holder:
            last_error = "API request timeout"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]API request timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        if "connect_error" in result_holder:
            last_error = "Network connection failed"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]Network connection failed, retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        if "response" in result_holder:
            response = result_holder["response"]
            if response.status_code != 200:
                return f"API Error: {response.status_code} - {response.text}"

            result = response.json()
            console.print(f"[dim]Completed in {elapsed_time:.1f}s[/dim]")
            return result["choices"][0]["message"]["content"]

    return f"Error: {last_error}, retried {max_retries} times."


def extract_scheduled_task(response: str) -> dict:
    """Extract scheduled task from response."""
    if "[SCHEDULE_TASK]" not in response or "[/SCHEDULE_TASK]" not in response:
        return {}

    match = re.search(r"\[SCHEDULE_TASK\](.*?)\[/SCHEDULE_TASK\]", response, re.DOTALL)
    if not match:
        return {}

    task_text = match.group(1)
    task = {}

    # Parse task fields
    patterns = {
        "id": r"-\s*ID:\s*(.+)",
        "name": r"-\s*Name:\s*(.+)",
        "frequency": r"-\s*Frequency:\s*(.+)",
        "command": r"-\s*Command:\s*(.+)",
        "description": r"-\s*Description:\s*(.+)",
        "insights": r"-\s*Insights:\s*(.+)",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, task_text)
        if m:
            task[key] = m.group(1).strip()

    return task


def save_scheduled_task(task: dict) -> bool:
    """Save scheduled task to Heartbeat.md."""
    from pathlib import Path
    from datetime import datetime

    heartbeat_path = Path(__file__).parent.parent.parent.parent / "Heartbeat.md"

    if not heartbeat_path.exists():
        return False

    try:
        content = heartbeat_path.read_text(encoding="utf-8")

        # Find the position to insert (before "## Execution Log")
        insert_marker = "## Execution Log"
        if insert_marker not in content:
            insert_marker = "## Add New Task Template"

        # Create task entry
        task_entry = f"""
### {len(re.findall(r'### \d+\.', content)) + 1}. {task.get('name', 'New Task')}
- **ID**: {task.get('id', 'task-' + datetime.now().strftime('%Y%m%d%H%M%S'))}
- **Frequency**: {task.get('frequency', 'Daily 00:00')}
- **Status**: `pending`
- **Command**:
  ```bash
  {task.get('command', 'sh analytics overview')}
  ```
- **Description**: {task.get('description', '')}
- **AI Insights**: {task.get('insights', 'false')}

---

"""

        # Insert before marker
        if insert_marker in content:
            content = content.replace(insert_marker, task_entry + insert_marker)
        else:
            content += task_entry

        heartbeat_path.write_text(content, encoding="utf-8")
        return True

    except Exception as e:
        console.print(f"[red]Failed to save scheduled task: {e}[/red]")
        return False


def extract_plan_steps(response: str) -> list[dict]:
    """Extract steps from a multi-step plan response."""
    steps = []

    # Check if response contains a plan
    if "[PLAN_START]" not in response or "[PLAN_END]" not in response:
        return steps

    # Extract plan section
    plan_match = re.search(r"\[PLAN_START\](.*?)\[PLAN_END\]", response, re.DOTALL)
    if not plan_match:
        return steps

    plan_text = plan_match.group(1)

    # Try multiple patterns to match steps
    # Pattern 1: With ```bash code blocks
    step_pattern1 = r"Step\s*(\d+)[：:]\s*(.+?)\n```bash\n(.+?)\n```"
    matches = re.findall(step_pattern1, plan_text, re.DOTALL)

    if not matches:
        # Pattern 2: Command on next line after description (no code block)
        step_pattern2 = r"Step\s*(\d+)[：:]\s*(.+?)\n+\s*(sh\s+[^\n]+)"
        matches = re.findall(step_pattern2, plan_text, re.DOTALL)

    if not matches:
        # Pattern 3: Command in code block without bash marker
        step_pattern3 = r"Step\s*(\d+)[：:]\s*(.+?)\n```\n(.+?)\n```"
        matches = re.findall(step_pattern3, plan_text, re.DOTALL)

    for match in matches:
        step_num, description, command = match
        # Clean up the command
        cmd = command.strip()
        # Remove any leading/trailing backticks
        cmd = cmd.strip('`').strip()
        steps.append({
            "number": int(step_num),
            "description": description.strip(),
            "command": cmd,
        })

    return steps


def execute_command(cmd: str) -> tuple[bool, str]:
    """Execute a CLI command and return success status and output."""
    python_exe = sys.executable

    # Replace 'sh ' with full python path
    if cmd.startswith("sh "):
        full_cmd = cmd.replace("sh ", f'"{python_exe}" -m socialhub.cli.main ', 1)
    else:
        full_cmd = cmd

    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout if result.stdout else result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command execution timeout"
    except Exception as e:
        return False, f"Execution error: {str(e)}"


def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on query results."""
    # Build context from results
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    if not results_text:
        return ""

    insight_prompt = f"""User query: {query}

The following are the data results from the analysis:
{results_text}

Please provide concise insight analysis based on the above data:
1. Key findings (2-3 points)
2. Trend analysis
3. Business recommendations (1-2 actionable suggestions)

Output insights directly, no commands. Be concise and professional."""

    return call_ai_api(insight_prompt, show_thinking=False)


def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute a multi-step plan with progress display."""
    console.print(f"\n[bold cyan]Executing {len(steps)} steps...[/bold cyan]\n")

    # Collect results for insights
    all_results = []

    for step in steps:
        step_num = step["number"]
        description = step["description"]
        command = step["command"]

        # Display step header
        console.print(f"[bold yellow]Step {step_num}:[/bold yellow] {description}")
        console.print(f"[dim]Command: {command}[/dim]\n")

        # Execute command
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description=f"Executing...", total=None)
            success, output = execute_command(command)

        # Collect result
        all_results.append({
            "step": step_num,
            "description": description,
            "success": success,
            "output": output,
        })

        # Display result
        if success:
            console.print(f"[green][OK][/green] Step {step_num} completed\n")
            if output:
                console.print(output)
        else:
            console.print(f"[red][FAIL][/red] Step {step_num} failed\n")
            if output:
                console.print(f"[red]{output}[/red]")

            # Ask whether to continue
            if step_num < len(steps):
                if not typer.confirm("Continue with remaining steps?", default=False):
                    console.print("[yellow]Execution cancelled[/yellow]")
                    return

        console.print()  # Add spacing between steps

    console.print("[bold green]All steps completed![/bold green]\n")

    # Generate insights if we have results and original query
    if original_query and any(r["success"] for r in all_results):
        console.print("[bold cyan]Generating insights...[/bold cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description="AI analyzing...", total=None)
            insights = generate_insights(original_query, all_results)

        if insights and "Error" not in insights:
            console.print(Panel(
                Markdown(insights),
                title="[bold magenta]AI Insights[/bold magenta]",
                border_style="magenta",
            ))


@app.command("chat")
def ai_chat(
    query: str = typer.Argument(..., help="Natural language query"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="OpenAI API Key"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Auto-execute generated commands"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Auto-execute multi-step plan (with confirmation)"),
) -> None:
    """
    Interact with CLI using natural language.

    Examples:
        ai chat "analyze customer retention for last 30 days"
        ai chat "show all VIP members"
        ai chat "export high-value customers to Excel"
        ai chat "show order distribution and trends" --auto
    """
    console.print(f"\n[dim]Analyzing: {query}[/dim]\n")

    response = call_ai_api(query, api_key)

    # Check for multi-step plan
    steps = extract_plan_steps(response)

    if steps:
        # Display plan without the markers
        display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        console.print(Panel(Markdown(display_response), title="AI Assistant - Analysis Plan", border_style="cyan"))

        # Ask for confirmation to execute plan
        if auto or execute:
            console.print(f"\n[bold]Detected {len(steps)} execution steps:[/bold]")
            for step in steps:
                console.print(f"  {step['number']}. {step['description']}")

            console.print()
            if typer.confirm("Execute this plan?", default=True):
                execute_plan(steps, original_query=query)
            else:
                console.print("[yellow]Plan not executed. You can run the commands manually.[/yellow]")
    else:
        # Display response as markdown
        console.print(Panel(Markdown(response), title="AI Assistant", border_style="cyan"))

        # Extract and optionally execute single command
        if (execute or auto) and "```bash" in response:
            commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
            if commands:
                cmd = commands[0].strip()
                if typer.confirm(f"\nExecute command: {cmd}?"):
                    console.print(f"\n[dim]Executing: {cmd}[/dim]\n")
                    success, output = execute_command(cmd)
                    if output:
                        console.print(output)


@app.command("help")
def ai_help(
    topic: str = typer.Argument("general", help="Help topic"),
) -> None:
    """Get help for specific features."""
    help_topics = {
        "general": """
## SocialHub.AI CLI User Guide

### Quick Start
```bash
# View all commands
python -m socialhub.cli.main --help

# Data analytics
python -m socialhub.cli.main analytics overview

# Customer management
python -m socialhub.cli.main customers list
```

### AI Assistant
Interact with CLI using natural language:
```bash
python -m socialhub.cli.main ai chat "your question"
```
        """,
        "analytics": """
## Data Analytics Commands

### Overview Analysis
```bash
python -m socialhub.cli.main analytics overview --period=7d
python -m socialhub.cli.main analytics overview --from=2024-01-01 --to=2024-03-01
```

### Customer Analysis
```bash
python -m socialhub.cli.main analytics customers --period=30d
python -m socialhub.cli.main analytics retention --days=7,14,30
```

### Order Analysis
```bash
python -m socialhub.cli.main analytics orders --period=30d
python -m socialhub.cli.main analytics orders --by=channel
```
        """,
        "customers": """
## Customer Management Commands

### Query Customers
```bash
python -m socialhub.cli.main customers list --type=member
python -m socialhub.cli.main customers search --phone=138
python -m socialhub.cli.main customers get C001
```

### Export Customers
```bash
python -m socialhub.cli.main customers export --output=customers.csv
python -m socialhub.cli.main customers export --type=member --output=members.xlsx
```
        """,
    }

    content = help_topics.get(topic, help_topics["general"])
    console.print(Markdown(content))


# Shortcuts for common queries
@app.command("analyze")
def analyze_shortcut(
    target: str = typer.Argument("overview", help="Analysis target: overview/customers/orders/retention"),
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
) -> None:
    """Quick analysis command shortcut."""
    from . import analytics

    target_map = {
        "overview": lambda: analytics.analytics_overview(period=period, format="table", from_date=None, to_date=None, customer_type="all", output=None),
        "customers": lambda: analytics.analytics_customers(period=period, channel="all", format="table", output=None),
        "orders": lambda: analytics.analytics_orders(period=period, metric="sales", repurchase_rate=False, by=None, format="table", output=None),
        "retention": lambda: analytics.analytics_retention(days="7,14,30", format="table", output=None),
    }

    if target in target_map:
        target_map[target]()
    else:
        console.print(f"[yellow]Unknown analysis target: {target}[/yellow]")
        console.print("Options: overview, customers, orders, retention")
