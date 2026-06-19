"""Twister test-runner wrapper (native_sim fast loop + gated HIL).

``native_sim`` runs are non-destructive. ``--device-testing`` flashes the
attached board, so the safety gate classifies it as destructive (see
references/test-engineering.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..shell import CommandResult

TWISTER = "./scripts/twister"


def run(
    ex: Executor,
    *,
    testdir: str = "tests/",
    board: Optional[str] = None,
    device_testing: bool = False,
    serial: Optional[str] = None,
    runner: str = "xsdb",
    bitstream: Optional[Path] = None,
    coverage: bool = False,
    tags: Optional[List[str]] = None,
) -> CommandResult:
    """Run Twister.

    Host loop (default): ``board=native_sim`` (or the configured board) without
    ``device_testing``. Hardware loop: ``device_testing=True`` flashes the board
    over the xsdb runner — gated.
    """
    board = board or ex.config.board
    cmd: List[str] = [TWISTER, "-p", board, "-T", testdir]
    if tags:
        for tag in tags:
            cmd += ["-t", tag]
    if coverage:
        cmd += ["--coverage", "--coverage-tool", "gcovr"]

    if device_testing:
        serial = serial or ex.config.serial
        bitstream = bitstream or ex.config.bitstream
        cmd += [
            "--west-runner", runner,
            "--device-testing",
            "--device-serial", serial,
        ]
        if bitstream:
            cmd.append(f"--west-flash=--bitstream={bitstream}")
        return ex.run(cmd, xilinx_env=True, capture=False,
                      label=f"twister HIL -p {board}")

    return ex.run(cmd, capture=False, label=f"twister -p {board}")
