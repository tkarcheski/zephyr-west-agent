# JTAG programming & debug via xsdb

Flashing and on-chip debug go through the `xsdb` runner. These steps touch
hardware state — the CLI agent **gates** them behind confirmation.

## west flash / debug with the xsdb runner

```bash
source /tools/Xilinx/Vivado/2025.1/settings64.sh

# Build first
cd ~/zephyrproject/zephyr
west build -p -b mbv32 samples/hello_world/

# Flash over JTAG (programmer connected)
west flash --runner xsdb \
  --elf-file build/zephyr/zephyr.elf \
  --bitstream /path/to/system.bit

# Interactive debug over JTAG
west debug --runner xsdb
```

## Manual xsdb TCL session (Versal APU/RPU)

When the runner abstracts away too much, drive xsdb directly:

```tcl
# Launch:  $ xsdb
connect
ta 1                               ;# list/attach targets
# Switch boot mode if needed (JTAG boot):
source versal_change_boot_mode.tcl
# Program the PDI (contains PLM + bitstream) on Versal:
device program ./vpl_gen_fixed.pdi
# Select the core you want to run on:
targets -set -filter {name =~ "Cortex-R5 #0"}
stop
dow build/zephyr/zephyr.elf        ;# download the ELF
con                                ;# continue
```

Notes:
- On Versal the PL/PLM is loaded via a **PDI** (`device program *.pdi`), not a
  bare `.bit`. `--bitstream` for `west flash` may map to PDI programming
  depending on the design; for hand sessions program the PDI explicitly.
- `versal_change_boot_mode.tcl` flips the boot mode register to JTAG so the PLM
  accepts a JTAG-loaded image.

## Multi-device / multi-core target selection

A JTAG chain (or a Versal with APU + RPU + PMC + MicroBlaze-V soft cores) exposes
many targets. Select explicitly — never assume target 1:

```tcl
targets                                   ;# print the full target tree
targets -set -filter {name =~ "MicroBlaze*"}
targets -set -filter {name =~ "Cortex-R52*#0"}
```

For `west`:

```bash
west flash --runner xsdb --dev-id <jtag-cable-id> ...
west flash --context <context>            ;# disambiguate when several boards attached
```

## Common JTAG failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `no targets found` / connect fails | hw_server not running, cable not enumerated | start `hw_server`, check USB/JTAG cable, `connect` |
| ELF downloads but core never runs | wrong core selected, boot mode not JTAG | re-`targets -set` the right core; run boot-mode TCL |
| Runs but immediately faults | image linked for wrong memory/core | check `/chosen zephyr,sram`, see `versal-hal-devicetree.md` |
| PL not configured / peripherals dead | PDI/bitstream not programmed | `device program *.pdi` before `dow` |
| Silent console after run | console UART DT/pinctrl/clock | triage via `debug-loop.md` |

## Gating policy (agent)

Treat as destructive (require confirmation): `device program`, `west flash`,
`fpga`/bitstream load, boot-mode change, `rst`, erase. Treat as safe (run
freely): `connect`, `targets`/`ta` listing, `bpadd`/`bp` read, register reads,
`west debug` attach without programming.
