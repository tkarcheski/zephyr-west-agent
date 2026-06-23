# Execution models — where does Zephyr actually run?

The QRB2210 is an *application* SoC (quad Cortex-A53 + Adreno 702 GPU + Hexagon
DSP), designed to run Qualcomm Linux. "Zephyr on the QRB2210" therefore means
one of three architectures. Pick one **before** you build — it decides the boot
path, the devicetree, the memory map, and what "done" looks like.

## Model A — Zephyr on the Cortex-A53 application cores (primary)

Zephyr *is* the OS on the A53 cluster, replacing or preempting Linux. This is the
direct analog of running Zephyr on a Versal RPU/APU core, and what the rest of
this skill defaults to.

- **Boot:** the Qualcomm chain (PBL → XBL → TZ/Hyp → ABL) hands off to a boot
  image whose "kernel" is `zephyr.bin`. Load via `fastboot boot zephyr-boot.img`
  (transient) or by flashing the boot partition. See `boot-flash-fastboot.md`.
- **Arch bring-up:** AArch64 entry at the EL the bootloader leaves you in
  (commonly EL1, sometimes EL2), GICv3, ARM generic timer, PSCI/SMC for
  secondary-core (SMP) start. See `board-porting.md`.
- **Console:** a GENI UART driver you write (Zephyr has none upstream) or a
  pre-initialised debug UART / JTAG semihosting. The #1 first-light blocker.
- **Good for:** dedicated RTOS appliances, deterministic control where Linux
  latency is unacceptable, security/bring-up research.
- **Cost:** you give up Linux, the Adreno/Hexagon stacks, the camera/ISP and
  modem firmware, and Qualcomm's BSP. You own the SoC port.

## Model B — AMP: Qualcomm Linux + Zephyr via remoteproc / OpenAMP

Linux owns the system on most of the cluster; Zephyr runs a real-time slice and
talks to Linux over **RPMsg** on a shared-memory **virtio** transport, with the
firmware lifecycle managed by the Linux **remoteproc** framework.

- **Mechanism:** Linux `remoteproc` loads + starts the Zephyr image into a
  reserved memory carveout; `OpenAMP`/`rpmsg` carries messages both ways. Zephyr
  ships the `open-amp` module and `openamp_rsc_table` sample for exactly this.
- **Reality check on the DSP:** the obvious "co-processor" here is the **Hexagon
  DSP**, which **Zephyr does not target**. So AMP on the QRB2210 means hosting
  Zephyr on a *reserved A53 core* under Linux, not on the DSP. This is less
  common than DSP-AMP on parts like i.MX (HiFi4) — treat it as advanced.
- **Good for:** keeping the Linux ecosystem (networking, AI, camera) while
  carving out a low-latency RTOS partition that Linux supervises.
- **Cost:** carveout + resource-table plumbing, cache-coherency discipline on the
  shared ring buffers, and a remoteproc firmware contract to honour.

## Model C — companion-MCU split (most common in production robotics)

The QRB2210 runs Qualcomm Linux (perception, planning, connectivity); a
*separate* MCU runs Zephyr for hard-real-time work (motor control, IMU fusion,
safety I/O) and is wired to the SoC over UART/SPI/I2C/CAN.

- **Why it dominates:** the A53s + Linux are great for the "brain" but poor at
  microsecond-deterministic control; a cheap Cortex-M/R running Zephyr is ideal
  for the "limbs". Qualcomm's own reference designs follow this split (e.g.
  Qualcomm-Linux paired with an STM32 running Zephyr).
- **Zephyr side:** a normal, fully-supported Zephyr board (nRF/STM32/RP2040/…).
  No SoC port needed — the hard QRB2210-specific work disappears.
- **Integration is the work:** define the wire protocol (framing, CRC, flow
  control), the transport (UART + DMA, SPI slave, or CAN), and the contract with
  the Linux side. This is where the debug loop and tests focus.
- **Good for:** shipping products. Lowest risk, best tool support.

## Choosing

```
Need Zephyr literally executing on the QRB2210 silicon?
├─ No  → Model C (companion MCU). Stop; use a supported Zephyr board.
└─ Yes
   ├─ Must keep Qualcomm Linux running alongside? → Model B (AMP, advanced)
   └─ Zephyr owns the cores outright?             → Model A (A53-native, default)
```

When in doubt for a *product*, it's Model C. When the task is genuinely "Zephyr
on the QRB2210 itself" (research, bring-up, this skill's headline), it's Model A
— and the remaining references assume Model A unless they say otherwise.
