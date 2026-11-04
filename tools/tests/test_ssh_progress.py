import subprocess
import sys
import pytest
import x2_transport

@pytest.mark.parametrize('fail', [False, True])
def test_progress_is_delivered_before_command_exit(monkeypatch, fail):
    real_popen = subprocess.Popen
    script = "import sys;print('first',flush=True);print('second',flush=True);sys.exit(%d)" % int(fail)
    def launch(argv, **kwargs):
        return real_popen([sys.executable, '-c', script], **kwargs)
    monkeypatch.setattr(x2_transport, 'board_identity', lambda: 'test-only')
    monkeypatch.setattr(x2_transport.subprocess, 'Popen', launch)
    t = x2_transport.Transport()
    lines = []
    if fail:
        with pytest.raises(RuntimeError):
            t.ssh_lines(['unused'], lines.append)
    else:
        t.ssh_lines(['unused'], lines.append)
    assert lines == ['first\n', 'second\n']
