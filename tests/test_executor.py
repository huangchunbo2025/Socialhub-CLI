"""Tests for cli.ai.executor — ToolCircuitBreaker + execute_plan guardrails."""

import time
from unittest.mock import MagicMock, patch

import pytest

from cli.ai.executor import (
    MAX_PLAN_STEPS,
    PLAN_WALL_CLOCK,
    ToolCircuitBreaker,
    execute_command,
    execute_plan,
)


# ---------------------------------------------------------------------------
# ToolCircuitBreaker
# ---------------------------------------------------------------------------


class TestToolCircuitBreaker:
    def test_allow_initially_open(self):
        breaker = ToolCircuitBreaker()
        assert breaker.allow("sh analytics overview") is True

    def test_key_uses_first_two_tokens(self):
        breaker = ToolCircuitBreaker()
        # Record failures for "sh analytics"
        for _ in range(3):
            breaker.record_result("sh analytics overview --limit 10", success=False)
        # Both commands share the same key "sh analytics"
        assert breaker.allow("sh analytics customers") is False

    def test_single_token_command(self):
        breaker = ToolCircuitBreaker()
        for _ in range(3):
            breaker.record_result("sh", success=False)
        assert breaker.allow("sh") is False

    def test_open_after_three_failures(self):
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD):
            breaker.record_result("sh analytics overview", success=False)
        assert breaker.allow("sh analytics overview") is False

    def test_not_open_after_two_failures(self):
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD - 1):
            breaker.record_result("sh analytics overview", success=False)
        assert breaker.allow("sh analytics overview") is True

    def test_reset_on_success(self):
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD - 1):
            breaker.record_result("sh analytics overview", success=False)
        breaker.record_result("sh analytics overview", success=True)
        assert breaker.allow("sh analytics overview") is True
        entry = breaker._state.get("sh analytics")
        assert entry is None or entry.failures == 0

    def test_half_open_after_cooldown(self):
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD):
            breaker.record_result("sh analytics overview", success=False)
        assert breaker.allow("sh analytics overview") is False

        # Advance time past cooldown
        with patch("cli.ai.executor.time") as mock_time:
            mock_time.time.return_value = (
                time.time() + ToolCircuitBreaker._COOLDOWN_SECONDS + 1
            )
            assert breaker.allow("sh analytics overview") is True

    def test_empty_command_key(self):
        breaker = ToolCircuitBreaker()
        # Empty command should use "unknown" key without crashing
        assert breaker.allow("") is True
        breaker.record_result("", success=False)
        assert "unknown" in breaker._state

    def test_different_prefixes_independent(self):
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD):
            breaker.record_result("sh analytics overview", success=False)
        # Different prefix should still be allowed
        assert breaker.allow("sh customers list") is True

    def test_half_open_failed_probe_reopens_circuit(self):
        """After cooldown, a failed probe increments failures and reopens the circuit."""
        breaker = ToolCircuitBreaker()
        for _ in range(ToolCircuitBreaker._FAILURE_THRESHOLD):
            breaker.record_result("sh analytics overview", success=False)
        assert breaker.allow("sh analytics overview") is False

        # Advance time past cooldown — half-open state, allow() returns True
        future_time = time.time() + ToolCircuitBreaker._COOLDOWN_SECONDS + 1
        with patch("cli.ai.executor.time") as mock_time:
            mock_time.time.return_value = future_time
            assert breaker.allow("sh analytics overview") is True

        # Probe call fails — breaker should re-open
        breaker.record_result("sh analytics overview", success=False)

        # Should be open again (still within a new cooldown window)
        key = "sh analytics"
        assert breaker._state[key].failures >= ToolCircuitBreaker._FAILURE_THRESHOLD


# ---------------------------------------------------------------------------
# execute_plan — MAX_PLAN_STEPS guard
# ---------------------------------------------------------------------------


