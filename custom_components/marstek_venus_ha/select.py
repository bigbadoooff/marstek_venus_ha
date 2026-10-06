import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from .coordinator import MarstekCoordinator
from .const import DOMAIN, SIGNAL_DIAGNOSTICS_UPDATED, EMHASS_MODES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EmhassModeSelect(entry, coordinator),
    ])


class EmhassModeSelect(SelectEntity):
    """Select written by a HA automation (EMHASS) to force grid charging or holding.

    The mode is only valid for a limited time (heartbeat). Each write, even with the
    same option, renews it. The mode is not restored after a restart.
    """

    def __init__(self, entry: ConfigEntry, data_object: MarstekCoordinator):
        self._entry = entry
        self._data = data_object
        self._attr_name = "EMHASS Mode"
        self._attr_icon = "mdi:robot"
        self._attr_unique_id = f"{entry.entry_id}_emhass_mode_select"
        self._attr_options = list(EMHASS_MODES)

    @property
    def available(self) -> bool:
        return bool(self._data.is_running)

    @property
    def current_option(self) -> str:
        return self._data.emhass_mode

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

    async def async_select_option(self, option: str) -> None:
        self._data.set_emhass_mode(option)
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_DIAGNOSTICS_UPDATED)
        if hasattr(self._data, "async_request_update"):
            self.hass.async_create_task(self._data.async_request_update(reason="emhass_mode"))
