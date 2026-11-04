"""Small ctypes binding to the locally installed AMD XFFT bit-accurate model.

AMD binaries remain in the ignored build directory; they are not redistributed.
The ABI below follows the installed xfft_v9_1_bitacc_cmodel.h, including SSR.
"""

import ctypes as ct
import os
from pathlib import Path
import zipfile

import numpy as np


class _Generics(ct.Structure):
    _fields_ = [(name, ct.c_int) for name in (
        "nfft", "arch", "runtime_nfft", "floating", "input_width", "twiddle_width",
        "scaling", "bfp", "rounding", "ssr", "inverse")]


class _Inputs(ct.Structure):
    _fields_ = [("nfft", ct.c_int), ("re", ct.POINTER(ct.c_double)),
                ("re_size", ct.c_int), ("im", ct.POINTER(ct.c_double)),
                ("im_size", ct.c_int), ("schedule", ct.POINTER(ct.c_int)),
                ("schedule_size", ct.c_int), ("direction", ct.c_int)]


class _Outputs(ct.Structure):
    _fields_ = [("re", ct.POINTER(ct.c_double)), ("re_size", ct.c_int),
                ("im", ct.POINTER(ct.c_double)), ("im_size", ct.c_int),
                ("exponent", ct.c_int), ("overflow", ct.c_int)]


_dll = None
_dll_dir = None


def _load():
    global _dll, _dll_dir
    if _dll is not None:
        return _dll
    if os.name != "nt":
        raise RuntimeError("This binding currently supports the installed Windows x64 model")
    repo = Path(__file__).resolve().parents[2]
    root = os.environ.get("XILINX_ROOT")
    if not root:
        raise RuntimeError("Initialize tools/env.ps1 or set XILINX_ROOT to the AMD version directory")
    archive = Path(root) / "Vivado/data/ip/xilinx/xfft_v9_1/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip"
    if not archive.is_file():
        raise FileNotFoundError(archive)
    cache = repo / "build/work/xfft_cmodel"
    cache.mkdir(parents=True, exist_ok=True)
    # Only known flat files from this local tool archive are used.
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if entry.filename == Path(entry.filename).name and entry.filename.endswith(".dll"):
                target = cache / entry.filename
                if not target.exists() or target.stat().st_size != entry.file_size:
                    target.write_bytes(z.read(entry))
    _dll_dir = os.add_dll_directory(str(cache))
    dll = ct.CDLL(str(cache / "libIp_xfft_v9_1_bitacc_cmodel.dll"))
    dll.xilinx_ip_xfft_v9_1_create_state.argtypes = [_Generics]
    dll.xilinx_ip_xfft_v9_1_create_state.restype = ct.c_void_p
    dll.xilinx_ip_xfft_v9_1_destroy_state.argtypes = [ct.c_void_p]
    dll.xilinx_ip_xfft_v9_1_destroy_state.restype = None
    dll.xilinx_ip_xfft_v9_1_bitacc_simulate.argtypes = [ct.c_void_p, _Inputs, ct.POINTER(_Outputs)]
    dll.xilinx_ip_xfft_v9_1_bitacc_simulate.restype = ct.c_int
    _dll = dll
    return dll


def fft_integer(iq, width=16):
    """Natural-order forward FFT, native signed integer output, scale 1/N.

    Pipelined architecture, 18-bit twiddles, convergent rounding, no BFP.
    Return N x 2 int64 containing exact integer output words. Overflow is fatal.
    """
    x = np.asarray(iq)
    if x.ndim != 2 or x.shape[1] != 2 or not np.issubdtype(x.dtype, np.integer):
        raise ValueError("Expected N x 2 integer IQ")
    n = len(x)
    if n < 8 or n > 65536 or n & (n - 1):
        raise ValueError("FFT length must be a power of two in [8, 65536]")
    if not isinstance(width, int) or not 8 <= width <= 32:
        raise ValueError("FFT width must be in [8,32]")
    scale = 1 << (width - 1)
    if np.any(x < -scale) or np.any(x >= scale):
        raise ValueError(f"FFT input outside signed {width}-bit range")
    logn = n.bit_length() - 1
    shifts = [2] * (logn // 2) + ([1] if logn % 2 else [])
    schedule = (ct.c_int * len(shifts))(*shifts)
    re = np.ascontiguousarray(x[:, 0] / scale, dtype=np.float64)
    im = np.ascontiguousarray(x[:, 1] / scale, dtype=np.float64)
    out_re, out_im = np.zeros(n), np.zeros(n)
    dp = lambda a: a.ctypes.data_as(ct.POINTER(ct.c_double))
    inputs = _Inputs(logn, dp(re), n, dp(im), n, schedule, len(shifts), 1)
    outputs = _Outputs(dp(out_re), n, dp(out_im), n, 0, 0)
    dll = _load()
    state = dll.xilinx_ip_xfft_v9_1_create_state(
        _Generics(logn, 3, 0, 0, width, 18, 1, 0, 1, 1, 0))
    if not state:
        raise RuntimeError("AMD FFT model state creation failed")
    try:
        code = dll.xilinx_ip_xfft_v9_1_bitacc_simulate(state, inputs, ct.byref(outputs))
        if code or outputs.re_size != n or outputs.im_size != n:
            raise RuntimeError(f"AMD FFT simulation failed: status={code}")
        if outputs.overflow:
            raise OverflowError("AMD FFT model reports arithmetic overflow")
        words = np.column_stack((out_re, out_im)) * scale
        if not np.all(words == np.rint(words)):
            raise RuntimeError("Unexpected FFT model output quantization")
        return words.astype(np.int64)
    finally:
        dll.xilinx_ip_xfft_v9_1_destroy_state(state)


def fft_i16(iq):
    """Native signed 16-bit FFT wrapper used by the spectrum front end."""
    return fft_integer(iq, width=16)
