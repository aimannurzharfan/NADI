# NADI IoT network on Huawei router + switch

Network-security part of NADI: the ESP32 sensors get their own VLAN, and Huawei VRP ACLs let them reach **only the MQTT port**. A compromised or cloned sensor can't scan staff PCs, hit the database, or reach the internet.

Files:

| File | Device | What |
|---|---|---|
| `router-ar.cfg` | Huawei AR router | DHCP pools, VLAN sub-interfaces, ACL 3030 (sensor allow-list), DNS proxy, NAT for huawei mode, SSH only |
| `switch-s.cfg` | Huawei S switch | VLANs 10/30, trunk to router and AP, access ports, port isolation, DHCP snooping, fallback ACL |

Nothing here has been pasted into a real device yet. Lines marked **verify on device** depend on the exact model and VRP version.

## Topology

```
                 campus / internet (huawei mode only, via NAT)
                         |
                   GE0/0/0 (WAN)
                 [ Huawei AR router ]  ACL 3030 inbound on GE0/0/1.30
                   GE0/0/1 trunk (VLAN 10, 30)
                         |
                 [ Huawei S switch ]
          GE0/0/2 |        GE0/0/3 |        GE0/0/4-8
     trunk VLAN 30|   access VLAN 10|   access VLAN 30 (isolated)
                  |                 |
      Wi-Fi AP (MikroTik/Cisco)   NADI server 192.168.10.10
      SSID "NADI-IoT" -> VLAN 30  (FastAPI :8000, Mosquitto :1883)
                  |
       ESP32 receiver + aircon node (192.168.30.x via DHCP)
```

UTM's Huawei kit is router + switch only, so the Wi-Fi comes from the borrowed MikroTik or Cisco AP: create an SSID `NADI-IoT` (WPA2-PSK) and tag it VLAN 30 on the port to switch GE0/0/2.

The CSI **sender** board talks to the receiver with raw Wi-Fi frames, not IP, so the ACL doesn't affect CSI capture. Only the receiver and the aircon node need IP.

## What a sensor is allowed to do (ACL 3030)

| Rule | Allows | Why |
|---|---|---|
| 5 | UDP 68 -> 67 | DHCP lease |
| 10 | UDP 53 to the gateway only | DNS for the IoTDA host name (huawei mode) |
| 15 | TCP 1883 to 192.168.10.10 only | MQTT to Mosquitto (local mode) |
| 20 | TCP 8883 | MQTTS to Huawei IoTDA (huawei mode) |
| 25 | UDP 123 | NTP so TLS certificate checks work (huawei mode) |
| 30 | ICMP to the gateway only | "is it online" checks |
| 100 | deny everything else | |

For a local-only demo you can delete rules 10, 20, 25 and the NAT block, so the sensors have no route to the internet at all.

## Applying

1. Console cable or SSH to each device, `system-view`.
2. Back up first: `display current-configuration` and save the output.
3. Change the address plan and port numbers at the top of each file if the lab is cabled differently.
4. Paste one numbered block at a time and read the output. Stop at any `Error:` line.
5. `save` on each device.

## Proving it works (for the judges)

1. Phone joins `NADI-IoT`: it gets a `192.168.30.x` address (`display ip pool name nadi-iot used`).
2. From that phone, `http://192.168.10.10:8000` (dashboard) **fails** because port 8000 isn't allowed. An MQTT app to `192.168.10.10:1883` **works**.
3. `display acl 3030`: rule 15 hit counter goes up as the receiver publishes; rule 100 counts the blocked attempts.

## Rollback

`undo traffic-filter inbound acl 3030` on `GE0/0/1.30` removes the filter without touching the rest. Full rollback: restore the backup from step 2.
