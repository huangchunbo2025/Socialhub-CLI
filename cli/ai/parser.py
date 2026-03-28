"""Response parsers — extract structured data from AI responses."""

import re


def extract_scheduled_task(response: str) -> dict:
    """Extract scheduled task from response."""
    if "[SCHEDULE_TASK]" not in response or "[/SCHEDULE_TASK]" not in response:
        return {}

    match = re.search(r"\[SCHEDULE_TASK\](.*?)\[/SCHEDULE_TASK\]", response, re.DOTALL)
    if not match:
        return {}

    task_text = match.group(1)
    task = {}

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


def extract_plan_steps(response: str) -> list[dict]:
    """Extract steps from a multi-step plan response."""
    steps = []

    if "[PLAN_START]" not in response or "[PLAN_END]" not in response:
        return steps

    plan_match = re.search(r"\[PLAN_START\](.*?)\[PLAN_END\]", response, re.DOTALL)
    if not plan_match:
        return steps

    plan_text = plan_match.group(1)

    # Pattern 1: With ```bash code blocks
    step_pattern1 = r"Step\s*(\d+)[：:]\s*(.+?)\n```bash\n(.+?)\n```"
    matches = re.findall(step_pattern1, plan_text, re.DOTALL)

    if not matches:
        # Pattern 2: Command on next line after description
        step_pattern2 = r"Step\s*(\d+)[：:]\s*(.+?)\n+\s*(sh\s+[^\n]+)"
        matches = re.findall(step_pattern2, plan_text, re.DOTALL)

    if not matches:
        # Pattern 3: Command in code block without bash marker
        step_pattern3 = r"Step\s*(\d+)[：:]\s*(.+?)\n```\n(.+?)\n```"
        matches = re.findall(step_pattern3, plan_text, re.DOTALL)

    for match in matches:
        step_num, description, command = match
        cmd = command.strip().strip('`').strip()
        steps.append({
            "number": int(step_num),
            "description": description.strip(),
            "command": cmd,
        })

    return steps