class TestExecutePlanGuards:
    def _make_steps(self, n: int) -> list[dict]:
        return [
            {"number": i + 1, "description": f"Step {i + 1}", "command": f"sh analytics overview --step {i}"}
            for i in range(n)
        ]

    def test_exact_max_steps_allowed(self, capsys):
        """A plan with exactly MAX_PLAN_STEPS steps should execute (not be refused)."""
        steps = self._make_steps(MAX_PLAN_STEPS)
        with patch("cli.ai.executor.execute_command", return_value=(True, "ok")):
            execute_plan(steps)
        # No "exceeds" error in output
        captured = capsys.readouterr()
        assert "exceeds" not in captured.out.lower()

    def test_over_max_steps_refused(self, capsys):
        """A plan with MAX_PLAN_STEPS + 1 steps must be refused immediately."""
        steps = self._make_steps(MAX_PLAN_STEPS + 1)
        called = []
        with patch("cli.ai.executor.execute_command", side_effect=lambda c: called.append(c) or (True, "ok")):
            execute_plan(steps)
        assert called == [], "No commands should execute when plan exceeds MAX_PLAN_STEPS"
        captured = capsys.readouterr()
        assert str(MAX_PLAN_STEPS) in captured.out

    def test_wall_clock_abort(self):
        """Wall-clock budget exceeded mid-plan should stop remaining steps."""
        steps = self._make_steps(5)
        execution_count = []

        def slow_execute(cmd):
            execution_count.append(cmd)
            return True, "ok"

        # Patch time.time so budget is exceeded after the first step
        call_count = [0]
        real_time = time.time()

        def fake_time():
            call_count[0] += 1
            # First call: plan_start (return normal time)
            # After 2nd call: exceed budget
            if call_count[0] <= 2:
                return real_time
            return real_time + PLAN_WALL_CLOCK + 1

        with patch("cli.ai.executor.execute_command", side_effect=slow_execute):
            with patch("cli.ai.executor.time") as mock_time:
                mock_time.time.side_effect = fake_time
                execute_plan(steps)

        # With budget exceeded quickly, fewer than 5 steps should run
        assert len(execution_count) < 5

    def test_circuit_breaker_skips_step(self, capsys):
        """A step whose circuit is open should be skipped (recorded as failed)."""
        steps = self._make_steps(4)
        # Make the first 3 steps fail to trip the breaker
        fail_count = [0]

        def failing_execute(cmd):
            fail_count[0] += 1
            if fail_count[0] <= 3:
                return False, "error"
            return True, "ok"

        # Patch typer.confirm and simulate TTY (isatty check in executor) to allow continuation
        with patch("cli.ai.executor.typer.confirm", return_value=True):
            with patch("cli.ai.executor.execute_command", side_effect=failing_execute):
                with patch("sys.stdin") as mock_stdin:
                    mock_stdin.isatty.return_value = True
                    execute_plan(steps)

        # All steps should have been attempted (3 fail + 1 succeed or skip)
        assert fail_count[0] >= 3

    def test_empty_steps_no_execution(self, capsys):
        """execute_plan([]) must output a warning and execute nothing."""
        called = []
        with patch("cli.ai.executor.execute_command", side_effect=lambda c: called.append(c) or (True, "ok")):
            execute_plan([])
        assert called == []
        captured = capsys.readouterr()
        assert "no steps" in captured.out.lower()

    def test_confirm_wait_excluded_from_wall_clock(self, capsys):
        """Time spent in typer.confirm() must not count against the wall-clock budget.

        Scenario: Step 1 fails, user is prompted.  The clock advances past
        PLAN_WALL_CLOCK while they decide.  After saying 'y' the _confirm_wait_s
        accumulator should cancel out that elapsed time so that Step 2 still runs.

        time.time() call order in execute_plan for a 2-step plan (step 1 fails):
          1  plan_start
          2  budget-check (step 1)
          3  step_start   (step 1)
          4  log_step     (step 1)
          5  _confirm_t   (start timing confirm dialog)
          6  _confirm_wait_s update (end timing confirm dialog)
          7  budget-check (step 2)  ← must NOT exceed budget
          8  step_start   (step 2)
          9  log_step     (step 2)
        """
        steps = self._make_steps(2)
        executed = []

        def _fake_execute(cmd):
            executed.append(cmd)
            return (False, "error") if len(executed) == 1 else (True, "ok")

        real_time = time.time()
        call_count = [0]

        def _fake_time():
            call_count[0] += 1
            # Calls 1-5: normal time (budget not yet exceeded)
            if call_count[0] <= 5:
                return real_time
            # Call 6+: clock has advanced past PLAN_WALL_CLOCK (user was slow to respond)
            return real_time + PLAN_WALL_CLOCK + 10

        # confirm returns True (user says "y")
        with patch("cli.ai.executor.execute_command", side_effect=_fake_execute):
            with patch("cli.ai.executor.typer.confirm", return_value=True):
                with patch("sys.stdin") as mock_stdin:
                    mock_stdin.isatty.return_value = True
                    with patch("cli.ai.executor.time") as mock_time:
                        mock_time.time.side_effect = _fake_time
                        execute_plan(steps)

        # Both steps should execute — confirm-wait offset prevents false budget abort
        assert len(executed) == 2, f"Expected 2 steps executed, got {len(executed)}"
        captured = capsys.readouterr()
        assert "wall-clock budget" not in captured.out

    def test_non_interactive_aborts_on_first_failure(self, capsys):
        """In non-TTY mode execute_plan must abort after the first failed step.

        When sys.stdin.isatty() returns False, the plan runner must not prompt the
        user and must return immediately after the first failure rather than
        continuing or waiting for input.
        """
        steps = self._make_steps(4)
        executed = []

        def _fake_execute(cmd):
            executed.append(cmd)
            return False, "error"

        with patch("cli.ai.executor.execute_command", side_effect=_fake_execute):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                execute_plan(steps)

        # Only the first step should be executed; the rest are aborted.
        assert len(executed) == 1
        captured = capsys.readouterr()
        assert "non-interactive" in captured.out.lower() or "aborting" in captured.out.lower()


