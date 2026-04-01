> CTO 审查: 有条件批准 — 2026-03-31

# SocialHub CLI 架构先进性提升 — 技术实现方案

**文档版本**: 1.0
**写作日期**: 2026-03-31
**状态**: 已完成 3 轮自我对抗迭代
**上游文档**: 05-prd.md（唯一需求来源）
**读者**: 实现工程师（按本文档可直接开始编码，无需再问问题）

---

## 总览

本文档覆盖 7 项改进的完整技术实现方案，每项改动均可追溯到 PRD 验收标准（AC）。文档末尾记录了 3 轮自我对抗迭代的修正记录。

### 文件改动总表

| # | 文件 | 类型 | 行数估计 | 关联改进 |
|---|------|------|---------|---------|
| 1 | `cli/skills/security.py` | 修改 | ~5 行 | 改进一 |
| 2 | `cli/commands/skills.py` | 修改 | ~60 行 | 改进一 |
| 3 | `cli/skills/manager.py` | 修改 | ~80 行 | 改进一 |
| 4 | `cli/main.py` | 修改 | ~50 行 | 改进二 |
| 5 | `cli/output/formatter.py` | 新建 | ~150 行 | 改进二 |
| 6 | `cli/commands/analytics.py` | 修改 | ~80 行 | 改进二 |
| 7 | `cli/commands/customers.py` | 修改 | ~50 行 | 改进二 |
| 8 | `cli/ai/sanitizer.py` | 新建 | ~60 行 | 改进三 |
| 9 | `cli/main.py` | 修改 | ~15 行 | 改进三 |
| 10 | `cli/ai/executor.py` | 修改 | ~70 行 | 改进三 |
| 11 | `cli/config.py` | 修改 | ~30 行 | 改进三/四/五/六 |
| 12 | `cli/ai/session.py` | 新建 | ~120 行 | 改进四 |
| 13 | `cli/commands/session_cmd.py` | 新建 | ~80 行 | 改进四 |
| 14 | `cli/main.py` | 修改 | ~40 行 | 改进四 |
| 15 | `cli/ai/client.py` | 修改 | ~30 行 | 改进四/五 |
| 16 | `cli/ai/trace.py` | 新建 | ~130 行 | 改进五 |
| 17 | `cli/commands/trace_cmd.py` | 新建 | ~80 行 | 改进五 |
| 18 | `cli/api/client.py` | 修改 | ~30 行 | 改进六 |
| 19 | `cli/skills/store_client.py` | 修改 | ~25 行 | 改进六 |
| 20 | `cli/commands/config_cmd.py` | 修改 | ~50 行 | 改进六 |
| 21 | `mcp_server/server.py` | 修改 | ~120 行 | 改进七 |
| 22 | `build/m365-agent/mcp-tools.json` | 修改 | ~200 行 | 改进七 |
| 23 | `tests/test_tool_schema_consistency.py` | 修改 | ~20 行 | 改进七 |

---

## 改进一：Ed25519 真实密钥对

**PRD 来源**: 改进清单 §改进一，AC-1 ~ AC-7

### 1.1 生成真实密钥对（运维一次性操作）

```bash
# 生成 Ed25519 私钥（PEM 格式）
openssl genpkey -algorithm Ed25519 -out socialhub_skill_signing.pem

# 导出公钥（DER 格式，与代码中 SubjectPublicKeyInfo 格式一致）
openssl pkey -in socialhub_skill_signing.pem -pubout -outform DER -out socialhub_skill_signing_pub.der

# 转为 Base64（单行，与现有代码 OFFICIAL_PUBLIC_KEY_B64 格式完全相同）
base64 -w 0 socialhub_skill_signing_pub.der
# 输出类似：MCowBQYDK2VwAyEA<真实32字节公钥的base64>=

# 计算指纹（用于 EXPECTED_KEY_FINGERPRINT）
openssl dgst -sha256 socialhub_skill_signing_pub.der | awk '{print "sha256:" $2}'
```

**私钥安全存储**：
- 将 PEM 文件内容写入 Render 平台 Secret，Key 名为 `SKILL_SIGNING_PRIVATE_KEY`
- 本地临时文件在部署后立即删除：`shred -u socialhub_skill_signing.pem`
- 永远不提交到代码仓库（在 `.gitignore` 中追加 `*.pem`）

### 1.2 公钥替换

```
改动文件: cli/skills/security.py
改动类型: 修改
改动行数估计: ~5 行（第 39、48 行）
改动描述: 替换 OFFICIAL_PUBLIC_KEY_B64 和 EXPECTED_KEY_FINGERPRINT 两个占位符常量
```

**改动位置**：`cli/skills/security.py` 第 39 行（`OFFICIAL_PUBLIC_KEY_B64`）和第 48 行（`EXPECTED_KEY_FINGERPRINT`）

```python
# 改前（占位符）
OFFICIAL_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAK5mPmkJXzWvHxLxV9G6Y8Z3q1fJnRt0vLhQE7YKp2Hw="
EXPECTED_KEY_FINGERPRINT = "sha256:a1b2c3d4e5f6..."  # placeholder

# 改后（真实值，运维生成后填入）
OFFICIAL_PUBLIC_KEY_B64 = "<上一步 base64 -w 0 的输出>"
EXPECTED_KEY_FINGERPRINT = "<openssl dgst 的输出>"
```

**Base64 格式说明**：`base64 -w 0` 输出不含换行的单行 Base64，与现有 `base64.b64decode(self.OFFICIAL_PUBLIC_KEY_B64)` 调用完全兼容（见 `security.py` load_public_key 方法）。

### 1.3 --dev-mode 本地安装实现

```
改动文件: cli/commands/skills.py
改动类型: 修改
改动行数估计: ~60 行
改动描述: 在 install 命令添加 --dev-mode 选项，走独立的本地安装分支
```

**在 `cli/commands/skills.py` 的 `install` 命令函数中新增参数**（在现有 `name`、`version`、`force` 参数之后）：

```python
@app.command()
def install(
    name: str = typer.Argument(..., help="Skill name or local path (with --dev-mode)"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Version"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall"),
    dev_mode: bool = typer.Option(
        False,
        "--dev-mode",
        help="Install from local zip file (skips signature verification, sandbox still enforced)",
    ),
):
    """Install a skill from the official store, or a local zip with --dev-mode."""
    if dev_mode:
        _install_dev_mode(name, force)
    else:
        _install_from_store(name, version, force)
```

```
改动文件: cli/skills/manager.py
改动类型: 修改
改动行数估计: ~80 行
改动描述: 新增 install_dev_mode() 方法，跳过签名验证但保留沙箱激活；在 registry.json 中标注 source=local_dev
```

**在 `cli/skills/manager.py` 的 `SkillManager` 类中新增方法**（位于现有 `install()` 方法之后约第 170 行）：

```python
def install_dev_mode(self, local_path: str, force: bool = False) -> InstalledSkill:
    """Install a skill from a local zip file (dev mode only).

    SECURITY NOTE: Signature verification is SKIPPED in dev mode.
    The three-layer sandbox (filesystem/network/execute) is still enforced.
    This mode is ONLY for local development and testing of skills.
    The installed skill is marked source='local_dev' in registry.json.

    Args:
        local_path: Absolute or relative path to local .zip file
        force: Force reinstall if already installed

    Returns:
        InstalledSkill record with source='local_dev'

    Raises:
        SkillManagerError: If path is not a local file or not a valid zip
        SecurityError: Should never happen (signature skipped), but sandbox violations still raise
    """
    import zipfile
    from pathlib import Path

    path = Path(local_path).resolve()

    # Enforce: only local file paths are allowed in dev mode (no URLs)
    if str(local_path).startswith(("http://", "https://", "ftp://")):
        raise SkillManagerError(
            "--dev-mode only accepts local file paths. "
            "To install from the store, omit --dev-mode."
        )

    if not path.exists():
        raise SkillManagerError(f"File not found: {path}")

    if not path.suffix == ".zip":
        raise SkillManagerError(f"Expected a .zip file, got: {path.suffix}")

    if not zipfile.is_zipfile(path):
        raise SkillManagerError(f"Not a valid zip file: {path}")

    # Read the zip and parse manifest (same as normal install)
    package_content = path.read_bytes()

    # Step: Verify hash integrity (SHA-256 still checked for corruption detection)
    # NOTE: We compute hash but do NOT compare against a remote-provided expected hash.
    # This detects file corruption but not tampering (acceptable for dev mode).
    actual_hash = compute_package_hash(package_content)

    # Steps: Extract, load manifest, check permissions (same as normal install)
    # SKIPPED: Ed25519 signature verification (dev mode exemption)
    self.audit_logger.log_event(
        event="DEV_MODE_INSTALL",
        severity="INFO",
        skill_name=str(path.name),
        note="Signature verification skipped (dev-mode). Sandbox enforced.",
    )

    # Extract to install path
    name = path.stem  # use filename without .zip as skill name
    install_path = self.registry.get_skill_path(name)
    if install_path.exists():
        if not force:
            raise SkillManagerError(
                f"Skill '{name}' already installed (dev mode). Use --force to reinstall."
            )
        shutil.rmtree(install_path)

    install_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(install_path)

    # Load manifest
    manifest_path = install_path / "manifest.yaml"
    if not manifest_path.exists():
        raise SkillManagerError("Missing manifest.yaml in skill zip")

    import yaml
    with open(manifest_path, encoding="utf-8") as f:
        manifest_data = yaml.safe_load(f)
    manifest = SkillManifest(**manifest_data)

    # Record in registry with source=local_dev (AC-5 requirement)
    installed_skill = InstalledSkill(
        name=name,
        version=manifest.version,
        installed_at=datetime.now().isoformat(),
        source="local_dev",           # AC-5: distinct from 'store' installs
        install_path=str(install_path),
        hash=actual_hash,
        signature="",                  # no signature in dev mode
        permissions=manifest.permissions if hasattr(manifest, "permissions") else [],
    )
    self.registry.save(installed_skill)

    console.print(
        f"[green][OK] Skill '{name}' installed in dev mode (signature skipped, sandbox active)[/green]"
    )
    console.print("[yellow]Warning: This skill is not signed. Only use for local development.[/yellow]")
    return installed_skill
```

