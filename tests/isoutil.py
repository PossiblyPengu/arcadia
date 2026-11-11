"""Build small but structurally valid disc images for tests."""

import struct
import zlib

SECTOR = 2048


def _record(name: bytes, lba: int, size: int, is_dir: bool = False) -> bytes:
    length = 33 + len(name)
    if length % 2:
        length += 1
    rec = bytearray(length)
    rec[0] = length
    rec[2:6] = struct.pack("<I", lba)
    rec[6:10] = struct.pack(">I", lba)
    rec[10:14] = struct.pack("<I", size)
    rec[14:18] = struct.pack(">I", size)
    rec[25] = 2 if is_dir else 0
    rec[32] = len(name)
    rec[33 : 33 + len(name)] = name
    return bytes(rec)


def logical_sectors(files=None, dirs=(), system_id=b"PLAYSTATION", sector0=b"") -> list[bytes]:
    """The 2048-byte sectors of an ISO 9660 disc. files: {"SYSTEM.CNF;1": b"..."}, dirs: ["PSP_GAME"]."""
    files = files or {}
    root_lba = 20
    next_lba = 24
    entries = [_record(b"\x00", root_lba, SECTOR, True), _record(b"\x01", root_lba, SECTOR, True)]
    payload: dict[int, bytes] = {}
    for d in dirs:
        entries.append(_record(d.encode("latin-1"), next_lba, SECTOR, True))
        next_lba += 1
    for name, data in files.items():
        entries.append(_record(name.encode("latin-1"), next_lba, len(data)))
        for k in range(0, max(len(data), 1), SECTOR):
            payload[next_lba + k // SECTOR] = data[k : k + SECTOR].ljust(SECTOR, b"\x00")
        next_lba += max(1, (len(data) + SECTOR - 1) // SECTOR)

    root = b"".join(entries).ljust(SECTOR, b"\x00")
    assert len(b"".join(entries)) <= SECTOR

    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[8:40] = system_id.ljust(32, b" ")
    pvd[156:190] = _record(b"\x00", root_lba, SECTOR, True)[:33] + b"\x00"
    pvd[156] = 34
    pvd[188] = 1  # root name length byte lives at offset 32 of the record
    pvd[156 + 32] = 1
    pvd[156 + 33] = 0

    sectors = [b"\x00" * SECTOR for _ in range(next_lba + 1)]
    sectors[0] = sector0.ljust(SECTOR, b"\x00")[:SECTOR]
    sectors[16] = bytes(pvd)
    sectors[17] = b"\xff" + b"CD001" + b"\x01" + b"\x00" * (SECTOR - 7)
    sectors[root_lba] = root
    for lba, data in payload.items():
        sectors[lba] = data
    return sectors


def lay_out(sectors: list[bytes], layout=(2048, 0)) -> bytes:
    size, offset = layout
    image = bytearray(len(sectors) * size)
    for i, sector in enumerate(sectors):
        start = i * size
        if size == 2352:
            image[start : start + 12] = b"\x00" + b"\xff" * 10 + b"\x00"  # sync pattern
        image[start + offset : start + offset + SECTOR] = sector
    return bytes(image)


def iso(files=None, dirs=(), system_id=b"PLAYSTATION", sector0=b"", layout=(2048, 0)) -> bytes:
    return lay_out(logical_sectors(files, dirs, system_id, sector0), layout)


def psx_disc(layout=(2048, 0)) -> bytes:
    return iso({"SYSTEM.CNF;1": b"BOOT = cdrom:\\SLUS_006.94;1\r\nTCB = 4\r\n"}, layout=layout)


def ps2_disc(layout=(2048, 0)) -> bytes:
    return iso({"SYSTEM.CNF;1": b"BOOT2 = cdrom0:\\SLUS_200.62;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"}, layout=layout)


def psp_disc() -> bytes:
    return iso(dirs=["PSP_GAME"], system_id=b"PSP GAME")


def ps3_disc() -> bytes:
    return iso({"PS3_DISC.SFB": b"SFB\x00"}, dirs=["PS3_GAME"], system_id=b"PS3VOLUME")


def cso(image: bytes, compress=True, align=0) -> bytes:
    """Wrap a 2048-byte-sector image as a CISO (.cso) file."""
    blocks = [image[i : i + SECTOR].ljust(SECTOR, b"\x00") for i in range(0, len(image), SECTOR)]
    header_size = 0x18
    index_size = 4 * (len(blocks) + 1)
    body = bytearray()
    index = []
    base = header_size + index_size
    for block in blocks:
        offset = base + len(body)
        assert offset % (1 << align) == 0
        packed = zlib.compress(block)[2:-4] if compress else block  # raw deflate
        if compress and len(packed) >= SECTOR:
            packed, plain = block, True
        else:
            plain = not compress
        index.append((offset >> align) | (0x80000000 if plain else 0))
        body += packed
        while len(body) % (1 << align):
            body += b"\x00"
    index.append((base + len(body)) >> align)
    head = b"CISO" + struct.pack("<IQIBB", header_size, len(blocks) * SECTOR, SECTOR, 1, align) + b"\x00\x00"
    return head + struct.pack(f"<{len(index)}I", *index) + bytes(body)


def read_at_for(data: bytes):
    return lambda offset, n: data[offset : offset + n]
