"""Manual xsdb JTAG sessions.

For when the ``west flash`` runner abstracts away too much and you need to drive
targets, program a PDI, or download an ELF by hand (see references/jtag-xsdb.md).

Commands are passed to ``xsdb -eval`` joined by ``;`` so no temp files are
written, keeping dry-run pure. Everything runs inside the Xilinx environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..shell import CommandResult


def run_tcl(ex: Executor, commands: List[str], *, label: str) -> CommandResult:
    """Run a sequence of xsdb TCL commands."""
    script = " ; ".join(commands)
    return ex.run(["xsdb", "-eval", script], xilinx_env=True, label=label)


def list_targets(ex: Executor) -> CommandResult:
    """Connect and print the JTAG target tree — SAFE (read-only)."""
    return run_tcl(ex, ["connect", "targets"], label="xsdb targets")


def program_pdi(ex: Executor, *, pdi: Path) -> CommandResult:
    """Program a Versal PDI (PLM + bitstream) — DESTRUCTIVE (gated)."""
    return run_tcl(
        ex,
        ["connect", "ta 1", f"device program {pdi}"],
        label=f"xsdb device program {pdi}",
    )


def download_elf(
    ex: Executor,
    *,
    elf: Optional[Path] = None,
    core_filter: Optional[str] = None,
) -> CommandResult:
    """Stop the selected core and download an ELF into it — DESTRUCTIVE (gated).

    ``core_filter`` is an xsdb ``-filter`` expression, e.g.
    ``name =~ "Cortex-R52*#0"`` or ``name =~ "MicroBlaze*"``.
    """
    elf = elf or (ex.config.build_dir / "zephyr" / "zephyr.elf")
    cmds = ["connect"]
    if core_filter:
        cmds.append(f"targets -set -filter {{{core_filter}}}")
    cmds += ["stop", f"dow {elf}", "con"]
    return run_tcl(ex, cmds, label=f"xsdb dow {elf}")


def change_boot_mode(ex: Executor, *, tcl: str = "versal_change_boot_mode.tcl") -> CommandResult:
    """Switch the board to JTAG boot mode — DESTRUCTIVE (gated)."""
    return run_tcl(ex, ["connect", f"source {tcl}"], label="xsdb change_boot_mode")
