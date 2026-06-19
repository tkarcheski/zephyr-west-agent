from pathlib import Path

from zephyr_agent.config import AgentConfig, load_config


def test_defaults_and_derived_paths():
    cfg = AgentConfig(workspace=Path("/ws"))
    assert cfg.board == "mbv32"
    assert cfg.zephyr_dir == Path("/ws/zephyr")
    assert cfg.build_dir == Path("/ws/zephyr/build")


def test_with_overrides_ignores_none():
    cfg = AgentConfig(board="mbv32")
    out = cfg.with_overrides(board=None, serial="/dev/ttyUSB9")
    assert out.board == "mbv32"
    assert out.serial == "/dev/ttyUSB9"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ZEPHYR_AGENT_BOARD", "native_sim")
    monkeypatch.setenv("ZEPHYR_AGENT_WORKSPACE", "/tmp/ws")
    cfg = load_config()
    assert cfg.board == "native_sim"
    assert cfg.workspace == Path("/tmp/ws")


def test_toml_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ZEPHYR_AGENT_BOARD", raising=False)
    f = tmp_path / "zephyr-agent.toml"
    f.write_text('board = "versal_rpu"\nserial = "/dev/ttyUSB3"\n')
    cfg = load_config(config_file=f)
    assert cfg.board == "versal_rpu"
    assert cfg.serial == "/dev/ttyUSB3"
