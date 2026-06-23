# Test engineering — Ztest + Twister + HIL

The debug loop exits by producing a test. On the QRB2210 the inner loop has two
free tiers (`native_sim` for logic, `qemu_cortex_a53` for the AArch64 path) and a
gated hardware tier over fastboot/qdl.

## Ztest anatomy

```c
#include <zephyr/ztest.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>

struct uart_fixture { const struct device *uart; };

static void *uart_setup(void)
{
	static struct uart_fixture fix;
	fix.uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
	return &fix;
}

ZTEST_SUITE(geni_uart_contract, NULL, uart_setup, NULL, NULL, NULL);

ZTEST_F(geni_uart_contract, test_device_is_ready)
{
	zassert_true(device_is_ready(fixture->uart),
		     "GENI console not ready — check DT status, the geni-uart "
		     "driver Kconfig, and pinctrl/clock deps");
}

ZTEST(geni_uart_contract, test_poll_out_does_not_fault)
{
	const struct device *u = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
	uart_poll_out(u, 'A');   /* contract: must not fault when ready */
}
```

Key points:
- `ZTEST_SUITE(name, predicate, setup, before, after, teardown)` — `predicate`
  returns `false` to skip the whole suite where it can't run (e.g. skip a GENI
  hardware test on `native_sim`).
- `ZTEST_F` gives you `fixture->`; `ZTEST` is fixtureless.
- `zassert_*` records + continues; `zassume_*` skips; `zexpect_*` is a soft check.

## Project layout for a test

```
tests/drivers/uart_geni/
  CMakeLists.txt          # find_package(Zephyr); target_sources(app PRIVATE src/main.c)
  prj.conf                # CONFIG_ZTEST=y + the GENI driver under test
  testcase.yaml           # how Twister builds/runs/filters it
  src/main.c              # the ZTEST_SUITE / ZTEST cases
  boards/qrb2210_rb1.overlay   # board-specific DT for the test (optional)
```

## `testcase.yaml` — the Twister contract

```yaml
tests:
  drivers.uart.geni.contract:
    tags: drivers uart
    harness: ztest
    platform_allow:
      - native_sim            # logic only (fixtureless cases)
      - qemu_cortex_a53       # arch path (GIC/timer/PSCI) — free
      - qrb2210_rb1           # real hardware path
    integration_platforms:
      - qemu_cortex_a53
    timeout: 60
    # Gate HW-only cases behind a fixture so CI doesn't fail them on QEMU:
    # harness_config:
    #   fixture: fixture_geni_uart
```

Useful keys: `tags` (`-t`), `platform_allow`/`platform_exclude`, `filter`
(Kconfig/DT expression), `extra_configs`, `extra_args`, `timeout`, `slow`,
`build_only`, `fixture` (only runs where the bench declares it).

## Three-speed execution

1. **`native_sim` — logic (free, fast, no gating).**

   ```bash
   west build -b native_sim tests/drivers/uart_geni && ./build/zephyr/zephyr.exe
   ./scripts/twister -p native_sim -T tests/drivers/uart_geni
   ```

2. **`qemu_cortex_a53` — the AArch64 path (free).** Proves GIC/timer/PSCI/SMP
   logic without a board. Make this the `integration_platforms` default.

   ```bash
   ./scripts/twister -p qemu_cortex_a53 -T tests/
   ```

3. **Hardware-in-the-loop — the outer loop (gated).** Promote to `qrb2210_rb1`
   over fastboot once QEMU is green. There is no in-tree fastboot Twister runner,
   so drive HIL through a custom runner or a `hardware-map.yaml` whose runner
   wraps `fastboot boot` (see `boot-flash-fastboot.md` for the gating policy):

   ```bash
   ./scripts/twister -p qrb2210_rb1 \
     --device-testing --hardware-map map.yaml -T tests/
   ```

## Coverage

```bash
./scripts/twister -p native_sim -T tests/ --coverage \
  --coverage-tool gcovr --coverage-formats html,xml
# Report lands in twister-out/coverage/
```

Measure coverage on `native_sim`; use QEMU + HIL to confirm *behaviour*, not
coverage.

## Fault injection / flakiness

For timing/concurrency bugs (likely with SMP + interrupts on the A53): repeat
cases under load (`CONFIG_ZTEST_STRESS`), enable `CONFIG_ASSERT=y` +
`CONFIG_ASSERT_LEVEL=2` in test builds so contract violations fault loudly, and
run N times in CI to catch SMP races before the bench.

## Rules

- Every test states, in its assert message, *what hardware/config fact it
  proves* — so a failure is self-diagnosing.
- A hardware-only test must be gated behind a `fixture:` so QEMU/`native_sim` CI
  doesn't report it failing.
- Prefer many small `ZTEST` cases over one big one — Twister reports per-case.
- The regression test for a bug must fail on the *pre-fix* tree. Verify that
  before you trust it.
