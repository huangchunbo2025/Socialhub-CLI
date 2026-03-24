"""Tests for CLI commands."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from cli.main import app


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
