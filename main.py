import sys
import socket
import time
import threading
import queue

import serial
from tqdm import tqdm

from program import (
    program as prog,
)

from config import read_config, erase_config, write_config
from protocol import GoCommand
from elf import load_elf
from binary import load_bin


class SocketWrapper:
    def __init__(self, sock):
        self.sock = sock

    
    def settimeout(self, timeout):
        self.sock.settimeout(timeout)

    def close(self):
        self.sock.close()

    def send(self, data):
        return self.sock.send(data)

    def sendall(self, data):
        return self.sock.sendall(data)

    def read(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise IOError("socket closed")
            data += chunk
        return data

    def write(self, data):
        self.sock.sendall(data)
        return len(data)


def usage():
    print(f"""
Usage:

Program firmware:
    {sys.argv[0]} program PORT FILE BASE

Read config region:
    {sys.argv[0]} readcfg PORT OFFSET SIZE

Erase config region:
    {sys.argv[0]} erasecfg PORT OFFSET SIZE

Write config region:
    {sys.argv[0]} writecfg PORT OFFSET FILE
""")
    sys.exit(1)


def open_connection(port: str):
    if port.startswith("tcp:"):
        addr = port[len("tcp:"):]
        host, port_str = addr.split(":")

        sock = socket.create_connection((host, int(port_str)))
        print("Opened connection to", addr)

        time.sleep(1)



        return SocketWrapper(sock)

    else:
        ser = serial.Serial(
            port=port,
            baudrate=921600,
            bytesize=8,
            stopbits=1,
            timeout=0.1,
        )

        print("Opened", port)
        return ser


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


class ProgressReporter(threading.Thread):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q
        self.daemon = True

    def run(self):
        last_stage = None
        bar = None

        while True:
            item = self.q.get()

            if item is None:
                break

            stage, progress, max_val = item

            if stage != last_stage:
                if bar:
                    bar.close()

                print(stage + ":")
                bar = tqdm(total=max_val, dynamic_ncols=True)

            if bar:
                bar.n = progress
                bar.refresh()

            last_stage = stage

        if bar:
            bar.close()


def make_progress_cb():
    progress_q = queue.Queue()

    reporter = ProgressReporter(progress_q)
    reporter.start()

    def progress_cb(stage, progress, max_val):
        progress_q.put((stage, progress, max_val))

    return progress_q, reporter, progress_cb


def run():
    if len(sys.argv) < 3:
        usage()

    command = sys.argv[1]
    port = sys.argv[2]

    conn = open_connection(port)
    conn.settimeout(3)

    #
    # PROGRAM
    #
    if command == "program":

        if len(sys.argv) < 4:
            usage()

        fname = sys.argv[3]

        img = load_image(fname)

        progress_q, reporter, progress_cb = make_progress_cb()

        try:
            prog(conn, img, progress_cb)

        finally:
            progress_q.put(None)
            reporter.join()

        gc = GoCommand(img.addr)
        gc.execute(conn)

        print("Programming complete")
        return

    #
    # READ CONFIG
    #
    elif command == "readcfg":

        if len(sys.argv) < 5:
            usage()


        offset = int(sys.argv[3])
        total_length = int(sys.argv[4])

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
            data += read_config(conn, offset, length)
            offset += length
            remaining_length -= length

        print(f"Read {len(data)} bytes")

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

        return

    #
    # ERASE CONFIG
    #
    elif command == "erasecfg":

        if len(sys.argv) < 5:
            usage()


        offset = int(sys.argv[3])
        length = int(sys.argv[4])
        erase_config(conn, offset, length)

        print("Config region erased")
        return
    

        #
    # WRITE CONFIG
    #
    elif command == "writecfg":

        if len(sys.argv) < 5:
            usage()

        offset = int(sys.argv[3])
        fname = sys.argv[4]

        if (offset & 255) != 0:
            raise ValueError("OFFSET must be multiple of 256")

        with open(fname, "rb") as f:
            data = f.read()

        # optional: enforce alignment rules like erase/read
        print(len(data))
        if len(data) & 255 != 0:
            raise ValueError("FILE SIZE must be multiple of 256")

        progress_q, reporter, progress_cb = make_progress_cb()

        try:
            write_config(conn, offset, data, progress_cb)
        finally:
            progress_q.put(None)
            reporter.join()

        print("Writecfg complete")
        return

    else:
        usage()


def main():
    try:
        run()

    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()