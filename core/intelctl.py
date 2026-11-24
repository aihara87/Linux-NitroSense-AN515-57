import os
import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

INTEL_UNDERVOLT_CONF = "/etc/intel-undervolt.conf"
INTEL_UNDERVOLT_OPTIONS = [
    ("0 mV (Off)", 0),
    ("-25 mV", -25),
    ("-40 mV", -40),
    ("-50 mV", -50),
    ("-60 mV", -60),
    ("-70 mV", -70),
    ("-80 mV", -80),
    ("-90 mV", -90),
]


class CommandRunner(QObject):
    finished = pyqtSignal(str)  # Emits the full output when done

    def __init__(self):
        super().__init__()
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._handle_output)
        self.process.finished.connect(self._on_finished)
        self.output = ""  # Store output here

    def run(self, cmd, args):
        self.output = ""  # Reset output
        self.process.start(cmd, args)
        self.process.waitForFinished()

    def _handle_output(self):
        new_output = self.process.readAllStandardOutput().data().decode()
        self.output += new_output  # Append to stored output

    def _on_finished(self):
        self.finished.emit(self.output)  # Emit the full output

    def close(self):
        self.process.close()


def _run_intel_undervolt(args: list[str]) -> tuple[bool, str]:
    cmd = ["intel-undervolt", *args]
    if os.geteuid() != 0:
        cmd = ["sudo", *cmd]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except OSError as exc:
        return False, str(exc)
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, output


def _is_config_enabled(config_path: str = INTEL_UNDERVOLT_CONF) -> bool | None:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*enable\s+(yes|no)\b", line)
                if m:
                    return m.group(1) == "yes"
    except OSError:
        return None
    return None


def update_intel_undervolt_config(
    offset_mv: int,
    enabled: bool,
    config_path: str = INTEL_UNDERVOLT_CONF,
) -> None:
    """Update enable flag and CPU/Cache offsets in intel-undervolt.conf."""
    offset_mv = max(-150, min(0, int(offset_mv)))
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    seen_enable = False
    seen_cpu = False
    seen_cache = False
    enable_line = f"enable {'yes' if enabled else 'no'}\n"
    cpu_line = f"undervolt 0 'CPU' {offset_mv}\n"
    cache_line = f"undervolt 2 'CPU Cache' {offset_mv}\n"

    for line in lines:
        if re.match(r"^\s*enable\s+\S+", line):
            new_lines.append(enable_line)
            seen_enable = True
        elif re.match(r"^\s*undervolt\s+0\s+", line):
            new_lines.append(cpu_line)
            seen_cpu = True
        elif re.match(r"^\s*undervolt\s+2\s+", line):
            new_lines.append(cache_line)
            seen_cache = True
        else:
            new_lines.append(line)

    if not seen_enable:
        new_lines.insert(0, enable_line)
    if not seen_cpu:
        new_lines.append(cpu_line)
    if not seen_cache:
        new_lines.append(cache_line)

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def checkUndervoltStatus(self):
    if not shutil.which("intel-undervolt"):
        self.undervolt = "intel-undervolt not installed."
        return

    ok, output = _run_intel_undervolt(["read"])
    if not ok:
        self.undervolt = f"Failed to read undervolt: {output}"
        return

    enabled = _is_config_enabled()
    state = "Enabled" if enabled else "Disabled" if enabled is False else "Active"
    self.undervolt = f"Status: {state}\n{output}"


def applyUndervolt(self):
    if not shutil.which("intel-undervolt"):
        self.undervolt = "intel-undervolt not installed."
        return

    offset_mv = self.undervolt_dropdown.currentData()
    if offset_mv is None:
        offset_mv = 0
    if offset_mv == 0:
        disableUndervolt(self)
        return

    try:
        update_intel_undervolt_config(offset_mv, enabled=True)
    except OSError as exc:
        self.undervolt = f"Failed to update config: {exc}"
        return

    ok, output = _run_intel_undervolt(["apply"])
    if not ok:
        self.undervolt = f"Failed to apply undervolt: {output}"
        return
    checkUndervoltStatus(self)


def disableUndervolt(self):
    if not shutil.which("intel-undervolt"):
        self.undervolt = "intel-undervolt not installed."
        return

    try:
        update_intel_undervolt_config(0, enabled=True)
        ok, output = _run_intel_undervolt(["apply"])
        update_intel_undervolt_config(0, enabled=False)
    except OSError as exc:
        self.undervolt = f"Failed to disable undervolt: {exc}"
        return

    if not ok:
        self.undervolt = f"Failed to reset undervolt: {output}"
        return

    if hasattr(self, "undervolt_dropdown"):
        self.undervolt_dropdown.setCurrentIndex(0)
    checkUndervoltStatus(self)


voltage_process = QProcess()


def checkVoltage(self):
    ## https://askubuntu.com/questions/876286/how-to-monitor-the-vcore-voltage
    cmd, args = ("rdmsr", ["0x198", "-a", "-u", "--bitfield", "47:32"])
    if os.geteuid() != 0:
        cmd, args = ("sudo", [cmd, *args])
    voltage_process.start(cmd, args)
    voltage_process.waitForFinished(1000)
    voltage = voltage_process.readAllStandardOutput()

    if voltage:
        data = [
            int(line)
            for line in voltage.data().decode("utf-8").splitlines()
            if line.strip().isdigit()
        ]
        if not data:
            return
        avg_v = sum(data) / len(data)
        voltage = int(avg_v) / 8192

        self.voltage = voltage

        if voltage < self.minrecordedVoltage:
            self.minrecordedVoltage = voltage
        if voltage > self.maxrecordedVoltage:
            self.maxrecordedVoltage = voltage

