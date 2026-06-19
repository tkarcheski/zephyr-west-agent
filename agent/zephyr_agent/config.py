"""Runtime configuration for the zephyr-agent CLI.

Configuration is layered, most specific wins:

    CLI flags  >  environment (ZEPHYR_AGENT_*)  >  zephyr-agent.toml  >  defaults

Nothing secret is stored here. The Anthropic API key is read from the
``ANTHROPIC_API_KEY`` environment variable by the LLM client, never persisted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional

try:  # Python 3.11+ ships tomllib; fall back gracefully if a TOML file is absent.
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    tomllib = None  # type: ignore

DEFAULT_WORKSPACE = Path("~/zephyrproject").expanduser()
DEFAULT_VIVADO_SETTINGS = Path("/tools/Xilinx/Vivado/2025.1/settings64.sh")
DEFAULT_BOARD = "mbv32"
DEFAULT_SERIAL = "/dev/ttyUSB0"
DEFAULT_MODEL = "claude-opus-4-8"
CONFIG_FILENAME = "zephyr-agent.toml"


@dataclass
class AgentConfig:
    """All knobs the agent and its tools need to reach real hardware."""

    workspace: Path = DEFAULT_WORKSPACE
    vivado_settings: Path = DEFAULT_VIVADO_SETTINGS
    board: str = DEFAULT_BOARD
    serial: str = DEFAULT_SERIAL
    dev_id: Optional[str] = None
    bitstream: Optional[Path] = None
    model: str = DEFAULT_MODEL
    #: When True, hardware-affecting commands are confirmed automatically.
    assume_yes: bool = False
    #: When True, no command is actually executed; commands are logged instead.
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def zephyr_dir(self) -> Path:
        """The Zephyr checkout inside the workspace (where builds run)."""
        return self.workspace / "zephyr"

    @property
    def build_dir(self) -> Path:
        return self.zephyr_dir / "build"

    def with_overrides(self, **overrides: Any) -> "AgentConfig":
        """Return a copy with non-None overrides applied (CLI flag layer)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self


def _coerce_paths(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("workspace", "vivado_settings", "bitstream"):
        if key in data and data[key] is not None:
            data[key] = Path(str(data[key])).expanduser()
    return data


def _from_toml(path: Path) -> dict[str, Any]:
    if tomllib is None or not path.is_file():
        return {}
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    # Accept either a flat table or a [tool.zephyr-agent] / [zephyr-agent] table.
    section = raw.get("tool", {}).get("zephyr-agent") or raw.get("zephyr-agent") or raw
    return {k.replace("-", "_"): v for k, v in section.items()}


def _from_env() -> dict[str, Any]:
    mapping = {
        "ZEPHYR_AGENT_WORKSPACE": "workspace",
        "ZEPHYR_AGENT_VIVADO_SETTINGS": "vivado_settings",
        "ZEPHYR_AGENT_BOARD": "board",
        "ZEPHYR_AGENT_SERIAL": "serial",
        "ZEPHYR_AGENT_DEV_ID": "dev_id",
        "ZEPHYR_AGENT_BITSTREAM": "bitstream",
        "ZEPHYR_AGENT_MODEL": "model",
    }
    out: dict[str, Any] = {}
    for env_key, field_name in mapping.items():
        if env_key in os.environ and os.environ[env_key] != "":
            out[field_name] = os.environ[env_key]
    return out


def load_config(
    *,
    config_file: Optional[Path] = None,
    search_from: Optional[Path] = None,
) -> AgentConfig:
    """Build an :class:`AgentConfig` from TOML + environment.

    CLI overrides are applied afterwards by the caller via
    :meth:`AgentConfig.with_overrides`.
    """
    data: dict[str, Any] = {}

    path = config_file
    if path is None:
        base = search_from or Path.cwd()
        candidate = base / CONFIG_FILENAME
        path = candidate if candidate.is_file() else None
    if path is not None:
        data.update(_from_toml(path))

    data.update(_from_env())
    data = _coerce_paths(data)

    known = {f for f in AgentConfig.__dataclass_fields__ if f != "extra"}  # type: ignore[attr-defined]
    clean = {k: v for k, v in data.items() if k in known}
    extra = {k: v for k, v in data.items() if k not in known}
    cfg = AgentConfig(**clean)
    if extra:
        cfg.extra.update(extra)
    return cfg
