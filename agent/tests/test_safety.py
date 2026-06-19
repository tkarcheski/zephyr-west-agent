from zephyr_agent.safety import Gate, Risk, classify


def test_safe_commands():
    assert classify("west build -b mbv32 samples/hello_world") is Risk.SAFE
    assert classify(["west", "build", "-p", "-b", "native_sim", "app"]) is Risk.SAFE
    assert classify("grep CONFIG_SERIAL build/zephyr/.config") is Risk.SAFE


def test_destructive_commands():
    assert classify("west flash --runner xsdb --elf-file z.elf") is Risk.DESTRUCTIVE
    assert classify("xsdb -eval 'connect ; device program a.pdi'") is Risk.DESTRUCTIVE
    assert classify("./scripts/twister -p mbv32 --device-testing") is Risk.DESTRUCTIVE
    assert classify("source versal_change_boot_mode.tcl") is Risk.DESTRUCTIVE


def test_safe_override_for_debug_and_targets():
    # west debug only attaches; listing targets is read-only.
    assert classify("west debug --runner xsdb") is Risk.SAFE
    assert classify("xsdb -eval 'connect ; targets'") is Risk.SAFE


def test_gate_allows_safe_without_confirm():
    gate = Gate(confirm=lambda _: False)  # would decline, but safe needs no ask
    d = gate.evaluate("west build -b native_sim app")
    assert d.allowed and d.risk is Risk.SAFE


def test_gate_blocks_destructive_when_declined():
    gate = Gate(confirm=lambda _: False)
    d = gate.evaluate("west flash --runner xsdb")
    assert not d.allowed and d.risk is Risk.DESTRUCTIVE


def test_gate_allows_destructive_when_confirmed():
    gate = Gate(confirm=lambda _: True)
    assert gate.evaluate("west flash --runner xsdb").allowed


def test_gate_assume_yes_bypasses_confirm():
    called = {"n": 0}

    def confirm(_):
        called["n"] += 1
        return False

    gate = Gate(assume_yes=True, confirm=confirm)
    assert gate.evaluate("west flash --runner xsdb").allowed
    assert called["n"] == 0  # never prompted
