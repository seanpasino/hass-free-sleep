"""
Switch platform for Free Sleep Pod integration.

This module is loaded automatically by Home Assistant to set up sensor entities
for the Free Sleep Pod integration.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aioesphomeapi import SensorStateClass
from homeassistant.components.sensor import (
  SensorDeviceClass,
  SensorEntity,
  SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
  PERCENTAGE,
  UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
  CoordinatorEntity,
)

from . import FreeSleepCoordinator
from .constants import DOMAIN
from .pod import Pod, Side


def _parse_dt(value: str | None) -> datetime | None:
  """Parse an ISO datetime string, ensuring UTC timezone."""
  if value is None:
    return None
  try:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
      dt = dt.replace(tzinfo=timezone.utc)
    return dt
  except (ValueError, TypeError):
    return None


def _sleep_duration_minutes(sleep_record: dict | None) -> int | None:
  """Return minutes of the most recent sleep session, or None."""
  if not sleep_record:
    return None
  entered = _parse_dt(sleep_record.get('entered_bed_at'))
  if not entered:
    return None
  left = _parse_dt(sleep_record.get('left_bed_at'))
  end = left if left else datetime.now(timezone.utc)
  return round((end - entered).total_seconds() / 60)


@dataclass(frozen=True)
class FreeSleepSensorDescription(SensorEntityDescription):
  """A class that describes Free Sleep Pod sensor entities."""

  name: str
  state_class: SensorStateClass | None = None
  requires_presence: bool = False

  get_value: Callable[[dict[str, Any]], StateType] | None = None


POD_SENSORS: tuple[FreeSleepSensorDescription, ...] = (
  FreeSleepSensorDescription(
    name='Version',
    key='version',
    translation_key='version',
    icon='mdi:information',
    get_value=lambda data: data['status']['freeSleep']['version'],
  ),
  FreeSleepSensorDescription(
    name='WiFi Strength',
    key='wifi_strength',
    translation_key='wifi_strength',
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:wifi',
    get_value=lambda data: data['status']['wifiStrength'],
  ),
)

POD_SIDE_SENSORS: tuple[FreeSleepSensorDescription, ...] = (
  FreeSleepSensorDescription(
    name='Heart Rate',
    key='heart_rate',
    translation_key='heart_rate',
    native_unit_of_measurement='bpm',
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:heart-pulse',
    requires_presence=True,
    get_value=lambda data: data['vitals']['avgHeartRate'],
  ),
  FreeSleepSensorDescription(
    name='Min Heart Rate',
    key='heart_rate_min',
    translation_key='heart_rate_min',
    native_unit_of_measurement='bpm',
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:heart-pulse',
    requires_presence=True,
    get_value=lambda data: data['vitals'].get('minHeartRate'),
  ),
  FreeSleepSensorDescription(
    name='Max Heart Rate',
    key='heart_rate_max',
    translation_key='heart_rate_max',
    native_unit_of_measurement='bpm',
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:heart-pulse',
    requires_presence=True,
    get_value=lambda data: data['vitals'].get('maxHeartRate'),
  ),
  FreeSleepSensorDescription(
    name='Respiration Rate',
    key='respiration_rate',
    translation_key='respiratory_rate',
    native_unit_of_measurement='breaths/min',
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:lungs',
    requires_presence=True,
    get_value=lambda data: data['vitals']['avgBreathingRate'],
  ),
  FreeSleepSensorDescription(
    name='HRV',
    key='hrv',
    translation_key='hrv',
    native_unit_of_measurement='ms',
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:heart',
    requires_presence=True,
    get_value=lambda data: data['vitals']['avgHRV'],
  ),
  FreeSleepSensorDescription(
    name='Sleep Duration',
    key='sleep_duration',
    translation_key='sleep_duration',
    native_unit_of_measurement=UnitOfTime.MINUTES,
    device_class=SensorDeviceClass.DURATION,
    state_class=SensorStateClass.MEASUREMENT,
    icon='mdi:sleep',
    get_value=lambda data: _sleep_duration_minutes(data.get('sleep')),
  ),
  FreeSleepSensorDescription(
    name='Sleep Entry',
    key='sleep_entry',
    translation_key='sleep_entry',
    device_class=SensorDeviceClass.TIMESTAMP,
    icon='mdi:sleep',
    get_value=lambda data: _parse_dt(
      data['sleep'].get('entered_bed_at') if data.get('sleep') else None
    ),
  ),
  FreeSleepSensorDescription(
    name='Sleep Exit',
    key='sleep_exit',
    translation_key='sleep_exit',
    device_class=SensorDeviceClass.TIMESTAMP,
    icon='mdi:sleep-off',
    get_value=lambda data: _parse_dt(
      data['sleep'].get('left_bed_at') if data.get('sleep') else None
    ),
  ),
)


async def async_setup_entry(
  hass: HomeAssistant,
  entry: ConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """
  Set up sensor entities for the Free Sleep pod.

  :param hass: The Home Assistant instance.
  :param entry: The configuration entry.
  :param async_add_entities: Callback to add entities.
  """
  pod, coordinator = hass.data[DOMAIN][entry.entry_id]
  sensors = [
    FreeSleepSensor(coordinator, pod, description)
    for description in POD_SENSORS
  ]

  async_add_entities(sensors, update_before_add=True)

  for side in pod.sides:
    side_switches = [
      FreeSleepSideSensor(coordinator, pod, side, description)
      for description in POD_SIDE_SENSORS
    ]

    async_add_entities(side_switches, update_before_add=True)


class FreeSleepSensor(CoordinatorEntity[FreeSleepCoordinator], SensorEntity):
  """A class that represents a sensor for a Free Sleep Pod."""

  entity_description: FreeSleepSensorDescription

  _attr_has_entity_name = True

  def __init__(
    self,
    coordinator: FreeSleepCoordinator,
    pod: Pod,
    description: FreeSleepSensorDescription,
  ) -> None:
    """
    Initialize the Free Sleep Pod sensor.

    :param coordinator: The data update coordinator.
    :param pod: The Free Sleep Pod instance.
    :param description: The entity description.
    """
    super().__init__(coordinator)

    self.pod = pod
    self.entity_description = description
    self._attr_name = description.name
    self._attr_unique_id = f'{pod.id}_{description.key}'

  @property
  def device_info(self) -> dict:
    """
    Return device information for the Free Sleep Pod. This is used by Home
    Assistant to group entities under a single device.

    :return: A dictionary containing device information.
    """
    return self.pod.device_info

  @property
  def native_value(self) -> StateType:
    """
    Get the native value of the sensor.

    This returns the result of the get_value function defined in the sensor
    description, if it exists.

    :return: The sensor value.
    """
    if self.entity_description.get_value:
      return self.entity_description.get_value(self.coordinator.data)

    return None


class FreeSleepSideSensor(
  CoordinatorEntity[FreeSleepCoordinator], SensorEntity
):
  """A class that represents a sensor for a Free Sleep Pod side."""

  entity_description: FreeSleepSensorDescription

  _attr_has_entity_name = True

  def __init__(
    self,
    coordinator: FreeSleepCoordinator,
    pod: Pod,
    side: Side,
    description: FreeSleepSensorDescription,
  ) -> None:
    """
    Initialize the Free Sleep Pod sensor.

    :param coordinator: The data update coordinator.
    :param pod: The Free Sleep Pod instance.
    :param side: The side of the pod (left or right).
    :param description: The entity description.
    """
    super().__init__(coordinator)

    self.pod = pod
    self.side = side
    self.entity_description = description
    self._attr_name = description.name
    self._attr_unique_id = f'{side.id}_{description.key}'

  @property
  def device_info(self) -> dict:
    """
    Return device information for the Free Sleep Pod. This is used by Home
    Assistant to group entities under a single device.

    :return: A dictionary containing device information.
    """
    return self.side.device_info

  @property
  def native_value(self) -> StateType:
    """
    Get the native value of the sensor.

    For sensors with requires_presence=True, returns None when presence has
    been absent for more than VITALS_STALE_MINUTES to avoid displaying stale
    biometric data when no one is in bed.

    :return: The sensor value, or None if presence is required but absent.
    """
    if (
      self.entity_description.requires_presence
      and not self.coordinator.is_vitals_valid(self.side.type)
    ):
      return None

    if self.entity_description.get_value:
      data = self.side.get_side_data(self.coordinator.data)
      return self.entity_description.get_value(data)

    return None
