"""Explicit allocation ownership for the installed PYNQ2.7 XRT backend."""
import ctypes


class _ImmediateRelease:
    def __init__(self, device):
        self.device = device

    def return_pointer(self, pointer):
        # PYNQ2.7's _xrt_allocate supplies (bo, ctypes_mapping, physical_address).
        # Use its own backend release routine with the complete mapped length.
        from pynq.pl_server.xrt_device import _free_bo
        bo, mapping, _ = pointer
        _free_bo(self.device, bo, ctypes.addressof(mapping), len(mapping))


def allocate_owned(nbytes):
    if not isinstance(nbytes, int) or nbytes <= 0:
        raise ValueError('Positive byte length required')
    import numpy as np
    from pynq import Device, allocate
    owner = allocate(shape=(nbytes,), dtype=np.uint8, cacheable=False,
                     cache=_ImmediateRelease(Device.active_device))
    if not getattr(owner, 'pointer', None):
        raise RuntimeError('Installed PYNQ allocation backend lacks expected ownership protocol')
    return owner
