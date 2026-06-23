---
name: zephyr-qrb2210
description: >-
  Bring-up, debug, and test-engineering loop for Zephyr RTOS on the Qualcomm
  QRB2210 / QCM2290 (Robotics RB1) — a quad Cortex-A53 (AArch64) IoT SoC. Covers
  the three real execution models (Zephyr on the A53 application cores, AMP with
  Qualcomm Linux over OpenAMP/RPMsg, and the companion-MCU split), porting an
  AArch64 SoC/board (GICv3, ARM generic timer, PSCI/SMP, GENI/QUP serial), and
  loading firmware over fastboot / qdl (EDL) instead of JTAG. Use for QRB2210
  bring-up, a silent GENI console, an AArch64 boot hang, devicetree ported from
  the mainline Linux QCM2290 DT, or Ztest/Twister on the A53. Triggers:
  "qrb2210", "qcm2290", "robotics rb1", "zephyr on cortex-a53", "aarch64
  bring-up", "geni uart silent", "fastboot boot zephyr", "qdl firehose", "edl
  mode", "gicv3 / generic timer / psci hang", "qcom devicetree port", "openamp
  rpmsg qualcomm".
---

# Zephyr on Qualcomm QRB2210 (QCM2290) — Bring-up, Debug & Test Loop

This skill turns a vague symptom ("it doesn't boot", "the console is silent",
"`device_is_ready()` is false") on the **Qualcomm QRB2210 / QCM2290** into a
disciplined experiment loop that converges on a root cause plus a regression
test. The QRB2210 is the Robotics RB1 SoC: a **quad-core Cortex-A53 (ARMv8-A /
AArch64)** application processor with an Adreno 702 GPU and a Hexagon DSP — *not*
a microcontroller and *not* an FPGA.

> **There is no upstream Zephyr board for the QRB2210.** Running Zephyr here is a
> **port/bring-up effort**, not a `west build -b qrb2210_rb1`. The closest
> in-tree anchor is `qemu_cortex_a53` (AArch64, GICv3, ARM generic timer, PSCI,
> SMP). This is the analog of the AMD Versal flow's "the DT *is* the HAL", but
> with the Qualcomm toolchain (fastboot/qdl) replacing Vivado/Lopper/xsdb.

## Step 0 — pick the execution model first (this changes everything)

Before any build, decide **where Zephyr runs**. Read `references/execution-models.md`.

| Model | Zephyr runs on | Use when |
| --- | --- | --- |
| **A53-native** (primary) | the QRB2210 Cortex-A53 cores, replacing/preempting Linux | you need Zephyr *on the SoC*; bare-metal RTOS bring-up |
| **AMP** | a subset of A53 cores under Qualcomm Linux, via remoteproc + OpenAMP/RPMsg | Linux owns the system; Zephyr handles a real-time slice |
| **Companion-MCU** | an *external* MCU wired to the QRB2210 (UART/SPI/I2C/CAN) | production robotics: Linux = brain, MCU = hard-real-time limbs |

The Hexagon DSP and Adreno are **not** Zephyr targets — don't plan to run Zephyr
on them.

## The loop

Work one hypothesis at a time. Never change two variables in the same build.

1. **Triage** — collect the symptom and the ground truth. Read, in order:
   `west build` output, `build/zephyr/zephyr.dts` (the *resolved* devicetree),
   `build/zephyr/.config` (the *resolved* Kconfig), and the serial console /
   JTAG (T32) state. Resolved artifacts are truth; `prj.conf` and overlays are
   only *requests*. See `references/debug-loop.md`.
2. **Hypothesize** — name one cause: Kconfig symbol unset, DT node
   `disabled`/missing, no GENI console driver, wrong exception level, GICv3 not
   wired, generic-timer frequency wrong, PSCI/SMP secondary-core failure,
   image linked for the wrong physical base, or MMU region missing.
