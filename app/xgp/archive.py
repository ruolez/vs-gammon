import struct
import zlib

RGMH_MAGIC = b"RGMH"
RGMH_SIZE = 8232
RGMH_STRING_CHARS = 1024
RGMH_GAME_NAME = 0x28
RGMH_SAVE_NAME = 0x828
RGMH_LEVEL_NAME = 0x1028
RGMH_COMMENTS = 0x1828

FOOTER_SIZE = 36
REGISTRY_ENTRY_SIZE = 532
ZLIB_LEVEL = 6


def read_utf16(buf, offset, chars):
    raw = buf[offset : offset + chars * 2].decode("utf-16-le")
    return raw.split("\x00", 1)[0]


def write_utf16(buf, offset, chars, text):
    encoded = text.encode("utf-16-le")[: (chars - 1) * 2]
    buf[offset : offset + chars * 2] = encoded + bytes(chars * 2 - len(encoded))


def parse_rich_header(data):
    if data[:4] != RGMH_MAGIC:
        raise ValueError("not an XG file: missing RGMH header")
    version, header_size, thumb_offset, thumb_size = struct.unpack_from("<iiqI", data, 4)
    if version != 1 or header_size != RGMH_SIZE:
        raise ValueError(f"unsupported RGMH header (version {version}, size {header_size})")
    return {
        "guid": bytes(data[0x18:0x28]),
        "game_name": read_utf16(data, RGMH_GAME_NAME, RGMH_STRING_CHARS),
        "save_name": read_utf16(data, RGMH_SAVE_NAME, RGMH_STRING_CHARS),
        "level_name": read_utf16(data, RGMH_LEVEL_NAME, RGMH_STRING_CHARS),
        "comments": read_utf16(data, RGMH_COMMENTS, RGMH_STRING_CHARS),
        "thumbnail": bytes(data[RGMH_SIZE + thumb_offset : RGMH_SIZE + thumb_offset + thumb_size]),
        "archive_start": RGMH_SIZE + thumb_offset + thumb_size,
    }


def build_rich_header(guid, save_name, thumbnail, game_name="", level_name="", comments=""):
    header = bytearray(RGMH_SIZE)
    header[:4] = RGMH_MAGIC
    struct.pack_into("<iiqI", header, 4, 1, RGMH_SIZE, 0, len(thumbnail))
    header[0x18:0x28] = guid
    write_utf16(header, RGMH_GAME_NAME, RGMH_STRING_CHARS, game_name)
    write_utf16(header, RGMH_SAVE_NAME, RGMH_STRING_CHARS, save_name)
    write_utf16(header, RGMH_LEVEL_NAME, RGMH_STRING_CHARS, level_name)
    write_utf16(header, RGMH_COMMENTS, RGMH_STRING_CHARS, comments)
    return bytes(header) + thumbnail


def unpack_archive(archive):
    crc, count, version, registry_size, archive_size, registry_compressed = struct.unpack_from(
        "<IiiiiB", archive, len(archive) - FOOTER_SIZE
    )
    body = archive[: len(archive) - FOOTER_SIZE]
    if zlib.crc32(body) != crc:
        raise ValueError("XG archive CRC mismatch")
    registry = body[archive_size : archive_size + registry_size]
    if registry_compressed:
        registry = zlib.decompress(registry)
    files = []
    for i in range(count):
        entry = registry[i * REGISTRY_ENTRY_SIZE : (i + 1) * REGISTRY_ENTRY_SIZE]
        name = entry[1 : 1 + entry[0]].decode("latin-1")
        size, csize, start, file_crc = struct.unpack_from("<iiiI", entry, 512)
        stored = entry[528] == 1
        chunk = body[start : start + csize]
        data = chunk if stored else zlib.decompress(chunk)
        if len(data) != size or zlib.crc32(data) != file_crc:
            raise ValueError(f"XG archive member {name} is corrupt")
        files.append((name, data))
    return files


def pack_archive(files):
    body = bytearray()
    registry = bytearray()
    for name, data in files:
        compressed = zlib.compress(data, ZLIB_LEVEL)
        entry = bytearray(REGISTRY_ENTRY_SIZE)
        encoded = name.encode("latin-1")
        entry[0] = len(encoded)
        entry[1 : 1 + len(encoded)] = encoded
        struct.pack_into("<iiiI", entry, 512, len(data), len(compressed), len(body), zlib.crc32(data))
        entry[528] = 0
        entry[529] = 2
        body += compressed
        registry += entry
    archive_size = len(body)
    body += zlib.compress(bytes(registry), ZLIB_LEVEL)
    footer = struct.pack(
        "<IiiiiB", zlib.crc32(body), len(files), 1, len(body) - archive_size, archive_size, 1
    ) + bytes(FOOTER_SIZE - 21)
    return bytes(body) + footer


def read_xg_file(data):
    header = parse_rich_header(data)
    header["files"] = unpack_archive(data[header["archive_start"] :])
    return header
