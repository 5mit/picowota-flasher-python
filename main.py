import sys
import socket
import time
import threading
import queue

import serial  # pip install pyserial
from tqdm import tqdm  # pip install tqdm

from program import program as prog
from protocol import GoCommand
from elf import load_elf
from binary import load_bin

class SocketWrapper:
    def __init__(self, sock):
        self.sock = sock

    def read(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise IOError("socket closed")
            data += chunk
        return data

    def write(self, data):
        self.sock.sendall(data)   # no return value
        return len(data)          # IMPORTANT FIX
    

def usage():
    raise ValueError(f"Usage: {sys.argv[0]} PORT FILE [BASE]")


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


def load_image():
    if len(sys.argv) < 3:
        usage()

    fname = sys.argv[2]

    if fname.endswith(".elf"):
        if len(sys.argv) > 3:
            print("base address can't be specified for ELF files")
            usage()

        return load_elf(fname)

    else:
        if len(sys.argv) < 4:
            print("base address must be specified for binary files")
            usage()

        base = int(sys.argv[3], 0)
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


def run():
    if len(sys.argv) < 3:
        usage()

    port = sys.argv[1]
    img = load_image()
    print(hex(img.addr))

    conn = open_connection(port)

    progress_q = queue.Queue()
    reporter = ProgressReporter(progress_q)
    reporter.start()


    # Convert callback → queue messages
    def progress_cb(stage, progress, max_val):
        progress_q.put((stage, progress, max_val))

    try:
        # Flash firmware
        prog(conn, img, progress_cb)

    finally:
        progress_q.put(None)
        reporter.join()

    # Execute Go command (jump to firmware)
    gc = GoCommand(img.addr)
    gc.execute(conn)

    print("Done")


def main():
    try:
        run()
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()