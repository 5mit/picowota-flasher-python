
from protocol import (
    SyncCommand,
    InfoCommand,
    EraseCommand,
    WriteCommand,
    SealCommand,
    GoCommand,
    NotSyncedError,
)
from progressbar import ProgressBar, report_progress
from elf import load_elf

MAX_SYNC_ATTEMPTS = 5


class Image:
    def __init__(self, addr: int, vtor: int, data: bytes, version: int):
        self.addr = addr
        self.vtor = vtor
        self.data = data
        self.version = version

def load_image(fname, base_arg=None):
    if fname.endswith(".elf"):
        if base_arg is not None:
            raise ValueError("base address can't be specified for ELF files")

        return load_elf(fname)

    else:
        if base_arg is None:
            raise ValueError("base address required for binary files")

        base = int(base_arg, 0)
        return load_bin(fname, base)





def align(val: int, to: int) -> int:
    return (val + (to - 1)) & ~(to - 1)


# ------------------------
# Sync logic
# ------------------------

def sync(rw, pbar:ProgressBar=None):
    last_err = None

    for i in range(MAX_SYNC_ATTEMPTS):
        if pbar: report_progress(pbar.progress_cb, "Synchronising", 0, 1)

        try:
            SyncCommand().execute(rw)
            if pbar: report_progress(pbar.progress_cb, "Synchronising", 1, 1)
            return
        except NotSyncedError as e:
            last_err = e
        except Exception:
            raise

    raise last_err

# ------------------------
# Info Query logic
# ------------------------
def query(rw, pbar:ProgressBar=None):

    if pbar: report_progress(pbar.progress_cb, "Querying device info", 0, 1)
    ic = InfoCommand()
    try:
        ic.execute(rw)
    except Exception as e:
        if pbar: 
            pbar.progress_q.put(None)
            pbar.reporter.join()
        raise Exception(f"info: {e}")
    
    if pbar: report_progress(pbar.progress_cb, "Querying device info", 1, 1)
    return ic
    

# ------------------------
# Main flashing logic
# ------------------------

def program(conn, fname, go=True, pbar:ProgressBar=None):
    
    img = load_image(fname)

    try:
        _program(conn, img, pbar)
    except Exception as e:
        if pbar: 
            pbar.progress_q.put(None)
            pbar.reporter.join()
        raise e

    print("Programming complete")
    
    if go:
        gc = GoCommand(img.addr)
        gc.execute(conn)


def _program(rw, img: Image, pbar:ProgressBar=None):
    
    # 1. Sync
    try:
        sync(rw, pbar)
    except Exception as e:
        raise Exception(f"sync: {e}")

    # 2. Query device info
    ic = None
    try:
        ic = query(rw, pbar)
    except Exception as e:
        raise Exception(f"info: {e}")

    # 3. Pad data to write size
    pad = align(len(img.data), ic.write_size) - len(img.data)
    data = img.data + (b"\x00" * pad)
    #print("img addr:" + str(hex(img.addr)))
    # 4. Bounds checking
    if img.vtor == ic.vtor: # Don't overwrite active firmware slot
        raise Exception(
            f"image load address same as active firmware in slot {"A" if ic.active_slot == 0 else "B"}: 0x{img.addr:08x} == 0x{ic.vtor:08x}. Provided image file must instead be linked for slot {"B" if ic.active_slot == 0 else "A"} (0x{ic.flash_addr:08x})"
        )
    # Ensure image is within target firmware slot
    if img.addr < ic.flash_addr:
        raise Exception(
            f"image load address too low: 0x{img.addr:08x} < 0x{ic.flash_addr:08x}"
        )
    if img.addr > ic.flash_addr + (2 * 1024 * 1024):
        raise Exception(
            f"image load address too high: 0x{img.addr:08x} < 0x{ic.flash_addr:08x}"
        )

    if img.addr + len(data) > ic.flash_addr + ic.flash_slot_size:
        raise Exception(
            f"image of {len(data)} bytes doesn't fit in flash at 0x{img.addr:08x}"
        )

    # 5. Erase
    erase_len = align(len(data), ic.erase_size)

    if pbar: report_progress(pbar.progress_cb, "Erasing", 0, erase_len)

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

        if pbar: report_progress(pbar.progress_cb, "Erasing", end, erase_len)
        start += ic.erase_size

    # 6. Write
    if pbar: report_progress(pbar.progress_cb, "Writing", 0, len(data))

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

        if pbar: report_progress(pbar.progress_cb, "Writing", end, len(data))
        start = end

    # 7. Seal
    if pbar: report_progress(pbar.progress_cb, "Sealing", 0, 1)

    sc = SealCommand(img.addr, data, img.version)

    try:
        sc.execute(rw)
    except Exception as e:
        raise Exception(f"seal: {e}")

    if pbar: 
        report_progress(pbar.progress_cb, "Sealing", 1, 1)
        pbar.progress_q.put(None)
        pbar.reporter.join()