from typing import Optional, Callable

from protocol import (
    SyncCommand,
    InfoCommand,
    ConfigReadCommand,
    ConfigEraseCommand,
    ConfigWriteCommand
)

from program import sync, report_progress


# ------------------------
# Config region read
# ------------------------

def read_config(rw, offset, length, progress_cb=None) -> bytes:
    """
    Read bytes from config flash region.
    """

    # Sync
    try:
        sync(rw, progress_cb)
    except Exception as e:
        raise Exception(f"sync: {e}")

    report_progress(progress_cb, "Reading config", 0, length)

    rc = ConfigReadCommand(offset, length)

    try:
        rc.execute(rw)
    except Exception as e:
        raise Exception(f"config read: {e}")

    report_progress(progress_cb, "Reading config", length, length)

    return rc.data


# ------------------------
# Pretty-print config region
# ------------------------

def print_config(rw, offset, length, progress_cb=None):
    """
    Read and hex-print config region.
    """

    data = read_config(rw, offset, length, progress_cb)

    print(f"\nConfig region @ offset 0x{offset:08X}")
    print(f"Length: {length} bytes\n")

    for i in range(0, len(data), 16):
        chunk = data[i:i+16]

        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(
            chr(b) if 32 <= b <= 126 else "."
            for b in chunk
        )

        print(f"{offset + i:08X}  {hex_part:<47}  {ascii_part}")


# ------------------------
# Config region erase
# ------------------------

def erase_config(rw, offset, length, progress_cb=None):
    """
    Erase config flash region.
    Offset/length should be sector aligned.
    """
    if (offset & 4095) != 0 or (length & 4095) != 0:
        raise ValueError("OFFSET & SIZE must be multiples of 4096")

    # Sync
    try:
        sync(rw, progress_cb)
    except Exception as e:
        raise Exception(f"sync: {e}")

    report_progress(progress_cb, "Erasing config", 0, length)

    start = 0
    erase_size = 4096

    while start < length:
        ec = ConfigEraseCommand(
            offset=offset + start,
            length=erase_size,
        )

        try:
            ec.execute(rw)
        except Exception as e:
            raise Exception(f"config erase: {e}")

        start += erase_size

        report_progress(
            progress_cb,
            "Erasing config",
            start,
            length,
        )

    print("Config erase complete.")


    from protocol import ConfigWriteCommand
from program import sync, report_progress


def write_config(rw, offset, data: bytes, progress_cb=None):
    """
    Write bytes to config flash region.
    """

    # Sync first (same pattern as read/erase)
    try:
        sync(rw, progress_cb)
    except Exception as e:
        raise Exception(f"sync: {e}")

    total = len(data)
    report_progress(progress_cb, "Writing config", 0, total)

    chunk_size = 1024  #TODO grab from InfoCommand
    written = 0

    #TODO erase sector first

    print(data)

    while written < total:
        chunk = data[written:written + chunk_size]

        wc = ConfigWriteCommand(offset + written, chunk)

        try:
            wc.execute(rw)
        except Exception as e:
            raise Exception(f"config write: {e}")

        written += len(chunk)

        report_progress(progress_cb, "Writing config", written, total)

    report_progress(progress_cb, "Writing config", total, total)
    print("Config write complete.")