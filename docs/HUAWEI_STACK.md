# NADI on Huawei: every component, where it is, and how to prove it

Status as of 24 Oct 2026. **In use now** = runs today on the laptop with no cloud account. **Ready, activates with coupon** = code and config are in the repo and switch on with `NADI_MODE=huawei` plus `.env` values; not yet run against the cloud.

The dashboard footer ("Built with") lists only what is actually in use at that moment, so it is the live proof in either mode.

| Component | What NADI uses it for | Where in the repo | Status | How to prove it to a judge |
|---|---|---|---|---|
| **MindSpore 2.10** | Trains the 0 / 1 / 2 / 3+ headcount classifier (5 CSI features -> 16 hidden -> 4 classes) | `ml/train.py`, `ml/model/` (`.ckpt`, `.mindir`, `.json`) | In use now (trained locally on synthetic data) | Run `.venv-ml\Scripts\python ml\train.py` live: MindSpore version, loss per epoch, accuracy, confusion matrix. Dashboard footer: "MindSpore 2.10.0 occupancy model" |
| **ModelArts** | Runs the same `train.py` as a cloud training job, data and model on OBS | `ml/MODELARTS.md`, `ml/train.py` (`--platform modelarts`, OBS/moxing support) | Ready, activates with coupon | Training job page (Completed + log), OBS output folder; footer changes to "trained on Huawei ModelArts" |
| **IoTDA** | Device access for the ESP32s: MQTT (TLS) in, HTTP push to the server | `sim/fake_sensor.py` (huawei mode), `server/main.py` `POST /iotda`, topic/JSON in the project brief | Ready, activates with coupon. Local mode already uses the exact IoTDA topic and JSON through Mosquitto, so devices need no change | IoTDA console: device online, message trace; footer shows "Huawei Cloud IoTDA" only after real pushes arrive |
| **IoTDA topic format (local)** | `$oc/devices/{id}/sys/properties/report` with the IoTDA `services` JSON, on a local broker | `docker-compose.yml` (mosquitto), `server/mqtt_local.py` | In use now | `docker compose logs mosquitto`; dashboard updates while the simulator prints each report |
| **ECS** | Hosts the FastAPI server and dashboard | `deploy/ecs_deploy.sh`, `deploy/nadi.service` | Ready, activates with coupon | Dashboard on `http://<ECS IP>:8000` with the header badge "HUAWEI CLOUD" and footer badge "Huawei Cloud ECS" |
| **DCS for Redis** | Live per-room counts, emergency state, last 20 alerts | `server/store.py` (`REDIS_HOST` etc.) | Ready, activates with coupon (local Docker Redis now) | Footer "Huawei Cloud DCS for Redis" when `REDIS_HOST` is the DCS address; DCS console metrics |
| **RDS for MySQL** | History tables `occupancy`, `climate`; training data source for `ml/prepare.py` | `server/store.py`, `ml/prepare.py` | Ready, activates with coupon (local Docker MySQL now) | Footer "Huawei Cloud RDS for MySQL"; RDS console, `SELECT COUNT(*) FROM occupancy` |
| **SMN** | SMS/email to wardens when emergency mode starts and for air conditioning waste | `server/alerts.py` (`huaweicloudsdksmn`) | Ready, activates with coupon. Local mode sends to console + dashboard only and never calls SMN | Warden's phone gets the SMS during the demo; the Alerts panel on the dashboard shows "Sent via Huawei SMN" instead of "Sent via console" |
| **ModelArts Studio (MaaS)** | Chat ("Ask NADI") in BM and English, answering only from live numbers | `server/chat.py` (OpenAI-compatible client) | Ready, activates with coupon. Local mode uses Ollama qwen2.5:3b and is labelled as such, never as MaaS | Chat footer "Answered by <model> on Huawei ModelArts Studio (MaaS)" |
| **CodeArts Repo** | Second git remote holding the same commits as GitHub | `deploy/CODEARTS.md` step 2 | Ready, activates with coupon | Repo commit list in the CodeArts console |
| **CodeArts Build** | Runs unit tests, packages `nadi.tar.gz` | `.cloudbuild/build.yml` | Ready, activates with coupon | Build log with `N passed` |
| **CodeArts Deploy** | Installs the package on ECS and restarts the service | `deploy/ecs_deploy.sh`, `deploy/CODEARTS.md` step 5 | Ready, activates with coupon | Deploy log ending in the `/api/info` JSON |
| **CodeArts Pipeline** | Push -> build/test -> deploy to ECS | `deploy/codearts/pipeline.yml` | Ready, activates with coupon | Pipeline run history; live push during Q&A if Wi-Fi allows |
| **Huawei Cloud Python SDK** (`huaweicloudsdkcore` 3.1.219 + smn, iotda, ecs, rds, dcs) | SMN publish; read-only preflight that the keys can see each service | `requirements.txt`, `server/alerts.py`, `deploy/huawei_preflight.py` | Installed and pinned. Preflight refuses to run unless `NADI_MODE=huawei` | `python deploy/huawei_preflight.py` after the coupon: one OK line per service |
| **KooCLI (`hcloud`)** | Command-line access to the same services (backup to the console during setup) | installed at `%LOCALAPPDATA%\hcloud`, on user PATH | Installed, not configured (first run asks for the privacy agreement, then `hcloud configure init` with the AK/SK) | `hcloud version` |
| **Huawei VRP (AR router + S switch)** | Separate IoT VLAN, DHCP, ACL allowing sensors only DHCP/DNS/MQTT | `deploy/huawei-network/` | Ready, needs UTM's Huawei router + switch (not applied to a device yet) | `display acl 3030` hit counters; phone on the IoT SSID can reach MQTT but not the dashboard |

## Not Huawei, and labelled that way

| Component | Why |
|---|---|
| Mosquitto, Docker Redis, Docker MySQL | Local stand-ins for IoTDA, DCS and RDS until the coupon |
| Ollama + qwen2.5:3b | Local stand-in for MaaS chat; the dashboard names it as Ollama |
| FastAPI, Playwright | App server and screenshot tooling |
| MikroTik / Cisco AP | UTM has no Huawei AP; the AP only carries the IoT SSID into the Huawei VLAN |
