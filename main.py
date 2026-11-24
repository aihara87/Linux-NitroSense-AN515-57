import enum
import os
import sys

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette

import utils.keyboard as keyboard
from core.device_regs import CPU_TYPE, ECS, KEYBOARD_UNSUPPORTED_MODELS, model
from core.ecwrite import ECWrite
from core.linuwu_sysfs import LinuwuBackend
from ui.frontend import Ui_NitroSense

if not ECS:
    sys.exit(1)

CONFIG_FOLDER = "/etc/nitrosense/"
UPDATE_INTERVAL_MS = 1000  # 1 sec interval


## ------------------------------##
## -------Nitro Fan Mode------##
class PFS(enum.Enum):
    Manual = 0
    Auto = 1
    Turbo = 2


if CPU_TYPE == "AMD":
    from core.amdctl import applyUndervolt, checkUndervoltStatus, checkVoltage
elif CPU_TYPE == "Intel":
    from core.intelctl import (
        INTEL_UNDERVOLT_OPTIONS,
        applyUndervolt,
        checkUndervoltStatus,
        checkVoltage,
        disableUndervolt,
    )
else:

    def checkUndervoltStatus(self):
        self.undervolt = "Undervolt not supported for this CPU type."

    def applyUndervolt(self):
        self.undervolt = "Undervolt not supported for this CPU type."

    def checkVoltage(self):
        self.voltage = "Voltage not supported for this CPU type."


## ------------------------------##
## -------Main QT Window---------##


