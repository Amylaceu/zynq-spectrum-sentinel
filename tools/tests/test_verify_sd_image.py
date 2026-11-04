"""Exercise backup verification with tiny synthetic images, never a real SD."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from tools.verify_sd_image import inspect_image

SCRIPT = Path(__file__).resolve().parents[1] / 'verify_sd_image.py'


@pytest.fixture
def backup(tmp_path):
    image = tmp_path / 'synthetic.img'
    data = bytearray(65536)
    data[510:512] = bytes.fromhex('55aa')
    partitions = [(0x0c, 4096, 8192), (0x83, 16384, 32768)]
    for index, (kind, offset, size) in enumerate(partitions):
        entry = 446 + index * 16
        data[entry + 4] = kind
        struct.pack_into('<II', data, entry + 8, offset // 512, size // 512)
    data[4096 + 510:4096 + 512] = bytes.fromhex('55aa')
    data[16384 + 1024 + 56:16384 + 1024 + 58] = bytes.fromhex('53ef')
    image.write_bytes(data)
    source = {
        'source_size_bytes': len(data),
        'image_path': str(image),
        'partitions': [
            {'PartitionNumber': index + 1, 'Offset': offset, 'Size': size}
            for index, (_, offset, size) in enumerate(partitions)
        ],
    }
    source_path = tmp_path / 'source.json'
    source_path.write_text(json.dumps(source), encoding='utf-8')
    output = tmp_path / 'verification.json'
    return image, source, source_path, output


def run_cli(backup, confirm=True):
    _, _, source_path, output = backup
    command = [sys.executable, str(SCRIPT), '--source-record', str(source_path),
               '--out', str(output)]
    if confirm:
        command.append('--confirm-read-complete')
    return subprocess.run(command, capture_output=True, text=True,
                          encoding='utf-8', timeout=20)


def test_complete_image_has_independently_checked_hash_and_limited_scope(backup):
    image, _, source_path, output = backup
    original = image.read_bytes()
    result = run_cli(backup)
    assert result.returncode == 0, result.stderr + result.stdout
    evidence = json.loads(output.read_text(encoding='utf-8'))
    assert evidence['status'] == 'PASS'
    assert evidence['image_size_bytes'] == len(original)
    assert evidence['image_sha256'] == hashlib.sha256(original).hexdigest()
    assert evidence['source_record_sha256'] == hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert evidence['restore_tested'] is False
    assert evidence['filesystem_health_verified'] is False
    assert evidence['source_disk_writes'] is False
    sidecar = Path(str(output) + '.sha256').read_text(encoding='ascii')
    assert sidecar.split()[0] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert image.read_bytes() == original


@pytest.mark.parametrize('length', [0, 512, 65535, 65537])
def test_rejects_partial_or_wrong_capacity_image(backup, length):
    image, source, _, _ = backup
    with image.open('r+b') as handle:
        handle.truncate(length)
    with pytest.raises(ValueError, match='whole card'):
        inspect_image(image, source)


@pytest.mark.parametrize('offset, message', [
    (510, 'MBR signature'),
    (4096 + 510, 'FAT boot-sector'),
    (16384 + 1024 + 56, 'superblock'),
])
def test_rejects_broken_partition_signatures(backup, offset, message):
    image, source, _, _ = backup
    with image.open('r+b') as handle:
        handle.seek(offset)
        handle.write(bytes(2))
    with pytest.raises(ValueError, match=message):
        inspect_image(image, source)


def test_rejects_different_partition_layout(backup):
    image, source, _, _ = backup
    source['partitions'][1]['Offset'] += 512
    with pytest.raises(ValueError, match='layout'):
        inspect_image(image, source)


def test_rejects_partition_beyond_whole_image(backup):
    image, source, _, _ = backup
    with image.open('r+b') as handle:
        handle.seek(446 + 16 + 12)
        handle.write(struct.pack('<I', 4096))
    with pytest.raises(ValueError, match='exceeds'):
        inspect_image(image, source)


def test_failure_creates_fail_evidence_without_claiming_backup_hash(backup):
    image, _, _, output = backup
    image.write_bytes(b'incomplete')
    result = run_cli(backup)
    assert result.returncode == 1
    evidence = json.loads(output.read_text(encoding='utf-8'))
    assert evidence['status'] == 'FAIL'
    assert 'image_sha256' not in evidence
    assert Path(str(output) + '.sha256').is_file()
    assert image.read_bytes() == b'incomplete'


def test_requires_human_read_completion_confirmation(backup):
    _, _, _, output = backup
    result = run_cli(backup, confirm=False)
    assert result.returncode != 0
    assert '--confirm-read-complete' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('existing_suffix', ['', '.sha256'])
def test_preserves_existing_evidence(backup, existing_suffix):
    _, _, _, output = backup
    existing = Path(str(output) + existing_suffix)
    existing.write_bytes(b'keep previous evidence')
    result = run_cli(backup)
    assert result.returncode != 0
    assert 'Output already exists' in result.stderr
    assert existing.read_bytes() == b'keep previous evidence'
