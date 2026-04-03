"""TraceLogger — AI 决策可观测性日志。

文件位置：{trace_dir}/ai_trace.jsonl（权限 600，TOCTOU 安全写入）
文件管理：超过 max_file_size_mb 时轮转为 ai_trace.jsonl.1
PII 脱敏：默认开启，通过 TraceConfig.pii_masking=False 关闭

写入是静默操作：任何 IO 异常仅静默忽略，不影响主执行流程。

SECURITY WARNING:
    _mask_pii() 只用于 TraceLogger 日志脱敏，绝对不能用于净化传给 AI 的用户输入
    （净化输入是 cli/ai/sanitizer.py 的职责）。两条代码路径完全隔离，不可混用。
"""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cli.config import TraceConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PII 脱敏模式（按顺序执行，顺序不可更改）
# ---------------------------------------------------------------------------
# 1. 身份证必须先于订单号运行，否则 18 位身份证会被订单号正则预先消费掉
# 2. 手机号、邮箱在身份证之后但订单号之前，避免部分重叠匹配
# ---------------------------------------------------------------------------


def _build_pii_patterns(order_id_min_digits: int) -> list[tuple[re.Pattern, str]]:
    """构建 PII 正则列表，订单号最小位数由配置决定。"""
    return [
        # 中国大陆身份证（17 位数字 + 1 位数字或 X）
        (re.compile(r"\b\d{17}[\dX]\b", re.IGNORECASE), "[ID_MASKED]"),
        # 中国大陆手机号（1 开头，第二位 3-9，共 11 位）
        (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE_MASKED]"),
        # 电子邮箱
        (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL_MASKED]"),
        # 订单号（纯数字长串，最小位数可配置，默认 16）
        (re.compile(r"\b\d{" + str(order_id_min_digits) + r",}\b"), "[ORDER_ID]"),
    ]


def _mask_pii(text: str, patterns: list[tuple[re.Pattern, str]]) -> str:
    """按顺序应用所有 PII 脱敏规则。仅供 TraceLogger 内部使用。"""
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# TraceLogger
# ---------------------------------------------------------------------------


