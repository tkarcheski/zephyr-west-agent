from zephyr_agent.config import AgentConfig
from zephyr_agent.executor import Executor
from zephyr_agent.safety import Gate


def _ex(*, dry_run=True, allow=False, assume_yes=False):
    cfg = AgentConfig(dry_run=dry_run, board="mbv32")
    gate = Gate(assume_yes=assume_yes, confirm=lambda _: allow)
    return Executor(cfg, gate=gate)


def test_safe_command_runs_in_dry_run():
    res = _ex().run("west build -b native_sim app")
    assert res.ok and res.dry_run and not res.skipped


def test_destructive_blocked_when_declined():
    res = _ex(allow=False).run("west flash --runner xsdb")
    assert res.skipped
    assert res.returncode == 126
    assert "blocked by safety gate" in res.stderr


def test_destructive_allowed_when_confirmed():
    res = _ex(allow=True).run("west flash --runner xsdb")
    assert not res.skipped and res.ok


def test_assume_yes_allows_destructive():
    res = _ex(assume_yes=True).run("west flash --runner xsdb")
    assert not res.skipped and res.ok
