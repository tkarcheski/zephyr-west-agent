# West workspace — init, manifest, update, SDK

The AMD Versal flow uses the `Xilinx/zephyr-amd` fork on top of upstream kernel
`v3.7.0`, with Lopper for devicetree generation.

## Full workspace setup

```bash
# Prerequisites (Ubuntu/Debian)
sudo apt install --no-install-recommends -y git cmake ninja-build gperf \
  ccache dfu-util device-tree-compiler wget python3-dev python3-pip \
  python3-setuptools python3-venv xz-utils file make gcc gcc-multilib \
  g++-multilib libsdl2-dev libmagic1

# Workspace + venv
mkdir ~/zephyrproject && cd ~/zephyrproject
python3 -m venv .venv
source .venv/bin/activate
pip install west

# Initialise against upstream, then swap in the AMD fork
west init -m https://github.com/zephyrproject-rtos/zephyr --mr v3.7.0
cd ~/zephyrproject
mv zephyr zephyr.upstream
git clone https://github.com/Xilinx/zephyr-amd.git -b xlnx_rel_v2025.1 zephyr
west update
west lopper-install            # installs Lopper + system-device-tree tooling

# Toolchain SDK + Python deps
cd zephyr && west sdk install
pip install -r scripts/requirements.txt
```

## How the manifest resolves

- `west init -m … --mr v3.7.0` writes `.west/config` pointing at the manifest
  repo/revision. The manifest (`west.yml`) lists the modules (HALs, libs) west
  will clone into the workspace.
- Replacing the `zephyr/` checkout with `zephyr-amd` makes the **fork's**
  `west.yml` authoritative after the next `west update`. That is what pulls in
  the AMD-specific modules and Lopper integration.
- `west update` clones/checks-out every project at the manifest-pinned revision.
  Run it after any manifest change or fork swap.

## Common workspace failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| `west update` pulls wrong revisions | manifest still pointing at upstream | confirm `zephyr/west.yml` is the fork's; re-run `west update` |
| `west: command not found` | venv not active | `source ~/zephyrproject/.venv/bin/activate` |
| `lopper` missing | skipped `west lopper-install` | re-run it inside the venv |
| SDK/toolchain not found | `west sdk install` skipped or wrong arch | re-run; check `ZEPHYR_SDK_INSTALL_DIR` |
| Module headers missing at build | stale workspace | `west update` then `west build -p` |

## Sanity checks

```bash
west topdir          # confirms you're inside the workspace
west list            # every project + its pinned revision
west manifest --resolve | head    # the fully-resolved manifest
```
