import logging
from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from .coordinator import MarstekCoordinator, PowerDir
from .const import DOMAIN, SIGNAL_DIAGNOSTICS_UPDATED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ControlSwitch(entry, coordinator),
        ChargingSwitch(entry, coordinator),
        DischargingSwitch(entry, coordinator),
        WallboxPrioritySwitch(entry, coordinator),
        BlockDischargingCCSwitch(entry, coordinator),
        PriceControlSwitch(entry, coordinator),
        SolarForecastSwitch(entry, coordinator),
    ])


class ControlSwitch(SwitchEntity):
    """Switch to enable/disable the entire integration's control logic."""

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        """Initialize the switch."""
        self._entry = entry
        self._data = data_object
        self._attr_name = "Control Batteries"
        self._attr_unique_id = f"{entry.entry_id}_control_switch"

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        return True  # Always available to allow re-enabling control

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return bool(self._data._control_enabled)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        if not self._data._control_enabled:
            _LOGGER.info("Battery control has been enabled.")
            self._data._control_enabled = True
            await self._data.async_save_settings()
            self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
            self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
            self.async_write_ha_state()
            async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
            if hasattr(self._data, "async_request_update"):
                self.hass.async_create_task(self._data.async_request_update(reason="control_enabled"))
            await self._data.async_start_listening()  # Start listening to updates when control is enabled

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        if self._data._control_enabled:
            self._data._control_enabled = False
            await self._data.async_save_settings()
            self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
            self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
            self.async_write_ha_state()
            async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
            await self._data.async_stop_listening()  # Stop listening to updates when control is disabled

class ChargingSwitch(SwitchEntity):
    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Allow Charging"
        self._attr_unique_id = f"{entry.entry_id}_charging_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._allow_charging)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._allow_charging = True
        await self._data.async_save_settings()
        self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
        self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._allow_charging = False
        await self._data.async_save_settings()
        self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
        self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))


class DischargingSwitch(SwitchEntity):
    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Allow Discharging"
        self._attr_unique_id = f"{entry.entry_id}_discharging_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._allow_discharging)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._allow_discharging = True
        await self._data.async_save_settings()
        self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
        self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._allow_discharging = False
        await self._data.async_save_settings()
        self._data._battery_priority = []  # Clear battery priority to force recalculation on next update
        self._data._last_power_direction = PowerDir.NEUTRAL  # Reset power direction to force recalculation
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

class WallboxPrioritySwitch(SwitchEntity):
    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Wallbox Priority"
        self._attr_unique_id = f"{entry.entry_id}_wallbox_priority_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._wallbox_priority)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._wallbox_priority = True
        await self._data.async_save_settings()
        self._data._wallbox_wait_start = None  # Reset wallbox wait timer to allow immediate priority
        self._data._last_wallbox_pause_attempt = datetime.min  # Reset last pause attempt to allow immediate action
        self._data._wallbox_power_history.clear()  # Clear power history to allow immediate stability assessment
        self._data._wallbox_power_is_stable = False  # Reset stability flag to force reassessment
        self._data._wallbox_stabilization_start = None  # Reset stabilization timer
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._wallbox_priority = False
        await self._data.async_save_settings()
        self._data._wallbox_charge_paused = False  # Release Batteries from blockade
        self._data._last_wallbox_pause_attempt = datetime.min  # Reset last pause attempt to allow immediate action
        self._data._wallbox_power_history.clear()  # Clear power history to allow immediate stability assessment
        self._data._wallbox_power_is_stable = False  # Reset stability flag to force reassessment
        self._data._wallbox_stabilization_start = None  # Reset stabilization timer
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

class BlockDischargingCCSwitch(SwitchEntity):
    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Block discharging while carcharging"
        self._attr_unique_id = f"{entry.entry_id}_block_discharging_cc_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._block_discharging_while_carcharging)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._block_discharging_while_carcharging = True
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._block_discharging_while_carcharging = False
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))


class PriceControlSwitch(SwitchEntity):
    """Switch to enable/disable price-based battery control.

    When enabled the coordinator uses the configured electricity price sensor
    to decide whether to force-charge (cheap price), block discharge (cheap),
    or block charging (expensive price).
    """

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Price-based Control"
        self._attr_unique_id = f"{entry.entry_id}_price_control_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._price_control_enabled)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._price_control_enabled = True
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._price_control_enabled = False
        # Clear transient price flags so the normal algorithm takes over immediately.
        self._data._price_is_cheap = False
        self._data._price_is_expensive = False
        self._data._price_current_ranking = None
        self._data._price_cheap_charge_soc_override = None
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))


class SolarForecastSwitch(SwitchEntity):
    """Switch to enable/disable solar forecast charge spreading.

    When enabled the coordinator uses the configured solar forecast sensor to
    compute a charge scaling factor so the battery fills up "just in time"
    rather than absorbing all available surplus early in the day.
    """

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "Solar Forecast Charge Spreading"
        self._attr_icon = "mdi:solar-power-variant"
        self._attr_unique_id = f"{entry.entry_id}_solar_forecast_switch"

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def is_on(self) -> bool:
        return bool(self._data._solar_forecast_enabled)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DIAGNOSTICS_UPDATED,
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._data._solar_forecast_enabled = True
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))

    async def async_turn_off(self, **kwargs):
        self._data._solar_forecast_enabled = False
        self._data._solar_forecast_charge_factor = 1.0
        await self._data.async_save_settings()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="switch_toggle"))