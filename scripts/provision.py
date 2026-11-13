"""Flash one NADI board, set it up over USB from .env, then check its log and print PASS/FAIL.

Plug in ONE board (the USB-C port labelled UART) and run from the repo root:

    .\\.venv\\Scripts\\python scripts\\provision.py --role send      # SEND-1     firmware/csi_send
    .\\.venv\\Scripts\\python scripts\\provision.py --role recv      # RECV-1     firmware/csi_recv (after SEND-1)
    .\\.venv\\Scripts\\python scripts\\provision.py --role climate   # CLIMATE-1  firmware/climate_node

Steps: find the single board port (CP2102 or CH340), flash, type "setup" and answer each question from .env (NADI_WIFI_SSID,
NADI_WIFI_PASS, MQTT_LAN_IP, port 1883, MQTT_PASSWORD_<DEVICE ID>, room room1), then read the log for 40 s.
Passwords only go to the board: they are never printed, and the board's output is shown with them blanked out.

SEND-1's CSI MAC address and channel are saved to data/provision/sender.json (git-ignored). The receiver has no
setup question for the sender MAC: it is compiled in (menuconfig "Sender MAC address", default 1a:00:00:00:00:00,
the same address the sender transmits as). So --role recv checks before flashing that the saved sender MAC is the
one built into firmware/csi_recv/build/merged.bin, and afterwards that the receiver listens for that MAC on
SEND-1's channel.

Options: --skip-flash (setup and log check only), --seconds N (log check time, default 40).
"""
import argparse
import ipaddress
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.mqtt_users import device_password_key  # noqa: E402

ENV = ROOT / ".env"
SENDER_FILE = ROOT / "data" / "provision" / "sender.json"
RECV_SDKCONFIG = ROOT / "firmware" / "csi_recv" / "sdkconfig"
CLIMATE_SECRETS = ROOT / "firmware" / "climate_node" / "secrets.h"
CLIMATE_SKETCH = ROOT / "firmware" / "climate_node"
CLIMATE_FQBN = ("esp32:esp32:esp32s3:CDCOnBoot=default,UploadMode=default,FlashSize=16M,PSRAM=opi,"
                "PartitionScheme=app3M_fat9M_16MB,FlashMode=dio")
# USB-serial chips on the DevKitC-1 boards: Silicon Labs CP2102 (most), WCH CH340 (some)
USB_SERIAL = {(0x10C4, 0xEA60): "CP2102", (0x1A86, 0x7523): "CH340"}
BAUD = 115200
ROOM = "room1"
DEFAULT_SENDER_MAC = "1a:00:00:00:00:00"
PROMPT_WAIT_S = 20          # for the first setup question
CLIMATE_PROMPT_WAIT_S = 60  # the climate node only reads serial after its start-up Wi-Fi and clock attempt (~35 s)

ROLES = {
    "send": {"label": "SEND-1", "banner": "NADI CSI sender", "bin": ROOT / "firmware" / "csi_send" / "build" / "merged.bin"},
    "recv": {"label": "RECV-1", "banner": "NADI CSI receiver", "bin": ROOT / "firmware" / "csi_recv" / "build" / "merged.bin"},
    "climate": {"label": "CLIMATE-1", "banner": "NADI climate node"},
}

# The setup questions, in the order the firmware asks them (copied from run_setup / runSetup)
SEND_PROMPTS = ["Wi-Fi name the receiver uses", "Channel to use if that network is not found"]
BOARD_PROMPTS = ["Wi-Fi name (2.4 GHz)", "Wi-Fi password", "Broker address", "Broker port", "MQTT password", "Room ID"]

CONNECT_FAILED = re.compile(r"Failed to connect|No serial data received|Wrong boot mode", re.I)
PORT_BUSY = re.compile(r"could not open port|Access is denied|port is busy", re.I)
MAC = r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})"


class ProvisionError(Exception):
    """Stop here and tell Aiman what to do. Messages never contain a password."""


