"""The "Try it" demo container: its start script and the compose service that runs it."""
import re
from pathlib import Path

from scripts import docker_demo

ROOT = Path(__file__).resolve().parent.parent


def test_env_is_copied_from_the_example_only_when_missing(tmp_path):
    (tmp_path / ".env.example").write_text("NADI_MODE=local\n", encoding="utf-8")
    assert docker_demo.ensure_env(tmp_path) is True
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "NADI_MODE=local\n"
    (tmp_path / ".env").write_text("NADI_MODE=local\nADMIN_TOKEN=kept\n", encoding="utf-8")
    assert docker_demo.ensure_env(tmp_path) is False
    assert "ADMIN_TOKEN=kept" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_server_listens_on_loopback_only_and_trusts_no_proxy_headers():
    cmd = docker_demo.server_command()
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert "--no-proxy-headers" in cmd
    assert cmd[cmd.index("--port") + 1] == str(docker_demo.SERVER_PORT) != str(docker_demo.PUBLIC_PORT)
    relay = docker_demo.relay_command()
    assert relay[1].startswith(f"TCP-LISTEN:{docker_demo.PUBLIC_PORT},") and relay[2] == f"TCP:127.0.0.1:{docker_demo.SERVER_PORT}"


def demo_service():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = re.search(r"^  demo:\n(.*?)(?=^\S)", text, flags=re.M | re.S)
    assert block, "docker-compose.yml has no demo service"
    return block.group(1)


def test_demo_service_starts_only_with_its_profile_and_is_published_on_this_computer_only():
    demo = demo_service()
    assert 'profiles: ["demo"]' in demo
    ports = re.findall(r'ports: \[(.*?)\]', demo)
    assert ports == [f'"127.0.0.1:{docker_demo.PUBLIC_PORT}:{docker_demo.PUBLIC_PORT}"']
    assert 'DEMO_SCENARIO: "on"' in demo and "NADI_MODE: local" in demo


def test_the_docker_build_is_sent_the_package_list_and_nothing_else():
    lines = [l.strip() for l in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    assert lines == ["*", "!requirements.txt"]