class MainWindow(QtWidgets.QDialog, Ui_NitroSense):
    def __init__(self):
        super().__init__()
        self._initialize_variables()
        self.setupUi(self)
        self._initialize_ec_handler()
        self._initialize_ui()
        self.setUpdateUITimer()

    def _initialize_variables(self):
        self.turboEnabled = False
        self.cpufanspeed = 0
        self.gpufanspeed = 0
        self.cpuTemp = 0
        self.gpuTemp = 0
        self.sysTemp = 0
        self.voltage = 0.5
        self.undervolt = ""
        self.minrecordedVoltage = 2.0
        self.maxrecordedVoltage = 0
        self.selected_color = (255, 255, 255)
        self.powerPluggedIn = False
        self.onBatteryPower = False
        self.displayOverdrive = False
        self.nitroMode = ECS.DEFAULTMODE.value
        self.usbCharging = ECS.USBCHARGINGON.value
        self.cpuMode = ECS.CPU_AUTO_MODE.value
        self.gpuMode = ECS.GPU_AUTO_MODE.value
        self.cpuFanMode = PFS.Auto
        self.gpuFanMode = PFS.Auto
        self.cpuFanSpeed = 0
        self.gpuFanSpeed = 0
        self.KB30Timeout = ECS.KB_30_AUTO_OFF.value
        self.batteryChargeLimit = ECS.BATTERYLIMITOFF.value
        self.linuwu = None
        self.ECHandler = None
        self._batStatusText = "Unknown"
        self.keyboardSupported = self._is_keyboard_supported()

    def _is_keyboard_supported(self):
        if model in KEYBOARD_UNSUPPORTED_MODELS:
            return False
        return os.path.exists(keyboard.CHARACTER_DEVICE) and os.path.exists(
            keyboard.CHARACTER_DEVICE_STATIC
        )

    def _initialize_ec_handler(self):
        if LinuwuBackend.is_available():
            self.linuwu = LinuwuBackend()
            print("Using 'linuwu_sense' sysfs/hwmon backend.")
            return
        self.ECHandler = ECWrite()
        self.ECHandler.ec_refresh()

    def _initialize_ui(self):
        checkUndervoltStatus(self)
        self.checkPowerTempFan()
        self.checkNitroStatus()
        if self.keyboardSupported:
            self.kbLoadConfig()
        if not self.linuwu:
            self.loadConfig()
        self.setupGUI()

    # ----------------------------------------------------
    # Initialise the frame, check all registers and set the appropriate widgets
    def setupGUI(self):
        if not self.keyboardSupported:
            keyboard_tab_index = self.fan_control_tab.indexOf(self.keyboard_tab)
            if keyboard_tab_index != -1:
                self.fan_control_tab.removeTab(keyboard_tab_index)

        # when any of the radio buttons are clicked, also save the current settings

        self.global_auto.clicked.connect(self.setGlobalAutoMode)
        self.global_turbo.clicked.connect(self.setTurboMode)

        self.cpu_auto.clicked.connect(self.cpuauto)
        self.cpu_manual.clicked.connect(self.cpusetmanual)
        self.cpu_turbo.clicked.connect(self.cpumax)
        self.gpu_auto.clicked.connect(self.gpuauto)
        self.gpu_manual.clicked.connect(self.gpusetmanual)
        self.gpu_turbo.clicked.connect(self.gpumax)
        self.cpuManualSlider.valueChanged.connect(self.cpumanual)
        self.cpuManualSlider.setEnabled(True)
        self.gpuManualSlider.valueChanged.connect(self.gpumanual)
        self.gpuManualSlider.setEnabled(True)
        self.exit_button.clicked.connect(self.shutdown)

        self.undervolt_button.clicked.connect(lambda: applyUndervolt(self))
        if CPU_TYPE == "Intel":
            self.undervolt_dropdown.clear()
            for label, mv in INTEL_UNDERVOLT_OPTIONS:
                self.undervolt_dropdown.addItem(label, mv)
            self.disable_undervolt_button = QtWidgets.QPushButton(parent=self.tab)
            self.disable_undervolt_button.setMaximumSize(
                self.undervolt_button.maximumSize()
            )
            self.disable_undervolt_button.setFont(self.undervolt_button.font())
            self.disable_undervolt_button.setText("Disable Undervolt")
            self.disable_undervolt_button.setObjectName("disable_undervolt_button")
            self.verticalLayout_6.addWidget(self.disable_undervolt_button)
            self.disable_undervolt_button.clicked.connect(
                lambda: disableUndervolt(self)
            )
        if self.keyboardSupported:
            self.color_button.clicked.connect(lambda: self.saveAndRun(self.kbSelectColor))
            self.apply_button.clicked.connect(lambda: self.saveAndRun(self.kbApplySettings))
            self.save_button.clicked.connect(lambda: self.saveAndRun(self.kbSaveConfig))
            self.load_button.clicked.connect(lambda: self.saveAndRun(self.kbLoadConfig))

        # Set the 30 sec backlight timer
        if self.KB30Timeout == int(ECS.KB_30_AUTO_OFF.value, 0):
            self.KBTimerCB.setChecked(False)
        else:
            self.KBTimerCB.setChecked(True)

        # Set the USB charging indicator
        if self.usbCharging == int(ECS.USBCHARGINGON.value, 0):
            self.usbChargingCB.setChecked(True)
        elif self.usbCharging == int(ECS.USBCHARGINGOFF.value, 0):
            self.usbChargingCB.setChecked(False)
        else:
            print("Error read EC register for USB Charging: " + str(self.usbCharging))

        # Set the charge limit indicator
        if self.batteryChargeLimit == int(ECS.BATTERYLIMITON.value, 0):
            self.chargeLimit.setChecked(True)
            self.batteryChargeLimitValue.setText("On ")
        elif self.batteryChargeLimit == int(ECS.BATTERYLIMITOFF.value, 0):
            self.chargeLimit.setChecked(False)
            self.batteryChargeLimitValue.setText("Off")
        else:
            print(
                "Error read EC register for Charge Limit: "
                + str(self.batteryChargeLimit)
            )

        if self.linuwu:
            if self.linuwu.read_backlight_timeout() is None:
                self.KBTimerCB.setEnabled(False)
                self.KBTimerCB.setToolTip("Not supported by firmware on this model")
            if self.linuwu.read_usb_charging() is None:
                self.usbChargingCB.setEnabled(False)
                self.usbChargingCB.setToolTip("Not supported by firmware on this model")

        self.setNitroMode()
        self.setFanMode()

        # ----------------------------------------------------

        self.quietModeCB.clicked["bool"].connect(self.setQuietMode)
        self.defaultModeCB.clicked["bool"].connect(self.setDefaultMode)
        self.extremeModeCB.clicked["bool"].connect(self.setExtremeMode)
        # self.trackpadCB.clicked['bool'].connect(self.toggletrackpad)
        self.KBTimerCB.clicked["bool"].connect(self.togglekbauto)
        self.usbChargingCB.clicked["bool"].connect(self.toggleUSBCharging)
        self.chargeLimit.clicked["bool"].connect(self.togglePowerLimit)

    # Set the current fan and turbo mode
    def setFanMode(self):
        if self.cpuMode == int(ECS.CPU_AUTO_MODE.value, 0):
            self.cpuFanMode = PFS.Auto
            self.cpu_auto.setChecked(True)
        elif self.cpuMode == int(ECS.CPU_TURBO_MODE.value, 0) or self.cpuMode == int(
            "0xA8", 0
        ):
            self.cpuFanMode = PFS.Turbo
            self.cpu_turbo.setChecked(True)
            if not self.linuwu:
                self.turboEnabled = True
        elif self.cpuMode == int(ECS.CPU_MANUAL_MODE.value, 0):
            self.cpuFanMode = PFS.Manual
            self.cpu_manual.setChecked(True)
        else:
            print("Warning: Unknow CPU fan mode value '" + str(self.cpuMode) + "'")

        if self.gpuMode == int(ECS.GPU_AUTO_MODE.value, 0) or self.gpuMode == int(
            "0x00", 0
        ):
            self.gpuFanMode = PFS.Auto
            self.gpu_auto.setChecked(True)
        elif self.gpuMode == int(ECS.GPU_TURBO_MODE.value, 0):
            self.gpuFanMode = PFS.Turbo
            self.gpu_turbo.setChecked(True)
        elif self.gpuMode == int(ECS.GPU_MANUAL_MODE.value, 0):
            self.gpuFanMode = PFS.Manual
            self.gpu_manual.setChecked(True)
        else:
            print("Warning: Unknow GPU fan mode value '" + str(self.gpuMode) + "'")

        if self.turboEnabled:
            self.global_turbo.setChecked(True)
            self.cpu_turbo.setChecked(True)
            self.gpu_turbo.setChecked(True)
            if not self.linuwu:
                self.nitroMode = int(ECS.EXTREMEMODE.value, 0)
                self.setTurboMode()
        elif self.cpuFanMode == PFS.Auto and self.gpuFanMode == PFS.Auto:
            self.global_auto.setChecked(True)
        elif self.global_turbo.isChecked():
            self.global_turbo.setAutoExclusive(False)
            self.global_turbo.setChecked(False)
            self.global_turbo.setAutoExclusive(True)

    # Create a timer to update the UI
    def setUpdateUITimer(self):
        print("Setting up callback timer for %d(ms)" % UPDATE_INTERVAL_MS)
        self.my_timer = QTimer()
        self.my_timer.timeout.connect(self.updateNitroStatus)
        self.my_timer.start(UPDATE_INTERVAL_MS)

    def _pct_to_mode_and_ec(self, pct, auto_val, turbo_val, manual_val):
        if pct >= 100:
            return PFS.Turbo, int(turbo_val, 0)
        if pct <= 0:
            return PFS.Auto, int(auto_val, 0)
        return PFS.Manual, int(manual_val, 0)

    def _sync_linuwu_state(self):
        cpu_pct, gpu_pct = self.linuwu.read_fan_speeds()
        self.cpuFanSpeed = cpu_pct
        self.gpuFanSpeed = gpu_pct
        self.cpuFanMode, self.cpuMode = self._pct_to_mode_and_ec(
            cpu_pct,
            ECS.CPU_AUTO_MODE.value,
            ECS.CPU_TURBO_MODE.value,
            ECS.CPU_MANUAL_MODE.value,
        )
        self.gpuFanMode, self.gpuMode = self._pct_to_mode_and_ec(
            gpu_pct,
            ECS.GPU_AUTO_MODE.value,
            ECS.GPU_TURBO_MODE.value,
            ECS.GPU_MANUAL_MODE.value,
        )
        self.turboEnabled = cpu_pct >= 100 and gpu_pct >= 100

        profile = self.linuwu.read_platform_profile()
        profile_map = {
            "quiet": ECS.QUIETMODE.value,
            "balanced": ECS.DEFAULTMODE.value,
            "balanced-performance": ECS.EXTREMEMODE.value,
            "performance": ECS.EXTREMEMODE.value,
        }
        mapped = profile_map.get(profile, ECS.DEFAULTMODE.value)
        self.nitroMode = int(mapped, 0)

        limiter = self.linuwu.read_battery_limiter()
        if limiter is not None:
            self.batteryChargeLimit = int(
                ECS.BATTERYLIMITON.value if limiter else ECS.BATTERYLIMITOFF.value, 0
            )
        kb_to = self.linuwu.read_backlight_timeout()
        self.KB30Timeout = int(
            ECS.KB_30_AUTO_ON.value if kb_to else ECS.KB_30_AUTO_OFF.value, 0
        )
        usb = self.linuwu.read_usb_charging()
        self.usbCharging = int(
            ECS.USBCHARGINGON.value if (usb is not None and usb > 0) else ECS.USBCHARGINGOFF.value,
            0,
        )

    # ----------------------------------------------------
    # Read the various EC registers and update the GUI
    def checkNitroStatus(self):
        if self.linuwu:
            self._sync_linuwu_state()
        else:
            self.cpuMode = self.ECHandler.ec_read(
                int(ECS.CPU_FAN_MODE_CONTROL.value, 0)
            )
            self.gpuMode = self.ECHandler.ec_read(
                int(ECS.GPU_FAN_MODE_CONTROL.value, 0)
            )
            self.KB30Timeout = self.ECHandler.ec_read(int(ECS.KB_30_SEC_AUTO.value, 0))
            self.usbCharging = self.ECHandler.ec_read(
                int(ECS.POWEROFFUSBCHARGING.value, 0)
            )
            self.nitroMode = self.ECHandler.ec_read(int(ECS.NITROMODE.value, 0))
            self.batteryChargeLimit = self.ECHandler.ec_read(
                int(ECS.BATTERYCHARGELIMIT.value, 0)
            )
            self.cpuFanSpeed = self.ECHandler.ec_read(
                int(ECS.CPU_MANUAL_SPEED_CONTROL.value, 0)
            )
            self.gpuFanSpeed = self.ECHandler.ec_read(
                int(ECS.GPU_MANUAL_SPEED_CONTROL.value, 0)
            )
        self.cpuManualSlider.setSliderPosition(
            max(0, min(20, int(self.cpuFanSpeed / 5)))
        )
        self.gpuManualSlider.setSliderPosition(
            max(0, min(20, int(self.gpuFanSpeed / 5)))
        )

    # ----------------------------------------------------
    # Read the newest register updates
    def checkPowerTempFan(self):
        if self.linuwu:
            self._sync_linuwu_state()
            (
                self.cpuTemp,
                self.gpuTemp,
                self.sysTemp,
                self.cpufanspeed,
                self.gpufanspeed,
            ) = self.linuwu.read_sensors()
            self.powerPluggedIn, self._batStatusText = self.linuwu.read_power_battery()
            return

        # Refresh the EC registers first before reading values
        # -optimisation, read EC registers once per update, prevents hangs/unresponsive GUI
        self.ECHandler.ec_refresh()

        self.cpuMode = self.ECHandler.ec_read(int(ECS.CPU_FAN_MODE_CONTROL.value, 0))
        self.gpuMode = self.ECHandler.ec_read(int(ECS.GPU_FAN_MODE_CONTROL.value, 0))
        self.powerPluggedIn = self.ECHandler.ec_read(int(ECS.POWERSTATUS.value, 0))
        self.onBatteryPower = self.ECHandler.ec_read(int(ECS.BATTERYSTATUS.value, 0))
        self.nitroMode = self.ECHandler.ec_read(int(ECS.NITROMODE.value, 0))
        self.batteryChargeLimit = self.ECHandler.ec_read(
            int(ECS.BATTERYCHARGELIMIT.value, 0)
        )

        self.cpuTemp = self.ECHandler.ec_read(int(ECS.CPUTEMP.value, 0))
        self.gpuTemp = self.ECHandler.ec_read(int(ECS.GPUTEMP.value, 0))
        self.sysTemp = self.ECHandler.ec_read(int(ECS.SYSTEMP.value, 0))

        cpufanspeedHighBits = self.ECHandler.ec_read(
            int(ECS.CPUFANSPEEDHIGHBITS.value, 0)
        )
        cpufanspeedLowBits = self.ECHandler.ec_read(
            int(ECS.CPUFANSPEEDLOWBITS.value, 0)
        )
        # example
        # cpufanspeed = '0x068B'
        # 1675
        self.cpufanspeed = cpufanspeedLowBits << 8 | cpufanspeedHighBits

        gpufanspeedHighBits = self.ECHandler.ec_read(
            int(ECS.GPUFANSPEEDHIGHBITS.value, 0)
        )
        gpufanspeedLowBits = self.ECHandler.ec_read(
            int(ECS.GPUFANSPEEDLOWBITS.value, 0)
        )
        self.gpufanspeed = gpufanspeedLowBits << 8 | gpufanspeedHighBits
        # print("cpufanspeed: " + str(cpufanspeed))
        # print("gpufanspeed: " + gpufanspeed)

    def _target_fan_pct(self, mode, slider):
        if mode == PFS.Auto:
            return 0
        if mode == PFS.Turbo:
            return 100
        return max(1, min(100, slider.value() * 5))

    def _apply_linuwu_fans(self):
        cpu_pct = self._target_fan_pct(self.cpuFanMode, self.cpuManualSlider)
        gpu_pct = self._target_fan_pct(self.gpuFanMode, self.gpuManualSlider)
        ok, err = self.linuwu.set_fan_speeds(cpu_pct, gpu_pct)
        if not ok:
            print(f"Error setting fan speed: {err}")
        self.turboEnabled = cpu_pct >= 100 and gpu_pct >= 100

    def _apply_linuwu_profile(self, profile):
        ok, err = self.linuwu.set_platform_profile(profile)
        if not ok:
            print(f"Error setting platform profile '{profile}': {err}")
        self._sync_linuwu_state()
        self.setNitroMode()

    # ---------Radio Button callback functions------------
    def setQuietMode(self):
        if self.linuwu:
            self.cpuFanMode = PFS.Auto
            self.gpuFanMode = PFS.Auto
            self.turboEnabled = False
            self._apply_linuwu_profile("quiet")
            self.setFanMode()
            return
        self.ECHandler.ec_write(
            int(ECS.NITROMODE.value, 0), int(ECS.QUIETMODE.value, 0)
        )
        self.setGlobalAuto()

    def setDefaultMode(self):
        if self.linuwu:
            self._apply_linuwu_profile("balanced")
            return
        self.ECHandler.ec_write(
            int(ECS.NITROMODE.value, 0), int(ECS.DEFAULTMODE.value, 0)
        )
        self.setGlobalAuto()

    def setExtremeMode(self):
        if self.linuwu:
            self._apply_linuwu_profile("balanced-performance")
            return
        self.ECHandler.ec_write(
            int(ECS.NITROMODE.value, 0), int(ECS.EXTREMEMODE.value, 0)
        )
        self.setGlobalAuto()

    def setTurboMode(self):
        if self.linuwu:
            self.cpuFanMode = PFS.Turbo
            self.gpuFanMode = PFS.Turbo
            self.turboEnabled = True
            self._apply_linuwu_fans()
            self._apply_linuwu_profile("performance")
            self.setFanMode()
            return
        self.ECHandler.ec_write(
            int(ECS.NITROMODE.value, 0), int(ECS.EXTREMEMODE.value, 0)
        )
        self.setGlobalTurbo()

    def setGlobalAutoMode(self):
        if self.linuwu:
            self.cpuFanMode = PFS.Auto
            self.gpuFanMode = PFS.Auto
            self.turboEnabled = False
            self._apply_linuwu_fans()
            self._apply_linuwu_profile("balanced")
            self.setFanMode()
            return
        self.ECHandler.ec_write(
            int(ECS.NITROMODE.value, 0), int(ECS.DEFAULTMODE.value, 0)
        )
        self.turboEnabled = False
        self.cpuauto()
        self.gpuauto()
        self.global_auto.setChecked(True)
        self.cpu_auto.setChecked(True)
        self.gpu_auto.setChecked(True)

    def setGlobalAuto(self):
        if self.turboEnabled:
            self.turboEnabled = False

            self.cpuauto()
            self.gpuauto()

            self.global_auto.setChecked(True)
            self.cpu_auto.setChecked(True)
            self.gpu_auto.setChecked(True)

    def setGlobalTurbo(self):
        if not self.turboEnabled:
            self.turboEnabled = True

            self.cpumax()
            self.gpumax()

            self.global_turbo.setChecked(True)
            self.cpu_turbo.setChecked(True)
            self.gpu_turbo.setChecked(True)

    def cpuauto(self):
        self.cpuFanMode = PFS.Auto
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.CPU_FAN_MODE_CONTROL.value, 0), int(ECS.CPU_AUTO_MODE.value, 0)
        )

    def cpumax(self):
        self.cpuFanMode = PFS.Turbo
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.CPU_FAN_MODE_CONTROL.value, 0), int(ECS.CPU_TURBO_MODE.value, 0)
        )

    def cpusetmanual(self):
        self.cpuFanMode = PFS.Manual
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.CPU_FAN_MODE_CONTROL.value, 0), int(ECS.CPU_MANUAL_MODE.value, 0)
        )

    def cpumanual(self, level):
        if self.linuwu:
            self.cpuFanMode = PFS.Manual
            self.cpu_manual.setChecked(True)
            self._apply_linuwu_fans()
            return
        speed = max(0, min(100, level * 5))
        self.ECHandler.ec_write(int(ECS.CPU_MANUAL_SPEED_CONTROL.value, 0), speed)

    def gpuauto(self):
        self.gpuFanMode = PFS.Auto
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.GPU_FAN_MODE_CONTROL.value, 0), int(ECS.GPU_AUTO_MODE.value, 0)
        )

    def gpumax(self):
        self.gpuFanMode = PFS.Turbo
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.GPU_FAN_MODE_CONTROL.value, 0), int(ECS.GPU_TURBO_MODE.value, 0)
        )

    def gpusetmanual(self):
        self.gpuFanMode = PFS.Manual
        if self.linuwu:
            self._apply_linuwu_fans()
            return
        self.ECHandler.ec_write(
            int(ECS.GPU_FAN_MODE_CONTROL.value, 0), int(ECS.GPU_MANUAL_MODE.value, 0)
        )

    def gpumanual(self, level):
        if self.linuwu:
            self.gpuFanMode = PFS.Manual
            self.gpu_manual.setChecked(True)
            self._apply_linuwu_fans()
            return
        speed = max(0, min(100, level * 5))
        self.ECHandler.ec_write(int(ECS.GPU_MANUAL_SPEED_CONTROL.value, 0), speed)

    # Toggle 30 seconds keyboard backlight timer
    def togglekbauto(self, tog):
        if self.linuwu:
            self.linuwu.set_backlight_timeout(bool(tog))
            return
        if not tog:
            self.ECHandler.ec_write(
                int(ECS.KB_30_SEC_AUTO.value, 0), int(ECS.KB_30_AUTO_OFF.value, 0)
            )
        else:
            self.ECHandler.ec_write(
                int(ECS.KB_30_SEC_AUTO.value, 0), int(ECS.KB_30_AUTO_ON.value, 0)
            )

    # USB charging whilst off
    def toggleUSBCharging(self, tog):
        if self.linuwu:
            self.linuwu.set_usb_charging(bool(tog))
            return
        if tog:
            self.ECHandler.ec_write(
                int(ECS.POWEROFFUSBCHARGING.value, 0), int(ECS.USBCHARGINGON.value, 0)
            )
        else:
            self.ECHandler.ec_write(
                int(ECS.POWEROFFUSBCHARGING.value, 0), int(ECS.USBCHARGINGOFF.value, 0)
            )

    # Toggle Power Limit
    def togglePowerLimit(self, tog):
        if self.linuwu:
            ok, err = self.linuwu.set_battery_limiter(bool(tog))
            if not ok:
                print(f"Error setting battery limiter: {err}")
            self._sync_linuwu_state()
            self.setBatteryStatus()
            return
        if tog:
            self.ECHandler.ec_write(
                int(ECS.BATTERYCHARGELIMIT.value, 0), int(ECS.BATTERYLIMITON.value, 0)
            )
        else:
            self.ECHandler.ec_write(
                int(ECS.BATTERYCHARGELIMIT.value, 0), int(ECS.BATTERYLIMITOFF.value, 0)
            )

    # ----------------------------------------------------

    # Update the Battery status
    def setBatteryStatus(self):
        if self.linuwu:
            batteryStat = self._batStatusText
        else:
            batteryStat = "Discharging"
            if self.onBatteryPower == int(ECS.BATTERYPLUGGEDINANDCHARGING.value, 0):
                batteryStat = "Charging"
            elif self.onBatteryPower == int(ECS.BATTERYDRAINING.value, 0):
                batteryStat = "Discharging"
            elif self.onBatteryPower == int(ECS.BATTERYOFF.value, 0):
                batteryStat = "Battery Not In Use"
            else:
                print(
                    "Error read EC register for Battery Status: "
                    + str(hex(self.onBatteryPower))
                )

        self.batteryStatusValue.setText(batteryStat)

        # Set the battery charge indicator
        if self.batteryChargeLimit == int(ECS.BATTERYLIMITON.value, 0):
            self.batteryChargeLimitValue.setText("On")
        elif self.batteryChargeLimit == int(ECS.BATTERYLIMITOFF.value, 0):
            self.batteryChargeLimitValue.setText("Off")

    # Update the Nitro state
    def setNitroMode(self):
        # print("nitroModeValue: " + str(self.nitroMode))
        if self.nitroMode == int(ECS.QUIETMODE.value, 0):
            self.nitroModeValue.setText("Quiet\t")
            self.quietModeCB.setChecked(True)
        elif self.nitroMode == int(ECS.DEFAULTMODE.value, 0):
            self.nitroModeValue.setText("Default\t")
            self.defaultModeCB.setChecked(True)
        elif self.nitroMode == int(ECS.EXTREMEMODE.value, 0):
            self.nitroModeValue.setText("Extreme\t")
            self.extremeModeCB.setChecked(True)
        else:
            print("Error read EC register for Nitro Mode: " + str(self.nitroMode))

    # keyboard
    def kbSelectColor(self):
        if not self.keyboardSupported:
            return

        # open color dialog with current color selected
        color = QtWidgets.QColorDialog.getColor(
            initial=QtGui.QColor.fromRgb(*self.selected_color)
        )
        if color.isValid():
            self.selected_color = (color.red(), color.green(), color.blue())

    def kbApplySettings(self):
        if not self.keyboardSupported:
            return

        mode = self.mode_combo.currentIndex()
        zone = self.zone_combo.currentIndex()
        speed = self.speed_spin.value()
        brightness = self.brightness_spin.value()
        direction = self.direction_combo.currentIndex() + 1
        red, green, blue = self.selected_color

        keyboard.set_mode(mode, zone, speed, brightness, direction, red, green, blue)

    def kbSaveConfig(self):
        if not self.keyboardSupported:
            return

        if not os.path.exists(CONFIG_FOLDER + "rbg.conf"):
            os.system(f"mkdir -p {CONFIG_FOLDER}")
            os.system(f"touch {CONFIG_FOLDER + 'rbg.conf'}")
        path = f"{CONFIG_FOLDER + 'rbg.conf'}"
        with open(path, "w") as f:
            f.write(f"{self.mode_combo.currentIndex()}\n")
            f.write(f"{self.zone_combo.currentIndex()}\n")
            f.write(f"{self.speed_spin.value()}\n")
            f.write(f"{self.brightness_spin.value()}\n")
            f.write(f"{self.direction_combo.currentIndex()}\n")
            f.write(f"{self.selected_color[0]}\n")
            f.write(f"{self.selected_color[1]}\n")
            f.write(f"{self.selected_color[2]}\n")

    def kbLoadConfig(self):
        if not self.keyboardSupported:
            return

        if not os.path.exists(CONFIG_FOLDER + "rbg.conf"):
            return
        path = f"{CONFIG_FOLDER + 'rbg.conf'}"
        with open(path, "r") as f:
            self.mode_combo.setCurrentIndex(int(f.readline()))
            self.zone_combo.setCurrentIndex(int(f.readline()))
            self.speed_spin.setValue(int(f.readline()))
            self.brightness_spin.setValue(int(f.readline()))
            self.direction_combo.setCurrentIndex(int(f.readline()))
            self.selected_color = (
                int(f.readline()),
                int(f.readline()),
                int(f.readline()),
            )
        self.kbApplySettings()

    def saveConfig(self):
        if self.linuwu:
            return
        if not os.path.exists(CONFIG_FOLDER + "nitrosense.conf"):
            os.system(f"mkdir -p {CONFIG_FOLDER}")
            os.system(f"touch {CONFIG_FOLDER + 'nitrosense.conf'}")
        path = f"{CONFIG_FOLDER + 'nitrosense.conf'}"
        with open(path, "w") as f:
            f.write(f"{self.cpuMode}\n")
            f.write(f"{self.gpuMode}\n")
            f.write(f"{self.KB30Timeout}\n")
            f.write(f"{self.usbCharging}\n")
            f.write(f"{self.nitroMode}\n")
            f.write(f"{self.batteryChargeLimit}\n")

    def loadConfig(self):
        if not os.path.exists(CONFIG_FOLDER + "nitrosense.conf"):
            return
        path = f"{CONFIG_FOLDER + 'nitrosense.conf'}"
        with open(path, "r") as f:
            self.cpuMode = int(f.readline())
            self.gpuMode = int(f.readline())
            self.KB30Timeout = int(f.readline())
            self.usbCharging = int(f.readline())
            self.nitroMode = int(f.readline())
            self.batteryChargeLimit = int(f.readline())
        self.setFanMode()
        self.setNitroMode()
        self.checkPowerTempFan()
        self.setBatteryStatus()

    def saveAndRun(self, function):
        function()
        self.saveConfig()

    # Update the UI state
    def updateNitroStatus(self):
        checkVoltage(self)
        # print(self.voltage)
        minmaxVoltages = (
            str("%1.2f" % self.minrecordedVoltage)
            + " / "
            + str("%1.2f" % self.maxrecordedVoltage)
        )
        # print(minmaxVoltages)
        self.voltageValue.setText(str("%1.2f" % self.voltage))
        self.voltageMinMaxValue.setText(minmaxVoltages)

        if self.undervoltStatus.toPlainText() != self.undervolt:
            self.undervoltStatus.setText(self.undervolt)

        self.checkPowerTempFan()

        if self.linuwu:
            self.setFanMode()
        else:
            if (
                self.cpuMode == int(ECS.CPU_TURBO_MODE.value, 0)
                or self.cpuMode == int("0xA8", 0)
            ) and self.gpuMode == int(ECS.GPU_TURBO_MODE.value, 0):
                if not self.turboEnabled:
                    print("Turbo enabled")
                    self.setTurboMode()

            if self.cpuMode == int(ECS.CPU_AUTO_MODE.value, 0) and self.gpuMode == int(
                ECS.GPU_AUTO_MODE.value, 0
            ):
                if self.turboEnabled:
                    print("Turbo disabled")
                    self.setDefaultMode()

        self.setBatteryStatus()
        self.setNitroMode()

        # self.voltageChart.update(float("%1.2f" % self.voltage))
        # self.cpuChart.update(self.cpuTemp)
        # self.gpuChart.update(self.gpuTemp)
        # self.sysChart.update(self.sysTemp)
        # self.cpuFanChart.update(self.cpufanspeed)
        # self.gpuFanChart.update(self.gpufanspeed)
        #
        self.cpuFanSpeedValue.setText(str(self.cpufanspeed) + " RPM")
        self.gpuFanSpeedValue.setText(str(self.gpufanspeed) + " RPM")
        self.cpuTempValue.setText(str(self.cpuTemp) + "°")
        self.gpuTempValue.setText(str(self.gpuTemp) + "°")
        self.sysTempValue.setText(str(self.sysTemp) + "°")
        #
        if self.linuwu:
            self.powerStatusValue.setText(
                "Plugged In" if self.powerPluggedIn else "On Battery"
            )
        else:
            self.powerStatusValue.setText(str(self.powerPluggedIn))

    # ----------------------------------------------------
    # Exit the program cleanly
    def shutdown(self):
        print("Cleaning up..")
        if self.ECHandler:
            self.ECHandler.shutdown_ec()
        print("Exiting")
        sys.exit(0)


app = QtWidgets.QApplication(sys.argv)
application = MainWindow()
app.setApplicationName("Linux NitroSense")
# Makes the window not resizeable
application.setFixedSize(500, 700)

application.setWindowIcon(QtGui.QIcon("nitro-sense.ico"))
# Set global window opacity
# application.setWindowOpacity(0.97)

# Dark theme implementation
palette = QPalette()
palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
palette.setColor(QPalette.ColorRole.NoRole, QColor(53, 53, 53))
app.setPalette(palette)
application.setPalette(palette)
application.show()
app.exec()
sys.exit()
