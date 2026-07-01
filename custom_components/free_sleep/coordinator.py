"""
A module that defines the data update coordinator for Free Sleep Pod devices,
which is responsible for fetching and updating the device state periodically.
"""

from asyncio import gather
from datetime import UTC, datetime, timedelta
from logging import Logger
from typing import Any, TypedDict

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
  DataUpdateCoordinator,
  UpdateFailed,
)

from .api import FreeSleepAPI
from .constants import PodSide
from .logger import log


class PodState(TypedDict):
  """A class that represents the state of a Free Sleep Pod device."""

  services: dict[str, Any]
  settings: dict[str, Any]
  status: dict[str, Any]
  vitals: dict[PodSide, Any]
  presence: dict[PodSide, Any]
  sleep: dict[PodSide, Any]         # Most recent sleep record per side (or None)
  server_status: dict[str, Any]     # Internal service health statuses
  schedules: dict[PodSide, Any]     # Full weekly schedule per side


class FirmwareState(TypedDict):
  """A class that represents the firmware state of a Free Sleep Pod device."""

  current_version: str | None
  latest_version: str | None


class FreeSleepCoordinator(DataUpdateCoordinator[PodState]):
  """A class that coordinates data updates for a Free Sleep Pod device."""

  def __init__(
    self,
    hass: HomeAssistant,
    log: Logger,
    api: FreeSleepAPI,
    update_interval: int = 30,
    config_entry: ConfigEntry | None = None,
  ) -> None:
    """
    Initialize the Free Sleep Coordinator.

    :param hass: The Home Assistant instance.
    :param api: The Free Sleep API instance.
    """
    super().__init__(
      hass,
      log,
      name='Free Sleep Coordinator',
      update_method=self._async_update_data,
      update_interval=timedelta(seconds=update_interval),
      config_entry=config_entry,
    )

    self.api = api
    self.presence_false_since: dict[PodSide, datetime] = {}

  async def _async_update_data(self) -> PodState:
    """
    Fetch the latest data from the Free Sleep Pod device.

    :return: A `PodState` dictionary containing the latest status, settings, and
    vitals.
    """
    requests = [
      self.api.fetch_device_status(),
      self.api.fetch_settings(),
      self.api.fetch_vitals('left'),
      self.api.fetch_vitals('right'),
      self.api.fetch_services(),
      self.api.fetch_presence(),
    ]

    try:
      (
        status,
        settings,
        vitals_left,
        vitals_right,
        services,
        presence,
      ) = await gather(*requests)
    except TimeoutError as error:
      log.error(
        f'Timeout while fetching data from device at "{self.api.host}".'
      )
      raise UpdateFailed from error
    except ClientError as error:
      log.error(
        f'Client error while fetching data from device at "{self.api.host}": '
        f'{error}'
      )
      raise UpdateFailed from error
    except Exception as error:
      log.error(
        'Unexpected error while fetching data from device at'
        f'"{self.api.host}": {error}'
      )
      raise UpdateFailed from error

    vitals_dict: dict[PodSide, Any] = {
      'left': vitals_left,
      'right': vitals_right,
    }

    presence_dict: dict[PodSide, Any] = {
      'left': presence.get('left', {}),
      'right': presence.get('right', {}),
    }

    for side in ('left', 'right'):
      if presence_dict[side].get('present'):
        self.presence_false_since.pop(side, None)
      elif side not in self.presence_false_since:
        self.presence_false_since[side] = datetime.now(UTC)

    # Fetch optional data with graceful fallback — failures here do not
    # prevent the core coordinator data from being returned.
    optional = await gather(
      self.api.fetch_sleep('left'),
      self.api.fetch_sleep('right'),
      self.api.fetch_server_status(),
      self.api.fetch_schedules(),
      return_exceptions=True,
    )
    sleep_left_raw, sleep_right_raw, server_status_raw, schedules_raw = optional

    def _safe(val: Any, default: Any) -> Any:
      return default if isinstance(val, BaseException) else val

    sleep_left_list: list = _safe(sleep_left_raw, [])
    sleep_right_list: list = _safe(sleep_right_raw, [])

    return PodState(
      services=services,
      settings=settings,
      status=status,
      vitals=vitals_dict,
      presence=presence_dict,
      sleep={
        'left': sleep_left_list[-1] if sleep_left_list else None,
        'right': sleep_right_list[-1] if sleep_right_list else None,
      },
      server_status=_safe(server_status_raw, {}),
      schedules=_safe(schedules_raw, {}),
    )

  def is_vitals_valid(self, side: PodSide, grace_minutes: int = 5) -> bool:
    """
    Return True if vitals should be displayed for the given side.

    Stays True for up to `grace_minutes` after presence is lost, so brief
    detection gaps don't immediately blank the sensors.

    :param side: The side of the pod ("left" or "right").
    :param grace_minutes: How long to keep showing vitals after presence is
      lost.
    """
    if self.data is None:
      return False

    if self.data['presence'][side].get('present'):
      return True

    since = self.presence_false_since.get(side)
    if since is None:
      return False

    return datetime.now(UTC) - since < timedelta(minutes=grace_minutes)


class FirmwareUpdateCoordinator(DataUpdateCoordinator[FirmwareState]):
  """
  A class that coordinates fetching the latest firmware version from GitHub.
  This is defined separately to avoid making frequent requests to GitHub when
  the main coordinator updates every 30 seconds.
  """

  def __init__(
    self, hass: HomeAssistant, log: Logger, api: FreeSleepAPI
  ) -> None:
    """
    Initialize the GitHub Update Coordinator.

    :param hass: The Home Assistant instance.
    :param log: Logger instance.
    :param api: The Free Sleep API instance.
    """
    super().__init__(
      hass,
      log,
      name='Firmware Update Coordinator',
      update_method=self._async_update_data,
      update_interval=timedelta(hours=1),
    )

    self.api = api

  async def _async_update_data(self) -> FirmwareState:
    """
    Fetch the latest firmware version from GitHub.

    :return: The latest firmware version as a string, or None if not available.
    """
    try:
      current_version, latest_version = await gather(
        self.api.fetch_current_version(), self.api.fetch_latest_version()
      )

      return FirmwareState(
        current_version=current_version, latest_version=latest_version
      )
    except Exception as error:
      log.error('Unexpected error while fetching firmware version.')
      raise UpdateFailed from error
