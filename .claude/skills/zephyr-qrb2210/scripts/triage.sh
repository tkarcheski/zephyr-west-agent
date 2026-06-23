#!/usr/bin/env sh
# triage.sh — dump the RESOLVED truth of a Zephyr build for fast QRB2210 debugging.
#
# Usage: triage.sh [BUILD_DIR]   (default: build)
#
# Prints the facts the debug loop (references/debug-loop.md) starts from: the
# resolved board/SoC, the AArch64 arch wiring (GIC / generic timer / PSCI / SMP),
# the /chosen console+sram, whether a GENI console node is enabled, and which
# devicetree nodes are actually enabled — so you compare against intent instead
# of guessing.
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
echo "== AArch64 arch wiring (build/zephyr/.config) =="
grep -E '^CONFIG_(ARM64|CPU_CORTEX_A53|GIC_V3|GIC_V2|ARM_ARCH_TIMER|PM_CPU_OPS_PSCI|SMP|MP_MAX_NUM_CPUS|SRAM_BASE_ADDRESS)=' \
	"$CONF" || echo "  (none found — is this an AArch64 build?)"

echo
echo "== /chosen wiring (build/zephyr/zephyr.dts) =="
awk '/chosen \{/{f=1} f{print "  " $0} /\};/{if(f)exit}' "$DTS" || true

echo
echo "== Console / GENI sanity =="
if grep -qE 'qcom,geni-(debug-)?uart' "$DTS"; then
	echo "  GENI UART node present:"
	grep -nE 'qcom,geni-(debug-)?uart' "$DTS" | sed 's/^/    /'
else
	echo "  NO GENI UART node in resolved DT — no console driver will bind."
	echo "  (See references/qcm2290-hal-devicetree.md + board-porting.md.)"
fi

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
echo "is set; for a dead/silent board walk the 'dead before console' tree in"
echo "references/debug-loop.md (entry/exception-level/MMU before console)."
