import asyncio
from datetime import datetime, timedelta

from custom_components.marstek_venus_ha.coordinator import (
    MarstekCoordinator,
    PowerDir,
)
from custom_components.marstek_venus_ha.const import (
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    EMHASS_MODE_CHARGE,
    EMHASS_MODE_HOLD,
    EMHASS_MODE_OFF,
)


def _mk_coordinator_for_emhass(*, socs: dict[str, float | None], config: dict | None = None):
    c = MarstekCoordinator.__new__(MarstekCoordinator)
    c.hass = None
    c.config = {CONF_MAX_CHARGE_POWER: 2500, CONF_MIN_SOC: 12, CONF_MAX_SOC: 100}
    c.config.update(config or {})
    c._batteries = [
        {"id": b, "soc": f"sensor.{b}_soc", "ac_power": f"sensor.{b}_ac_power"} for b in socs
    ]
    c._battery_priority = []
    c._last_power_direction = PowerDir.DISCHARGE
    c._last_priority_update = datetime.min
    c._priority_list_power_direction = None
    c._power_direction_change_start = None
    c._allow_charging = True
    c._allow_discharging = True
    c._price_control_enabled = False
    c._price_is_cheap = False
    c._price_is_expensive = False
    c._price_current_ranking = None
    c._price_cheap_charge_soc_override = None
    c._solar_forecast_charge_factor = 1.0

    c._emhass_mode = EMHASS_MODE_OFF
    c._emhass_mode_set_at = None
    c._emhass_target_soc = 80
    c._emhass_charge_power = c.emhass_max_charge_power
    c._emhass_charge_soc_target = None
    c._emhass_active_state = None

    soc_by_entity = {f"sensor.{b}_soc": soc for b, soc in socs.items()}
    c._get_float_state = lambda entity_id: soc_by_entity.get(entity_id)

    c.zero_calls = 0
    c.distribute_calls = []

    async def _set_all_batteries_to_zero():
        c.zero_calls += 1

    async def _distribute_power(power, target_num_batteries=1, *, from_pid=False):
        c.distribute_calls.append((power, target_num_batteries, c._last_power_direction))

    c._set_all_batteries_to_zero = _set_all_batteries_to_zero
    c._distribute_power = _distribute_power
    return c


def test_off_lets_normal_algorithm_run():
    c = _mk_coordinator_for_emhass(socs={"b1": 50.0})

    assert asyncio.run(c._handle_emhass_mode()) is False
    assert c.zero_calls == 0
    assert c.distribute_calls == []
    assert c._last_power_direction == PowerDir.DISCHARGE


def test_hold_writes_zero_and_takes_control():
    c = _mk_coordinator_for_emhass(socs={"b1": 50.0})
    c._battery_priority = [{"id": "b1"}]
    c.set_emhass_mode(EMHASS_MODE_HOLD)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 1
    assert c._battery_priority == []
    assert c.distribute_calls == []


def test_charge_below_target_charges_with_capped_power():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0, "b2": 60.0})
    c.set_emhass_target_soc(80)
    c.set_emhass_charge_power(1200)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 0
    assert c.distribute_calls == [(1200.0, 2, PowerDir.CHARGE)]
    assert [b["id"] for b in c._battery_priority] == ["b1", "b2"]


def test_charge_power_is_capped_to_eligible_batteries():
    # b2 is already at target, so only one battery can take max_charge_power.
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0, "b2": 85.0})
    c.set_emhass_charge_power(5000)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.distribute_calls == [(2500.0, 1, PowerDir.CHARGE)]
    assert [b["id"] for b in c._battery_priority] == ["b1"]


def test_charge_power_number_is_clamped_to_total_max():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0, "b2": 40.0})
    c.set_emhass_charge_power(99999)
    assert c.emhass_charge_power == 5000
    c.set_emhass_charge_power(-5)
    assert c.emhass_charge_power == 0


def test_charge_target_reached_holds():
    c = _mk_coordinator_for_emhass(socs={"b1": 80.0, "b2": 90.0})
    c.set_emhass_target_soc(80)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 1
    assert c.distribute_calls == []
    assert c._emhass_charge_soc_target is None


def test_charge_target_is_limited_by_max_soc():
    c = _mk_coordinator_for_emhass(socs={"b1": 92.0}, config={CONF_MAX_SOC: 90})
    c.set_emhass_target_soc(100)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 1
    assert c.distribute_calls == []


def test_charge_with_zero_power_holds():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c.set_emhass_charge_power(0)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 1
    assert c.distribute_calls == []


