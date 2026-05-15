"""Tests for the protocol module: just verifies the constants exist."""

from server import protocol


def test_constants_present():
    assert protocol.C2S_JOIN == "join"
    assert protocol.C2S_INPUT == "input"
    assert protocol.C2S_FIRE == "fire"
    assert protocol.S2C_WELCOME == "welcome"
    assert protocol.S2C_STATE == "state"
    assert protocol.S2C_EVENT == "event"
    assert protocol.S2C_JOIN_ERROR == "join_error"
