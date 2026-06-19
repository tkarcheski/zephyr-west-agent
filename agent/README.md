# zephyr-agent

A gated CLI agent for debugging Zephyr on AMD Versal hardware. It wraps
`west` / `lopper` / `xsdb` / `twister`, routes every command through one safety
gate, and offers an LLM-driven debug loop (`ask`). It is the executor for the
[`zephyr-versal` skill](../.claude/skills/zephyr-versal/).

## Install

```bash
pip install -e .            # core CLI, zero runtime deps
pip install -e '.[llm]'     # adds `ask` (anthropic)
pip install -e '.[dev]'     # adds pytest
```

Requires Python ≥ 3.9. The hardware commands additionally need a Linux host with
Vivado/Vitis 2025.1 and a JTAG programmer; the CLI itself runs anywhere
(use `--dry-run` to preview commands without hardware).

## Commands

| Command | Purpose | Gated? |
| --- | --- | --- |
| `setup` | Bootstrap the AMD Zephyr west workspace | no |
| `sdt --xsa X` | XSA → System Device Tree → Zephyr DT (xsct/sdtgen + Lopper) | no |
| `build APP [--board B] [-p] [--conf F] [--overlay O]` | `west build` (`--board native_sim` for the fast loop) | no |
| `flash [--elf E]` | `west flash` over the xsdb runner | **yes** |
| `program --pdi P` | Program a Versal PDI via xsdb | **yes** |
| `debug` | `west debug` (attach only) | no |
| `targets` | List JTAG targets via xsdb | no |
| `test [DIR] [--hw] [--coverage] [-t TAG]` | Twister; `--hw` = device-testing on the board | `--hw` only |
| `ask "PROMPT"` | LLM-driven debug loop over the workspace | per-command |
| `gating` | Print what counts as destructive | no |

Global flags (accepted before or after the subcommand): `--workspace`,
`--board`, `--serial`, `--dev-id`, `--bitstream`, `--vivado-settings`,
`--model`, `--config`, `-n/--dry-run`, `-y/--yes`, `-v/--verbose`.

## Safety model

Commands are classified `SAFE` or `DESTRUCTIVE` by `safety.py`. Destructive =
anything that programs or perturbs the board: `west flash`, `device program`,
bitstream/PDI load, boot-mode change, `dow`/download, reset, erase, and Twister
`--device-testing`. These require confirmation; everything else runs freely.
`--yes` auto-confirms, `--dry-run` prints commands without executing. Run
`zephyr-agent gating` for the live list.

## Architecture

```
cli.py        argparse front end, one handler per subcommand
config.py     layered config (flags > env > toml > defaults)
safety.py     classify() + Gate: the destructive-command policy
shell.py      subprocess runner, dry-run, Xilinx-env sourcing
executor.py   the choke point: gate -> run; tools never touch subprocess directly
tools/        west.py, lopper.py, xsdb.py, twister.py  (build the actual commands)
llm.py        Anthropic tool-use loop powering `ask` (run_shell/read_file/write_file)
```

Every command path — including the tools the LLM calls — flows through
`Executor.run`, so the gate cannot be bypassed.

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

The suite is fully offline: subprocess execution is exercised via `--dry-run`,
and the gate's confirmation function is injected, so no hardware or network (or
Anthropic key) is needed to test.
