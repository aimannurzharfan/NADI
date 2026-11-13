# NADI glossary

Every phrase NADI shows to users and judges, in English and Bahasa Melayu.
Generated from `dashboard/strings.json` by `python scripts/glossary.py`. Edit the JSON, not this file.
The dashboard and the server both read the JSON, so a wording change there changes it everywhere.

Rules: formal English with British/Malaysian spelling (colour, metres); standard Malay (bahasa baku), no mixing.
**[CHECK]** marks Malay wording a native speaker should confirm (0 entries).
`{name}` and similar are filled in at run time.

## Key terms

| English | Bahasa Melayu | Note |
|---|---|---|
| air conditioning (the system) | penghawa dingin | Never "aircon". "A/C" only where space is tight. |
| air conditioner (the unit) | penghawa dingin |  |
| emergency mode | mod kecemasan |  |
| empty room, air conditioning still on | bilik kosong, penghawa dingin masih hidup |  |
| people still inside | orang masih di dalam |  |
| occupied | berpenghuni |  |
| sensor | sensor |  |
| online / offline | dalam talian / luar talian |  |
| floor plan | pelan lantai |  |
| exit | keluar | As on Malaysian exit signs: KELUAR |
| headcount | bilangan orang |  |
| alert | amaran |  |
| warden | warden |  |

## Header and page

| Key | English | Bahasa Melayu |
|---|---|---|
| `ui.page_title` | NADI: building occupancy and safety | NADI: penghunian dan keselamatan bangunan |
| `ui.home` | NADI, home | NADI, laman utama |
| `ui.start_emergency` | Start emergency mode | Mulakan mod kecemasan |
| `ui.mode_local` | LOCAL | TEMPATAN |
| `ui.mode_huawei` | HUAWEI CLOUD | HUAWEI CLOUD |
| `ui.mode_local_hint` | Local mode: no Huawei Cloud services are called | Mod tempatan: tiada perkhidmatan Huawei Cloud digunakan |
| `ui.mode_huawei_hint` | Huawei Cloud mode: IoTDA, DCS, RDS, SMN and MaaS | Mod Huawei Cloud: IoTDA, DCS, RDS, SMN dan MaaS |
| `ui.sensors_badge` | {live}/{total} sensors online | {live}/{total} sensor dalam talian |
| `ui.admin_localhost` | Admin: localhost only | Pentadbir: komputer ini sahaja |
| `ui.admin_refused` | Admin: set ADMIN_TOKEN | Pentadbir: tetapkan ADMIN_TOKEN |
| `ui.summary_label` | Building summary | Ringkasan bangunan |

## Summary strip

| Key | English | Bahasa Melayu |
|---|---|---|
| `kpi.people` | people inside | orang di dalam bangunan |
| `kpi.rooms` | rooms occupied | bilik berpenghuni |
| `kpi.waste` | air conditioning waste today | pembaziran penghawa dingin hari ini |
| `kpi.sensors` | sensors online | sensor dalam talian |

## Floor plan

| Key | English | Bahasa Melayu |
|---|---|---|
| `plan.title` | {level} floor plan | Pelan lantai {level} |
| `plan.hint` | Select a room for details | Pilih bilik untuk melihat butiran |
| `plan.label` | Floor plan | Pelan lantai |
| `plan.em_label` | Floor plan with occupied rooms highlighted | Pelan lantai dengan bilik berpenghuni ditonjolkan |
| `plan.corridor` | Corridor | Koridor |
| `plan.toilets` | Toilets | Tandas |
| `plan.store` | Store | Stor |
| `plan.lifts` | Lifts | Lif |
| `plan.pantry` | Pantry | Pantri |
| `plan.stair_a` | Stair A | Tangga A |
| `plan.stair_b` | Stair B | Tangga B |
| `plan.exit_sign` | EXIT | KELUAR |
| `plan.waste_sub` | Empty {minutes} min, A/C on | Kosong {minutes} min, A/C hidup |
| `plan.em_people` | {count} {people} | {count} orang |
| `plan.em_three_plus` | 3 or more people | 3 orang atau lebih |
| `plan.em_none` | No one detected | Tiada orang dikesan |
| `plan.room_label` | {name}: {count} {people}, {status} | {name}: {count} orang, {status} |

## Floor plan key

| Key | English | Bahasa Melayu |
|---|---|---|
| `legend.ok` | Occupied | Berpenghuni |
| `legend.empty` | Empty | Kosong |
| `legend.waste` | Empty, A/C on | Kosong, A/C hidup |
| `legend.off` | Sensor offline | Sensor luar talian |

## Room status

| Key | English | Bahasa Melayu |
|---|---|---|
| `status.ok` | Occupied | Berpenghuni |
| `status.empty` | Empty | Kosong |
| `status.waste` | Empty, A/C on | Kosong, A/C hidup |
| `status.off` | Offline | Luar talian |

## Units

| Key | English | Bahasa Melayu |
|---|---|---|
| `unit.person` | person | orang |
| `unit.people` | people | orang |
| `unit.minute` | minute | minit |
| `unit.minutes` | minutes | minit |
| `unit.room` | room | bilik |
| `unit.rooms` | rooms | bilik |
| `unit.sensor` | sensor | sensor |
| `unit.sensors` | sensors | sensor |
| `unit.kwh` | kWh | kWj |

## Room cards

| Key | English | Bahasa Melayu |
|---|---|---|
| `rooms.title` | Rooms | Bilik |
| `rooms.hint` | Headcount, last 30 minutes | Bilangan orang, 30 minit terakhir |
| `rooms.none` | No sensor has reported yet. Start a sensor or the simulator. | Belum ada sensor yang menghantar data. Hidupkan sensor atau simulator. |
| `card.updated` | updated {ago} | dikemas kini {ago} |
| `card.last_seen` | last seen {ago} | data terakhir diterima {ago} |
| `card.humidity` | {value}% RH | Kelembapan {value}% |
| `card.label` | {name}, {count} {people}, {status}. Open details | {name}, {count} orang, {status}. Buka butiran |

## Room details

| Key | English | Bahasa Melayu |
|---|---|---|
| `detail.close` | Close room details | Tutup butiran bilik |
| `detail.summary` | {people}, {status} | {people}, {status} |
| `detail.temperature` | Temperature | Suhu |
| `detail.humidity` | Humidity | Kelembapan |
| `detail.last_update` | Last update | Kemas kini terakhir |
| `detail.nearest_exit` | Nearest exit | Laluan keluar terdekat |
| `detail.temp_ac_on` | {temp} °C, air conditioning on | {temp} °C, penghawa dingin hidup |
| `detail.no_reading` | No reading | Tiada bacaan |
| `detail.not_on_plan` | Not on the floor plan | Tiada dalam pelan lantai |
| `detail.axis_start` | 30 minutes ago | 30 minit lalu |
| `detail.axis_mid` | Headcount, 0 to 3+ | Bilangan orang, 0 hingga 3+ |
| `detail.axis_end` | Now | Kini |
| `detail.waste_note` | Empty with the air conditioning on for {minutes} {minute_word}. About RM {rm} wasted so far. | Bilik kosong dengan penghawa dingin hidup selama {minutes} minit. Kira-kira RM {rm} telah dibazirkan setakat ini. |
| `detail.offline_note` | Sensor offline. The count shown is the last one received. | Sensor luar talian. Bilangan yang dipaparkan ialah bacaan terakhir yang diterima. |

## Times

| Key | English | Bahasa Melayu |
|---|---|---|
| `time.just_now` | just now | baru sahaja |
| `time.seconds` | {n} s ago | {n} saat lalu |
| `time.minutes` | {n} min ago | {n} minit lalu |
| `time.hours` | {n} h ago | {n} jam lalu |
| `time.days` | {n} d ago | {n} hari lalu |
| `time.never` | never | tiada |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.title` | Alerts | Amaran |
| `alerts.none` | No alerts yet. Emergencies and air conditioning waste appear here. | Tiada amaran lagi. Kecemasan dan pembaziran penghawa dingin akan dipaparkan di sini. |
| `alerts.via` | Sent via {channels} | Dihantar melalui {channels} |

## list

| Key | English | Bahasa Melayu |
|---|---|---|
| `list.and` |  and  |  dan  |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.via_console` | console | konsol |
| `alerts.via_smn` | Huawei SMN | Huawei SMN |

## Alert messages (SMN and console)

| Key | English | Bahasa Melayu |
|---|---|---|
| `alert.emergency_subject` | NADI: Emergency mode started | NADI: Penggera kecemasan berbunyi |
| `alert.emergency_body` | {total} {people} inside when the alarm started. {rooms} | {total} orang di dalam semasa penggera berbunyi. {rooms} |
| `alert.emergency_body_plus` | {total} or more people inside when the alarm started. {rooms} | {total} orang atau lebih di dalam semasa penggera berbunyi. {rooms} |
| `alert.waste_subject` | NADI: Air conditioning on in an empty room ({name}) | NADI: Bilik kosong, penghawa dingin masih hidup ({name}) |
| `alert.waste_body` | {name} has been empty with the air conditioning on for {minutes} {minute_word} ({temp} °C). About RM {rm} wasted so far. | {name} kosong dengan penghawa dingin masih hidup selama {minutes} minit ({temp} °C). Kira-kira RM {rm} telah dibazirkan setakat ini. |
| `alert.audit_start_subject` | NADI: Emergency mode started by {who} | NADI: Mod kecemasan dimulakan oleh {who} |
| `alert.audit_end_subject` | NADI: Emergency mode ended by {who} | NADI: Mod kecemasan ditamatkan oleh {who} |
| `alert.audit_body` | {who} at {time}. | {who} pada {time}. |

## Ask NADI

| Key | English | Bahasa Melayu |
|---|---|---|
| `chat.title` | Ask NADI | Tanya NADI |
| `chat.languages` | English or Bahasa Melayu | Bahasa Inggeris atau Bahasa Melayu |
| `chat.intro` | Answers come only from the live sensor readings. | Jawapan hanya berdasarkan bacaan sensor semasa. |
| `chat.placeholder` | Type a question… | Taip soalan… |
| `chat.question_label` | Question | Soalan |
| `chat.ask` | Ask | Tanya |
| `chat.waiting` | Checking the live readings… | Menyemak bacaan semasa… |
| `chat.not_answered` | Not answered: {detail} | Tidak dijawab: {detail} |
| `chat.unreachable` | the server cannot be reached ({error}) | pelayan tidak dapat dihubungi ({error}) |
| `chat.q_total` | How many people are inside? | Berapa orang di dalam bangunan? |

## Chat answers (built-in)

| Key | English | Bahasa Melayu |
|---|---|---|
| `answer.no_data` | There is no live room data at the moment. | Tiada data bilik terkini buat masa ini. |
| `answer.room_offline` | {name}: no live data (sensor offline). | {name}: tiada data terkini (sensor luar talian). |
| `answer.room_count` | {name}: {count} {people}{temp}. | {name}: {count} orang{temp}. |
| `answer.waste_none` | No empty room has the air conditioning on. | Tiada bilik kosong yang penghawa dinginnya masih hidup. |
| `answer.waste_item` | {name} ({minutes} {minute_word}, RM {rm}) | {name} ({minutes} minit, RM {rm}) |
| `answer.waste_list` | Air conditioning is on in empty rooms: {rooms}. RM {total} wasted so far. | Penghawa dingin masih hidup di bilik kosong: {rooms}. Sebanyak RM {total} telah dibazirkan setakat ini. |
| `answer.empty_none` | No rooms are empty. | Tiada bilik yang kosong. |
| `answer.empty_list` | Empty rooms: {rooms}. | {rooms} kosong. |
| `answer.help` | I can answer questions about the people inside, individual rooms, air conditioning and emergency status. For example: How many people are inside? | Saya boleh menjawab soalan tentang orang di dalam bangunan, bilik tertentu, penghawa dingin dan status kecemasan. Contohnya: Berapa orang di dalam bangunan? |
| `answer.total` | {total}{or_more} {people} inside, in {rooms} {room_word}. | {total} orang{or_more} di dalam, di {rooms} bilik. |
| `answer.total_none` | No one is inside. | Tiada orang di dalam. |
| `answer.emergency_on` | Emergency mode is on. The alarm started {minutes} {minute_word} ago. | Mod kecemasan sedang aktif. Penggera berbunyi {minutes} minit lalu. |
| `answer.emergency_off` | Emergency mode is off. | Mod kecemasan tidak aktif. |
| `answer.first` | Check {name} first: {count} {people}{via}. | Periksa {name} dahulu: {count} orang{via}. |
| `answer.first_none` | No one is inside, so no room needs checking first. | Tiada orang di dalam, jadi tiada bilik yang perlu diperiksa dahulu. |
| `answer.priority` | Emergency mode is on. Check the rooms in this order: {rooms}. | Mod kecemasan sedang aktif. Periksa bilik mengikut susunan ini: {rooms}. |
| `answer.priority_item` | {rank}. {name} ({count}{last_known}{via}) | {rank}. {name} ({count}{last_known}{via}) |
| `answer.via` | , via {exit} | , melalui {exit} |
| `answer.last_known` | , last known count | , bilangan terakhir diketahui |
| `answer.or_more` |  or more |  atau lebih |

