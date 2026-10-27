"""LED_SET and LED_GET commands: protocol.md sections 6.4 and 6.5.

Each test starts with LD1 off, after both commands were found in the CAPS
list (section 3.4). The state returned is the pin level read back by the
firmware, so LED_SET checks the hardware without an instrument. A rejected
request must leave LD1 unchanged (section 7.1); LD1 must be off after a
reset. DEVICE_ERROR needs a faulty pin and is not tested here.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import pytest

pytestmark = pytest.mark.led


def led_state(board) -> str:
    """State of LD1 reported by LED_GET."""
    response = board.request("LED_GET")
    assert response.ok
    return response.fields["state"]


@pytest.fixture
def led(fresh_board):
    """The session board, LED commands supported, LD1 off."""
    fresh_board.require("LED_SET")
    fresh_board.require("LED_GET")
    assert fresh_board.request("LED_SET", state="off").fields == {"state": "off"}
    return fresh_board


@pytest.mark.parametrize("state", ["on", "off"])
def test_led_set(led, state):
    response = led.request("LED_SET", state=state)
    assert response.ok
    assert response.fields == {"state": state}
    assert led_state(led) == state


def test_led_toggle(led):
    for expected in ("on", "off"):
        response = led.request("LED_SET", state="toggle")
        assert response.ok
        assert response.fields == {"state": expected}
        assert led_state(led) == expected


def test_led_off_after_reset(led):
    assert led.request("LED_SET", state="on").ok
    led.start_session()
    led.require("LED_GET")  # New session: CAPS again before any other command
    assert led_state(led) == "off"


@pytest.mark.parametrize("args", [{}, {"state": "blink"}, {"state": "ON"}, {"state": "on", "led": "1"}, {"level": "on"}],
                         ids=["missing_state", "unknown_value", "uppercase", "extra_argument", "unknown_key"])
def test_led_set_invalid(led, args):
    assert led.request("LED_SET", state="on").ok
    response = led.request("LED_SET", **args)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")
    assert led_state(led) == "on"  # Not executed: LD1 unchanged


def test_led_get_argument(led):
    response = led.request("LED_GET", x=1)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")
