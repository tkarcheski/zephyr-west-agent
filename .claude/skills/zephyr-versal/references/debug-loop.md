# Debug loop — triage methodology

The goal of triage is to convert a symptom into one falsifiable hypothesis, then
run the smallest experiment that proves or kills it.

## Step 1 — read the resolved truth, not the source intent

`prj.conf`, `*.overlay`, and `Kconfig.*` are *requests*. The build resolves them.
Always diff your intent against what actually landed:

- **`build/zephyr/.config`** — the resolved Kconfig. If `CONFIG_FOO=y` is not in
  here, it is not in the firmware, no matter what `prj.conf` says. A symbol can
  be silently dropped because its `depends on` is unmet.
- **`build/zephyr/zephyr.dts`** — the fully resolved devicetree. If a node shows
  `status = "disabled"` or is absent, no driver binds to it. Overlays that don't
  match an existing node by label/path are silently ignored.
- **`build/zephyr/zephyr.dts.pre`** / the CMake `Devicetree` warnings — show
  overlay application order.
- **`build/zephyr/include/generated/zephyr/devicetree_generated.h`** — what the
  `DT_*` macros actually expand to.

Quick checks:

```bash
# Did my Kconfig request survive?
grep CONFIG_UART_XLNX build/zephyr/.config

# Is the node enabled and bound?
grep -A3 'serial@' build/zephyr/zephyr.dts

# What board/SOC did I actually build for?
grep -E 'CONFIG_BOARD=|CONFIG_SOC=' build/zephyr/.config
```

For a one-shot dump of all of the above, run the bundled helper:
`scripts/triage.sh build` (prints identity, `/chosen` wiring, and enabled vs
disabled nodes).

## Step 2 — classify the symptom

| Symptom | Most likely class | First reference |
| --- | --- | --- |
| CMake/Kconfig error before compile | Kconfig dependency / missing fragment | this doc + `app-structure.md` |
| Link error, `region overflowed`, bad placement | Linker/memory, DT `/chosen` zephyr,sram | `versal-hal-devicetree.md` |
| Builds, but no serial output at all | Console DT `/chosen`, pinctrl, clocks | `versal-hal-devicetree.md` |
| `device_is_ready()` == false | Node `disabled`, driver Kconfig off, init-priority | this doc |
| Boots then hangs/faults | Init order, stack size, IRQ/GIC, RPU vs APU placement | `jtag-xsdb.md` |
| Works on `native_sim`, fails on HW | Hardware-specific: DT/clock/pinctrl/PDI | `jtag-xsdb.md` |
| Flaky under load | Concurrency, timing, ISR latency | `test-engineering.md` (fault injection) |

## Step 3 — the `device_is_ready()` decision tree

This is the most common Versal bring-up failure. Walk it in order:

1. Is the node present **and** `status = "okay"` in `build/zephyr/zephyr.dts`?
   - No → fix the devicetree (the XSA-derived DT or an overlay), see
     `versal-hal-devicetree.md`. Stop here; nothing else matters until it's enabled.
2. Is the driver's Kconfig selected in `build/zephyr/.config`
   (e.g. `CONFIG_SERIAL=y`, `CONFIG_UART_XLNX_UARTPS=y`)?
   - No → add the fragment; check its `depends on` chain isn't blocking it.
3. Does the driver's `compatible` match a binding that Zephyr has?
   - No → the node won't get a driver. Find the right `compatible` or add a binding.
4. Is another device it depends on (clock controller, pinctrl, parent bus)
   initialised *before* it?
   - No → init-priority ordering. Bump `CONFIG_*_INIT_PRIORITY` or fix the
     `/chosen`/clock reference.

## Step 4 — make it a one-variable experiment

Encode the hypothesis as the smallest artifact:

```bash
# Kconfig experiment — additive fragment, never edit .config
echo 'CONFIG_UART_XLNX_UARTPS=y' > debug.conf
west build -p -b mbv32 app -- -DEXTRA_CONF_FILE=debug.conf

# Devicetree experiment — overlay, never edit the generated DT
cat > debug.overlay <<'EOF'
&uart0 { status = "okay"; };
EOF
west build -b mbv32 app -- -DEXTRA_DTC_OVERLAY_FILE=debug.overlay
```

Rebuild with `-p` (pristine) whenever you change board or devicetree, otherwise
stale CMake cache will lie to you.

## Step 5 — bisect when the cause is non-obvious

- **Config bisect**: start from a known-good sample (`samples/hello_world`) on the
  same board; add your config deltas one at a time until it breaks.
- **DT bisect**: disable peripherals in the overlay until boot succeeds, then
  re-enable one at a time.
- **Commit bisect**: `git bisect` across `zephyr-amd` if a previously-working tree
  regressed.

## Step 6 — exit as a test

A bug is not fixed until a test would have caught it. Convert the proven
hypothesis into a Ztest case (logic/driver-contract bugs) or a Twister scenario
(board/HIL bugs). See `test-engineering.md`. Only then apply the production fix
and re-run the new test to watch it pass.
