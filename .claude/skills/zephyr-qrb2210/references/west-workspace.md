# West workspace — init, manifest, update, SDK

Unlike the AMD Versal flow there is **no vendor fork** to swap in — QRB2210
support does not exist upstream, so you work from a normal upstream Zephyr
workspace and add the SoC/board yourself (see `board-porting.md`). Pin the kernel
to a known-good tag so your port is reproducible.

## Full workspace setup

```bash
# Prerequisites (Ubuntu/Debian)
sudo apt install --no-install-recommends -y git cmake ninja-build gperf \
  ccache dfu-util device-tree-compiler wget python3-dev python3-pip \
  python3-setuptools python3-venv xz-utils file make gcc gcc-multilib \
  g++-multilib libsdl2-dev libmagic1
# Hardware-loading tools (host side):
sudo apt install --no-install-recommends -y fastboot android-sdk-libsparse-utils
# qdl + mkbootimg are built/obtained separately (linux-msm/qdl, mkbootimg).

# Workspace + venv
mkdir ~/zephyrproject && cd ~/zephyrproject
python3 -m venv .venv && source .venv/bin/activate
pip install west

# Upstream Zephyr, pinned
west init -m https://github.com/zephyrproject-rtos/zephyr --mr v3.7.0
west update
west zephyr-export
pip install -r zephyr/scripts/requirements.txt

# AArch64 toolchain (the SDK includes aarch64-zephyr-elf)
cd zephyr && west sdk install
```

## How the manifest resolves

- `west init -m … --mr <tag>` writes `.west/config` pointing at the manifest
  repo/revision. The manifest (`zephyr/west.yml`) lists the modules west clones
  — for QRB2210 the relevant extras are `open-amp` and `libmetal` (only if you
  use **Model B / AMP**; see `execution-models.md`).
- `west update` clones/checks-out every project at the manifest-pinned revision.
  Re-run it after any manifest change.
- There is **no** `west lopper-install` step here — the QCM2290 DT is transcribed
  from mainline Linux by hand, not generated (`qcm2290-hal-devicetree.md`).

## Where your port lives

Keep the port *in the workspace* but out of the upstream `zephyr/` tree so
`west update` stays clean — a small out-of-tree module is ideal:

```
~/zephyrproject/
  zephyr/                      # upstream, untouched
  qrb2210/                     # your module
    zephyr/module.yml          # registers board_root + soc_root
    soc/qualcomm/qcm2290/      # the SoC port
    boards/qualcomm/qrb2210_rb1/
    dts/bindings/serial/qcom,geni-uart.yaml
    drivers/serial/uart_geni.c
```

`module.yml` makes `west build -b qrb2210_rb1` discover your board without
patching upstream. Alternatively develop in-tree and upstream later.

## Common workspace failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| `west: command not found` | venv not active | `source ~/zephyrproject/.venv/bin/activate` |
| board not found | module not registered | check `qrb2210/zephyr/module.yml` board_root; `west update` |
| SDK/toolchain not found | `west sdk install` skipped / no aarch64 | re-run; check `ZEPHYR_SDK_INSTALL_DIR` |
| `open-amp` missing (Model B) | not in manifest | add the module, `west update` |
| module headers stale at build | stale workspace | `west update` then `west build -p` |

## Sanity checks

```bash
west topdir                       # confirms you're inside the workspace
west list                         # every project + pinned revision
west boards | grep qrb2210        # your board is discovered
west build -p -b qemu_cortex_a53 samples/hello_world   # arch path works before HW
```
