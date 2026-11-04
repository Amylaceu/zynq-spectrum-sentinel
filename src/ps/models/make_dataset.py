"""Stratified, deterministic AMC data with ADC words and fixed HOC features."""

import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import time

import numpy as np

from sim.golden.hoc import features_from_moments, moments_fixed, recommended_norm_shift
from sim.golden.params import MOD_CLASSES
from sim.golden.siggen import gen_mod, to_int16_iq


SNRS = list(range(-4, 21, 2))
SEED = 20261102
# This is the capture rate AFTER PFB and DEC=8, not the wideband RF ADC rate.
CAPTURE_FS = 480000


def _group(task):
    label, snr_index, count = task
    iq = np.empty((count, 2, 1024), dtype=np.int16)
    hoc = np.empty((count, 8), dtype=np.float32)
    shifts = np.empty(count, dtype=np.uint8)
    ids = np.empty(count, dtype=np.uint32)
    clipping = 0
    for i in range(count):
        seed = SEED + label * 100000000 + snr_index * 100000 + i
        rng = np.random.default_rng(seed)
        sps = int(rng.integers(4, 17))
        paths = None
        if rng.random() < 0.5:
            a, b = (rng.normal(size=2) + 1j * rng.normal(size=2)) / np.sqrt(2)
            paths = [(0, a), (int(rng.integers(1, sps + 1)), 0.5 * b)]
        x = gen_mod(MOD_CLASSES[label], 1024, sps, fs=CAPTURE_FS, snr_db=SNRS[snr_index],
                    cfo_hz=rng.uniform(-0.02, 0.02) * CAPTURE_FS / sps,
                    phase=rng.uniform(0, 2 * np.pi), iq_imb_db=rng.uniform(-1, 1),
                    iq_imb_deg=rng.uniform(-5, 5), multipath=paths, seed=seed)
        # AGC on total noisy IQ prevents low-SNR samples being ADC-clipped merely
        # because noise variance rises. Signal/noise ratio is unchanged by AGC.
        x /= np.sqrt(np.mean(np.abs(x)**2))
        words = to_int16_iq(x, backoff_db=12).reshape(1024, 2)
        clipping += int(np.any((words == -32768) | (words == 32752)))
        centered = np.clip(np.rint(words.astype(float) - words.mean(axis=0)), -32768, 32767).astype(np.int16)
        shift = recommended_norm_shift(1024, int(np.max(np.abs(centered.astype(np.int32)))))
        fixed = moments_fixed(centered, shift)
        iq[i] = words.T
        hoc[i] = features_from_moments(fixed)
        shifts[i], ids[i] = shift, seed
    return label, snr_index, iq, hoc, shifts, ids, clipping


def make_dataset(out, per_cell=2000, workers=4):
    if per_cell < 10 or per_cell % 10 or per_cell > 10000:
        raise ValueError("per-cell must be a multiple of 10 in [10,10000]")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if any((out / f"amc_v1_{split}.npz").exists() for split in ("train", "val", "test")):
        raise FileExistsError("Dataset output already exists; choose a new output directory")
    work = out / "_generation"
    work.mkdir(exist_ok=True)
    total = len(MOD_CLASSES) * len(SNRS) * per_cell
    arrays = {
        "iq": np.lib.format.open_memmap(work / "iq.npy", mode="w+", dtype=np.int16, shape=(total, 2, 1024)),
        "hoc": np.lib.format.open_memmap(work / "hoc.npy", mode="w+", dtype=np.float32, shape=(total, 8)),
        "norm_shift": np.lib.format.open_memmap(work / "shift.npy", mode="w+", dtype=np.uint8, shape=(total,)),
        "sample_id": np.lib.format.open_memmap(work / "id.npy", mode="w+", dtype=np.uint32, shape=(total,)),
        "label": np.empty(total, dtype=np.int64), "snr": np.empty(total, dtype=np.int8),
    }
    tasks = [(c, s, per_cell) for c in range(10) for s in range(13)]
    start, clipped = time.monotonic(), 0
    # spawn gives isolated generators; no global random state is shared.
    with mp.get_context("spawn").Pool(workers) as pool:
        for done, (c, s, iq, hoc, shifts, ids, clips) in enumerate(pool.imap_unordered(_group, tasks), 1):
            begin = (c * 13 + s) * per_cell
            section = slice(begin, begin + per_cell)
            arrays["iq"][section], arrays["hoc"][section] = iq, hoc
            arrays["norm_shift"][section], arrays["sample_id"][section] = shifts, ids
            arrays["label"][section], arrays["snr"][section] = c, SNRS[s]
            clipped += clips
            print(f"generation {done}/130 groups; {done*per_cell}/{total} samples; elapsed={time.monotonic()-start:.1f}s", flush=True)
    if not np.all(np.isfinite(arrays["hoc"])) or len(np.unique(arrays["sample_id"])) != total:
        raise AssertionError("Nonfinite features or duplicate sample identifiers")
    splits = {name: [] for name in ("train", "val", "test")}
    train_count, val_count = per_cell * 8 // 10, per_cell // 10
    for cell in range(130):
        indices = np.random.default_rng(SEED + cell).permutation(per_cell) + cell * per_cell
        splits["train"].append(indices[:train_count])
        splits["val"].append(indices[train_count:train_count + val_count])
        splits["test"].append(indices[train_count + val_count:])
    manifest = dict(schema=1, per_cell=per_cell, total=total, classes=MOD_CLASSES, snrs=SNRS,
                    fs=CAPTURE_FS, capture_len=1024, seed=SEED, clipped_segments=clipped,
                    signal_model="gen_mod in-band SNR; random sps/CFO/phase/IQ/two-path; total-power AGC then ADC12",
                    hoc_preprocess="round(iq-mean), measured-peak normalization, signed48 exact moments",
                    splits={}, sources={})
    for name, parts in splits.items():
        idx = np.concatenate(parts)
        idx = np.random.default_rng(SEED).permutation(idx)
        path = out / f"amc_v1_{name}.npz"
        temp = path.with_suffix(".npz.tmp")
        with temp.open("wb") as stream:
            np.savez(stream, **{key: value[idx] for key, value in arrays.items()})
        temp.replace(path)
        manifest["splits"][name] = dict(count=len(idx), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        print(f"saved {name}: {len(idx)} samples", flush=True)
    repo = Path(__file__).resolve().parents[3]
    for rel in ("sim/golden/siggen.py", "sim/golden/hoc.py", "src/ps/models/make_dataset.py"):
        manifest["sources"][rel] = hashlib.sha256((repo / rel).read_bytes()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DATASET_COMPLETE total={total} clipped_segments={clipped} elapsed={time.monotonic()-start:.1f}s", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/synthetic/amc_v1")
    p.add_argument("--per-cell", type=int, default=2000)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    make_dataset(a.out, a.per_cell, a.workers)