# ---------------------------------------------------------------------------
# TraceLogger integration
# ---------------------------------------------------------------------------


class TestExecutePlanTracing:
    """Verify TraceLogger wiring in execute_plan."""

    def _make_steps(self, n: int) -> list[dict]:
        return [
            {"number": i + 1, "description": f"Step {i + 1}", "command": f"sh analytics overview --step {i}"}
            for i in range(n)
        ]

    def _mock_config(self, mock_cfg, provider="azure"):
        mock_cfg.return_value.trace = MagicMock()
        mock_cfg.return_value.ai.provider = provider
        mock_cfg.return_value.ai.azure_deployment = "gpt-4o"
        mock_cfg.return_value.ai.openai_model = "gpt-3.5-turbo"

    def test_tracer_receives_session_id_and_usage(self):
        """session_id and token counts are forwarded to log_plan_start / log_plan_end."""
        steps = self._make_steps(1)
        mock_tracer = MagicMock()
        mock_tracer.log_plan_start.return_value = "trace-abc"

        with patch("cli.ai.executor._get_tracer", return_value=mock_tracer):
            with patch("cli.ai.executor.load_config") as mock_cfg:
                self._mock_config(mock_cfg)
                with patch("cli.ai.executor.execute_command", return_value=(True, "ok")):
                    execute_plan(
                        steps,
                        original_query="query text",
                        session_id="sess-001",
                        prompt_tokens=10,
                        completion_tokens=5,
                    )

        mock_tracer.log_plan_start.assert_called_once_with(
            session_id="sess-001",
            user_input="query text",
            model="gpt-4o",
        )
        end_args = mock_tracer.log_plan_end.call_args[0]
        assert end_args[0] == "trace-abc"  # trace_id passed through
        assert end_args[3] == 10           # prompt_tokens
        assert end_args[4] == 5            # completion_tokens

    def test_tracer_log_plan_end_called_on_cancel(self):
        """log_plan_end is invoked even when the user cancels mid-plan."""
        steps = self._make_steps(2)
        mock_tracer = MagicMock()
        mock_tracer.log_plan_start.return_value = "trace-cancel"

        with patch("cli.ai.executor._get_tracer", return_value=mock_tracer):
            with patch("cli.ai.executor.load_config") as mock_cfg:
                self._mock_config(mock_cfg, provider="openai")
                with patch("cli.ai.executor.execute_command", return_value=(False, "fail")):
                    with patch("cli.ai.executor.typer.confirm", return_value=False):
                        execute_plan(steps)

        mock_tracer.log_plan_end.assert_called_once()

    def test_tracer_log_step_called_per_step(self):
        """log_step is invoked once per executed step."""
        steps = self._make_steps(3)
        mock_tracer = MagicMock()
        mock_tracer.log_plan_start.return_value = "trace-steps"

        with patch("cli.ai.executor._get_tracer", return_value=mock_tracer):
            with patch("cli.ai.executor.load_config") as mock_cfg:
                self._mock_config(mock_cfg)
                with patch("cli.ai.executor.execute_command", return_value=(True, "output")):
                    execute_plan(steps)

        assert mock_tracer.log_step.call_count == 3

    def test_malformed_step_missing_command_key_does_not_crash(self, capsys):
        """A step dict without 'command' key must not surface an unhandled KeyError.

        This test reveals a current defect (R8.4): the report_step_idx scan at the
        top of execute_plan accesses step["command"] unconditionally, so a malformed
        AI-generated step raises KeyError instead of a graceful error message.
        """
        steps = [{"number": 1, "description": "no command key here"}]
        mock_tracer = MagicMock()
        mock_tracer.log_plan_start.return_value = "trace-x"

        with patch("cli.ai.executor._get_tracer", return_value=mock_tracer):
            with patch("cli.ai.executor.load_config") as mock_cfg:
                self._mock_config(mock_cfg)
                with patch("cli.ai.executor.execute_command", return_value=(True, "ok")):
                    execute_plan(steps)  # must not raise KeyError

        captured = capsys.readouterr()
        assert "traceback" not in captured.out.lower()


