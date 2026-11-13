# Third-party notices

NADI's own code is Apache-2.0 ([LICENSE](LICENSE)). It builds on the components below. Licences were read on 25 Oct 2026 from the installed packages (Python package metadata, the Arduino library folders, the licence files inside the Docker images) or, where nothing is installed locally, from the project's own licence file.

The built web console (`web/dist`) bundles the frontend libraries below; the shadcn/ui component source is copied into `web/src/components/ui`. Everything else is installed separately (`pip`, `npm`, Docker, Arduino CLI, ESP-IDF, Ollama) and keeps its own licence.

## Copied or bundled into this repository

| Component | Version | Licence | Where |
|---|---|---|---|
| Inter (variable font, via @fontsource-variable/inter) | 5.1.0 | SIL Open Font License 1.1 | Bundled in `web/dist/assets`; licence in `web/public/licenses/Inter-OFL.txt` |
| shadcn/ui components (source copied) | 2024 | MIT | `web/src/components/ui/` |
| React, React DOM | 18.3.1 | MIT | Bundled in `web/dist` |
| React Router | 6.28.0 | MIT | Bundled |
| TanStack Query | 5.62.0 | MIT | Bundled |
| Recharts | 2.15.0 | MIT | Bundled |
| Motion (motion, with framer-motion, motion-dom, motion-utils) | 14.6.0 | MIT | Bundled: the overview's signal line and rolling counts |
| Magic UI components "Animated Beam" and "Number Ticker" (source copied and adapted) | Nov 2026 | MIT | `web/src/components/magicui/` |
| Radix UI primitives (dialog, select, tooltip, tabs, switch, toggle group, dropdown menu, scroll area, slot) | 1.2 to 2.4 | MIT | Bundled |
| Lucide icons (lucide-react) | 0.468.0 | ISC | Bundled |
| class-variance-authority | 0.7.1 | Apache-2.0 | Bundled |
| clsx, tailwind-merge | 2.1.1, 2.5.5 | MIT | Bundled |
| Tailwind CSS, tailwindcss-animate | 3.4.17, 1.0.7 | MIT | Build tool (CSS generated into `web/dist`) |

Build and test only (not bundled): Vite 5.4.11, TypeScript 5.6.3, Vitest 2.1.8, Testing Library (all MIT).

## Firmware (ESP32)

| Component | Version | Licence | Used for |
|---|---|---|---|
| espressif/esp-csi examples (`csi_send`, `csi_recv`) | master | Apache-2.0 | Starting point for the CSI sender and receiver |
| ESP-IDF | 5.4.1 | Apache-2.0 | Sender and receiver firmware |
| Arduino core for ESP32 (arduino-esp32) | 3.3.12 | LGPL-2.1-or-later | Climate node firmware |
| IRremoteESP8266 | 2.9.0 | LGPL-2.1 | Recording and replaying the air conditioner remote |
| DHT sensor library (Adafruit) | 1.4.7 | MIT | DHT22 temperature and humidity |
| Adafruit Unified Sensor | 1.1.15 | Apache-2.0 | Needed by the DHT library |
| PubSubClient | 2.8 | MIT | MQTT on the climate node |
| ArduinoJson | 7.4.3 | MIT | Reading the `ac_off` command |

The LGPL libraries are linked into the climate node firmware unmodified; their source is available from their projects.

## Server (Python)

| Component | Version | Licence |
|---|---|---|
| FastAPI | 0.115.12 | MIT |
| Starlette | 0.46.2 | BSD-3-Clause |
| Pydantic | 2.14.1 | MIT |
| Uvicorn | 0.34.0 | BSD-3-Clause |
| redis-py | 5.2.1 | MIT |
| PyMySQL | 1.1.1 | MIT |
| cryptography | 44.0.0 | Apache-2.0 or BSD-3-Clause |
| paho-mqtt | 2.1.0 | EPL-2.0 or BSD-3-Clause (EDL-1.0) |
| python-dotenv | 1.0.1 | BSD-3-Clause |
| openai (Python client, for Ollama and MaaS) | 3.37.0 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| Huawei Cloud Python SDK (core, SMN, IoTDA, ECS, RDS, DCS) | 3.1.219 | Apache-2.0 |

Development and testing only: pytest 9.1.1 (MIT), Playwright 1.64.1 (Apache-2.0), psutil 7.0.0 (BSD-3-Clause).

## Model training

| Component | Version | Licence |
|---|---|---|
| MindSpore | 2.10.0 | Apache-2.0 |
| NumPy | 1.26.4 | BSD-3-Clause |

## Services run alongside (Docker images and local apps, not shipped with NADI)

| Component | Version | Licence | Note |
|---|---|---|---|
| Eclipse Mosquitto | 2.0.20 | EPL-2.0 or EDL-1.0 | MQTT broker in local mode |
| MySQL Community Server | 8.0.46 | GPL-2.0 with the Universal FOSS Exception | History database |
| Valkey (`valkey/valkey:8.0.2`) | 8.0.2 | BSD-3-Clause | Live store in local mode, in place of Redis (Redis 7.4 and later are source-available under RSALv2 or SSPLv1, not open source). Same protocol, so the redis-py client is unchanged. Licence: `COPYING` in github.com/valkey-io/valkey (the image carries no licence file). |
| Ollama | 0.40.10 | MIT | Runs the local chat model |
| Qwen2.5 3B (`qwen2.5:3b`) | | **Qwen Research License** | Allows research and non-commercial use only. Fine for the competition prototype; a commercial deployment needs a model with a licence that permits it. The chat works without any model (built-in answers). |

In Huawei Cloud mode, IoTDA, DCS, RDS, SMN, ModelArts and MaaS are cloud services under Huawei Cloud's terms of service.
