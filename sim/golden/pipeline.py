"""Offline reference chain and reproducible four-signal demonstration."""

import argparse
import json
from pathlib import Path

import numpy as np

from .cfar import alpha_for_pfa, cfar, cluster
from .hoc import features_from_moments, moments_fixed, recommended_norm_shift
from .params import CAPTURE_LEN, FS_DEFAULT, NFFT
from .pfb import decimate, design_prototype, nco_mix, pfb_os2_fixed, select_channel
from .render import render_frame
from .siggen import gen_wideband, to_int16_iq
from .spectrum import fft_fixed, power_u32, to_db_q88, welch_update, window_coefs


def run(iq_int16, cfg=None):
    cfg = {} if cfg is None else cfg
    words = np.asarray(iq_int16)
    if words.dtype != np.int16 or words.ndim != 1 or words.size % 2:
        raise ValueError("Expected interleaved int16 IQ")
    fs, nfft = float(cfg.get("fs", FS_DEFAULT)), int(cfg.get("nfft", NFFT))
    count = words.size // (2 * nfft)
    if count < 1:
        raise ValueError("Need at least one FFT frame")
    n, g, mode = int(cfg.get("cfar_n", 16)), int(cfg.get("cfar_g", 2)), cfg.get("cfar_mode", "CA")
    alpha = alpha_for_pfa(float(cfg.get("pfa", 1e-3)), n, mode)
    w = window_coefs(n=nfft)
    averaged = np.zeros(nfft, dtype=np.uint32)
    spectra, powers, thresholds, targets = [], [], [], []
    for f in range(count):
        transformed = fft_fixed(words[2 * f * nfft:2 * (f + 1) * nfft], w)
        p = np.fft.fftshift(power_u32(transformed))
        averaged = welch_update(averaged, p, int(cfg.get("welch_shift", 3)))
        thr, hit = cfar(averaged, mode, n, g, alpha, int(cfg.get("dc_mask", 3)))
        powers.append(averaged.copy())
        spectra.append(to_db_q88(averaged))
        thresholds.append(thr)
        targets.append(cluster(hit, averaged, int(cfg.get("cluster_gap", 2)), 32))
    captures, features, labels = [], [], []
    if cfg.get("capture", True) and len(targets[-1]):
        channels = pfb_os2_fixed(words, design_prototype())
        for target in targets[-1]:
            center_bin = (int(target["start"]) + int(target["stop"])) / 2
            frequency = (center_bin - nfft // 2) * fs / nfft
            ch, residual = select_channel(frequency, fs)
            sample = channels[16:, ch, 0].astype(float) + 1j * channels[16:, ch, 1].astype(float)
            mixed = nco_mix(sample, residual, fs / 8)
            reduced = decimate(mixed, int(cfg.get("capture_dec", 1)))
            sample = reduced[128:128 + CAPTURE_LEN]
            if len(sample) < CAPTURE_LEN:
                continue
            # Hardware HOC contract requires DC removal; retain ADC integer scale.
            sample = sample - np.mean(sample)
            iq = np.clip(np.rint(np.column_stack((sample.real, sample.imag))), -32768, 32767).astype(np.int16)
            shift = recommended_norm_shift(len(iq), int(np.max(np.abs(iq.astype(np.int32)))))
            hoc = features_from_moments(moments_fixed(iq, shift))
            captures.append({"channel": ch, "frequency_hz": frequency, "iq": iq,
                             "fs": fs / 8 / int(cfg.get("capture_dec", 1)), "norm_shift": shift})
            features.append(hoc)
            classify = cfg.get("classify")
            labels.append(classify(iq, hoc) if classify is not None else None)
    return dict(spec_frames=np.array(spectra), power_frames=np.array(powers),
                threshold_frames=np.array(thresholds), targets_per_frame=targets,
                captures=captures, hoc=features, labels=labels, fs=fs, nfft=nfft)


def demo(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fs = FS_DEFAULT
    signals = [
        dict(mod="QPSK", sps=31, f_off=3e6, power_dbfs=-18),
        dict(mod="2FSK", sps=64, f_off=-5e6, power_dbfs=-18),
        dict(mod="FM", sps=32, f_off=8e6, power_dbfs=-18),
        dict(mod="16QAM", sps=31, f_off=-9e6, power_dbfs=-18),
    ]
    # 15 dB in the QPSK occupied bandwidth; all four have equal total power.
    bandwidth = fs / 31 * 1.35
    noise_dbfs = -18 - 15 + 10 * np.log10(fs / bandwidth)
    x = gen_wideband(signals, 131072, fs, noise_dbfs, seed=20261102)
    cfg = dict(fs=fs, cfar_n=128, cfar_g=48, pfa=1e-3)
    result = run(to_int16_iq(x, backoff_db=0), cfg)
    last = result["targets_per_frame"][-1]
    rows = []
    for target in last:
        record = {name: int(target[name]) for name in last.dtype.names}
        record["center_hz"] = ((record["start"] + record["stop"]) / 2 - 1024) * fs / 2048
        rows.append(record)
    payload = dict(targets=rows, truth_centers_hz=[-9e6, -5e6, 3e6, 8e6], config=cfg,
                   classifier="not_trained", labels=result["labels"],
                   noise_reference="15 dB within QPSK occupied bandwidth; not equal per-class bandwidth SNR")
    (out / "targets.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    offset = int(round(10 * np.log10(2**30) * 256))
    spec = result["spec_frames"].astype(np.int32) - offset
    thr_db = to_db_q88(result["threshold_frames"][-1]).astype(np.int32) - offset
    frequencies = (np.arange(2048) - 1024) * fs / 2048 / 1e6
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(frequencies, spec[-1] / 256, label="Welch spectrum")
    ax.plot(frequencies, thr_db / 256, color="red", linewidth=.7, label="CA-CFAR threshold")
    for t in rows:
        ax.axvspan(frequencies[t["start"]], frequencies[t["stop"]], color="green", alpha=.18)
    ax.set(xlabel="Frequency offset (MHz)", ylabel="Power / bin (dBFS)", ylim=(-85, -25))
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(out / "spectrum.png", dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.imshow(spec / 256, aspect="auto", origin="lower", extent=[-fs/2e6, fs/2e6, 0, len(spec)],
              vmin=-85, vmax=-30, cmap="turbo")
    ax.set(xlabel="Frequency offset (MHz)", ylabel="FFT frame")
    fig.tight_layout(); fig.savefig(out / "waterfall.png", dpi=150); plt.close(fig)
    fig, axes = plt.subplots(1, max(1, len(result["captures"])), figsize=(12, 3), squeeze=False)
    for ax, captured in zip(axes[0], result["captures"]):
        iq = captured["iq"]
        ax.scatter(iq[:, 0], iq[:, 1], s=2)
        ax.set_title(f'{captured["frequency_hz"]/1e6:+.3f} MHz (unclassified)')
        ax.set_aspect("equal", adjustable="datalim"); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(out / "constellations.png", dpi=150); plt.close(fig)
    edges = np.arange(721) * 2048 // 720
    display_db = np.array([[max(row[edges[c]:edges[c+1]]) for c in range(720)] for row in spec])
    wf = np.clip((display_db + 85 * 256) * 255 // (55 * 256), 0, 255).astype(np.uint8)
    wf = np.tile(wf[::-1], ((200 + len(wf) - 1) // len(wf), 1))[:200]
    frame = render_frame(spec[-1], np.max(spec, axis=0), thr_db, last, wf, None, None,
                         dict(db_min_q88=-85 * 256, db_max_q88=-30 * 256))
    rgb = np.stack((((frame >> 11) & 31) * 255 // 31,
                    ((frame >> 5) & 63) * 255 // 63, (frame & 31) * 255 // 31), axis=-1).astype(np.uint8)
    Image.fromarray(rgb).save(out / "frame_ref.png")
    print(json.dumps(payload, indent=2))
    truth = np.array(payload["truth_centers_hz"])
    measured = np.array([record["center_hz"] for record in rows])
    if len(measured) != 4 or np.any(np.abs(np.sort(measured) - truth) > fs / 2048):
        raise AssertionError("Four-target center-frequency acceptance failed")
    print("P2.7_PASS four targets, centers within one FFT bin; classifier not trained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--out", default="sim/results/p2_demo")
    args = parser.parse_args()
    if not args.demo:
        parser.error("Use --demo to run the deterministic offline scenario")
    demo(args.out)
