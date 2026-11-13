"""Floor plan background uploads (server/upload.py): only real PNG and JPEG files, decided by their bytes, within
2 MB and 64 to 4096 pixels a side, stored without any metadata and served so a browser can never run them."""
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from server import main, plan, site, upload
from tests.util import LOCAL_URL

TOKEN = "upload-token-0123456789a"
H = {"X-Admin-Token": TOKEN}


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def png(width=64, height=64, extra=(), tail=b""):
    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))  # filter byte + grey pixels
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (upload.PNG_SIGNATURE + chunk(b"IHDR", ihdr) + b"".join(extra) + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b"") + tail)


def seg(marker, body):
    return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body


def jpeg(width=64, height=64, tail=b""):
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + seg(0xE1, b"Exif\x00\x00GPS 3.1390 N 101.6869 E camera-serial-123")
            + seg(0xFE, b"made with some editor")
            + seg(0xDB, b"\x00" + bytes(range(64)))
            + seg(0xC0, b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00")
            + seg(0xC4, b"\x00" + b"\x00" * 16 + b"\x00")
            + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\x56\x78" + b"\xff\xd9" + tail)


@pytest.fixture
def folder(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_DIR", str(tmp_path / "site"))
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    plan.refresh()
    yield tmp_path / "site"
    monkeypatch.undo()
    plan.refresh()


def api():
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


def post(data, headers=None, floor="f1", lang="en"):
    return api().post(f"/api/floors/{floor}/image?lang={lang}", content=data, headers={**H, "Content-Type": "image/png", **(headers or {})})


# --- the checks themselves ---

def test_a_png_keeps_only_its_image_chunks():
    text = chunk(b"tEXt", b"Software\x00Some tool v1"), chunk(b"eXIf", b"MM\x00*GPS"), chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x/>")
    cleaned, ext, w, h = upload.clean(png(100, 80, extra=text))
    assert (ext, w, h) == ("png", 100, 80)
    assert b"tEXt" not in cleaned and b"eXIf" not in cleaned and b"iTXt" not in cleaned and b"Some tool" not in cleaned
    assert cleaned == png(100, 80)  # exactly the image, rewritten


def test_a_jpeg_loses_exif_and_comments():
    cleaned, ext, w, h = upload.clean(jpeg(640, 480))
    assert (ext, w, h) == ("jpg", 640, 480)
    assert b"Exif" not in cleaned and b"GPS" not in cleaned and b"some editor" not in cleaned
    assert cleaned.startswith(b"\xff\xd8\xff\xe0") and cleaned.endswith(b"\xff\xd9")


@pytest.mark.parametrize("data,key", [
    (b"<html><script>alert(1)</script></html>", "site.err_image"),                       # a renamed HTML file
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "site.err_image"),    # SVG
    (b"GIF89a" + b"\x00" * 100, "site.err_image"),                                     # GIF
    (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 100, "site.err_image"),               # WebP
    (png(tail=b"<html>appended</html>"), "site.err_image"),                            # PNG with trailing data
    (png()[:-20], "site.err_image"),                                                   # truncated
    (png()[:40] + b"\x00" + png()[41:], "site.err_image"),                             # a byte changed: CRC fails
    (upload.PNG_SIGNATURE + chunk(b"IEND", b""), "site.err_image"),                    # no IHDR
    (jpeg(tail=b"PK\x03\x04zip"), "site.err_image"),                                   # JPEG with something after EOI
    (b"\xff\xd8\xff" + b"\x00" * 50 + b"\xff\xd9", "site.err_image"),                 # no segments
    (png(5000, 64), "site.err_image_size"),                                            # too wide
    (png(64, 63), "site.err_image_size"),                                              # too small
    (jpeg(4097, 100), "site.err_image_size"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * (upload.MAX_BYTES + 1), "site.err_image_size"),  # over 2 MB
], ids=["html", "svg", "gif", "webp", "png-trailing", "png-truncated", "png-crc", "png-no-ihdr", "jpeg-trailing",
        "jpeg-no-segments", "png-5000px", "png-63px", "jpeg-4097px", "over-2mb"])
def test_everything_else_is_refused(data, key):
    with pytest.raises(upload.Refused) as e:
        upload.clean(data)
    assert e.value.key == key


# --- the endpoint ---

def test_an_upload_is_stored_by_its_hash_and_served_as_an_image_only(folder):
    out = post(png(200, 100, extra=[chunk(b"tEXt", b"Author\x00someone")]), headers={"Content-Type": "text/html"})
    assert out.status_code == 200
    body = out.json()
    assert body["width"] == 200 and body["height"] == 100 and site.IMAGE_NAME.fullmatch(body["image"]) and body["image"].endswith(".png")
    stored = (folder / "images" / body["image"]).read_bytes()
    assert stored == png(200, 100) and b"someone" not in stored
    served = api().get(f"/api/site/images/{body['image']}")
    assert served.content == stored and served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff" and served.headers["content-security-policy"] == "default-src 'none'"
    assert post(png(200, 100)).json()["image"] == body["image"]  # the same picture is stored once
    assert len(list((folder / "images").iterdir())) == 1


def test_refusals_come_back_in_the_page_language(folder):
    out = post(b"<html></html>", lang="ms")
    assert out.status_code == 422 and out.json()["errors"][0]["message"] == "Fail ini bukan imej PNG atau JPG yang boleh digunakan."
    big = post(png(64, 5000))
    assert big.status_code == 422 and big.json()["errors"][0]["key"] == "site.err_image_size"
    assert not (folder / "images").exists()


def test_a_body_over_2_mb_is_refused_before_it_is_read(folder):
    out = post(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024))
    assert out.status_code == 413


def test_only_admins_upload_and_never_to_the_example_building(folder):
    assert api().post("/api/floors/f1/image", content=png()).status_code == 401
    assert post(png(), floor="ex-2").status_code == 409
    assert post(png(), floor="f404").status_code == 404
