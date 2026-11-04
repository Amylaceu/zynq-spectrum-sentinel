"""CPU training with stratified validation; hold-out test used only at the end."""

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset, Subset

from .amc_net import AMCNet


def loader(path, batch_size, shuffle=False):
    with np.load(path, allow_pickle=False) as a:
        tensors = [torch.from_numpy(a[key]) for key in ("iq", "hoc", "label", "snr")]
    return DataLoader(TensorDataset(*tensors), batch_size=batch_size, shuffle=shuffle, num_workers=0)


def evaluate(model, batches):
    model.eval()
    predictions, truth, snrs = [], [], []
    with torch.inference_mode():
        for iq, hoc, target, snr in batches:
            predictions.append(model(iq, hoc).argmax(dim=1).numpy())
            truth.append(target.numpy()); snrs.append(snr.numpy())
    pred, labels, snrs = map(np.concatenate, (predictions, truth, snrs))
    accuracy = {str(int(s)): float(np.mean(pred[snrs == s] == labels[snrs == s])) for s in np.unique(snrs)}
    confusion = np.zeros((10, 10), dtype=np.int64)
    np.add.at(confusion, (labels, pred), 1)
    return float(np.mean(pred == labels)), accuracy, confusion


def train(data, out, epochs=40, batch_size=256, lr=1e-3, use_hoc=True, threads=8, smoke=False, input_mode="raw", curriculum_epochs=0, phase_augment=False):
    torch.set_num_threads(threads)
    random.seed(20261102); np.random.seed(20261102); torch.manual_seed(20261102)
    data, out = Path(data), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data / "manifest.json").read_text())
    if not smoke and manifest["per_cell"] != 2000:
        raise ValueError("Production training requires exactly 2000 segments per class/SNR")
    if smoke and manifest["per_cell"] >= 2000:
        raise ValueError("Use smoke only on a small, separate test dataset")
    train_batches = loader(data / "amc_v1_train.npz", batch_size, shuffle=True)
    if not 0 <= curriculum_epochs < epochs:
        raise ValueError("Curriculum must leave at least one all-SNR epoch")
    high_snr = torch.nonzero(train_batches.dataset.tensors[3] >= 8).flatten().tolist()
    curriculum_batches = DataLoader(Subset(train_batches.dataset, high_snr), batch_size=batch_size,
                                    shuffle=True, num_workers=0)
    validation = loader(data / "amc_v1_val.npz", batch_size)
    model = AMCNet(use_hoc=use_hoc, input_mode=input_mode)
    hoc = train_batches.dataset.tensors[1].float().clamp_min(0).log1p()
    model.hoc_mean.copy_(hoc.mean(dim=0)); model.hoc_std.copy_(hoc.std(dim=0).clamp_min(1e-4))
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_fn, best = nn.CrossEntropyLoss(), -1.0
    prefix = "amc_v1" if use_hoc else "cnn_only"
    checkpoint = out / f"{prefix}_fp32.pt"
    history, start = [], time.monotonic()
    for epoch in range(epochs):
        model.train(); total_loss, count = 0.0, 0
        batches = curriculum_batches if epoch < curriculum_epochs else train_batches
        for iq, features, labels, _ in batches:
            if phase_augment:
                angle = torch.rand(len(iq), 1) * (2 * np.pi)
                real, imag = iq[:, 0].float(), iq[:, 1].float()
                iq = torch.stack((real * angle.cos() - imag * angle.sin(),
                                  real * angle.sin() + imag * angle.cos()), dim=1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(iq, features), labels)
            loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            total_loss += loss.item() * len(labels); count += len(labels)
        scheduler.step()
        val_accuracy, val_curve, _ = evaluate(model, validation)
        row = dict(epoch=epoch + 1, loss=total_loss/count, val_accuracy=val_accuracy,
                   val_snr10=val_curve["10"], curriculum=epoch < curriculum_epochs,
                   elapsed_s=time.monotonic() - start)
        history.append(row)
        print(json.dumps(row), flush=True)
        (out / f"{prefix}_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        if val_accuracy > best:
            best = val_accuracy
            torch.save(dict(state_dict=model.state_dict(), use_hoc=use_hoc, classes=manifest["classes"],
                            fs=manifest["fs"], epoch=epoch + 1, val_accuracy=best, smoke=smoke,
                            input_mode=input_mode, curriculum_epochs=curriculum_epochs,
                            phase_augment=phase_augment), checkpoint)
    chosen = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(chosen["state_dict"])
    testing = loader(data / "amc_v1_test.npz", batch_size)
    overall, curve, confusion = evaluate(model, testing)
    result = dict(overall_accuracy=overall, accuracy_vs_snr=curve, confusion=confusion.tolist(),
                  best_epoch=chosen["epoch"], use_hoc=use_hoc, smoke=smoke, input_mode=input_mode,
                  snr10_pass=curve["10"] >= .88, quantization="not_yet_exported",
                  curriculum_epochs=curriculum_epochs, phase_augment=phase_augment,
                  elapsed_s=time.monotonic()-start)
    (out / f"{prefix}_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    if smoke:
        print("SMOKE_ONLY: training I/O passed; no accuracy acceptance claimed", flush=True)
    elif use_hoc and not result["snr10_pass"]:
        raise RuntimeError(f"P2.9 accuracy acceptance failed: SNR10={curve['10']:.4%}, required>=88%")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/synthetic/amc_v1")
    p.add_argument("--out", default="src/ps/models/weights")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--bs", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--cnn-only", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--input-mode", choices=("raw", "differential"), default="raw")
    p.add_argument("--curriculum-epochs", type=int, default=0)
    p.add_argument("--phase-augment", action="store_true")
    a = p.parse_args()
    train(a.data, a.out, a.epochs, a.bs, a.lr, not a.cnn_only, a.threads, a.smoke, a.input_mode,
          a.curriculum_epochs, a.phase_augment)
