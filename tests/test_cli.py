"""Tests for CLI commands."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from cli.main import app
from cli.ai.validator import validate_command


runner = CliRunner()


def test_version():
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "SocialHub.AI CLI v" in result.output


def test_help():
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "SocialHub.AI CLI" in result.output
    assert "analytics" in result.output
    assert "customers" in result.output
    assert "campaigns" in result.output


def test_config_show():
    """Test config show command."""
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "mode" in result.output.lower()


def test_config_path():
    """Test config path command."""
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "config" in result.output.lower()


def test_analytics_help():
    """Test analytics help."""
    result = runner.invoke(app, ["analytics", "--help"])
    assert result.exit_code == 0
    assert "overview" in result.output
    assert "customers" in result.output
    assert "retention" in result.output


def test_customers_help():
    """Test customers help."""
    result = runner.invoke(app, ["customers", "--help"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "get" in result.output
    assert "list" in result.output


def test_segments_help():
    """Test segments help."""
    result = runner.invoke(app, ["segments", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output


def test_campaigns_help():
    """Test campaigns help."""
    result = runner.invoke(app, ["campaigns", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output
    assert "calendar" in result.output


def test_coupons_help():
    """Test coupons help."""
    result = runner.invoke(app, ["coupons", "--help"])
    assert result.exit_code == 0
    assert "rules" in result.output
    assert "list" in result.output


def test_points_help():
    """Test points help."""
    result = runner.invoke(app, ["points", "--help"])
    assert result.exit_code == 0
    assert "rules" in result.output
    assert "balance" in result.output
    assert "history" in result.output


def test_messages_help():
    """Test messages help."""
    result = runner.invoke(app, ["messages", "--help"])
    assert result.exit_code == 0
    assert "templates" in result.output
    assert "records" in result.output
    assert "stats" in result.output


def test_tags_help():
    """Test tags help."""
    result = runner.invoke(app, ["tags", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

def test_validator_rejects_non_sh():
    ok, reason = validate_command("rm -rf /")
    assert not ok
    assert "must start with" in reason


def test_validator_accepts_valid_top_cmd():
    ok, _ = validate_command("sh analytics overview")
    assert ok


def test_validator_rejects_unknown_top_cmd():
    ok, reason = validate_command("sh foobar list")
    assert not ok
    assert "foobar" in reason


def test_validator_rejects_unknown_subcmd():
    ok, reason = validate_command("sh analytics doesnotexist")
    assert not ok
    assert "doesnotexist" in reason


def test_validator_accepts_flags_after_top_cmd():
    ok, _ = validate_command("sh analytics --help")
    assert ok


def test_validator_nested_valid():
    """sh coupons rules list — two-level nesting should pass."""
    ok, _ = validate_command("sh coupons rules list")
    assert ok


def test_validator_nested_invalid_leaf():
    """sh coupons rules listt — typo at the third level should fail."""
    ok, reason = validate_command("sh coupons rules listt")
    assert not ok
    assert "listt" in reason


def test_validator_nested_invalid_group():
    """sh messages badrules list — bad second-level group should fail."""
    ok, reason = validate_command("sh messages badrules list")
    assert not ok
    assert "badrules" in reason


def test_validator_workflow_daily_brief():
    ok, _ = validate_command("sh workflow daily-brief")
    assert ok


def test_validator_workflow_with_option():
    ok, _ = validate_command("sh workflow daily-brief --period=7d")
    assert ok


def test_validator_workflow_unknown_subcmd():
    ok, reason = validate_command("sh workflow nonexistent")
    assert not ok
    assert "nonexistent" in reason


# ---------------------------------------------------------------------------
# Workflow smoke tests
# ---------------------------------------------------------------------------

def test_workflow_help():
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0
    assert "daily-brief" in result.output


def test_workflow_daily_brief_help():
    result = runner.invoke(app, ["workflow", "daily-brief", "--help"])
    assert result.exit_code == 0
    assert "period" in result.output
    assert "output" in result.output


# ---------------------------------------------------------------------------
# analytics overview --explain / --sql-trace smoke tests
# ---------------------------------------------------------------------------

def test_analytics_overview_explain_flag_exists():
    """--explain flag should be recognised (local mode, no MCP)."""
    result = runner.invoke(app, ["analytics", "overview", "--help"])
    assert result.exit_code == 0
    assert "explain" in result.output


def test_analytics_overview_sql_trace_flag_exists():
    result = runner.invoke(app, ["analytics", "overview", "--help"])
    assert result.exit_code == 0
    assert "sql-trace" in result.output
