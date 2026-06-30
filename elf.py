from elftools.elf.elffile import ELFFile


FLASH_BASE = 0x10000000
FLASH_SIZE = 2 * 1024 * 1024


def default_in_flash(addr: int, size: int) -> bool:
    return FLASH_BASE <= addr and (addr + size) <= (FLASH_BASE + FLASH_SIZE)


class Image:
    def __init__(self, addr: int, vtor: int,  data: bytes, version: int):
        self.vtor = vtor
        self.addr = addr
        self.data = data
        self.version = version


class Chunk:
    def __init__(self, paddr: int, data: bytes):
        self.paddr = paddr
        self.data = data


def in_prog(vaddr: int, size: int, prog) -> bool:
    return vaddr >= prog["p_vaddr"] and (vaddr + size) <= (
        prog["p_vaddr"] + prog["p_memsz"]
    )

def read_fw_version(elf):
    sec = elf.get_section_by_name(".fw_version")
    if sec is None:
        return 0

    data = sec.data()
    return int.from_bytes(data[:4], "little")


from elftools.elf.sections import SymbolTableSection

def read_vtor(elf):
    for section in elf.iter_sections():
        if not isinstance(section, SymbolTableSection):
            continue

        symbol = section.get_symbol_by_name("__flash_binary_start")
        if symbol:
            return symbol[0]["st_value"]

    raise ValueError("__flash_binary_start not found")

def load_elf(fname: str, in_flash=default_in_flash) -> Image:
    with open(fname, "rb") as f:
        elf = ELFFile(f)

        chunks = []

        vtor = read_vtor(elf)
        print(f"found VTOR: {vtor:08x}")

        for prog in elf.iter_segments():
            paddr = prog["p_paddr"]
            
            memsz = prog["p_memsz"]

            if not in_flash(paddr, memsz):
                continue

            for sec in elf.iter_sections():
                if sec["sh_size"] == 0:
                    continue

                vaddr = sec["sh_addr"]
                size = sec["sh_size"]

                if not in_prog(vaddr, size, prog):
                    continue

                prog_offset = vaddr - prog["p_vaddr"]
                data = sec.data()

                chunk = Chunk(
                    paddr=paddr + prog_offset,
                    data=data,
                )
                chunks.append(chunk)

        if not chunks:
            raise Exception("no flashable segments found")

        # sort by physical address
        chunks.sort(key=lambda c: c.paddr)

        min_paddr = chunks[0].paddr
        last = chunks[-1]
        max_paddr = last.paddr + len(last.data)

        total_size = max_paddr - min_paddr
        data = bytearray(total_size)

        for c in chunks:
            offset = c.paddr - min_paddr
            data[offset:offset + len(c.data)] = c.data
        
        return Image(
            addr=min_paddr,
            vtor=vtor,
            data=bytes(data),
            version=read_fw_version(elf),
        )