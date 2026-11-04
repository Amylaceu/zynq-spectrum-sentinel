"""Strict SSH and immutable evidence helpers; no hardware activity on import."""
import json
from pathlib import Path
import shlex
import subprocess
import queue
import tempfile
import threading
import time

from deploy_x1 import board_identity
from run_x1_board import ROOT, REMOTE, PYTHON, OPTIONS, sha, write_evidence


def verified(path):
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence digest mismatch: '+str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def remote_name(name):
    if name.startswith('src/ps/'):
        return name[4:]
    if name.startswith('board/'):
        return name[6:]
    if name.startswith('data/reference/'):
        return name
    raise ValueError('Not a deployable path: '+name)


class Transport:
    def __init__(self, password=None):
        self.target = board_identity()
        self.password = password

    def privileged(self, command):
        return ['sudo', '-S', '-p', '']+command if self.password else ['sudo', '-n']+command

    def ssh(self, command, payload=None, privileged=False, timeout=60):
        if privileged:
            command = self.privileged(command)
            payload = self.password+'\n' if self.password else None
        if not isinstance(command, str):
            command = shlex.join(command)
        result = subprocess.run(['ssh', *OPTIONS, self.target, command], input=payload,
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('SSH exit %d: %s' % (result.returncode, result.stderr[-1800:]))
        return result.stdout

    def copy(self, source, destination):
        subprocess.run(['scp', *OPTIONS, str(source), str(destination)], check=True, timeout=90)

    def ssh_lines(self, command, on_line, privileged=False, timeout=700):
        """Deliver flushed board progress immediately; keep stderr off the pipe.

        A transport timeout only closes SSH. It does not reset hardware or free
        a possibly owned board DMA buffer; independent postflight is required.
        """
        if privileged:
            command = self.privileged(command)
        payload = self.password+'\n' if privileged and self.password else None
        command = shlex.join(command) if not isinstance(command, str) else command
        with tempfile.TemporaryFile() as errors:
            child = subprocess.Popen(['ssh', *OPTIONS, self.target, command],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                text=True, encoding='utf-8', errors='replace')
            pending = queue.Queue(maxsize=32)
            stopped = threading.Event()
            def enqueue(value):
                while not stopped.is_set():
                    try:
                        pending.put(value, timeout=.2)
                        return
                    except queue.Full:
                        pass
            def read_lines():
                try:
                    for line in child.stdout:
                        enqueue(line)
                        if stopped.is_set():
                            break
                finally:
                    enqueue(None)
            threading.Thread(target=read_lines, daemon=True).start()
            deadline = time.monotonic()+timeout
            try:
                if payload:
                    child.stdin.write(payload)
                child.stdin.close()
                while True:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('SSH progress deadline expired; inspect board ownership')
                    try:
                        line = pending.get(timeout=min(.5, remaining))
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    on_line(line)
                child.wait(timeout=max(.1, deadline-time.monotonic()))
                if child.returncode:
                    errors.seek(0)
                    raise RuntimeError('SSH exit %d: %s' %
                                       (child.returncode, errors.read()[-1800:].decode('utf-8', 'replace')))
            finally:
                stopped.set()
                if child.poll() is None:
                    child.kill()
                child.wait()

    def check_files(self, files):
        script = """import hashlib,json,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root'])
for name,digest in p['files'].items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Board file differs: '+name)
print('X2_BOARD_FILES_VERIFIED')
"""
        return self.ssh(['python3', '-c', script], payload=json.dumps(dict(root=REMOTE, files=files)))

    def postflight(self):
        return json.loads(self.ssh([PYTHON, '-I', REMOTE+'/scripts/x2_postflight.py'], privileged=True))
