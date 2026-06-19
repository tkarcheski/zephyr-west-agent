"""The reasoning loop: Claude drives the debug/test-engineering cycle.

This is the "agent" in zephyr-agent. Claude is given a small set of tools —
read/write files in the workspace and run shell commands — and every command it
runs is funnelled through :class:`~zephyr_agent.executor.Executor`, so the safety
gate applies to anything the model tries to do to hardware.

The Anthropic SDK is imported lazily so the rest of the CLI works without it.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .executor import Executor

log = logging.getLogger("zephyr_agent.llm")

MAX_ITERATIONS = 24
MAX_READ_BYTES = 200_000

SYSTEM_PROMPT = """\
You are zephyr-agent, an expert in debugging Zephyr RTOS on AMD Versal /
MicroBlaze-V (mbv32) and Cortex-R52 RPU hardware via west, Lopper-generated
devicetree, and JTAG/xsdb. You are running on a real host with hardware
attached.

Work the debug loop, one variable at a time:
  1. Triage from RESOLVED truth: build/zephyr/.config and build/zephyr/zephyr.dts
     are ground truth; prj.conf and overlays are only requests.
  2. Form ONE falsifiable hypothesis.
  3. Run the SMALLEST experiment: a focused Ztest, an additive Kconfig fragment
     (EXTRA_CONF_FILE), or a devicetree overlay (EXTRA_DTC_OVERLAY_FILE). Never
     edit generated artifacts directly.
  4. Build native_sim first for logic bugs; real hardware only when needed.
  5. Observe, compare to the experiment's expectation, iterate.
  6. Exit by capturing the proven cause as a permanent Ztest/Twister case, then
     apply the real fix and re-run.

Tool rules:
- Use run_shell for west/twister/xsdb commands. Hardware-affecting commands
  (flash, device program, boot-mode, reset, --device-testing) are GATED and may
  be declined by the operator — if a command is blocked, explain and propose the
  safe next step instead of retrying blindly.
- Use read_file to inspect resolved artifacts and logs before theorising.
- Use write_file to create/modify tests, overlays, and conf fragments (inside
  the workspace only).
Be concise. State the hypothesis before each experiment and the conclusion after.
"""


def _tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "run_shell",
            "description": (
                "Run a shell command from the Zephyr workspace. Use for west, "
                "twister, xsdb, grep, etc. Hardware-affecting commands are gated "
                "and may be declined."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command line to run."},
                    "xilinx_env": {
                        "type": "boolean",
                        "description": "Source Vivado/Vitis settings first (needed for xsct/xsdb).",
                        "default": False,
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "read_file",
            "description": "Read a text file (e.g. build/zephyr/.config, zephyr.dts, a log).",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": (
                "Create or overwrite a text file inside the workspace (a Ztest, "
                "overlay, or conf fragment)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    ]


class Agent:
    def __init__(
        self,
        executor: Executor,
        *,
        api_key: Optional[str] = None,
        skill_context: Optional[str] = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self.ex = executor
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.skill_context = skill_context
        self.max_iterations = max_iterations

    # -- tool dispatch ---------------------------------------------------

    def _resolve_in_workspace(self, path: str) -> "tuple[Path, Path]":
        ws = self.ex.config.workspace.resolve()
        p = Path(path)
        if not p.is_absolute():
            p = (self.ex.config.zephyr_dir / p)
        p = p.resolve()
        return p, ws

    def _tool_run_shell(self, command: str, xilinx_env: bool = False) -> str:
        res = self.ex.run(command, xilinx_env=xilinx_env, label=command)
        body = {
            "returncode": res.returncode,
            "blocked": res.skipped,
            "dry_run": res.dry_run,
            "stdout": res.stdout[-8000:],
            "stderr": res.stderr[-4000:],
        }
        return json.dumps(body)

    def _tool_read_file(self, path: str) -> str:
        p, _ = self._resolve_in_workspace(path)
        if not p.is_file():
            return f"ERROR: not a file: {p}"
        data = p.read_bytes()[:MAX_READ_BYTES]
        return data.decode("utf-8", errors="replace")

    def _tool_write_file(self, path: str, content: str) -> str:
        p, ws = self._resolve_in_workspace(path)
        if ws not in p.parents and p != ws:
            return f"ERROR: refusing to write outside workspace: {p}"
        if self.ex.config.dry_run:
            return f"[dry-run] would write {len(content)} bytes to {p}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} bytes to {p}"

    def _dispatch(self, name: str, args: Dict[str, Any]) -> str:
        try:
            if name == "run_shell":
                return self._tool_run_shell(
                    args["command"], bool(args.get("xilinx_env", False))
                )
            if name == "read_file":
                return self._tool_read_file(args["path"])
            if name == "write_file":
                return self._tool_write_file(args["path"], args["content"])
            return f"ERROR: unknown tool {name}"
        except Exception as exc:  # surface tool errors to the model, don't crash
            log.exception("tool %s failed", name)
            return f"ERROR: {type(exc).__name__}: {exc}"

    # -- main loop -------------------------------------------------------

    def run(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it to use `zephyr-agent ask`."
            )
        try:
            import anthropic  # lazy: keeps core CLI dependency-free
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'anthropic' package is required for `ask`. "
                "Install it with: pip install 'zephyr-agent[llm]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        system = SYSTEM_PROMPT
        if self.skill_context:
            system += "\n\n# Skill reference\n" + self.skill_context

        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        tools = _tool_schemas()
        final_text: List[str] = []

        for _ in range(self.max_iterations):
            resp = client.messages.create(
                model=self.ex.config.model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            )
            assistant_content: List[Dict[str, Any]] = []
            tool_results: List[Dict[str, Any]] = []

            for block in resp.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    final_text.append(block.text)
                    print(block.text)
                elif block.type == "tool_use":
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    result = self._dispatch(block.name, dict(block.input))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "assistant", "content": assistant_content})
            if resp.stop_reason == "tool_use":
                messages.append({"role": "user", "content": tool_results})
                continue
            break
        else:
            final_text.append("\n[stopped: reached max iterations]")

        return "\n".join(final_text)


def find_skill_context(start: Optional[Path] = None) -> Optional[str]:
    """Locate the installed SKILL.md and return its text, if present."""
    here = (start or Path.cwd()).resolve()
    for base in [here, *here.parents]:
        candidate = base / ".claude" / "skills" / "zephyr-versal" / "SKILL.md"
        if candidate.is_file():
            return candidate.read_text()
    return None
