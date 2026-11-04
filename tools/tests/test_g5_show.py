"""The show shortcut must keep demo safety and disclose missing playback."""
import json
from types import SimpleNamespace

import pytest

from tools.tests.test_release_board_f1 import entry, ROOT


def args(**changes):
    value = dict(command='show', group='A', segment=None, loop=False, cycles=3,
                 ui='v3', source='live', antenna_confirmed=None)
    value.update(changes)
    return SimpleNamespace(**value)


def command(tmp_path, **changes):
    config = json.loads((ROOT/'board/release/config.yaml').read_text())
    return entry().worker_command(tmp_path, config, args(**changes), tmp_path/'out')


def test_show_a_keeps_persistent_demo_and_records_wav_request(tmp_path):
    result = command(tmp_path)
    assert str(tmp_path/'scripts/demo_a.py') in result
    assert '--hostlink' in result and result[result.index('--ui')+1] == 'v3'
    assert result[result.index('--record-audio')+1] == str(tmp_path/'out/playback.wav')
    assert result[result.index('--cycles')+1] == '3'


def test_show_b_still_requires_fresh_confirmation(tmp_path):
    with pytest.raises(ValueError, match='confirmation'):
        command(tmp_path, group='B')
    result = command(tmp_path, group='B', antenna_confirmed='yes', segment=6)
    assert str(tmp_path/'scripts/demo_b.py') in result and '--hostlink' in result
    assert '--record-audio' not in result
    assert result[result.index('--segment')+1] == '6'


@pytest.mark.parametrize('changes', [dict(source='replay'), dict(isolated=True), dict(ui='v2')])
def test_unavailable_source_or_incompatible_mode_fails_before_launch(tmp_path, changes):
    with pytest.raises(ValueError):
        command(tmp_path, **changes)
