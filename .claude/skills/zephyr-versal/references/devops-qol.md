# DevOps & developer QoL

Keep the inner loop fast and the tree clean so debugging effort goes to bugs,
not to environment drift.

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

Zephyr also ships `scripts/checkpatch.pl` and `west` extension
`./scripts/ci/check_compliance.py` for the same checks CI runs — run compliance
locally before pushing:

```bash
python3 ./scripts/ci/check_compliance.py -c upstream/main..HEAD
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

`.vscode/tasks.json` for one-key build/flash/test:

```json
{
  "version": "2.0.0",
  "tasks": [
    { "label": "west build mbv32", "type": "shell",
      "command": "west build -p -b mbv32 ${input:app}" },
    { "label": "twister native_sim", "type": "shell",
      "command": "./scripts/twister -p native_sim -T tests/" }
  ]
}
```

Recommended extensions (`.vscode/extensions.json`): `ms-vscode.cpptools`,
`marus25.cortex-debug`, `nordic-semiconductor.nrf-devicetree`,
`nordic-semiconductor.nrf-kconfig` (DT/Kconfig language support is fork-agnostic
and helps on Versal too).

## Bootstrap script

A `bootstrap.sh` that creates the venv, installs west, runs the workspace setup
from `west-workspace.md`, and installs pre-commit gives new machines a
one-command path to a building tree.

## Layered CI

- **Fast tier (every push / PR):** compliance + `native_sim` Twister.

  ```yaml
  # .github/workflows/ci.yml (sketch)
  - run: ./scripts/twister -p native_sim -T tests/ --inline-logs
  - run: python3 ./scripts/ci/check_compliance.py -c origin/main..HEAD
  ```

- **Hardware tier (self-hosted runner with a board attached):** Twister
  `--device-testing` over xsdb, gated to the bench. Run on a schedule or label,
  not on every PR, because it serialises on physical hardware.

  ```yaml
  - run: ./scripts/twister -p mbv32 --device-testing \
           --hardware-map map.yaml -T tests/ --west-runner xsdb
  ```

Keep the two tiers separate so a busy JTAG bench never blocks code review, and so
the fast tier stays a true inner-loop gate.
