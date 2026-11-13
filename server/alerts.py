"""Alerts: Huawei SMN in huawei mode when SMN_TOPIC_URN + HUAWEICLOUD_AK/SK are set, otherwise console only.
Local mode never calls SMN, even if the keys are in .env.
The last 20 alerts are always kept in Redis for the dashboard.
Wording comes from dashboard/strings.json. An alert is stored as string keys plus values, so the dashboard shows it
in its own language (?lang=ms); SMN and the console get English and Malay together.
Alerts raised during a drill carry "drill": their subject starts with [DRILL] / [LATIHAN] and the text says it is a
drill, on the dashboard, the console and SMN alike, so nobody mistakes a practice run for a real emergency."""
import hashlib
import json
import os
import re
import secrets
import time

from server import config, logic, store
from server.strings import t

KEEP = 200       # kept in Redis for the Alerts page
DASHBOARD = 20   # shown on the overview
SEVERITY = {"emergency": "critical", "waste": "warning", "info": "info", "sensor": "warning", "drill": "info"}
SEVERITIES = ("critical", "warning", "info")
ALERT_ID = re.compile(r"[0-9a-f-]{6,40}")


def smn_enabled():
    return config.is_huawei() and all(os.getenv(k) for k in ("SMN_TOPIC_URN", "HUAWEICLOUD_AK", "HUAWEICLOUD_SK"))


def _smn_publish(subject, message):
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdksmn.v2 import PublishMessageRequest, PublishMessageRequestBody, SmnClient
    from huaweicloudsdksmn.v2.region.smn_region import SmnRegion

    region = os.getenv("SMN_REGION") or os.getenv("HUAWEICLOUD_REGION", "ap-southeast-1")
    client = (SmnClient.new_builder()
              .with_credentials(BasicCredentials(os.environ["HUAWEICLOUD_AK"], os.environ["HUAWEICLOUD_SK"]))
              .with_region(SmnRegion.value_of(region))
              .build())
    client.publish_message(PublishMessageRequest(
        topic_urn=os.environ["SMN_TOPIC_URN"],
        body=PublishMessageRequestBody(subject=subject[:512], message=message),
    ))


KINDS = ("emergency", "waste", "info", "sensor", "drill")


def render(alert, lang="en"):
    """(subject, message) of a stored alert in lang. Alerts saved before keys were used keep their text."""
    if "subject_key" not in alert:
        return alert.get("subject", ""), alert.get("message", "")
    values = dict(alert.get("values") or {})
    if "minutes" in values:
        values["minute_word"] = logic.minute_word(values["minutes"], lang)
    if lang == "ms" and "rooms_ms" in values:  # a list of rooms joined with "dan"
        values["rooms"] = values["rooms_ms"]
    for number in ("total", "after"):  # "1 person", "2 people": the word follows the number, in the alert's language
        if number in values and "people" not in values:
            values["people"] = logic.people_word(values[number], lang)
    if "kind_key" in values:
        values["kind"] = t(values["kind_key"], lang)
    subject, body = t(alert["subject_key"], lang, **values), t(alert["body_key"], lang, **values)
    if alert.get("drill"):
        body = body.rstrip()
        if not body.endswith((".", "!", "?")):  # "Lab 2: 1" + " This is a drill." needs the full stop between
            body += "."
        subject, body = t("alert.drill_subject", lang, subject=subject), t("alert.drill_body", lang, body=body)
    return subject, body


def send(kind, subject_key, body_key, severity=None, drill=False, **values):
    """kind picks the dashboard icon (emergency, waste, info, sensor or drill); the keys point into strings.json.
    severity overrides the kind's usual one (a sensor going offline is critical during a real emergency)."""
    now = int(time.time())
    alert = {"id": f"{now:x}-{secrets.token_hex(3)}", "ts": now, "kind": kind if kind in KINDS else "info",
             "subject_key": subject_key, "body_key": body_key, "values": values}
    if severity in SEVERITIES:
        alert["severity"] = severity
    if drill:
        alert["drill"] = True
    (en_subject, en_body), (ms_subject, ms_body) = render(alert, "en"), render(alert, "ms")
    via = "console"
    if smn_enabled():
        try:
            _smn_publish(f"{en_subject} / {ms_subject}", f"{en_body}\n\n{ms_body}")
            via = "smn"
        except Exception as e:  # never let a failed alert break ingest
            print(f"SMN publish failed, console only: {e}", flush=True)
    print(f"[ALERT] {en_subject}: {en_body}\n[AMARAN] {ms_subject}: {ms_body}", flush=True)
    try:
        store.r.lpush("alerts", json.dumps({**alert, "via": via}, ensure_ascii=False))
        store.r.ltrim("alerts", 0, KEEP - 1)
    except store.REDIS_ERRORS as e:  # the console line above is the record while Redis is offline
        print(f"alert not kept for the dashboard, Redis offline: {e}", flush=True)
    return via


def recent(lang="en", limit=DASHBOARD):
    """Newest first, with subject and message in lang, severity and who acknowledged it (if anyone)."""
    out = []
    raws = store.r.lrange("alerts", 0, min(limit, KEEP) - 1)
    acks = store.r.hgetall("alert_ack") if raws else {}
    for raw in raws:
        a = json.loads(raw)
        aid = a.get("id") or hashlib.sha1(raw.encode()).hexdigest()[:12]  # alerts stored before ids existed
        subject, message = render(a, lang)
        kind = a.get("kind", "info")
        ack = json.loads(acks[aid]) if aid in acks else None
        out.append({"id": aid, "ts": a["ts"], "kind": kind, "severity": a.get("severity") or SEVERITY.get(kind, "info"),
                    "via": a.get("via", "console"), "subject": subject, "message": message, "ack": ack,
                    "drill": bool(a.get("drill"))})
    return out


def acknowledge(alert_id, by, now):
    """Mark an alert as seen by an admin (token label). Returns False if no such alert is kept."""
    if not ALERT_ID.fullmatch(alert_id) or alert_id not in {a["id"] for a in recent(limit=KEEP)}:
        return False
    store.r.hset("alert_ack", alert_id, json.dumps({"by": by, "ts": now}))
    known = {a["id"] for a in recent(limit=KEEP)}
    stale = [k for k in store.r.hkeys("alert_ack") if k not in known]
    if stale:
        store.r.hdel("alert_ack", *stale)
    return True
