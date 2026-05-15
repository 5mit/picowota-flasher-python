from typing import Optional, Callable
from protocol import (
    SyncCommand,
    InfoCommand,
    EraseCommand,
    WriteCommand,
    SealCommand,
    NotSyncedError,
)

MAX_SYNC_ATTEMPTS = 5


class Image:
    def __init__(self, addr: int, data: bytes):
        self.addr = addr
        self.data = data


class ProgressReport:
    def __init__(self, stage: str, progress: int, max_val: int):
        self.stage = stage
        self.progress = progress
        self.max = max_val


def report_progress(callback: Optional[Callable], stage, progress, max_val):
    if callback:
        callback(stage, progress, max_val)


def align(val: int, to: int) -> int:
    return (val + (to - 1)) & ~(to - 1)


# ------------------------
# Sync logic
# ------------------------

def sync(rw, progress_cb=None):
    last_err = None

    for i in range(MAX_SYNC_ATTEMPTS):
        report_progress(progress_cb, "Synchronising", i, MAX_SYNC_ATTEMPTS)

        try:
            SyncCommand().execute(rw)
            report_progress(progress_cb, "Synchronising", i + 1, MAX_SYNC_ATTEMPTS)
            return
        except NotSyncedError as e:
            last_err = e
        except Exception:
            raise

    raise last_err


# ------------------------
# Main flashing logic
# ------------------------

def program(rw, img: Image, progress_cb=None):
    
    # 1. Sync
    try:
        sync(rw, progress_cb)
    except Exception as e:
        raise Exception(f"sync: {e}")

    # 2. Query device info
    report_progress(progress_cb, "Querying device info", 0, 1)

    ic = InfoCommand()
    try:
        ic.execute(rw)
    except Exception as e:
        raise Exception(f"info: {e}")

    report_progress(progress_cb, "Querying device info", 1, 1)

    # 3. Pad data to write size
    pad = align(len(img.data), ic.write_size) - len(img.data)
    data = img.data + (b"\x00" * pad)
    print("img addr:" + str(hex(img.addr)))
    # 4. Bounds checking
    if img.addr < ic.flash_addr:
        raise Exception(
            f"image load address too low: 0x{img.addr:08x} < 0x{ic.flash_addr:08x}"
        )
    if img.addr > ic.flash_addr + (2 * 1024 * 1024):
        raise Exception(
            f"image load address too high: 0x{img.addr:08x} < 0x{ic.flash_addr:08x}"
        )

    if img.addr + len(data) > ic.flash_addr + ic.flash_size:
        raise Exception(
            f"image of {len(data)} bytes doesn't fit in flash at 0x{img.addr:08x}"
        )

    # 5. Erase
    erase_len = align(len(data), ic.erase_size)

    report_progress(progress_cb, "Erasing", 0, erase_len)

    start = 0
    while start < erase_len:
        end = start + ic.erase_size

        ec = EraseCommand(
            addr=img.addr + start,
            length=ic.erase_size,
        )

        try:
            ec.execute(rw)
        except Exception as e:
            raise Exception(f"erase: {e}")

        report_progress(progress_cb, "Erasing", end, erase_len)
        start += ic.erase_size

    # 6. Write
    report_progress(progress_cb, "Writing", 0, len(data))

    start = 0
    while start < len(data):
        end = min(start + ic.max_data_len, len(data))
        wc = WriteCommand(
            addr=img.addr + start,
            data=data[start:end],
        )

        try:
            wc.execute(rw)
        except Exception as e:
            raise Exception(f"write: {e}")

        report_progress(progress_cb, "Writing", end, len(data))
        start = end

    # 7. Seal
    report_progress(progress_cb, "Finalising", 0, 1)

    sc = SealCommand(img.addr, data)

    try:
        sc.execute(rw)
    except Exception as e:
        raise Exception(f"seal: {e}")

    report_progress(progress_cb, "Finalising", 1, 1)