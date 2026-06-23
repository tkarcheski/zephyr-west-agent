#!/usr/bin/env sh
# mkbootimg-zephyr.sh — wrap a Zephyr image as an Android boot image so the
# QRB2210/RB1 bootloader (ABL) can `fastboot boot` it. See
# references/boot-flash-fastboot.md.
#
# Usage: mkbootimg-zephyr.sh ZEPHYR_BIN [OUT_IMG]
#   ZEPHYR_BIN  path to build/zephyr/zephyr.bin
#   OUT_IMG     output image (default: zephyr-boot.img)
#
# DESTRUCTIVE-ADJACENT: this script only *builds* an image (safe). Booting it is
# the gated step:  fastboot boot OUT_IMG   (requires an UNLOCKED bootloader).
#
# !! The base / kernel_offset / pagesize below are STARTING POINTS for the
# !! QCM2290 (DRAM base 0x80000000). They MUST match your device — verify with
# !! `fastboot getvar all` (look for kernel/page-size/base) and your board's
# !! existing boot image. A wrong base = the core loads Zephyr at the wrong
# !! address and dies before the console (see boot-flash-fastboot.md).
set -eu

KERNEL="${1:?usage: mkbootimg-zephyr.sh ZEPHYR_BIN [OUT_IMG]}"
OUT="${2:-zephyr-boot.img}"

: "${BASE:=0x80000000}"          # QCM2290 DRAM base — VERIFY
: "${KERNEL_OFFSET:=0x00008000}" # arm64 text offset — VERIFY
: "${PAGESIZE:=4096}"            # VERIFY against fastboot getvar
: "${CMDLINE:=}"                 # Zephyr ignores the bootloader cmdline + DTB
: "${MKBOOTIMG:=mkbootimg}"      # from the Android build tools / linux-msm

if [ ! -f "$KERNEL" ]; then
	echo "kernel image not found: $KERNEL (build with 'west build' first)" >&2
	exit 1
fi
if ! command -v "$MKBOOTIMG" >/dev/null 2>&1; then
	echo "mkbootimg not found (set MKBOOTIMG=/path/to/mkbootimg)" >&2
	exit 1
fi

# ABL expects a ramdisk slot; supply an empty one. Zephyr never reads it.
RAMDISK="$(mktemp)"
trap 'rm -f "$RAMDISK"' EXIT
: > "$RAMDISK"

echo "Packaging $KERNEL -> $OUT"
echo "  base=$BASE kernel_offset=$KERNEL_OFFSET pagesize=$PAGESIZE"
"$MKBOOTIMG" \
	--kernel "$KERNEL" \
	--ramdisk "$RAMDISK" \
	--base "$BASE" \
	--kernel_offset "$KERNEL_OFFSET" \
	--pagesize "$PAGESIZE" \
	--cmdline "$CMDLINE" \
	-o "$OUT"

echo "Wrote $OUT"
echo "Next (GATED, needs an unlocked bootloader): fastboot boot $OUT"
