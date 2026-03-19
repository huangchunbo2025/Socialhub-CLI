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

SYSTEM_PROMPT = """你是 SocialHub.AI CLI 的智能助手，帮助用户使用命令行工具进行数据分析和营销管理。

所有命令都必须以 "sh " 前缀开头！

可用的命令包括：
1. 数据分析 (analytics)
   - sh analytics overview --period=7d|30d|365d  # 概览分析
   - sh analytics customers --period=30d  # 客户分析
   - sh analytics retention --days=7,14,30  # 留存分析
   - sh analytics orders --period=30d --by=channel|province  # 订单分析
   - sh analytics chart bar --data=customers --group=customer_type --output=chart.png  # 生成柱状图
   - sh analytics chart pie --data=customers --group=customer_type --output=pie.png  # 生成饼图
   - sh analytics chart dashboard --output=dashboard.png  # 生成分析仪表板
   - sh analytics chart funnel --output=funnel.png  # 生成漏斗图
   - sh analytics report --output=report.html  # 生成HTML分析报告（可打印为PDF）
   - sh analytics report --title="月度分析报告" --output=monthly.html  # 自定义标题的报告

2. 客户管理 (customers)
   - sh customers list --type=member|registered|visitor  # 客户列表
   - sh customers search --phone=xxx --email=xxx  # 搜索客户
   - sh customers get <customer_id>  # 客户详情
   - sh customers export --output=file.csv  # 导出客户

3. 分群管理 (segments)
   - sh segments list  # 分群列表
   - sh segments create --name="名称" --rules='{"key":"value"}'  # 创建分群
   - sh segments export <segment_id> --output=file.csv  # 导出分群

4. 标签管理 (tags)
   - sh tags list --type=rfm|aipl|static  # 标签列表
   - sh tags create --name="标签名" --type=static --values="值1,值2"  # 创建标签

5. 营销活动 (campaigns)
   - sh campaigns list --status=draft|running|finished  # 活动列表
   - sh campaigns analysis <campaign_id> --funnel  # 活动分析
   - sh campaigns calendar --month=2024-03  # 营销日历

6. 优惠券 (coupons)
   - sh coupons rules list  # 优惠券规则
   - sh coupons list --status=unused|used|expired  # 优惠券列表
   - sh coupons analysis <rule_id>  # 优惠券分析

7. 积分 (points)
   - sh points rules list  # 积分规则
   - sh points balance <member_id>  # 积分余额
   - sh points history <member_id>  # 积分历史

8. 消息 (messages)
   - sh messages templates list --channel=sms|email|wechat  # 消息模板
   - sh messages records --status=success|failed  # 发送记录
   - sh messages stats --period=7d  # 消息统计

## 回复格式规则

当用户请求需要多个步骤完成时，使用以下格式输出计划：

```
[PLAN_START]
步骤 1: <步骤描述>
```bash
<命令>
```

步骤 2: <步骤描述>
```bash
<命令>
```

...更多步骤...
[PLAN_END]

<洞察说明或分析建议>
```

当用户请求只需要单个命令时，直接输出：
```bash
<命令>
```
并附上简要说明。

## 定时任务

当用户要求设置定时任务时，使用 [SCHEDULE_TASK] 标记输出任务配置：

```
[SCHEDULE_TASK]
- ID: <任务唯一标识>
- 名称: <任务名称>
- 频率: <每天/每周/每小时 HH:MM>
- 命令: <要执行的sh命令>
- 说明: <任务描述>
- 洞察: <是否需要AI洞察分析 true/false>
[/SCHEDULE_TASK]
```

示例：用户说"每天晚上8点生成渠道分析报告"
```
[SCHEDULE_TASK]
- ID: daily-channel-report
- 名称: 每日渠道分析报告
- 频率: 每天 20:00
- 命令: sh analytics orders --by=channel && sh analytics report --title="渠道分析报告" --output=channel_report.html
- 说明: 每天晚上8点自动生成客户渠道分析报告
- 洞察: true
[/SCHEDULE_TASK]
任务已添加到定时计划中，将在每天 20:00 自动执行并生成 AI 洞察分析。
```

重要规则：
1. 所有命令必须以 "sh " 前缀开头！
2. 多步骤分析必须使用 [PLAN_START] 和 [PLAN_END] 标记包裹
3. 每个步骤必须有清晰的描述和对应的命令
4. 定时任务必须使用 [SCHEDULE_TASK] 标记
5. 回复使用中文
"""