def test_heartbeat_expired_falls_back_to_off():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c.set_emhass_mode(EMHASS_MODE_HOLD)
    c._emhass_mode_set_at = datetime.now() - timedelta(minutes=11)

    assert asyncio.run(c._handle_emhass_mode()) is False
    assert c.emhass_mode == EMHASS_MODE_OFF
    assert c.zero_calls == 0


def test_same_option_renews_heartbeat():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c.set_emhass_mode(EMHASS_MODE_HOLD)
    c._emhass_mode_set_at = datetime.now() - timedelta(minutes=9)
    c.set_emhass_mode(EMHASS_MODE_HOLD)
    c._emhass_mode_set_at -= timedelta(minutes=2)  # 11 minutes after the first write

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.emhass_mode == EMHASS_MODE_HOLD


def test_unknown_soc_holds():
    c = _mk_coordinator_for_emhass(socs={"b1": None})
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert c.zero_calls == 1
    assert c.distribute_calls == []


def test_unknown_soc_battery_is_not_charged():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0, "b2": None})
    c.set_emhass_charge_power(5000)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert [b["id"] for b in c._battery_priority] == ["b1"]
    assert c.distribute_calls == [(2500.0, 1, PowerDir.CHARGE)]


def test_charge_bypasses_allow_charging_switch():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c._allow_charging = False
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    assert [b["id"] for b in c._battery_priority] == ["b1"]
    assert len(c.distribute_calls) == 1


def test_off_respects_allow_charging_switch():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c._allow_charging = False
    c._last_power_direction = PowerDir.CHARGE

    assert asyncio.run(c._handle_emhass_mode()) is False
    asyncio.run(c._calculate_battery_priority())
    assert c._battery_priority == []


def test_charge_bypasses_price_block_and_ignores_price_override():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0, "b2": 55.0})
    c._price_control_enabled = True
    c._price_is_expensive = True
    c._price_cheap_charge_soc_override = 50
    c.set_emhass_target_soc(80)
    c.set_emhass_mode(EMHASS_MODE_CHARGE)

    assert asyncio.run(c._handle_emhass_mode()) is True
    # b2 (55%) is above the stale price override (50%) but below the EMHASS target.
    assert [b["id"] for b in c._battery_priority] == ["b1", "b2"]
    assert c._price_cheap_charge_soc_override is None
    assert c._price_is_expensive is False


def test_releasing_control_clears_overrides():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    c.set_emhass_mode(EMHASS_MODE_CHARGE)
    asyncio.run(c._handle_emhass_mode())
    assert c._emhass_charge_soc_target == 80

    c.set_emhass_mode(EMHASS_MODE_OFF)
    assert asyncio.run(c._handle_emhass_mode()) is False
    assert c._emhass_charge_soc_target is None
    assert c._battery_priority == []


def test_priority_is_not_recalculated_every_cycle():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    calls = 0
    original = c._calculate_battery_priority

    async def _counting():
        nonlocal calls
        calls += 1
        await original()

    c._calculate_battery_priority = _counting
    c.set_emhass_mode(EMHASS_MODE_CHARGE)
    for _ in range(3):
        asyncio.run(c._handle_emhass_mode())
    assert calls == 1

    c.set_emhass_target_soc(90)
    asyncio.run(c._handle_emhass_mode())
    assert calls == 2


def _prepare_for_async_update(c, *, wallbox_takes_control: bool):
    c._control_enabled = True
    c._solar_forecast_enabled = False
    c._price_control_enabled = True
    c._pid_enabled = False
    c._wallbox_is_active = False
    c.price_calls = 0
    c.wallbox_calls = 0

    async def _wallbox(real_power):
        c.wallbox_calls += 1
        return wallbox_takes_control

    async def _price():
        c.price_calls += 1
        return False

    c._get_smoothed_grid_power = lambda: 100.0
    c._get_real_power = lambda grid: 100.0
    c._handle_wallbox_logic = _wallbox
    c._handle_price_logic = _price
    c._reset_pid_state = lambda: None


def test_async_update_emhass_runs_before_price_logic():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    _prepare_for_async_update(c, wallbox_takes_control=False)
    c.set_emhass_mode(EMHASS_MODE_HOLD)

    asyncio.run(c._async_update())
    assert c.zero_calls == 1
    assert c.price_calls == 0


def test_async_update_wallbox_has_precedence_over_emhass():
    c = _mk_coordinator_for_emhass(socs={"b1": 40.0})
    _prepare_for_async_update(c, wallbox_takes_control=True)
    c.set_emhass_mode(EMHASS_MODE_HOLD)

    asyncio.run(c._async_update())
    assert c.wallbox_calls == 1
    assert c.zero_calls == 0
    assert c.price_calls == 0
