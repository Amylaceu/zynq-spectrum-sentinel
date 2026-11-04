"""Small IQ-CNN + fixed-moment HOC fusion network from the project runbook."""

import torch
from torch import nn
from torch.nn import functional as F


class AMCNet(nn.Module):
    def __init__(self, classes=10, use_hoc=True, input_mode="raw"):
        super().__init__()
        if input_mode not in ("raw", "differential"):
            raise ValueError("Unknown IQ input representation")
        self.use_hoc = use_hoc
        self.input_mode = input_mode
        self.conv1, self.bn1 = nn.Conv1d(2, 16, 7, stride=2), nn.BatchNorm1d(16)
        self.conv2, self.bn2 = nn.Conv1d(16, 32, 5), nn.BatchNorm1d(32)
        self.conv3, self.bn3 = nn.Conv1d(32, 48, 3), nn.BatchNorm1d(48)
        self.hoc_fc = nn.Linear(8, 16) if use_hoc else None
        self.fuse, self.output = nn.Linear(64, 32), nn.Linear(32, classes)
        self.dropout = nn.Dropout(0.3)
        self.register_buffer("hoc_mean", torch.zeros(8))
        self.register_buffer("hoc_std", torch.ones(8))

    @staticmethod
    def normalize_iq(iq, input_mode="raw"):
        x = iq.float()
        x = x - x.mean(dim=2, keepdim=True)
        rms = torch.sqrt(x.square().sum(dim=1, keepdim=True).mean(dim=2, keepdim=True)).clamp_min(1e-8)
        x = x / rms
        if input_mode == "differential":
            # z[n]*conj(z[n-1]): constant carrier phase cancels; CFO becomes a
            # constant rotation, rather than a ramp across the entire capture.
            re = x[:, 0, 1:] * x[:, 0, :-1] + x[:, 1, 1:] * x[:, 1, :-1]
            im = x[:, 1, 1:] * x[:, 0, :-1] - x[:, 0, 1:] * x[:, 1, :-1]
            x = F.pad(torch.stack((re, im), dim=1), (1, 0))
            rms = torch.sqrt(x.square().sum(dim=1, keepdim=True).mean(dim=2, keepdim=True)).clamp_min(1e-8)
            x = x / rms
        return x

    def forward(self, iq, hoc):
        x = self.normalize_iq(iq, self.input_mode)
        x = F.max_pool1d(F.relu(self.bn1(self.conv1(x))), 2)
        x = F.max_pool1d(F.relu(self.bn2(self.conv2(x))), 2)
        x = F.relu(self.bn3(self.conv3(x))).mean(dim=2)
        if self.use_hoc:
            h = (torch.log1p(hoc.float().clamp_min(0)) - self.hoc_mean) / self.hoc_std
            h = F.relu(self.hoc_fc(h))
        else:
            h = x.new_zeros((len(x), 16))
        return self.output(self.dropout(F.relu(self.fuse(torch.cat((x, h), dim=1)))))