## Chat model labels

| Key | English | Bahasa Melayu |
|---|---|---|
| `model.builtin` | built-in answers (no language model) | jawapan automatik (tanpa model AI) |
| `model.ollama` | {model} via Ollama (local) | {model} melalui Ollama (tempatan) |
| `model.maas` | {model} on Huawei ModelArts Studio (MaaS) | {model} di Huawei ModelArts Studio (MaaS) |

## Built with

| Key | English | Bahasa Melayu |
|---|---|---|
| `built.title` | Built with | Dibina dengan |
| `built.mosquitto` | Mosquitto MQTT (IoTDA topic format) | Mosquitto MQTT (format topik IoTDA) |
| `built.redis_local` | Redis (local) | Redis (tempatan) |
| `built.mysql_local` | MySQL (local) | MySQL (tempatan) |
| `built.iotda` | Huawei Cloud IoTDA | Huawei Cloud IoTDA |
| `built.dcs` | Huawei Cloud DCS for Redis | Huawei Cloud DCS untuk Redis |
| `built.rds` | Huawei Cloud RDS for MySQL | Huawei Cloud RDS untuk MySQL |
| `built.ecs` | Huawei Cloud ECS | Huawei Cloud ECS |
| `built.model_modelarts` | {framework} occupancy model (trained on Huawei ModelArts, {data} data) | Model penghunian {framework} (dilatih di Huawei ModelArts, data {data}) |
| `built.model_local` | {framework} occupancy model (trained locally, {data} data) | Model penghunian {framework} (dilatih secara tempatan, data {data}) |
| `built.data_synthetic` | synthetic | sintetik |
| `built.data_real` | real CSI | CSI sebenar |
| `built.data_mixed` | mixed real and synthetic | campuran data sebenar dan sintetik |
| `built.threshold` | Threshold rule (no trained model yet) | Peraturan ambang (belum ada model terlatih) |
| `built.smn` | Huawei Cloud SMN alerts | Amaran Huawei Cloud SMN |
| `built.console` | Console alerts | Amaran konsol |

## Footer

| Key | English | Bahasa Melayu |
|---|---|---|
| `footer.updated` | Updated {time} | Dikemas kini {time} |
| `footer.connecting` | Connecting… | Menyambung… |
| `footer.unreachable` | The server cannot be reached ({error}). Retrying every 5 seconds. | Pelayan tidak dapat dihubungi ({error}). Mencuba semula setiap 5 saat. |

## banner

| Key | English | Bahasa Melayu |
|---|---|---|
| `banner.redis` | Database offline, showing last known data at {time}. | Pangkalan data di luar talian, memaparkan data terakhir pada {time}. |
| `banner.mysql` | History database offline since {time}. Live counts still update; history is saved when it is back. | Pangkalan data sejarah di luar talian sejak {time}. Kiraan langsung masih dikemas kini; sejarah disimpan apabila ia kembali. |
| `banner.mqtt` | Sensor link offline since {time}. Counts are not updating. | Sambungan sensor di luar talian sejak {time}. Kiraan tidak dikemas kini. |
| `banner.server` | Server unreachable, showing last known data at {time}. | Pelayan tidak dapat dihubungi, memaparkan data terakhir pada {time}. |

## Start emergency dialog

| Key | English | Bahasa Melayu |
|---|---|---|
| `start.title` | Start emergency mode? | Mulakan mod kecemasan? |
| `start.body` | Every screen switches to the emergency view, and wardens receive an alert with the current headcount. | Semua skrin akan bertukar kepada paparan kecemasan, dan warden akan menerima amaran bersama bilangan orang semasa. |
| `start.cancel` | Cancel | Batal |
| `start.go` | Start emergency mode | Mulakan mod kecemasan |

## Emergency view

| Key | English | Bahasa Melayu |
|---|---|---|
| `em.flag` | Emergency mode | Mod kecemasan |
| `em.since` | since the alarm | sejak penggera berbunyi |
| `em.still_inside` | people still inside | orang masih di dalam |
| `em.in_rooms` | in {n} {room_word} | di dalam {n} bilik |
| `em.offline_note` | , {n} {sensor_word} offline (last known counts) | , {n} sensor luar talian (bilangan terakhir diketahui) |
| `em.all_live` | , all sensors live | , semua sensor aktif |
| `em.go_first` | Go here first | Utamakan bilik ini |
| `em.live` | live, {ago} | masa nyata, {ago} |
| `em.last_known` | last known count, {s} s ago | bilangan terakhir diketahui, {s} saat lalu |
| `em.no_data` | No room data. Search every room. | Tiada data bilik. Periksa setiap bilik. |
| `em.end` | End emergency mode | Tamatkan mod kecemasan |
| `em.confirm_question` | Is everyone accounted for? | Adakah semua orang telah disahkan selamat? |
| `em.keep` | Keep emergency mode on | Teruskan mod kecemasan |
| `em.confirm_end` | End emergency mode on every screen | Tamatkan mod kecemasan pada semua skrin |
| `em.label` | Emergency mode | Mod kecemasan |

## Admin

| Key | English | Bahasa Melayu |
|---|---|---|
| `admin.prompt` | Admin token for emergency mode and chat: | Token pentadbir untuk mod kecemasan dan sembang: |
| `admin.not_changed` | Emergency mode was not changed: {detail} | Mod kecemasan tidak diubah: {detail} |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.admin_required` | An admin token is required. | Token pentadbir diperlukan. |
| `api.admin_huawei` | ADMIN_TOKEN must be set in Huawei Cloud mode. | ADMIN_TOKEN mesti ditetapkan dalam mod Huawei Cloud. |
| `api.admin_localhost` | ADMIN_TOKEN is not set, so this works only from the server computer. | ADMIN_TOKEN tidak ditetapkan, jadi ini hanya berfungsi dari komputer pelayan. |
| `api.bad_token` | The ingest token is wrong. | Token data tidak sah. |
| `api.empty_question` | The question is empty. | Soalan kosong. |
| `api.admin_token_short` | The admin token on the server is shorter than {n} characters, so emergency mode and chat are switched off until it is replaced. | Token pentadbir pada pelayan kurang daripada {n} aksara, jadi mod kecemasan dan sembang dimatikan sehingga token itu diganti. |

## label

| Key | English | Bahasa Melayu |
|---|---|---|
| `label.page_title` | NADI: calibration | NADI: kalibrasi |
| `label.title` | Calibration | Kalibrasi |
| `label.intro` | Tap the number of people in the room now. Tap again when it changes, and Stop when you finish. | Ketik bilangan orang di dalam bilik sekarang. Ketik semula apabila bilangan berubah, dan Henti apabila selesai. |
| `label.sensor` | Sensor now: {count} | Sensor sekarang: {count} |
| `label.current` | Labelled {count} since {time} | Dilabel {count} sejak {time} |
| `label.none` | Not labelling | Tiada label aktif |
| `label.stop` | Stop | Henti |
| `label.undo` | Undo last | Batal yang terakhir |
| `label.empty` | No labels yet. | Belum ada label. |
| `label.saved` | Saved: {name}, {count} at {time} | Disimpan: {name}, {count} pada {time} |
| `label.stopped` | Stopped: {name} at {time} | Dihentikan: {name} pada {time} |
| `label.undone` | Last label removed. | Label terakhir dibuang. |
| `label.error` | Not saved: {detail} | Tidak disimpan: {detail} |
| `label.ended` | {start} to {end} | {start} hingga {end} |
| `label.running` | {start}, still running | {start}, masih berjalan |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.reject_headcount` | headcount must be a whole number from 0 to 100. | headcount mesti nombor bulat dari 0 hingga 100. |

## Header and page

| Key | English | Bahasa Melayu |
|---|---|---|
| `ui.demo` | DEMO SCENARIO | SENARIO DEMO |
| `ui.demo_hint` | A recorded story, not live sensor data: {t} of 3:00 | Cerita rakaman, bukan data sensor sebenar: {t} daripada 3:00 |
| `ui.demo_pause` | A recorded story, not live sensor data: restarting shortly | Cerita rakaman, bukan data sensor sebenar: bermula semula sebentar lagi |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.demo_off` | Demo scenario is off. Set DEMO_SCENARIO=on in .env and restart the server. | Senario demo dimatikan. Tetapkan DEMO_SCENARIO=on dalam .env dan mulakan semula pelayan. |

## board

| Key | English | Bahasa Melayu |
|---|---|---|
| `board.button` | Board address | Alamat papan |
| `board.title` | Where the boards connect | Alamat sambungan papan |
| `board.body` | Boards connect to {ip}, port {port}. If this address has changed, type setup on each board's serial port and enter it. | Papan bersambung ke {ip}, port {port}. Jika alamat ini berubah, taip setup pada port bersiri setiap papan dan masukkan alamat ini. |
| `board.mismatch` | Mosquitto listens on {configured} (MQTT_LAN_IP in .env), but this computer's address is now {ip}. Set MQTT_LAN_IP={ip} in .env and run docker compose up -d mosquitto. | Mosquitto mendengar pada {configured} (MQTT_LAN_IP dalam .env), tetapi alamat komputer ini sekarang {ip}. Tetapkan MQTT_LAN_IP={ip} dalam .env dan jalankan docker compose up -d mosquitto. |
| `board.unknown` | This computer has no network address. Connect it to the same Wi-Fi network as the boards first. | Komputer ini tiada alamat rangkaian. Sambungkan komputer ini ke rangkaian Wi-Fi yang sama dengan papan dahulu. |
| `board.close` | Close | Tutup |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.board_local_only` | Only in local mode: in Huawei Cloud mode the boards connect to IoTDA. | Hanya dalam mod tempatan: dalam mod Huawei Cloud, papan bersambung ke IoTDA. |
| `api.reject_fw` | fw_version may use only letters, digits, dots, - and _ (up to 16). | fw_version hanya boleh mengandungi huruf, digit, titik, - dan _ (maksimum 16). |
| `api.alert_unknown` | That alert is no longer kept. | Amaran itu tidak lagi disimpan. |

## nav

| Key | English | Bahasa Melayu |
|---|---|---|
| `nav.label` | Main navigation | Navigasi utama |
| `nav.overview` | Overview | Gambaran keseluruhan |
| `nav.floor` | Floor plan | Pelan lantai |
| `nav.rooms` | Rooms | Bilik |
| `nav.sensors` | Sensors | Sensor |
| `nav.energy` | Energy | Tenaga |
| `nav.alerts` | Alerts | Amaran |
| `nav.label_page` | Calibration | Kalibrasi |

## top

| Key | English | Bahasa Melayu |
|---|---|---|
| `top.clock` | Time now | Masa sekarang |
| `top.other_lang` | Bahasa Melayu | English |
| `top.theme_dark` | Switch to the dark theme | Tukar ke tema gelap |
| `top.theme_light` | Switch to the light theme | Tukar ke tema cerah |

## common

| Key | English | Bahasa Melayu |
|---|---|---|
| `common.loading` | Loading… | Memuatkan… |
| `common.empty` | Nothing to show yet. | Belum ada apa-apa untuk dipaparkan. |
| `common.load_failed` | Could not load this | Tidak dapat memuatkan bahagian ini |

## Admin

| Key | English | Bahasa Melayu |
|---|---|---|
| `admin.sign_in` | Sign in | Log masuk |
| `admin.sign_out` | Sign out of admin features | Log keluar daripada ciri pentadbir |
| `admin.sign_in_title` | Admin sign-in | Log masuk pentadbir |
| `admin.sign_in_body` | Enter the admin token (ADMIN_TOKEN or one of ADMIN_TOKENS on the server). It is kept for this browser tab only. | Masukkan token pentadbir (ADMIN_TOKEN atau salah satu ADMIN_TOKENS pada pelayan). Token ini disimpan untuk tab pelayar ini sahaja. |
| `admin.token_label` | Admin token | Token pentadbir |
| `admin.wrong_token` | That token is not accepted. | Token itu tidak diterima. |
| `admin.signed_in_as` | Admin: {who} | Pentadbir: {who} |
| `admin.signed_in_local` | Admin: this computer | Pentadbir: komputer ini |
| `admin.local_hint` | No admin token is set, so admin features work on the server computer only. | Tiada token pentadbir ditetapkan, jadi ciri pentadbir berfungsi pada komputer pelayan sahaja. |
| `admin.needed_title` | Admin sign-in needed | Log masuk pentadbir diperlukan |
| `admin.needed_body` | {what} is for admins only. | {what} untuk pentadbir sahaja. |
| `admin.needed_localhost` | No admin token is set, so open this page on the server computer. | Tiada token pentadbir ditetapkan, jadi buka halaman ini pada komputer pelayan. |
| `admin.needed_refused` | Set ADMIN_TOKEN on the server first. | Tetapkan ADMIN_TOKEN pada pelayan dahulu. |
| `admin.needed_short` | Admin sign-in needed: use Sign in in the top bar. | Log masuk pentadbir diperlukan: gunakan Log masuk di bar atas. |

