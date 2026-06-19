"""zephyr-agent command-line interface.

A thin wrapper over west / lopper / xsdb / twister with a gated execution model
and an LLM-driven debug loop (`ask`). See the zephyr-versal skill for the
methodology these commands serve.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import AgentConfig, load_config
from .executor import Executor
from .safety import patterns_for_docs
from .tools import lopper, twister, west, xsdb


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    """Global flags, with suppressed defaults so they can appear on either side
    of the subcommand without the subparser clobbering an earlier value."""
    s = argparse.SUPPRESS
    parser.add_argument("--workspace", type=Path, default=s, help="west workspace (default ~/zephyrproject)")
    parser.add_argument("--board", default=s, help="target board (default mbv32)")
    parser.add_argument("--serial", default=s, help="device serial port for HIL (default /dev/ttyUSB0)")
    parser.add_argument("--dev-id", default=s, help="JTAG cable/dev id for west flash")
    parser.add_argument("--bitstream", type=Path, default=s, help="bitstream/PDI path for flashing")
    parser.add_argument("--vivado-settings", type=Path, default=s, help="path to Vivado settings64.sh")
    parser.add_argument("--model", default=s, help="Claude model id for `ask` (default claude-opus-4-8)")
    parser.add_argument("--config", type=Path, default=s, help="path to zephyr-agent.toml")
    parser.add_argument("-n", "--dry-run", action="store_true", default=s, help="print commands, don't run them")
    parser.add_argument("-y", "--yes", action="store_true", default=s, help="auto-confirm destructive (gated) commands")
    parser.add_argument("-v", "--verbose", action="count", default=s, help="-v info, -vv debug")


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_global_flags(common)

    p = argparse.ArgumentParser(
        prog="zephyr-agent",
        description="Gated CLI agent for Zephyr on AMD Versal (west/lopper/xsdb/twister).",
        parents=[common],
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("setup", parents=[common], help="bootstrap the AMD Zephyr west workspace")
    sp.set_defaults(func=_cmd_setup)

    sp = sub.add_parser("sdt", parents=[common], help="XSA -> System Device Tree -> Zephyr DT (Lopper)")
    sp.add_argument("--xsa", type=Path, required=True, help="Vivado XSA file")
    sp.add_argument("--out-dir", default="my_design", help="SDT output dir")
    sp.add_argument("--processor", default="microblaze_riscv_0", help="SDT processor node")
    sp.add_argument("--sdt", type=Path, help="system-top.dts (defaults to <out-dir>/system-top.dts)")
    sp.set_defaults(func=_cmd_sdt)

    sp = sub.add_parser("build", parents=[common], help="west build (use --board native_sim for the fast loop)")
    sp.add_argument("app", help="application/sample/test path")
    sp.add_argument("-p", "--pristine", action="store_true")
    sp.add_argument("--conf", action="append", help="EXTRA_CONF_FILE fragment (repeatable)")
    sp.add_argument("--overlay", action="append", help="EXTRA_DTC_OVERLAY_FILE (repeatable)")
    sp.set_defaults(func=_cmd_build)

    sp = sub.add_parser("flash", parents=[common], help="west flash over xsdb (GATED)")
    sp.add_argument("--elf", type=Path, help="ELF to flash (default build output)")
    sp.add_argument("--runner", default="xsdb")
    sp.set_defaults(func=_cmd_flash)

    sp = sub.add_parser("debug", parents=[common], help="west debug over xsdb (attach)")
    sp.add_argument("--runner", default="xsdb")
    sp.set_defaults(func=_cmd_debug)

    sp = sub.add_parser("targets", parents=[common], help="list JTAG targets via xsdb (safe)")
    sp.set_defaults(func=_cmd_targets)

    sp = sub.add_parser("program", parents=[common], help="program a PDI via xsdb (GATED)")
    sp.add_argument("--pdi", type=Path, required=True)
    sp.set_defaults(func=_cmd_program)

    sp = sub.add_parser("test", parents=[common], help="run Twister (native_sim, or --hw for gated HIL)")
    sp.add_argument("testdir", nargs="?", default="tests/")
    sp.add_argument("--hw", action="store_true", help="device-testing on attached board (GATED)")
    sp.add_argument("--coverage", action="store_true")
    sp.add_argument("-t", "--tag", action="append", dest="tags")
    sp.set_defaults(func=_cmd_test)

    sp = sub.add_parser("ask", parents=[common], help="LLM-driven debug loop over the workspace")
    sp.add_argument("prompt", nargs="+", help="the question / symptom to debug")
    sp.set_defaults(func=_cmd_ask)

    sp = sub.add_parser("gating", parents=[common], help="show what counts as a destructive (gated) command")
    sp.set_defaults(func=_cmd_gating)

    return p


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(message)s")


def _make_config(args: argparse.Namespace) -> AgentConfig:
    # Global flags use argparse.SUPPRESS, so they may be absent from the
    # namespace entirely; getattr keeps the config-file/env layer authoritative.
    g = lambda name, default=None: getattr(args, name, default)
    cfg = load_config(config_file=g("config"))
    return cfg.with_overrides(
        workspace=g("workspace"),
        board=g("board"),
        serial=g("serial"),
        dev_id=g("dev_id"),
        bitstream=g("bitstream"),
        vivado_settings=g("vivado_settings"),
        model=g("model"),
        assume_yes=g("yes", False) or None,
        dry_run=g("dry_run", False) or None,
    )


# -- command handlers ----------------------------------------------------

def _report(results) -> int:
    if not isinstance(results, list):
        results = [results]
    rc = 0
    for res in results:
        if res is None:
            continue
        if res.skipped:
            print(f"[blocked] {res.command}", file=sys.stderr)
            rc = rc or 126
        elif not res.ok:
            sys.stderr.write(res.stderr)
            rc = rc or res.returncode
        else:
            if res.stdout:
                sys.stdout.write(res.stdout)
    return rc


def _cmd_setup(ex: Executor, args) -> int:
    return _report(west.setup_workspace(ex))


def _cmd_sdt(ex: Executor, args) -> int:
    r1 = lopper.generate_sdt(ex, xsa=args.xsa, out_dir=args.out_dir)
    if not r1.ok:
        return _report(r1)
    sdt = args.sdt or (Path(args.out_dir) / "system-top.dts")
    r2 = lopper.lopper_command(ex, processor=args.processor, sdt=sdt)
    return _report([r1, r2])


def _cmd_build(ex: Executor, args) -> int:
    return _report(
        west.build(
            ex,
            app=args.app,
            pristine=args.pristine,
            extra_conf=args.conf,
            extra_overlay=args.overlay,
        )
    )


def _cmd_flash(ex: Executor, args) -> int:
    return _report(west.flash(ex, elf=args.elf, runner=args.runner))


def _cmd_debug(ex: Executor, args) -> int:
    return _report(west.debug(ex, runner=args.runner))


def _cmd_targets(ex: Executor, args) -> int:
    return _report(xsdb.list_targets(ex))


def _cmd_program(ex: Executor, args) -> int:
    return _report(xsdb.program_pdi(ex, pdi=args.pdi))


def _cmd_test(ex: Executor, args) -> int:
    return _report(
        twister.run(
            ex,
            testdir=args.testdir,
            device_testing=args.hw,
            coverage=args.coverage,
            tags=args.tags,
        )
    )


def _cmd_ask(ex: Executor, args) -> int:
    from .llm import Agent, find_skill_context

    prompt = " ".join(args.prompt)
    agent = Agent(ex, skill_context=find_skill_context())
    try:
        agent.run(prompt)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _cmd_gating(ex: Executor, args) -> int:
    print("Commands matching any of these are treated as DESTRUCTIVE and gated:")
    for pat in patterns_for_docs():
        print(f"  - {pat}")
    print("\nUse --yes to auto-confirm, or --dry-run to preview without executing.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", 0))
    cfg = _make_config(args)
    ex = Executor(cfg)
    return args.func(ex, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
