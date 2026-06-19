"""west workspace + build/flash/debug wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..shell import CommandResult


def build(
    ex: Executor,
    *,
    app: str,
    board: Optional[str] = None,
    pristine: bool = False,
    extra_conf: Optional[List[str]] = None,
    extra_overlay: Optional[List[str]] = None,
) -> CommandResult:
    """``west build`` — non-destructive, runs freely.

    ``board`` defaults to the configured board; pass ``native_sim`` for the fast
    host loop.
    """
    board = board or ex.config.board
    cmd: List[str] = ["west", "build"]
    if pristine:
        cmd.append("-p")
    cmd += ["-b", board, app]

    extras: List[str] = []
    if extra_conf:
        extras.append(f"-DEXTRA_CONF_FILE={';'.join(extra_conf)}")
    if extra_overlay:
        extras.append(f"-DEXTRA_DTC_OVERLAY_FILE={';'.join(extra_overlay)}")
    if extras:
        cmd.append("--")
        cmd += extras
    return ex.run(cmd, label=f"west build -b {board} {app}")


def update(ex: Executor) -> CommandResult:
    """``west update`` — sync the manifest projects."""
    return ex.run(["west", "update"], label="west update")


def flash(
    ex: Executor,
    *,
    elf: Optional[Path] = None,
    bitstream: Optional[Path] = None,
    runner: str = "xsdb",
    dev_id: Optional[str] = None,
) -> CommandResult:
    """``west flash`` over the xsdb runner — DESTRUCTIVE (gated).

    Programs the board over JTAG. ``elf``/``bitstream``/``dev_id`` fall back to
    the build output and configured defaults.
    """
    elf = elf or (ex.config.build_dir / "zephyr" / "zephyr.elf")
    bitstream = bitstream or ex.config.bitstream
    dev_id = dev_id or ex.config.dev_id

    cmd: List[str] = ["west", "flash", "--runner", runner, "--elf-file", str(elf)]
    if bitstream:
        cmd += ["--bitstream", str(bitstream)]
    if dev_id:
        cmd += ["--dev-id", dev_id]
    return ex.run(cmd, xilinx_env=True, label=f"west flash --runner {runner}")


def debug(ex: Executor, *, runner: str = "xsdb") -> CommandResult:
    """``west debug`` — attaches a debugger (treated as safe: no programming)."""
    return ex.run(
        ["west", "debug", "--runner", runner],
        xilinx_env=True,
        capture=False,
        label=f"west debug --runner {runner}",
    )


def setup_workspace(ex: Executor, *, kernel_rev: str = "v3.7.0") -> List[CommandResult]:
    """Bootstrap the AMD Zephyr west workspace (idempotent-ish best effort).

    Mirrors references/west-workspace.md. Returns the result of each step so the
    caller can stop on the first failure.
    """
    ws = ex.config.workspace
    steps: List[List[str]] = [
        ["west", "init", "-m", "https://github.com/zephyrproject-rtos/zephyr",
         "--mr", kernel_rev],
        ["west", "update"],
        ["west", "lopper-install"],
    ]
    results: List[CommandResult] = []
    for step in steps:
        cwd = ws if step[:2] == ["west", "init"] else ex.config.zephyr_dir
        res = ex.run(step, cwd=cwd, label=" ".join(step))
        results.append(res)
        if not res.ok:
            break
    return results