### 1.4 开发者通知模板（AC-6）

通知模板在 PRD §改进一 中已定义。发送方式：Skills Store 后端管理员端点 `POST /api/v1/admin/notify-all-developers`，请求体：

```json
{
  "subject": "[SocialHub] Skills 签名验证问题已修复 — 请验证您的 Skill",
  "body": "您好，\n\n我们修复了一个影响 Skills 安装的基础问题：由于公钥配置错误，过去所有 Skill 的安装均会失败。这不是您的 Skill 代码的问题。\n\n修复已于今日部署。请使用最新版本的 SocialHub CLI 验证您的 Skill 是否可以正常安装：\n  socialhub skills install <your-skill-name>\n\n如遇到任何问题，请通过 [支持渠道] 联系我们。\n\n感谢您对 SocialHub 生态的贡献。\nSocialHub 团队"
}
```

此步骤是密钥修复的**验收条件之一**（AC-6），在部署当天执行，不可遗漏。

---

## 改进二：--output-format json/csv/stream-json

**PRD 来源**: 改进清单 §改进二，AC-1 ~ AC-9；接口规范 §4.1

### 2.1 全局选项声明

```
改动文件: cli/main.py
改动类型: 修改
改动行数估计: ~50 行
改动描述: 在 @app.callback() main() 函数签名中添加 output_format 参数，读取环境变量，存入上下文
```

**插入位置**：`cli/main.py` 第 87 行 `@app.callback()` 装饰器所在的 `main()` 函数。

```python
# 在文件顶部补充导入（第 4 行附近）
import os

# 修改 main() 函数签名（第 88-110 行区段完整替换）
@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    output_format: str = typer.Option(
        None,
        "--output-format",
        help="Output format: text | json | stream-json | csv",
        envvar="SOCIALHUB_OUTPUT_FORMAT",
    ),
) -> None:
    """SocialHub.AI CLI ..."""
    # Validate output_format value
    valid_formats = {"text", "json", "stream-json", "csv", None}
    if output_format not in valid_formats:
        console.print(f"[red]Invalid --output-format '{output_format}'. Choose: text, json, stream-json, csv[/red]")
        raise typer.Exit(1)

    # Store in context for sub-commands to read
    ctx.ensure_object(dict)
    ctx.obj["output_format"] = output_format or "text"
```

**注意**：`ctx: typer.Context` 参数必须是第一个参数（Typer 约定）。

### 2.2 OutputFormatter 类

```
改动文件: cli/output/formatter.py
改动类型: 新建
改动行数估计: ~150 行
改动描述: 统一输出格式器，支持 text/json/csv/stream-json 四种模式，严格 stdout/stderr 分离
```

```python
"""OutputFormatter — 统一输出格式管理，严格 stdout/stderr 分离。

设计约束（来自 PRD §4.1）：
- json 模式：stdout 只有一行完整 JSON，无 ANSI 转义码
- csv 模式：第一行列标题，值 UTF-8，无 ANSI 转义码
- stream-json 模式：每行独立合法 JSON（NDJSON）
- text 模式：现有 Rich 渲染完全不变（向后兼容）
"""

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from rich.console import Console


# stderr-only console：进度条和诊断信息写这里，不污染 stdout
_stderr_console = Console(stderr=True)

# stdout-only console：text 模式的 Rich 渲染写这里
_stdout_console = Console()


class OutputFormatter:
    """Context-aware output formatter.

    Usage in command handlers:
        formatter = OutputFormatter.from_context(ctx)
        formatter.output(data=rows, columns=["segment", "count"])
    """

    VALID_FORMATS = {"text", "json", "stream-json", "csv"}

    def __init__(self, fmt: str = "text"):
        if fmt not in self.VALID_FORMATS:
            fmt = "text"
        self.fmt = fmt
        # In non-text mode, Rich console output must go to stderr only
        self.console = _stderr_console if fmt != "text" else _stdout_console

    @classmethod
    def from_context(cls, ctx: "typer.Context") -> "OutputFormatter":
        """Construct from Typer context object."""
        obj = ctx.find_root().obj or {}
        fmt = obj.get("output_format", "text")
        return cls(fmt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def output(
        self,
        data: Any,
        columns: Optional[list[str]] = None,
        command: str = "",
        tenant_id: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Output data in the configured format.

        Args:
            data: List of dicts (table rows) or a single dict (summary)
            columns: Column names for CSV header. If None, inferred from data.
            command: Command name for JSON envelope (e.g. "analytics overview")
            tenant_id: Tenant ID for JSON envelope
            duration_ms: Execution duration in ms for JSON metadata
        """
        if self.fmt == "text":
            return  # Caller handles Rich rendering directly

        now = datetime.now(timezone.utc).isoformat()
        record_count = len(data) if isinstance(data, list) else 1

        if self.fmt == "json":
            envelope = {
                "success": True,
                "command": command,
                "timestamp": now,
                "tenant_id": tenant_id,
                "data": data,
                "metadata": {
                    "duration_ms": duration_ms,
                    "record_count": record_count,
                },
                "warnings": [],
            }
            # Single line JSON to stdout — no ANSI codes
            print(json.dumps(envelope, ensure_ascii=False), file=sys.stdout)

        elif self.fmt == "stream-json":
            # start event
            self._write_ndjson({"type": "start", "command": command, "timestamp": now})
            # data events
            rows = data if isinstance(data, list) else [data]
            for row in rows:
                self._write_ndjson({"type": "data", "data": row})
            # end event
            self._write_ndjson({
                "type": "end",
                "metadata": {"record_count": record_count, "duration_ms": duration_ms},
            })

        elif self.fmt == "csv":
            rows = data if isinstance(data, list) else [data]
            if not rows:
                return
            cols = columns or list(rows[0].keys())
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=cols,
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

    def output_error(
        self,
        message: str,
        code: str = "ERROR",
        suggestion: str = "",
        command: str = "",
    ) -> None:
        """Output error in the configured format."""
        now = datetime.now(timezone.utc).isoformat()

        if self.fmt == "json":
            envelope = {
                "success": False,
                "command": command,
                "timestamp": now,
                "error": {
                    "code": code,
                    "message": message,
                    "suggestion": suggestion,
                },
            }
            print(json.dumps(envelope, ensure_ascii=False), file=sys.stdout)

        elif self.fmt == "stream-json":
            self._write_ndjson({
                "type": "error",
                "error": {"code": code, "message": message, "suggestion": suggestion},
            })

        elif self.fmt == "csv":
            # CSV errors go to stderr
            print(f"ERROR: {message}", file=sys.stderr)

        else:
            # text mode: caller handles rich rendering
            pass

    def emit_progress(self, message: str) -> None:
        """Emit a progress event (stream-json only; silent in other non-text modes)."""
        if self.fmt == "stream-json":
            self._write_ndjson({"type": "progress", "message": message})
        elif self.fmt == "text":
            self.console.print(f"[dim]{message}[/dim]")
        # json and csv modes: silence all progress output (AC-5)

    def is_text_mode(self) -> bool:
        return self.fmt == "text"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_ndjson(self, obj: dict) -> None:
        """Write one NDJSON line to stdout."""
        print(json.dumps(obj, ensure_ascii=False), file=sys.stdout)
        sys.stdout.flush()
```

**stream-json NDJSON event schema**（AC-3）：

| type | 含义 | 额外字段 |
|------|------|---------|
| `start` | 命令开始 | `command`, `timestamp` |
| `data` | 一行数据 | `data` (dict) |
| `progress` | 进度提示 | `message` |
| `end` | 命令完成 | `metadata.record_count`, `metadata.duration_ms` |
| `error` | 执行失败 | `error.code`, `error.message`, `error.suggestion` |

### 2.3 命令层注入方式

**注入模式**：在各命令函数签名中接收 `ctx: typer.Context`，通过 `OutputFormatter.from_context(ctx)` 构造 formatter，用 `if formatter.is_text_mode()` 分支区分渲染路径。

```
改动文件: cli/commands/analytics.py
改动类型: 修改
改动行数估计: ~80 行（6 个目标命令各约 13 行改动）
改动描述: 在 overview/customers/orders/retention 命令添加 ctx 参数，分支渲染
```

**以 `analytics overview` 为例**（其他 5 个命令同理）：

```python
@app.command()
def overview(
    ctx: typer.Context,
    # ... 现有参数不变 ...
):
    from cli.output.formatter import OutputFormatter
    formatter = OutputFormatter.from_context(ctx)

    # ... 现有数据获取逻辑不变 ...
    data = get_overview_data(...)  # 现有逻辑

    if formatter.is_text_mode():
        # 现有 Rich 渲染完全不变（向后兼容 AC-7）
        console.print(table)
    else:
        formatter.output(
            data=rows,
            columns=["segment", "count", "revenue"],
            command="analytics overview",
            tenant_id=config.tenant_id,
            duration_ms=elapsed_ms,
        )
```

### 2.4 stdout/stderr 分离方案

`OutputFormatter.console` 在非 text 模式指向 `Console(stderr=True)`。命令函数中**凡使用 `console.print()`** 的进度/状态输出，需判断 `formatter.is_text_mode()` 后才调用，或替换为 `formatter.emit_progress()`。

**关键约束**：json 模式下，`sys.stdout` 只能有 `print(json.dumps(...))` 这一行写入，任何其他写入都会破坏 `jq` 解析（PRD §4.1 核心约束）。

---

## 改进三：输入净化 + 执行护栏

