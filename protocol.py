import struct
import zlib

# Opcodes
OPCODE_SYNC  = b"SYNC"
OPCODE_READ  = b"READ"
OPCODE_CSUM  = b"CSUM"
OPCODE_CRC   = b"CRCC"
OPCODE_ERASE = b"ERAS"
OPCODE_WRITE = b"WRIT"
OPCODE_SEAL  = b"SEAL"
OPCODE_GO    = b"GOGO"
OPCODE_INFO  = b"INFO"

# Responses
RESPONSE_SYNC      = b"PICO"
RESPONSE_SYNC_WOTA = b"WOTA"
RESPONSE_OK        = b"OKOK"
RESPONSE_ERR       = b"ERR!"

class NotSyncedError(Exception):
    pass


# ------------------------
# Low-level helpers
# ------------------------

def read_exact(rw, n):
    """Read exactly n bytes"""
    buf = b""
    while len(buf) < n:
        chunk = rw.read(n - len(buf))
        if not chunk:
            raise IOError("connection closed")
        buf += chunk
    return buf


def read_response(rw, response_len):
    data = b""
    while len(data) < response_len:
        chunk = rw.read(response_len - len(data))
        if not chunk:
            raise IOError("connection closed")
        data += chunk
    return data


def u32le(x):
    return struct.pack("<I", x)


def unpack_u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


# ------------------------
# Commands
# ------------------------

class SyncCommand:
    def execute(self, rw):
        rw.write(b"SYNC")

        # ONLY read exactly 4 bytes (response header)
        resp = read_exact(rw, 4)

        if resp in (b"PICO", b"WOTA"):
            return

        raise Exception(f"unexpected sync response: {resp!r}")


class ReadCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.data = None

    def execute(self, rw):
        buf = OPCODE_READ + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        resp = read_response(rw, 4 + self.length)

        self.data = resp[4:]


class CsumCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.csum = None

    def execute(self, rw):
        buf = OPCODE_CSUM + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        resp = read_response(rw, 8)
        self.csum = unpack_u32(resp, 4)


def calculate_checksum(data: bytes) -> int:
    aligned_len = ((len(data) + 3) // 4) * 4
    buf = data.ljust(aligned_len, b"\x00")

    result = 0
    for i in range(0, aligned_len, 4):
        result += struct.unpack_from("<I", buf, i)[0]

    return result & 0xFFFFFFFF


class CRCCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.crc = None

    def execute(self, rw):
        buf = OPCODE_CRC + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        resp = read_response(rw, 8)
        self.crc = unpack_u32(resp, 4)


class EraseCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length

    def execute(self, rw):
        buf = OPCODE_ERASE + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        read_response(rw, 4)


class WriteCommand:
    def __init__(self, addr, data: bytes):
        self.addr = addr
        self.length = len(data)
        self.data = data

    def execute(self, rw):
        buf = (
            OPCODE_WRITE
            + u32le(self.addr)
            + u32le(self.length)
            + self.data
        )

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        resp = read_response(rw, 8)

        resp_crc = unpack_u32(resp, 4)
        calc_crc = zlib.crc32(self.data) & 0xFFFFFFFF

        if resp_crc != calc_crc:
            raise Exception(
                f"CRC mismatch: 0x{resp_crc:08x} vs 0x{calc_crc:08x}"
            )


class SealCommand:
    def __init__(self, addr, data: bytes):
        self.addr = addr
        self.length = len(data)
        self.crc = zlib.crc32(data) & 0xFFFFFFFF

    def execute(self, rw):
        buf = (
            OPCODE_SEAL
            + u32le(self.addr)
            + u32le(self.length)
            + u32le(self.crc)
            + u32le(0) # Version
        )
        print(self.addr)
        print(self.length)
        print(self.crc)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        read_response(rw, 4)


class GoCommand:
    def __init__(self, addr):
        self.addr = addr

    def execute(self, rw):
        print(f"Jump to {hex(self.addr)}")
        buf = OPCODE_GO + u32le(self.addr)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        # fire-and-forget (same as Go)


class InfoCommand:
    def __init__(self):
        self.flash_addr = None
        self.flash_size = None
        self.erase_size = None
        self.write_size = None
        self.max_data_len = None
        self.active_slot = None
        self.slot_a_state = None
        self.slot_b_state = None

    def execute(self, rw):
        if rw.write(OPCODE_INFO) != len(OPCODE_INFO):
            raise Exception("unexpected write length")

        resp = read_response(rw, 4 + 32)

        self.flash_addr = unpack_u32(resp, 4)
        self.flash_size = unpack_u32(resp, 8)
        self.erase_size = unpack_u32(resp, 12)
        self.write_size = unpack_u32(resp, 16)
        self.max_data_len = unpack_u32(resp, 20)
        self.active_slot = unpack_u32(resp, 24)
        self.slot_a_state = unpack_u32(resp, 28)
        self.slot_b_state = unpack_u32(resp, 32)

        print(f"flash_addr: 0x{self.flash_addr:08x}")
        print(f"flash_size: {self.flash_size} bytes")
        print(f"erase_size: {self.erase_size} bytes")
        print(f"write_size: {self.write_size} bytes")
        print(f"max_data_len: {self.max_data_len} bytes")
        print(f"active_slot: {self.active_slot}")
        print(f"slot_a_state: {self.slot_a_state}")
        print(f"slot_b_state: {self.slot_b_state}")