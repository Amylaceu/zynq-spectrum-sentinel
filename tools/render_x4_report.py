"""E7: historical v1 curve vs explicitly different 4096-point v2 dataset."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from x2_transport import ROOT, verified, sha, write_evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1,2,3), required=True)
    args = p.parse_args()
    source = ROOT/'board/measurements'/('x4_analysis_r'+str(args.attempt)+'.json')
    result = verified(source)
    baseline = ROOT/'src/ps/models/weights/amc_v1_metrics.json'
    historical = json.loads(baseline.read_text())
    metrics = result['metrics']
    output = ROOT/'report/figures'
    output.mkdir(exist_ok=True)
    prefix = 'e7_x4_r'+str(args.attempt)
    files = {}
    fig, ax = plt.subplots(figsize=(10, 5.2))
    snrs = list(range(-4,21,2))
    for label, curve in (
        ('v1 historical: 1024 samples, 10 classes',historical['accuracy_vs_snr']),
        ('v2 FP32: 4096 samples, 10 classes',metrics['fp32']['accuracy_vs_snr']),
        ('v2 INT8: 4096 samples, 10 classes',metrics['int8']['accuracy_vs_snr']),
        ('v2 INT8: 8 coarse classes',metrics['int8']['coarse_accuracy_vs_snr'])):
        ax.plot(snrs,[100*curve[str(s)] for s in snrs],marker='o',label=label)
    ax.axvline(10, color='gray', linestyle=':', linewidth=1)
    ax.set(xlabel='Occupied-bandwidth SNR (dB)', ylabel='Accuracy (%)', ylim=(0,102),
           title='E7: synthetic AMC; historical comparison, different capture lengths')
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.text(.5,.01,'Historical v1 and v2 use different waveforms/capture lengths; not a paired same-input speed or accuracy test.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1))
    target = output/(prefix+'_snr.png')
    fig.savefig(target,dpi=150); plt.close(fig)
    files[target.relative_to(ROOT).as_posix()] = sha(target)
    matrix = np.asarray(metrics['int8']['confusion_snr10'])
    names = ('BPSK','QPSK','8PSK','16QAM','64QAM','2FSK','GFSK','OOK','AM','FM')
    fig, ax = plt.subplots(figsize=(9,8))
    image = ax.imshow(matrix/matrix.sum(1,keepdims=True),vmin=0,vmax=1,cmap='Blues')
    for row in range(10):
        for col in range(10):
            ax.text(col,row,str(matrix[row,col]),ha='center',va='center',fontsize=7,
                    color='white' if matrix[row,col]/matrix[row].sum() > .55 else 'black')
    ax.set(xticks=range(10),yticks=range(10),xticklabels=names,yticklabels=names,
           xlabel='Predicted',ylabel='True',title='v2 INT8 confusion at SNR=10 dB (counts; color=row ratio)')
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    fig.colorbar(image,ax=ax,fraction=.046)
    fig.tight_layout()
    target = output/(prefix+'_confusion.png')
    fig.savefig(target,dpi=150); plt.close(fig)
    files[target.relative_to(ROOT).as_posix()] = sha(target)
    write_evidence(ROOT/'board/measurements'/('x4_report_r'+str(args.attempt)+'.json'),
                   dict(analysis_sha256=sha(source),historical_sha256=sha(baseline),
                        generator_sha256=sha(Path(__file__)), outputs_sha256=files))
    print(json.dumps(files,indent=2))


if __name__ == '__main__':
    main()