## ov

| Key | English | Bahasa Melayu |
|---|---|---|
| `ov.people_now` | People inside now | Orang di dalam sekarang |
| `ov.in_rooms` | in {n} of {total} rooms | dalam {n} daripada {total} bilik |
| `ov.people_avg` | Average people, {range} | Purata orang, {range} |
| `ov.peak` | peak {n} | puncak {n} |
| `ov.alerts` | Alerts, {range} | Amaran, {range} |
| `ov.vs_yesterday` | vs yesterday | berbanding semalam |
| `ov.no_previous` | No earlier data to compare | Tiada data terdahulu untuk dibandingkan |
| `ov.occupancy_title` | Occupancy per room | Penghunian setiap bilik |
| `ov.occupancy_hint` | Headcount, {range} | Bilangan orang, {range} |
| `ov.occupancy_empty` | No readings in this time range yet. Check that the sensors are running. | Belum ada bacaan dalam julat masa ini. Pastikan sensor sedang berfungsi. |
| `ov.open_plan` | Open floor plan | Buka pelan lantai |
| `ov.recent_alerts` | Recent alerts | Amaran terkini |
| `ov.all_alerts` | All alerts | Semua amaran |
| `ov.energy_title` | Air conditioning waste | Pembaziran penghawa dingin |
| `ov.open_energy` | Energy details | Butiran tenaga |

## floor

| Key | English | Bahasa Melayu |
|---|---|---|
| `floor.description` | Live count per room. Select a room for details. | Bilangan semasa setiap bilik. Pilih bilik untuk butiran. |

## drawer

| Key | English | Bahasa Melayu |
|---|---|---|
| `drawer.climate_chart` | Temperature and humidity | Suhu dan kelembapan |
| `drawer.no_climate` | No temperature readings in this time range. | Tiada bacaan suhu dalam julat masa ini. |
| `drawer.sensor_health` | Sensor health | Kesihatan sensor |
| `drawer.sensor_health_what` | Sensor health | Kesihatan sensor |
| `drawer.no_sensors` | No sensor has reported for this room. | Tiada sensor yang melaporkan untuk bilik ini. |

## Room cards

| Key | English | Bahasa Melayu |
|---|---|---|
| `rooms.description` | Every room with its live count, climate and sensor state. | Setiap bilik dengan bilangan semasa, iklim dan keadaan sensor. |
| `rooms.count` | {n} of {total} rooms | {n} daripada {total} bilik |
| `rooms.search` | Search rooms | Cari bilik |
| `rooms.filter_status` | Filter by status | Tapis mengikut status |
| `rooms.all_statuses` | All statuses | Semua status |
| `rooms.col_room` | Room | Bilik |
| `rooms.col_status` | Status | Status |
| `rooms.col_people` | People | Orang |
| `rooms.col_ac` | Air conditioning | Penghawa dingin |
| `rooms.col_waste` | Waste today | Pembaziran hari ini |
| `rooms.col_sensor` | Sensor | Sensor |
| `rooms.col_seen` | Last report | Laporan terakhir |
| `rooms.ac_on` | On (below {temp} °C) | Hidup (bawah {temp} °C) |
| `rooms.ac_off` | Off | Mati |
| `rooms.sensor_live` | Live | Dalam talian |

## sensors

| Key | English | Bahasa Melayu |
|---|---|---|
| `sensors.description` | Every board and its health. Red rows have stopped reporting. | Setiap papan dan kesihatannya. Baris merah sudah berhenti melapor. |
| `sensors.what` | The sensor list | Senarai sensor |
| `sensors.count` | {n} devices | {n} peranti |
| `sensors.count_one` | 1 device | 1 peranti |
| `sensors.offline_count` | {n} not reporting | {n} tidak melapor |
| `sensors.all_online` | All reporting | Semua melapor |
| `sensors.none` | No board has reported yet. Follow docs/BOARD_DAY.md to connect one. | Belum ada papan yang melapor. Ikut docs/BOARD_DAY.md untuk menyambungkan papan. |
| `sensors.col_device` | Device ID | ID peranti |
| `sensors.col_type` | Type | Jenis |
| `sensors.col_last` | Last report | Laporan terakhir |
| `sensors.col_rssi` | Wi-Fi signal | Isyarat Wi-Fi |
| `sensors.col_packets` | Packets per {s} s | Paket setiap {s} s |
| `sensors.col_uptime` | Uptime | Tempoh aktif |
| `sensors.col_fw` | Firmware | Perisian tegar |
| `sensors.col_heap` | Free memory | Memori bebas |
| `sensors.col_dropped` | Dropped | Hilang |
| `sensors.type_receiver` | CSI receiver | Penerima CSI |
| `sensors.type_sender` | CSI sender | Penghantar CSI |
| `sensors.type_climate` | Climate node | Nod iklim |
| `sensors.sender_of` | Sender for {id} | Penghantar untuk {id} |
| `sensors.via_receiver` | From its receiver's packets | Daripada paket penerimanya |
| `sensors.online` | Online | Dalam talian |
| `sensors.offline` | Offline | Luar talian |
| `sensors.simulator` | simulator | simulator |
| `sensors.board_hint` | Type this into each board's setup command if the address has changed. | Taip alamat ini dalam arahan setup setiap papan jika alamat berubah. |
| `sensors.broker_address` | Broker address | Alamat pelayan MQTT |
| `sensors.broker_port` | Port | Port |

## energy

| Key | English | Bahasa Melayu |
|---|---|---|
| `energy.description` | A/C left on in empty rooms: money, energy and estimated CO2. | Penghawa dingin hidup di bilik kosong: wang, tenaga dan anggaran CO2. |
| `energy.wasted` | Wasted | Dibazirkan |
| `energy.tariff` | at RM {rate} per kWh | pada RM {rate} sekWj |
| `energy.rooms_now` | Empty with the air conditioning on now | Kosong dengan penghawa dingin hidup sekarang |
| `energy.range` | Period | Tempoh |
| `energy.range_today` | Today | Hari ini |
| `energy.range_7d` | 7 days | 7 hari |
| `energy.range_30d` | 30 days | 30 hari |
| `energy.k_rm_today` | Wasted today | Dibazirkan hari ini |
| `energy.k_rm_7d` | Wasted, last 7 days | Dibazirkan, 7 hari lalu |
| `energy.k_rm_30d` | Wasted, last 30 days | Dibazirkan, 30 hari lalu |
| `energy.k_kwh_today` | Energy wasted today | Tenaga dibazirkan hari ini |
| `energy.k_kwh_7d` | Energy wasted, last 7 days | Tenaga dibazirkan, 7 hari lalu |
| `energy.k_kwh_30d` | Energy wasted, last 30 days | Tenaga dibazirkan, 30 hari lalu |
| `energy.k_co2_today` | CO2 estimate, today | Anggaran CO2, hari ini |
| `energy.k_co2_7d` | CO2 estimate, last 7 days | Anggaran CO2, 7 hari lalu |
| `energy.k_co2_30d` | CO2 estimate, last 30 days | Anggaran CO2, 30 hari lalu |
| `energy.co2_factor` | at {f} kg per kWh | pada {f} kg sekWj |
| `energy.by_room_today` | Waste by room, today | Pembaziran mengikut bilik, hari ini |
| `energy.by_room_7d` | Waste by room, last 7 days | Pembaziran mengikut bilik, 7 hari lalu |
| `energy.by_room_30d` | Waste by room, last 30 days | Pembaziran mengikut bilik, 30 hari lalu |
| `energy.over_today` | Waste per hour, today | Pembaziran setiap jam, hari ini |
| `energy.over_7d` | Waste per day, last 7 days | Pembaziran setiap hari, 7 hari lalu |
| `energy.over_30d` | Waste per day, last 30 days | Pembaziran setiap hari, 30 hari lalu |
| `energy.none_today` | No air conditioning waste today. | Tiada pembaziran penghawa dingin hari ini. |
| `energy.none_7d` | No air conditioning waste in the last 7 days. | Tiada pembaziran penghawa dingin dalam 7 hari lalu. |
| `energy.none_30d` | No air conditioning waste in the last 30 days. | Tiada pembaziran penghawa dingin dalam 30 hari lalu. |
| `energy.vs_today` | vs yesterday | berbanding semalam |
| `energy.vs_7d` | vs the 7 days before | berbanding 7 hari sebelumnya |
| `energy.vs_30d` | vs the 30 days before | berbanding 30 hari sebelumnya |
| `energy.same_today` | Same as yesterday | Sama seperti semalam |
| `energy.same_7d` | Same as the 7 days before | Sama seperti 7 hari sebelumnya |
| `energy.same_30d` | Same as the 30 days before | Sama seperti 30 hari sebelumnya |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.description` | Emergencies, drills, offline sensors and A/C waste. | Kecemasan, latihan, sensor luar talian dan pembaziran penghawa dingin. |
| `alerts.count` | {n} alerts | {n} amaran |
| `alerts.count_one` | 1 alert | 1 amaran |
| `alerts.none_filtered` | No alerts match these filters. | Tiada amaran yang sepadan dengan penapis ini. |
| `alerts.col_severity` | Severity | Tahap |
| `alerts.col_type` | Type | Jenis |
| `alerts.col_time` | Time | Masa |
| `alerts.col_alert` | Alert | Amaran |
| `alerts.col_ack` | Acknowledged | Diakui |
| `alerts.all_severities` | All severities | Semua tahap |
| `alerts.all_types` | All types | Semua jenis |
| `alerts.sev_critical` | Critical | Kritikal |
| `alerts.sev_warning` | Warning | Amaran |
| `alerts.sev_info` | Information | Maklumat |
| `alerts.type_emergency` | Emergency | Kecemasan |
| `alerts.type_waste` | Air conditioning waste | Pembaziran penghawa dingin |
| `alerts.type_info` | Emergency mode log | Log mod kecemasan |
| `alerts.open_only` | Not acknowledged only | Belum diakui sahaja |
| `alerts.ack` | Acknowledge | Akui |
| `alerts.acked_by` | {who}, {ago} | {who}, {ago} |
| `alerts.not_acked` | Not acknowledged | Belum diakui |
| `alerts.audit_title` | Audit log | Log audit |
| `alerts.audit_hint` | Every warden and admin action: who, what, from which address and when. | Setiap tindakan warden dan pentadbir: siapa, apa, dari alamat mana dan bila. |
| `alerts.audit_what` | The audit log with IP addresses | Log audit dengan alamat IP |
| `alerts.audit_none` | Emergency mode has not been used yet. | Mod kecemasan belum pernah digunakan. |
| `alerts.audit_start` | Started | Dimulakan |
| `alerts.audit_end` | Ended | Ditamatkan |
| `alerts.col_action` | Action | Tindakan |
| `alerts.col_by` | By | Oleh |
| `alerts.col_ip` | IP address | Alamat IP |
| `alerts.col_duration` | Lasted | Tempoh |

## Ask NADI

| Key | English | Bahasa Melayu |
|---|---|---|
| `chat.admin_needed` | admin sign-in needed (Sign in in the top bar) | log masuk pentadbir diperlukan (Log masuk di bar atas) |

## Emergency view

| Key | English | Bahasa Melayu |
|---|---|---|
| `em.export` | Export for emergency services | Eksport untuk perkhidmatan kecemasan |

## print

| Key | English | Bahasa Melayu |
|---|---|---|
| `print.title` | NADI snapshot for emergency services | Petikan NADI untuk perkhidmatan kecemasan |
| `print.print` | Print or save as PDF | Cetak atau simpan sebagai PDF |
| `print.taken` | Taken {time}. | Diambil {time}. |
| `print.alarm` | Alarm started {time}, {duration} ago. | Penggera bermula {time}, {duration} lalu. |
| `print.no_alarm` | Emergency mode is off. | Mod kecemasan dimatikan. |
| `print.offline` | {n} sensors offline: counts shown are the last known. | {n} sensor luar talian: bilangan yang ditunjukkan ialah bilangan terakhir diketahui. |
| `print.all_live` | All sensors live. | Semua sensor dalam talian. |
| `print.count_source` | Count | Bilangan |
| `print.live` | live | masa nyata |
| `print.footer` | Counts come from Wi-Fi sensing (3+ means 3 or more, ? means the sensor is not reporting). Search every room: a count is a guide, not a guarantee. | Bilangan diperoleh daripada penderiaan Wi-Fi (3+ bermaksud 3 atau lebih, ? bermaksud sensor tidak menghantar data). Periksa setiap bilik: bilangan ialah panduan, bukan jaminan. |

## label

| Key | English | Bahasa Melayu |
|---|---|---|
| `label.what` | Headcount labelling | Pelabelan bilangan orang |

## design

| Key | English | Bahasa Melayu |
|---|---|---|
| `design.title` | Design system | Sistem reka bentuk |
| `design.description` | Colours, type, controls and states used across the console. | Warna, tipografi, kawalan dan keadaan yang digunakan dalam konsol. |
| `design.colour` | Colour | Warna |
| `design.type` | Type | Tipografi |
| `design.controls` | Controls and status | Kawalan dan status |
| `design.loading` | Loading… | Memuatkan… |
| `design.empty` | Empty | Kosong |
| `design.error` | Error | Ralat |
| `design.banner` | Banners | Makluman |
| `design.table` | Table | Jadual |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.not_found` | There is no such API address. | Tiada alamat API sedemikian. |
| `api.console_not_built` | The web console has not been built. Run npm run build in the web folder. | Konsol web belum dibina. Jalankan npm run build dalam folder web. |