def call_ai_api(user_message: str, api_key: Optional[str] = None) -> str:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI)."""
    ai_config = get_ai_config()
    provider = ai_config["provider"]

    try:
        if provider == "azure":
            # Azure OpenAI
            key = api_key or ai_config["azure_api_key"]
            if not key:
                return "错误：未配置 Azure OpenAI API Key。请运行 'sh config set ai.azure_api_key YOUR_KEY' 或设置环境变量 AZURE_OPENAI_API_KEY。"

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
            # Standard OpenAI
            key = api_key or ai_config["openai_api_key"]
            if not key:
                return "错误：未配置 OpenAI API Key。请运行 'sh config set ai.openai_api_key YOUR_KEY' 或设置环境变量 OPENAI_API_KEY。"

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

        if response.status_code != 200:
            return f"API 错误: {response.status_code} - {response.text}"

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        return "错误：API 请求超时，请重试。"
    except Exception as e:
        return f"错误：{str(e)}"


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
        "name": r"-\s*名称:\s*(.+)",
        "frequency": r"-\s*频率:\s*(.+)",
        "command": r"-\s*命令:\s*(.+)",
        "description": r"-\s*说明:\s*(.+)",
        "insights": r"-\s*洞察:\s*(.+)",
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

        # Find the position to insert (before "## 执行日志")
        insert_marker = "## 执行日志"
        if insert_marker not in content:
            insert_marker = "## 添加新任务模板"

        # Create task entry
        task_entry = f"""
### {len(re.findall(r'### \d+\.', content)) + 1}. {task.get('name', 'New Task')}
- **ID**: {task.get('id', 'task-' + datetime.now().strftime('%Y%m%d%H%M%S'))}
- **频率**: {task.get('frequency', '每天 00:00')}
- **状态**: `pending`
- **命令**:
  ```bash
  {task.get('command', 'sh analytics overview')}
  ```
- **说明**: {task.get('description', '')}
- **AI洞察**: {task.get('insights', 'false')}

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
        console.print(f"[red]保存定时任务失败: {e}[/red]")
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
    step_pattern1 = r"步骤\s*(\d+)[：:]\s*(.+?)\n```bash\n(.+?)\n```"
    matches = re.findall(step_pattern1, plan_text, re.DOTALL)

    if not matches:
        # Pattern 2: Command on next line after description (no code block)
        step_pattern2 = r"步骤\s*(\d+)[：:]\s*(.+?)\n+\s*(sh\s+[^\n]+)"
        matches = re.findall(step_pattern2, plan_text, re.DOTALL)

    if not matches:
        # Pattern 3: Command in code block without bash marker
        step_pattern3 = r"步骤\s*(\d+)[：:]\s*(.+?)\n```\n(.+?)\n```"
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
        return False, "命令执行超时"
    except Exception as e:
        return False, f"执行错误: {str(e)}"


def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on query results."""
    # Build context from results
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    if not results_text:
        return ""

    insight_prompt = f"""用户查询: {query}

以下是执行分析后得到的数据结果:
{results_text}

请基于以上数据，提供简洁的洞察分析:
1. 关键发现 (2-3点)
2. 趋势分析
3. 业务建议 (1-2条可执行建议)

