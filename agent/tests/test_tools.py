from pathlib import Path

from zephyr_agent.config import AgentConfig
from zephyr_agent.executor import Executor
from zephyr_agent.safety import Gate
from zephyr_agent.tools import lopper, twister, west, xsdb


def _ex(*, allow=False, assume_yes=False, **cfg_kw):
    cfg_kw.setdefault("board", "mbv32")
    cfg = AgentConfig(dry_run=True, **cfg_kw)
    gate = Gate(assume_yes=assume_yes, confirm=lambda _: allow)
    return Executor(cfg, gate=gate)


def test_build_command_includes_board_and_fragments():
    ex = _ex()
    res = west.build(
        ex, app="app", pristine=True,
        extra_conf=["debug.conf"], extra_overlay=["debug.overlay"],
    )
    assert "west build -p -b mbv32 app" in res.command
    assert "-DEXTRA_CONF_FILE=debug.conf" in res.command
    assert "-DEXTRA_DTC_OVERLAY_FILE=debug.overlay" in res.command


def test_build_defaults_to_configured_board():
    res = west.build(_ex(board="native_sim"), app="tests/x")
    assert "-b native_sim" in res.command


def test_flash_is_gated():
    blocked = west.flash(_ex(allow=False), bitstream=Path("/tmp/system.bit"))
    assert blocked.skipped

    ok = west.flash(_ex(allow=True), bitstream=Path("/tmp/system.bit"))
    assert not ok.skipped
    assert "west flash --runner xsdb" in ok.command
    assert "--bitstream /tmp/system.bit" in ok.command


def test_program_pdi_is_gated():
    assert xsdb.program_pdi(_ex(allow=False), pdi=Path("a.pdi")).skipped
    ok = xsdb.program_pdi(_ex(allow=True), pdi=Path("a.pdi"))
    assert "device program a.pdi" in ok.command


def test_list_targets_is_safe():
    res = xsdb.list_targets(_ex(allow=False))
    assert not res.skipped and res.ok
    assert "targets" in res.command


def test_twister_native_sim_safe_hw_gated():
    safe = twister.run(_ex(), board="native_sim", testdir="tests/")
    assert not safe.skipped
    assert "-p native_sim" in safe.command

    blocked = twister.run(_ex(allow=False), device_testing=True)
    assert blocked.skipped


def test_lopper_pipeline_builds_commands():
    ex = _ex()
    sdt = lopper.generate_sdt(ex, xsa=Path("d.xsa"), out_dir="design")
    assert "sdtgen" in sdt.command and "d.xsa" in sdt.command
    lc = lopper.lopper_command(ex, processor="microblaze_riscv_0", sdt=Path("design/system-top.dts"))
    assert "west lopper-command" in lc.command
    assert "microblaze_riscv_0" in lc.command
