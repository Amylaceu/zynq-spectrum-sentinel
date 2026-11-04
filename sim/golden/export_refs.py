"""Deterministic RTL reference vectors with explicit scalar/AXIS word layouts."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from .cfar import alpha_for_pfa, cfar, cluster, pack_targets
from .demod import am_demod, fm_demod, resample_to_48k
from .hoc import MOMENTS, moments_fixed, recommended_norm_shift
from .params import MOD_CLASSES
from .pfb import decimate, design_prototype, nco_mix, pfb_os2_fixed
from .render import render_frame
from .siggen import gen_mod, to_int16_iq
from .spectrum import DB_LOG2_Q16, DB_MANTISSA_LUT_Q16, fft_fixed, power_u32, to_db_q88, welch_update, window_coefs


def export(out):
    from PIL import Image
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = {}

    def record(path, **metadata):
        files[path.relative_to(out).as_posix()] = dict(
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size, **metadata)

    def save(name, a, bits=None):
        a = np.asarray(a)
        if not np.issubdtype(a.dtype, np.integer):
            raise ValueError("Reference transport must be integer")
        a = a.astype(a.dtype.newbyteorder("<"))
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path.with_suffix(".npy"), a, allow_pickle=False)
        record(path.with_suffix(".npy"), shape=list(a.shape), dtype=a.dtype.str)
        bits = a.dtype.itemsize * 8 if bits is None else bits
        mask = (1 << bits) - 1
        digits = (bits + 3) // 4
        path.with_suffix(".hex").write_text("".join(f"{int(v) & mask:0{digits}x}\n" for v in a.flat), encoding="ascii")
        record(path.with_suffix(".hex"), word_bits=bits, order="C scalar order, twos complement")

    def iq_save(name, words):
        words = np.asarray(words, dtype=np.int16).reshape(-1, 2)
        save(name + "_iq", words)
        packed = words[:, 0].astype(np.uint16).astype(np.uint32) | (words[:, 1].astype(np.uint16).astype(np.uint32) << 16)
        save(name + "_axis32", packed)

    rng = np.random.default_rng(20261102)
    sample = to_int16_iq(gen_mod("QPSK", 8192, 8, snr_db=18, seed=137))
    iq_save("spectrum/in", sample)
    window = window_coefs()
    save("spectrum/window", window.astype(np.int32), bits=18)
    coe = out / "spectrum/window.coe"
    coe.write_text("memory_initialization_radix=10;\nmemory_initialization_vector=\n" +
                   ",\n".join(str(int(v)) for v in window) + ";\n", encoding="ascii")
    record(coe)
    transformed, power, average, db = [], [], [], []
    state = np.zeros(2048, dtype=np.uint32)
    for frame in sample.reshape(4, 4096):
        x = fft_fixed(frame, window)
        p = np.fft.fftshift(power_u32(x))
        state = welch_update(state, p, 3)
        transformed.append(x); power.append(p); average.append(state); db.append(to_db_q88(state))
    save("spectrum/exp_fft", np.array(transformed), bits=24)
    save("spectrum/exp_power_shifted", np.array(power))
    save("spectrum/exp_welch", np.array(average))
    save("spectrum/exp_db", np.array(db))
    save("spectrum/log_mantissa_q16", DB_MANTISSA_LUT_Q16.astype(np.uint32))

    p = np.rint(rng.exponential(2**15, 2048)).astype(np.uint32)
    for start, stop in ((180, 183), (650, 654), (1500, 1502)):
        p[start:stop+1] = 2**24
    save("cfar/in_power", p)
    for mode in ("CA", "GO", "SO"):
        threshold, hit = cfar(p, mode, alpha_q88=alpha_for_pfa(1e-3, 16, mode))
        targets = cluster(hit, p)
        save(f"cfar/exp_thr_{mode.lower()}", threshold)
        save(f"cfar/exp_hit_{mode.lower()}", hit)
        save(f"cfar/exp_tgt_{mode.lower()}", np.frombuffer(pack_targets(targets), dtype=np.uint8))

    n = np.arange(16384)
    tones = sum(0.01 * np.exp(2j * np.pi * ch * n / 16) for ch in range(16))
    tones += 0.15 * gen_mod("QPSK", len(n), 32, seed=23) * np.exp(2j * np.pi * 3 * n / 16)
    pfb_input = to_int16_iq(tones, backoff_db=0)
    h = design_prototype()
    iq_save("pfb/in", pfb_input)
    save("pfb/prototype", h.astype(np.int32), bits=18)
    save("pfb/exp_channels", pfb_os2_fixed(pfb_input, h))

    fs_ch, residual, decimation = 3.84e6, 25000, 4
    mixed_input = to_int16_iq(gen_mod("QPSK", 8192, 16, fs=fs_ch, cfo_hz=residual, seed=79))
    iq_save("nco_capture/in", mixed_input)
    x = mixed_input.reshape(-1, 2)
    complex_input = x[:, 0].astype(float) + 1j * x[:, 1]
    captured = decimate(nco_mix(complex_input, residual, fs_ch), decimation)[128:1152]
    captured = np.clip(np.rint(np.column_stack((captured.real, captured.imag))), -32768, 32767).astype(np.int16)
    iq_save("nco_capture/exp", captured)

    shifts = []
    for mod in MOD_CLASSES:
        iq = to_int16_iq(gen_mod(mod, 1024, 8, fs=480000, seed=342), backoff_db=9)
        raw = moments_fixed(iq, recommended_norm_shift(1024))
        iq_save(f"hoc/in_{mod.lower().replace('-', '_')}", iq)
        acc = np.array([raw[f"M{p}{q}"] for p, q in MOMENTS], dtype=np.int64)
        save(f"hoc/exp_{mod.lower().replace('-', '_')}", acc, bits=48)
        shifts.append(raw["norm_shift"])
    for mode in ("FM", "AM-DSB"):
        y = 0.5 * gen_mod(mode, 16384, 8, fs=192000, seed=183)
        words = to_int16_iq(y, backoff_db=0)
        decoded = words.reshape(-1, 2)
        z = (decoded[:, 0].astype(float) + 1j * decoded[:, 1]) / 32768
        demodulated = fm_demod(z) if mode == "FM" else am_demod(z)
        audio = np.clip(np.rint(resample_to_48k(demodulated, 192000) * 32768), -32768, 32767).astype(np.int16)
        tag = mode.lower().replace("-", "_")
        iq_save(f"demod/in_{tag}", words)
        save(f"demod/exp_audio_{tag}", audio)

    dbfs = np.array(db[-1], dtype=np.int32) - int(round(10 * np.log10(2**30) * 256))
    threshold, hit = cfar(np.array(average[-1]), alpha_q88=alpha_for_pfa(1e-3))
    targets = cluster(hit, np.array(average[-1]))
    wf = rng.integers(0, 256, (200, 720), dtype=np.uint8)
    density = rng.integers(0, 256, (128, 360), dtype=np.uint8)
    ui = np.full((480, 800), 0xF81F, dtype=np.uint16)
    ui[370:400, 40:300] = 0x001F
    threshold_dbfs = to_db_q88(threshold).astype(np.int32) - int(round(10 * np.log10(2**30) * 256))
    save("render/in_spec", dbfs)
    save("render/in_peak", dbfs)
    save("render/in_threshold", threshold_dbfs)
    save("render/in_targets_bytes", np.frombuffer(pack_targets(targets), dtype=np.uint8))
    save("render/in_waterfall", wf)
    save("render/in_dpx", density)
    save("render/in_ui", ui)
    picture = render_frame(dbfs, dbfs, threshold_dbfs, targets, wf, density, ui)
    save("render/exp_frame", picture)
    rgb = np.stack((((picture >> 11) & 31) * 255 // 31, ((picture >> 5) & 63) * 255 // 63,
                    (picture & 31) * 255 // 31), axis=-1).astype(np.uint8)
    Image.fromarray(rgb).save(out / "render/exp_frame.png")
    record(out / "render/exp_frame.png")
    model_archive = Path(os.environ["XILINX_ROOT"]) / "Vivado/data/ip/xilinx/xfft_v9_1/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip"
    manifest = dict(schema=1, seed=20261102, files=files,
                    fft_backend=dict(name="AMD XFFT v9.1 Windows model", archive_sha256=hashlib.sha256(model_archive.read_bytes()).hexdigest()),
                    settings=dict(nfft=2048, spectrum_fft_width=16, fft_transport_width=24,
                                  fft_scale=[2, 2, 2, 2, 2, 1], spectrum_fft_order="natural",
                                  power_order="fftshifted", log2_db_q16=DB_LOG2_Q16,
                                  axis_iq="I bits15:0, Q bits31:16",
                                  cfar=dict(n=16, g=2, pfa=1e-3, dc_mask=3, gap=2),
                                  pfb=dict(m=16, d=8, taps=128, phase_endpoint="n*D", fft_width=24),
                                  capture=dict(fs=fs_ch, fcw=int(round(residual/fs_ch*2**32)), dec=decimation,
                                               discard_output_samples=128, length=1024,
                                               reference="phase-quantized NCO + floating FIR; P3 SQNR comparison"),
                                  hoc=dict(classes=MOD_CLASSES, shifts=shifts, moment_order=[f"M{p}{q}" for p, q in MOMENTS]),
                                  audio=dict(fs_in=192000, fs_out=48000, amplitude_scale=32768),
                                  display=dict(width=800, height=480, wf_head=0)))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    total = sum(item["size_bytes"] for item in files.values())
    print(f"P2.8 exported {len(files)} files, {total} bytes; manifest SHA256=" +
          hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
    if total >= 50 * 1024 * 1024:
        raise AssertionError("Reference set exceeds 50 MiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/reference")
    args = parser.parse_args()
    export(args.out)
