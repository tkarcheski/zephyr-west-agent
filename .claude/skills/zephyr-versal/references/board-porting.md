# Adding / porting a board

A board needs both a **software defaults** half (Kconfig) and a **hardware
description** half (devicetree). For Versal the DTS is typically *regenerated*
from the XSA-derived system devicetree rather than hand-authored.

```
boards/<vendor>/<board>/
  board.yml                 # board + SoC identity, revisions
  Kconfig.<board>           # board-level Kconfig hook
  <board>_defconfig         # default Kconfig for the board
  <board>.dts               # the hardware description (often Lopper-generated)
  <board>-pinctrl.dtsi      # pin mux (optional, often included by the .dts)
  board.cmake               # runner wiring (e.g. xsdb) (optional)
  support/                  # runner helper files, e.g. xsdb TCL (optional)
  doc/index.rst             # board docs (optional)
```

## board.yml

```yaml
board:
  name: <board>
  vendor: amd
  socs:
    - name: versal            # or the mbv soft-core SoC name
```

## Kconfig.<board> + <board>_defconfig

```kconfig
# Kconfig.<board>
config BOARD_<BOARD>
	select SOC_<SOC>
```

```conf
# <board>_defconfig  — minimal sane defaults
CONFIG_CONSOLE=y
CONFIG_SERIAL=y
CONFIG_GPIO=y
```

## The DTS — regenerate, don't hand-write (Versal)

For Versal, produce `<board>.dts` from the System Device Tree:

1. `sdtgen` the XSA → SDT (see `versal-hal-devicetree.md`).
2. Lopper `-p <processor>` to specialise it into a Zephyr-shaped DT.
3. Drop the result in as `<board>.dts` (add `/chosen`, aliases, and any
   board-level fixups via a small included `.dtsi` rather than editing the
   generated body — keeps regeneration clean).

Hand-authoring is reserved for stable, non-PL boards; on a PL design the DT must
track the bitstream.

## Wiring the runner (support/ + board.cmake)

```cmake
# board.cmake
board_runner_args(xsdb "--elf-file=${PROJECT_BINARY_DIR}/zephyr/zephyr.elf")
include(${ZEPHYR_BASE}/boards/common/xsdb.board.cmake)
```

Put board-specific xsdb TCL (boot-mode, PDI path) under `support/` and reference
it from the runner args so `west flash`/`west debug` "just work" for the board.

## Verify the port

```bash
west boards | grep <board>                 # board is discovered
west build -p -b <board> samples/hello_world
grep -E 'CONFIG_BOARD=|CONFIG_SOC=' build/zephyr/.config   # identity resolved
```

Then promote: a `samples/hello_world` boot + a console-UART Ztest on the new
board (see `test-engineering.md`) is the minimum bar for "ported".
