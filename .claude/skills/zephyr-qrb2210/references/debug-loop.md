# Debug loop — triage methodology (AArch64 / QCM2290)

Triage converts a symptom into one falsifiable hypothesis, then runs the smallest
experiment that proves or kills it. On the QRB2210 the most expensive mistake is
debugging C when the real fault is architectural (exception level, GIC, timer,
link address) or devicetree.

## Step 1 — read the resolved truth, not the source intent

`prj.conf`, `*.overlay`, and `Kconfig.*` are *requests*. The build resolves them.
Diff intent against what actually landed:

- **`build/zephyr/.config`** — resolved Kconfig. If `CONFIG_FOO=y` isn't here,
  it's not in the firmware. A symbol is dropped silently when its `depends on` is
  unmet (e.g. a UART driver that needs `CONFIG_PINCTRL` or a clock controller).
- **`build/zephyr/zephyr.dts`** — fully resolved devicetree. A node that is
  `status = "disabled"` or absent binds no driver. Overlays that don't match an
  existing node by label/path are ignored silently.
- **`build/zephyr/include/generated/zephyr/devicetree_generated.h`** — what the
  `DT_*` macros actually expand to.

Quick checks (or run `scripts/triage.sh build` for all of them at once):

```bash
grep -E 'CONFIG_(BOARD|SOC)=' build/zephyr/.config         # what did I build for?
grep -E 'CONFIG_(GIC|ARM_ARCH_TIMER|PSCI|SMP|ARM64)' build/zephyr/.config
grep -A3 'chosen {' build/zephyr/zephyr.dts                # console/sram wiring
grep -B1 'status = "okay"' build/zephyr/zephyr.dts | grep '@'
```

## Step 2 — classify the symptom

| Symptom | Most likely class | First reference |
| --- | --- | --- |
| CMake/Kconfig error before compile | Kconfig dependency / missing fragment | this doc + `app-structure.md` |
| Link error / `region overflowed` | linker/memory, `/chosen zephyr,sram`, wrong DRAM base | `qcm2290-hal-devicetree.md` |
| Builds, loads, but **totally silent** | no GENI console driver, wrong UART, pinctrl/clock | `qcm2290-hal-devicetree.md`, `board-porting.md` |
| Loads but never reaches `main` (dead before console) | wrong entry/link address, wrong exception level, MMU | `board-porting.md`, `boot-flash-fastboot.md` |
| `device_is_ready()` == false | node `disabled`, driver Kconfig off, init-priority | this doc |
| Boots, then hangs at first interrupt/tick | GICv3 not initialised, timer freq/PPI wrong | `board-porting.md` |
| Only core 0 runs; SMP cores never start | PSCI method/IDs, `enable-method`, `CONFIG_SMP` | `board-porting.md` |
| Works on `qemu_cortex_a53`, fails on HW | silicon-specific: clock/pinctrl/GENI/load-address | `boot-flash-fastboot.md` |

## Step 3 — the "dead before console" decision tree (AArch64-specific)

The classic A53 first-light failure is *no output at all*. You cannot `printk`
your way out — use JTAG/T32 (or QEMU first). Walk it in order:

1. **Is it even my image running?** Attach JTAG, read `PC`/`ELR_ELx`. If the core
   is in TZ/PLM or looping in the bootloader, the handoff/load address is wrong —
   see `boot-flash-fastboot.md` (boot image base vs Zephyr link base).
2. **What exception level am I in?** Read `CurrentEL`. Zephyr must enter at the EL
   it was built for; an EL mismatch faults immediately. Confirm against how ABL
   left the core.
3. **Did the MMU/early init run?** Break at `__start` / `z_arm64_mmu_init`. A bad
   MMU region (peripheral range not mapped device-nGnRE) faults on the first
   peripheral access — including the UART.
4. **Is the console node real?** Only now is it a *console* problem: check
   `/chosen zephyr,console` resolves to an `okay` UART with a driver
   (`device_is_ready()` tree below).

## Step 4 — the `device_is_ready()` decision tree

1. Node present **and** `status = "okay"` in `build/zephyr/zephyr.dts`?
   - No → fix the DT (port it correctly or layer an overlay), see
     `qcm2290-hal-devicetree.md`. Nothing else matters until it's enabled.
2. Driver's Kconfig selected in `.config` (e.g. `CONFIG_SERIAL=y` plus the GENI
   UART symbol you added)?
   - No → add the fragment; check its `depends on` chain (PINCTRL, CLOCK_CONTROL).
3. Does the `compatible` match a binding Zephyr has?
   - No → for GENI there is **no upstream binding/driver** — you must add both
     (`dts/bindings/serial/qcom,geni-uart.yaml` + a driver). See `board-porting.md`.
4. Are its dependencies (clock controller, pinctrl, GIC) initialised *before* it?
   - No → init-priority ordering. Bump `CONFIG_*_INIT_PRIORITY` or fix the
     `clocks`/`pinctrl-0` reference.

## Step 5 — make it a one-variable experiment

```bash
# Kconfig experiment — additive fragment, never edit .config
echo 'CONFIG_LOG_BACKEND_UART=n' > debug.conf
echo 'CONFIG_LOG_MODE_MINIMAL=y' >> debug.conf
west build -p -b qrb2210_rb1 app -- -DEXTRA_CONF_FILE=debug.conf

# Devicetree experiment — overlay, never edit the generated DT
cat > debug.overlay <<'EOF'
&uart_dbg { status = "okay"; current-speed = <115200>; };
EOF
west build -b qrb2210_rb1 app -- -DEXTRA_DTC_OVERLAY_FILE=debug.overlay
```

Rebuild with `-p` whenever you change board/SoC/DT, or a stale CMake cache lies.

## Step 6 — bisect when the cause is non-obvious

- **Platform bisect:** prove the logic on `native_sim`, then the arch path on
  `qemu_cortex_a53`, *then* hardware. A bug that reproduces on QEMU is not
  silicon-specific — debug it there for free.
- **Config bisect:** start from `samples/hello_world` on `qemu_cortex_a53`; add
  your deltas one at a time until it breaks.
- **DT bisect:** disable peripherals in the overlay until boot succeeds, then
  re-enable one at a time.

## Step 7 — exit as a test

A bug isn't fixed until a test would have caught it. Convert the proven
hypothesis into a Ztest (logic/driver-contract) or a Twister scenario (board/HIL)
— see `test-engineering.md` — verify it fails on the pre-fix tree, then apply the
production fix and watch it pass.
