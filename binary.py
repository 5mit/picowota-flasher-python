class Image:
    def __init__(self, addr: int, data: bytes):
        self.addr = addr
        self.data = data


def load_bin(fname: str, base: int) -> Image:
    with open(fname, "rb") as f:
        data = f.read()

    return Image(addr=base, data=data)