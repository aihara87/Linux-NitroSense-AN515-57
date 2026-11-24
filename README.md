# Linux-NitroSense (Acer Nitro 5 AN515-57 — BIOS V1.17)

Custom fork of [Packss/Linux-NitroSense](https://github.com/Packss/Linux-NitroSense) adapted specifically for **Acer Nitro 5 AN515-57 (BIOS V1.17)** running on Linux (tested on **CachyOS / Arch Linux**, kernel `7.3.5-2-cachyos`, **Intel Core i5-11400H** + **NVIDIA GeForce RTX 3050**).

## Why This Fork Exists

On the **Nitro AN515-57 (BIOS V1.17)**, writing directly to raw EC registers via `ec_sys` (`0x21`/`0x22`) is immediately overridden back to `Auto` by firmware, and register `0x03` (battery charge limit) differs from older `ECS_AN515_46` mappings.

This repository adds a **`linuwu_sense` sysfs/hwmon backend** (`core/linuwu_sysfs.py`) and **Intel undervolting support** (`core/intelctl.py` via `intel-undervolt`), while keeping raw `ECWrite` as a fallback when `linuwu_sense` is not present.

---

## Tested Hardware & Feature Status (AN515-57 BIOS V1.17)

| Feature | Status | Backend / Notes |
|---|---|---|
| **Fan Control (Auto / Manual 0–100% / Max)** | Working | `/sys/devices/platform/acer-wmi/nitro_sense/fan_speed` (`linuwu_sense`) |
| **Fan RPM & Temps** | Working | `/sys/class/hwmon/hwmon*` (`name == "acer"`). GPU temp shows `0°` when dGPU is in runtime `suspended` (D3 power saving). |
| **Nitro Modes (Quiet / Default / Extreme / Turbo)** | Working | `/sys/firmware/acpi/platform_profile` (`Quiet`, `Extreme`, and `Turbo` require AC charger plugged in). |
| **Battery Charge Limit (80%)** | Working | `/sys/devices/platform/acer-wmi/nitro_sense/battery_limiter` |
| **CPU VCore Voltage Monitoring** | Working | `msr-tools` (`rdmsr 0x198`) |
| **Intel CPU Undervolt + Disable Button** | Working* | `intel-undervolt` (`0 mV` to `-90 mV` on `CPU` & `CPU Cache`, plus **Disable Undervolt**). *Requires BIOS Overclocking Lock (`MSR 0x194` bit 20) = `0`. |
| **USB Charging / KB 30s Timeout** | Disabled (Unsupported) | Firmware returns `-1` via WMI on this model; checkboxes are automatically disabled. |
| **4-Zone RGB Keyboard Tab** | Optional | Automatically hidden unless `/dev/acer-gkbbl-0` and `/dev/acer-gkbbl-static-0` (`acer-predator-module`) exist. |

---

## Requirements (Arch Linux / CachyOS)

1. **Disable Secure Boot** in BIOS (required to load unsigned DKMS kernel modules).
2. **Kernel Driver for Fan & WMI Control (`linuwu-sense-dkms-git`)** + matching kernel headers (e.g., `linux-cachyos-headers` or `linux-headers`):
   ```sh
   paru -S linuwu-sense-dkms-git
   ```
   Load the module immediately (or reboot so the installed modprobe blacklist for `acer_wmi` takes effect):
   ```sh
   sudo modprobe -r ec_sys acer_wmi 2>/dev/null
   sudo modprobe linuwu_sense
   ```
   Verify the WMI sysfs nodes exist:
   ```sh
   ls -la /sys/devices/platform/acer-wmi/nitro_sense/ /sys/firmware/acpi/platform_profile
   ```
3. **Intel Voltage Reading & Undervolting (`msr-tools` & `intel-undervolt`)**:
   ```sh
   sudo pacman -S msr-tools intel-undervolt
   ```
   *(Optional check before undervolting — `0` means unlocked):*
   ```sh
   sudo rdmsr 0x194 -f 20:20
   sudo intel-undervolt read
   ```
4. **Python Environment & Dependencies**:
   ```sh
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```
5. *(Optional)* **4-Zone RGB Keyboard**: Install [acer-predator-module](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module) if your AN515-57 unit has a 4-zone RGB keyboard.

---

## Usage

Run from the repository directory with `sudo -E` (root access is required for writing to `sysfs`, reading DMI/MSR, and running `intel-undervolt`):

```sh
sudo -E ./venv/bin/python main.py
```

### Undervolt Safety Notes
* Start conservatively (e.g., `-40 mV` or `-50 mV`) and test stability under both idle and load before trying lower offsets.
* Use the **Disable Undervolt** button (or select `0 mV (Off)`) to immediately reset `CPU` and `CPU Cache` offsets back to `0 mV` and set `enable no` in `/etc/intel-undervolt.conf`.

### NVIDIA GPU Power (`nvidia-powerd`)
After switching **Nitro Mode** (e.g., to `Extreme` or `Turbo`), you may need to restart `nvidia-powerd` so the updated GPU TGP limit is applied:
```sh
sudo systemctl restart nvidia-powerd
nvidia-smi
```

---

## Credits
* Upstream project: [Packss/Linux-NitroSense](https://github.com/Packss/Linux-NitroSense)
* Kernel WMI driver: [0x7375646F/Linuwu-Sense](https://github.com/0x7375646F/Linuwu-Sense)
