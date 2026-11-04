"""Atomically publish measurement files after syncing their contents to storage."""
import json
import os
import tempfile
from pathlib import Path


def atomic_write(path, writer):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=str(path.parent),
                                         prefix=path.name+'.', suffix='.tmp',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(str(temporary), 0o644)
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        temporary = None
        if os.name == 'posix':
            directory = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink()


def atomic_json(path, value):
    data = (json.dumps(value, indent=2)+'\n').encode('utf-8')
    atomic_write(path, lambda stream: stream.write(data))