## sensors

| Key | English | Bahasa Melayu |
|---|---|---|
| `sensors.type_simulator` | Simulated sensors | Sensor simulasi |
| `sensors.all_rooms` | All rooms | Semua bilik |

## nav

| Key | English | Bahasa Melayu |
|---|---|---|
| `nav.skip` | Skip to content | Langkau ke kandungan |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.too_large` | The request is too large: the limit is {limit} bytes. | Permintaan terlalu besar: hadnya {limit} bait. |
| `api.redis_offline` | The live data store (Redis) is offline. Try again shortly. | Stor data langsung (Redis) di luar talian. Cuba lagi sebentar lagi. |
| `api.mysql_offline` | The history database (MySQL) is offline. Try again shortly. | Pangkalan data sejarah (MySQL) di luar talian. Cuba lagi sebentar lagi. |
| `api.locked_out` | Too many wrong admin tokens from this address. Try again in {minutes} minutes. | Terlalu banyak token pentadbir yang salah dari alamat ini. Cuba lagi dalam {minutes} minit. |
| `api.rate_limited` | Too many requests. Try again in {seconds} seconds. | Terlalu banyak permintaan. Cuba lagi dalam {seconds} saat. |
| `api.question_too_long` | The question is too long: the limit is {limit} characters. | Soalan terlalu panjang: hadnya {limit} aksara. |
| `api.reject_missing` | {field} is missing. | {field} tiada. |
| `api.reject_type` | {field} must be a number. | {field} mesti nombor. |
| `api.reject_range` | {field} must be between {low} and {high}. | {field} mesti antara {low} dan {high}. |
| `api.reject_shape` | Each entry must have a service_id and properties. | Setiap entri mesti mempunyai service_id dan properties. |
| `api.reject_service` | service_id must be csi or climate. | service_id mesti csi atau climate. |
| `api.reject_room_id` | room_id may use only letters, digits, - and _ (up to 32). | room_id hanya boleh mengandungi huruf, digit, - dan _ (maksimum 32). |
| `api.reject_unknown_room` | {room} is not a registered room. | {room} bukan bilik yang berdaftar. |
| `api.reject_device_room` | Device {device} may not report for {room}. | Peranti {device} tidak dibenarkan menghantar data untuk {room}. |
| `api.reject_ts_old` | ts is more than one day old. | ts lebih lama daripada satu hari. |
| `api.reject_ts_future` | The timestamp is more than 5 minutes ahead of the server clock. | Cap masa melebihi 5 minit ke hadapan berbanding jam pelayan. |
| `api.reject_no_services` | The report has no services list. | Laporan tidak mempunyai senarai perkhidmatan. |
| `api.reject_too_many` | The report has more than 50 entries. | Laporan mempunyai lebih daripada 50 entri. |

## Chat answers (built-in)

| Key | English | Bahasa Melayu |
|---|---|---|
| `answer.unknown_one` | 1 room is not reporting, so its count is unknown: {rooms}. | 1 bilik tidak menghantar data, jadi bilangannya tidak diketahui: {rooms}. |
| `answer.unknown_many` | {n} rooms are not reporting, so their counts are unknown: {rooms}. | {n} bilik tidak menghantar data, jadi bilangannya tidak diketahui: {rooms}. |
| `answer.total_none_known` | No one is inside the rooms that are reporting. | Tiada orang di dalam bilik yang menghantar data. |

## Alert messages (SMN and console)

| Key | English | Bahasa Melayu |
|---|---|---|
| `alert.emergency_body_unknown` | At least {total} {people} inside when the alarm started. {rooms} Not reporting, count unknown ({n}): {unknown}. | Sekurang-kurangnya {total} orang di dalam semasa penggera berbunyi. {rooms} Tidak menghantar data, bilangan tidak diketahui ({n}): {unknown}. |
| `alert.suspicious_subject` | Suspicious reading | Bacaan mencurigakan |
| `alert.suspicious_body` | {name} went from {before} to {after} {people} in one report. The reading is held back until the next report confirms it. | {name} berubah daripada {before} kepada {after} orang dalam satu laporan. Bacaan ini ditahan sehingga laporan seterusnya mengesahkannya. |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.viewer_required` | A viewer token is required to see this dashboard. | Token pemerhati diperlukan untuk melihat papan pemuka ini. |

## safety

| Key | English | Bahasa Melayu |
|---|---|---|
| `safety.disclaimer` | NADI assists rescuers; it does not replace a physical sweep. Counts may be incomplete. | NADI membantu pasukan penyelamat; NADI tidak menggantikan pemeriksaan fizikal. Bilangan mungkin tidak lengkap. |

## Header and page

| Key | English | Bahasa Melayu |
|---|---|---|
| `ui.rooms_reporting` | {live}/{total} rooms reporting | {live}/{total} bilik menghantar data |

## count

| Key | English | Bahasa Melayu |
|---|---|---|
| `count.at_least` | at least {n} | sekurang-kurangnya {n} |
| `count.at_least_label` | At least | Sekurang-kurangnya |
| `count.unknown` | Count unknown: sensor not reporting | Bilangan tidak diketahui: sensor tidak menghantar data |

## room

| Key | English | Bahasa Melayu |
|---|---|---|
| `room.sim_counter` | Simulated counter (phase 2) | Pembilang simulasi (fasa 2) |

## count

| Key | English | Bahasa Melayu |
|---|---|---|
| `count.unknown_one` | 1 room unknown | 1 bilik tidak diketahui |
| `count.unknown_many` | {n} rooms unknown | {n} bilik tidak diketahui |
| `count.last_known` | Unknown now, last known {count} ({ago}) | Tidak diketahui sekarang, bilangan terakhir {count} ({ago}) |
| `count.unknown_short` | Count unknown | Bilangan tidak diketahui |
| `count.last_short` | last known {count} | bilangan terakhir {count} |

## Floor plan

| Key | English | Bahasa Melayu |
|---|---|---|
| `plan.room_unknown` | {name}: count unknown, {status} | {name}: bilangan tidak diketahui, {status} |

## Admin

| Key | English | Bahasa Melayu |
|---|---|---|
| `admin.sign_out_short` | Sign out | Log keluar |

## viewer

| Key | English | Bahasa Melayu |
|---|---|---|
| `viewer.title` | Viewer sign-in | Log masuk pemerhati |
| `viewer.body` | This dashboard needs a viewer token. Ask the building manager for one. It is kept for this browser tab only. | Papan pemuka ini memerlukan token pemerhati. Minta token daripada pengurus bangunan. Token ini disimpan untuk tab pelayar ini sahaja. |
| `viewer.token_label` | Viewer token | Token pemerhati |
| `viewer.sign_out` | Sign out of the dashboard | Log keluar daripada papan pemuka |

## sensors

| Key | English | Bahasa Melayu |
|---|---|---|
| `sensors.show_retired` | Show devices not seen for 24 hours ({n}) | Tunjukkan peranti yang tidak dilihat selama 24 jam ({n}) |
| `sensors.retired` | Not seen for 24 h | Tidak dilihat 24 jam |
| `sensors.clear_test` | Clear test devices | Kosongkan peranti ujian |
| `sensors.clear_confirm` | Remove the simulator and devices not seen for 24 hours from this list? A device that reports again comes back. | Buang simulator dan peranti yang tidak dilihat selama 24 jam daripada senarai ini? Peranti yang melapor semula akan kembali. |
| `sensors.cleared` | {n} devices cleared. | {n} peranti dikosongkan. |
| `sensors.cleared_one` | 1 device cleared. | 1 peranti dikosongkan. |
| `sensors.type_counter` | People counter | Pembilang orang |

## label

| Key | English | Bahasa Melayu |
|---|---|---|
| `label.custom` | Other number (0 to 100) | Nombor lain (0 hingga 100) |
| `label.save_custom` | Save | Simpan |
| `label.sensor_hidden` | Sensor count hidden while you label | Bilangan sensor disembunyikan semasa anda melabel |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.page` | Page {page} of {pages} | Halaman {page} daripada {pages} |
| `alerts.prev` | Previous | Sebelumnya |
| `alerts.next` | Next | Seterusnya |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.cross_site` | Refused: this request came from another website. | Ditolak: permintaan ini datang daripada laman web lain. |
| `api.ingest_local_only` | Readings may only be posted from this computer unless INGEST_TOKEN is set. | Bacaan hanya boleh dihantar dari komputer ini melainkan INGEST_TOKEN ditetapkan. |
| `api.no_emergency` | Emergency mode or a drill is not on. | Mod kecemasan atau latihan tidak aktif. |
| `api.incident_unknown` | No such report. | Laporan tersebut tidak wujud. |

## drill

| Key | English | Bahasa Melayu |
|---|---|---|
| `drill.flag` | Drill | Latihan |
| `drill.banner` | DRILL: this is a practice run, not a real emergency. | LATIHAN: ini ialah latihan, bukan kecemasan sebenar. |
| `drill.since` | since the drill started | sejak latihan bermula |
| `drill.start` | Start drill | Mulakan latihan |
| `drill.end` | End drill | Tamatkan latihan |
| `drill.keep` | Keep the drill running | Teruskan latihan |
| `drill.confirm_end` | End the drill on every screen | Tamatkan latihan pada semua skrin |
| `drill.ui_banner` | Drill running: every screen shows the emergency view with a DRILL banner. | Latihan sedang berjalan: semua skrin memaparkan paparan kecemasan dengan sepanduk LATIHAN. |

## Start emergency dialog

| Key | English | Bahasa Melayu |
|---|---|---|
| `start.drill_hint` | A drill shows the same screens with a DRILL banner. Its alerts say DRILL, and it is kept apart from real incidents. | Latihan memaparkan skrin yang sama dengan sepanduk LATIHAN. Amarannya ditandakan LATIHAN, dan rekodnya diasingkan daripada insiden sebenar. |

## Alert messages (SMN and console)

| Key | English | Bahasa Melayu |
|---|---|---|
| `alert.drill_subject` | [DRILL] {subject} | [LATIHAN] {subject} |
| `alert.drill_body` | {body} This is a drill, not a real emergency. | {body} Ini ialah latihan, bukan kecemasan sebenar. |

## Chat answers (built-in)

| Key | English | Bahasa Melayu |
|---|---|---|
| `answer.drill_on` | A drill is running. It started {minutes} {minute_word} ago. | Latihan sedang berjalan. Latihan bermula {minutes} minit lalu. |

## acc

| Key | English | Bahasa Melayu |
|---|---|---|
| `acc.col` | Warden check | Semakan warden |
| `acc.none` | Not marked | Belum ditanda |
| `acc.clear` | Searched, clear | Telah diperiksa, tiada orang |
| `acc.help` | People still inside, need help | Orang masih di dalam, perlukan bantuan |
| `acc.help_short` | Need help | Perlukan bantuan |
| `acc.clear_short` | Clear | Tiada orang |
| `acc.undo` | Remove mark | Buang tanda |
| `acc.by` | {status} ({who}, {time}) | {status} ({who}, {time}) |
| `acc.hint` | Wardens: mark each room once searched. | Warden: tandakan setiap bilik selepas diperiksa. |

## print

| Key | English | Bahasa Melayu |
|---|---|---|
| `print.call` | Emergency number: {number} | Nombor kecemasan: {number} |
| `print.number_default` | 999 (112 from a mobile phone) | 999 (112 dari telefon bimbit) |
| `print.saved` | Saved automatically by NADI at {time} (Malaysia time). Record {id}. | Disimpan secara automatik oleh NADI pada {time} (waktu Malaysia). Rekod {id}. |
| `print.autosaved` | A copy is saved on the server every minute: {n} so far, the last at {time}. | Satu salinan disimpan di pelayan setiap minit: {n} setakat ini, yang terakhir pada {time}. |

## Times

| Key | English | Bahasa Melayu |
|---|---|---|
| `time.zone` | Malaysia time | waktu Malaysia |

## report

