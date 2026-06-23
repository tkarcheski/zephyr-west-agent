# QCM2290 HAL = the devicetree (ported from mainline Linux)

As on Versal, there is **no monolithic HAL library**. Zephyr's generic driver
APIs bind to peripheral instances through devicetree nodes, so "configuring the
HAL" means producing a correct Zephyr DT for the QCM2290. Unlike Versal there is
**no Lopper/XSA generator** — the QCM2290 is a fixed-function SoC, so the
authoritative hardware description is the **mainline Linux devicetree**, which
you transcribe into Zephyr form.

## Source of truth: the mainline Linux DT

```
arch/arm64/boot/dts/qcom/qcm2290.dtsi      # the SoC: CPUs, GIC, timer, GCC, TLMM, QUP/GENI…
arch/arm64/boot/dts/qcom/qrb2210-rb1.dts   # the RB1 board: which UART/SD/USB/regulators are on
```

Read these as the spec. Copy base addresses, interrupt numbers, and clock IDs
from them — do **not** invent them. Then re-express each node in the subset of DT
that Zephyr's bindings understand.

## The load-bearing SoC nodes (verbatim compatibles)

| Function | Linux `compatible` | Zephyr status |
| --- | --- | --- |
| CPUs (×4) | `arm,cortex-a53`, `enable-method = "psci"` | supported (AArch64) |
| Interrupt controller | `arm,gic-v3` | supported (`CONFIG_GIC_V3`) |
| Architected timer | `arm,armv8-timer` | supported (`CONFIG_ARM_ARCH_TIMER`) |
| Power coordination | `arm,psci-1.0`, `method = "smc"` | supported (`CONFIG_PM_CPU_OPS_PSCI`) |
| Pin mux | `qcom,qcm2290-tlmm` | **no Zephyr driver** — port or pre-mux in bootloader |
| Serial-engine wrapper | `qcom,geni-se-qup` | **no Zephyr driver** |
| UART / debug UART | `qcom,geni-uart`, `qcom,geni-debug-uart` | **no Zephyr driver** — write one |
| Clocks | `qcom,gcc-qcm2290` (+ RPMh) | **no Zephyr driver** — see below |

> Always re-confirm the exact strings in the DTSI you build against — the SoC
> family moved to GICv3; do not assume the GIC-400/GICv2 of older MSM parts.

## What Zephyr already gives you vs what you must add

- **Free (in-tree, AArch64 core support):** GICv3, ARM generic timer, PSCI,
  SMP, MMU. These bind from standard DT nodes once your SoC `.dtsi` declares them.
- **You must add (no upstream driver):**
  - **GENI UART** — binding `dts/bindings/serial/qcom,geni-uart.yaml` + a driver.
    This is the gate to a console; do it first. The Linux `qcom_geni_serial`
    driver is your behavioural reference for the FIFO/registers.
  - **TLMM pinctrl** — or, for first light, rely on the pin mux ABL/Linux already
    applied and skip Zephyr pinctrl until the console works.
  - **GCC/RPMh clocks** — for early bring-up, treat the UART clock as
    already-on (the bootloader enabled it) with a `fixed-clock`, and add a real
    clock-control driver later.

This "lean on the bootloader's setup, replace it incrementally" approach keeps
the first-light experiment to one variable: the UART driver.

## Binding model (recap)

- A peripheral is a DT node with `compatible`, `reg` (base+size), `interrupts`
  (GICv3: `<GIC_SPI n IRQ_TYPE_LEVEL_HIGH>`), `clocks`, `pinctrl-*`, `status`.
- Zephyr matches `compatible` → a **binding** (`dts/bindings/**/*.yaml`); the
  matching **driver** (gated by `CONFIG_*`) calls `DEVICE_DT_DEFINE` per `okay`
  instance.
- `/chosen` wires roles: `zephyr,console`, `zephyr,sram`, `zephyr,shell-uart`.
  Wrong/missing `/chosen` = no console or bad memory placement.

## Memory map — get the DRAM base right

The QCM2290 DRAM base is **`0x80000000`**. Zephyr's link address
(`CONFIG_SRAM_BASE_ADDRESS`/`/chosen zephyr,sram`) and the boot-image load
address **must agree** with where the bootloader places and enters the image, or
you get `region overflowed` at link time or a dead core at boot (see
`boot-flash-fastboot.md`). Reserve carveouts (TZ, modem, etc.) — never link Zephyr
over a region the firmware owns.

## Debugging a DT/HAL problem

1. Inspect the **resolved** DT: `build/zephyr/zephyr.dts` (post-overlay truth).
2. Confirm the node is `okay`, has a sane `reg`/`interrupts` copied from the
   Linux DTSI, and a `compatible` a binding exists for.
3. Confirm `/chosen` points at the right console/sram nodes.
4. Tweak with an **overlay**, never by editing generated DT:

   ```dts
   /* debug.overlay */
   &uart_dbg {
       status = "okay";
       current-speed = <115200>;
   };
   ```

   Build with `-DEXTRA_DTC_OVERLAY_FILE=debug.overlay`.
5. If a base address / interrupt is structurally wrong, fix it at the source —
   re-check the mainline DTSI; a transcription error there poisons everything
   downstream.
