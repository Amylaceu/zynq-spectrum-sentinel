"""Local AF_UNIX control. Root-only socket, bounded messages, owner-thread MMIO.

Network/UI integration can call the same dispatcher; this socket deliberately
cannot arm or start a transmitter. No shell commands are accepted.
"""
import json
import os
from pathlib import Path
import select
import socket

from .resident import SceneUnavailable, validate_request

SOCKET = '/run/zss_resident_v1.sock'
MAX_REQUEST = 1024


def request(message, path=SOCKET, timeout=12):
    validate_request(message)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(json.dumps(message).encode('utf-8')+b'\n')
        data = bytearray()
        while not data.endswith(b'\n'):
            part = client.recv(4096)
            if not part:
                raise ConnectionError('Resident closed before reply')
            data.extend(part)
            if len(data) > 65536:
                raise ValueError('Oversized resident reply')
    return json.loads(data)


class LocalControl:
    def __init__(self, dispatch, path=SOCKET):
        self.dispatch, self.path = dispatch, Path(path)
        self.socket = None

    def __enter__(self):
        # A stale path must be inspected, not blindly unlinked across owners.
        if self.path.exists():
            raise RuntimeError('Resident socket already exists; inspect owning process')
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.bind(str(self.path))
            os.chmod(str(self.path), 0o600)
            self.socket.listen(4)
        except BaseException:
            self.socket.close()
            self.socket = None
            raise
        return self

    def poll(self):
        if not select.select([self.socket], [], [], 0)[0]:
            return
        connection, _ = self.socket.accept()
        with connection:
            connection.settimeout(.1)
            try:
                data = bytearray()
                while not data.endswith(b'\n'):
                    part = connection.recv(MAX_REQUEST+1-len(data))
                    if not part:
                        raise ValueError('Incomplete resident command')
                    data.extend(part)
                    if len(data) > MAX_REQUEST:
                        raise ValueError('Resident command too long')
                message = json.loads(data)
                validate_request(message)
                result = self.dispatch(message)
                response = dict(ok=True, result=result)
            except (ValueError, SceneUnavailable, socket.timeout) as error:
                response = dict(ok=False, error=str(error))
            try:
                connection.sendall(json.dumps(response).encode('utf-8')+b'\n')
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                # A disconnected local client must not kill the receiver.
                pass

    def __exit__(self, *_):
        if self.socket is not None:
            self.socket.close()
            self.path.unlink()
