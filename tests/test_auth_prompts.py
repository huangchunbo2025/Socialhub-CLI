from __future__ import annotations

from unittest.mock import patch

from cli.auth.prompts import prompt_password, should_show_password


def test_should_show_password_false_by_default(monkeypatch):
    monkeypatch.delenv("SOCIALHUB_SHOW_PASSWORD", raising=False)
    assert should_show_password() is False


def test_should_show_password_true_from_env(monkeypatch):
    monkeypatch.setenv("SOCIALHUB_SHOW_PASSWORD", "true")
    assert should_show_password() is True


def test_prompt_password_hides_input_by_default(monkeypatch):
    monkeypatch.delenv("SOCIALHUB_SHOW_PASSWORD", raising=False)
    with patch("cli.auth.prompts.typer.prompt", return_value="secret") as prompt:
        assert prompt_password() == "secret"
    prompt.assert_called_once_with("Password", hide_input=True)


def test_prompt_password_can_be_visible_explicitly():
    with patch("cli.auth.prompts.typer.prompt", return_value="secret") as prompt:
        assert prompt_password(explicit_visible=True) == "secret"
    prompt.assert_called_once_with("Password", hide_input=False)
