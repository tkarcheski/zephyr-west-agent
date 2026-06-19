# zephyr-west-agent

An AI expert in **Zephyr RTOS development on AMD Versal FPGAs** — west workspaces,
Lopper-generated devicetree (the Versal "HAL"), JTAG/xsdb programming, and
Ztest/Twister test engineering.

It ships in two pieces that work together:

| Piece | What it is | Where |
| --- | --- | --- |
| **`zephyr-versal` skill** | A Claude skill that drives a disciplined **debug + test-engineering loop**: form one hypothesis, write a Ztest / toggle a Kconfig fragment / devicetree overlay, build, run on `native_sim` or real hardware, observe, iterate, then capture the fix as a regression test. | [`.claude/skills/zephyr-versal/`](.claude/skills/zephyr-versal/) |
| **`zephyr-agent` CLI** | A thin Python CLI that *executes* that loop on real hardware — wrapping `west` / `lopper` / `xsdb` / `twister` — with hardware-affecting commands **gated** behind confirmation, plus an LLM-driven `ask` command. | [`agent/`](agent/) |

Both assume **real hardware**: a Linux host with Vivado/Vitis 2025.1, a JTAG
programmer, and a Versal board (MicroBlaze-V `mbv32` and/or Cortex-R52 RPU),
running the `Xilinx/zephyr-amd` fork (`xlnx_rel_v2025.1`, kernel `v3.7.0`).

## The skill

The skill turns a vague symptom ("won't boot", "device not ready", "UART
silent") into a falsifiable experiment loop. `SKILL.md` is the router; the
detailed playbooks live under `references/`:

- `debug-loop.md` — triage methodology (resolved-truth first, `device_is_ready` decision tree, bisection)
- `test-engineering.md` — Ztest anatomy, `testcase.yaml`, Twister HIL, coverage, fault injection
- `west-workspace.md`, `versal-hal-devicetree.md`, `jtag-xsdb.md`,
  `app-structure.md`, `board-porting.md`, `devops-qol.md`

Claude Code discovers the skill automatically from `.claude/skills/`.

## The CLI agent

```bash
cd agent
pip install -e .            # core CLI (no LLM deps)
pip install -e '.[llm]'     # add `ask` (Anthropic SDK)

zephyr-agent gating         # show what's treated as destructive (gated)
zephyr-agent --dry-run build samples/hello_world --board native_sim
zephyr-agent build samples/hello_world            # real build
zephyr-agent flash --bitstream system.pdi         # GATED: asks before programming
zephyr-agent test tests/drivers/uart              # native_sim (fast, free)
zephyr-agent test tests/drivers/uart --hw         # GATED: device-testing on the board
export ANTHROPIC_API_KEY=...                       # for the reasoning loop
zephyr-agent ask "mbv32 boots but the console UART is silent"
```

**Safety model:** read-only/build commands run freely; flash, PDI/bitstream
programming, boot-mode change, reset, and Twister `--device-testing` are
**destructive** and require confirmation (`--yes` to auto-confirm, `--dry-run` to
preview). See `zephyr-agent gating`.

Configuration layers **CLI flags > `ZEPHYR_AGENT_*` env > `zephyr-agent.toml` >
defaults** — see `agent/zephyr-agent.toml.example`. The Anthropic API key is only
ever read from the environment, never stored.

See [`agent/README.md`](agent/README.md) for the full command reference and the
development/testing workflow.

## Provenance

The Zephyr/Versal knowledge base originates from
[issue #1](https://github.com/tkarcheski/zephyr-west-agent/issues/1).