| Key | English | Bahasa Melayu |
|---|---|---|
| `report.title_real` | Incident report | Laporan insiden |
| `report.title_drill` | Drill report | Laporan latihan |
| `report.record` | Record {id} | Rekod {id} |
| `report.started` | Started | Bermula |
| `report.ended` | Ended | Tamat |
| `report.duration` | Duration | Tempoh |
| `report.by` | by {who} | oleh {who} |
| `report.people_start` | People inside at the start | Orang di dalam semasa bermula |
| `report.unknown_start` | Not reporting at the start: {rooms} | Tidak menghantar data semasa bermula: {rooms} |
| `report.rooms_title` | Rooms | Bilik |
| `report.col_start` | At the start | Semasa bermula |
| `report.col_zero` | Reached zero after | Menjadi sifar selepas |
| `report.col_end` | At the end | Pada akhir |
| `report.empty_start` | Empty at the start | Kosong semasa bermula |
| `report.not_zero` | Did not reach zero | Tidak menjadi sifar |
| `report.offline_title` | Sensors offline during the event | Sensor luar talian semasa kejadian |
| `report.offline_none` | No sensor went offline. | Tiada sensor yang luar talian. |
| `report.period` | {start} to {end} | {start} hingga {end} |
| `report.until_end` | the end | akhir kejadian |
| `report.alerts_title` | Alerts and acknowledgements | Amaran dan pengesahan |
| `report.alerts_none` | No alerts during the event. | Tiada amaran semasa kejadian. |
| `report.snapshots` | {n} snapshots saved on the server, the last at {time}. | {n} petikan disimpan di pelayan, yang terakhir pada {time}. |
| `report.snapshots_one` | 1 snapshot saved on the server, at {time}. | 1 petikan disimpan di pelayan, pada {time}. |
| `report.open_snapshot` | Open the last snapshot | Buka petikan terakhir |
| `report.not_found` | Report not found. | Laporan tidak dijumpai. |
| `report.back` | Back to alerts | Kembali ke amaran |

## incidents

