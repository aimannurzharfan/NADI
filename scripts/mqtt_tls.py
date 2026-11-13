"""Make a private CA and a broker certificate for MQTT over TLS on the local Mosquitto (port 8883).

Writes (all git-ignored):
  deploy/mqtt_ca/ca.key                         the CA's private key (it can sign more certificates). Kept outside
                                                deploy/mosquitto, which is mounted into the broker container: the
                                                broker never needs it, so a compromised broker cannot leak it
  deploy/mosquitto/certs/ca.crt                 the CA certificate (public)
  deploy/mosquitto/certs/server.crt, server.key the broker certificate, valid for 127.0.0.1, localhost and the
                                                laptop IP (MQTT_LAN_IP in .env, or --ip)
  deploy/mosquitto/conf.d/tls.conf              the 8883 listener (same logins and topic limits as 1883)
  firmware/csi_recv/main/mqtt_ca.pem            the CA for the CSI receiver (menuconfig: MQTT over TLS)
  firmware/climate_node/mqtt_ca.h               the CA for the climate node (secrets.h: MQTT_TLS 1)

Run again when the laptop IP changes (the boards keep working: the CA stays the same unless you pass --new-ca).

    python scripts/mqtt_tls.py [--ip 192.168.1.23] [--new-ca]
    docker compose up -d --force-recreate mosquitto
"""
import argparse
import datetime
import ipaddress
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parent.parent
CERTS = ROOT / "deploy" / "mosquitto" / "certs"
CA_KEY = ROOT / "deploy" / "mqtt_ca" / "ca.key"
OLD_CA_KEY = CERTS / "ca.key"  # where earlier versions of this script kept it
CONF = ROOT / "deploy" / "mosquitto" / "conf.d" / "tls.conf"
RECV_CA = ROOT / "firmware" / "csi_recv" / "main" / "mqtt_ca.pem"
CLIMATE_CA = ROOT / "firmware" / "climate_node" / "mqtt_ca.h"

LISTENER = """# Written by scripts/mqtt_tls.py. MQTT over TLS for the boards; logins and topic limits as on 1883.
listener 8883
max_connections 50
cafile /mosquitto/config/certs/ca.crt
certfile /mosquitto/config/certs/server.crt
keyfile /mosquitto/config/certs/server.key
tls_version tlsv1.2
"""


def lan_ip():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("MQTT_LAN_IP="):
                return line.split("=", 1)[1].strip() or None
    return None


def pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def write_private(path, data):
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def make_ca():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NADI local MQTT CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    return key, cert


def make_server(ca_key, ca_cert, ips):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    sans = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ips[-1])]))
            .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return key, cert


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ip", help="the laptop's IP address on the boards' Wi-Fi (default MQTT_LAN_IP from .env)")
    ap.add_argument("--new-ca", action="store_true", help="make a new CA too (every board then needs the new CA)")
    args = ap.parse_args()
    ips = ["127.0.0.1"]
    extra = args.ip or lan_ip()
    if extra:
        try:
            ipaddress.ip_address(extra)
        except ValueError:
            sys.exit(f"Not an IP address: {extra}")
        if extra not in ips:
            ips.append(extra)
    else:
        print("No laptop IP (MQTT_LAN_IP in .env or --ip): the certificate is valid for 127.0.0.1 only.")

    CERTS.mkdir(parents=True, exist_ok=True)
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CA_KEY.parent.mkdir(parents=True, exist_ok=True)
    ca_crt, ca_key_path = CERTS / "ca.crt", CA_KEY
    if OLD_CA_KEY.exists():  # move the key out of the folder the broker container can read
        if not CA_KEY.exists():
            write_private(CA_KEY, OLD_CA_KEY.read_bytes())
            print("Moved the CA key out of deploy/mosquitto/certs to deploy/mqtt_ca/.")
        OLD_CA_KEY.unlink()
    if ca_crt.exists() and ca_key_path.exists() and not args.new_ca:
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_crt.read_bytes())
        print("Using the existing CA (pass --new-ca for a new one).")
    else:
        ca_key, ca_cert = make_ca()
        write_private(ca_key_path, pem_key(ca_key))
        ca_crt.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
        print("Made a new CA.")
    key, cert = make_server(ca_key, ca_cert, ips)
    write_private(CERTS / "server.key", pem_key(key))
    (CERTS / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    CONF.write_text(LISTENER, encoding="utf-8", newline="\n")

    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode()
    RECV_CA.write_text(ca_pem, encoding="utf-8", newline="\n")
    body = " \\\n".join(f'  "{line}\\n"' for line in ca_pem.strip().splitlines())
    CLIMATE_CA.write_text("// Written by scripts/mqtt_tls.py: the local broker's CA (public, not a secret).\n"
                          f"#define MQTT_CA_PEM \\\n{body}\n", encoding="utf-8", newline="\n")
    print(f"Broker certificate for {', '.join(ips)} and localhost, valid 825 days.")
    print("Wrote deploy/mosquitto/certs/, deploy/mqtt_ca/ca.key, deploy/mosquitto/conf.d/tls.conf, "
          "firmware/csi_recv/main/mqtt_ca.pem and firmware/climate_node/mqtt_ca.h (all git-ignored).")
    print("Next: docker compose up -d --force-recreate mosquitto, then set the boards to port 8883 with TLS on.")


if __name__ == "__main__":
    main()
