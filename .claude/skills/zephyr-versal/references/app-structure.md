# Application structure

A Zephyr application is the build entry point that pulls in the kernel, drivers,
and your board's devicetree.

```
my_app/
  CMakeLists.txt          # find_package(Zephyr) + sources
  prj.conf                # baseline Kconfig requests
  src/main.c              # entry point
  boards/                 # per-board overlays & extra config
    mbv32.overlay
    mbv32.conf
  Kconfig                 # (optional) app-specific symbols
  app.overlay             # (optional) board-agnostic DT additions
```

## CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(my_app)

target_sources(app PRIVATE src/main.c)
```

## prj.conf — request, don't assume

```conf
CONFIG_GPIO=y
CONFIG_SERIAL=y
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=3
```

Remember the resolved truth lives in `build/zephyr/.config`. A request with an
unmet `depends on` is dropped silently — always verify (see `debug-loop.md`).

## Config layering (most → least specific wins via order)

```bash
west build -b mbv32 my_app -- \
  -DEXTRA_CONF_FILE="debug.conf" \
  -DEXTRA_DTC_OVERLAY_FILE="debug.overlay"
```

- `prj.conf` is the base; `boards/<board>.conf` auto-applies for that board.
- `EXTRA_CONF_FILE` adds experiment fragments without touching `prj.conf`.
- `EXTRA_DTC_OVERLAY_FILE` and `boards/<board>.overlay` add devicetree.

## src/main.c — device acquisition pattern

```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>

#define LED0 DT_ALIAS(led0)
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0, gpios);

int main(void)
{
	if (!gpio_is_ready_dt(&led)) {
		return -ENODEV;   /* DT node disabled or driver not built */
	}
	gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
	while (1) {
		gpio_pin_toggle_dt(&led);
		k_msleep(500);
	}
	return 0;
}
```

The `_is_ready` guard is the in-code mirror of the `device_is_ready()` decision
tree in `debug-loop.md`. If it returns false, debug the devicetree/Kconfig, not
the C.

## Build / run cheatsheet

```bash
west build -p -b mbv32 my_app           # pristine build
west build -b native_sim my_app && ./build/zephyr/zephyr.exe   # host run
west build -t menuconfig                 # explore resolved Kconfig interactively
west build -t rom_report                 # where the image's bytes went
```
