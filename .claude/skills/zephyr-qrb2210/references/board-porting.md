# Porting the QCM2290 SoC + QRB2210/RB1 board (AArch64)

This is the heart of Model-A bring-up. Unlike Versal (where the DTS is
Lopper-generated) you author an AArch64 **SoC** port plus a **board**, then write
the one driver that stands between you and a console (GENI UART). Transcribe
every address/IRQ/clock from the mainline Linux DT (`qcm2290-hal-devicetree.md`)
— never invent them.

## Layout

```
soc/qualcomm/qcm2290/
  soc.yml                   # family/series/soc identity
  Kconfig.soc               # config SOC_QCM2290 + selects
  Kconfig.defconfig         # SoC default Kconfig
  qcm2290.dtsi              # CPUs, GIC, timer, PSCI, peripherals (from Linux DT)
  mmu_regions.c (or DT)     # device/normal memory map
boards/qualcomm/qrb2210_rb1/
  board.yml                 # board + SoC identity
  Kconfig.qrb2210_rb1
  qrb2210_rb1_defconfig
  qrb2210_rb1.dts           # board: /chosen, aliases, which peripherals are on
  qrb2210_rb1-pinctrl.dtsi  # (optional) TLMM mux
  board.cmake               # runner wiring (fastboot/qdl helper, optional)
dts/bindings/serial/qcom,geni-uart.yaml
drivers/serial/uart_geni.c
```

## SoC identity (soc.yml + Kconfig.soc)

```yaml
# soc.yml
family:
  - name: qualcomm
    series:
      - name: qcm2290
        socs:
          - name: qcm2290
```

```kconfig
# Kconfig.soc
config SOC_QCM2290
	bool
	select ARM64
	select CPU_CORTEX_A53
	select GIC_V3
	select ARM_ARCH_TIMER
	select HAS_PM_CPU_OPS        # PSCI for SMP secondary start
	help
	  Qualcomm QCM2290 / QRB2210 — quad Cortex-A53.
```

## The SoC `.dtsi` — the eight things that must be right

Transcribe these from `arch/arm64/boot/dts/qcom/qcm2290.dtsi`:

1. **CPUs** — four `arm,cortex-a53`, each `enable-method = "psci"`, with a
   `psci` node (`compatible = "arm,psci-1.0"; method = "smc";`).
2. **GICv3** — `compatible = "arm,gic-v3"`, the distributor + redistributor
   `reg`, `#interrupt-cells = <4>` (GICv3 uses 4 cells on Zephyr's binding —
   verify), `interrupt-controller`.
3. **Architected timer** — `arm,armv8-timer` with the four PPIs
   (secure/non-secure/virtual/hyp). Get the **clock-frequency** right or every
   `k_msleep` is wrong.
4. **Memory** — DRAM `reg = <0x0 0x80000000 …>`; reserve TZ/modem/PIL carveouts
   so Zephyr never links over them.
5. **GENI/QUP** — the `qcom,geni-se-qup` wrapper and the UART child
   (`qcom,geni-uart` / `qcom,geni-debug-uart`) with its `reg`, `interrupts`
   (`GIC_SPI …`), and `clocks`.
6. **Clocks** — for first light, a `fixed-clock` standing in for the UART's GCC
   clock (the bootloader already enabled it); add `qcom,gcc-qcm2290` later.
7. **Pinctrl** — `qcom,qcm2290-tlmm`, or omit and rely on the bootloader's mux
   until the console works.
8. **`/chosen`** (in the *board* dts) — `zephyr,console`, `zephyr,shell-uart`,
   `zephyr,sram` pointing at the debug UART and DRAM.

## SoC defconfig

```conf
# Kconfig.defconfig (sketch)
CONFIG_NUM_IRQS=...           # match the GICv3 SPI count from the DTSI
CONFIG_GIC_V3=y
CONFIG_ARM_ARCH_TIMER=y
CONFIG_SMP=y
CONFIG_MP_MAX_NUM_CPUS=4
CONFIG_SRAM_BASE_ADDRESS=0x80000000
```

## The MMU map — peripherals must be mapped device memory

AArch64 faults on the first access to an unmapped region — including the UART, so
this fault happens *before* any console output. Map DRAM as normal cached memory
and each peripheral window (GIC, GENI/QUP) as device-nGnRE. Express via the SoC's
`mmu_regions` (or `zephyr,memory-region` DT nodes). A missing peripheral mapping
is a top "dead before console" cause (`debug-loop.md`).

## The GENI UART driver (the console gate)

Zephyr has no GENI driver. Minimum viable for first light: implement
`uart_poll_out`/`uart_poll_in` against the GENI FIFO (TX FIFO + status
registers), reading the register layout from Linux's `qcom_geni_serial`. Wire it
up:

```c
/* drivers/serial/uart_geni.c — skeleton */
#define DT_DRV_COMPAT qcom_geni_uart
static int geni_poll_out(const struct device *dev, unsigned char c) { /* push to TX FIFO */ }
static const struct uart_driver_api geni_api = { .poll_out = geni_poll_out, /* … */ };
DEVICE_DT_INST_DEFINE(0, geni_init, NULL, &data, &cfg,
		      PRE_KERNEL_1, CONFIG_SERIAL_INIT_PRIORITY, &geni_api);
```

Add the matching `dts/bindings/serial/qcom,geni-uart.yaml`. Until interrupts are
trusted, keep it **polling-mode** — it isolates the console from GIC bring-up.

## Bring-up order (one variable at a time)

1. `qemu_cortex_a53` builds and runs `hello_world` → arch/Kconfig sane.
2. SoC `.dtsi` + board: `west build -p -b qrb2210_rb1 samples/hello_world` links
   at `0x80000000` with no `region overflowed`.
3. `fastboot boot` the image; over JTAG confirm it reaches `__start` (entry/EL/MMU).
4. Polling GENI `poll_out` prints a byte → **first light**.
5. Enable the architected timer + GICv3 → `k_msleep` works, interrupts fire.
6. Enable PSCI/SMP → secondary cores start (`CONFIG_MP_MAX_NUM_CPUS=4`).
7. Add pinctrl/clock drivers to drop the bootloader-state assumptions.

## Verify the port

```bash
west boards | grep qrb2210_rb1
west build -p -b qrb2210_rb1 samples/hello_world
grep -E 'CONFIG_(BOARD|SOC|GIC_V3|ARM_ARCH_TIMER|SMP)=' build/zephyr/.config
scripts/triage.sh build           # /chosen, GIC/timer/PSCI/CPU presence, console check
```

The minimum bar for "ported": `hello_world` prints over the GENI console on
hardware, plus a console-UART Ztest (`test-engineering.md`).
