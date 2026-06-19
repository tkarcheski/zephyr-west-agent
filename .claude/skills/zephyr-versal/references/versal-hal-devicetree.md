# Versal HAL = the generated devicetree

There is **no monolithic Versal HAL library**. The devicetree generated from the
Vivado XSA (via `xsct`/`sdtgen` + Lopper) *is* the hardware abstraction. Zephyr's
generic driver APIs bind to peripheral instances through devicetree nodes, so
"configuring the HAL" means producing a correct devicetree for your exact PL/PS
design.

## XSA → SDT → Zephyr devicetree pipeline

```bash
# 0. Source the Xilinx environment (provides xsct, sdtgen, runners)
source /tools/Xilinx/Vivado/2025.1/settings64.sh

# 1. Export the System Device Tree (SDT) from your Vivado XSA
xsct -eval "sdtgen set_dt_param -dir my_design -xsa my_design_wrapper.xsa ; sdtgen generate_sdt"

# 2. Run Lopper to specialise the SDT for one processor into Zephyr DT
LOPPER_DTC_FLAGS="-b 0 -@" west lopper-command \
  -p microblaze_riscv_0 \          # the processor node to target
  -s my_design/system-top.dts \    # the SDT Lopper consumes
  -w ~/zephyrproject/zephyr        # workspace to write the Zephyr DT into
```

- `sdtgen` turns the bitstream's hardware description (XSA) into a System Device
  Tree describing *all* processors and peripherals.
- Lopper "prunes" that multi-core SDT down to the view for one processor
  (`-p microblaze_riscv_0`, or the RPU/APU node), emitting devicetree Zephyr can
  consume. `LOPPER_DTC_FLAGS="-b 0 -@"` keeps symbols/overlays usable.
- Re-run this whenever the PL design changes (new IP, moved base addresses,
  changed interrupts). A stale DT against a new bitstream is a top cause of
  "device not ready" / silent peripherals.

## Binding model

- A peripheral instance is a DT node with a `compatible` string, `reg` (base +
  size), `interrupts`, `clocks`, and `status`.
- Zephyr matches `compatible` to a **binding** (`dts/bindings/**/*.yaml`) which
  defines the properties; the matching **driver** (gated by a `CONFIG_*`) calls
  `DEVICE_DT_DEFINE` for each `okay` instance.
- `/chosen` nodes wire up roles: `zephyr,console`, `zephyr,sram`,
  `zephyr,flash`, `zephyr,shell-uart`. Wrong/missing `/chosen` = no console,
  bad memory placement.

## Debugging a DT/HAL problem

1. Inspect the **resolved** DT: `build/zephyr/zephyr.dts`. This is post-overlay,
   post-Lopper truth.
2. Confirm the node is `status = "okay"`, has a sane `reg`, and a `compatible`
   that a binding exists for.
3. Confirm `/chosen` points at the right console/sram nodes.
4. If you must tweak without regenerating, layer an **overlay** rather than
   editing generated DT:

   ```dts
   /* debug.overlay */
   &uart0 {
       status = "okay";
       current-speed = <115200>;
   };
   ```

   Build with `-DEXTRA_DTC_OVERLAY_FILE=debug.overlay`.
5. If the base address / interrupt is structurally wrong, the fix belongs
   upstream of Zephyr: regenerate the SDT from the correct XSA and re-run Lopper.

## Memory placement (mbv32 vs RPU)

- `/chosen { zephyr,sram = <&…>; }` decides where the image links. On RPU vs APU
  vs mbv32 the valid memory windows differ — a `region overflowed` link error or
  an immediate fault on boot usually means the image is linked into memory the
  selected core can't run from. Cross-check the SDT's memory nodes against the
  core you targeted with Lopper `-p`.
