"""
Select platform for Free Sleep Pod integration.

This module is loaded automatically by Home Assistant to set up select entities
for the Free Sleep Pod integration.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
  CoordinatorEntity,
  DataUpdateCoordinator,
)

from .constants import DOMAIN
from .pod import Pod


@dataclass(frozen=True)
class FreeSleepSelectDescription(SelectEntityDescription):
  """A class that describes Free Sleep Pod select entities."""

  name: str
  options: list[str] = None  # type: ignore[assignment]
  get_value: Callable[[dict[str, Any]], str | None] | None = None
  set_value: Callable[[Pod, str], Awaitable[None]] | None = None


POD_SELECTS: tuple[FreeSleepSelectDescription, ...] = (
  FreeSleepSelectDescription(
    name='Temperature Format',
    key='temperature_format',
    translation_key='temperature_format',
    icon='mdi:thermometer',
    options=['celsius', 'fahrenheit'],
    get_value=lambda data: data['settings'].get('temperatureFormat'),
    set_value=lambda pod, value: pod.set_temperature_format(value),
  ),
)


async def async_setup_entry(
  hass: HomeAssistant,
  entry: ConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """
  Set up select entities for the Free Sleep pod.

  :param hass: The Home Assistant instance.
  :param entry: The configuration entry.
  :param async_add_entities: Callback to add entities.
  """
  pod, coordinator = hass.data[DOMAIN][entry.entry_id]

  selects = [
    FreeSleepSelect(coordinator, pod, description) for description in POD_SELECTS
  ]

  async_add_entities(selects, update_before_add=True)


class FreeSleepSelect(CoordinatorEntity, SelectEntity):
  """A class that represents a select entity for a Free Sleep Pod."""

  entity_description: FreeSleepSelectDescription

  _attr_has_entity_name = True

  def __init__(
    self,
    coordinator: DataUpdateCoordinator,
    pod: Pod,
    description: FreeSleepSelectDescription,
  ) -> None:
    """
    Initialize the Free Sleep Pod select entity.

    :param coordinator: The data update coordinator.
    :param pod: The Free Sleep Pod instance.
    :param description: The entity description.
    """
    super().__init__(coordinator)

    self.pod = pod
    self.entity_description = description
    self._attr_name = description.name
    self._attr_unique_id = f'{pod.id}_{description.key}'
    self._attr_options = description.options or []

  @property
  def device_info(self) -> dict:
    """
    Return device information for the Free Sleep Pod.

    :return: A dictionary containing device information.
    """
    return self.pod.device_info

  @property
  def current_option(self) -> str | None:
    """Return the currently selected option."""
    if self.entity_description.get_value:
      return self.entity_description.get_value(self.coordinator.data)
    return None

  async def async_select_option(self, option: str) -> None:
    """Handle option selection."""
    if self.entity_description.set_value:
      await self.entity_description.set_value(self.pod, option)

    await self.coordinator.async_request_refresh()
