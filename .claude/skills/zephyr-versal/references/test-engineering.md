# Test engineering — Ztest + Twister + HIL

The debug loop exits by producing a test. This is how you write one that is
fast, isolated, and runnable both on `native_sim` and on real Versal hardware.

## Ztest anatomy

```c
#include <zephyr/ztest.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>

/* Fixture: shared, mutable state handed to every test in the suite. */
struct uart_fixture {
	const struct device *uart;
};

static void *uart_setup(void)
{
	static struct uart_fixture fix;
	fix.uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
	return &fix;          /* becomes the `fixture` arg below */
}

static void uart_before(void *f)  { ARG_UNUSED(f); /* per-test reset */ }

ZTEST_SUITE(uart_contract, NULL, uart_setup, uart_before, NULL, NULL);
/*           name           pred  setup       before      after teardown */

ZTEST_F(uart_contract, test_device_is_ready)
{
	zassert_true(device_is_ready(fixture->uart),
		     "console UART not ready — check DT status + driver Kconfig");
}

ZTEST(uart_contract, test_poll_out_does_not_fault)
{
	const struct device *u = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
	uart_poll_out(u, 'A');     /* contract: must not fault when ready */
}
```

Key points:
- `ZTEST_SUITE(name, predicate, setup, before, after, teardown)` — `predicate`
  returns `false` to skip the whole suite on a platform where it can't run
  (e.g. skip a JTAG test on `native_sim`).
- `ZTEST_F` gives you `fixture->`; `ZTEST` is fixtureless.
- Assertions: `zassert_*` records the failure and continues the function;
  `zassume_*` skips the test if unmet; `zexpect_*` is a soft check.
- Parameterize by looping over a table inside one `ZTEST`, or generate suites
  with `ZTEST_SUITE` per variant.

## Project layout for a test

```
tests/drivers/uart/
  CMakeLists.txt          # find_package(Zephyr); target_sources(app PRIVATE src/main.c)
  prj.conf                # CONFIG_ZTEST=y plus the driver under test
  testcase.yaml           # how Twister builds/runs/filters it
  src/main.c              # the ZTEST_SUITE / ZTEST cases
  boards/mbv32.overlay    # board-specific DT for the test (optional)
```

## `testcase.yaml` — the Twister contract

```yaml
tests:
  drivers.uart.contract:
    tags: drivers uart
    harness: ztest                 # parse ZTEST pass/fail from console
    platform_allow:
      - native_sim                 # fast logic path
      - mbv32                      # real hardware path
    integration_platforms:
      - native_sim
    timeout: 60
    extra_args: EXTRA_CONF_FILE="debug.conf"
    # harness_config / fixture: gates HW-only tests behind a named fixture
    # so they run only when the bench advertises it:
    # harness: console
    # fixture: fixture_jtag
```

Useful keys: `tags` (select with `-t`), `platform_allow`/`platform_exclude`,
`filter` (Kconfig/DT expression), `extra_configs`, `extra_args`, `timeout`,
`slow`, `build_only`, `fixture` (only runs where the bench declares the
fixture via `--device-testing`/hardware map).

## Two-speed execution

1. **`native_sim` — the inner loop (free, fast, no gating).** Run logic,
   state-machine, and driver-contract tests on the host:

   ```bash
   west build -b native_sim tests/drivers/uart && ./build/zephyr/zephyr.exe
   # or via Twister:
   ./scripts/twister -p native_sim -T tests/drivers/uart
   ```

2. **Hardware-in-the-loop — the outer loop (gated).** Promote to real Versal via
   xsdb once logic is proven. See `jtag-xsdb.md` for runner details:

   ```bash
   ./scripts/twister -p mbv32 \
     --west-runner xsdb \
     --device-testing \
     --device-serial /dev/ttyUSB0 \
     --west-flash="--bitstream=/path/to/system.bit"
   ```

   For a persistent bench, prefer a `hardware-map.yaml`
   (`./scripts/twister --generate-hardware-map map.yaml`, then
   `--device-testing --hardware-map map.yaml`) so serial/runner/fixtures are
   declared per board instead of on the command line.

## Coverage

```bash
# Host coverage on native_sim
./scripts/twister -p native_sim -T tests/ --coverage \
  --coverage-tool gcovr --coverage-formats html,xml
# Report lands in twister-out/coverage/
```

On-target coverage is possible but expensive; keep coverage measurement on
`native_sim` and use HIL runs to confirm behaviour, not coverage.

## Fault injection / flakiness

For timing- and concurrency-class bugs the debug loop turned up:
- add stress with `CONFIG_ZTEST_STRESS` patterns (repeat the case under load),
- inject delays/IRQ pressure to expose ISR-latency races,
- use `CONFIG_ASSERT=y` + `CONFIG_ASSERT_LEVEL=2` in test builds so contract
  violations fault loudly instead of corrupting silently,
- run the case N times in CI (`--retry-failed`, or a loop) to catch flakiness
  before it reaches the bench.

## Test-engineering rules

- Every test must state, in its assert message, *what hardware/config fact it
  proves* — so a failure is self-diagnosing.
- A test that only runs on hardware must be gated behind a `fixture:` so CI
  doesn't report it as failing on `native_sim`.
- Prefer many small `ZTEST` cases over one big one — Twister reports per-case.
- The regression test for a bug must fail on the *pre-fix* tree. Verify that
  before you trust it.
