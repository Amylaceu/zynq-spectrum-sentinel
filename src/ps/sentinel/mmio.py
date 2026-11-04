"""Bounded little-endian word access, with an explicit /dev/mem fallback."""
import mmap
import os
import struct


class DevMem:
    def __init__(self, address, length=4096, device='/dev/mem'):
        if not isinstance(address, int) or address < 0 or address % 4 or length < 4:
            raise ValueError('Invalid MMIO mapping')
        self.address, self.length = address, length
        aligned = address // mmap.ALLOCATIONGRANULARITY * mmap.ALLOCATIONGRANULARITY
        self._delta = address - aligned
        fd = os.open(device, os.O_RDWR | getattr(os,'O_SYNC',0))
        try:
            self._map = mmap.mmap(fd, length+self._delta, access=mmap.ACCESS_WRITE, offset=aligned)
        finally:
            os.close(fd)

    def _offset(self, offset):
        if not isinstance(offset, int) or offset < 0 or offset % 4 or offset+4 > self.length:
            raise ValueError('MMIO offset outside mapping or not word-aligned')
        return self._delta+offset

    def read(self, offset=0):
        return struct.unpack_from('<I', self._map, self._offset(offset))[0]

    def write(self, offset, value):
        if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
            raise ValueError('Expected uint32 register value')
        struct.pack_into('<I', self._map, self._offset(offset), value)

    def close(self):
        self._map.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def make_mmio(address, length=4096):
    try:
        from pynq import MMIO
    except ImportError:
        return DevMem(address, length)
    # Do not turn PYNQ permission/driver failures into a silent alternate path.
    return MMIO(address, length)
