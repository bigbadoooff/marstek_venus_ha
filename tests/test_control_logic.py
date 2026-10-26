import asyncio

from custom_components.marstek_venus_ha.coordinator import (
    MarstekCoordinator,
    PowerDir,
)
from custom_components.marstek_venus_ha.const import (
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MIN_CONSUMPTION,
    CONF_MIN_SURPLUS,
    CONF_MAX_LIMIT_BREACHES_BEFORE_ZEROING,
    CONF_POWER_STAGE_OFFSET,
)


def _mk_battery(batt_id: str) -> dict:
    return {
        "id": batt_id,
        "ac_power": f"sensor.{batt_id}_ac_power",
        "soc": f"sensor.{batt_id}_soc",
    }


def _mk_coordinator_for_control_logic(*, config: dict, battery_ids: list[str], states: dict | None = None):
    c = MarstekCoordinator.__new__(MarstekCoordinator)
    c.config = dict(config)
    c._batteries = [_mk_battery(b) for b in battery_ids]
    c._battery_priority = [{**_mk_battery(b), "current_soc": 50.0} for b in battery_ids]
    c._below_min_charge_count = 0
    c._below_min_discharge_count = 0
    c._charge_suspended = False
    c._discharge_suspended = False
    c._last_grid_power_raw = None
    c._solar_forecast_enabled = False
    c._solar_forecast_charge_factor = 1.0

    float_states = {f"sensor.{b}_soc": 50.0 for b in battery_ids}
    float_states.update(states or {})
    c._get_float_state = float_states.get

    async def _noop_async(*args, **kwargs):
        return None

    c._set_all_batteries_to_zero = _noop_async
    c._set_battery_power = _noop_async
    return c


def test_get_desired_number_of_batteries_charge_upshift_from_single():
    c = _mk_coordinator_for_control_logic(
        config={
            CONF_POWER_STAGE_OFFSET: 100,
            "powerstage_1_to_2": 1800,
            "powerstage_2_to_3": 3600,
        },
        battery_ids=["b1", "b2", "b3"],
    )
    c._last_power_direction = PowerDir.CHARGE

    # No batteries currently active; negative power means charging.
    assert c._get_desired_number_of_batteries(-1700) == 1
    assert c._get_desired_number_of_batteries(-2000) == 2
    assert c._get_desired_number_of_batteries(-3800) == 3


def test_get_desired_number_of_batteries_discharge_hysteresis_hold_two():
    c = _mk_coordinator_for_control_logic(
        config={
            CONF_POWER_STAGE_OFFSET: 100,
            "powerstage_1_to_2": 1400,
            "powerstage_2_to_3": 2000,
        },
        battery_ids=["b1", "b2", "b3"],
        states={"sensor.b1_ac_power": 50.0, "sensor.b2_ac_power": 50.0},
    )
    c._last_power_direction = PowerDir.DISCHARGE

    # With two active batteries, stay at 2 within hysteresis band:
    # stage1-offset=1300 and stage2+offset=2100
    assert c._get_desired_number_of_batteries(1500) == 2
    assert c._get_desired_number_of_batteries(2050) == 2

    # Drop below stage1-offset -> downshift to 1
    assert c._get_desired_number_of_batteries(1200) == 1

    # Rise above stage2+offset -> upshift to 3
    assert c._get_desired_number_of_batteries(2200) == 3


def test_get_desired_number_of_batteries_adds_battery_when_soc_caps_are_too_low():
    c = _mk_coordinator_for_control_logic(
        config={
            CONF_POWER_STAGE_OFFSET: 100,
            "powerstage_1_to_2": 3000,
            CONF_MAX_CHARGE_POWER: 2500,
        },
        battery_ids=["b1", "b2"],
        # SoC 99 % caps charging at charge level 1 (default 1500 W).
        states={"sensor.b1_soc": 99.0, "sensor.b2_soc": 99.0},
    )
    c._last_power_direction = PowerDir.CHARGE

    assert c._get_desired_number_of_batteries(-2000) == 2


def test_distribute_power_caps_per_battery_to_configured_max_charge_power():
    calls: list[tuple[str, int, int]] = []

    c = _mk_coordinator_for_control_logic(
        config={
            CONF_MAX_CHARGE_POWER: 2500,
            CONF_MAX_DISCHARGE_POWER: 2500,
        },
        battery_ids=["b1", "b2"],
    )
    c._last_power_direction = PowerDir.CHARGE

    async def _set_battery_power(batt: dict, power: int, direction: int):
        calls.append((batt["id"], power, direction))

    c._set_battery_power = _set_battery_power

    # abs_power=6000, 2 active batteries => 3000 each, but cap to max_charge_power=2500
    asyncio.run(c._distribute_power(power=6000.0, target_num_batteries=2))

    assert ("b1", 2500, PowerDir.CHARGE) in calls
    assert ("b2", 2500, PowerDir.CHARGE) in calls


def test_distribute_power_zero_target_sets_all_batteries_to_zero():
    zero_calls: list[object] = []
    set_calls: list[tuple[str, int, int]] = []

    c = _mk_coordinator_for_control_logic(config={}, battery_ids=["b1"])
    c._last_power_direction = PowerDir.CHARGE

    async def _set_all_batteries_to_zero():
        zero_calls.append(object())

    async def _set_battery_power(batt: dict, power: int, direction: int):
        set_calls.append((batt["id"], power, direction))

    c._set_all_batteries_to_zero = _set_all_batteries_to_zero
    c._set_battery_power = _set_battery_power

    asyncio.run(c._distribute_power(power=1000.0, target_num_batteries=0))

    assert len(zero_calls) == 1
    assert set_calls == []


def _mk_coordinator_for_thresholds():
    c = _mk_coordinator_for_control_logic(
        config={
            CONF_MIN_SURPLUS: 200,
            CONF_MIN_CONSUMPTION: 200,
            CONF_MAX_LIMIT_BREACHES_BEFORE_ZEROING: 10,
        },
        battery_ids=["b1"],
    )
    c._last_power_direction = PowerDir.CHARGE
    return c


def test_check_power_thresholds_suspends_only_after_n_cycles():
    c = _mk_coordinator_for_thresholds()

    for _ in range(9):
        assert asyncio.run(c._check_power_thresholds(100.0)) is False

    assert c._below_min_charge_count == 9

    assert asyncio.run(c._check_power_thresholds(100.0)) is True
    assert c._below_min_charge_count == 10

    # The counter is capped at the configured number of cycles.
    asyncio.run(c._check_power_thresholds(100.0))
    assert c._below_min_charge_count == 10


def test_check_power_thresholds_resumes_only_when_counter_reaches_zero():
    c = _mk_coordinator_for_thresholds()

    for _ in range(10):
        asyncio.run(c._check_power_thresholds(100.0))
    assert c._charge_suspended is True

    # Above the threshold the counter decays by one per cycle.
    for remaining in range(9, 0, -1):
        assert asyncio.run(c._check_power_thresholds(300.0)) is True
        assert c._below_min_charge_count == remaining

    assert asyncio.run(c._check_power_thresholds(300.0)) is False
    assert c._below_min_charge_count == 0
    assert c._below_min_discharge_count == 0


def test_check_power_thresholds_counts_discharge_separately():
    c = _mk_coordinator_for_thresholds()
    c._last_power_direction = PowerDir.DISCHARGE

    for _ in range(3):
        asyncio.run(c._check_power_thresholds(100.0))

    assert c._below_min_discharge_count == 3
    assert c._below_min_charge_count == 0
