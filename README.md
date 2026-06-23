# zephyr-west-agent

AI experts in **Zephyr RTOS development on heterogeneous SoCs**. Each specialises
the same disciplined **debug + test-engineering loop** — form one hypothesis,
write a Ztest / toggle a Kconfig fragment / devicetree overlay, build, run on
`native_sim`/QEMU or real hardware, observe, iterate, then capture the fix as a
regression test — for a specific silicon family and toolchain.

It ships as a set of Claude skills, plus a CLI that executes the loop on Versal
hardware:

| Piece | Specialises in | Where |
| --- | --- | --- |
| **`zephyr-versal` skill** | Zephyr on **AMD Versal** — west workspaces, Lopper-generated devicetree (the Versal "HAL"), JTAG/xsdb programming, MicroBlaze-V `mbv32` / Cortex-R52 RPU. | [`.claude/skills/zephyr-versal/`](.claude/skills/zephyr-versal/) |
| **`zephyr-qrb2210` skill** | Zephyr on the **Qualcomm QRB2210 / QCM2290** (Robotics RB1) — quad Cortex-A53 (AArch64) bring-up, devicetree ported from mainline Linux, GENI/QUP console, and loading over fastboot / qdl (EDL) instead of JTAG. | [`.claude/skills/zephyr-qrb2210/`](.claude/skills/zephyr-qrb2210/) |
| **`zephyr-agent` CLI** | A thin Python CLI that *executes* the Versal loop on real hardware — wrapping `west` / `lopper` / `xsdb` / `twister` — with hardware-affecting commands **gated** behind confirmation, plus an LLM-driven `ask` command. | [`agent/`](agent/) |

Claude Code discovers both skills automatically from `.claude/skills/` and routes
to whichever one's triggers match (Versal/`mbv32`/xsdb vs QRB2210/QCM2290/fastboot).
The Versal flow assumes a Linux host with Vivado/Vitis 2025.1, a JTAG programmer,
and a Versal board running the `Xilinx/zephyr-amd` fork; the QRB2210 flow assumes
an RB1 dev kit with `fastboot`/`qdl` and upstream Zephyr.

## The Versal skill

`zephyr-versal` turns a vague symptom ("won't boot", "device not ready", "UART
silent") into a falsifiable experiment loop. `SKILL.md` is the router; the
detailed playbooks live under `references/`:

- `debug-loop.md` — triage methodology (resolved-truth first, `device_is_ready` decision tree, bisection)
- `test-engineering.md` — Ztest anatomy, `testcase.yaml`, Twister HIL, coverage, fault injection
- `west-workspace.md`, `versal-hal-devicetree.md`, `jtag-xsdb.md`,
  `app-structure.md`, `board-porting.md`, `devops-qol.md`

## The QRB2210 skill

`zephyr-qrb2210` specialises the same loop for the **Qualcomm QRB2210 / QCM2290**
(Robotics RB1) — a quad Cortex-A53 (AArch64) application SoC, not an MCU or FPGA.
There is **no upstream Zephyr board for it**, so the skill is a bring-up/porting
guide as much as a debug loop. `SKILL.md` routes; `references/` covers:

- `execution-models.md` — the three real ways Zephyr meets this SoC (on the A53
  cores; AMP under Qualcomm Linux via OpenAMP/RPMsg; or a companion MCU) — **read
  this first**, it decides everything downstream
- `board-porting.md` — the AArch64 SoC/board port: GICv3, ARM generic timer,
  PSCI/SMP, the MMU map, and the GENI UART driver that gates first light
- `qcm2290-hal-devicetree.md` — the "HAL" = a Zephyr DT transcribed from the
  mainline Linux QCM2290 DT (no Lopper here)
- `boot-flash-fastboot.md` — loading over `fastboot boot` / `qdl` (EDL firehose)
  and JTAG/T32, with the destructive-command gating policy
- `debug-loop.md`, `west-workspace.md`, `app-structure.md`,
  `test-engineering.md`, `devops-qol.md`

The inner loop is two free tiers — `native_sim` (logic) and `qemu_cortex_a53`
(the AArch64/GIC/timer/PSCI path) — before any hardware. The `zephyr-agent` CLI
above does not yet execute the Qualcomm flow; the fastboot/qdl gating policy it
*would* enforce is specified in `boot-flash-fastboot.md`.

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
