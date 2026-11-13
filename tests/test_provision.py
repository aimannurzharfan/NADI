"""scripts/provision.py without boards: port detection, setup answers from .env, a fake board's setup dialog,
log checks, the sender MAC hand-over, and that no password is ever printed."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import provision as pv

ROOT = Path(__file__).resolve().parent.parent
WIFI_PASS = "fake-hotspot-password"
MQTT_PASS = "fake-recv-mqtt-password"
MQTT_CLIMATE_PASS = "fake-climate-mqtt-password"
ENV = {
    "NADI_WIFI_SSID": "NADI Hotspot",
    "NADI_WIFI_PASS": WIFI_PASS,
    "MQTT_LAN_IP": "192.168.43.10",
    "MQTT_DEVICE_IDS": "nadi-sim,nadi-recv-1,nadi-climate-1",
    "MQTT_PASSWORD_NADI_RECV_1": MQTT_PASS,
    "MQTT_PASSWORD_NADI_CLIMATE_1": MQTT_CLIMATE_PASS,
}
SECRETS = [WIFI_PASS, MQTT_PASS, MQTT_CLIMATE_PASS]


def port(device, description, vid=None, pid=None):
    return SimpleNamespace(device=device, description=description, vid=vid, pid=pid)


@pytest.fixture(autouse=True)
def built_firmware(tmp_path, monkeypatch):
    """Stand-in merged.bin files: the real ones are build output, not in git (so not on CI)."""
    for role in ("send", "recv"):
        fake = tmp_path / f"{role}_merged.bin"
        fake.write_bytes(b"\x00" * 16)
        monkeypatch.setitem(pv.ROLES[role], "bin", fake)


CP2102 = port("COM3", "Silicon Labs CP210x USB to UART Bridge (COM3)", 0x10C4, 0xEA60)
CH340 = port("COM5", "USB-SERIAL CH340 (COM5)", 0x1A86, 0x7523)
BLUETOOTH = port("COM4", "Standard Serial over Bluetooth link (COM4)")
OTHER_SILABS = port("COM8", "Silicon Labs CP2105 Dual USB to UART Bridge (COM8)", 0x10C4, 0xEA70)


# ---------- port detection ----------

@pytest.mark.parametrize("board", [CP2102, CH340])
def test_one_board_is_picked_among_other_ports(board):
    assert pv.find_port([BLUETOOTH, board, OTHER_SILABS]) == board.device


@pytest.mark.parametrize("ports,words", [
    ([], "No board found"),
    ([BLUETOOTH, OTHER_SILABS], "No board found"),
    ([CP2102, CH340], "2 boards found (COM3, COM5)"),
    ([CP2102, port("COM7", "Silicon Labs CP210x USB to UART Bridge (COM7)", 0x10C4, 0xEA60)],
     "2 boards found (COM3, COM7)"),
])
def test_none_or_several_boards_stop(ports, words):
    with pytest.raises(pv.ProvisionError, match=re.escape(words)):
        pv.find_port(ports)


def test_real_port_list_can_be_read():
    """The real serial port list (no board is plugged in on CI): either the one-board answer or a clear stop."""
    pytest.importorskip("serial")
    try:
        assert pv.find_port().startswith(("COM", "/dev/"))
    except pv.ProvisionError as e:
        assert "No board found" in str(e) or "boards found" in str(e)


# ---------- setup answers ----------

def test_sender_answers():
    answers = pv.setup_answers("send", ENV)
    assert [(a.prompt, a.value, a.secret) for a in answers] == [
        ("Wi-Fi name the receiver uses", "NADI Hotspot", False),
        ("Channel to use if that network is not found", "", False),  # Enter keeps 6
    ]


@pytest.mark.parametrize("role,mqtt", [("recv", MQTT_PASS), ("climate", MQTT_CLIMATE_PASS)])
def test_receiver_and_climate_answers_in_firmware_order(role, mqtt):
    answers = pv.setup_answers(role, ENV)
    assert [(a.prompt, a.value, a.secret) for a in answers] == [
        ("Wi-Fi name (2.4 GHz)", "NADI Hotspot", False),
        ("Wi-Fi password", WIFI_PASS, True),
        ("Broker address", "192.168.43.10", False),
        ("Broker port", "1883", False),
        ("MQTT password", mqtt, True),
        ("Room ID", "room1", False),
    ]


def source_between(path, start, end):
    text = (ROOT / path).read_text(encoding="utf-8")
    return text[text.index(start):text.index(end, text.index(start))]


@pytest.mark.parametrize("path,start,end,prompts", [
    ("firmware/csi_send/main/main.c", "static void run_setup", "esp_restart", pv.SEND_PROMPTS),
    ("firmware/csi_recv/main/main.c", "static void run_setup", "esp_restart", pv.BOARD_PROMPTS),
    ("firmware/climate_node/climate_node.ino", "void runSetup", "ESP.restart", pv.BOARD_PROMPTS),
])
def test_prompts_are_the_firmware_questions_in_its_order(path, start, end, prompts):
    body = source_between(path, start, end)
    positions = []
    for p in prompts:
        # the secret's question is the SECRET_NAME macro, "MQTT password" in local mode
        where = body.find("SECRET_NAME") if p == "MQTT password" else body.find(p)
        assert where >= 0, f"{p!r} is not asked in {path}"
        positions.append(where)
    assert positions == sorted(positions)
    if "MQTT password" in prompts:
        assert '#define SECRET_NAME "MQTT password"' in (ROOT / path).read_text(encoding="utf-8")


@pytest.mark.parametrize("change,key", [
    ({"NADI_WIFI_SSID": ""}, "NADI_WIFI_SSID"),
    ({"NADI_WIFI_SSID": "x" * 33}, "NADI_WIFI_SSID"),
    ({"NADI_WIFI_SSID": "Café"}, "NADI_WIFI_SSID"),
    ({"NADI_WIFI_PASS": ""}, "NADI_WIFI_PASS"),
    ({"NADI_WIFI_PASS": "short"}, "NADI_WIFI_PASS"),
    ({"MQTT_LAN_IP": ""}, "MQTT_LAN_IP"),
    ({"MQTT_LAN_IP": "laptop.local"}, "MQTT_LAN_IP"),
    ({"MQTT_PASSWORD_NADI_RECV_1": ""}, "MQTT_PASSWORD_NADI_RECV_1"),
])
def test_bad_env_stops_naming_the_key_not_the_value(change, key):
    env = {**ENV, **change}
    with pytest.raises(pv.ProvisionError) as e:
        pv.setup_answers("recv", env)
    assert key in str(e.value)
    for s in SECRETS + ["short"]:
        assert s not in str(e.value)


def test_sender_needs_no_password():
    assert pv.setup_answers("send", {"NADI_WIFI_SSID": "NADI Hotspot"})


def test_redact_blanks_every_secret():
    hide = pv.secrets_to_hide({**ENV, "MYSQL_PASSWORD": "nadi_local_pw"}, pv.setup_answers("recv", ENV))
    text = f"a {WIFI_PASS} b {MQTT_PASS} c {MQTT_CLIMATE_PASS} d nadi_local_pw"
    assert pv.redact(text, hide) == "a ******** b ******** c ******** d ********"


def test_network_warnings():
    assert pv.warn_network("recv", ENV, ips={"192.168.43.10"}, broker_up=True) == []
    w = pv.warn_network("recv", {**ENV, "MQTT_DEVICE_IDS": "nadi-sim"}, ips={"192.168.1.60"}, broker_up=False)
    assert len(w) == 3 and "192.168.1.60" in w[0] and "1883" in w[1] and "nadi-recv-1" in w[2]


# ---------- flashing ----------

def test_flash_retries_once_after_the_boot_buttons(capsys):
    calls, prompts = [], []

    def runner(cmd):
        calls.append(cmd)
        if len(calls) == 1:
            return 2, "Connecting......\nA fatal error occurred: Failed to connect to ESP32-S3: No serial data received."
        return 0, "Chip is ESP32-S3\nMAC: 34:85:18:AA:BB:CC\nHash of data verified.\n"

    assert pv.flash("send", "COM5", runner=runner, wait_enter=lambda: prompts.append(1)) == "34:85:18:aa:bb:cc"
    assert "Hold BOOT, tap RST, release BOOT, then press Enter" in capsys.readouterr().out
    assert prompts == [1] and len(calls) == 2
    assert "--before" not in calls[0] and calls[1][calls[1].index("--before") + 1] == "no_reset"
    assert calls[0][-3:] == ["write_flash", "0x0", str(pv.ROLES["send"]["bin"])] and "460800" in calls[0]


def test_flash_gives_up_after_the_retry():
    with pytest.raises(pv.ProvisionError, match="Flashing failed"):
        pv.flash("recv", "COM5", runner=lambda cmd: (2, "Failed to connect to ESP32-S3"), wait_enter=lambda: None)


def test_busy_port_says_close_the_monitor():
    with pytest.raises(pv.ProvisionError, match="Close any Serial Monitor"):
        pv.flash("recv", "COM5", runner=lambda cmd: (1, "could not open port 'COM5': PermissionError(13, "
                                                          "'Access is denied.')"), wait_enter=lambda: None)


def test_climate_compiles_then_uploads_with_the_checklist_fqbn(monkeypatch):
    monkeypatch.setattr(pv, "arduino_cli", lambda: "arduino-cli")
    calls = []
    pv.flash("climate", "COM6", runner=lambda cmd: calls.append(cmd) or (0, "MAC: 34:85:18:00:00:01\n"),
             wait_enter=lambda: None)
    assert [c[1] for c in calls] == ["compile", "upload"]
    fqbn = "esp32:esp32:esp32s3:CDCOnBoot=default,UploadMode=default,FlashSize=16M,PSRAM=opi," \
           "PartitionScheme=app3M_fat9M_16MB,FlashMode=dio"
    assert calls[1] == ["arduino-cli", "upload", "-p", "COM6", "--fqbn", fqbn, str(pv.CLIMATE_SKETCH)]
    assert fqbn in (ROOT / "docs" / "FLASH_TOMORROW.md").read_text(encoding="utf-8")


# ---------- a fake board on the serial port ----------

BOOT = {
    "send": "I (300) nadi_send: NADI CSI sender 1.1.0 is starting. Type setup and press Enter to change the Wi-Fi name or channel.\n",
    "recv": "I (310) nadi_recv: NADI CSI receiver 1.1.0 is starting. Device nadi-recv-1, room room1, one report every 10 s.\n",
    "climate": "NADI climate node 1.1.0 is starting. Type setup and press Enter to change the Wi-Fi network or broker.\n",
}
QUESTIONS = {
    "send": [("Wi-Fi name the receiver uses (2.4 GHz, no password needed) [not set]: ", False),
             ("Channel to use if that network is not found, 1 to 13 [6]: ", False)],
    "recv": [("Wi-Fi name (2.4 GHz) [not set]: ", False), ("Wi-Fi password [(not set), Enter keeps it]: ", True),
             ("Broker address (the laptop IP shown on the dashboard) [not set]: ", False), ("Broker port [1883]: ", False),
             ("MQTT password [(not set), Enter keeps it]: ", True), ("Room ID (for example room1) [room1]: ", False)],
}
QUESTIONS["climate"] = QUESTIONS["recv"]
AFTER = {
    "send": ("I (900) nadi_send: Found the Wi-Fi network \"NADI Hotspot\" on channel 11.\n"
             "I (910) nadi_send: Sending 50 packets per second on channel 11 from 1a:00:00:00:00:00.\n"
             "I (10910) nadi_send: Sent 500 packets on channel 11 in the last 10 s.\n"),
    "recv": ("I (500) wifi:mode : sta (34:85:18:aa:bb:01)\n"
             "I (520) nadi_recv: Listening for CSI from the sender 1a:00:00:00:00:00.\n"
             "I (2100) nadi_recv: Connected to \"NADI Hotspot\" on channel 11. IP address: 192.168.43.20.\n"
             "I (2400) nadi_recv: Connected to the MQTT broker at 192.168.43.10:1883.\n"
             "I (12400) nadi_recv: Report sent: 498 packets, motion_mean 0.0123, motion_std 0.0456, amp_var 0.000100, "
             "RSSI -40.0 dBm.\n"),
    "climate": ("Connected to \"NADI Hotspot\". IP address: 192.168.43.21.\n"
                "Connected to the MQTT broker at 192.168.43.10. Listening for the command ac_off.\n"
                "Climate report sent: 27.4 C, humidity 61.0%.\n"),
}


class FakeBoard:
    """Answers like the firmware: banner on reset, questions after "setup", * for each typed password character."""

    def __init__(self, role, after=None, leak=None, stale=""):
        self.role, self.after, self.leak = role, AFTER[role] if after is None else after, leak
        self.stale = stale  # printed by the old settings between "Saved." and the restart
        self.out = bytearray()
        self.typed = b""
        self.answers = []
        self.step = None
        self.dtr = self.rts = False

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        if getattr(self, "_rts", False) and not value:  # RTS released: the board restarts
            self.say(BOOT[self.role])
        self._rts = value

    def say(self, text):
        self.out += text.encode()

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, n):
        data, self.out[:] = bytes(self.out[:n]), self.out[n:]
        return data

    def flush(self):
        pass

    def close(self):
        pass

    def write(self, data):
        assert b"\r" not in data
        self.typed += data
        while b"\n" in self.typed:
            line, self.typed = self.typed.split(b"\n", 1)
            self.line(line.decode())

    def line(self, text):
        questions = QUESTIONS[self.role]
        if self.step is None:
            if text == "setup":
                self.step = 0
                self.say("\nSetup: type a new value and press Enter, or press Enter to keep the value in brackets.\n")
                self.say(questions[0][0])
            return
        secret = questions[self.step][1]
        self.answers.append(text)
        self.say(("*" * len(text) if secret else text) + "\r\n")
        self.step += 1
        if self.step < len(questions):
            self.say(questions[self.step][0])
        else:
            self.say("Saved. Restarting in 2 s to use them.\n" + self.stale + BOOT[self.role] + (self.leak or "") +
                     self.after)


def test_lines_from_the_old_settings_before_the_restart_do_not_count(monkeypatch, tmp_path, capsys):
    """Seen on SEND-1: the old run keeps logging until the restart. Its PASS lines must not hide a failure."""
    failing = 'W (900) nadi_recv: The Wi-Fi network "NADI Hotspot" refused the connection. Check the Wi-Fi password.\n'
    board = FakeBoard("recv", after=failing, stale=AFTER["recv"])
    assert run_main(monkeypatch, tmp_path, "recv", board) == 1
    assert "RECV-1 on COM5: FAIL" in capsys.readouterr().out


def run_main(monkeypatch, tmp_path, role, board, env=ENV, sender=None, args=()):
    monkeypatch.setattr(pv, "load_env", lambda: dict(env))
    monkeypatch.setattr(pv, "SENDER_FILE", tmp_path / "sender.json")
    if sender:
        pv.save_sender(sender)
    monkeypatch.setattr(pv, "check_receiver_build", lambda s: None)
    monkeypatch.setattr(pv, "warn_network", lambda r, e: [])
    monkeypatch.setattr(pv, "find_port", lambda: "COM5")
    monkeypatch.setattr(pv, "flash", lambda r, p: "34:85:18:aa:bb:cc")
    monkeypatch.setattr(pv, "open_serial", lambda p: board)
    monkeypatch.setattr(pv.time, "sleep", lambda s: None)
    return pv.main(["--role", role, "--seconds", "2", *args])


@pytest.mark.parametrize("role", ["send", "recv", "climate"])
def test_whole_run_passes_and_never_prints_a_password(monkeypatch, tmp_path, capsys, role):
    board = FakeBoard(role)
    assert run_main(monkeypatch, tmp_path, role, board) == 0
    out = capsys.readouterr()
    assert f"{pv.ROLES[role]['label']} on COM5: PASS" in out.out
    for s in SECRETS:
        assert s not in out.out and s not in out.err
    expected = [a.value for a in pv.setup_answers(role, ENV)]
    assert board.answers == expected  # the passwords did reach the board


def test_firmware_echoing_a_password_is_still_blanked(monkeypatch, tmp_path, capsys):
    leak = f"W (600) nadi_recv: debug pass={WIFI_PASS} secret={MQTT_PASS}\n"
    assert run_main(monkeypatch, tmp_path, "recv", FakeBoard("recv", leak=leak)) == 0
    out = capsys.readouterr().out
    assert "debug pass=******** secret=********" in out
    assert WIFI_PASS not in out and MQTT_PASS not in out


def test_sender_mac_and_channel_saved_for_the_receiver(monkeypatch, tmp_path, capsys):
    assert run_main(monkeypatch, tmp_path, "send", FakeBoard("send")) == 0
    saved = json.loads((tmp_path / "sender.json").read_text())
    assert saved["mac"] == "1a:00:00:00:00:00" and saved["channel"] == 11 and saved["network_found"] is True
    assert pv.load_sender(tmp_path / "sender.json") == saved


def test_receiver_on_another_channel_than_the_sender_fails(monkeypatch, tmp_path, capsys):
    sender = {"mac": "1a:00:00:00:00:00", "channel": 6}
    assert run_main(monkeypatch, tmp_path, "recv", FakeBoard("recv"), sender=sender) == 1
    out = capsys.readouterr().out
    assert "RECV-1 on COM5: FAIL" in out and "SEND-1 is on 6" in out


def test_receiver_matching_the_saved_sender_passes(monkeypatch, tmp_path, capsys):
    sender = {"mac": "1a:00:00:00:00:00", "channel": 11}
    assert run_main(monkeypatch, tmp_path, "recv", FakeBoard("recv"), sender=sender) == 0
    out = capsys.readouterr().out
    assert "11, same as SEND-1" in out and "listens for sender 1a:00:00:00:00:00, same as SEND-1" in out


def test_bad_env_stops_before_touching_the_board(monkeypatch, tmp_path, capsys):
    board = FakeBoard("recv")
    assert run_main(monkeypatch, tmp_path, "recv", board, env={**ENV, "NADI_WIFI_PASS": ""}) == 2
    assert "STOPPED: NADI_WIFI_PASS" in capsys.readouterr().out and board.answers == []


def test_board_that_never_asks_stops_with_a_clear_message(monkeypatch, tmp_path, capsys):
    class Silent(FakeBoard):
        def line(self, text):  # starts up but ignores "setup"
            pass

    monkeypatch.setattr(pv, "PROMPT_WAIT_S", 0.3)
    assert run_main(monkeypatch, tmp_path, "send", Silent("send")) == 2
    assert 'did not ask "Wi-Fi name the receiver uses"' in capsys.readouterr().out


# ---------- log checks ----------

def statuses(rows):
    return {r.name: r.status for r in rows}


def test_wrong_wifi_password_and_no_broker_fail_with_hints():
    log = ('W (900) nadi_recv: The Wi-Fi network "NADI Hotspot" refused the connection. Check the Wi-Fi password.\n')
    rows = pv.check_log("recv", log, final=True)
    assert statuses(rows)["Wi-Fi connected"] == "FAIL" and "NADI_WIFI_PASS" in rows[0].detail
    assert statuses(rows)["CSI packets received"] == "FAIL"


def test_receiver_without_sender_packets_fails():
    log = AFTER["recv"].split("I (12400)")[0] + "W (12400) nadi_recv: Only 0 CSI packets from the sender (1a:00:00:00:00:00)\n"
    rows = pv.check_log("recv", log, final=True)
    assert statuses(rows)["CSI packets received"] == "FAIL" and statuses(rows)["MQTT connected"] == "PASS"


def test_climate_dht_missing_fails():
    log = AFTER["climate"].split("Climate report")[0] + "The DHT22 did not answer. Check the wiring.\n"
    assert statuses(pv.check_log("climate", log, final=True))["Temperature read"] == "FAIL"


def test_sender_that_cannot_find_the_hotspot_fails():
    log = ('W (900) nadi_send: The Wi-Fi network "NADI Hotspot" was not found. Using the fixed channel 6. Check\n'
           "I (910) nadi_send: Sending 50 packets per second on channel 6 from 1a:00:00:00:00:00.\n")
    s = statuses(pv.check_log("send", log, final=True))
    assert s["Wi-Fi network found"] == "FAIL" and s["Packets sent"] == "FAIL" and s["Channel"] == "PASS"


@pytest.mark.parametrize("role", ["send", "recv", "climate"])
def test_log_patterns_are_the_firmware_messages(role):
    """Each message the checks look for is printed by the firmware (so a reworded message breaks this test)."""
    source = {
        "send": "firmware/csi_send/main/main.c", "recv": "firmware/csi_recv/main/main.c",
        "climate": "firmware/climate_node/climate_node.ino",
    }[role]
    text = (ROOT / source).read_text(encoding="utf-8")
    phrases = {
        "send": ["Found the Wi-Fi network", "was not found. Using the fixed channel", "packets per second on channel",
                 "packets on channel %d in the last 10 s"],
        "recv": ["\\\" on channel %d. IP address: ", "Listening for CSI from the sender", "Connected to the MQTT broker at",
                 "Report sent: %lu packets, motion_mean", "Only %lu CSI packets from the sender",
                 "refused the connection", "Fix the settings above with setup"],
        "climate": ["\\\". IP address: %s.", "Connected to the MQTT broker at %s.", "Climate report sent: %.1f C, humidity",
                    "The DHT22 did not answer", "refused the connection", "Type setup to fix the settings"],
    }[role]
    for p in phrases:
        assert p in text, f"{p!r} not in {source}"


# ---------- sender MAC compiled into the receiver ----------

def test_receiver_build_must_contain_the_sender_mac(tmp_path):
    sdk = tmp_path / "sdkconfig"
    sdk.write_text('CONFIG_NADI_SENDER_MAC="1a:00:00:00:00:00"\n')
    good = tmp_path / "good.bin"
    good.write_bytes(b"\x00junk1a:00:00:00:00:00\x00")
    pv.check_receiver_build({"mac": "1A:00:00:00:00:00", "channel": 11}, sdk, good)
    with pytest.raises(pv.ProvisionError, match="Sender MAC address = 1a:00:00:00:00:02"):
        pv.check_receiver_build({"mac": "1a:00:00:00:00:02", "channel": 11}, sdk, good)


def test_built_firmware_sender_and_receiver_macs_match():
    """The committed defaults: the sender transmits as the MAC the receiver listens for."""
    send = (ROOT / "firmware/csi_send/main/Kconfig.projbuild").read_text(encoding="utf-8")
    recv = (ROOT / "firmware/csi_recv/main/Kconfig.projbuild").read_text(encoding="utf-8")
    mac = re.compile(r'config NADI_SENDER_MAC\s+string "[^"]*"\s+default "([^"]+)"')
    assert mac.search(send).group(1) == mac.search(recv).group(1) == pv.DEFAULT_SENDER_MAC


def test_bad_sender_file_is_ignored(tmp_path):
    f = tmp_path / "sender.json"
    f.write_text('{"mac": "not a mac", "channel": 11}')
    assert pv.load_sender(f) is None
    f.write_text("{broken")
    assert pv.load_sender(f) is None
