"""Seeded baseband generators and the explicit fixed-point noise contract.

Floating IQ is complex64. ADC conversion preserves requested backoff and maps
full scale to signed 12-bit values left-aligned in interleaved int16 words.
Noise samples are raw signed sums of twelve non-overlapping 12-bit PRBS words.
"""
import numpy as np
from scipy.signal import convolve

from .params import (
    FS_DEFAULT, LFSR_MASK, LFSR_UNIFORM_BITS, LFSR_DRAWS, LFSR_STRIDE,
    MOD_CLASSES, NOISE_AMP_BITS, NOISE_AMP_FRAC,
)


def rrc_taps(sps: int, beta: float = 0.35, span: int = 8) -> np.ndarray:
    """Unit-energy root-raised-cosine pulse, including removable singularities."""
    if sps < 2 or span <= 0 or span % 2 or not 0 <= beta <= 1:
        raise ValueError("RRC requires sps>=2, positive even span, 0<=beta<=1")
    t = np.arange(-span * sps // 2, span * sps // 2 + 1, dtype=float) / sps
    if beta == 0:
        h = np.sinc(t)
    else:
        h = np.empty_like(t)
        zero = np.isclose(t, 0)
        edge = np.isclose(np.abs(t), 1 / (4 * beta))
        regular = ~(zero | edge)
        u = t[regular]
        h[regular] = (np.sin(np.pi * u * (1 - beta)) + 4 * beta * u * np.cos(np.pi * u * (1 + beta))) / (np.pi * u * (1 - (4 * beta * u) ** 2))
        h[zero] = 1 + beta * (4 / np.pi - 1)
        h[edge] = beta / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
    return h / np.linalg.norm(h)


def _gray_decode(values):
    decoded = values.copy()
    shifted = values.copy()
    while np.any(shifted):
        shifted >>= 1
        decoded ^= shifted
    return decoded


def _shaped(symbols, n, sps, beta):
    pulse = rrc_taps(sps, beta)
    up = np.zeros(len(symbols) * sps, dtype=complex)
    up[::sps] = symbols
    # Four prefix/suffix symbols plus the pulse group delay remove transients.
    return convolve(up, pulse, mode="full")[8 * sps:8 * sps + n]


def gen_mod(mod: str, n: int, sps: int, fs: float = FS_DEFAULT,
            snr_db: float = None, cfo_hz: float = 0.0, phase: float = 0.0,
            beta: float = 0.35, iq_imb_db: float = 0.0, iq_imb_deg: float = 0.0,
            multipath: list = None, seed: int = 0) -> np.ndarray:
    """Generate unit-power IQ before noise; snr_db is occupied-bandwidth SNR.

    Multipath is a complex FIR tap list, or a list of (integer delay, gain).
    The final noiseless waveform is normalized after impairments. SNR uses
    total complex noise power Pn_full=Ps/(10**(SNR/10))*fs/occupied_bw.
    """
    if mod not in MOD_CLASSES or n < 1 or not isinstance(sps, (int, np.integer)) or sps < 2 or fs <= 0:
        raise ValueError("Invalid modulation, sample count, sps, or sample rate")
    if not 0 <= beta <= 1 or not np.isfinite([fs, cfo_hz, phase, iq_imb_db, iq_imb_deg]).all():
        raise ValueError("Invalid shaping or impairment parameter")
    rng = np.random.default_rng(seed)
    count = (n + sps - 1) // sps + 8
    bandwidth = min(fs, fs / sps * (1 + beta))
    if mod in ("BPSK", "QPSK", "8PSK"):
        order = {"BPSK": 2, "QPSK": 4, "8PSK": 8}[mod]
        index = _gray_decode(rng.integers(order, size=count))
        rotation = np.pi / 4 if mod == "QPSK" else 0
        x = _shaped(np.exp(1j * (2 * np.pi * index / order + rotation)), n, sps, beta)
    elif mod in ("16QAM", "64QAM"):
        side = 4 if mod == "16QAM" else 8
        i = 2 * _gray_decode(rng.integers(side, size=count)) - (side - 1)
        q = 2 * _gray_decode(rng.integers(side, size=count)) - (side - 1)
        x = _shaped((i + 1j * q) / np.sqrt(2 * (side * side - 1) / 3), n, sps, beta)
    elif mod == "OOK":
        x = _shaped(rng.integers(2, size=count).astype(float), n, sps, beta)
    elif mod in ("2FSK", "GFSK"):
        data = np.repeat(2 * rng.integers(2, size=count) - 1, sps).astype(float)
        h = 1.0 if mod == "2FSK" else 0.5
        if mod == "GFSK":
            axis = np.arange(-2 * sps, 2 * sps + 1)
            sigma = np.sqrt(np.log(2)) * sps / (2 * np.pi * 0.5)
            pulse = np.exp(-0.5 * (axis / sigma) ** 2)
            data = convolve(data, pulse / pulse.sum(), mode="same")
        angle = np.cumsum(np.pi * h * data / sps)
        x = np.exp(1j * angle[4 * sps:4 * sps + n])
        bandwidth = min(fs, (1 + h) * fs / sps)
    else:
        time = np.arange(n) / fs
        frequencies = rng.uniform(300, 3000, 5)
        message = np.sin(2 * np.pi * time[:, None] * frequencies + rng.uniform(0, 2 * np.pi, 5)).sum(axis=1) / 5
        if mod == "AM-DSB":
            x = (1 + rng.uniform(0.5, 0.9) * message).astype(complex)
            bandwidth = min(fs, 6000.0)
        else:
            deviation = rng.uniform(5000, 75000)
            x = np.exp(1j * np.cumsum(2 * np.pi * deviation * message / fs))
            bandwidth = min(fs, 2 * (deviation + 3000))
    if multipath is not None:
        if len(multipath) == 0:
            raise ValueError("Empty multipath channel")
        if isinstance(multipath[0], (tuple, list)):
            delays = [pair[0] for pair in multipath]
            if any(not isinstance(d, (int, np.integer)) or d < 0 for d in delays):
                raise ValueError("Channel delays must be nonnegative integers")
            taps = np.zeros(max(delays) + 1, dtype=complex)
            for delay, gain in multipath:
                taps[delay] += gain
        else:
            taps = np.asarray(multipath, dtype=complex)
        x = convolve(x, taps, mode="full")[:n]
    # Gain imbalance is relative I/Q amplitude in dB; phase imbalance is quadrature error.
    gain = 10 ** (iq_imb_db / 40)
    angle = np.deg2rad(iq_imb_deg)
    x = gain * x.real + 1j * (x.imag * np.cos(angle) + x.real * np.sin(angle)) / gain
    power = np.mean(np.abs(x) ** 2)
    if not np.isfinite(power) or power <= 0:
        raise ValueError("Channel has zero or nonfinite power")
    x /= np.sqrt(power)
    x *= np.exp(1j * (phase + 2 * np.pi * cfo_hz * np.arange(n) / fs))
    if snr_db is not None:
        if not np.isfinite(snr_db):
            raise ValueError("SNR must be finite or None")
        variance = fs / bandwidth / (10 ** (snr_db / 10))
        x += np.sqrt(variance / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return np.asarray(x, dtype=np.complex64)


def gen_wideband(signals: list[dict], n: int, fs: float, noise_dbfs: float, seed: int) -> np.ndarray:
    """Sum signals with f_off (Hz) and amplitude or power_dbfs (unit complex FS).

    noise_dbfs is total complex white noise power over the full sample bandwidth.
    Remaining dictionary fields are gen_mod parameters; each signal may set seed.
    """
    if n < 1 or fs <= 0 or not np.isfinite(noise_dbfs):
        raise ValueError("Invalid wideband dimensions or noise power")
    rng = np.random.default_rng(seed)
    x = np.zeros(n, dtype=np.complex128)
    for signal in signals:
        args = dict(signal)
        offset = float(args.pop("f_off", 0))
        amplitude = args.pop("amplitude", None)
        dbfs = args.pop("power_dbfs", None)
        if amplitude is not None and dbfs is not None:
            raise ValueError("Choose amplitude or power_dbfs, not both")
        amplitude = 10 ** (float(dbfs) / 20) if dbfs is not None else (1 if amplitude is None else amplitude)
        args.setdefault("seed", int(rng.integers(0, 2**32)))
        x += amplitude * gen_mod(n=n, fs=fs, **args) * np.exp(2j * np.pi * offset * np.arange(n) / fs)
    variance = 10 ** (noise_dbfs / 10)
    x += np.sqrt(variance / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return x.astype(np.complex64)


def to_int16_iq(x: np.ndarray, backoff_db: float = 12.0) -> np.ndarray:
    """Quantize signed 12-bit ADC samples and left-shift four bits, saturating."""
    x = np.asarray(x)
    if x.ndim != 1 or not np.isfinite(x).all() or not np.isfinite(backoff_db):
        raise ValueError("Expected finite one-dimensional IQ")
    scale = 2048 * 10 ** (-backoff_db / 20)
    out = np.empty(2 * x.size, dtype=np.int16)
    out[0::2] = (np.clip(np.rint(x.real * scale), -2048, 2047).astype(np.int32) << 4).astype(np.int16)
    out[1::2] = (np.clip(np.rint(x.imag * scale), -2048, 2047).astype(np.int32) << 4).astype(np.int16)
    return out


def _iq_words(words):
    words = np.asarray(words)
    if words.ndim != 1 or words.dtype != np.int16 or words.size % 2:
        raise ValueError("Expected even-length interleaved int16 IQ")
    return words


def from_int16_iq(b: np.ndarray) -> np.ndarray:
    """Decode normalized full-scale IQ; the original backoff is preserved."""
    b = _iq_words(b)
    return (b[0::2].astype(np.float32) + 1j * b[1::2].astype(np.float32)) / 32768


def lfsr_gauss_fixed(n: int, seed_i: int, seed_q: int) -> np.ndarray:
    """Interleaved int16 PRBS sums; advance before reading, reset by both seeds.

    For each uniform word advance LFSR_STRIDE=12 bit steps, then take bits 11:0.
    Sum twelve words, subtract 12*4095/2=24570. I and Q have separate states.
    """
    if n < 0 or any(not 0 < s < 2**32 for s in (seed_i, seed_q)):
        raise ValueError("Noise length must be nonnegative and seeds nonzero uint32")
    result = np.empty(2 * n, dtype=np.int16)
    mask = (1 << LFSR_UNIFORM_BITS) - 1
    offset = LFSR_DRAWS * mask // 2
    for lane, state in enumerate((int(seed_i), int(seed_q))):
        for sample in range(n):
            total = 0
            for _ in range(LFSR_DRAWS):
                for _ in range(LFSR_STRIDE):
                    state = (state >> 1) ^ (LFSR_MASK if state & 1 else 0)
                total += state & mask
            result[2 * sample + lane] = total - offset
    return result


def add_noise_fixed(iq_int16: np.ndarray, noise_amp: int, seed_i: int, seed_q: int) -> np.ndarray:
    words = _iq_words(iq_int16)
    if not isinstance(noise_amp, (int, np.integer)) or not 0 <= noise_amp < 2**NOISE_AMP_BITS:
        raise ValueError("NOISE_AMP must be unsigned 16-bit Q1.15")
    noise = lfsr_gauss_fixed(words.size // 2, seed_i, seed_q).astype(np.int64)
    mixed = words.astype(np.int64) + ((noise * int(noise_amp)) >> NOISE_AMP_FRAC)
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def noise_amp_for_snr(sig_power_lsb2: float, snr_db: float, occ_bw_hz: float, fs: float) -> int:
    if not np.isfinite([sig_power_lsb2, snr_db, occ_bw_hz, fs]).all() or sig_power_lsb2 < 0 or not 0 < occ_bw_hz <= fs:
        raise ValueError("Invalid signal power or occupied bandwidth")
    variance_per_lane = LFSR_DRAWS * ((1 << (2 * LFSR_UNIFORM_BITS)) - 1) / 12
    full_noise_power = sig_power_lsb2 / 10 ** (snr_db / 10) * fs / occ_bw_hz
    amplitude = int(np.rint((1 << NOISE_AMP_FRAC) * np.sqrt(full_noise_power / (2 * variance_per_lane))))
    if amplitude >= 2**NOISE_AMP_BITS:
        raise ValueError("Requested SNR exceeds NOISE_AMP range; reduce input signal power")
    return amplitude
