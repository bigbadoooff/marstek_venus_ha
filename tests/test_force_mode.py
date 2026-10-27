import types

from homeassistant.core import State

from custom_components.marstek_venus_ha.coordinator import MarstekCoordinator


def _mk_coordinator(options):
    c = MarstekCoordinator.__new__(MarstekCoordinator)
    states = {} if options is None else {"select.force_mode": State("standby", {"options": options})}
    c.hass = types.SimpleNamespace(states=types.SimpleNamespace(get=states.get))
    return c


def test_idle_option_uses_standby_when_stop_is_not_offered():
    c = _mk_coordinator(["standby", "charge", "discharge"])
    assert c._get_force_mode_idle_option("select.force_mode") == "standby"


def test_idle_option_keeps_stop_when_offered():
    c = _mk_coordinator(["stop", "charge", "discharge"])
    assert c._get_force_mode_idle_option("select.force_mode") == "stop"


def test_idle_option_falls_back_to_stop_without_state():
    c = _mk_coordinator(None)
    assert c._get_force_mode_idle_option("select.force_mode") == "stop"