**PRD 来源**: 改进清单 §改进三，AC-1 ~ AC-8；接口规范 §4.4

### 3.1 cli/ai/sanitizer.py（新建）

```
改动文件: cli/ai/sanitizer.py
改动类型: 新建
改动行数估计: ~60 行
改动描述: 用户输入净化模块，移除控制标记防止计划注入，注入尝试写入 SecurityAuditLogger
```

```python
"""Input sanitizer — prevents prompt injection via control markers.

PRD AC-1: [PLAN_START] injected in user input must NOT trigger plan execution.
PRD AC-7: sanitize_user_input() is called in cli/main.py BEFORE call_ai_api().
No new dependencies — pure standard library (re, hashlib).
"""

import hashlib
import re
from typing import Optional


# Markers that have special meaning in parser.py — must be stripped from user input
_CONTROL_MARKERS = [
    "[PLAN_START]",
    "[PLAN_END]",
    "[STEP:",      # prefix match, so strip anything starting with [STEP:
    "[INSIGHT_START]",
    "[INSIGHT_END]",
    "[SCHEDULE_TASK]",
    "[/SCHEDULE_TASK]",
]

# Regex for bracket-style markers (covers partial/malformed variants)
_MARKER_PATTERN = re.compile(
    r"\[(?:PLAN_START|PLAN_END|STEP:[^\]]*|INSIGHT_START|INSIGHT_END|SCHEDULE_TASK|/SCHEDULE_TASK)\]",
    re.IGNORECASE,
)


def contains_control_markers(text: str) -> bool:
    """Return True if text contains any SocialHub control markers.

    Used to decide whether to log a security audit event.
    """
    return bool(_MARKER_PATTERN.search(text))


def sanitize_user_input(
    text: str,
    audit_logger: Optional[object] = None,
    tenant_id: str = "",
) -> str:
    """Strip control markers from user input.

    If markers are detected, logs a PLAN_INJECTION_ATTEMPT event to audit_logger
    (the SHA-256 hash of original input, NOT the plaintext — PRD AC-5).

    Args:
        text: Raw user input from CLI argv
        audit_logger: SecurityAuditLogger instance (optional). If None, no audit log.
        tenant_id: For audit log context.

    Returns:
        Sanitized text with all control markers removed.
    """
    if not contains_control_markers(text):
        return text

    # Log injection attempt BEFORE sanitizing (hash of original input)
    if audit_logger is not None:
        input_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        audit_logger.log_event(
            event="PLAN_INJECTION_ATTEMPT",
            severity="HIGH",
            user_input_hash=input_hash,
            tenant_id=tenant_id,
        )

    # Strip all control markers
    sanitized = _MARKER_PATTERN.sub("", text).strip()
    return sanitized
```

### 3.2 调用位置（parser.py 之前）

```
改动文件: cli/main.py
改动类型: 修改
改动行数估计: ~15 行
改动描述: 在 call_ai_api(query) 调用之前插入 sanitize_user_input()，对 query 净化
```

**插入位置**：`cli/main.py` 第 231 行 `response = call_ai_api(query)` 之前：

```python
# 在 try 块顶部（第 221 行附近）的局部 import 区段追加：
from .ai.sanitizer import sanitize_user_input
from .skills.security import SecurityAuditLogger as _AuditLogger

# 第 231 行改为：
_audit = _AuditLogger()
query = sanitize_user_input(query, audit_logger=_audit, tenant_id="")
response = call_ai_api(query)
```

**设计说明**：`sanitize_user_input` 在 `call_ai_api()` 之前调用，`validate_command()` 在 `execute_command()` 之前调用，两层独立，各自职责明确（PRD §5.2 合规性确认）。

### 3.3 executor.py 三层护栏

```
改动文件: cli/ai/executor.py
改动类型: 修改
改动行数估计: ~70 行
改动描述: 步骤上限截断（MAX_PLAN_STEPS）、总挂钟超时（PLAN_WALL_CLOCK）、Circuit Breaker（连续失败熔断）
```

#### 护栏一：MAX_PLAN_STEPS=10

**插入位置**：`executor.py` 第 136 行 `execute_plan()` 函数体开头（在 `console.print(...)` 之前）：

```python
def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute a multi-step plan with progress display."""
    # --- 护栏一：步骤上限截断（PRD AC-2） ---
    from ..config import load_config
    cfg = load_config()
    max_steps = int(os.getenv("SOCIALHUB_MAX_PLAN_STEPS", cfg.ai.max_plan_steps))
    step_timeout = int(cfg.ai.step_timeout_seconds)
    cb_threshold = int(cfg.ai.circuit_breaker_threshold)

    if len(steps) > max_steps:
        skipped = len(steps) - max_steps
        console.print(
            f"[yellow]注意：您的查询内容较多，已为您完成核心分析（前 {max_steps} 项）。\n"
            f"如需查看更多维度的数据，可以分别提问。\n"
            f"已跳过的分析（{skipped} 项）可通过以下方式补充：\n"
            f'  socialhub "单独分析 [跳过的内容]"[/yellow]'
        )
        steps = steps[:max_steps]
```

#### 护栏二：PLAN_WALL_CLOCK（累计总超时 300s）

**在步骤循环外记录开始时间，每步结束后检查累计耗时**：

```python
    import time as _time
    plan_start_time = _time.time()

    for idx, step in enumerate(steps):
        # ... 现有代码 ...
        success, output = execute_command(command, timeout=step_timeout)  # 注：需修改 execute_command 签名以传入 timeout

        # --- 护栏二：总挂钟超时检查（PRD AC-3） ---
        elapsed_total = _time.time() - plan_start_time
        if elapsed_total > step_timeout and idx < len(steps) - 1:
            console.print(
                f"[yellow]提示：数据加载时间较长，已为您保存已完成的分析结果。\n"
                f"已完成：{idx + 1} 项分析\n"
                f"未完成：{len(steps) - idx - 1} 项（建议缩小时间范围后重试）[/yellow]"
            )
            break
```

**同时修改 `execute_command()` 函数签名**（第 41 行），增加 `timeout` 参数：

```python
def execute_command(cmd: str, timeout: int = 120) -> tuple[bool, str]:
    # 第 74-82 行 subprocess.run 的 timeout=120 改为 timeout=timeout
```

#### 护栏三：Circuit Breaker（连续失败熔断）

**在步骤循环中跟踪连续失败计数**：

```python
    consecutive_failures = 0  # 在 for 循环之前初始化

    for idx, step in enumerate(steps):
        # ... 执行命令 ...

        if success:
            consecutive_failures = 0  # 成功则重置计数器
        else:
            consecutive_failures += 1
            # --- 护栏三：Circuit Breaker（PRD AC-4） ---
            if consecutive_failures >= cb_threshold:
                console.print(
                    "[red]提示：您的查询遇到了一些问题，无法继续执行。\n\n"
                    "建议用更具体的方式描述您的需求，例如：\n"
                    '  socialhub "帮我查看上周 VIP 客户的数量"\n\n'
                    "如果问题持续，请联系技术支持。[/red]"
                )
                return  # 中止后续步骤

            # 原有"Continue?"确认逻辑保留（<cb_threshold 时仍询问用户）
            if idx < len(steps) - 1:
                if not typer.confirm("Continue with remaining steps?", default=False):
                    console.print("[yellow]Execution cancelled[/yellow]")
                    return
```

**Circuit Breaker 状态机说明**：本实现采用**简化的两态模型**（closed / open），无 half-open 状态。原因：full state machine（closed/open/half-open）需要跨调用持久化状态，引入文件锁或进程级单例，复杂度远超收益。对于单次 `execute_plan()` 调用内的连续失败，两态模型完全够用；跨调用的熔断是未来 v2.0 特性。

### 3.4 config.py 扩展（护栏参数）

```
改动文件: cli/config.py
改动类型: 修改
改动行数估计: ~15 行（AIConfig 类扩展）
改动描述: 在 AIConfig 中新增 max_plan_steps、step_timeout_seconds、circuit_breaker_threshold 字段
```

```python
class AIConfig(BaseModel):
    # ... 现有字段 ...
    max_plan_steps: int = 10          # PRD §4.4
    step_timeout_seconds: int = 300   # PRD §4.4
    circuit_breaker_threshold: int = 3 # PRD §4.4
```

---

## 改进四：AI Session 多轮对话

**PRD 来源**: 改进清单 §改进四，AC-1 ~ AC-12；接口规范 §4.2

### 4.1 Session 文件结构

**存储位置**：`~/.socialhub/sessions/`

```
~/.socialhub/sessions/
├── index.json          # 所有 session 的元数据索引（ID、标题、时间、状态）
├── a3f2.json           # 单个 session 完整数据
└── b7c9.json
```

**单个 session_id.json 的 JSON schema**：

```json
{
  "session_id": "a3f2",
  "title": "上周 VIP 客户流失分析",
  "created_at": "2026-03-31T09:00:00Z",
  "last_active_at": "2026-03-31T11:30:00Z",
  "expires_at": "2026-04-01T11:30:00Z",
  "ttl_hours": 24,
  "messages": [
    {
      "role": "user",
      "content": "分析上周 VIP 客户流失",
      "timestamp": "2026-03-31T09:00:00Z"
    },
    {
      "role": "assistant",
      "content": "根据数据...",
      "timestamp": "2026-03-31T09:00:05Z"
    }
  ],
  "metadata": {
    "total_tokens_used": 4200,
    "query_count": 3
  }
}
```

**index.json schema**：

```json
{
  "sessions": [
    {
      "session_id": "a3f2",
      "title": "上周 VIP 客户流失分析",
      "last_active_at": "2026-03-31T11:30:00Z",
      "expires_at": "2026-04-01T11:30:00Z",
      "status": "active"
    }
  ]
}
```

### 4.2 SessionStore 类