@dataclass
class Answer:
    prompt: str
    value: str
    secret: bool = False


@dataclass
class Check:
    name: str
    status: str  # PASS, FAIL, WAIT (not seen yet) or "-" (information only)
    detail: str = ""


# ---------- settings ----------

def shown(path):
    """A path as printed: relative to the repo when it is inside it."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def load_env(path=ENV):
    if not path.exists():
        raise ProvisionError("No .env file. Copy .env.example to .env first.")
    return {k: (v or "") for k, v in dotenv_values(path).items()}


def compiled(path, pattern, default):
    """A value compiled into a board (sdkconfig or secrets.h, both git-ignored), or the default if not found."""
    try:
        m = re.search(pattern, path.read_text(encoding="utf-8", errors="replace"), re.M)
    except OSError:
        return default
    return m.group(1) if m else default


def device_id(role):
    if role == "recv":
        return compiled(RECV_SDKCONFIG, r'^CONFIG_NADI_DEVICE_ID="(.*)"', "nadi-recv-1")
    if role == "climate":
        return compiled(CLIMATE_SECRETS, r'^#define DEVICE_ID "(.*)"', "nadi-climate-1")
    return None


def printable(value):
    return all(" " <= c <= "~" for c in value)


def setup_answers(role, env):
    """Answers to the board's setup questions, in its order. Raises ProvisionError (naming the key, never the value)."""
    ssid = env.get("NADI_WIFI_SSID", "")
    if not ssid:
        raise ProvisionError("NADI_WIFI_SSID is empty in .env. Put the hotspot name there.")
    if len(ssid.encode()) > 32 or not printable(ssid):
        raise ProvisionError("NADI_WIFI_SSID must be at most 32 plain ASCII characters (the board's serial setup "
                             "accepts nothing else).")
    if role == "send":
        # Enter keeps the fallback channel (6); the sender finds the hotspot's real channel by its name
        return [Answer(SEND_PROMPTS[0], ssid), Answer(SEND_PROMPTS[1], "")]

    password = env.get("NADI_WIFI_PASS", "")
    if not 8 <= len(password) <= 63 or not printable(password):
        raise ProvisionError("NADI_WIFI_PASS in .env must be the hotspot password: 8 to 63 plain ASCII characters.")
    ip = env.get("MQTT_LAN_IP", "")
    try:
        ipaddress.IPv4Address(ip)
    except ValueError:
        raise ProvisionError("MQTT_LAN_IP in .env must be this laptop's IPv4 address on the hotspot (ipconfig, "
                             "Wireless LAN adapter Wi-Fi). Then: docker compose up -d --wait") from None
    key = device_password_key(device_id(role))
    mqtt_password = env.get(key, "")
    if not mqtt_password:
        raise ProvisionError(f"{key} is empty in .env. Run python scripts/mqtt_users.py, then "
                             "docker compose up -d --force-recreate mosquitto")
    if len(mqtt_password) > 64 or not printable(mqtt_password):
        raise ProvisionError(f"{key} must be at most 64 plain ASCII characters. Empty it and run "
                             "python scripts/mqtt_users.py to make a new one.")
    values = [ssid, password, ip, "1883", mqtt_password, ROOM]
    secret = {"Wi-Fi password", "MQTT password"}
    return [Answer(p, v, p in secret) for p, v in zip(BOARD_PROMPTS, values)]


def secrets_to_hide(env, answers):
    """Every password the board's output is scrubbed of: the setup answers plus any password-like .env value."""
    hide = {a.value for a in answers if a.secret}
    hide |= {v for k, v in env.items() if re.search(r"PASS|SECRET|TOKEN|_KEY$|_SK$", k) and len(v) >= 6}
    return sorted(hide, key=len, reverse=True)


def redact(text, secrets):
    for s in secrets:
        if s:
            text = text.replace(s, "********")
    return text