# ---------------------------------------------------------------------------
# execute_command — security boundary tests
# ---------------------------------------------------------------------------


class TestExecuteCommand:
    def test_non_sh_prefix_rejected(self):
        ok, msg = execute_command("python -c 'import os'")
        assert not ok
        assert "sh" in msg.lower() or "allowed" in msg.lower()

    def test_empty_command_rejected(self):
        ok, msg = execute_command("")
        assert not ok

    @pytest.mark.parametrize("dangerous", [";", "&&", "||", "|", "`", "$", ">", "<", "\n", "\r"])
    def test_dangerous_chars_blocked(self, dangerous):
        ok, msg = execute_command(f"sh analytics overview {dangerous} rm -rf /")
        assert not ok, f"Expected '{dangerous}' to be blocked"

    def test_timeout_returns_false(self):
        import subprocess
        with patch(
            "cli.ai.executor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["sh"], timeout=120),
        ):
            with patch("cli.ai.validator.validate_command", return_value=(True, "")):
                ok, msg = execute_command("sh analytics overview")
        assert not ok
        assert "timeout" in msg.lower()

    def test_valid_sh_command_structure(self):
        """Valid 'sh analytics' command structure passes early checks without network."""
        with patch("cli.ai.validator.validate_command", return_value=(False, "test-reject")):
            ok, msg = execute_command("sh analytics overview")
        assert not ok
        assert "test-reject" in msg
