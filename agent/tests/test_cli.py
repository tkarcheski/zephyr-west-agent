import builtins

import pytest

from zephyr_agent.cli import main


def test_build_dry_run_returns_zero(capsys):
    rc = main(["--dry-run", "build", "samples/hello_world", "--board", "native_sim"])
    assert rc == 0


def test_gating_listing(capsys):
    rc = main(["gating"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DESTRUCTIVE" in out
    assert "west" in out


def test_flash_blocked_without_confirmation(monkeypatch, capsys):
    # Simulate the operator declining at the prompt.
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "n")
    rc = main(["--dry-run", "flash"])
    err = capsys.readouterr().err
    assert rc == 126
    assert "blocked" in err.lower()


def test_flash_allowed_with_yes_flag(monkeypatch):
    # --yes auto-confirms; --dry-run keeps it from touching hardware.
    rc = main(["--dry-run", "--yes", "flash", "--elf", "/tmp/zephyr.elf"])
    assert rc == 0


def test_ask_without_api_key_errors(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["--dry-run", "ask", "why", "won't", "it", "boot"])
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
