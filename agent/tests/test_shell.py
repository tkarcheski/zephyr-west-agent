from zephyr_agent.shell import run_command


def test_dry_run_does_not_execute(tmp_path):
    marker = tmp_path / "should_not_exist"
    res = run_command(["touch", str(marker)], dry_run=True)
    assert res.dry_run and res.ok
    assert not marker.exists()


def test_string_command_quoting():
    res = run_command(["echo", "a b"], dry_run=True)
    assert "'a b'" in res.command


def test_real_command_success_and_failure():
    assert run_command(["true"]).ok
    res = run_command(["false"])
    assert res.returncode != 0 and not res.ok
