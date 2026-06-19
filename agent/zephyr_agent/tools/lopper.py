"""XSA -> System Device Tree -> Zephyr devicetree (the Versal HAL pipeline).

See references/versal-hal-devicetree.md. Both steps require the Xilinx
environment, so they run with ``xilinx_env=True``. Neither programs hardware, so
both are non-destructive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..shell import CommandResult


def generate_sdt(
    ex: Executor,
    *,
    xsa: Path,
    out_dir: str = "my_design",
) -> CommandResult:
    """Run ``xsct``/``sdtgen`` to turn a Vivado XSA into a System Device Tree."""
    eval_script = (
        f"sdtgen set_dt_param -dir {out_dir} -xsa {xsa} ; sdtgen generate_sdt"
    )
    return ex.run(
        ["xsct", "-eval", eval_script],
        xilinx_env=True,
        label=f"sdtgen {xsa} -> {out_dir}",
    )


def lopper_command(
    ex: Executor,
    *,
    processor: str,
    sdt: Path,
    workspace: Optional[Path] = None,
    dtc_flags: str = "-b 0 -@",
) -> CommandResult:
    """Specialise the SDT for one processor into a Zephyr devicetree.

    ``processor`` is the SDT node to target, e.g. ``microblaze_riscv_0`` or the
    RPU/APU core. ``LOPPER_DTC_FLAGS`` defaults to ``-b 0 -@`` to keep symbols
    and overlays usable.
    """
    workspace = workspace or ex.config.zephyr_dir
    # west lopper-command must see LOPPER_DTC_FLAGS in its environment; wrap it.
    inner = (
        f'LOPPER_DTC_FLAGS="{dtc_flags}" west lopper-command '
        f"-p {processor} -s {sdt} -w {workspace}"
    )
    return ex.run(
        ["bash", "-c", inner],
        xilinx_env=True,
        label=f"lopper -p {processor} -s {sdt}",
    )