```
改动文件: cli/ai/session.py
改动类型: 新建
改动行数估计: ~120 行
改动描述: Session 持久化存储，load/save/list/clear/is_expired 方法，TTL 计算，文件权限 600
```

```python
"""Session store — 管理多轮对话历史。

文件权限：所有 session 文件创建时 chmod 600（PRD AC-9）。
TTL：expires_at = last_active_at + ttl_hours * 3600（PRD §4.2）。
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path.home() / ".socialhub" / "sessions"
INDEX_FILE = SESSIONS_DIR / "index.json"
MAX_CONTEXT_MESSAGES = 10  # PRD AC-11：只发送最近 10 条消息


class SessionStore:
    """Persistent session storage with TTL support."""

    def __init__(self, ttl_hours: int = 24, max_sessions: int = 20):
        self.ttl_hours = ttl_hours
        self.max_sessions = max_sessions
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def new_session(self, first_query: str = "") -> dict:
        """Create a new session and save it."""
        session_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.ttl_hours)

        session = {
            "session_id": session_id,
            "title": first_query[:40] or "New session",
            "created_at": now.isoformat(),
            "last_active_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl_hours": self.ttl_hours,
            "messages": [],
            "metadata": {"total_tokens_used": 0, "query_count": 0},
        }
        self.save(session)
        return session

    def load(self, session_id: str) -> Optional[dict]:
        """Load session by ID. Returns None if not found."""
        path = SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def load_latest(self) -> Optional[dict]:
        """Load the most recently active non-expired session."""
        index = self._load_index()
        active = [s for s in index.get("sessions", []) if s.get("status") == "active"]
        if not active:
            return None
        latest = max(active, key=lambda s: s["last_active_at"])
        session = self.load(latest["session_id"])
        if session and self.is_expired(session):
            return None
        return session

    def save(self, session: dict) -> None:
        """Save session to disk (chmod 600)."""
        path = SESSIONS_DIR / f"{session['session_id']}.json"
        path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(path, 0o600)
        self._update_index(session)

    def append_message(self, session: dict, role: str, content: str, tokens: int = 0) -> None:
        """Append a message to session history and refresh TTL."""
        now = datetime.now(timezone.utc)
        session["messages"].append({
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
        })
        session["last_active_at"] = now.isoformat()
        # Refresh TTL on each interaction (PRD §4.2)
        session["expires_at"] = (now + timedelta(hours=session["ttl_hours"])).isoformat()
        session["metadata"]["total_tokens_used"] += tokens
        if role == "user":
            session["metadata"]["query_count"] += 1
        self.save(session)

    def get_context_messages(self, session: dict) -> list[dict]:
        """Return the last MAX_CONTEXT_MESSAGES messages for API context (PRD AC-11)."""
        messages = session.get("messages", [])
        # Take last 10 messages
        context = messages[-MAX_CONTEXT_MESSAGES:]
        # Strip timestamp before sending to API
        return [{"role": m["role"], "content": m["content"]} for m in context]

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def is_expired(self, session: dict) -> bool:
        """Check if session has exceeded its TTL."""
        try:
            expires_at = datetime.fromisoformat(session["expires_at"])
            return datetime.now(timezone.utc) > expires_at
        except (KeyError, ValueError):
            return True

    def list(self, limit: int = 10) -> list[dict]:
        """Return recent sessions (up to limit), sorted by last_active_at desc."""
        index = self._load_index()
        sessions = index.get("sessions", [])
        # Annotate status
        for s in sessions:
            raw = self.load(s["session_id"])
            s["status"] = "expired" if (raw and self.is_expired(raw)) else "active"
        sessions.sort(key=lambda s: s["last_active_at"], reverse=True)
        return sessions[:limit]

    def clear(self, session_id: Optional[str] = None) -> int:
        """Clear expired sessions (or a specific session by ID).

        Returns number of sessions deleted.
        """
        index = self._load_index()
        deleted = 0
        remaining = []
        for s in index.get("sessions", []):
            if session_id:
                # Clear specific session
                if s["session_id"] == session_id:
                    (SESSIONS_DIR / f"{session_id}.json").unlink(missing_ok=True)
                    deleted += 1
                    continue
            else:
                # Clear all expired sessions
                raw = self.load(s["session_id"])
                if raw and self.is_expired(raw):
                    (SESSIONS_DIR / f"{s['session_id']}.json").unlink(missing_ok=True)
                    deleted += 1
                    continue
            remaining.append(s)
        self._save_index({"sessions": remaining})
        return deleted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        if not INDEX_FILE.exists():
            return {"sessions": []}
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"sessions": []}

    def _save_index(self, index: dict) -> None:
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(INDEX_FILE, 0o600)

    def _update_index(self, session: dict) -> None:
        index = self._load_index()
        sessions = index.get("sessions", [])
        # Remove existing entry for this session_id
        sessions = [s for s in sessions if s["session_id"] != session["session_id"]]
        sessions.append({
            "session_id": session["session_id"],
            "title": session["title"],
            "last_active_at": session["last_active_at"],
            "expires_at": session["expires_at"],
            "status": "active",
        })
        # Enforce max_sessions: remove oldest expired sessions
        if len(sessions) > self.max_sessions:
            sessions.sort(key=lambda s: s["last_active_at"])
            sessions = sessions[len(sessions) - self.max_sessions:]
        self._save_index({"sessions": sessions})
```

### 4.3 main.py 中的 -c/--continue 和 --session 标志

```
改动文件: cli/main.py
改动类型: 修改
改动行数估计: ~40 行
改动描述: 在 main() 回调和 cli() 入口函数添加 -c/--continue 和 --session 全局选项，传入上下文
```

**在 `main()` 回调（第 88 行）签名中追加两个参数**（在 `output_format` 之后）：

```python
@app.callback()
def main(
    ctx: typer.Context,
    # ... version, output_format ...
    continue_session: bool = typer.Option(
        False,
        "--continue", "-c",
        help="Continue the most recent active session",
        is_flag=True,
    ),
    session_id: Optional[str] = typer.Option(
        None,
        "--session",
        help="Continue a specific session by ID",
    ),
) -> None:
    ctx.obj["continue_session"] = continue_session
    ctx.obj["session_id"] = session_id
```

**在 `cli()` 入口的 smart 模式路径（第 220 行 try 块）中**，在调用 `call_ai_api(query)` 之前处理 session：

```python
# 在 try 块开头（第 221 行附近）的局部 import 之后：
from .ai.session import SessionStore
from ..config import load_config as _load_cfg

_cfg = _load_cfg()
_store = SessionStore(
    ttl_hours=_cfg.session.ttl_hours,
    max_sessions=_cfg.session.max_sessions,
)

_continue = "--continue" in sys.argv or "-c" in sys.argv
_session_id_arg = None
for i, a in enumerate(sys.argv):
    if a == "--session" and i + 1 < len(sys.argv):
        _session_id_arg = sys.argv[i + 1]

# CTO 修正：上方直接解析 sys.argv 是错误实现。必须改为从 Typer 上下文读取参数值：
# _continue = ctx.obj.get("continue_session", False)
# _session_id_arg = ctx.obj.get("session_id", None)
# 理由：
# 1. sys.argv 解析绕过 Typer，`--session=a3f2`（等号格式）会解析失败。
# 2. 子命令路径（`socialhub session list`）会错误触发 session 加载逻辑。
# 3. `socialhub -c` 在非 AI 查询命令下（如 `socialhub skills list -c`）会产生歧义。
# 正确实现：在 main() 回调中已将 continue_session/session_id 存入 ctx.obj，
# 在 cli() 的 smart-mode 分支读取 ctx.obj 即可，无需二次解析 argv。
# 工程师必须在实现时替换此处的 sys.argv 解析逻辑。

current_session = None
conversation_history = []

if _continue or _session_id_arg:
    if _session_id_arg:
        current_session = _store.load(_session_id_arg)
    else:
        current_session = _store.load_latest()

    if current_session is None:
        console.print("[yellow]会话已过期或不存在。将开始新会话。[/yellow]")
        console.print("[dim]查看历史: socialhub session list[/dim]")
    elif _store.is_expired(current_session):
        console.print("[yellow]会话已过期（超过 24 小时）。请开始新会话。[/yellow]")
        console.print(f"[dim]查看历史: socialhub session show {current_session['session_id']}[/dim]")
        current_session = None
    else:
        conversation_history = _store.get_context_messages(current_session)

# 调用 AI 时传入历史
response = call_ai_api(query, conversation_history=conversation_history)

# 调用完成后保存到 session
if current_session is None:
    current_session = _store.new_session(query)
_store.append_message(current_session, "user", query)
_store.append_message(current_session, "assistant", response)

# Session 提示（text 模式才显示，AC-10）
fmt = "text"  # 从 ctx.obj 读取
if fmt == "text":
    sid = current_session["session_id"]
    console.print(f"\n[dim]会话 {sid} | 续接: socialhub -c \"...\" | 查看: socialhub session show {sid}[/dim]")
```

### 4.4 call_ai_api() 接收 conversation_history

```
改动文件: cli/ai/client.py
改动类型: 修改
改动行数估计: ~30 行
改动描述: call_ai_api() 增加 conversation_history 参数，在 messages 列表开头插入历史消息
```

**修改 `call_ai_api()` 函数签名**（第 36 行）：

```python
def call_ai_api(
    user_message: str,
    api_key: Optional[str] = None,
    max_retries: int = 3,
    show_thinking: bool = True,
    conversation_history: Optional[list[dict]] = None,  # 新增
) -> str:
```

**在构建 `messages` 列表时**（第 71 行 azure 分支和第 94 行 openai 分支），将历史消息插入到 system 和 user 消息之间：

```python
# 原来的 messages 列表（单轮）
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_message},
]

# 改为（多轮，插入历史）
history = conversation_history or []
messages = (
    [{"role": "system", "content": SYSTEM_PROMPT}]
    + history                                       # 历史轮次（已截断至最近 10 条）
    + [{"role": "user", "content": user_message}]
)
```

