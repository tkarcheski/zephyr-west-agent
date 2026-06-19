"""Low-level command execution.

Wraps :mod:`subprocess` with logging, dry-run support, and a helper to run
commands inside the sourced Xilinx (Vivado/Vitis) environment that ``xsct``,
``xsdb`` and the ``xsdb`` west runner require.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

log = logging.getLogger("zephyr_agent.shell")

CommandLike = Union[str, Sequence[str]]


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    dry_run: bool = False
    skipped: bool = False  # blocked by the safety gate

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.skipped


def _to_argv(cmd: CommandLike) -> list[str]:
    if isinstance(cmd, str):
        return shlex.split(cmd)
    return [str(part) for part in cmd]


def _to_text(cmd: CommandLike) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(shlex.quote(str(part)) for part in cmd)


def run_command(
    cmd: CommandLike,
    *,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    dry_run: bool = False,
    check: bool = False,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> CommandResult:
    """Run a command and return a :class:`CommandResult`.

    With ``dry_run=True`` the command is logged and a synthetic successful
    result is returned without touching the system.
    """
    text = _to_text(cmd)
    if dry_run:
        log.info("[dry-run] %s", text)
        return CommandResult(text, 0, "", "", dry_run=True)

    log.info("$ %s", text)
    proc = subprocess.run(
        _to_argv(cmd),
        cwd=str(cwd) if cwd else None,
        env=dict(env) if env is not None else None,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )
    result = CommandResult(
        command=text,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    if check and not result.ok:
        raise subprocess.CalledProcessError(
            result.returncode, text, result.stdout, result.stderr
        )
    return result


def run_in_xilinx_env(
    cmd: CommandLike,
    *,
    vivado_settings: Path,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
    check: bool = False,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> CommandResult:
    """Run ``cmd`` after sourcing the Vivado/Vitis settings script.

    The Xilinx tools mutate ``PATH`` and a number of environment variables; the
    only reliable way to inherit them is to source ``settings64.sh`` in the same
    shell, so we wrap the command in ``bash -c``.
    """
    inner = _to_text(cmd)
    wrapped = f"source {shlex.quote(str(vivado_settings))} && {inner}"
    return run_command(
        ["bash", "-c", wrapped],
        cwd=cwd,
        dry_run=dry_run,
        check=check,
        capture=capture,
        timeout=timeout,
    )
