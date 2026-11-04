"""Compact 8-class CNN + HOC, trained only on the train split."""
import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from src.ps.sentinel.amc.contract import COARSE_MAP, COARSE_CLASSES, SCHEMA
from .make_dataset_v2 import sha


class AMCLevel1(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv1d(4, 8, 7, stride=2)
        self.bn1 = nn.BatchNorm1d(8)
        self.conv2 = nn.Conv1d(8, 12, 5, stride=2)
        self.bn2 = nn.BatchNorm1d(12)
        self.conv3 = nn.Conv1d(12, 16, 3, stride=2)
        self.bn3 = nn.BatchNorm1d(16)
        self.hoc_fc = nn.Linear(24, 24)
        self.fuse = nn.Linear(40, 32)
        self.output = nn.Linear(32, 8)
        self.register_buffer('feature_mean', torch.zeros(24))
        self.register_buffer('feature_std', torch.ones(24))

    def forward(self, front, features):
        x = torch.relu(self.bn1(self.conv1(front)))
        x = torch.relu(self.bn2(self.conv2(x)))
        x = torch.relu(self.bn3(self.conv3(x))).mean(dim=2)
        h = torch.relu(self.hoc_fc((features-self.feature_mean)/self.feature_std))
        return self.output(torch.relu(self.fuse(torch.cat((x, h), dim=1))))


class Captures(Dataset):
    def __init__(self, directory):
        directory = Path(directory)
        self.front = np.load(directory/'front.npy', mmap_mode='r')
        self.features = np.load(directory/'features.npy', mmap_mode='r')
        self.labels = np.load(directory/'label.npy', mmap_mode='r')
        self.snrs = np.load(directory/'snr.npy', mmap_mode='r')
        self.coarse = np.asarray(COARSE_MAP)[self.labels]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, index):
        return (np.array(self.front[index]), np.array(self.features[index]),
                int(self.coarse[index]), int(self.snrs[index]))


def train(data, out, epochs=30, batch_size=512, threads=8, seed=20261103,
          smoke=False, lr=.002):
    torch.set_num_threads(threads)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    data, out = Path(data), Path(out)
    manifest = json.loads((data/'manifest.json').read_text())
    if manifest['schema'] != SCHEMA or manifest['smoke_only'] != smoke:
        raise ValueError('Dataset schema or smoke mode mismatch')
    if not smoke and manifest['per_cell'] != 2000:
        raise ValueError('Production requires exactly 2000 captures per class/SNR')
    out.mkdir(parents=True, exist_ok=False)
    # Verify training and validation inputs before using them. Test is untouched.
    for split in ('train', 'val'):
        for key in ('front', 'features', 'label', 'snr', 'sample_id'):
            rel = split+'/'+key+'.npy'
            if sha(data/rel) != manifest['files'][rel]:
                raise ValueError('Dataset digest mismatch: '+rel)
    training, validation = Captures(data/'train'), Captures(data/'val')
    model = AMCLevel1()
    model.feature_mean.copy_(torch.from_numpy(training.features.mean(0)))
    model.feature_std.copy_(torch.from_numpy(training.features.std(0).clip(1e-4)))
    batches = DataLoader(training, batch_size=batch_size, shuffle=True, num_workers=0)
    val_batches = DataLoader(validation, batch_size=batch_size, num_workers=0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    history, best, start = [], -1., time.monotonic()
    checkpoint = out/'amc_l1_fp32.pt'
    # Every original class has equal count; coarse PSK/QAM each have double
    # count. Original 10-class weighting is retained, not secretly rebalanced.
    for epoch in range(epochs):
        model.train()
        loss_sum = 0.
        for front, features, target, _ in batches:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(front, features), target)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            loss_sum += loss.item()*len(target)
        schedule.step()
        model.eval()
        correct, total, high_correct, high_total = 0, 0, 0, 0
        with torch.inference_mode():
            for front, features, target, snr in val_batches:
                hit = model(front, features).argmax(1) == target
                correct += int(hit.sum()); total += len(target)
                high_correct += int(hit[snr == 10].sum()); high_total += int((snr == 10).sum())
        row = dict(epoch=epoch+1, loss=loss_sum/len(training), val_accuracy=correct/total,
                   val_snr10=high_correct/high_total, elapsed_s=time.monotonic()-start)
        history.append(row)
        print(json.dumps(row), flush=True)
        (out/'history.json').write_text(json.dumps(history, indent=2)+'\n', encoding='utf-8')
        if row['val_accuracy'] > best:
            best = row['val_accuracy']
            torch.save(dict(state_dict=model.state_dict(), schema=SCHEMA, seed=seed,
                            smoke_only=smoke, epoch=epoch+1, val_accuracy=best,
                            classes=COARSE_CLASSES, dataset_sha256=sha(data/'manifest.json')),
                       out/'checkpoint.tmp')
            (out/'checkpoint.tmp').replace(checkpoint)
    print('TRAIN_COMPLETE '+sha(checkpoint), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data/synthetic/amc_v2')
    parser.add_argument('--out', required=True)
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--bs', type=int, default=512)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--seed', type=int, default=20261103)
    parser.add_argument('--lr', type=float, default=.002)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    train(args.data, args.out, args.epochs, args.bs, args.threads, args.seed, args.smoke, args.lr)
