"""Gating policy for hardware-affecting commands.

The agent runs real commands, but anything that mutates hardware or board state
(flash, PDI/bitstream programming, boot-mode change, reset, erase) is classified
as *destructive* and must be confirmed before it runs. Read-only commands
(building, listing targets, register reads) are *safe* and run freely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional, Sequence, Union

CommandLike = Union[str, Sequence[str]]


class Risk(str, Enum):
    SAFE = "safe"
    DESTRUCTIVE = "destructive"


#: Substrings/regexes that mark a command as hardware-affecting. Matched against
#: the whole command line, case-insensitively.
DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwest\s+flash\b",
        r"\bdevice\s+program\b",      # xsdb PDI/bitstream programming
        r"\bfpga\b.*\b(program|-f|\.bit|\.pdi)\b",
        r"\bprogram_flash\b",
        r"change_boot_mode",          # versal_change_boot_mode.tcl
        r"boot_?mode",                # boot-mode register changes
        r"\b(dow|download)\b",         # downloading an image into target memory
        r"\brst\b",                    # xsdb reset
        r"\berase\b",
        r"--device-testing\b",        # twister will flash the attached board
    )
)

#: Patterns that, when present, force a command back to SAFE even if a
#: destructive pattern also matched (e.g. ``west debug`` only attaches).
SAFE_OVERRIDES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwest\s+debug\b",
        r"\btargets\b\s*$",
    )
)


def _as_text(cmd: CommandLike) -> str:
    return cmd if isinstance(cmd, str) else " ".join(str(part) for part in cmd)


def classify(cmd: CommandLike) -> Risk:
    """Classify a command as SAFE or DESTRUCTIVE."""
    text = _as_text(cmd)
    if any(p.search(text) for p in SAFE_OVERRIDES):
        return Risk.SAFE
    if any(p.search(text) for p in DESTRUCTIVE_PATTERNS):
        return Risk.DESTRUCTIVE
    return Risk.SAFE


#: A confirmation callback: given a human-readable prompt, return True to allow.
ConfirmFn = Callable[[str], bool]


def tty_confirm(prompt: str) -> bool:
    """Default interactive confirmation (y/N)."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, OSError):  # non-interactive stdin -> treat as decline
        return False
    return answer in {"y", "yes"}


@dataclass
class Decision:
    allowed: bool
    risk: Risk
    reason: str


class Gate:
    """Decides whether a command may run, honouring --yes and --dry-run.

    The confirmation function is injectable so the gate is fully testable
    without a TTY.
    """

    def __init__(
        self,
        *,
        assume_yes: bool = False,
        confirm: Optional[ConfirmFn] = None,
    ) -> None:
        self.assume_yes = assume_yes
        self._confirm = confirm or tty_confirm

    def evaluate(self, cmd: CommandLike, *, label: Optional[str] = None) -> Decision:
        risk = classify(cmd)
        if risk is Risk.SAFE:
            return Decision(True, risk, "read-only / non-destructive")
        if self.assume_yes:
            return Decision(True, risk, "approved via --yes")
        shown = label or _as_text(cmd)
        ok = self._confirm(f"About to run a DESTRUCTIVE command on hardware:\n  {shown}\nProceed?")
        return Decision(
            ok,
            risk,
            "confirmed by operator" if ok else "declined by operator",
        )


def patterns_for_docs() -> Iterable[str]:
    """Human-readable list of what counts as destructive (used in --help)."""
    return [p.pattern for p in DESTRUCTIVE_PATTERNS]
