import logging

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from .coordinator import MarstekCoordinator
from .const import DOMAIN, SIGNAL_DIAGNOSTICS_UPDATED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EmhassTargetSocNumber(entry, coordinator),
        EmhassChargePowerNumber(entry, coordinator),
    ])


class _EmhassNumberBase(RestoreNumber):
    """Common behaviour: value lives in the coordinator and is restored after a restart."""

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Marstek Venus HA",
        )

    def _apply(self, value: float) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._apply(last.native_value)
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

    async def async_set_native_value(self, value: float) -> None:
        self._apply(value)
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="emhass_setting"))


class EmhassTargetSocNumber(_EmhassNumberBase):
    """Target SoC for EMHASS mode 'laden'. Once reached, 'laden' behaves like 'halten'."""

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        super().__init__(entry, data_object)
        self._attr_name = "EMHASS Target SoC"
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_unique_id = f"{entry.entry_id}_emhass_target_soc"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return float(self._data.emhass_target_soc)

    def _apply(self, value: float) -> None:
        self._data.set_emhass_target_soc(value)


class EmhassChargePowerNumber(_EmhassNumberBase):
    """Upper limit for the grid charge power in EMHASS mode 'laden' (all batteries together)."""

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        super().__init__(entry, data_object)
        self._attr_name = "EMHASS Charge Power"
        self._attr_icon = "mdi:transmission-tower-import"
        self._attr_unique_id = f"{entry.entry_id}_emhass_charge_power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = data_object.emhass_max_charge_power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return float(self._data.emhass_charge_power)

    def _apply(self, value: float) -> None:
        self._data.set_emhass_charge_power(value)