class TraceLogger:
    """记录 AI 执行计划的可观测性日志，写入 NDJSON 格式的 ai_trace.jsonl。

    每个公共方法对应计划生命周期中的一个事件：
        log_plan_start  — 计划开始，返回 trace_id（UUID）
        log_step        — 单步执行结果
        log_plan_end    — 计划完成，含 token 消耗

    当 config.enabled=False 时，所有方法立即返回，不写文件。
    当 config.pii_masking=True 时，user_input 在写入前经过 PII 脱敏。

    TOCTOU 安全写入：使用 os.open(O_CREAT|O_WRONLY|O_APPEND, 0o600) 保证
    文件从创建时起即为 600 权限，消除 open()+chmod() 的时间窗口。
    """

    TRACE_FILENAME = "ai_trace.jsonl"

    def __init__(self, config: TraceConfig) -> None:
        self._config = config
        self._trace_path = Path(config.trace_dir) / self.TRACE_FILENAME
        self._backup_count = config.backup_count
        self._max_bytes = config.max_file_size_mb * 1024 * 1024
        self._pii_patterns: list[tuple[re.Pattern, str]] | None = (
            _build_pii_patterns(config.order_id_min_digits)
            if config.pii_masking
            else None
        )
        self._lock = threading.Lock()  # serializes rotate + write to prevent rename race
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def log_plan_start(self, session_id: str, user_input: str, model: str) -> str:
        """记录计划开始，返回 trace_id（UUID hex 字符串）。

        如果 config.enabled=False，仍返回有效的 trace_id，但不写文件。
        这样调用方无需判断 None，可以将 trace_id 无条件传给后续方法。
        """
        trace_id = uuid.uuid4().hex

        if not self._config.enabled:
            return trace_id

        masked_input = self._apply_pii(user_input)
        event = {
            "ts": _utcnow(),
            "type": "plan_start",
            "trace_id": trace_id,
            "session_id": session_id,
            "user_input": masked_input,
            "model": model,
        }
        self._write(event)
        return trace_id

    def log_step(
        self,
        trace_id: str,
        step_num: int,
        command: str,
        success: bool,
        duration_ms: int,
        output_chars: int,
        error_msg: str = "",
    ) -> None:
        """记录单步执行结果。enabled=False 时静默忽略。"""
        if not self._config.enabled:
            return

        event: dict = {
            "ts": _utcnow(),
            "type": "step",
            "trace_id": trace_id,
            "step": step_num,
            "command": command,
            "success": success,
            "duration_ms": duration_ms,
            "output_chars": output_chars,
        }
        if not success and error_msg:
            event["error_msg"] = error_msg[:500]  # cap at 500 chars to avoid huge logs
        self._write(event)

    def log_memory_write(
        self,
        memory_type: str,
        file_path: str,
        content_hash: str,
        pii_masked: bool,
        session_id: str = "",
        trace_id: str = "",
        skipped: bool = False,
        skip_reason: str = "",
    ) -> None:
        """Record a memory write (or skip) event for audit purposes.

        Args:
            memory_type: "insight" | "summary" | "preference"
            file_path:   Relative path within ~/.socialhub/memory/
            content_hash: SHA-256 hex digest of the written content (not the content itself)
            pii_masked:  True if the content went through PII masking before write
            session_id:  Source session ID
            trace_id:    Source trace ID (links back to plan_start event)
            skipped:     True when write was intentionally skipped (e.g. extractor timeout)
            skip_reason: Human-readable reason when skipped=True
        """
        if not self._config.enabled:
            return

        event: dict = {
            "ts": _utcnow(),
            "type": "memory_write",
            "memory_type": memory_type,
            "file_path": file_path,
            "content_hash": content_hash,
            "pii_masked": pii_masked,
            "skipped": skipped,
        }
        if session_id:
            event["session_id"] = session_id
        if trace_id:
            event["trace_id"] = trace_id
        if skip_reason:
            event["skip_reason"] = skip_reason
        self._write(event)

    def log_memory_injection(
        self,
        session_id: str,
        trace_id: str,
        injected_layers: list[str],
        token_count: int,
        insight_ids: list[str],
        summary_ids: list[str],
    ) -> None:
        """Record which memory items were injected into a specific SYSTEM_PROMPT build.

        This enables "which memory caused this AI response?" audit queries.

        Args:
            session_id:     Current session ID
            trace_id:       Current trace ID
            injected_layers: e.g. ["L4_profile", "L4_context", "L3_insights", "L2_summaries"]
            token_count:    Total tokens consumed by injected memory
            insight_ids:    IDs of injected L3 insights
            summary_ids:    Session IDs of injected L2 summaries
        """
        if not self._config.enabled:
            return

        event: dict = {
            "ts": _utcnow(),
            "type": "memory_injection",
            "session_id": session_id,
            "trace_id": trace_id,
            "injected_layers": injected_layers,
            "token_count": token_count,
            "insight_ids": insight_ids,
            "summary_ids": summary_ids,
        }
        self._write(event)

    def log_heartbeat_execution(
        self,
        task_id: str,
        task_name: str,
        success: bool,
        duration_ms: int,
        error_msg: str = "",
    ) -> None:
        """Record a heartbeat task execution event."""
        if not self._config.enabled:
            return
        event: dict = {
            "ts": _utcnow(),
            "type": "heartbeat_execution",
            "task_id": task_id,
            "task_name": task_name,
            "success": success,
            "duration_ms": duration_ms,
        }
        if not success and error_msg:
            event["error_msg"] = error_msg[:500]
        self._write(event)

    def log_plan_end(
        self,
        trace_id: str,
        total_steps: int,
        succeeded: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """记录计划完成，含 token 消耗。enabled=False 时静默忽略。"""
        if not self._config.enabled:
            return

        event = {
            "ts": _utcnow(),
            "type": "plan_end",
            "trace_id": trace_id,
            "total": total_steps,
            "succeeded": succeeded,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        self._write(event)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _apply_pii(self, text: str) -> str:
        """如果 pii_masking 开启则脱敏，否则原样返回。"""
        if self._pii_patterns is None:
            return text
        return _mask_pii(text, self._pii_patterns)

    def _write(self, event: dict) -> None:
        """TOCTOU 安全写入单条 NDJSON 事件到 ai_trace.jsonl。

        写入步骤：
          1. 确保 trace_dir 存在（parents=True，exist_ok=True）
          2. 检查是否需要轮转
          3. 用 os.open(O_CREAT|O_WRONLY|O_APPEND, 0o600) 追加写入
             — 文件从创建起即为 0o600，消除 chmod TOCTOU 窗口
             — 已存在的文件权限不被 mode 参数修改（仅 O_CREAT 时生效）

        任何异常静默忽略（PRD AC-8）。
        """
        try:
            with self._lock:
                self._rotate_if_needed()
                line = json.dumps(event, ensure_ascii=False) + "\n"
                fd = os.open(
                    str(self._trace_path),
                    os.O_CREAT | os.O_WRONLY | os.O_APPEND,
                    0o600,
                )
                try:
                    os.write(fd, line.encode("utf-8"))
                finally:
                    os.close(fd)
        except Exception as exc:
            # 写入失败静默忽略，不影响主执行流程（PRD AC-8）
            logger.debug("Trace write failed (non-fatal): %s", exc)

    def _rotate_if_needed(self) -> None:
        """文件超出 max_file_size_mb 时轮转，保留最多 backup_count 个备份。

        轮转逻辑：.N-1 → .N, ..., .1 → .2, current → .1。
        轮转后 _write() 会用 O_CREAT 创建新的 ai_trace.jsonl（权限 600）。
        """
        try:
            if not (self._trace_path.exists() and self._trace_path.stat().st_size >= self._max_bytes):
                return
            base = self._trace_path
            # Shift existing backups: .{n-1} → .{n}, dropping any beyond backup_count
            for i in range(self._backup_count - 1, 0, -1):
                src = base.with_name(base.name + f".{i}")
                dst = base.with_name(base.name + f".{i + 1}")
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
            # Current file → .1
            dst1 = base.with_name(base.name + ".1")
            if dst1.exists():
                dst1.unlink()
            self._trace_path.rename(dst1)
        except Exception as exc:
            logger.debug("Trace rotate failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（秒精度，不含微秒）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# 模块级 tracer 缓存（供 main.py / heartbeat.py 共享使用）
# ---------------------------------------------------------------------------

_global_tracer: "TraceLogger | None" = None
_global_tracer_lock = threading.Lock()


def get_tracer() -> "TraceLogger":
    """Return the process-level TraceLogger singleton.

    Creates it on first call using the current config.
    Callers that need a fresh tracer (e.g., after config change) should
    use TraceLogger(load_config().trace) directly.
    """
    global _global_tracer
    if _global_tracer is not None:
        return _global_tracer
    with _global_tracer_lock:
        if _global_tracer is None:
            from cli.config import load_config
            _global_tracer = TraceLogger(load_config().trace)
    return _global_tracer
