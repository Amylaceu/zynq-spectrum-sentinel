"""Fold BN into convolution, export per-output-channel symmetric INT8 weights.

Activations use dynamic symmetric INT8 and signed INT32 accumulation in the
NumPy runtime. Bias, scale, global pooling and softmax remain FP32. This is
mixed precision and is documented as such, not an all-integer NPU export.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from .amc_l1 import AMCLevel1
from .make_dataset_v2 import sha
from src.ps.sentinel.amc.contract import SCHEMA


def export(checkpoint, out):
    checkpoint, out = Path(checkpoint), Path(out)
    if out.exists():
        raise FileExistsError('Preserve previous export')
    chosen = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if chosen['schema'] != SCHEMA:
        raise ValueError('Checkpoint contract mismatch')
    model = AMCLevel1().eval()
    model.load_state_dict(chosen['state_dict'])
    arrays = {key: value.detach().numpy() for key, value in (
        ('feature_mean', model.feature_mean), ('feature_std', model.feature_std))}
    for index in range(1, 4):
        conv = getattr(model, 'conv'+str(index))
        bn = getattr(model, 'bn'+str(index))
        fused = torch.nn.utils.fusion.fuse_conv_bn_eval(conv, bn)
        arrays['conv'+str(index)+'.weight'] = fused.weight.detach().numpy()
        arrays['conv'+str(index)+'.bias'] = fused.bias.detach().numpy()
    for name in ('hoc_fc', 'fuse', 'output'):
        layer = getattr(model, name)
        arrays[name+'.weight'] = layer.weight.detach().numpy()
        arrays[name+'.bias'] = layer.bias.detach().numpy()
    for name in tuple(arrays):
        if name.endswith('.weight'):
            weight = arrays[name]
            axes = tuple(range(1, weight.ndim))
            scale = np.max(np.abs(weight), axis=axes).clip(1e-12)/127
            arrays[name+'.scale'] = scale.astype(np.float32)
            arrays[name+'.int8'] = np.clip(np.rint(weight/scale.reshape((-1,)+(1,)*(weight.ndim-1))),
                                          -127, 127).astype(np.int8)
    arrays['metadata'] = np.asarray(json.dumps(dict(
        schema=SCHEMA, checkpoint_sha256=sha(checkpoint), smoke_only=chosen['smoke_only'],
        quantization='per-output-channel INT8 weights; dynamic INT8 activation; INT32 MAC; FP32 bias/scales/pool/softmax',
        dataset_sha256=chosen['dataset_sha256'])))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as stream:
        np.savez_compressed(stream, **arrays)
    Path(str(out)+'.sha256').write_text(sha(out)+'  '+out.name+'\n', encoding='ascii')
    print('EXPORT_COMPLETE '+sha(out), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    export(args.checkpoint, args.out)