| Key | English | Bahasa Melayu |
|---|---|---|
| `incidents.title` | Incident and drill reports | Laporan insiden dan latihan |
| `incidents.hint` | Written when emergency mode or a drill ends. Open one to print it. | Ditulis apabila mod kecemasan atau latihan tamat. Buka laporan untuk mencetaknya. |
| `incidents.real` | Real incidents | Insiden sebenar |
| `incidents.drills` | Drills | Latihan |
| `incidents.none` | None yet. | Belum ada. |
| `incidents.col_people` | People at the start | Orang semasa bermula |
| `incidents.col_marked` | Rooms marked | Bilik ditanda |
| `incidents.col_offline` | Rooms offline | Bilik luar talian |
| `incidents.open` | Open | Buka |
| `incidents.active` | Running now: {n} snapshots saved. | Sedang berjalan: {n} petikan disimpan. |
| `incidents.active_one` | Running now: 1 snapshot saved. | Sedang berjalan: 1 petikan disimpan. |
| `incidents.demo` | Demo | Demo |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.type_sensor` | Sensor | Sensor |
| `alerts.type_drill` | Drill | Latihan |
| `alerts.audit_room_clear` | Room marked clear | Bilik ditanda tiada orang |
| `alerts.audit_room_help` | Room marked: need help | Bilik ditanda: perlukan bantuan |
| `alerts.audit_room_reset` | Room mark removed | Tanda bilik dibuang |
| `alerts.audit_delete_all` | All stored data deleted | Semua data yang disimpan dipadam |
| `alerts.audit_drill` | Drill | Latihan |
| `alerts.col_room` | Room | Bilik |
| `alerts.attention_now` | Needs attention now | Perlu perhatian sekarang |
| `alerts.audit_energy` | Energy settings changed | Tetapan tenaga diubah |
| `alerts.audit_plan_save` | Floor plan saved | Pelan lantai disimpan |
| `alerts.audit_plan_restore` | Floor plan restored | Pelan lantai dipulihkan |
| `alerts.audit_site_add` | Building or floor added | Bangunan atau tingkat ditambah |
| `alerts.audit_site_rename` | Building or floor renamed | Bangunan atau tingkat dinamakan semula |
| `alerts.audit_plan_image` | Floor plan image uploaded | Imej pelan lantai dimuat naik |
| `alerts.audit_plan_detail` | {floor}, version {version} | {floor}, versi {version} |

## Alert messages (SMN and console)

| Key | English | Bahasa Melayu |
|---|---|---|
| `alert.sensor_offline_subject` | NADI: Sensor stopped reporting ({rooms}) | NADI: Sensor berhenti menghantar data ({rooms}) |
| `alert.sensor_offline_body` | The {kind} sensor for {rooms} has not reported for {seconds} seconds. Counts there are unknown until it reports again. | Sensor {kind} bagi {rooms} tidak menghantar data selama {seconds} saat. Bilangan di situ tidak diketahui sehingga sensor menghantar data semula. |
| `alert.sensor_online_subject` | NADI: Sensor back online ({rooms}) | NADI: Sensor kembali dalam talian ({rooms}) |
| `alert.sensor_online_body` | The {kind} sensor for {rooms} is reporting again. | Sensor {kind} bagi {rooms} menghantar data semula. |

## sensor

| Key | English | Bahasa Melayu |
|---|---|---|
| `sensor.kind_count` | occupancy | penghunian |
| `sensor.kind_climate` | temperature | suhu |

## privacy

| Key | English | Bahasa Melayu |
|---|---|---|
| `privacy.title` | Delete all stored data | Padam semua data yang disimpan |
| `privacy.body` | For a personal data request (PDPA). Deletes every reading, label, alert, audit entry, report and snapshot. This cannot be undone. | Untuk permintaan data peribadi (PDPA). Memadam semua bacaan, label, amaran, entri audit, laporan dan petikan. Tindakan ini tidak boleh dibatalkan. |
| `privacy.type` | Type {phrase} to confirm | Taip {phrase} untuk mengesahkan |
| `privacy.phrase` | DELETE ALL DATA | PADAM SEMUA DATA |
| `privacy.go` | Delete everything | Padam semua |
| `privacy.done` | All stored data has been deleted. | Semua data yang disimpan telah dipadam. |
| `privacy.what` | Deleting stored data | Pemadaman data yang disimpan |

## Server error messages

| Key | English | Bahasa Melayu |
|---|---|---|
| `api.delete_confirm` | Type {phrase} to confirm. | Taip {phrase} untuk mengesahkan. |
| `api.delete_emergency` | Not during emergency mode or a drill. | Tidak dibenarkan semasa mod kecemasan atau latihan. |
| `api.floor_unknown` | There is no floor {floor}. | Tiada tingkat {floor}. |

## banner

| Key | English | Bahasa Melayu |
|---|---|---|
| `banner.clock` | The server clock is {n} seconds off internet time. Times shown may be wrong. | Jam pelayan berbeza {n} saat daripada waktu internet. Masa yang dipaparkan mungkin salah. |

## Alert messages (SMN and console)

| Key | English | Bahasa Melayu |
|---|---|---|
| `alert.sensor_offline_body_minutes` | The {kind} sensor for {rooms} has not reported for {minutes} {minute_word}. Counts there are unknown until it reports again. | Sensor {kind} bagi {rooms} tidak menghantar data selama {minutes} minit. Bilangan di situ tidak diketahui sehingga sensor menghantar data semula. |

## list

| Key | English | Bahasa Melayu |
|---|---|---|
| `list.more` | {n} more | {n} lagi |
| `list.view_all` | View all {n} | Lihat semua {n} |
| `list.show_more` | Show {n} more | Papar {n} lagi |
| `list.show_fewer` | Show fewer | Papar kurang |
| `list.and_more` | and {n} more | dan {n} lagi |

## ov

| Key | English | Bahasa Melayu |
|---|---|---|
| `ov.status_label` | Building status | Status bangunan |
| `ov.s_updated` | updated {ago} | dikemas kini {ago} |
| `ov.live` | Live | Langsung |
| `ov.not_live` | Not updating | Tidak dikemas kini |
| `ov.no_live_data` | No live data | Tiada data langsung |
| `ov.loading_status` | Checking the building… | Memeriksa bangunan… |
| `ov.span_s` | {n} s | {n} saat |
| `ov.span_min` | {n} min | {n} minit |
| `ov.span_h` | {n} h | {n} jam |
| `ov.attention_title` | Needs attention | Perlu perhatian |
| `ov.attention_none` | Nothing needs attention | Tiada apa-apa yang memerlukan perhatian |
| `ov.attention_none_hint` | Air conditioning waste, silent sensors and suspicious readings appear here. | Pembaziran penghawa dingin, sensor senyap dan bacaan mencurigakan dipaparkan di sini. |
| `ov.attention_count` | {n} to deal with | {n} perlu ditangani |
| `ov.kind_service` | Service offline | Perkhidmatan luar talian |
| `ov.kind_connection` | Connection lost | Sambungan terputus |
| `ov.att_connection` | This screen | Skrin ini |
| `ov.att_redis` | Live data store | Storan data langsung |
| `ov.att_mqtt` | Sensor link | Sambungan sensor |
| `ov.att_mysql` | History database | Pangkalan data sejarah |
| `ov.att_sensor_for` | sensor offline, no report for {span} | sensor luar talian, tiada laporan selama {span} |
| `ov.att_sensor` | sensor offline | sensor luar talian |
| `ov.att_last_known` | count unknown (last known {count}) | bilangan tidak diketahui (bilangan terakhir {count}) |
| `ov.att_unknown` | count unknown | bilangan tidak diketahui |
| `ov.att_waste` | empty {minutes} min, A/C on | kosong {minutes} min, A/C hidup |
| `ov.att_rm` | RM {rm} so far | RM {rm} setakat ini |
| `ov.todo_label` | What to do | Tindakan |
| `ov.todo_waste` | Switch off the air conditioner in this room. | Matikan penghawa dingin di bilik ini. |
| `ov.todo_sensor` | Check the board's power and Wi-Fi. Treat the room as unknown, not empty. | Periksa bekalan kuasa dan Wi-Fi papan. Anggap bilik ini tidak diketahui, bukan kosong. |
| `ov.todo_service` | Check that the services are running on the server computer (docs/DEPLOYMENT.md). | Pastikan perkhidmatan berjalan pada komputer pelayan (docs/DEPLOYMENT.md). |
| `ov.todo_connection` | Check that the NADI server is running and that this computer is on the same network. | Pastikan pelayan NADI berjalan dan komputer ini berada dalam rangkaian yang sama. |
| `ov.todo_suspicious` | Nothing to do if the next report agrees. Check the room if it happens again. | Tiada tindakan diperlukan jika laporan seterusnya sepadan. Periksa bilik jika berulang. |
| `ov.ack_failed` | Could not acknowledge this. | Tidak dapat mengakui perkara ini. |
| `ov.activity_title` | Live activity | Aktiviti langsung |
| `ov.activity_none` | No activity yet. Alerts and events appear here as they happen. | Belum ada aktiviti. Amaran dan peristiwa akan dipaparkan di sini apabila berlaku. |
| `ov.plan_title` | Live floor plan | Pelan lantai langsung |

## Floor plan

| Key | English | Bahasa Melayu |
|---|---|---|
| `plan.no_sensor` | No sensor | Tiada sensor |
| `plan.room_no_sensor` | {name}: no sensor | {name}: tiada sensor |

## ov

| Key | English | Bahasa Melayu |
|---|---|---|
| `ov.signal_title` | Live signal | Isyarat langsung |
| `ov.signal_none` | No reports from this room in the last {minutes} minutes. | Tiada laporan dari bilik ini dalam {minutes} minit lalu. |
| `ov.signal_no_room` | No room with Wi-Fi sensing has reported yet. | Belum ada bilik dengan sensor Wi-Fi yang menghantar data. |
| `ov.signal_mysql` | History database offline. The chart returns when it is back. | Pangkalan data sejarah di luar talian. Carta akan kembali apabila ia pulih. |
| `ov.signal_now` | Now {x} dB | Kini {x} dB |
| `ov.signal_offline` | Sensor offline | Sensor luar talian |
| `ov.signal_since` | No data since {time} | Tiada data sejak {time} |
| `ov.signal_axis` | Motion (dB) | Pergerakan (dB) |
| `ov.signal_motion` | Motion | Pergerakan |
| `ov.today_label` | Today's summary | Ringkasan hari ini |
| `ov.today_peak` | Peak people today | Puncak orang hari ini |
| `ov.today_peak_hint` | most inside at once | paling ramai serentak |
| `ov.today_hours` | Hours occupied today | Jam berpenghuni hari ini |
| `ov.today_hours_value` | {n} h | {n} jam |
| `ov.today_hours_hint` | with someone inside | ada orang di dalam |
| `ov.today_uptime` | Sensor uptime today | Masa aktif sensor hari ini |
| `ov.today_uptime_hint` | time online since the first report today | masa dalam talian sejak laporan pertama hari ini |
| `ov.today_none` | no data yet today | belum ada data hari ini |
| `ov.today_offline` | history database offline | pangkalan data sejarah di luar talian |
| `ov.off_plan` | Not on this plan | Tiada dalam pelan ini |
| `ov.today_full` | View full summary | Lihat ringkasan penuh |
| `ov.today_incidents` | Emergency and drills | Kecemasan dan latihan |
| `ov.today_normal` | Normal | Biasa |
| `ov.today_no_drill` | no drill today | tiada latihan hari ini |
| `ov.today_drills_one` | 1 drill today, last at {time} | 1 latihan hari ini, terakhir pada {time} |
| `ov.today_drills_many` | {n} drills today, last at {time} | {n} latihan hari ini, terakhir pada {time} |
| `ov.today_last_drill` | last drill: {date} | latihan terakhir: {date} |
| `ov.today_emergencies` | emergencies today: {n} | kecemasan hari ini: {n} |
| `ov.signal_unit` | dB | dB |

## Emergency view

| Key | English | Bahasa Melayu |
|---|---|---|
| `em.still_inside_one` | person still inside | orang masih di dalam |

## sig

| Key | English | Bahasa Melayu |
|---|---|---|
| `sig.title` | Signal | Isyarat |
| `sig.sender` | Sender | Penghantar |
| `sig.receiver` | Receiver | Penerima |
| `sig.calm` | Calm signal: {x} dB, below the threshold of {t} dB | Isyarat tenang: {x} dB, di bawah ambang {t} dB |
| `sig.disturbed` | Disturbed signal: {x} dB, above the threshold of {t} dB | Isyarat terganggu: {x} dB, melepasi ambang {t} dB |
| `sig.calm_model` | Calm signal: {x} dB, counted as empty | Isyarat tenang: {x} dB, dikira sebagai kosong |
| `sig.disturbed_model` | Disturbed signal: {x} dB, counted as occupied | Isyarat terganggu: {x} dB, dikira sebagai berpenghuni |
| `sig.offline` | Sensor offline: no signal is being measured | Sensor luar talian: tiada isyarat yang diukur |
| `sig.waiting` | No report from this room in the last {minutes} minutes | Tiada laporan dari bilik ini dalam {minutes} minit lalu |
| `sig.no_sensor_hint` | Drawn on the plan for orientation only. NADI does not count people in this room. | Dilukis pada pelan sebagai panduan sahaja. NADI tidak mengira orang di bilik ini. |

## rec

| Key | English | Bahasa Melayu |
|---|---|---|
| `rec.title` | Recorded waves | Gelombang yang dirakam |
| `rec.kind.empty` | Empty room | Bilik kosong |
| `rec.kind.walk` | One person walking through the line | Seorang berjalan melintasi garisan |
| `rec.kind.hand` | Hand waved near the receiver | Tangan dilambai berhampiran penerima |
| `rec.kind.moved` | Sender moved by hand | Penghantar digerakkan dengan tangan |
| `rec.kind.other` | Recording | Rakaman |
| `rec.spread` | Measured spread (standard deviation): {x} dB over {n} packets | Sebaran yang diukur (sisihan piawai): {x} dB bagi {n} paket |
| `rec.caption` | Signal strength of each Wi-Fi packet between this room's two boards, {rate} per second. A body in the path disturbs it. | Kekuatan isyarat setiap paket Wi-Fi antara dua papan di bilik ini, {rate} paket sesaat. Tubuh yang berada di laluan mengganggunya. |
| `rec.source` | Recorded on {date} with the boards {distance} m apart. | Dirakam pada {date} dengan jarak {distance} m antara dua papan. |
| `rec.source_no_distance` | Recorded on {date}. | Dirakam pada {date}. |
| `rec.axis` | RSSI (dBm) | RSSI (dBm) |
| `rec.axis_time` | Seconds | Saat |
| `rec.chart_label` | {what}: signal strength of {n} packets over {seconds} seconds, between {min} and {max} dBm | {what}: kekuatan isyarat {n} paket dalam {seconds} saat, antara {min} dan {max} dBm |

## cal

| Key | English | Bahasa Melayu |
|---|---|---|
| `cal.detector_rule_hint` | A room counts as occupied when the movement of its signal rises above the threshold. | Bilik dikira berpenghuni apabila pergerakan isyaratnya melepasi ambang. |
| `cal.detector_model_hint` | A model trained with Huawei MindSpore turns each report into a headcount. | Model yang dilatih dengan Huawei MindSpore menukar setiap laporan kepada bilangan orang. |
| `cal.training_title` | Model training · Huawei MindSpore | Latihan model · Huawei MindSpore |
| `cal.model_none` | No trained model file yet. | Belum ada fail model terlatih. |
| `cal.model_active` | Active: this model is counting people now. | Aktif: model ini sedang mengira orang sekarang. |
| `cal.model_inactive_synth` | Not active: trained on simulated data. Goes live once it beats the rule on real labelled data. | Tidak aktif: dilatih dengan data simulasi. Digunakan apabila mengatasi peraturan pada data berlabel sebenar. |
| `cal.model_inactive` | Not active: the calibrated rule is counting. A model goes live only when it beats the rule on real labelled data. | Tidak aktif: peraturan terkalibrasi sedang mengira. Model hanya digunakan apabila mengatasi peraturan pada data berlabel sebenar. |
| `cal.fact_framework` | Framework | Rangka kerja |
| `cal.fact_trained_on` | Trained on | Dilatih dengan |
| `cal.fact_rows` | Training rows | Baris latihan |
| `cal.fact_trained_at` | Trained | Dilatih pada |
| `cal.fact_accuracy` | Accuracy on its own test rows | Ketepatan pada baris ujiannya sendiri |
| `cal.fact_rule_accuracy` | Threshold rule on the same rows | Peraturan ambang pada baris yang sama |
| `cal.data_synthetic` | simulated data | data simulasi |
| `cal.data_real` | real labelled data | data berlabel sebenar |
| `cal.dots_title` | Labelled reports | Laporan berlabel |
| `cal.dots_caption` | Each dot is a real {seconds}-second report we labelled. | Setiap titik ialah laporan sebenar {seconds} saat yang telah kami labelkan. |
| `cal.dots_empty` | Labelled empty | Dilabel kosong |
| `cal.dots_occupied` | Labelled occupied | Dilabel berpenghuni |
| `cal.dots_count` | {empty} labelled empty, {occupied} labelled occupied | {empty} dilabel kosong, {occupied} dilabel berpenghuni |
| `cal.dots_label` | {name}: {empty} reports labelled empty, {occupied} labelled occupied, motion from {min} to {max} dB | {name}: {empty} laporan dilabel kosong, {occupied} dilabel berpenghuni, pergerakan dari {min} hingga {max} dB |
| `cal.threshold` | threshold {x} dB | ambang {x} dB |
| `cal.none` | No labelled data yet | Belum ada data berlabel |
| `cal.none_hint` | Label a still room as 0 and a walk through the line as 1. The reports sent during each label appear here. | Labelkan bilik yang tenang sebagai 0 dan berjalan melintasi garisan sebagai 1. Laporan yang dihantar semasa setiap label akan dipaparkan di sini. |
| `cal.mysql` | History database offline. The labelled reports return when it is back. | Pangkalan data sejarah di luar talian. Laporan berlabel akan kembali apabila ia pulih. |

## sig

| Key | English | Bahasa Melayu |
|---|---|---|
| `sig.plan_id` | Room ID on the plan: {id} | ID bilik pada pelan: {id} |
| `sig.no_report_hint` | A sensor pair is drawn here, but no report has arrived yet. The count is unknown until one does. | Sepasang sensor dilukis di sini, tetapi belum ada laporan. Bilangan tidak diketahui sehingga laporan diterima. |
| `sig.room` | Room shown | Bilik dipaparkan |
| `sig.none_here` | No sensor in this room | Tiada sensor di bilik ini |
| `sig.not_yet` | No report from this room yet | Belum ada laporan dari bilik ini |
| `sig.threshold_tip` | Threshold {x} dB | Ambang {x} dB |
| `sig.chart_label` | Live signal of {name}: now {now} dB, threshold {x} dB; above the threshold the room counts as occupied. | Isyarat langsung {name}: kini {now} dB, ambang {x} dB; di atas ambang bilik dikira berpenghuni. |
| `sig.chart_model` | Live signal of {name}: now {now} dB; a trained model is counting, so there is no single threshold. | Isyarat langsung {name}: kini {now} dB; model terlatih sedang mengira, jadi tiada satu ambang. |
| `sig.chart_offline` | Live signal of {name}: sensor offline, no data since {time}; threshold {x} dB. | Isyarat langsung {name}: sensor luar talian, tiada data sejak {time}; ambang {x} dB. |
| `sig.chart_above` | Live signal of {name}: now {now} dB, above the threshold of {x} dB: movement detected. | Isyarat langsung {name}: kini {now} dB, di atas ambang {x} dB: pergerakan dikesan. |
| `sig.chart_below` | Live signal of {name}: now {now} dB, below the threshold of {x} dB: steady. | Isyarat langsung {name}: kini {now} dB, di bawah ambang {x} dB: stabil. |
| `sig.range` | Time range | Julat masa |
| `sig.range_1h` | 1 h | 1 j |
| `sig.range_24h` | 24 h | 24 j |
| `sig.range_7d` | 7 d | 7 h |
| `sig.range_30d` | 30 d | 30 h |
| `sig.range_long_24h` | the last 24 hours | 24 jam lalu |
| `sig.range_long_7d` | the last 7 days | 7 hari lalu |
| `sig.range_long_30d` | the last 30 days | 30 hari lalu |
| `sig.people_title` | People | Penghuni |

## cal

| Key | English | Bahasa Melayu |
|---|---|---|
| `cal.fact_accuracy_sim` | Accuracy on simulated test rows | Ketepatan pada baris ujian simulasi |
| `cal.fact_rule_accuracy_sim` | Threshold rule on the same simulated rows | Peraturan ambang pada baris simulasi yang sama |

## Floor plan

| Key | English | Bahasa Melayu |
|---|---|---|
| `plan.no_report` | No report yet | Belum ada laporan |
| `plan.room_no_report` | {name}: no report yet | {name}: belum ada laporan |
| `plan.select_hint` | Click a room for its chart, double-click for details | Klik bilik untuk cartanya, klik dua kali untuk butiran |

## nav

| Key | English | Bahasa Melayu |
|---|---|---|
| `nav.expand` | Open the menu | Buka menu |
| `nav.collapse` | Collapse the menu | Kecilkan menu |
| `nav.alerts_count` | {label}: {n} not acknowledged | {label}: {n} belum disahkan |
| `nav.open_alerts` | Not acknowledged | Belum disahkan |

## ask

| Key | English | Bahasa Melayu |
|---|---|---|
| `ask.placeholder` | Ask NADI about the building… | Tanya NADI tentang bangunan ini… |
| `ask.label` | Ask NADI a question | Tanya NADI satu soalan |
| `ask.open` | Open Ask NADI | Buka Tanya NADI |

## Ask NADI

| Key | English | Bahasa Melayu |
|---|---|---|
| `chat.try` | Try one of these questions | Cuba salah satu soalan ini |
| `chat.q_waste_which` | Which rooms waste air conditioning? | Bilik mana yang membazirkan penghawa dingin? |
| `chat.q_occupied` | Which rooms have people? | Bilik mana ada orang? |
| `chat.you` | You | Anda |
| `chat.nadi` | NADI | NADI |
| `chat.foot_rules` | Answered from live sensor data. | Dijawab daripada data sensor langsung. |
| `chat.foot_model` | Worded by {model}. Numbers from live sensor data. | Ayat disusun oleh {model}. Angka daripada data sensor langsung. |

## bs

| Key | English | Bahasa Melayu |
|---|---|---|
| `bs.overall` | Overall | Keseluruhan |
| `bs.rooms` | Rooms | Bilik |
| `bs.sensors` | Sensors | Sensor |
| `bs.occupied` | {n} occupied | {n} berpenghuni |
| `bs.empty` | {n} empty | {n} kosong |
| `bs.unknown` | {n} unknown | {n} tidak diketahui |
| `bs.no_sensor` | {n} no sensor | {n} tiada sensor |
| `bs.no_report` | {n} no report yet | {n} belum ada laporan |
| `bs.no_waste` | No waste | Tiada pembaziran |
| `bs.waste_one` | {n} empty, A/C on | {n} kosong, A/C hidup |
| `bs.waste_many` | {n} empty, A/C on | {n} kosong, A/C hidup |
| `bs.all_online` | All online | Semua dalam talian |
| `bs.online` | {n} online | {n} dalam talian |
| `bs.offline` | {n} offline | {n} luar talian |
| `bs.none_reporting` | No sensor reporting | Tiada sensor menghantar data |
| `bs.drill` | Drill running | Latihan sedang berjalan |
| `bs.emergency_on` | Emergency active | Kecemasan aktif |
| `bs.all_clear` | All clear | Semua terkawal |
| `bs.attention_one` | {n} needs attention | {n} perlu perhatian |
| `bs.attention_many` | {n} need attention | {n} perlu perhatian |
| `bs.ac_today` | Air conditioning waste today | Pembaziran penghawa dingin hari ini |
| `bs.kwh` | {kwh} kWh | {kwh} kWj |
| `bs.none_now` | None right now | Tiada sekarang |

## det

| Key | English | Bahasa Melayu |
|---|---|---|
| `det.title` | Detection | Pengesanan |
| `det.live` | Live detector | Pengesan semasa |
| `det.rule` | Calibrated rule, threshold {x} dB | Peraturan terkalibrasi, ambang {x} dB |
| `det.rule_plain` | Calibrated rule | Peraturan terkalibrasi |
| `det.model` | MindSpore model | Model MindSpore |
| `det.training` | Model training | Latihan model |
| `det.framework` | Huawei MindSpore | Huawei MindSpore |
| `det.open` | Open calibration | Buka kalibrasi |
| `det.unknown` | The server did not say what is counting. | Pelayan tidak menyatakan apa yang sedang mengira. |

## cal

| Key | English | Bahasa Melayu |
|---|---|---|
| `cal.description` | Label what the sensors should see and check what is counting now. | Labelkan apa yang patut dikesan dan semak apa yang mengira sekarang. |
| `cal.label_title` | Label headcount | Label bilangan orang |
| `cal.room` | Room | Bilik |
| `cal.labelling_now` | labelling now | sedang dilabel |
| `cal.people_now` | People in the room now | Orang di dalam bilik sekarang |
| `cal.recent` | Recent labels | Label terkini |
| `cal.col_room` | Room | Bilik |
| `cal.col_people` | People | Orang |
| `cal.col_time` | Time | Masa |
| `cal.live_title` | Live detector | Pengesan semasa |
| `cal.col_counting` | Counting by | Dikira oleh |
| `cal.col_threshold` | Threshold or model | Ambang atau model |
| `cal.col_last` | Last reading | Bacaan terakhir |
| `cal.by_rule` | Calibrated rule | Peraturan terkalibrasi |
| `cal.by_model` | MindSpore model | Model MindSpore |
| `cal.by_counter` | People counter | Pembilang orang |
| `cal.last_at` | {x} dB at {time} | {x} dB pada {time} |
| `cal.dots_room` | Room shown | Bilik dipaparkan |
| `cal.dots_none_room` | No labelled reports for this room yet | Belum ada laporan berlabel untuk bilik ini |

## sum

| Key | English | Bahasa Melayu |
|---|---|---|
| `sum.title` | Today's summary | Ringkasan hari ini |
| `sum.description` | People, sensors and air conditioning waste since midnight. | Orang, sensor dan pembaziran penghawa dingin sejak tengah malam. |
| `sum.back` | Building summary | Ringkasan bangunan |
| `sum.people` | People today | Orang hari ini |
| `sum.by_room` | By room | Mengikut bilik |
| `sum.col_room` | Room | Bilik |
| `sum.col_peak` | Peak people | Orang paling ramai |
| `sum.col_hours` | Hours occupied | Jam berpenghuni |
| `sum.col_uptime` | Sensor uptime | Masa aktif sensor |
| `sum.col_waste` | A/C waste | Pembaziran penghawa dingin |
| `sum.no_rooms` | No room has reported today. | Tiada bilik menghantar data hari ini. |
| `sum.incidents` | Emergencies and drills today | Kecemasan dan latihan hari ini |
| `sum.incidents_none` | None today. | Tiada hari ini. |
| `sum.open_report` | Open report | Buka laporan |

## es

| Key | English | Bahasa Melayu |
|---|---|---|
| `es.title` | Energy settings | Tetapan tenaga |
| `es.tariff` | Electricity tariff | Tarif elektrik |
| `es.ac_kw` | Air conditioner power | Kuasa penghawa dingin |
| `es.ac_kw_room` | Power for one room | Kuasa untuk satu bilik |
| `es.ac_on_below` | Air conditioning counts as on below | Penghawa dingin dikira hidup di bawah |
| `es.waste_after` | Waste flagged after | Pembaziran ditanda selepas |
| `es.co2` | CO2 factor | Faktor CO2 |
| `es.unit_tariff` | RM per kWh | RM sekWj |
| `es.unit_kw` | kW | kW |
| `es.unit_c` | °C | °C |
| `es.unit_min` | minutes | minit |
| `es.unit_co2` | kg per kWh | kg sekWj |
| `es.val_tariff` | RM {x} per kWh | RM {x} sekWj |
| `es.val_kw` | {x} kW | {x} kW |
| `es.val_c` | {x} °C | {x} °C |
| `es.val_min` | {x} minutes | {x} minit |
| `es.val_min_one` | 1 minute | 1 minit |
| `es.val_co2` | {x} kg per kWh | {x} kg sekWj |
| `es.edit` | Edit | Sunting |
| `es.save` | Save | Simpan |
| `es.cancel` | Cancel | Batal |
| `es.rooms_own` | Rooms with their own air conditioner power | Bilik dengan kuasa penghawa dingin tersendiri |
| `es.rooms_none` | Every room uses the building value. | Semua bilik menggunakan nilai bangunan. |
| `es.add_room` | Add a room | Tambah bilik |
| `es.add_room_pick` | Room to add | Bilik untuk ditambah |
| `es.remove_room` | Remove {name} | Buang {name} |
| `es.room_kw_label` | Air conditioner power for {name} | Kuasa penghawa dingin untuk {name} |
| `es.not_set` | building value | nilai bangunan |
| `es.changed_by` | Last changed by {who} on {date} | Kali terakhir diubah oleh {who} pada {date} |
| `es.defaults` | Default values from the server configuration | Nilai lalai daripada konfigurasi pelayan |
| `es.last_known` | The database is offline: these are the last known values. | Pangkalan data di luar talian: ini nilai terakhir yang diketahui. |
| `es.cold_defaults` | The database is offline: default values are in use until it is back. | Pangkalan data di luar talian: nilai lalai digunakan sehingga ia pulih. |
| `es.confirm_title` | Save these changes? | Simpan perubahan ini? |
| `es.confirm_note` | Applies from now. Earlier figures keep the earlier values. | Berkuat kuasa mulai sekarang. Angka terdahulu mengekalkan nilai terdahulu. |
| `es.change` | {label}: {old} → {new} | {label}: {old} → {new} |
| `es.saved` | Saved. The new values apply from {time}. | Disimpan. Nilai baharu berkuat kuasa mulai {time}. |
| `es.nothing` | Nothing was changed. | Tiada perubahan. |
| `es.history` | Change history | Sejarah perubahan |
| `es.history_none` | No change has been saved yet. | Belum ada perubahan disimpan. |
| `es.col_when` | Applies from | Berkuat kuasa mulai |
| `es.col_who` | Changed by | Diubah oleh |
| `es.col_what` | What changed | Apa yang berubah |
| `es.rate_changed` | Rate changed on {date}. Figures before then use the earlier values. | Kadar diubah pada {date}. Angka sebelum itu menggunakan nilai terdahulu. |
| `es.err_range` | {label} must be between {min} and {max} {unit}. | {label} mesti antara {min} dan {max} {unit}. |
| `es.err_number` | {label} must be a number. | {label} mesti berupa nombor. |
| `es.err_room` | {room} is not a known room. | {room} bukan bilik yang dikenali. |
| `es.err_too_many` | At most {n} rooms can have their own power. | Selebih-lebihnya {n} bilik boleh mempunyai kuasa tersendiri. |
| `es.err_offline` | The database is offline, so the change cannot be saved. | Pangkalan data di luar talian, jadi perubahan tidak dapat disimpan. |
| `es.err_save` | The change could not be saved: {reason} | Perubahan tidak dapat disimpan: {reason} |
| `es.rule_line` | Waste: empty room, below {temp} °C, longer than {delay} min. RM = {kw} kW x hours x RM {rate} per kWh. CO2 = kWh x {factor} (estimate). | Pembaziran: bilik kosong, di bawah {temp} °C, lebih lama daripada {delay} min. RM = {kw} kW x jam x RM {rate} sekWj. CO2 = kWj x {factor} (anggaran). |
| `es.per_room` | Per room ({n}) | Setiap bilik ({n}) |
| `es.history_hint` | Every saved change, newest first. | Setiap perubahan yang disimpan, terbaru dahulu. |
| `es.history_link` | History | Sejarah |

## site

| Key | English | Bahasa Melayu |
|---|---|---|
| `site.err_shape` | The plan is not in the expected format. | Pelan tidak mengikut format yang dijangka. |
| `site.err_shape_of` | {name} is not drawn as a rectangle. | {name} tidak dilukis sebagai segi empat. |
| `site.err_too_large` | The plan is larger than {kb} KB. | Pelan melebihi {kb} KB. |
| `site.err_too_many` | A floor can have at most {n} rooms. | Satu tingkat boleh mempunyai paling banyak {n} bilik. |
| `site.err_outside` | {name} is outside the floor. | {name} berada di luar tingkat. |
| `site.err_small` | {name} must be at least {min} x {min}. | {name} mesti sekurang-kurangnya {min} x {min}. |
| `site.err_door` | The door of {name} must be on its north or south wall, within the room. | Pintu {name} mesti berada di dinding utara atau selatan, dalam bilik itu. |
| `site.err_overlap` | {a} and {b} overlap. | {a} dan {b} bertindih. |
| `site.err_no_exit` | The floor needs at least one exit or staircase. | Tingkat ini memerlukan sekurang-kurangnya satu pintu keluar atau tangga. |
| `site.err_exit_missing` | {name} needs a nearest exit that is on this floor. | {name} memerlukan pintu keluar terdekat yang berada di tingkat ini. |
| `site.err_id` | Room ID {id} must start with a lower-case letter or digit and use only a to z, 0 to 9, - and _ (up to 32). | ID bilik {id} mesti bermula dengan huruf kecil atau digit dan hanya menggunakan a hingga z, 0 hingga 9, - dan _ (sehingga 32). |
| `site.err_duplicate` | Room ID {id} is used more than once. | ID bilik {id} digunakan lebih daripada sekali. |
| `site.err_taken` | Room ID {id} is already used on {floor}. | ID bilik {id} sudah digunakan di {floor}. |
| `site.err_name` | The name of {name} must be 1 to {max} characters. | Nama {name} mesti antara 1 hingga {max} aksara. |
| `site.err_area` | The floor area of {name} must be between 1 and 100000 m². | Keluasan lantai {name} mesti antara 1 hingga 100000 m². |
| `site.err_link` | The sender and receiver of {name} must be inside the room and at least {min} apart. | Penghantar dan penerima {name} mesti berada dalam bilik dan sekurang-kurangnya {min} jaraknya. |
| `site.err_live` | {name} ({id}) has a sensor reporting, so it cannot be removed. | {name} ({id}) mempunyai sensor yang sedang melapor, jadi ia tidak boleh dibuang. |
| `site.err_background` | The background image is missing or its opacity is not between 0 and 1. | Imej latar tiada atau kelegapannya bukan antara 0 dan 1. |
| `site.err_image` | The file is not a PNG or JPG image this page can use. | Fail ini bukan imej PNG atau JPG yang boleh digunakan. |
| `site.err_image_size` | The image must be at most 2 MB and between 64 and 4096 pixels on each side. | Imej mesti tidak melebihi 2 MB dan antara 64 hingga 4096 piksel pada setiap sisi. |
| `site.switch` | Change building or floor | Tukar bangunan atau tingkat |
| `site.search` | Search building, code or floor | Cari bangunan, kod atau tingkat |
| `site.current` | current | semasa |
| `site.example` | Example | Contoh |
| `site.example_note` | Example data: this building has no sensors. | Data contoh: bangunan ini tiada sensor. |
| `site.none_found` | No building or floor matches. | Tiada bangunan atau tingkat yang sepadan. |
| `site.rooms_count` | {n} rooms | {n} bilik |
| `site.rooms_one` | 1 room | 1 bilik |
| `site.err_title` | A name must be 1 to {max} characters. | Nama mesti antara 1 hingga {max} aksara. |
| `site.err_code` | A code may use letters, digits and - only, up to 16 characters. | Kod hanya boleh menggunakan huruf, digit dan -, sehingga 16 aksara. |
| `site.err_level` | The level must be a whole number from -10 to 300. | Aras mesti nombor bulat dari -10 hingga 300. |
| `site.err_example` | The example building cannot be changed. | Bangunan contoh tidak boleh diubah. |
| `site.example_name` | Example Tower (example data) | Menara Contoh (data contoh) |
| `site.level_n` | Level {n} | Aras {n} |
| `site.example_room` | Room {level}.{n} | Bilik {level}.{n} |
| `site.buildings` | Buildings | Bangunan |
| `site.floors_of` | Floors of {name} | Tingkat {name} |
| `site.results` | Matching floors | Tingkat yang sepadan |

## ed

| Key | English | Bahasa Melayu |
|---|---|---|
| `ed.conflict` | Someone else saved this plan. Reload to see their version. | Orang lain telah menyimpan pelan ini. Muat semula untuk melihat versi mereka. |
| `ed.open` | Edit plan | Sunting pelan |
| `ed.what` | Editing a floor plan | Menyunting pelan lantai |
| `ed.title` | Edit plan: {building}, {floor} | Sunting pelan: {building}, {floor} |
| `ed.version` | Version {n} is in use. | Versi {n} sedang digunakan. |
| `ed.back` | Back to the floor plan | Kembali ke pelan lantai |
| `ed.off` | The floor plan editor is switched off on this server (PLAN_EDITOR=off). | Penyunting pelan lantai dimatikan pada pelayan ini (PLAN_EDITOR=off). |
| `ed.tool_select` | Select | Pilih |
| `ed.tool_room` | Room | Bilik |
| `ed.tool_exit` | Stairs or exit | Tangga atau pintu keluar |
| `ed.tool_other` | Other space | Ruang lain |
| `ed.template` | Start from | Mula daripada |
| `ed.template_use` | Use | Guna |
| `ed.tpl_corridor` | Corridor with rooms on both sides | Koridor dengan bilik di kedua-dua belah |
| `ed.tpl_hall` | Open hall | Dewan terbuka |
| `ed.tpl_blank` | Blank grid | Grid kosong |
| `ed.replace` | Replace the drawing with this template? Unsaved changes are lost. | Gantikan lukisan dengan templat ini? Perubahan yang belum disimpan akan hilang. |
| `ed.opacity` | Image opacity: {n}% | Kelegapan imej: {n}% |
| `ed.bg_remove` | Remove the image | Buang imej |
| `ed.canvas` | Floor plan drawing | Lukisan pelan lantai |
| `ed.keys` | Drag to draw or move a shape, or drag a handle to make it larger or smaller. Arrow keys move it by 10 (Shift: 1); Delete removes it. | Seret untuk melukis atau mengalihkan bentuk, atau seret pemegang untuk membesarkan atau mengecilkannya. Kekunci anak panah mengalihkannya sebanyak 10 (Shift: 1); kekunci padam membuangnya. |
| `ed.place_send` | Click inside the room where the sender stands. | Klik di dalam bilik tempat penghantar diletakkan. |
| `ed.place_recv` | Now click where the receiver stands. | Sekarang klik tempat penerima diletakkan. |
| `ed.panel` | Shapes and details | Bentuk dan butiran |
| `ed.shapes` | Shapes on this floor | Bentuk di tingkat ini |
| `ed.add_room` | Add a room | Tambah bilik |
| `ed.add_exit` | Add stairs or an exit | Tambah tangga atau pintu keluar |
| `ed.add_other` | Add another space | Tambah ruang lain |
| `ed.no_shapes` | Nothing drawn yet. | Belum ada yang dilukis. |
| `ed.select_hint` | Select a shape on the drawing or in the list to see its details. | Pilih bentuk pada lukisan atau dalam senarai untuk melihat butirannya. |
| `ed.kind_room` | room | bilik |
| `ed.kind_exit` | exit | pintu keluar |
| `ed.kind_other` | space | ruang |
| `ed.selected` | Selected: {name} | Dipilih: {name} |
| `ed.room_id` | Room ID (what the sensors report) | ID bilik (yang dilaporkan oleh sensor) |
| `ed.id_taken` | Room ID {id} is already used on another floor. | ID bilik {id} sudah digunakan di tingkat lain. |
| `ed.name` | Name | Nama |
| `ed.nearest_exit` | Nearest exit | Pintu keluar terdekat |
| `ed.choose_exit` | Choose an exit | Pilih pintu keluar |
| `ed.door_side` | Door | Pintu |
| `ed.door_none` | No door drawn | Tiada pintu dilukis |
| `ed.door_n` | North wall | Dinding utara |
| `ed.door_s` | South wall | Dinding selatan |
| `ed.door_x` | Door position | Kedudukan pintu |
| `ed.width` | Width | Lebar |
| `ed.height` | Height | Tinggi |
| `ed.size` | Floor area | Keluasan lantai |
| `ed.area` | Area in m² | Keluasan dalam m² |
| `ed.area_or` | or width x length in metres: | atau lebar x panjang dalam meter: |
| `ed.width_m` | Width (m) | Lebar (m) |
| `ed.length_m` | Length (m) | Panjang (m) |
| `ed.guideline` | Guideline only: suggested sensor pairs: {n} (one pair covers about 3 to 5 m between boards, from our test) | Panduan sahaja: cadangan pasangan sensor: {n} (satu pasangan meliputi kira-kira 3 hingga 5 m antara papan, daripada ujian kami) |
| `ed.pair` | Sensor pair | Pasangan sensor |
| `ed.pair_none` | No sensor pair drawn. | Tiada pasangan sensor dilukis. |
| `ed.pair_placed` | Sender and receiver drawn. | Penghantar dan penerima telah dilukis. |
| `ed.pair_placing` | Click inside the room: first the sender, then the receiver. | Klik di dalam bilik: penghantar dahulu, kemudian penerima. |
| `ed.pair_place` | Place | Letak |
| `ed.pair_clear` | Clear | Kosongkan |
| `ed.ac_power` | Air conditioner power: {kw} kW. | Kuasa penghawa dingin: {kw} kW. |
| `ed.ac_link` | Change it in Energy settings | Ubah dalam Tetapan tenaga |
| `ed.remove` | Remove this shape | Buang bentuk ini |
| `ed.kind` | Kind | Jenis |
| `ed.kind_stair` | Staircase | Tangga |
| `ed.kind_door` | Exit door | Pintu keluar |
| `ed.new_room` | New room | Bilik baharu |
| `ed.new_exit` | New stair | Tangga baharu |
| `ed.new_other` | Space | Ruang |
| `ed.checks` | Checks | Semakan |
| `ed.checks_n` | Checks: {n} problems | Semakan: {n} masalah |
| `ed.checks_ok` | No problems found | Tiada masalah ditemui |
| `ed.preview` | Preview | Pratonton |
| `ed.edit` | Back to drawing | Kembali melukis |
| `ed.preview_title` | Preview: how the live plan will look | Pratonton: rupa pelan langsung |
| `ed.save_open` | Save... | Simpan... |
| `ed.save` | Save | Simpan |
| `ed.save_title` | Save this plan as a new version? | Simpan pelan ini sebagai versi baharu? |
| `ed.note` | Note | Catatan |
| `ed.saved` | Saved as version {n}. | Disimpan sebagai versi {n}. |
| `ed.conflict_title` | The plan has changed | Pelan telah berubah |
| `ed.reload` | Reload | Muat semula |
| `ed.leave` | Leave without saving? Your changes to the plan are lost. | Keluar tanpa menyimpan? Perubahan pada pelan akan hilang. |
| `ed.versions` | Versions | Versi |
| `ed.col_version` | Version | Versi |
| `ed.builtin` | Built-in plan | Pelan asal |
| `ed.restore` | Restore this version | Pulihkan versi ini |
| `ed.restore_title` | Restore version {n}? | Pulihkan versi {n}? |
| `ed.restore_note` | It becomes the plan in use, saved as a new version. Every version is kept. | Ia menjadi pelan yang digunakan, disimpan sebagai versi baharu. Setiap versi disimpan. |
| `ed.restored` | Version {from} restored as version {n}. | Versi {from} dipulihkan sebagai versi {n}. |
| `ed.restored_from` | Restored from version {n} | Dipulihkan daripada versi {n} |
| `ed.sum_added` | {n} rooms added | {n} bilik ditambah |
| `ed.sum_added_one` | 1 room added | 1 bilik ditambah |
| `ed.sum_removed` | {n} rooms removed | {n} bilik dibuang |
| `ed.sum_removed_one` | 1 room removed | 1 bilik dibuang |
| `ed.sum_moved` | {n} moved or reshaped | {n} dialih atau diubah bentuk |
| `ed.sum_moved_one` | 1 moved or reshaped | 1 dialih atau diubah bentuk |
| `ed.sum_renamed` | {n} renamed | {n} dinamakan semula |
| `ed.sum_renamed_one` | 1 renamed | 1 dinamakan semula |
| `ed.sum_other` | stairs, exits or other spaces changed | tangga, pintu keluar atau ruang lain berubah |
| `ed.sum_none` | No change to the rooms. | Tiada perubahan pada bilik. |
| `ed.upload_button` | Choose an image | Pilih imej |
| `ed.version_builtin` | The built-in plan is in use. | Pelan asal sedang digunakan. |
| `ed.tpl_hall_name` | Hall | Dewan |
| `ed.tpl_exit_name` | Exit {x} | Pintu keluar {x} |

## scope

| Key | English | Bahasa Melayu |
|---|---|---|
| `scope.prefix` | {scope}: {answer} | {scope}: {answer} |
| `scope.whole` | Whole building | Seluruh bangunan |
| `scope.this_floor` | This floor: {floor} | Tingkat ini: {floor} |
| `scope.label` | Answers for | Jawapan untuk |
| `scope.locked_emergency` | Emergency mode is on: answers cover the whole building. | Mod kecemasan aktif: jawapan meliputi seluruh bangunan. |
| `scope.locked_drill` | A drill is on: answers cover the whole building. | Latihan sedang berjalan: jawapan meliputi seluruh bangunan. |
| `scope.no_such_floor` | There is no level {n} in {building}. | Tiada aras {n} di {building}. |
| `scope.example` | Example data: this floor has no sensors. | Data contoh: tingkat ini tiada sensor. |
| `scope.no_sensors` | No sensors on this floor. | Tiada sensor di tingkat ini. |
| `scope.floor_count` | {floor}: {count} {people} | {floor}: {count} {people} |
| `scope.floor_unknown` | {floor}: unknown | {floor}: tidak diketahui |
| `scope.breakdown` | By floor: {floors}. | Mengikut tingkat: {floors}. |
| `scope.floor_at_least` | {floor}: at least {count} {people} | {floor}: sekurang-kurangnya {count} {people} |

## site

| Key | English | Bahasa Melayu |
|---|---|---|
| `site.err_capacity` | The capacity of {name} must be a whole number from 1 to {max}. | Kapasiti {name} mesti nombor bulat dari 1 hingga {max}. |

## ed

| Key | English | Bahasa Melayu |
|---|---|---|
| `ed.capacity` | Capacity (people), optional | Kapasiti (orang), pilihan |
| `ed.capacity_hint` | Shown as a dashed line on the room's people chart. Not an alert. | Dipaparkan sebagai garis putus-putus pada carta penghuni bilik. Bukan amaran. |

## Alerts panel

| Key | English | Bahasa Melayu |
|---|---|---|
| `alerts.audit_capacity` | Capacity of {room}: {old} → {new} | Kapasiti {room}: {old} → {new} |
| `alerts.audit_capacity_none` | not set | tidak ditetapkan |

## ppl

| Key | English | Bahasa Melayu |
|---|---|---|
| `ppl.now` | Now {count} | Kini {count} |
| `ppl.since` | since {time} | sejak {time} |
| `ppl.details` | Room details | Butiran bilik |
| `ppl.peak` | Peak | Puncak |
| `ppl.of_capacity` | {n} of {cap} | {n} daripada {cap} |
| `ppl.occupied` | Occupied | Berpenghuni |
| `ppl.minutes` | {n} min | {n} min |
| `ppl.hours_minutes` | {h} h {m} min | {h} j {m} min |
| `ppl.span` | {from} to {to} | {from} hingga {to} |
| `ppl.capacity_tip` | Capacity {n} | Kapasiti {n} |
| `ppl.none` | No reports from this room in {range}. | Tiada laporan dari bilik ini dalam {range}. |
| `ppl.no_room` | No room has reported yet. | Belum ada bilik yang menghantar data. |
| `ppl.label` | People in {name} over {range}: at most {max} at once. | Orang di {name} sepanjang {range}: paling ramai {max} serentak. |
| `ppl.label_capacity` | Capacity {cap}. | Kapasiti {cap}. |

## sig

| Key | English | Bahasa Melayu |
|---|---|---|
| `sig.range_long_1h` | the last hour | 1 jam lalu |

## chart

| Key | English | Bahasa Melayu |
|---|---|---|
| `chart.data_from` | Data from {date} | Data dari {date} |

## Room details

| Key | English | Bahasa Melayu |
|---|---|---|
| `detail.nearest_exit_is` | Nearest exit: {exit} | Laluan keluar terdekat: {exit} |
| `detail.capacity` | Capacity | Kapasiti |
| `detail.room_id_label` | Room ID | ID bilik |

## energy

| Key | English | Bahasa Melayu |
|---|---|---|
| `energy.col_room` | Room | Bilik |
| `energy.col_rm` | Wasted | Dibazirkan |
| `energy.col_kwh` | kWh | kWj |
| `energy.col_hours` | Hours | Jam |
| `energy.filter_room` | Show {room} in the chart | Papar {room} dalam carta |
| `energy.filter_remove` | Show the whole building | Papar seluruh bangunan |

## ed

| Key | English | Bahasa Melayu |
|---|---|---|
| `ed.group_draw` | Draw | Lukis |
| `ed.group_image` | Background image | Imej latar |
| `ed.upload_help` | PNG or JPG, up to 2 MB | PNG atau JPG, sehingga 2 MB |
| `ed.sum_details` | details of {n} rooms changed | butiran {n} bilik diubah |
| `ed.sum_details_one` | details of 1 room changed | butiran 1 bilik diubah |
