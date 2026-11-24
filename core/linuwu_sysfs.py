import glob
import os

NITRO_SENSE_DIR = "/sys/devices/platform/acer-wmi/nitro_sense"
PLATFORM_PROFILE_PATH = "/sys/firmware/acpi/platform_profile"
POWER_SUPPLY_DIR = "/sys/class/power_supply"


def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _write_text(path: str, value: str) -> tuple[bool, str | None]:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
        return True, None
    except OSError as exc:
        return False, str(exc)


def _read_int(path: str, default: int = 0) -> int:
    raw = _read_text(path)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def find_acer_hwmon_dir() -> str | None:
    """Return the hwmon directory exposed by the linuwu_sense/acer driver."""
    for path in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        if _read_text(os.path.join(path, "name")) == "acer":
            return path
    return None


def _find_power_supply(ps_type: str) -> str | None:
    for path in sorted(glob.glob(os.path.join(POWER_SUPPLY_DIR, "*"))):
        if _read_text(os.path.join(path, "type")) == ps_type:
            return path
    return None


class LinuwuBackend:
    """Sysfs/hwmon backend for the linuwu_sense kernel driver."""

    def __init__(self, base_dir: str = NITRO_SENSE_DIR):
        self.base_dir = base_dir
        self.hwmon_dir = find_acer_hwmon_dir()
        self.ac_dir = _find_power_supply("Mains")
        self.bat_dir = _find_power_supply("Battery")

    @classmethod
    def is_available(cls, base_dir: str = NITRO_SENSE_DIR) -> bool:
        return os.path.isdir(base_dir)

    def _attr_path(self, name: str) -> str:
        return os.path.join(self.base_dir, name)

    def read_sensors(self) -> tuple[int, int, int, int, int]:
        """Return (cpu_temp_c, gpu_temp_c, sys_temp_c, cpu_rpm, gpu_rpm)."""
        if not self.hwmon_dir:
            self.hwmon_dir = find_acer_hwmon_dir()
        if not self.hwmon_dir:
            return 0, 0, 0, 0, 0

        cpu_temp = _read_int(os.path.join(self.hwmon_dir, "temp1_input")) // 1000
        gpu_temp = _read_int(os.path.join(self.hwmon_dir, "temp2_input")) // 1000
        sys_temp = _read_int(os.path.join(self.hwmon_dir, "temp3_input")) // 1000
        cpu_rpm = _read_int(os.path.join(self.hwmon_dir, "fan1_input"))
        gpu_rpm = _read_int(os.path.join(self.hwmon_dir, "fan2_input"))
        return cpu_temp, gpu_temp, sys_temp, cpu_rpm, gpu_rpm

    def read_power_battery(self) -> tuple[int, str]:
        """Return (ac_online, battery_status)."""
        ac_online = (
            _read_int(os.path.join(self.ac_dir, "online"))
            if self.ac_dir
            else 0
        )
        bat_status = (
            _read_text(os.path.join(self.bat_dir, "status")) or "Unknown"
            if self.bat_dir
            else "Unknown"
        )
        return ac_online, bat_status

    def read_fan_speeds(self) -> tuple[int, int]:
        raw = _read_text(self._attr_path("fan_speed"))
        if not raw or "," not in raw:
            return 0, 0
        parts = raw.split(",", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return 0, 0

    def set_fan_speeds(self, cpu_pct: int, gpu_pct: int) -> tuple[bool, str | None]:
        cpu_pct = max(0, min(100, int(cpu_pct)))
        gpu_pct = max(0, min(100, int(gpu_pct)))
        return _write_text(self._attr_path("fan_speed"), f"{cpu_pct},{gpu_pct}")

    def read_platform_profile(self) -> str | None:
        return _read_text(PLATFORM_PROFILE_PATH)

    def set_platform_profile(self, profile: str) -> tuple[bool, str | None]:
        return _write_text(PLATFORM_PROFILE_PATH, profile)

    def read_battery_limiter(self) -> bool | None:
        val = _read_int(self._attr_path("battery_limiter"), default=-1)
        return None if val < 0 else bool(val)

    def set_battery_limiter(self, enabled: bool) -> tuple[bool, str | None]:
        return _write_text(self._attr_path("battery_limiter"), "1" if enabled else "0")

    def read_backlight_timeout(self) -> bool | None:
        val = _read_int(self._attr_path("backlight_timeout"), default=-1)
        return None if val < 0 else bool(val)

    def set_backlight_timeout(self, enabled: bool) -> tuple[bool, str | None]:
        return _write_text(
            self._attr_path("backlight_timeout"), "1" if enabled else "0"
        )

    def read_usb_charging(self) -> int | None:
        val = _read_int(self._attr_path("usb_charging"), default=-1)
        return None if val < 0 else val

    def set_usb_charging(self, enabled: bool) -> tuple[bool, str | None]:
        return _write_text(self._attr_path("usb_charging"), "30" if enabled else "0")
