"""The firmware's JSON matches the data contract and the server accepts it; firmware messages follow the
house style; secrets stay out of git. No boards, broker or database needed."""
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts import mqtt_users
from server import main
from sim import fake_board, fake_sensor

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE = ROOT / "firmware"
SOURCES = [FIRMWARE / "csi_send" / "main" / "main.c", FIRMWARE / "csi_recv" / "main" / "main.c",
           FIRMWARE / "climate_node" / "climate_node.ino"]

# Printed by the C code itself (firmware/csi_recv/test/run_host_test.sh, line "fixed:") for
# motion_mean 0.12345, motion_std 0.04567, amp_var 0.0007891, rssi_mean -48.25, n_packets 987
# and health firmware 1.1.0, uptime 3600 s, Wi-Fi -55 dBm, 180000 bytes free, 2 dropped
C_OUTPUT = ('{"services":[{"service_id":"csi","properties":{"room_id":"room1","ts":1761800000,"motion_mean":0.1235,'
            '"motion_std":0.0457,"amp_var":0.000789,"rssi_mean":-48.2,"n_packets":987,"fw_version":"1.1.0",'
            '"uptime_s":3600,"wifi_rssi":-55,"free_heap":180000,"dropped":2}}]}')
FIXED = {"motion_mean": 0.12345, "motion_std": 0.04567, "amp_var": 0.0007891, "rssi_mean": -48.25, "n_packets": 987}
FIXED_HEALTH = {"fw_version": "1.1.0", "uptime_s": 3600, "wifi_rssi": -55, "free_heap": 180000, "dropped": 2}
HEALTH_KEYS = ["fw_version", "uptime_s", "wifi_rssi", "free_heap", "dropped"]


def test_fake_board_sends_the_same_bytes_as_the_c_code():
    assert fake_board.csi_payload("room1", 1761800000, FIXED, FIXED_HEALTH) == C_OUTPUT


def test_csi_report_matches_the_data_contract():
    body = json.loads(fake_board.csi_payload("room1", 1761800000, fake_board.WALKING))
    assert list(body) == ["services"] and len(body["services"]) == 1
    svc = body["services"][0]
    assert svc["service_id"] == "csi"
    assert list(svc["properties"]) == ["room_id", "ts", "motion_mean", "motion_std", "amp_var", "rssi_mean", "n_packets",
                                       *HEALTH_KEYS]
    p = svc["properties"]
    assert isinstance(p["ts"], int) and isinstance(p["n_packets"], int)
    assert isinstance(p["fw_version"], str) and all(isinstance(p[k], int) for k in HEALTH_KEYS[1:])
    assert len(json.dumps(body)) < 4096
    assert all(isinstance(p[k], float) for k in ("motion_mean", "motion_std", "amp_var", "rssi_mean"))


def test_climate_report_matches_the_data_contract():
    body = json.loads(fake_board.climate_payload("room2", 0, 24.34, 61.0, FIXED_HEALTH))
    svc = body["services"][0]
    assert svc["service_id"] == "climate"
    assert svc["properties"] == {"room_id": "room2", "ts": 0, "temp_c": 24.3, "humidity": 61.0, **FIXED_HEALTH}


def test_topic_is_the_iotda_report_topic():
    assert fake_board.report_topic("nadi-recv-1") == fake_sensor.report_topic("nadi-recv-1")


def test_server_ingests_firmware_json(monkeypatch):
    saved = []
    monkeypatch.setattr(main.store, "save_csi", lambda room, ts, count, p: saved.append(("csi", room, ts, p)))
    monkeypatch.setattr(main.store, "save_climate", lambda room, ts, p: saved.append(("climate", room, ts, p)))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    monkeypatch.setattr(main.validate, "clock", lambda: 1761800000 + 20)  # the fixed ts above is "now"
    for payload in (C_OUTPUT, fake_board.climate_payload("room1", 1761800000, 24.3, 61.5)):
        assert main.ingest(json.loads(payload)["services"]) == 1
    assert saved[0][:3] == ("csi", "room1", 1761800000) and saved[0][3]["n_packets"] == 987
    assert saved[1][:3] == ("climate", "room1", 1761800000) and saved[1][3]["temp_c"] == 24.3


def test_ts_zero_means_server_clock(monkeypatch):
    """Boards without internet send ts 0; the server stamps the report with its own time."""
    stamps = []
    monkeypatch.setattr(main.store, "save_csi", lambda room, ts, count, p: stamps.append(ts))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    main.ingest(json.loads(fake_board.csi_payload("room1", 0, FIXED))["services"])
    assert stamps[0] > 1700000000


def string_literals(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)  # comments are not shown to anyone
    return [s for s in re.findall(r'"((?:[^"\\\n]|\\.)*)"', text) if re.search(r"[A-Za-z]{3}", s)]


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.parent.name if p.parent.name != "main" else p.parent.parent.name)
def test_firmware_messages_follow_the_house_style(path):
    banned = re.compile(r"aircon|air-con|\bppl\b|\bcolor|\bcenter\b|\bmeters?\b|\w+iz(e|ed|ing|ation)\b|behavior|—", re.I)
    messages = string_literals(path)
    assert len(messages) > 10
    bad = [m for m in messages if banned.search(m)]
    assert not bad, bad


