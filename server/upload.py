"""Floor plan background images: PNG or JPEG only, decided by the bytes (never by the file name or the type the
browser claims), checked by walking the file's own structure, and written out again without any metadata.

PNG: the 8-byte signature, then chunks (length, type, data, CRC) with every CRC checked, IHDR first, IEND last and
nothing after it. Only IHDR, PLTE, tRNS, IDAT and IEND are kept, so text, EXIF, colour profiles and anything a tool
stamped into the file are dropped.
JPEG: SOI, then segments up to the start of the scan (SOS); the size comes from the SOF segment; APP1 to APP15
(EXIF, XMP, ICC, vendor data) and COM are dropped; the file must end with EOI. Everything from the first SOS to EOI
is kept as it is: that is where the camera and editing tools do not write metadata in an ordinary JPEG, but a
progressive JPEG may carry segments between its scans, and those are not looked at.

Width and height must each be 64 to 4096 pixels, and the file at most 2 MB. No image library: nothing here decodes
pixels, so a crafted image cannot reach a decoder on the server.
"""
import struct
import zlib

MAX_BYTES = 2 * 1024 * 1024
MIN_SIDE, MAX_SIDE = 64, 4096
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_KEEP = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class Refused(Exception):
    """key: the strings key that says why (site.err_image or site.err_image_size)."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


def _size_ok(width, height):
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise Refused("site.err_image_size")


def clean_png(data):
    pos, out, width, height, first, ended, has_data = 8, [PNG_SIGNATURE], 0, 0, True, False, False
    while pos < len(data):
        if ended or pos + 12 > len(data):
            raise Refused("site.err_image")  # bytes after IEND, or a cut-off chunk
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if length > len(data) or end > len(data) or not kind.isalpha():
            raise Refused("site.err_image")
        body = data[pos + 8:pos + 8 + length]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != struct.unpack(">I", data[end - 4:end])[0]:
            raise Refused("site.err_image")
        if first:
            if kind != b"IHDR" or length != 13:
                raise Refused("site.err_image")
            width, height = struct.unpack(">II", body[:8])
            first = False
        if kind == b"IDAT":
            has_data = True
        if kind == b"IEND":
            ended = True
        if kind in PNG_KEEP:
            out.append(data[pos:end])
        pos = end
    if first or not ended or not has_data:
        raise Refused("site.err_image")
    _size_ok(width, height)
    return b"".join(out), width, height


def clean_jpeg(data):
    if data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise Refused("site.err_image")  # no SOI, or not ending with EOI (something appended)
    pos, out, size = 2, [b"\xff\xd8"], None
    while True:
        if pos + 4 > len(data) or data[pos] != 0xFF:
            raise Refused("site.err_image")
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            raise Refused("site.err_image")  # no image data before these
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        end = pos + 2 + length
        if length < 2 or end > len(data):
            raise Refused("site.err_image")
        if marker in SOF:
            if length < 8:
                raise Refused("site.err_image")
            height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
            size = (width, height)
        if marker == 0xDA:  # start of scan: the compressed image follows, up to EOI
            if size is None:
                raise Refused("site.err_image")
            out.append(data[pos:])
            break
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):  # APP1..APP15 and COM are left out
            out.append(data[pos:end])
        pos = end
    _size_ok(*size)
    return b"".join(out), size[0], size[1]


def clean(data):
    """(cleaned bytes, extension, width, height) of an uploaded image, or raises Refused."""
    if len(data) > MAX_BYTES:
        raise Refused("site.err_image_size")
    if data.startswith(PNG_SIGNATURE):
        cleaned, width, height = clean_png(data)
        return cleaned, "png", width, height
    if data.startswith(b"\xff\xd8\xff"):
        cleaned, width, height = clean_jpeg(data)
        return cleaned, "jpg", width, height
    raise Refused("site.err_image")