### 4.5 config.py 扩展（Session 配置）

```
改动文件: cli/config.py
改动类型: 修改
改动行数估计: ~10 行
改动描述: 新增 SessionConfig 类（ttl_hours=24, max_sessions=20），在 Config 根模型中引用
```

```python
class SessionConfig(BaseModel):
    ttl_hours: int = 24        # PRD §4.2 默认 24 小时
    max_sessions: int = 20     # PRD §4.2 最多保留 20 个 session

class Config(BaseModel):
    # ... 现有字段 ...
    session: SessionConfig = SessionConfig()
```

### 4.6 session 子命令

```
改动文件: cli/commands/session_cmd.py
改动类型: 新建
改动行数估计: ~80 行
改动描述: session list / show / clear 三个子命令（PRD AC-6/7/8）
```

在 `cli/main.py` 中注册：`app.add_typer(session_cmd.app, name="session", help="Session management")`

---

## 改进五：AI 决策可观测性

**PRD 来源**: 改进清单 §改进五，AC-1 ~ AC-10；接口规范 §4.3

### 5.1 ai_trace.jsonl 的 NDJSON schema

每条记录是单行 JSON，schema 严格按 PRD §4.3 定义（已完整定义，参见 PRD 第 602-634 行）。关键字段：

```
trace_id        - "tr_" + session_id[:4] + "_" + 递增序号
session_id      - 来自当前 SessionStore session（无 session 则空字符串）
timestamp       - UTC ISO 8601
tenant_id       - 来自 config.tenant_id
user_input      - PII 脱敏后的输入
ai_model        - "gpt-4o" 等（来自 ai_config 的 provider+deployment/model）
plan.steps_generated / steps_executed / steps_truncated
steps[]         - 每步的 command、status、duration_ms、output_lines
token_usage     - prompt_tokens / completion_tokens / total_tokens
total_duration_ms
outcome         - "success" | "partial" | "circuit_breaker" | "error"
```

### 5.2 PII 脱敏正则列表

```
改动文件: cli/ai/trace.py（新建，TraceWriter 类内部）
```

```python
_PII_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[PHONE]"),             # 中国手机号
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),  # 邮箱地址
    (re.compile(r"\d{17}[\dXx]"), "[ID_NUMBER]"),         # 中国身份证号（17位数字+校验位）
    (re.compile(r"\b\d{10,20}\b"), "[ORDER_ID]"),         # 订单号（10-20位纯数字串）
]

def _mask_pii(text: str) -> str:
    """Apply all PII masking patterns sequentially."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
```

**执行顺序说明**：身份证号模式（18位）必须在订单号模式（10-20位）之前运行，否则身份证号会先被 `[ORDER_ID]` 替换，导致模式失配。当前顺序已正确。

**CTO 修正**：订单号正则 `\b\d{10,20}\b` 存在严重误杀风险，会将普通客户 ID、ERP 系统编号、积分账户号等任意 10-20 位纯数字串全部替换为 `[ORDER_ID]`，使 trace 日志丧失诊断价值。修正方案：

1. **收紧订单号特征**：中国电商订单号通常以平台前缀开头，纯数字长度集中在 16-20 位，且罕见于正常自然语言描述的中段。将正则收紧为 `\b\d{16,20}\b`（从 10 改为 16）以大幅降低误杀率。
2. **增加上下文感知保护**：在 `_mask_pii()` 之前先用 PHONE/ID_NUMBER 模式消费掉已知 PII，订单号正则最后运行（当前顺序已正确，强制保持）。
3. **在 trace.py 注释中明确警告**：`_mask_pii()` 只能用于 TraceWriter 日志脱敏，**绝对不能**用于净化传给 AI 的用户输入（那是 sanitizer.py 的职责），工程师必须理解两条代码路径完全隔离。
4. **配置项**：新增 `ai.trace_order_id_min_digits: int = 16`，允许 IT 管理员根据实际订单号规则调整，默认值 16。

### 5.3 TraceWriter 类

```
改动文件: cli/ai/trace.py
改动类型: 新建
改动行数估计: ~130 行
改动描述: TraceWriter 类，写入 ai_trace.jsonl，PII 脱敏，文件权限 600，10MB 轮转
```

```python
"""TraceWriter — AI 决策可观测性日志。

文件位置：~/.socialhub/ai_trace.jsonl（权限 600）
文件管理：超过 10MB 轮转为 ai_trace.jsonl.1，最多保留 2 个文件
PII 脱敏：默认开启，通过 ai.trace_pii_masking=false 关闭
写入是静默操作：失败时仅在 --verbose 模式输出警告（PRD AC-8）
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


TRACE_FILE = Path.home() / ".socialhub" / "ai_trace.jsonl"
TRACE_BACKUP = Path.home() / ".socialhub" / "ai_trace.jsonl.1"
MAX_TRACE_SIZE = 10 * 1024 * 1024  # 10MB

_PII_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\d{17}[\dXx]"), "[ID_NUMBER]"),
    (re.compile(r"\b\d{10,20}\b"), "[ORDER_ID]"),
]


def _mask_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class TraceWriter:
    """Write AI execution traces to ai_trace.jsonl.

    Usage:
        writer = TraceWriter(pii_masking=True)
        trace_id = writer.begin(session_id="a3f2", user_input="...", ai_model="gpt-4o")
        writer.add_step(trace_id, step_index=1, command="sh analytics overview", ...)
        writer.end(trace_id, token_usage={...}, outcome="success")
    """

    def __init__(self, pii_masking: bool = True, verbose: bool = False):
        self.pii_masking = pii_masking
        self.verbose = verbose
        self._pending: dict[str, dict] = {}  # trace_id -> in-progress record

    def begin(
        self,
        session_id: str = "",
        user_input: str = "",
        ai_model: str = "",
        tenant_id: str = "",
    ) -> str:
        """Start a new trace record. Returns trace_id."""
        trace_id = "tr_" + uuid.uuid4().hex[:12]
        masked_input = _mask_pii(user_input) if self.pii_masking else user_input
        self._pending[trace_id] = {
            "trace_id": trace_id,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "user_input": masked_input,
            "ai_model": ai_model,
            "plan": {"steps_generated": 0, "steps_executed": 0, "steps_truncated": 0},
            "steps": [],
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "total_duration_ms": 0,
            "outcome": "unknown",
            "_start_ts": time.time(),
        }
        return trace_id

    def add_step(
        self,
        trace_id: str,
        step_index: int,
        command: str,
        status: str,
        duration_ms: int,
        output_lines: int = 0,
    ) -> None:
        if trace_id not in self._pending:
            return
        self._pending[trace_id]["steps"].append({
            "step_index": step_index,
            "command": command,
            "status": status,
            "duration_ms": duration_ms,
            "output_lines": output_lines,
        })
        self._pending[trace_id]["plan"]["steps_executed"] += 1

    def end(
        self,
        trace_id: str,
        token_usage: Optional[dict] = None,
        outcome: str = "success",
        steps_generated: int = 0,
        steps_truncated: int = 0,
    ) -> None:
        if trace_id not in self._pending:
            return
        record = self._pending.pop(trace_id)
        record["token_usage"] = token_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        record["outcome"] = outcome
        record["total_duration_ms"] = int((time.time() - record.pop("_start_ts")) * 1000)
        record["plan"]["steps_generated"] = steps_generated
        record["plan"]["steps_truncated"] = steps_truncated
        self._write(record)

    def _write(self, record: dict) -> None:
        """Silently write record to ai_trace.jsonl (PRD AC-8)."""
        try:
            self._rotate_if_needed()
            TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
            is_new = not TRACE_FILE.exists()
            with open(TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if is_new:
                os.chmod(TRACE_FILE, 0o600)  # PRD AC-4
        except Exception as e:
            if self.verbose:
                import sys
                print(f"[trace warning] Failed to write trace: {e}", file=sys.stderr)

    def _rotate_if_needed(self) -> None:
        """Rotate ai_trace.jsonl if it exceeds 10MB (PRD AC-9)."""
        if TRACE_FILE.exists() and TRACE_FILE.stat().st_size > MAX_TRACE_SIZE:
            if TRACE_BACKUP.exists():
                TRACE_BACKUP.unlink()
            TRACE_FILE.rename(TRACE_BACKUP)
```

**文件大小检查位置**：`_write()` → `_rotate_if_needed()` 在每次写入前调用，无额外后台线程，纯同步操作。

**CTO 修正（生产事故风险）**：`_write()` 中 `chmod 600` 的时机存在 TOCTOU（Time-Of-Check-Time-Of-Use）安全窗口。当前逻辑：文件创建（默认 umask 权限，可能是 644）→ 写入内容 → 再 chmod 600。在多用户共享服务器上，另一个同 UID 的进程可以在写入内容到 chmod 之间读取 PII 数据（即使 PII 已脱敏，trace 内容仍可能含租户 ID、查询摘要等敏感业务信息）。

修正方案：用低级 `os.open()` 在创建时直接指定权限：

```python
def _write(self, record: dict) -> None:
    """Silently write record to ai_trace.jsonl (PRD AC-8)."""
    try:
        self._rotate_if_needed()
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # 用 os.open 保证创建时即为 0o600，消除 TOCTOU 窗口
        fd = os.open(
            str(TRACE_FILE),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            mode=0o600,
        )
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as e:
        if self.verbose:
            import sys
            print(f"[trace warning] Failed to write trace: {e}", file=sys.stderr)
```

注意：`os.open` 的 `mode` 参数在文件已存在时不改变权限（仅在 `O_CREAT` 创建时生效），不影响已有文件的权限，行为与 PRD 要求完全一致。

### 5.4 client.py 中提取 token usage

