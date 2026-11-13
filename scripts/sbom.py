"""Write the software bill of materials (CycloneDX JSON) to docs/sbom/: every third-party package NADI ships.

  docs/sbom/python.cdx.json   the server's Python packages: requirements.txt and everything it pulls in, as pip
                              resolves it (pip install --dry-run, nothing is installed; needs PyPI access)
  docs/sbom/web.cdx.json      the web console's npm packages bundled into web/dist (no build-only tools)

Run after changing requirements.txt or web/package.json:
    python scripts/sbom.py
Needs cyclonedx-bom (requirements-dev.txt) and npm 10.8 or later.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "sbom"


def tidy(path):
    """Drop the per-run serial number and timestamp, so the file only changes when the packages change."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("serialNumber", None)
    data.get("metadata", {}).pop("timestamp", None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(data.get("components", []))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    py = OUT / "python.cdx.json"
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
                        "--report", str(report), "-r", str(ROOT / "requirements.txt")], check=True)
        resolved = sorted(f"{i['metadata']['name']}=={i['metadata']['version']}"
                          for i in json.loads(report.read_text(encoding="utf-8"))["install"])
        pins = Path(tmp) / "resolved.txt"
        pins.write_text("\n".join(resolved) + "\n", encoding="utf-8")
        subprocess.run([sys.executable, "-m", "cyclonedx_py", "requirements", str(pins),
                        "--output-format", "JSON", "--output-file", str(py)], check=True)
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    web = OUT / "web.cdx.json"
    res = subprocess.run([npm, "sbom", "--sbom-format", "cyclonedx", "--omit", "dev"], cwd=ROOT / "web",
                         capture_output=True, text=True, encoding="utf-8", check=True)
    web.write_text(res.stdout, encoding="utf-8")
    print(f"docs/sbom/python.cdx.json: {tidy(py)} packages; docs/sbom/web.cdx.json: {tidy(web)} packages")


if __name__ == "__main__":
    main()
