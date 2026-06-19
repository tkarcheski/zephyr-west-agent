#!/usr/bin/env sh
# triage.sh — dump the RESOLVED truth of a Zephyr build for fast debugging.
#
# Usage: triage.sh [BUILD_DIR]   (default: build)
#
# Prints the facts the debug loop (references/debug-loop.md) starts from:
# the resolved board/SoC, the /chosen wiring, and which devicetree nodes are
# actually enabled — so you compare against intent instead of guessing.
set -eu

BUILD="${1:-build}"
CONF="$BUILD/zephyr/.config"
DTS="$BUILD/zephyr/zephyr.dts"

if [ ! -f "$CONF" ] || [ ! -f "$DTS" ]; then
	echo "No resolved artifacts under '$BUILD/'. Run 'west build' first." >&2
	exit 1
fi

echo "== Identity (build/zephyr/.config) =="
grep -E '^CONFIG_(BOARD|SOC)=' "$CONF" || echo "  (board/soc not found)"

echo
echo "== /chosen wiring (build/zephyr/zephyr.dts) =="
awk '/chosen \{/{f=1} f{print "  " $0} /\};/{if(f)exit}' "$DTS" || true

echo
echo "== Enabled vs disabled nodes =="
ok=$(grep -c 'status = "okay"' "$DTS" || true)
dis=$(grep -c 'status = "disabled"' "$DTS" || true)
echo "  okay: $ok    disabled: $dis"

echo
echo "== Disabled nodes (candidates for an overlay enabling them) =="
grep -nB1 'status = "disabled"' "$DTS" | grep -E '@|disabled' | head -40 || \
	echo "  (none)"

echo
echo "Next: confirm the peripheral you expect is 'okay' and its driver Kconfig"
echo "is set; see references/debug-loop.md (device_is_ready decision tree)."
