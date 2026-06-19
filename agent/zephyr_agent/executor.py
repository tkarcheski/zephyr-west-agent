"""The execution layer the tools call.

Ties together configuration, the safety gate, and the shell runner so every
command the agent issues passes through one choke point:

    classify -> (gate if destructive) -> run (or dry-run) -> CommandResult

Tools never call :mod:`subprocess` directly; they build a command and hand it to
:class:`Executor`, which is the single place hardware-affecting actions are
allowed or blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .config import AgentConfig
from .safety import Gate, Risk
from .shell import CommandLike, CommandResult, run_command, run_in_xilinx_env

log = logging.getLogger("zephyr_agent.executor")


class Executor:
    def __init__(self, config: AgentConfig, *, gate: Optional[Gate] = None) -> None:
        self.config = config
        self.gate = gate or Gate(assume_yes=config.assume_yes)

    def run(
        self,
        cmd: CommandLike,
        *,
        cwd: Optional[Path] = None,
        xilinx_env: bool = False,
        check: bool = False,
        capture: bool = True,
        label: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Gate (if needed) then execute a command.

        ``xilinx_env=True`` sources the Vivado/Vitis settings first (needed for
        ``xsct``/``xsdb`` and the xsdb west runner).
        """
        decision = self.gate.evaluate(cmd, label=label)
        if not decision.allowed:
            log.warning("BLOCKED (%s): %s", decision.reason, label or cmd)
            from .shell import _to_text  # local import to avoid cycle at top

            return CommandResult(
                command=_to_text(cmd),
                returncode=126,
                stdout="",
                stderr=f"blocked by safety gate: {decision.reason}",
                skipped=True,
            )
        if decision.risk is Risk.DESTRUCTIVE:
            log.info("PROCEEDING (%s)", decision.reason)

        cwd = cwd or self.config.zephyr_dir
        if xilinx_env:
            return run_in_xilinx_env(
                cmd,
                vivado_settings=self.config.vivado_settings,
                cwd=cwd,
                dry_run=self.config.dry_run,
                check=check,
                capture=capture,
                timeout=timeout,
            )
        return run_command(
            cmd,
            cwd=cwd,
            dry_run=self.config.dry_run,
            check=check,
            capture=capture,
            timeout=timeout,
        )