```
改动文件: cli/ai/client.py
改动类型: 修改
改动行数估计: ~15 行
改动描述: 在解析 API 响应时提取 result["usage"] 并存入 result_holder，供调用方获取 token 消耗
```

**修改第 169-173 行 `result = response.json()` 之后**：

```python
result = response.json()
usage = result.get("usage", {})
result_holder["usage"] = {
    "prompt_tokens": usage.get("prompt_tokens", 0),
    "completion_tokens": usage.get("completion_tokens", 0),
    "total_tokens": usage.get("total_tokens", 0),
}
console.print(f"[dim]Completed in {elapsed_time:.1f}s[/dim]")
return result["choices"][0]["message"]["content"]
```

**调用方获取 token usage 的方式**：`call_ai_api()` 的返回值目前是 `str`，保持签名兼容。token usage 通过线程共享的 `result_holder` 字典传出。实现上，`call_ai_api()` 返回值增加第二个返回值：

```python
def call_ai_api(...) -> tuple[str, dict]:
    # 返回 (content, usage_dict)
    # usage_dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
```

所有现有调用方（`cli/main.py`）需同步更新为 `response, usage = call_ai_api(...)` 或 `response, _ = call_ai_api(...)`。

### 5.5 config.py 扩展（trace 配置）

```
改动文件: cli/config.py
改动类型: 修改
改动行数估计: ~5 行（AIConfig 扩展）
改动描述: 在 AIConfig 中新增 trace_enabled 和 trace_pii_masking 字段
```

```python
class AIConfig(BaseModel):
    # ... 现有字段 ...
    trace_enabled: bool = True       # PRD AC-1
    trace_pii_masking: bool = True   # PRD AC-2/3
```

### 5.6 trace 子命令

```
改动文件: cli/commands/trace_cmd.py
改动类型: 新建
改动行数估计: ~80 行
改动描述: trace list / show / stats 三个子命令（PRD AC-5/6/7），读取 ai_trace.jsonl 并格式化输出
```

在 `cli/main.py` 中注册：`app.add_typer(trace_cmd.app, name="trace", help="AI execution traces")`

---

## 改进六：企业代理/CA 证书

**PRD 来源**: 改进清单 §改进六，AC-1 ~ AC-8；接口规范相关条款

### 6.1 config.py 的 NetworkConfig 新增字段

```
改动文件: cli/config.py
改动类型: 修改
改动行数估计: ~20 行
改动描述: 新增 NetworkConfig 类，在 Config 根模型中引用
```

```python
class NetworkConfig(BaseModel):
    https_proxy: Optional[str] = None   # PRD AC-3
    http_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    ca_bundle: Optional[str] = None     # PRD AC-4，本地 CA 证书文件路径
    ssl_verify: bool = True             # PRD AC-5，false 时每次命令显示高危警告

class Config(BaseModel):
    # ... 现有字段 ...
    network: NetworkConfig = NetworkConfig()
```

### 6.2 httpx 代理/CA 注入方案

**优先级（PRD AC-7）**：

```
SOCIALHUB_HTTPS_PROXY（环境变量）
  > HTTPS_PROXY（系统标准环境变量）
    > config.json network.https_proxy
      > 无代理（直连）
```

**抽取为共享工厂函数**（在 `cli/api/base.py` 或 `cli/network.py` 新建，避免两处重复）：

```python
# cli/network.py（新建，~30 行）
"""统一 httpx 客户端构建工厂，注入代理和 CA 证书。"""
import os
from typing import Optional
import httpx
from .config import load_config


def build_httpx_client(timeout: int = 60) -> httpx.Client:
    """构建注入代理和 CA 配置的 httpx.Client。

    优先级：SOCIALHUB_HTTPS_PROXY > HTTPS_PROXY > config.json
    """
    cfg = load_config().network

    https_proxy = (
        os.getenv("SOCIALHUB_HTTPS_PROXY")
        or os.getenv("HTTPS_PROXY")
        or cfg.https_proxy
    )
    http_proxy = (
        os.getenv("SOCIALHUB_HTTP_PROXY")
        or os.getenv("HTTP_PROXY")
        or cfg.http_proxy
    )
    no_proxy = (
        os.getenv("SOCIALHUB_NO_PROXY")
        or os.getenv("NO_PROXY")
        or cfg.no_proxy
    )

    proxies = {}
    if https_proxy:
        proxies["https://"] = https_proxy
    if http_proxy:
        proxies["http://"] = http_proxy

    ca_bundle = (
        os.getenv("SOCIALHUB_CA_BUNDLE")
        or os.getenv("REQUESTS_CA_BUNDLE")
        or cfg.ca_bundle
    )

    ssl_ctx = ca_bundle if ca_bundle else cfg.ssl_verify

    return httpx.Client(
        proxies=proxies if proxies else None,
        verify=ssl_ctx,
        timeout=timeout,
    )

# CTO 修正（生产事故风险）：httpx >= 0.24 已将 `proxies=` 参数标记为废弃，
# 未来版本将移除。企业环境中 pip 升级 httpx 后所有 API 调用将产生
# DeprecationWarning，进一步版本更新可能直接报错，导致整个 CLI 不可用。
#
# 工程师实现时必须检查项目 httpx 版本约束：
# - 如果 requirements 锁定 httpx < 0.24：可暂时保留 proxies= 写法，但需在 CHANGELOG 标注
# - 如果未锁定或 >= 0.24：改用 mounts= 参数：
#
# proxies_map = {}
# if https_proxy:
#     proxies_map["https://"] = httpx.HTTPTransport(proxy=https_proxy)
# if http_proxy:
#     proxies_map["http://"] = httpx.HTTPTransport(proxy=http_proxy)
# return httpx.Client(mounts=proxies_map if proxies_map else None, verify=ssl_ctx, timeout=timeout)
#
# 建议：在 pyproject.toml 中固定 httpx>=0.24,<1.0 并使用 mounts= 写法，一劳永逸。
```

```
改动文件: cli/api/client.py（APIClient 的 httpx 初始化）
改动类型: 修改
改动行数估计: ~15 行
改动描述: 将现有 httpx.Client(...) 替换为 build_httpx_client() 调用
```

```
改动文件: cli/skills/store_client.py（SkillsStoreClient 的 httpx 初始化）
改动类型: 修改
改动行数估计: ~10 行
改动描述: 同上，替换为 build_httpx_client()；Store URL 硬编码不变（CLAUDE.md 红线）
```

**注意**：`store_client.py` 的 `STORE_BASE_URL` 硬编码常量**绝对不得**从代理配置或任何外部输入读取（CLAUDE.md 红线：Store URL 不可覆盖）。

### 6.3 SSL 错误信息增强

**捕获位置**：`cli/ai/client.py` 第 107 行 `except httpx.ConnectError:` 之后，以及 `cli/skills/store_client.py` 的同类异常捕获处。

```python
except httpx.ConnectError as e:
    err_str = str(e).lower()
    if "ssl" in err_str or "certificate" in err_str or "verify" in err_str:
        # Enhanced SSL error message (PRD AC-2)
        result_holder["error"] = (
            "Error: SSL 证书验证失败。\n"
            "如果您在企业网络中，请配置 CA 证书：\n"
            "  socialhub config set ca_bundle /path/to/ca.crt\n"
            "或设置环境变量：export REQUESTS_CA_BUNDLE=/path/to/ca.crt\n"
            "如需配置代理：export HTTPS_PROXY=http://proxy.corp.com:8080"
        )
    else:
        result_holder["connect_error"] = True
```

### 6.4 ssl_verify=false 高危警告横幅

**位置**：`cli/main.py` 的 `cli()` 入口函数（第 180 行），在任何命令执行之前：

```python
# ssl_verify 高危警告（PRD AC-5）
from .config import load_config as _cfg_loader
if not _cfg_loader().network.ssl_verify:
    console = Console(stderr=True)
    console.print(
        "[bold red]高危警告：SSL 证书验证已禁用（ssl_verify=false）。"
        "您的连接可能被中间人攻击。仅在受信任的测试环境中使用此设置。[/bold red]"
    )
```

### 6.5 verify-network 诊断命令

```
改动文件: cli/commands/config_cmd.py
改动类型: 修改
改动行数估计: ~50 行
改动描述: 新增 verify-network 子命令，测试 AI 服务、Skills Store、代理连通性
```

```python
@config_app.command("verify-network")
def verify_network():
    """诊断网络连通性（代理、CA、AI 服务、Skills Store）。"""
    from cli.network import build_httpx_client

    endpoints = [
        ("AI 服务 (Azure OpenAI)", cfg.ai.azure_endpoint + "/"),
        ("Skills Store", "https://skills-store-backend.onrender.com/health"),
    ]
    client = build_httpx_client(timeout=10)
    for name, url in endpoints:
        try:
            r = client.get(url)
            console.print(f"[green][OK][/green] {name}: HTTP {r.status_code}")
        except Exception as e:
            console.print(f"[red][FAIL][/red] {name}: {e}")
```

---

## 改进七：MCP 工具描述优化

**PRD 来源**: 改进清单 §改进七，AC-1 ~ AC-4

### 7.1 三段式描述模板

```
适用场景：[具体触发词和场景列表]
不适用场景：[至少 2 条负面边界]
参数说明：[必要参数的简要说明]
```

**字符数约束**：每个工具描述 ≤ 200 字符（PRD AC-3，Token 预算约束）。

### 7.2 需改动的工具列表（8 个 M365 暴露工具）

```
改动文件: mcp_server/server.py
改动类型: 修改
改动行数估计: ~120 行（8 个工具的 description 字段）
改动描述: 按三段式模板更新所有 8 个工具的 description，使用中文简洁描述
```

以 `get_customer_rfm` 为例（其余 7 个同理，具体工具名需对照 server.py Tool 定义列表）：

