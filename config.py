

from protocol import (
    SyncCommand,
    InfoCommand,
    ConfigReadCommand,
    ConfigEraseCommand,
    ConfigWriteCommand
)

from program import sync, query
from progressbar import ProgressBar, report_progress

# ------------------------
# Config region read
# ------------------------

def read_config(rw, offset, total_length, pbar:ProgressBar=None) -> bytes:
      
    if (offset & 255) != 0 or (total_length & 255) != 0:
        raise ValueError("OFFSET & SIZE must be multiples of 256")

    remaining_length = total_length
    data = b""

    MAX_CHUNK_SIZE = 1024
    while remaining_length > 0:
        if remaining_length > MAX_CHUNK_SIZE:
            length = MAX_CHUNK_SIZE
        else:
            length = remaining_length
        try:
            data += _read_config(rw, offset, length, pbar)
        except Exception as e:
            if pbar: 
                pbar.progress_q.put(None)
                pbar.reporter.join()
            raise e
        offset += length
        remaining_length -= length

    print(f"Read {len(data)} bytes")

    return data

def _read_config(rw, offset, length, pbar:ProgressBar=None) -> bytes:
    """
    Read bytes from config flash region.
    """

    # Sync
    try:
        sync(rw, pbar)
    except Exception as e:
        raise Exception(f"sync: {e}")

    if pbar: report_progress(pbar.progress_cb, "Reading config", 0, length)

    rc = ConfigReadCommand(offset, length)

    try:
        rc.execute(rw)
    except Exception as e:
        raise Exception(f"config read: {e}")

    if pbar: 
        report_progress(pbar.progress_cb, "Reading config", length, length)
        pbar.progress_q.put(None)
        pbar.reporter.join()
    return rc.data

def print_config_raw(data:bytes):
    for i in range(0, len(data), 16):
        if i > 0 and (i % 256) == 0:
            print()
        chunk = data[i:i+16]

        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(
            chr(b) if 32 <= b < 127 else "."
            for b in chunk
        )

        print(f"{i:08X}  {hex_part:<48}  {ascii_part}")


# ------------------------
# Config region erase
# ------------------------

def erase_config(rw, offset, length, pbar:ProgressBar=None):
    """
    Erase config flash region.
    Offset/length should be sector aligned.
    """
    if (offset & 4095) != 0 or (length & 4095) != 0:
        raise ValueError("OFFSET & SIZE must be multiples of 4096")

    # Sync
    try:
        sync(rw, pbar)
    except Exception as e:
        raise Exception(f"sync: {e}")

    if pbar: report_progress(pbar.progress_cb, "Erasing config", 0, length)

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

        if pbar: report_progress(
            pbar.progress_cb,
            "Erasing config",
            start,
            length,
        )
    if pbar:
        pbar.progress_q.put(None)
        pbar.reporter.join()
    print("Config erase complete.")




def write_config(conn, offset:int, fname:str, pbar:ProgressBar=None):
    if (offset & 255) != 0:
        raise ValueError("OFFSET must be multiple of 256")

    with open(fname, "rb") as f:
        data = f.read()

    # optional: enforce alignment rules like erase/read
    print(len(data))
    if len(data) & 255 != 0:
        raise ValueError("FILE SIZE must be multiple of 256")

    try:
        _write_config(conn, offset, data, pbar)
    except Exception as e:
        if pbar: 
            pbar.progress_q.put(None)
            pbar.reporter.join()
        raise e


    print("Writecfg complete")
    return


def _write_config(rw, offset, data: bytes, pbar:ProgressBar=None):
    """
    Write bytes to config flash region.
    """

    # Sync first (same pattern as read/erase)
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



    total = len(data)
    if pbar: report_progress(pbar.progress_cb, "Writing config", 0, total)

    chunk_size = ic.max_data_len
    written = 0

    #TODO erase sector first

    print(data)

    while written < total:
        chunk = data[written:(written + chunk_size)]

        wc = ConfigWriteCommand(offset + written, chunk)

        try:
            wc.execute(rw)
        except Exception as e:
            raise Exception(f"config write: {e}")

        written += len(chunk)

        if pbar: report_progress(pbar.progress_cb, "Writing config", written, total)

    if pbar: 
        report_progress(pbar.progress_cb, "Writing config", total, total)
        pbar.progress_q.put(None)
        pbar.reporter.join()
    print("Config write complete.")