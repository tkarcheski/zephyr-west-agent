---
name: zephyr-versal
description: >-
  Debug and test-engineering loop for Zephyr RTOS on AMD Versal / MicroBlaze-V
  (mbv32) and Cortex-R52 RPU, using west, Lopper-generated devicetree, and JTAG
  via xsdb. Use when debugging a Zephyr build/boot/driver failure, when a
  peripheral won't bind, when iterating on Kconfig fragments or devicetree
  overlays, or when writing/running Ztest suites and Twister hardware-in-the-loop
  tests. Triggers: "zephyr won't boot", "device not ready", "driver not binding",
  "west build error", "write a ztest", "twister device-testing", "xsdb flash",
  "lopper", "XSA to devicetree", "mbv32", "versal", "RPU".
---

# Zephyr on AMD Versal — Debug & Test-Engineering Loop

This skill turns a vague symptom ("it doesn't boot", "the UART is silent",
"`device_is_ready()` returns false") into a disciplined experiment loop that
converges on a root cause and a regression test that proves it stays fixed.

The companion CLI agent (`agent/`, command `zephyr-agent`) executes this loop on
real hardware. Hardware-affecting steps (flash, `device program`, boot-mode
change) are **gated** — they require confirmation. Read-only and build steps run
freely.

## The loop

Work one hypothesis at a time. Never change two variables in the same build.

1. **Triage** — collect the symptom and the ground truth. Read, in order:
   `west build` output, `build/zephyr/zephyr.dts` (the *resolved* devicetree),
   `build/zephyr/.config` (the *resolved* Kconfig), and serial/xsdb output.
   The resolved artifacts are the truth; `prj.conf` and overlays are only
   *requests*. See `references/debug-loop.md`.
2. **Hypothesize** — name one cause: a Kconfig symbol unset, a devicetree node
   `disabled`/missing, wrong board, a driver not selected, an init-priority
   ordering bug, a memory/linker placement issue, or a clock/pinctrl gap.
3. **Experiment** — make the *smallest* change that confirms or kills the
   hypothesis. Prefer, in order:
   - a focused **Ztest** case that isolates the suspect API (`references/test-engineering.md`),
   - a **Kconfig fragment** (`-DEXTRA_CONF_FILE=debug.conf`) — never edit `.config` directly,
   - a **devicetree overlay** (`boards/<board>.overlay` or `-DEXTRA_DTC_OVERLAY_FILE`).
4. **Build & run** — `native_sim` first for logic bugs (fast, free), then real
   hardware via xsdb only when the bug is hardware-specific (`references/jtag-xsdb.md`).
5. **Observe** — compare actual output to the expectation the experiment encoded.
   If inconclusive, the experiment was too big — shrink it.
6. **Converge** — when the cause is proven, capture it as a permanent Ztest
   case (or Twister scenario) so the regression can't return, then apply the
   real fix and re-run.

## Routing — read the reference for the phase you're in

| You are… | Read |
| --- | --- |
| Triaging any failure | `references/debug-loop.md` |
| Writing/structuring tests, `testcase.yaml`, coverage, HIL | `references/test-engineering.md` |
| Setting up / repairing the west workspace, manifest, SDK | `references/west-workspace.md` |
| Chasing a devicetree/HAL / XSA→SDT→Lopper issue | `references/versal-hal-devicetree.md` |
| Flashing/debugging over JTAG, target/core selection, PDI | `references/jtag-xsdb.md` |
| Scaffolding an app (`CMakeLists.txt`, `prj.conf`, overlays) | `references/app-structure.md` |
| Porting/adding a board | `references/board-porting.md` |
| Pre-commit, CI, VS Code, dev QoL | `references/devops-qol.md` |

## Reference environment (assume real hardware)

- AMD Zephyr fork `Xilinx/zephyr-amd` branch `xlnx_rel_v2025.1`, kernel pinned to `v3.7.0`.
- Targets: 32-bit MicroBlaze-V `mbv32` (primary bring-up) and ARM Cortex-R52 RPU.
- Host: Linux with Vivado/Vitis 2025.1 (`source /tools/Xilinx/Vivado/2025.1/settings64.sh`), JTAG programmer attached.
- The devicetree generated from the Vivado XSA (via `xsct`/`sdtgen` + Lopper) **is** the Versal HAL — there is no monolithic Versal HAL library.

## Hard rules

- One variable per experiment. Rebuild clean (`west build -p`) when changing boards or DT.
- Trust resolved artifacts (`build/zephyr/zephyr.dts`, `build/zephyr/.config`), not source intent.
- Every confirmed bug exits the loop as a test, not just a code change.
- Treat flash/program/boot-mode as destructive — confirm before running on hardware.
