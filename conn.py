import socket
import time
import serial
from progressbar import ProgressBar
from program import program as _prog, query, sync
from config import read_config as _read_cfg, erase_config as _erase_cfg, write_config as _write_cfg, print_config_raw

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


class SerialFlasher:
    def __init__(self, port, progress_bar=False):
        self.port = port
        self.conn = self._open_connection(port)
        if progress_bar:
            self.pbar = ProgressBar()
        else:
            self.pbar = None
    
    
    def _open_connection(self, port: str):
        
        if port.startswith("tcp:"):
            addr = port[len("tcp:"):]
            host, port_str = addr.split(":")
            sock = socket.create_connection((host, int(port_str)))
            print("Opened connection to", addr)
            time.sleep(1)
            conn = SocketWrapper(sock)
            conn.settimeout(3)
            return conn

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

    def info(self):
        try:
            sync(self.conn, self.pbar)
            ic = query(self.conn, self.pbar)
        finally:
            if self.pbar:
                self.pbar.progress_q.put(None)
                self.pbar.reporter.join()
        
        ic.print()
        return
    
    def program(self, fname:str, go=True):
        _prog(self.conn, fname, go, self.pbar)
        return
    
    def read_config(self, offset:int, length:int, print=True) -> bytes:
        data = _read_cfg(self.conn, offset, length, self.pbar)
        if print:
            print_config_raw(data)
        return data
    
    def erase_config(self, offset:int, length:int):
        _erase_cfg(self.conn, offset, length, self.pbar)
        return
    
    def write_config(self, offset:int, fname:str):
        _write_cfg(self.conn, offset, fname, self.pbar)
        return