```python
Tool(
    name="get_customer_rfm",
    description=(
        "查询客户 RFM 分层分析（近期购买 R、购买频次 F、消费金额 M）。"
        "适用：VIP 分层、流失预警、高价值客户识别。"
        "不适用：新客户列表查询（用 get_new_customers）、物流状态查询（用 get_order_status）。"
        "参数：segment（RFM 分层名，可选）、period（分析周期，默认 30d）。"
    ),
    # ...
)
```

**所有 8 个工具的 description 改动须在 `server.py` 和 `mcp-tools.json` 中完全相同（逐字一致，PRD AC-2）。**

```
改动文件: build/m365-agent/mcp-tools.json
改动类型: 修改
改动行数估计: ~200 行（8 个工具的 description 字段）
改动描述: 与 server.py 保持逐字一致，同步更新
```

### 7.3 一致性检查机制（test_tool_schema_consistency.py 扩展）

```
改动文件: tests/test_tool_schema_consistency.py
改动类型: 修改
改动行数估计: ~20 行
改动描述: 新增 test_description_sync 测试，比较 server.py 和 mcp-tools.json 中同名工具的 description 字段是否逐字一致
```

```python
def test_description_sync():
    """AC-2: server.py 和 mcp-tools.json 的工具描述必须完全一致。"""
    import json
    from pathlib import Path

    mcp_tools_path = Path(__file__).parent.parent / "build" / "m365-agent" / "mcp-tools.json"
    mcp_tools = json.loads(mcp_tools_path.read_text(encoding="utf-8"))

    # Build dict: tool_name -> description from mcp-tools.json
    json_descriptions = {
        t["name"]: t["description"]
        for t in mcp_tools.get("tools", [])
    }

    # Import server tools (need to trigger tool list)
    # This requires the server module to expose a TOOLS list or similar
    from mcp_server.server import _get_tool_definitions  # 需要 server.py 暴露此函数
    server_tools = _get_tool_definitions()
    server_descriptions = {t.name: t.description for t in server_tools}

    for name, json_desc in json_descriptions.items():
        assert name in server_descriptions, f"Tool '{name}' in mcp-tools.json not found in server.py"
        assert server_descriptions[name] == json_desc, (
            f"Description mismatch for '{name}':\n"
            f"  server.py: {server_descriptions[name]!r}\n"
            f"  mcp-tools.json: {json_desc!r}"
        )
```

**为此需要在 `mcp_server/server.py` 中暴露一个 `_get_tool_definitions()` 函数**，返回 `list[Tool]`，供测试直接导入，不依赖运行中的 MCP Server 实例。

**CTO 修正**：`_get_tool_definitions()` 函数是测试能运行的前提，但改进七的改动清单中没有把它列为必交付文件，只在测试代码注释里隐含要求，工程师极易遗漏。修正：

1. **在文件改动总表（第 21 行）中补充一行**：`mcp_server/server.py` 的改动类型升级为"修改 + 新增函数"，明确列出 `_get_tool_definitions() -> list[Tool]` 是 §7.3 测试的强依赖。
2. **函数定义规范**：该函数必须直接返回静态 Tool 列表（不启动任何 async 上下文），示例：
   ```python
   def _get_tool_definitions() -> list[Tool]:
       """Return the list of Tool objects for schema consistency testing."""
       return list(_HANDLERS.keys())  # 视 server.py 实际结构调整
   ```
3. **测试隔离**：`test_description_sync` 不得依赖任何数据库连接或 MCP 运行时，只验证 Tool 对象的 `.description` 属性。工程师实现时必须确认 `_get_tool_definitions()` 在无环境变量的纯 import 下不抛出异常。

### 7.4 MCP 缓存 maxsize 修复

```
改动文件: mcp_server/server.py
改动类型: 修改
改动行数估计: ~15 行
改动描述: 将无界 _cache dict 替换为有界 TTLCache（使用 cachetools 或纯标准库实现 LRU）
```

**现状问题**：`_cache: dict[str, tuple[list, float]] = {}` 是无界 dict，可无限增长（project-status.md §G3 记录）。

**修复方案（纯标准库，不新增依赖）**：

```python
# 替换第 44 行的 _cache 定义：
import collections

class _BoundedTTLCache:
    """轻量有界 TTL 缓存（LRU 驱逐，最多 500 条）。"""
    MAX_SIZE = 500

    def __init__(self):
        self._store: collections.OrderedDict[str, tuple[list, float]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple | None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)  # LRU: 访问时移到末尾
                return self._store[key]
            return None

    def set(self, key: str, value: tuple) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            if len(self._store) > self.MAX_SIZE:
                self._store.popitem(last=False)  # 驱逐最旧条目（LRU）

    def __getitem__(self, key):
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def __setitem__(self, key, value):
        self.set(key, value)

    def __contains__(self, key):
        return self.get(key) is not None


_cache = _BoundedTTLCache()
```

**更新 `_get_cached_result()` 和 `_run_with_cache()` 中的访问方式**（需修改第 60-102 行的 `_cache.get(key)` 和 `_cache[key] = ...` 调用以适配新接口，接口设计已向前兼容）。

**注意**：`_BoundedTTLCache` 内部使用 `threading.Lock`，与现有 `_inflight_lock` 并存，不产生锁竞争（两个锁保护不同数据结构）。

---

## === 3 轮自我对抗迭代 ===

### Round 1：破坏者视角（并发/异常崩溃分析）

#### 问题 R1-1：TraceWriter 多进程并发写入 ai_trace.jsonl

**场景**：用户同时打开两个终端分别运行 `sh ...`，两个进程同时向 `ai_trace.jsonl` 追加写入。

**分析**：Python 的 `open(path, 'a')` 在 POSIX 系统上保证原子追加（O_APPEND 语义），但在 Windows 上不保证。每次写入是单行 JSON（无跨行结构），最坏情况下两行 JSON 可能交错，但由于 NDJSON 是逐行解析，损坏仅影响单行，不破坏整个文件。

**修正**：在 `TraceWriter._write()` 中使用 `os.O_APPEND | os.O_WRONLY | os.O_CREAT` 低级接口（Windows 同样安全），或接受当前单行追加的风险（PRD 的接受策略：`写入模式：追加，天然支持并发追加`）。当前设计已满足 PRD 要求，不需额外修正。

#### 问题 R1-2：SessionStore._update_index() 竞争条件

**场景**：两个并发 AI 调用同时调用 `_update_index()`，一个覆盖另一个的写入。

**分析**：CLI 进程是单线程（Typer 是同步框架），正常使用场景下不存在并发 session 写入。唯一风险是用户在脚本中并发启动多个 `sh` 进程。

**修正**：在 `_save_index()` 中使用 `fcntl.flock`（POSIX）或 `msvcrt.locking`（Windows）进行文件锁。但这会引入平台差异处理逻辑（20 行），且风险场景极低频。**决策**：接受当前设计，注释说明"并发场景下 index.json 可能有轻微数据丢失（Session 记录重复或缺失），但 session 数据文件（session_id.json）不受影响"。

#### 问题 R1-3：execute_plan() 挂钟超时与 subprocess.TimeoutExpired 的交互

**场景**：单步设置 `step_timeout=300s`，总挂钟也是 300s。第一步恰好执行了 299s（接近但未触发单步超时），第二步开始时挂钟已过 300s，触发挂钟中止。

**分析**：正确行为。挂钟是"计划总时间"的护栏，单步超时是"单个命令"的护栏，两者独立，无逻辑矛盾。

**修正**：在挂钟超时的提示语中说明"已完成 N 项分析"（当前方案已包含），用户可理解。无需代码修改。

#### 问题 R1-4：call_ai_api() 返回值从 str 改为 tuple 的破坏性变更

**场景**：`call_ai_api()` 增加 `usage` 返回值后，所有现有调用方（`cli/main.py`、`cli/ai/insights.py` 等）需同步修改。

**修正**：改为返回 `str`，同时通过一个可选的 `_usage_out` 列表参数（mutable container pattern）将 usage 传出，避免破坏所有调用方：

```python
def call_ai_api(
    user_message: str,
    ...,
    _usage_out: Optional[list] = None,  # 如果提供，append usage dict
) -> str:
    # ...
    if _usage_out is not None:
        _usage_out.append(usage)
    return content
```

**调用方**（需要 usage 时）：
```python
usage_holder = []
response = call_ai_api(query, _usage_out=usage_holder)
usage = usage_holder[0] if usage_holder else {}
```

此方案不破坏任何现有调用，完全向后兼容。

---

### Round 2：CLAUDE.md 守护者（逐条红线核查）

#### 检查 R2-1：shell=True 有没有引入？

扫描所有改动：
- `cli/ai/executor.py`：步骤上限和超时改动不触及 `subprocess.run()` 的 `shell=` 参数，保持 `shell=False`。
- `cli/skills/manager.py`：`install_dev_mode()` 中没有调用 `subprocess`，只用 `zipfile` 和 `yaml`。
- `cli/network.py`：纯 `httpx.Client` 构建，不使用 `subprocess`。
- `cli/commands/config_cmd.py`：`verify-network` 使用 `httpx.Client.get()`，不使用 `subprocess`。

**结论：无 shell=True 引入**。

#### 检查 R2-2：沙箱能被绕过吗？

`install_dev_mode()` 中**没有调用 `SandboxManager.activate()`**——但分析发现，沙箱的激活不在安装阶段，而在**执行阶段**（`cli/skills/loader.py`）。`install_dev_mode()` 只是解压和注册，沙箱在下次 `sh skills run` 执行 Skill 时由 `SandboxManager` 激活，与安装路径无关。

**修正**：在 `install_dev_mode()` 的注释中明确说明"沙箱在执行阶段由 loader.py 激活，安装阶段无需调用"，防止后续工程师误读。

#### 检查 R2-3：--dev-mode 会不会被误用为 --skip-verify？

