import struct
import zlib
from dataclasses import dataclass


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
# Config region opcodes
OPCODE_CFG_READ  = b"CFGR"
OPCODE_CFG_WRITE = b"CFGW"
OPCODE_CFG_ERASE = b"CFGE"


# Responses
RESPONSE_SYNC      = b"PICO"
RESPONSE_SYNC_WOTA = b"WOTA"
RESPONSE_OK        = b"OKOK"
RESPONSE_ERR       = b"ERR!"


# Header Structure from server
RESP_HDR = 8 # 4 bytes status + 4 bytes length

class NotSyncedError(Exception):
    pass


# ------------------------
# Low-level helpers
# ------------------------


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


def read_frame(rw):
    header = rw.read(RESP_HDR)
    status = header[:4]
    length = unpack_u32(header, 4)
    #print(header, status, length)
    payload = b""
    if length:
        payload = rw.read(length)
        #print("payload::::", payload)
        #print(len(payload))
    



    return status, payload


# ------------------------
# Commands
# ------------------------

class SyncCommand:
    def execute(self, rw):
        rw.write(b"SYNC")

        status, _ = read_frame(rw)
        #print(status)

        if status in (b"PICO", b"WOTA"):
            return

        raise Exception(f"unexpected sync response: {status!r}")


class ReadCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.data = None

    def execute(self, rw):
        buf = OPCODE_READ + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"READ failed: {status!r}")

        self.data = payload


class CsumCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.csum = None

    def execute(self, rw):
        buf = OPCODE_CSUM + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        #resp = read_response(rw, 8)
        #self.csum = unpack_u32(resp, 4)

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"CSUM failed: {status!r}")

        self.csum = unpack_u32(payload, 0)


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

        #resp = read_response(rw, 8)
        #self.crc = unpack_u32(resp, 4)

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"CRC failed: {status!r}")

        self.crc = unpack_u32(payload, 0)


class EraseCommand:
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length

    def execute(self, rw):
        buf = OPCODE_ERASE + u32le(self.addr) + u32le(self.length)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        #read_response(rw, 4)
        status, _ = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"ERASE failed: {status!r}")


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

        #resp = read_response(rw, 8)

       # resp_crc = unpack_u32(resp, 4)
        #calc_crc = zlib.crc32(self.data) & 0xFFFFFFFF

        #if resp_crc != calc_crc:
        #    raise Exception(
        #        f"CRC mismatch: 0x{resp_crc:08x} vs 0x{calc_crc:08x}"
        #    )
        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"WRITE failed: {status!r}")

        resp_crc = unpack_u32(payload, 0)
        calc_crc = zlib.crc32(self.data) & 0xFFFFFFFF

        if resp_crc != calc_crc:
            raise Exception(
                f"CRC mismatch: 0x{resp_crc:08x} vs 0x{calc_crc:08x}"
            )


class SealCommand:
    def __init__(self, addr, data: bytes, version: int):
        self.addr = addr
        self.length = len(data)
        self.version = version
        self.crc = zlib.crc32(data) & 0xFFFFFFFF

    def execute(self, rw):
        buf = (
            OPCODE_SEAL
            + u32le(self.addr)
            + u32le(self.length)
            + u32le(self.version)
            + u32le(self.crc)
            
        )
        print("SEAL command:")
        print(self.addr)
        print(self.length)
        print(self.version)
        print(self.crc)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        #read_response(rw, 4)
        status, _ = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"SEAL failed: {status!r}")


class GoCommand:
    def __init__(self, addr):
        self.addr = addr

    def execute(self, rw):
        print(f"Jump to {hex(self.addr)}")
        buf = OPCODE_GO + u32le(self.addr)

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        # fire-and-forget (same as Go) (No response expected)

@dataclass
class InfoCommand:
    # Bounds
    flash_addr: int | None = None
    flash_size: int | None = None
    erase_size: int | None = None
    write_size: int | None = None
    max_data_len: int | None = None
    # Meta
    active_slot: int | None = None
    slot_a_state: int | None = None
    slot_b_state: int | None = None
    # Active Image Header
    vtor: int | None = None
    size: int | None = None
    version: int | None = None
    crc: int | None = None

    def execute(self, rw):
        if rw.write(OPCODE_INFO) != len(OPCODE_INFO):
            raise Exception("unexpected write length")

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception("INFO failed")

        (
            self.flash_addr,
            self.flash_size,
            self.erase_size,
            self.write_size,
            self.max_data_len,
            self.active_slot,
            self.slot_a_state,
            self.slot_b_state,
            self.vtor,
            self.size,
            self.version,
            self.crc,
        ) = struct.unpack("<12I", payload)

        print(f"flash_addr: 0x{self.flash_addr:08x}")
        print(f"flash_size: {self.flash_size} bytes")
        print(f"erase_size: {self.erase_size} bytes")
        print(f"write_size: {self.write_size} bytes")
        print(f"max_data_len: {self.max_data_len} bytes")
        print(f"active_slot: {self.active_slot}")
        print(f"slot_a_state: {self.slot_a_state}")
        print(f"slot_b_state: {self.slot_b_state}")
        print(f"vtor: 0x{self.vtor:08x}")
        print(f"size: {self.size} bytes")
        print(f"version: 0x{self.version:08x}")
        print(f"crc: 0x{self.crc:08x}")

class ConfigReadCommand:
    def __init__(self, offset, length):
        self.offset = offset
        self.length = length
        self.data = None

    def execute(self, rw):
        buf = (
            OPCODE_CFG_READ
            + u32le(self.offset)
            + u32le(self.length)
        )

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"config read failed: {status!r}")

        self.data = payload


class ConfigEraseCommand:
    def __init__(self, offset, length):
        self.offset = offset
        self.length = length

    def execute(self, rw):
        buf = (
            OPCODE_CFG_ERASE
            + u32le(self.offset)
            + u32le(self.length)
        )

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        status, _ = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"config erase failed: {status!r}")



class ConfigWriteCommand:
    def __init__(self, offset, data: bytes):
        self.offset = offset
        self.length = len(data)
        self.data = data

    def execute(self, rw):
        buf = (
            OPCODE_CFG_WRITE
            + u32le(self.offset)
            + u32le(self.length)
            + self.data
        )

        if rw.write(buf) != len(buf):
            raise Exception("unexpected write length")

        status, payload = read_frame(rw)

        if status != RESPONSE_OK:
            raise Exception(f"config write failed: {status!r}")

        resp_crc = unpack_u32(payload, 0)
        calc_crc = zlib.crc32(self.data) & 0xFFFFFFFF

        if resp_crc != calc_crc:
            raise Exception(
                f"CRC mismatch: 0x{resp_crc:08X} vs 0x{calc_crc:08X}"
            )