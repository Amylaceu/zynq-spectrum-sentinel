"""Validate a completed whole-card image without modifying image or source SD."""
import argparse
import hashlib
import json
import os
import struct
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write(chr(10))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if path.exists():
            raise FileExistsError('Preserve existing evidence: ' + str(path))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def inspect_image(path, source):
    expected_size = int(source['source_size_bytes'])
    if path.stat().st_size != expected_size:
        raise ValueError('Image must contain the whole card: expected %d bytes, got %d' % (expected_size, path.stat().st_size))
    with path.open('rb') as handle:
        mbr = handle.read(512)
        if mbr[510:512] != bytes.fromhex('55aa'):
            raise ValueError('Invalid MBR signature')
        partitions = []
        for index in range(4):
            entry = mbr[446 + 16 * index:462 + 16 * index]
            kind = entry[4]
            lba, sectors = struct.unpack_from('<II', entry, 8)
            if kind and sectors:
                offset, size = lba * 512, sectors * 512
                if offset + size > expected_size:
                    raise ValueError('Partition exceeds image length')
                partitions.append({'partition_number': index + 1, 'mbr_type': kind, 'offset': offset, 'size': size})
        expected = [(int(x['Offset']), int(x['Size'])) for x in source['partitions']]
        actual = [(x['offset'], x['size']) for x in partitions]
        if actual != expected:
            raise ValueError('Image partition layout does not match the verified card: %r' % actual)
        if len(partitions) != 2 or partitions[0]['mbr_type'] not in (0x06, 0x0b, 0x0c, 0x0e) or partitions[1]['mbr_type'] != 0x83:
            raise ValueError('Expected FAT boot and Linux root partitions')
        handle.seek(partitions[0]['offset'] + 510)
        if handle.read(2) != bytes.fromhex('55aa'):
            raise ValueError('Invalid FAT boot-sector signature')
        handle.seek(partitions[1]['offset'] + 1024 + 56)
        if handle.read(2) != bytes.fromhex('53ef'):
            raise ValueError('Missing ext filesystem superblock magic')
    return partitions

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--source-record', type=Path, default=ROOT / 'docs/x0_sd_source.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/sd_backup_verification.json')
    parser.add_argument('--confirm-read-complete', action='store_true', required=True, help='Use only after the human operator confirms whole-card Read completed.')
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() or Path(str(output) + '.sha256').exists():
        parser.error('Output already exists; choose a new output name')
    source_bytes = args.source_record.read_bytes()
    source = json.loads(source_bytes.decode('utf-8-sig'))
    image = (args.image or Path(source['image_path'])).resolve()
    if not image.is_file():
        parser.error('Image file does not exist: ' + str(image))
    result = {'status': 'STARTED', 'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'image_path': str(image), 'source_record_sha256': hashlib.sha256(source_bytes).hexdigest(),
              'operator_reported_read_complete': True, 'source_disk_writes': False,
              'restore_tested': False, 'filesystem_health_verified': False,
              'scope': 'Image size, partition signatures and SHA256; does not prove error-free filesystems or a successful restore.'}
    try:
        before = image.stat()
        result['partitions'] = inspect_image(image, source)
        digest = hashlib.sha256()
        processed, last_report = 0, time.monotonic()
        with image.open('rb') as handle:
            while True:
                chunk = handle.read(8 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                processed += len(chunk)
                if time.monotonic() - last_report >= 5:
                    print('SHA256: %d / %d bytes (%.1f%%)' % (processed, before.st_size, processed * 100 / before.st_size), flush=True)
                    last_report = time.monotonic()
        after = image.stat()
        if processed != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Image changed during verification; wait for Read to finish')
        result.update(status='PASS', image_size_bytes=processed, image_sha256=digest.hexdigest())
    except Exception as error:
        result.update(status='FAIL', error=str(error))
    atomic_json(output, result)
    sidecar = Path(str(output) + '.sha256')
    with sidecar.open('x', encoding='ascii') as handle:
        handle.write(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + chr(10))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