**语义分析**：
- `--dev-mode`：意思是"本地开发模式安装"，暗示这是专门给开发者本地测试用的临时状态。
- `--skip-verify`：意思是"跳过验证"，语义上允许对任何来源（包括 Store）跳过验证，危险性远高。

**代码约束**：`install_dev_mode()` 开头的 `if str(local_path).startswith(("http://", "https://", "ftp://"))` 检查**强制要求本地路径**，从 URL 安装会被拒绝，即使传入 `--dev-mode` 也无法绕过到 Store 安装路径。

**结论**：`--dev-mode` 在语义和实现两个层面都无法被误用为 Store 安装的签名跳过。PRD §5.2 合规性确认通过。

#### 检查 R2-4：Store URL 有没有被可覆盖？

`cli/network.py` 的 `build_httpx_client()` 只注入代理和 CA，**不覆盖请求的目标 URL**。`store_client.py` 中的 `STORE_BASE_URL = "https://skills.socialhub.ai/api/v1"` 常量仍然是硬编码，`build_httpx_client()` 不修改它。

**结论**：Store URL 硬编码约束完整保持。

#### 检查 R2-5：MCP 工具处理器返回类型

改进七只修改 `description` 字段（字符串），不修改任何 `_handle_*` 函数的返回类型。

**结论**：所有处理器继续返回 `list[TextContent]`，约束保持。

#### 检查 R2-6：账户表严格隔离

改进一~七均不触及 Skills Store 后端（`skills-store/backend/`）的任何代码，开发者通知只通过后端已有的管理员 API 发送。

**结论**：账户表隔离约束完整保持。

---

### Round 3：新入职工程师视角（实现顺序与依赖关系检查）

#### 发现 R3-1：config.py 修改需要在其他改进之前完成

`cli/config.py` 被改进三（AIConfig 扩展）、改进四（SessionConfig）、改进五（trace 字段）、改进六（NetworkConfig）均依赖。如果分配给不同工程师并行开发，会产生合并冲突。

**修正**：将所有 `config.py` 改动合并为一个独立的首要任务（Day 1 上午），完成后其他改进才能开始依赖新配置字段。**建议实现顺序**见下节。

#### 发现 R3-2：call_ai_api() 签名变更影响多处

`call_ai_api()` 新增 `conversation_history` 和 `_usage_out` 参数，但由于都有默认值（`None`），所有现有调用方无需修改（Python 向后兼容）。`response = call_ai_api(query)` 在现有代码中仍然有效。

**结论**：无破坏性变更，可安全实施。

#### 发现 R3-3：main.py 三处独立改动（改进二、三、四）需合并

`cli/main.py` 同时被三项改进修改（output_format 参数、sanitize_user_input 调用、session 处理）。如果独立 PR，会有三次 main.py 冲突。

**修正**：`cli/main.py` 的所有改动在同一个 PR 中一次性完成，不拆分。

#### 发现 R3-4：trace_cmd 和 session_cmd 需要在 main.py 中注册

新建的 `cli/commands/session_cmd.py` 和 `cli/commands/trace_cmd.py` 需要在 `cli/main.py` 中 `app.add_typer(...)` 注册，才能被 CLI 发现。新入职工程师可能遗漏此步骤。

**修正**：在文件改动清单中明确标注"main.py 需追加两行 add_typer 注册"。

#### 建议实现顺序（最终修正版）

```
Day 1 上午（基础设施 — 单人，消除合并冲突根源）：
  1. cli/config.py — 所有新字段一次性完成（NetworkConfig/SessionConfig/AIConfig 扩展）
  2. cli/network.py — 新建（依赖 config.py）
  → 提交 PR，必须在 Day 1 上午合并，是所有后续工作的前提

Day 1 下午（P0 + 独立任务并行）：
  [工程师 A — 安全链]
  3. cli/ai/sanitizer.py — 新建（无依赖）
  4. cli/skills/security.py — 替换公钥（无代码依赖，运维配合生成密钥对）
  5. cli/skills/manager.py — install_dev_mode()（无新依赖）
  6. cli/commands/skills.py — --dev-mode 参数（依赖 manager.py）

  [工程师 B — 输出格式]
  7. cli/output/formatter.py — 新建（依赖 config.py）
  8. cli/commands/analytics.py — output_format 注入（依赖 formatter.py）
  9. cli/commands/customers.py — output_format 注入

Day 2 上午（P0 尾部 + P1 提前启动）：
  [工程师 A — P0 尾部]
  10. cli/ai/executor.py — 三层护栏（依赖 sanitizer.py）
  11. cli/api/client.py — build_httpx_client 注入（依赖 network.py）
  12. cli/skills/store_client.py — build_httpx_client 注入
  13. cli/commands/config_cmd.py — verify-network 命令

  [工程师 B — P1 提前启动，不依赖 main.py]
  14. cli/ai/session.py — SessionStore（只依赖 config.py，可提前开始）
  15. cli/ai/trace.py — TraceWriter（只依赖 config.py，可提前开始）

Day 2 下午（main.py 一次性合并 + 子命令完成）：
  [工程师 A — 唯一的 main.py 操作者]
  16. cli/main.py — 一次性完成：output_format + sanitize + session -c + SSL 警告 + 注册 session/trace 子命令
  （此步骤串行，避免多人冲突；工程师 B 同期完成 P1 子命令）

  [工程师 B — 同期进行]
  17. cli/commands/session_cmd.py — session list/show/clear（依赖 session.py）
  18. cli/commands/trace_cmd.py — trace list/show/stats（依赖 trace.py）
  19. cli/ai/client.py — conversation_history + _usage_out 参数

Day 3（MCP 改进 — 任意工程师，完全独立）：
  20. mcp_server/server.py — _BoundedTTLCache 修复（独立任务，优先于描述改动，便于隔离调试）
  21. mcp_server/server.py — 工具描述更新 + _get_tool_definitions() 函数（独立 commit）
  22. build/m365-agent/mcp-tools.json — 与 server.py 同步（逐字核对，手工执行）
  23. tests/test_tool_schema_consistency.py — description_sync 测试

关键并行化收益：
  - 工程师 B 的 session.py/trace.py 从 Day 3 上午提前至 Day 2 上午，节省半天
  - MCP 缓存修复与描述优化拆分为独立 commit，调试更清晰
  - main.py 改动收归单人，消除三次合并冲突
```

**CTO 修正（Round 3 — 开发效率）**：

1. **main.py 瓶颈已消除**：工程师 B 在 Day 2 上午可以直接开始 session.py/trace.py（纯文件级别，不依赖 main.py），不必等 Day 2 下午的 main.py 合并。原方案让工程师 B 在 Day 2 上午空等，是浪费。

2. **MCP 任务拆分**：`_BoundedTTLCache` 是 MCP 稳定性修复（独立 bug fix），工具描述更新是纯文本改动，两者混在一个 commit 是不良实践。拆分后，如果 cache 实现有 bug（如 ThreadLock 争用），可以单独回滚不影响描述更新。

3. **可以砍掉的设计**：`_BoundedTTLCache` 的 MAX_SIZE=500 是拍脑袋的数字。实际 MCP cache key 格式为 `{tenant_id}:{tool_name}:{params_hash}`，生产环境中租户数 × 工具数 × 参数组合量极少超过 100。500 意味着 cache 永远不会驱逐，LRU 逻辑永远不运行，等于纯粹的代码死路径。建议 MAX_SIZE 调整为 200，或将 MAX_SIZE 作为 MCP Server 启动参数（`--cache-maxsize`）使其可观测。

---

## 迭代记录

### Round 1 修正项

| ID | 问题 | 修正措施 | 影响范围 |
|----|------|---------|---------|
| R1-1 | TraceWriter 并发写入 | 接受 POSIX 原子追加语义，与 PRD 规范对齐 | 无代码修改 |
| R1-2 | SessionStore index 竞争 | 接受轻微风险（单进程正常使用场景无并发），注释说明 | 文档注释 |
| R1-3 | 挂钟超时逻辑 | 确认两种超时独立，无逻辑冲突 | 无代码修改 |
| R1-4 | call_ai_api 返回类型变更 | 改用 _usage_out 可选 mutable 参数，保持向后兼容 | client.py 签名变更 |

### Round 2 修正项

| ID | 问题 | 修正措施 | 影响范围 |
|----|------|---------|---------|
| R2-1 | shell=True 检查 | 全部改动扫描确认无引入 | 无代码修改 |
| R2-2 | 沙箱绕过检查 | 确认沙箱在执行阶段激活，install_dev_mode 不需要调用；追加代码注释 | manager.py 注释 |
| R2-3 | --dev-mode 语义 | 确认本地路径限制阻止 URL 绕过；语义与 --skip-verify 区别清晰 | 无代码修改 |
| R2-4 | Store URL 覆盖 | 确认 build_httpx_client 不修改目标 URL，硬编码保持 | 无代码修改 |
| R2-5 | MCP 处理器返回类型 | 确认描述改动不触及返回类型 | 无代码修改 |
| R2-6 | 账户表隔离 | 确认无 backend 代码改动 | 无代码修改 |

### Round 3 修正项

| ID | 问题 | 修正措施 | 影响范围 |
|----|------|---------|---------|
| R3-1 | config.py 并行冲突 | 提升为 Day 1 首要任务，单人完成 | 实现顺序调整 |
| R3-2 | call_ai_api 兼容性 | 确认默认参数值保持向后兼容 | 无代码修改 |
| R3-3 | main.py 三处冲突 | 所有 main.py 改动合并为 Day 2 下午单次 PR | 实现顺序调整 |
| R3-4 | 子命令注册遗漏 | 在改动清单中明确标注 add_typer 步骤 | 文档说明 |

---

*生成者：资深架构师 — 2026-03-31*
*上游文档：05-prd.md v1.0*
*已完成 3 轮自我对抗迭代（破坏者 / CLAUDE.md 守护者 / 新入职工程师）*