def test_firmware_secrets_are_not_committed():
    for path in ("firmware/csi_recv/sdkconfig", "firmware/csi_send/sdkconfig", "firmware/climate_node/secrets.h",
                 "deploy/mosquitto/passwd", ".env"):
        assert subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0, path
    for kconfig in FIRMWARE.glob("*/main/Kconfig.projbuild"):
        text = kconfig.read_text(encoding="utf-8")
        for name in ("PASSWORD", "SECRET"):
            for block in re.findall(rf"config NADI_\w*{name}\w*\n(.*?)(?=\n\s*config |\nendmenu)", text, flags=re.S):
                assert 'default ""' in block, (kconfig, name)
    example = (FIRMWARE / "climate_node" / "secrets.example.h").read_text(encoding="utf-8")
    for name in ("WIFI_PASSWORD", "MQTT_PASSWORD", "IOTDA_DEVICE_SECRET"):
        assert re.search(rf'^#define {name} ""(\s|$)', example, flags=re.M), name


def test_n16r8_flash_and_psram_defaults():
    for project in ("csi_send", "csi_recv"):
        text = (FIRMWARE / project / "sdkconfig.defaults").read_text(encoding="utf-8")
        for line in ("CONFIG_IDF_TARGET=\"esp32s3\"", "CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y", "CONFIG_SPIRAM=y",
                     "CONFIG_SPIRAM_MODE_OCT=y"):
            assert line in text.splitlines(), (project, line)


def test_mosquitto_password_hash_format():
    salt = b"0123456789ab"
    h = mqtt_users.mosquitto_hash("pw", salt)
    _, kind, iterations, salt_b64, digest_b64 = h.split("$")
    assert kind == "7" and int(iterations) == mqtt_users.ITERATIONS
    assert base64.b64decode(salt_b64) == salt
    assert base64.b64decode(digest_b64) == hashlib.pbkdf2_hmac("sha512", b"pw", salt, mqtt_users.ITERATIONS)


def test_each_device_has_its_own_password_key():
    keys = [mqtt_users.device_password_key(d) for d in ("nadi-sim", "nadi-recv-1", "nadi-climate-1")]
    assert keys == ["MQTT_PASSWORD_NADI_SIM", "MQTT_PASSWORD_NADI_RECV_1", "MQTT_PASSWORD_NADI_CLIMATE_1"]
    # IDs that would map to the same key are refused by mqtt_users.py, so two boards never share a password
    assert mqtt_users.device_password_key("nadi-recv-1") == mqtt_users.device_password_key("nadi_recv_1")


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.parent.name if p.parent.name != "main" else p.parent.parent.name)
def test_boards_take_setup_show_reset_over_serial(path):
    text = path.read_text(encoding="utf-8")
    for command in ("setup", "show", "reset"):
        assert f'"{command}"' in text, command


def test_passwords_only_ever_printed_masked():
    """Every place a board prints a password or secret goes through the masking helper."""
    recv = (FIRMWARE / "csi_recv" / "main" / "main.c").read_text(encoding="utf-8")
    climate = (FIRMWARE / "climate_node" / "climate_node.ino").read_text(encoding="utf-8")
    assert re.findall(r"printf\([^;]*s_cfg\.(?:pass|secret)[^;]*;", recv) == [
        m for m in re.findall(r"printf\([^;]*s_cfg\.(?:pass|secret)[^;]*;", recv) if "nadi_cfg_mask" in m]
    assert re.findall(r"printf\([^;]*cfg(?:Pass|Secret)[^;]*;", climate) == [
        m for m in re.findall(r"printf\([^;]*cfg(?:Pass|Secret)[^;]*;", climate) if "masked(" in m]
    assert "nadi_console_read(line, sizeof(line), secret" in recv  # typed passwords echo as *


def test_self_recovery_and_led_defaults():
    recv = (FIRMWARE / "csi_recv" / "main" / "main.c").read_text(encoding="utf-8")
    climate = (FIRMWARE / "climate_node" / "climate_node.ino").read_text(encoding="utf-8")
    assert "#define RESTART_AFTER_S 300" in recv and "#define RESTART_AFTER_MS 300000UL" in climate
    assert "setSocketTimeout(5)" in climate and "esp_task_wdt_add" in climate
    for project in ("csi_send", "csi_recv"):
        assert "CONFIG_ESP_TASK_WDT_PANIC=y" in (FIRMWARE / project / "sdkconfig.defaults").read_text(encoding="utf-8")
        assert re.search(r"config NADI_LED_GPIO\n.*?default 48", (FIRMWARE / project / "main" / "Kconfig.projbuild")
                         .read_text(encoding="utf-8"), flags=re.S)
