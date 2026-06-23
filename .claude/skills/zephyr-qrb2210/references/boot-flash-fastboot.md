# Loading firmware — fastboot, qdl/EDL, and JTAG

There is no xsdb/PDI here. The QRB2210 boots through the Qualcomm chain and is
loaded over **fastboot** (high level) or **qdl/EDL** (low level, recovery).
On-chip debug is over **JTAG** (Lauterbach T32 or OpenOCD). All of these perturb
or rewrite the board — the agent **gates** them.

## The boot chain (so you know where a hang lives)

```
PBL (ROM) → SBL/XBL (UEFI/EDK2) → TZ (TrustZone) + Hyp → ABL (LinuxLoader.efi, fastboot)
                                                            └─→ boot image (kernel + DTB)
```

RB1 is **eMMC**; it cannot boot UEFI straight from flash, so the boot partition
holds an Android boot image. To run Zephyr you put `zephyr.bin` where the
"kernel" goes. ABL jumps to it per the arm64 boot protocol (with a DTB pointer in
`x0` — which Zephyr ignores, since its devicetree is compiled in).

## Model A: package Zephyr as a boot image and `fastboot boot`

The fast inner loop on hardware is a **transient** RAM boot — nothing on eMMC
changes:

```bash
# 1. Build for the board (see board-porting.md for the port itself)
west build -p -b qrb2210_rb1 samples/hello_world

# 2. Wrap zephyr.bin in an Android boot image.
#    base/offset/pagesize MUST match the device — verify with `fastboot getvar all`.
scripts/mkbootimg-zephyr.sh build/zephyr/zephyr.bin zephyr-boot.img

# 3. Transient boot (RAM only — GATED). Requires an UNLOCKED bootloader.
fastboot boot zephyr-boot.img
```

- The boot-image **base + kernel_offset** must land `zephyr.bin` at Zephyr's link
  address (`CONFIG_SRAM_BASE_ADDRESS`, DRAM base `0x80000000`). A mismatch =
  dead core. This is the single most common Model-A boot failure — confirm over
  JTAG (`debug-loop.md`, "dead before console").
- A **fused/locked/secure-boot** device rejects an unsigned image. Bring up on an
  **unlocked** dev kit; signing is a separate, later concern.
- To make it persistent (also GATED, rewrites the OS boot partition):
  `fastboot flash boot zephyr-boot.img`.

## qdl / EDL — the low-level firehose path (recovery & full flash)

When fastboot is unavailable (bricked, blank eMMC) or you must rewrite the
partition layout, use **Emergency Download (EDL)** + the firehose programmer:

```bash
# Put the board in EDL (boot-mode strap / key combo / `fastboot oem edl`), then:
qdl --allow-missing --storage emmc \
    prog_firehose_ddr.elf rawprogram*.xml patch*.xml
```

`prog_firehose_ddr.elf` is the signed flashing program (from the Qualcomm BSP for
*this* SoC), `rawprogram*.xml`/`patch*.xml` define the partition image set.
This rewrites eMMC — treat it as the most destructive operation here.

## JTAG debug (T32 / OpenOCD)

Use JTAG for "dead before console" triage — read `PC`, `CurrentEL`, GIC/timer
registers, set breakpoints at `__start`:

```
; Lauterbach T32 sketch
SYStem.CPU CORTEXA53
SYStem.Up
Data.LOAD.Elf build/zephyr/zephyr.elf /NoCODE   ; symbols only if loaded by fastboot
Break.Set __start
Go
```

OpenOCD with a generic CMSIS-DAP/J-Link works for halt/step if you have a config
for the DAP; on production boards JTAG may be fused off.

## Common load/boot failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `fastboot boot` errors / "not allowed" | locked/secure bootloader | use an unlocked dev kit; or sign the image |
| Image accepted, core dead, no console | load/link address mismatch, wrong EL | align boot-image base with link base; check `CurrentEL` over JTAG |
| Hang right after first tick | GICv3/timer not wired | verify timer freq + GIC init (`board-porting.md`) |
| Only one core runs | PSCI/SMP wiring | check `enable-method`, PSCI IDs, `CONFIG_SMP` |
| Console silent though running | no GENI driver / wrong UART / clock | `qcm2290-hal-devicetree.md` |
| `qdl` stalls / `no device` | not in EDL, wrong firehose, USB | re-enter EDL, use this SoC's `prog_firehose_ddr.elf` |

## Gating policy (agent)

Treat as **destructive** (require confirmation): `qdl`/firehose flashing,
`fastboot flash`, `fastboot erase`, `fastboot boot` (transient but perturbs the
running system), `fastboot oem edl`/boot-mode change, `fastboot reboot`/reset,
and Twister `--device-testing`. Treat as **safe** (run freely): `fastboot
devices`, `fastboot getvar …`, JTAG attach/register reads/breakpoints without
download, serial-console *reads*, and all host builds (`native_sim`,
`qemu_cortex_a53`).
