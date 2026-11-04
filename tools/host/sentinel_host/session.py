"""Streaming .zsr sessions; binary blobs are .npy entries in a .npz zip.

No pickle, whole-session buffering or silently substituted synthetic data.
An unfinished recording lacks a verified manifest and cannot be replayed.
"""
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile

import numpy as np


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


class Recorder:
    def __init__(self, path, *, source='live', clock=time.monotonic):
        self.path = Path(path)
        if self.path.suffix != '.zsr':
            raise ValueError('Use a new .zsr directory')
        self.path.mkdir(parents=True, exist_ok=False)
        self.clock, self.started = clock, clock()
        self.index = self.bytes = 0
        self.closed = False
        self.source = source
        self.stream = (self.path/'session.jsonl').open('x', encoding='utf-8')
        self.blobs = zipfile.ZipFile(self.path/'blobs.npz', 'x', compression=zipfile.ZIP_DEFLATED)

    def append(self, header, payload=b''):
        if self.closed or len(payload) != header['len']:
            raise ValueError('Closed session or mismatched payload')
        if self.bytes+len(payload) > 256*1024*1024:
            raise ValueError('Session recording reached 256 MiB; start a new session')
        item = dict(header=header, elapsed_s=self.clock()-self.started)
        if payload:
            key = 'blob_%08d' % self.index
            self.index += 1
            with self.blobs.open(key+'.npy', 'w') as target:
                np.save(target, np.frombuffer(payload, dtype=np.uint8), allow_pickle=False)
            item['blob'] = key
            self.bytes += len(payload)
        self.stream.write(json.dumps(item, allow_nan=False, separators=(',', ':'))+'\n')

    def close(self):
        if self.closed:
            return
        self.stream.close()
        self.blobs.close()
        manifest = dict(schema='zsr/1', source=self.source, binary_bytes=self.bytes,
            blobs=self.index, files_sha256={name:digest(self.path/name) for name in ('session.jsonl', 'blobs.npz')})
        path = self.path/'manifest.json'
        path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        Path(str(path)+'.sha256').write_text(digest(path)+'  manifest.json\n')
        self.closed = True


class Replay:
    def __init__(self, path):
        self.path = Path(path)
        manifest_path = self.path/'manifest.json'
        if digest(manifest_path) != Path(str(manifest_path)+'.sha256').read_text().split()[0]:
            raise ValueError('Session manifest checksum mismatch')
        self.manifest = json.loads(manifest_path.read_text())
        if self.manifest.get('schema') != 'zsr/1':
            raise ValueError('Unknown session format')
        if set(self.manifest['files_sha256']) != {'session.jsonl', 'blobs.npz'}:
            raise ValueError('Unexpected session manifest members')
        for name, sha in self.manifest['files_sha256'].items():
            if digest(self.path/name) != sha:
                raise ValueError('Session data checksum mismatch')

    def __iter__(self):
        previous = -1.
        with (self.path/'session.jsonl').open(encoding='utf-8') as stream, zipfile.ZipFile(self.path/'blobs.npz') as blobs:
            for line in stream:
                if len(line) > 32768:
                    raise ValueError('Session header limit')
                item = json.loads(line)
                if item['elapsed_s'] < previous:
                    raise ValueError('Session time moved backwards')
                previous = item['elapsed_s']
                header = item['header']
                from sentinel.app.hostlink_protocol import checked_header
                checked_header(header)
                payload = b''
                if 'blob' in item:
                    name = item['blob']+'.npy'
                    info = blobs.getinfo(name)
                    if info.file_size > 1024*1024+1024:
                        raise ValueError('Session blob limit')
                    with blobs.open(name) as source:
                        array = np.load(io.BytesIO(source.read()), allow_pickle=False)
                    if array.dtype != np.uint8 or array.ndim != 1:
                        raise ValueError('Unexpected blob dtype/shape')
                    payload = array.tobytes()
                if len(payload) != header['len']:
                    raise ValueError('Session payload length mismatch')
                yield item['elapsed_s'], header, payload