def warn_network(role, env, ips=None, broker_up=None):
    """Warnings (not stops) for the laptop side of MQTT: stale MQTT_LAN_IP, broker not listening, unknown device."""
    warnings = []
    ip = env.get("MQTT_LAN_IP", "")
    ips = local_ipv4s() if ips is None else ips
    if ips and ip not in ips:
        warnings.append(f"MQTT_LAN_IP {ip} is not one of this laptop's addresses now ({', '.join(sorted(ips))}). "
                        "Join the hotspot, update MQTT_LAN_IP, then docker compose up -d --wait")
    up = broker_open(ip) if broker_up is None else broker_up
    if not up:
        warnings.append(f"Nothing answers on {ip}:1883. Start Mosquitto: docker compose up -d --wait "
                        "(and allow port 1883 in Windows Firewall).")
    ids = [d.strip() for d in env.get("MQTT_DEVICE_IDS", "").split(",")]
    if device_id(role) not in ids:
        warnings.append(f"{device_id(role)} is not in MQTT_DEVICE_IDS, so the broker will refuse it. Add it, run "
                        "python scripts/mqtt_users.py and restart Mosquitto.")
    return warnings


def local_ipv4s():
    try:
        return {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return set()


def broker_open(ip, port=1883):
    try:
        socket.create_connection((ip, port), timeout=2).close()
        return True
    except OSError:
        return False


# ---------- sender MAC (receiver side) ----------

def load_sender(path=None):
    path = path or SENDER_FILE
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or not re.fullmatch(MAC, str(info.get("mac", ""))) or not str(info.get("channel", "")).isdigit():
        return None
    return info


def save_sender(info, path=None):
    path = path or SENDER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def check_receiver_build(sender, sdkconfig=RECV_SDKCONFIG, binary=ROLES["recv"]["bin"]):
    """Before flashing RECV-1: the MAC SEND-1 transmits as must be the one compiled into the receiver."""
    want = sender["mac"].lower()
    built = compiled(sdkconfig, r'^CONFIG_NADI_SENDER_MAC="(.*)"', DEFAULT_SENDER_MAC).lower()
    try:
        in_binary = want.encode() in binary.read_bytes()
    except OSError:
        raise ProvisionError(f"{shown(binary)} is missing. Build csi_recv first (firmware/README.md).") from None
    if built != want or not in_binary:
        raise ProvisionError(
            f"SEND-1 transmits as {want}, but RECV-1's firmware listens for {built}. The receiver's sender MAC is "
            "compiled in, not set over serial. Rebuild it: cd firmware\\csi_recv; ..\\idf.ps1 menuconfig > "
            f"NADI CSI receiver > Sender MAC address = {want}; ..\\idf.ps1 build; then run this again.")


# ---------- port and flashing ----------

def find_port(ports=None):
    """The one board port (CP2102 or CH340). Stops if there are none or several."""
    if ports is None:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
    boards = [p for p in ports if (p.vid, p.pid) in USB_SERIAL]
    if len(boards) == 1:
        return boards[0].device
    seen = ", ".join(f"{p.device} ({p.description})" for p in ports) or "none"
    if not boards:
        raise ProvisionError("No board found. Plug one board into the USB-C port labelled UART with a data cable "
                             "(Device Manager > Ports should show Silicon Labs CP210x USB to UART Bridge, or "
                             f"USB-SERIAL CH340). Ports seen: {seen}.")
    names = ", ".join(p.device for p in boards)
    raise ProvisionError(f"{len(boards)} boards found ({names}). Unplug all but the one to set up, then run "
                         "this again.")


def arduino_cli():
    found = shutil.which("arduino-cli") or Path.home() / ".local" / "bin" / "arduino-cli.exe"
    if not Path(found).exists():
        raise ProvisionError("arduino-cli not found (expected in ~/.local/bin). See docs/FLASH_TOMORROW.md.")
    return str(found)


def flash_command(role, port, manual_boot=False):
    if role == "climate":
        return [arduino_cli(), "upload", "-p", port, "--fqbn", CLIMATE_FQBN, str(CLIMATE_SKETCH)]
    cmd = [sys.executable, "-m", "esptool", "--chip", "esp32s3", "-p", port, "-b", "460800"]
    if manual_boot:
        cmd += ["--before", "no_reset"]  # already in download mode from the buttons
    return cmd + ["write_flash", "0x0", str(ROLES[role]["bin"])]


def run(cmd):
    """Run a command, showing its output as it comes. Returns (exit code, output)."""
    out = []
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for line in proc.stdout:
        print("  " + line.rstrip())
        out.append(line)
    return proc.wait(), "".join(out)


def flash(role, port, runner=run, wait_enter=input):
    """Flash the board; one retry in manual download mode if it would not connect. Returns the chip MAC."""
    if role == "climate":
        print("Compiling climate_node (quick if nothing changed)...")
        code, _ = runner([arduino_cli(), "compile", "--fqbn", CLIMATE_FQBN, str(CLIMATE_SKETCH)])
        if code:
            raise ProvisionError("The climate sketch did not compile (output above).")
    elif not ROLES[role]["bin"].exists():
        raise ProvisionError(f"{shown(ROLES[role]['bin'])} is missing. Build it first (firmware/README.md).")
    for attempt in (1, 2):
        print(f"Flashing {ROLES[role]['label']} on {port}...")
        code, out = runner(flash_command(role, port, manual_boot=attempt == 2))
        if code == 0:
            m = re.search(r"MAC: " + MAC, out)
            return m.group(1).lower() if m else ""
        if PORT_BUSY.search(out):
            raise ProvisionError(f"{port} is in use. Close any Serial Monitor or miniterm on it, then run this again.")
        if attempt == 1 and CONNECT_FAILED.search(out):
            print("\nHold BOOT, tap RST, release BOOT, then press Enter")
            wait_enter()
            continue
        break
    raise ProvisionError("Flashing failed (output above). Try another data cable or USB port, then run this again.")


# ---------- serial ----------

def open_serial(port):
    import serial
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, BAUD, 0.2
    ser.dtr = ser.rts = False  # opening the port must not hold the board in reset or in download mode
    ser.open()
    return ser


def restart(ser):
    """Hard reset through the auto-reset circuit (RTS pulls EN low), the same way esptool does after flashing."""
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False


class Console:
    """The board's serial output: shown live with passwords blanked out, and searched for prompts and log lines."""

    def __init__(self, ser, secrets=(), show=print):
        self.ser, self.secrets, self.show = ser, list(secrets), show
        self.text = ""
        self.pos = 0    # prompts are looked for after this point
        self.shown = 0  # output printed so far

    def pull(self):
        data = self.ser.read(self.ser.in_waiting or 1)
        if not data:
            return
        self.text += data.decode("utf-8", errors="replace").replace("\r", "")
        end = self.text.rfind("\n")
        if end >= self.shown:
            for line in self.text[self.shown:end].split("\n"):
                self.show("  | " + redact(line, self.secrets))
            self.shown = end + 1

    def wait_for(self, pattern, timeout):
        regex = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while True:
            m = regex.search(self.text, self.pos)
            if m:
                self.pos = m.end()
                return m
            if time.monotonic() > deadline:
                return None
            self.pull()

    def send_line(self, value):
        # "\n" only: the climate node would read the "\n" of "\r\n" as a second, empty answer
        self.ser.write((value + "\n").encode("ascii"))
        self.ser.flush()


def run_setup(con, role, answers, port):
    banner = ROLES[role]["banner"]
    if not con.wait_for(re.escape(banner), 10):
        print("No start-up message yet. Tap RST on the board now.")
        if not con.wait_for(re.escape(banner), 20):
            if not con.text.strip():
                raise ProvisionError(f"Nothing came from the board on {port}. Tap RST, check the cable is in the UART "
                                     "port, then run this again with --skip-flash.")
            print("Start-up message not seen; typing setup anyway.")
    print("Typing setup...")
    con.send_line("setup")
    first_wait = CLIMATE_PROMPT_WAIT_S if role == "climate" else PROMPT_WAIT_S
    for i, a in enumerate(answers):
        if not con.wait_for(re.escape(a.prompt) + r"[^\n]*?\]: ", first_wait if i == 0 else 10):
            raise ProvisionError(f'The board did not ask "{a.prompt}" (output above). Run this again with --skip-flash.')
        con.send_line(a.value)
        print(f"  > {a.prompt}: " + ("(hidden)" if a.secret else a.value or "(Enter, keep)"))
    m = con.wait_for(r"Saved\. Restarting|Nothing saved|setup cancelled|Could not save", 15)
    if not m or not m.group(0).startswith("Saved"):
        raise ProvisionError("The board did not save the settings (output above). Run this again with --skip-flash.")


# ---------- log checks ----------

def last(pattern, text):
    m = None
    for m in re.finditer(pattern, text):
        pass
    return m


def check_log(role, log, sender=None, chip_mac="", final=False, seconds=40):
    """PASS/FAIL rows from the board's log after setup. WAIT = not seen yet (FAIL once final)."""
    rows = []
    if role == "send":
        found = last(r'Found the Wi-Fi network "(.*)" on channel (\d+)\.', log)
        missing = last(r'The Wi-Fi network "(.*)" was not found\. Using the fixed channel (\d+)', log)
        sending = last(r"Sending \d+ packets per second on channel (\d+) from " + MAC, log)
        sent = last(r"Sent (\d+) packets on channel (\d+) in the last 10 s(?:; (\d+) could not be sent)?", log)
        if found:
            rows.append(Check("Wi-Fi network found", "PASS", f'"{found.group(1)}" on channel {found.group(2)}'))
        elif missing:
            rows.append(Check("Wi-Fi network found", "FAIL", f'"{missing.group(1)}" not found, using fixed channel '
                              f"{missing.group(2)}. Check NADI_WIFI_SSID and that the hotspot is 2.4 GHz."))
        else:
            rows.append(Check("Wi-Fi network found", "WAIT"))
        rows.append(Check("Channel", "PASS", sending.group(1)) if sending else Check("Channel", "WAIT"))
        if "sender MAC address" in log and "is not valid" in log:
            rows.append(Check("CSI sender MAC", "FAIL", "the compiled sender MAC is not valid (menuconfig)"))
        else:
            rows.append(Check("CSI sender MAC", "PASS", sending.group(2).lower()) if sending
                        else Check("CSI sender MAC", "WAIT"))
        rows.append(Check("MQTT connected", "-", "not used by the sender"))
        if sent and int(sent.group(1)) > 0:
            lost = f", {sent.group(3)} could not be sent" if sent.group(3) else ""
            rows.append(Check("Packets sent", "PASS", f"{sent.group(1)} in 10 s{lost}"))
        else:
            rows.append(Check("Packets sent", "FAIL" if sent else "WAIT", "0 in 10 s" if sent else ""))
    else:
        if role == "recv":
            wifi = last(r'Connected to "(.*)" on channel (\d+)\. IP address: ([\d.]+)', log)
            ip = wifi.group(3) if wifi else ""
        else:
            wifi = last(r'Connected to "(.*)"\. IP address: ([\d.]+)', log)
            ip = wifi.group(2) if wifi else ""
        wifi_bad = last(r'The Wi-Fi network "(.*)" (was not found|refused the connection)', log)
        if wifi:
            rows.append(Check("Wi-Fi connected", "PASS", f'"{wifi.group(1)}", IP {ip}'))
        elif wifi_bad:
            hint = "check NADI_WIFI_PASS" if "refused" in wifi_bad.group(2) else "check NADI_WIFI_SSID and 2.4 GHz"
            rows.append(Check("Wi-Fi connected", "FAIL", f'"{wifi_bad.group(1)}" {wifi_bad.group(2)}: {hint}'))
        elif re.search(r"Fix the settings above with setup|Type setup to fix the settings", log):
            rows.append(Check("Wi-Fi connected", "FAIL", "the board says its settings are incomplete (log above)"))
        else:
            rows.append(Check("Wi-Fi connected", "WAIT"))

        if role == "recv":
            if not wifi:
                rows.append(Check("Channel", "WAIT"))
            elif not sender:
                rows.append(Check("Channel", "PASS", f"{wifi.group(2)} (SEND-1 not set up from this laptop: not compared)"))
            elif int(wifi.group(2)) == int(sender["channel"]):
                rows.append(Check("Channel", "PASS", f"{wifi.group(2)}, same as SEND-1"))
            else:
                rows.append(Check("Channel", "FAIL", f"{wifi.group(2)}, but SEND-1 is on {sender['channel']}: tap RST "
                                  "on SEND-1 so it scans for the hotspot again"))
            listen = last(r"Listening for CSI from the sender " + MAC, log)
            sta = last(r"wifi:mode : sta \(" + MAC + r"\)", log)
            own = chip_mac or (sta.group(1).lower() if sta else "?")
            if not listen:
                rows.append(Check("MAC", "WAIT"))
            elif sender and listen.group(1).lower() != sender["mac"].lower():
                rows.append(Check("MAC", "FAIL", f"board {own}; listens for {listen.group(1).lower()}, SEND-1 is "
                                  f"{sender['mac']}"))
            else:
                same = ", same as SEND-1" if sender else ""
                rows.append(Check("MAC", "PASS", f"board {own}; listens for sender {listen.group(1).lower()}{same}"))
        else:
            rows.append(Check("Channel", "-", "not printed by the climate firmware"))
            rows.append(Check("MAC", "-", f"board {chip_mac}" if chip_mac else "not printed (shown when flashing)"))

        broker = last(r"Connected to the MQTT broker at ([\w.:-]+?)\.(?:\s|$)", log)
        if broker:
            rows.append(Check("MQTT connected", "PASS", f"broker {broker.group(1)}"))
        elif re.search(r"refused the login", log):
            rows.append(Check("MQTT connected", "FAIL", "broker refused the login: check the device is in "
                              "MQTT_DEVICE_IDS, run python scripts/mqtt_users.py, restart Mosquitto"))
        elif re.search(r"Could not reach the (MQTT )?broker", log):
            rows.append(Check("MQTT connected", "FAIL", "broker not reachable: check MQTT_LAN_IP, docker compose "
                              "up -d --wait, Windows Firewall port 1883"))
        else:
            rows.append(Check("MQTT connected", "WAIT"))

        if role == "recv":
            report = last(r"Report sent: (\d+) packets, motion_mean [\d.]+, motion_std ([\d.]+)", log)
            unsent = last(r"this report was not sent: (\d+) packets, motion_std ([\d.]+)", log)
            few = last(r"Only (\d+) CSI packets from the sender", log)
            if report:
                rows.append(Check("CSI packets received", "PASS", f"{report.group(1)} in one report, motion_std "
                                  f"{report.group(2)}"))
            elif unsent:
                rows.append(Check("CSI packets received", "PASS", f"{unsent.group(1)} (report not sent: no MQTT)"))
            elif few:
                rows.append(Check("CSI packets received", "FAIL", f"only {few.group(1)}: is SEND-1 powered and on "
                                  "the same channel?"))
            else:
                rows.append(Check("CSI packets received", "WAIT"))
        else:
            sent = last(r"Climate report sent: (-?[\d.]+) C, humidity ([\d.]+)%", log)
            unsent = last(r"this report was not sent: (-?[\d.]+) C, humidity ([\d.]+)%", log)
            if sent or unsent:
                m = sent or unsent
                note = "" if sent else " (report not sent: no MQTT)"
                rows.append(Check("Temperature read", "PASS", f"{m.group(1)} C, humidity {m.group(2)}%{note}"))
            elif "The DHT22 did not answer" in log:
                rows.append(Check("Temperature read", "FAIL", "DHT22 not answering: VCC 3.3 V, GND, DATA on GPIO 4"))
            else:
                rows.append(Check("Temperature read", "WAIT"))

    if final:
        for r in rows:
            if r.status == "WAIT":
                r.status, r.detail = "FAIL", f"not seen in {seconds} s"
    return rows


def watch(con, role, seconds, sender=None, chip_mac=""):
    """Read the log after setup until every check passes or the time is up.

    Only lines after the start-up message that follows "Saved." count: until the restart the board is still running
    on its old settings, and those lines must not pass a check."""
    banner = re.compile(re.escape(ROLES[role]["banner"]))
    print(f"Reading the board's log for up to {seconds} s...")

    def new_log():
        m = banner.search(con.text, con.pos)
        return con.text[m.end():] if m else ""

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        con.pull()
        rows = check_log(role, new_log(), sender, chip_mac)
        if all(r.status in ("PASS", "-") for r in rows):
            break
    return check_log(role, new_log(), sender, chip_mac, final=True, seconds=seconds)


def sender_info(rows, port, chip_mac):
    """What --role recv needs from SEND-1, or None if its MAC or channel was not seen."""
    by_name = {r.name: r for r in rows}
    mac, channel = by_name["CSI sender MAC"], by_name["Channel"]
    if mac.status != "PASS" or channel.status != "PASS":
        return None
    return {"mac": mac.detail, "channel": int(channel.detail), "network_found": by_name["Wi-Fi network found"].status
            == "PASS", "port": port, "chip_mac": chip_mac, "saved": datetime.now().isoformat(timespec="seconds")}


def print_summary(label, port, rows):
    ok = all(r.status in ("PASS", "-") for r in rows)
    print(f"\n{label} on {port}: {'PASS' if ok else 'FAIL'}")
    for r in rows:
        print(f"  {r.status:<5} {r.name:<22} {r.detail}")
    return ok


# ---------- main ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Flash and set up one NADI board over USB.")
    parser.add_argument("--role", required=True, choices=sorted(ROLES))
    parser.add_argument("--skip-flash", action="store_true", help="setup and log check only")
    parser.add_argument("--seconds", type=int, default=40, help="how long to read the log after setup")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    label = ROLES[args.role]["label"]
    try:
        env = load_env()
        answers = setup_answers(args.role, env)
        sender = load_sender()
        if args.role == "recv":
            if sender:
                check_receiver_build(sender)
            else:
                print(f"Note: SEND-1 has not been set up from this laptop ({shown(SENDER_FILE)} missing), "
                      "so the channel and sender MAC are not compared. Set up SEND-1 first if you can.")
        if args.role != "send":
            for w in warn_network(args.role, env):
                print("Warning: " + w)
        port = find_port()
        print(f"{label}: board found on {port}.")
        rows = []
        chip_mac = ""
        if args.skip_flash:
            rows.append(Check("Flash", "-", "skipped (--skip-flash)"))
        else:
            chip_mac = flash(args.role, port)
            rows.append(Check("Flash", "PASS", f"chip MAC {chip_mac}" if chip_mac else "done"))
        ser = open_serial(port)
        try:
            con = Console(ser, secrets_to_hide(env, answers))
            restart(ser)
            run_setup(con, args.role, answers, port)
            rows += watch(con, args.role, args.seconds, sender if args.role == "recv" else None, chip_mac)
        finally:
            ser.close()
    except ProvisionError as e:
        print(f"\nSTOPPED: {e}")
        return 2
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    ok = print_summary(label, port, rows)
    if args.role == "send":
        info = sender_info(rows, port, chip_mac)
        if info:
            save_sender(info)
            print(f"Saved SEND-1's MAC {info['mac']} and channel {info['channel']} to "
                  f"{shown(SENDER_FILE)} for --role recv.")
        else:
            print("SEND-1's MAC and channel were not seen, so nothing was saved for --role recv.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
