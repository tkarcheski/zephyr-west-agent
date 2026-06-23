# DevOps & developer QoL

Keep the inner loop fast and the tree clean so debugging effort goes to bugs, not
environment drift. The two free tiers (`native_sim`, `qemu_cortex_a53`) are your
gate; hardware runs serialise on one board and stay off the PR path.

## Pre-commit (hygiene + checkpatch)

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: mixed-line-ending
  - repo: local
    hooks:
      - id: checkpatch
        name: zephyr checkpatch
        entry: ./zephyr/scripts/checkpatch.pl --no-tree -
        language: system
        types: [c]
```

```bash
pip install pre-commit && pre-commit install
pre-commit run --all-files
```

Run the same compliance CI runs before pushing — important for an out-of-tree
SoC/board port you intend to upstream:

```bash
python3 ./zephyr/scripts/ci/check_compliance.py -c upstream/main..HEAD
```

## .editorconfig

```ini
root = true
[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
trim_trailing_whitespace = true
[*.{c,h}]
indent_style = tab
indent_size = 8
[*.{py,yml,yaml,rst}]
indent_style = space
indent_size = 4
```

## VS Code

`.vscode/tasks.json` for one-key build/run/test:

```json
{
  "version": "2.0.0",
  "tasks": [
    { "label": "west build qrb2210_rb1", "type": "shell",
      "command": "west build -p -b qrb2210_rb1 ${input:app}" },
    { "label": "qemu run", "type": "shell",
      "command": "west build -b qemu_cortex_a53 ${input:app} -t run" },
    { "label": "twister qemu+native", "type": "shell",
      "command": "./scripts/twister -p native_sim -p qemu_cortex_a53 -T tests/" }
  ]
}
```

Recommended extensions (`.vscode/extensions.json`): `ms-vscode.cpptools`,
`marus25.cortex-debug`, `nordic-semiconductor.nrf-devicetree`,
`nordic-semiconductor.nrf-kconfig` (DT/Kconfig language support is vendor-agnostic
and helps on the QCM2290 port too).

## Bootstrap script

A `bootstrap.sh` that creates the venv, installs west, runs the workspace setup
from `west-workspace.md` (upstream Zephyr + AArch64 SDK + your port module), and
installs pre-commit gives new machines a one-command path to a building tree.

## Layered CI

- **Fast tier (every push / PR):** compliance + `native_sim` **and**
  `qemu_cortex_a53` Twister. The QEMU tier is what makes AArch64/GIC/timer/PSCI
  regressions visible without hardware.

  ```yaml
  # .github/workflows/ci.yml (sketch)
  - run: ./scripts/twister -p native_sim -p qemu_cortex_a53 -T tests/ --inline-logs
  - run: python3 ./zephyr/scripts/ci/check_compliance.py -c origin/main..HEAD
  ```

- **Hardware tier (self-hosted runner with an RB1 attached):** Twister
  `--device-testing` over a fastboot-based runner, gated to the bench. Run on a
  schedule or label, not every PR — it serialises on the physical board and every
  `fastboot boot`/flash is destructive (see `boot-flash-fastboot.md`).

  ```yaml
  - run: ./scripts/twister -p qrb2210_rb1 --device-testing \
           --hardware-map map.yaml -T tests/
  ```

Keep the two tiers separate so a busy bench never blocks code review, and so the
fast tier stays a true inner-loop gate.