直接输出洞察内容，不要输出命令。用中文回复，简洁专业。"""

    return call_ai_api(insight_prompt)


def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute a multi-step plan with progress display."""
    console.print(f"\n[bold cyan]开始执行 {len(steps)} 个步骤...[/bold cyan]\n")

    # Collect results for insights
    all_results = []

    for step in steps:
        step_num = step["number"]
        description = step["description"]
        command = step["command"]

        # Display step header
        console.print(f"[bold yellow]步骤 {step_num}:[/bold yellow] {description}")
        console.print(f"[dim]命令: {command}[/dim]\n")

        # Execute command
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description=f"执行中...", total=None)
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
            console.print(f"[green][OK][/green] 步骤 {step_num} 完成\n")
            if output:
                console.print(output)
        else:
            console.print(f"[red][FAIL][/red] 步骤 {step_num} 失败\n")
            if output:
                console.print(f"[red]{output}[/red]")

            # Ask whether to continue
            if step_num < len(steps):
                if not typer.confirm("是否继续执行后续步骤?", default=False):
                    console.print("[yellow]执行已取消[/yellow]")
                    return

        console.print()  # Add spacing between steps

    console.print("[bold green]所有步骤执行完成![/bold green]\n")

    # Generate insights if we have results and original query
    if original_query and any(r["success"] for r in all_results):
        console.print("[bold cyan]正在生成洞察分析...[/bold cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description="AI 分析中...", total=None)
            insights = generate_insights(original_query, all_results)

        if insights and "错误" not in insights:
            console.print(Panel(
                Markdown(insights),
                title="[bold magenta]AI 洞察分析[/bold magenta]",
                border_style="magenta",
            ))


@app.command("chat")
def ai_chat(
    query: str = typer.Argument(..., help="自然语言查询"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="OpenAI API Key"),
    execute: bool = typer.Option(False, "--execute", "-e", help="自动执行生成的命令"),
    auto: bool = typer.Option(False, "--auto", "-a", help="自动执行多步骤计划（需确认）"),
) -> None:
    """
    使用自然语言与 CLI 交互。

    示例:
        ai chat "分析最近30天的客户留存"
        ai chat "查看所有VIP会员"
        ai chat "导出高价值客户到Excel"
        ai chat "查看历史订单的分布及趋势" --auto
    """
    console.print(f"\n[dim]正在分析: {query}[/dim]\n")

    response = call_ai_api(query, api_key)

    # Check for multi-step plan
    steps = extract_plan_steps(response)

    if steps:
        # Display plan without the markers
        display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        console.print(Panel(Markdown(display_response), title="AI 助手 - 分析计划", border_style="cyan"))

        # Ask for confirmation to execute plan
        if auto or execute:
            console.print(f"\n[bold]检测到 {len(steps)} 个执行步骤:[/bold]")
            for step in steps:
                console.print(f"  {step['number']}. {step['description']}")

            console.print()
            if typer.confirm("是否执行以上计划?", default=True):
                execute_plan(steps, original_query=query)
            else:
                console.print("[yellow]计划未执行。您可以手动运行上述命令。[/yellow]")
    else:
        # Display response as markdown
        console.print(Panel(Markdown(response), title="AI 助手", border_style="cyan"))

        # Extract and optionally execute single command
        if (execute or auto) and "```bash" in response:
            commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
            if commands:
                cmd = commands[0].strip()
                if typer.confirm(f"\n执行命令: {cmd}?"):
                    console.print(f"\n[dim]执行: {cmd}[/dim]\n")
                    success, output = execute_command(cmd)
                    if output:
                        console.print(output)


@app.command("help")
def ai_help(
    topic: str = typer.Argument("general", help="帮助主题"),
) -> None:
    """获取特定功能的帮助说明。"""
    help_topics = {
        "general": """
## SocialHub.AI CLI 使用指南

### 快速开始
```bash
# 查看所有命令
python -m socialhub.cli.main --help

# 数据分析
python -m socialhub.cli.main analytics overview

# 客户管理
python -m socialhub.cli.main customers list
```

### AI 助手
使用自然语言与 CLI 交互：
```bash
python -m socialhub.cli.main ai chat "你的问题"
```
        """,
        "analytics": """
## 数据分析命令

### 概览分析
```bash
python -m socialhub.cli.main analytics overview --period=7d
python -m socialhub.cli.main analytics overview --from=2024-01-01 --to=2024-03-01
```

### 客户分析
```bash
python -m socialhub.cli.main analytics customers --period=30d
python -m socialhub.cli.main analytics retention --days=7,14,30
```

### 订单分析
```bash
python -m socialhub.cli.main analytics orders --period=30d
python -m socialhub.cli.main analytics orders --by=channel
```
        """,
        "customers": """
## 客户管理命令

### 查询客户
```bash
python -m socialhub.cli.main customers list --type=member
python -m socialhub.cli.main customers search --phone=138
python -m socialhub.cli.main customers get C001
```

### 导出客户
```bash
python -m socialhub.cli.main customers export --output=customers.csv
python -m socialhub.cli.main customers export --type=member --output=members.xlsx
```
        """,
    }

    content = help_topics.get(topic, help_topics["general"])
    console.print(Markdown(content))


# Shortcuts for common queries
@app.command("分析")
def analyze_shortcut(
    target: str = typer.Argument("概览", help="分析目标: 概览/客户/订单/留存"),
    period: str = typer.Option("30d", "--period", "-p", help="时间周期"),
) -> None:
    """快捷分析命令（中文）。"""
    from . import analytics

    target_map = {
        "概览": lambda: analytics.analytics_overview(period=period, format="table", from_date=None, to_date=None, customer_type="all", output=None),
        "客户": lambda: analytics.analytics_customers(period=period, channel="all", format="table", output=None),
        "订单": lambda: analytics.analytics_orders(period=period, metric="sales", repurchase_rate=False, by=None, format="table", output=None),
        "留存": lambda: analytics.analytics_retention(days="7,14,30", format="table", output=None),
    }

    if target in target_map:
        target_map[target]()
    else:
        console.print(f"[yellow]未知分析目标: {target}[/yellow]")
        console.print("可选: 概览, 客户, 订单, 留存")