3. **Experiment** — the *smallest* change that confirms or kills it: a focused
   **Ztest** (`references/test-engineering.md`), a **Kconfig fragment**
   (`-DEXTRA_CONF_FILE=debug.conf`, never edit `.config`), or a **DT overlay**
   (`-DEXTRA_DTC_OVERLAY_FILE=debug.overlay`, never edit generated DT).
4. **Build & run** — `native_sim` first for logic, `qemu_cortex_a53` for the
   AArch64/GIC/timer/PSCI path (fast, free), then real hardware over
   fastboot/qdl only when the bug is silicon-specific (`references/boot-flash-fastboot.md`).
5. **Observe** — compare actual output to what the experiment encoded. If
   inconclusive, the experiment was too big — shrink it.
6. **Converge** — capture the proven cause as a permanent Ztest / Twister
   scenario so it can't regress, then apply the real fix and re-run.

## Routing — read the reference for the phase you're in

| You are… | Read |
| --- | --- |
| Deciding where Zephyr runs (A53 / AMP / companion-MCU) | `references/execution-models.md` |
| Triaging any failure | `references/debug-loop.md` |
| Porting the SoC/board (GICv3, timer, PSCI, MMU, GENI console) | `references/board-porting.md` |
| Translating the QCM2290 Linux DT into a Zephyr DT | `references/qcm2290-hal-devicetree.md` |
| Loading firmware (fastboot boot, qdl/EDL firehose, JTAG/T32) | `references/boot-flash-fastboot.md` |
| Setting up / repairing the west workspace, AArch64 SDK | `references/west-workspace.md` |
| Scaffolding an app (`CMakeLists.txt`, `prj.conf`, overlays) | `references/app-structure.md` |
| Writing/structuring tests, `testcase.yaml`, coverage, HIL | `references/test-engineering.md` |
| Pre-commit, CI, VS Code, dev QoL | `references/devops-qol.md` |

## Reference environment (assume an RB1 dev kit)

- Upstream Zephyr (`zephyrproject-rtos/zephyr`), kernel pinned to a known tag;
  AArch64 Zephyr SDK. No vendor fork ships QRB2210 support — you add
  `soc/qualcomm/qcm2290` and `boards/qualcomm/qrb2210_rb1` yourself.
- SoC: QCM2290 — 4× Cortex-A53, **GICv3** (`arm,gic-v3`), ARM generic timer
  (`arm,armv8-timer`), PSCI via SMC (`arm,psci-1.0`), peripherals behind the
  **GENI/QUP** serial-engine block (`qcom,geni-se-qup` → `qcom,geni-uart` /
  `qcom,geni-debug-uart`), TLMM pinctrl (`qcom,qcm2290-tlmm`). DRAM base
  `0x80000000`.
- Host: Linux with `fastboot`, `qdl`, and the Android boot-image tools
  (`mkbootimg`/`abootimg`); optionally a JTAG probe driven by Lauterbach T32 or
  OpenOCD. The board's boot chain is PBL → XBL → TZ/Hyp → ABL (fastboot).
- The **hardware truth** is the mainline Linux QCM2290 devicetree
  (`arch/arm64/boot/dts/qcom/qcm2290.dtsi` + `qrb2210-rb1.dts`). You *transcribe*
  it into a Zephyr DT — there is no Lopper/XSA generator here.

## Hard rules

- One variable per experiment. Rebuild clean (`west build -p`) when changing
  board, SoC, or DT.
- Trust resolved artifacts (`build/zephyr/zephyr.dts`, `build/zephyr/.config`),
  not source intent — and trust JTAG/T32 register state over assumptions about
  exception level and GIC/timer wiring.
- Every confirmed bug exits the loop as a test, not just a code change.
- Treat `qdl`/firehose, `fastboot flash`/`erase`, `fastboot boot`, boot-mode
  (EDL) change, and reset as **destructive** — confirm before running on
  hardware. See the gating policy in `references/boot-flash-fastboot.md`.
- On a fused/secure-boot/locked device, an unsigned image is rejected — bring up
  on an **unlocked** dev kit first.
